"""قالب‌ها و ابزارهای مشترک نمایش: یک نمونهٔ Jinja2 با فیلترها و متغیرهای سراسری.

هم صفحه‌های کاربر و هم پنل ادمین از همین نمونه استفاده می‌کنند تا فیلترهایی مثل
`fa` (ارقام فارسی) و `icon` (آیکون Font Awesome) همه‌جا یکسان کار کنند.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict

from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from . import static_content
from .content import astrology, lexicon
from .content import methods as method_catalogue
from .content import personality as test_catalogue
from .content import fortunes as fortune_pool
from .forms import GENDERS
from .utils import MONTHS_FA, to_fa

BASE_DIR = Path(__file__).resolve().parent

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


_asset_cache: Dict[str, Any] = {"value": "1", "at": 0.0}


def asset_version() -> str:
    """شمارهٔ نسخهٔ دارایی‌های استاتیک، از روی زمان آخرین تغییر CSS/JS.

    مرورگرها فایل‌های استاتیک را سخت کش می‌کنند؛ اگر آدرس ثابت بماند، کاربر بعد از
    هر تغییر، استایل قدیمی را می‌بیند (باگی که ظاهر سایت را به‌هم می‌ریخت). با
    افزودن `?v=`، آدرس با هر تغییر عوض می‌شود و کش بی‌اثر می‌گردد.

    نتیجه چند ثانیه کش می‌شود تا هر درخواست مجبور به گشتن فایل‌ها نباشد، ولی بعد از
    ویرایش CSS/JS بدون ری‌استارت سرور هم تازه می‌شود.
    """
    import time

    now = time.monotonic()
    if _asset_cache["at"] and now - float(_asset_cache["at"]) < 3.0:
        return str(_asset_cache["value"])

    latest = 0.0
    for path in (BASE_DIR / "static").rglob("*"):
        if path.suffix in {".css", ".js"} and path.is_file():
            latest = max(latest, path.stat().st_mtime)
    _asset_cache["value"] = str(int(latest)) if latest else "1"
    _asset_cache["at"] = now
    return str(_asset_cache["value"])


def icon_html(value: object, extra: str = "") -> Markup:
    """رشتهٔ آیکون را به تگ Font Awesome یا گلیف متنی تبدیل می‌کند."""
    text = str(value or "").strip()
    if not text:
        return Markup("")
    if text.startswith("fa-"):
        classes = f"{text} {extra}".strip()
        return Markup(f'<i class="{classes}" aria-hidden="true"></i>')
    return Markup(f'<span class="glyph {extra}">{text}</span>')


def mask_phone(phone: str) -> str:
    digits = str(phone or "")
    if len(digits) < 11:
        return to_fa(digits)
    return to_fa(f"{digits[:4]}***{digits[-4:]}")


templates.env.filters["fa"] = to_fa
templates.env.filters["icon"] = icon_html
templates.env.filters["mask_phone"] = mask_phone
templates.env.globals.update(
    METHODS=method_catalogue.METHODS,
    METHOD_ORDER=method_catalogue.METHOD_ORDER,
    METHOD_GROUPS=method_catalogue.METHOD_GROUPS,
    TESTS=test_catalogue.TESTS,
    TEST_ORDER=test_catalogue.TEST_ORDER,
    TEST_GROUPS=test_catalogue.TEST_GROUPS,
    TOPICS=lexicon.TOPICS,
    TOPIC_ORDER=lexicon.TOPIC_ORDER,
    GENDERS=GENDERS,
    MONTHS_FA=MONTHS_FA,
    SIGNS=astrology.SIGNS,
    TESTIMONIALS=static_content.TESTIMONIALS,
    HIGHLIGHTS=static_content.HIGHLIGHTS,
    FAQ=static_content.FAQ,
    FORTUNE_POOL=fortune_pool,
    ASSET_VERSION=asset_version,
)


def _collect_toasts(request: Any, context: dict) -> list:
    """همهٔ پیام‌هایی که باید به‌شکل توست دیده شوند را یک‌جا جمع می‌کند.

    سه سرچشمه دارد:
      ۱. پیام‌های فلشی که از درخواست قبلی به ارث رسیده (نتیجهٔ یک ریدایرکت).
      ۲. متن خطاهایی که صفحات فرم در `errors` می‌گذارند — این‌جا خودکار به توست
         تبدیل می‌شوند، پس هر صفحهٔ خطا در کل برنامه انیمیشن می‌گیرد بی‌آنکه لازم
         باشد هر مسیر را جداگانه دست بزنیم.
      ۳. توست‌های دستیِ خودِ مسیر (`toasts`).
    """
    from . import flash

    items: list = []
    for entry in flash.from_request(request) or []:
        if isinstance(entry, dict):
            items.append(entry)
        elif entry:
            items.append({"message": str(entry), "kind": "info", "title": ""})

    for entry in context.get("toasts") or []:
        if isinstance(entry, dict):
            items.append(entry)
        elif entry:
            items.append({"message": str(entry), "kind": "info", "title": ""})

    # خطاهای فرم هم توست می‌شوند (فقط اگر همین خطا در «پیام» تکراری نباشد).
    seen = {str(item.get("message") or "") for item in items}
    for error in context.get("errors") or []:
        text = " ".join(str(error or "").split())
        if not text or text in seen:
            continue
        seen.add(text)
        items.append({"message": text[:300], "kind": "error", "title": ""})

    cleaned = []
    for item in items[: flash.MAX_ITEMS]:
        normalized = flash.normalize(item.get("message"), str(item.get("kind") or "info"), str(item.get("title") or ""))
        if normalized:
            cleaned.append(normalized)
    return cleaned


def render(request, template: str, context: dict, status_code: int = 200) -> Any:
    """صفحه را با پیام‌های توستِ جمع‌آوری‌شده رندر می‌کند (تنها راه رندر صفحات)."""
    context = dict(context or {})
    context["toasts"] = _collect_toasts(request, context)
    return templates.TemplateResponse(request, template, context, status_code=status_code)
