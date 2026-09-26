"""پیام‌های کوتاه (flash): پیامی که از یک درخواست به درخواست بعدی می‌رود.

الگوی رایج در وب «POST → Redirect → GET» است: سرور کاربر را به صفحهٔ دیگری می‌فرستد
و دیگر نمی‌تواند داخل همان پاسخ پیام بگذارد. این ماژول پیام را در یک کوکی کوچک
می‌گذارد؛ صفحهٔ بعدی آن را می‌خواند و به‌شکل توستِ انیمیشنی نشان می‌دهد و کوکی پاک
می‌شود. پس نه پیام گم می‌شود و نه با رفرش تکرار.

پیام‌ها کوتاه و محدود نگه داشته می‌شوند (طول + تعداد) تا کوکی از سقف مرورگر رد نشود
و کسی نتواند با آن حجم زیادی داده به صفحه تزریق کند.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import Any, Dict, List, Optional

from fastapi import Request
from fastapi.responses import RedirectResponse, Response

COOKIE = "nsh_flash"

# حداکثر اندازه‌ها: سه پیام، هر کدام ۳۰۰ کاراکتر. کوکی مرورگر ۴KB است و ما عمداً
# خیلی زیر آن می‌مانیم تا جای دیگر هم بماند.
MAX_ITEMS = 3
MAX_MESSAGE = 300
MAX_TITLE = 60

KINDS = ("success", "error", "warning", "info")

# آیکون هر نوع پیام؛ هم در HTML و هم در JS همین نگاشت استفاده می‌شود.
ICONS = {
    "success": "fa-solid fa-circle-check",
    "error": "fa-solid fa-circle-exclamation",
    "warning": "fa-solid fa-triangle-exclamation",
    "info": "fa-solid fa-circle-info",
}

# عنوان پیش‌فرض هر نوع، اگر فراخوان عنوانی نداده باشد.
DEFAULT_TITLES = {
    "success": "انجام شد",
    "error": "نشد",
    "warning": "حواست باشد",
    "info": "یک نکته",
}


def _clip(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def normalize(message: Any, kind: str = "info", title: str = "") -> Optional[Dict[str, str]]:
    """پیام خام را به ساختار امن و یکدست تبدیل می‌کند (یا ``None`` اگر خالی باشد)."""
    text = _clip(message, MAX_MESSAGE)
    if not text:
        return None
    kind = kind if kind in KINDS else "info"
    return {
        "message": text,
        "kind": kind,
        "title": _clip(title, MAX_TITLE) or DEFAULT_TITLES[kind],
    }


def _encode(items: List[Dict[str, str]]) -> str:
    payload = json.dumps(items[:MAX_ITEMS], ensure_ascii=False, separators=(",", ":"))
    return urllib.parse.quote(payload, safe="")


def decode(raw: Optional[str]) -> List[Dict[str, str]]:
    """کوکی را به فهرست پیام‌های سالم تبدیل می‌کند (هر دادهٔ خرابی نادیده گرفته می‌شود)."""
    if not raw:
        return []
    try:
        data = json.loads(urllib.parse.unquote(raw))
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    items: List[Dict[str, str]] = []
    for entry in data:
        if isinstance(entry, str):
            entry = {"message": entry, "kind": "info"}
        if not isinstance(entry, dict):
            continue
        item = normalize(entry.get("message"), str(entry.get("kind") or "info"), str(entry.get("title") or ""))
        if item:
            items.append(item)
    return items[:MAX_ITEMS]


def add(response: Response, message: Any, kind: str = "info", title: str = "") -> Response:
    """پیام را به پاسخ اضافه می‌کند (روی همان پاسخ، برای زنجیرهٔ ریدایرکت).

    پیام‌ها روی خود شیء پاسخ جمع می‌شوند تا چند بار صدا زدن این تابع، پیام‌های
    قبلی را از دست ندهد.
    """
    item = normalize(message, kind, title)
    if not item:
        return response
    items = list(getattr(response, "_flash_items", []) or [])
    items.append(item)
    response._flash_items = items[-MAX_ITEMS:]  # type: ignore[attr-defined]
    response.set_cookie(
        COOKIE,
        _encode(response._flash_items),  # type: ignore[attr-defined]
        max_age=120,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


def attach(response: Response, messages: Any) -> Response:
    """چند پیام را یک‌جا روی پاسخ می‌گذارد (فهرست رشته یا دیکشنری)."""
    if not messages:
        return response
    if isinstance(messages, (str, dict)):
        messages = [messages]
    for entry in messages:
        if isinstance(entry, dict):
            add(response, entry.get("message"), str(entry.get("kind") or "info"), str(entry.get("title") or ""))
        else:
            add(response, entry, "info")
    return response


def redirect(url: str, message: Any = "", kind: str = "info", title: str = "") -> RedirectResponse:
    """ریدایرکت همراه با پیام — جایگزین کوتاه `RedirectResponse` در مسیرها."""
    response = RedirectResponse(url, status_code=303)
    if message:
        add(response, message, kind, title)
    return response


def from_request(request: Request) -> List[Dict[str, str]]:
    """پیام‌های همراهِ این درخواست، چه از وسط‌کار (state) و چه از کوکی."""
    cached = getattr(request.state, "flash", None)
    if cached is not None:
        return list(cached)
    return decode(request.cookies.get(COOKIE))


def clear(response: Response) -> Response:
    response.delete_cookie(COOKIE, path="/")
    return response
