"""لایهٔ مدل زبانی: جمینای به‌عنوان ارائه‌دهندهٔ اصلی و گروک/Groq به‌عنوان پشتیبان.

طراحی با سه اصل:

1. **هرگز کاربر را معطل نمی‌گذارد.** هر تماس سقف زمانی دارد و اگر همهٔ ارائه‌دهنده‌ها
   جواب ندهند، تابع `None` برمی‌گرداند و برنامه همان متن پایهٔ خودش را نشان می‌دهد.
   یعنی خرابی یا اتمام سهمِ مدل، هیچ صفحه‌ای را نمی‌شکند.
2. **همه‌چیز ثبت می‌شود.** هر تلاش — موفق یا ناموفق — در جدول `llm_calls` می‌نشیند:
   ارائه‌دهنده، مدل، تأخیر، توکن‌های ورودی/خروجی، متن خطا و اینکه پشتیبان بوده یا نه.
   پنل ادمین روی همین جدول ساخته شده است.
3. **کلیدها از محیط می‌آیند.** مقدار پیش‌فرض در کد است تا پروژه بدون تنظیم کار کند،
   ولی هر کلید/مدل/آدرس با متغیر محیطی قابل تغییر است و هیچ‌جای لاگ چاپ نمی‌شود.

متغیرهای محیطی مرتبط:
  NESHANE_LLM            «0» کل لایه را خاموش می‌کند
  NESHANE_GEMINI_KEY / NESHANE_GEMINI_MODEL / NESHANE_GEMINI_BASE
  NESHANE_GROQ_KEY   / NESHANE_GROQ_MODEL   / NESHANE_GROQ_BASE
  NESHANE_LLM_TIMEOUT    سقف زمانی هر درخواست (ثانیه، پیش‌فرض ۱۵)
  NESHANE_LLM_BREAKER    چند دقیقه یک ارائه‌دهندهٔ خطادار رد شود (پیش‌فرض ۵)
  NESHANE_LLM_PROXY      آدرس پروکسی (مثل socks5://… یا http://…؛ خالی = بی‌واسطه)

**دربارهٔ فیلترشدن:** هر دو سرویس (Google و Groq) پشت Cloudflare هستند و از بعضی
شبکه‌ها/کشورها بی‌واسطه پاسخ نمی‌دهند. چنین خطایی اینجا «مسدود» تشخیص داده می‌شود،
نه «کلید خراب»: پنجرهٔ کوتاه می‌گیرد و مرتب دوباره امتحان می‌شود. هر لحظه که مسیر
باز شود (پروکسی روشن شود)، خودِ برنامه بدون ری‌استارت به همان ارائه‌دهنده برمی‌گردد.
در تمام این مدت سایت کامل کار می‌کند و فقط متن پایهٔ خودش را نشان می‌دهد.
"""

from __future__ import annotations

import json
import os
import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import db, prompts

# --------------------------------------------------------------------------- #
# پیکربندی
# --------------------------------------------------------------------------- #

# هیچ کلیدی در سورس نیست. کلیدها از `.env` (که کامیت نمی‌شود) یا از متغیر
# محیطی سرور خوانده می‌شوند:  NESHANE_GEMINI_KEY / NESHANE_GROQ_KEY
# اگر کلیدی نباشد، همان ارائه‌دهنده از فهرست کنار گذاشته می‌شود و اپ با متن پایه
# کار می‌کند — هیچ صفحه‌ای نمی‌شکند.
GEMINI_DEFAULT_KEY = ""
GROQ_DEFAULT_KEY = ""

# بدون User-Agent واقعی، Cloudflare جلوی درخواست Groq را می‌گیرد (خطای 1010).
USER_AGENT = "Neshane/1.0 (+self-hosted; python-urllib)"

DEFAULT_TIMEOUT = float(os.environ.get("NESHANE_LLM_TIMEOUT", "15") or 15)
BREAKER_MINUTES = float(os.environ.get("NESHANE_LLM_BREAKER", "5") or 5)
MAX_RETRIES = 1

# حداکثر طول پیش‌نمایشِ پرامپت که در دیتابیس ذخیره می‌شود (برای بازبینی در پنل).
PREVIEW_CHARS = 1500


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None or value.strip() == "" else value.strip()


def enabled() -> bool:
    return _env("NESHANE_LLM", "1").lower() not in {"0", "false", "no", "off"}


# --------------------------------------------------------------------------- #
# ساختار ارائه‌دهنده‌ها
# --------------------------------------------------------------------------- #


@dataclass
class Provider:
    """یک ارائه‌دهندهٔ مدل زبانی (جمینای یا هر سرویس سازگار با OpenAI مثل Groq)."""

    key: str
    label: str
    kind: str  # "gemini" | "openai"
    base: str
    api_key: str
    models: List[str]
    role: str = "primary"
    timeout: float = DEFAULT_TIMEOUT
    note: str = ""

    @property
    def ready(self) -> bool:
        return bool(self.api_key and self.models)


def providers() -> List[Provider]:
    """فهرست ارائه‌دهنده‌ها به ترتیب اولویت: جمینای، بعد گروک."""
    gemini_models = [
        _env("NESHANE_GEMINI_MODEL", ""),
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-flash-latest",
    ]
    groq_models = [
        _env("NESHANE_GROQ_MODEL", ""),
        "openai/gpt-oss-120b",
        "qwen/qwen3.8-27b",
        "openai/gpt-oss-20b",
    ]
    return [
        Provider(
            key="gemini",
            label="جمینای (Gemini)",
            kind="gemini",
            base=_env("NESHANE_GEMINI_BASE", "https://generativelanguage.googleapis.com/v1beta"),
            api_key=_env("NESHANE_GEMINI_KEY", GEMINI_DEFAULT_KEY),
            models=[item for item in gemini_models if item],
            role="primary",
            timeout=DEFAULT_TIMEOUT,
            note="ارائه‌دهندهٔ اصلی؛ اگر خطا بدهد، خودکار به پشتیبان می‌رود.",
        ),
        Provider(
            key="groq",
            label="گروک (Groq)",
            kind="openai",
            base=_env("NESHANE_GROQ_BASE", "https://api.groq.com/openai/v1"),
            api_key=_env("NESHANE_GROQ_KEY", GROQ_DEFAULT_KEY),
            models=[item for item in groq_models if item],
            role="fallback",
            timeout=max(DEFAULT_TIMEOUT, 20.0),
            note="پشتیبان؛ سرویس Groq با مدل‌های متن‌باز.",
        ),
    ]


def provider_view() -> List[Dict[str, Any]]:
    """تصویر امنِ ارائه‌دهنده‌ها برای پنل ادمین (کلید فقط ماسک‌شده)."""
    result: List[Dict[str, Any]] = []
    for provider in providers():
        stats = db.llm_provider_stats(provider.key)
        result.append(
            {
                "key": provider.key,
                "label": provider.label,
                "kind": provider.kind,
                "base": provider.base,
                "models": provider.models,
                "role": provider.role,
                "note": provider.note,
                "configured": provider.ready,
                "key_hint": _mask(provider.api_key),
                "stats": stats,
            }
        )
    return result


def _mask(key: str) -> str:
    key = key or ""
    if len(key) <= 10:
        return "—" if not key else f"{key[:2]}…{key[-2:]}"
    return f"{key[:6]}…{key[-4:]}"


# --------------------------------------------------------------------------- #
# مدارشکن: دو نوع خطا، دو پنجرهٔ متفاوت
# --------------------------------------------------------------------------- #
#
# «خطای قطعی» یعنی کلید یا دسترسی رد شده؛ تکرارکردنش فایده‌ای ندارد و پنجرهٔ بلند
# می‌گیرد. «خطای موقت» یعنی لبهٔ سرویس بدقلقی کرد؛ پنجرهٔ کوتاه می‌گیرد تا سریع
# به همان ارائه‌دهندهٔ اصلی برگردیم.
#
# نکتهٔ مهم: جمینای با کلید نامعتبر همیشه صفحهٔ ۴۰۳ با متن «does not have
# permission» می‌فرستد (خطای قطعی)، ولی گروک گاهی فقط «Forbidden» بدون توضیح
# می‌دهد که معمولاً گذرا است؛ پس ۴۰۳ فقط برای جمینای قطعی حساب می‌شود.

BREAKER_SHORT_SECONDS = float(os.environ.get("NESHANE_LLM_BREAKER_SHORT", "60") or 60)
PERMANENT_STATUSES = {"http_401", "http_402", "auth", "permission", "forbidden_key"}
# خطاهایی که «مسیر شبکه» را نشان می‌دهند: هرگز قطعی حساب نمی‌شوند، چون ممکن است
# پل ارتباطی (پروکسی/فیلترشکن) هر لحظه روشن شود و باید خودکار برگردیم.
LINK_STATUSES = {"edge_blocked", "geo_blocked", "network", "timeout"}
SOFT_STATUSES = {
    "http_403",
    "http_429",
    "rate_limited",
    "timeout",
    "network",
    "unexpected",
    "empty",
    "bad_json",
    "bad_request",
} | LINK_STATUSES

_breaker: Dict[str, Tuple[float, str]] = {}


def _breaker_window(provider: Provider, status: str) -> Tuple[float, bool]:
    """مدت و قطعی‌بودنِ پنجرهٔ مدارشکن برای یک خطای مشخص."""
    if status in PERMANENT_STATUSES:
        return BREAKER_MINUTES * 60, True
    if status == "http_403" and provider.kind == "gemini":
        # پیام JSON جمینای: «دسترسی ندارد» ⇒ کلید/دسترسی مشکل دارد. (فیلترشدن
        # به‌صورت edge_blocked/geo_blocked جدا می‌شود و به اینجا نمی‌رسد.)
        return BREAKER_MINUTES * 60, True
    return BREAKER_SHORT_SECONDS, False


def _breaker_open(provider_key: str) -> Optional[str]:
    """آیا این ارائه‌دهنده در پنجرهٔ مدارشکن است؟ (حافظه، بعد دیتابیس)

    ثبت در دیتابیس یعنی این تصمیم با ری‌استارت سرور هم باقی می‌ماند و اولین
    درخواست کاربر دوباره ثانیه‌ها معطل یک ارائه‌دهندهٔ خراب نمی‌شود.
    """
    stamp = _breaker.get(provider_key)
    if stamp:
        if stamp[0] > time.time():
            return stamp[1]
        _breaker.pop(provider_key, None)
    row = db.breaker_for(provider_key)
    if not row:
        return None
    reason = str(row.get("reason") or "مدار باز")
    _breaker[provider_key] = (float(row["until"]), reason)
    return reason


def _breaker_trip(provider: Provider, reason: str, status: str) -> float:
    """ارائه‌دهنده را برای مدتی کنار می‌گذارد و مدت آن را برمی‌گرداند."""
    seconds, permanent = _breaker_window(provider, status)
    label = reason + ("" if permanent else " (مدار کوتاه؛ به‌زودی دوباره امتحان می‌شود)")
    _breaker[provider.key] = (time.time() + seconds, label)
    db.open_breaker(provider.key, label, seconds)
    return seconds


def breaker_state() -> List[Dict[str, Any]]:
    """وضعیت پایدارِ مدارهای باز (خوانده‌شده از دیتابیس)."""
    rows: List[Dict[str, Any]] = []
    for row in db.open_breakers():
        rows.append(
            {
                "provider": row["provider"],
                "reason": row["reason"],
                "age_seconds": int(row["age"]),
                "remaining_seconds": int(row["remaining"]),
                "open": True,
            }
        )
    return rows


# --------------------------------------------------------------------------- #
# فراخوانی خام HTTP
# --------------------------------------------------------------------------- #


class LLMError(RuntimeError):
    def __init__(self, status: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.message = message[:400]
        self.retryable = retryable


def _blocked_status(kind: str) -> str:
    """وضعیت خطای «مسیر بسته است»: لبهٔ سرویس یا محدودیت منطقه."""
    return "edge_blocked" if kind == "edge" else "geo_blocked"


def _blocked_message(label: str, kind: str, detail: str) -> str:
    if kind == "geo":
        head = f"سرویس {label} برای این منطقه/شبکه فعال نیست"
        tail = " — با پروکسی حل می‌شود؛ کلید مشکلی ندارد."
    else:
        head = f"درخواست به {label} پیش از رسیدن به سرویس مسدود شد (لبهٔ شبکه)"
        tail = " — احتمالاً IP فیلتر است یا کلید رد شده؛ برنامه بدون آن ادامه می‌دهد."
    return f"{head}{tail} ({detail})"


# نام متغیرهای استاندارد پروکسی هم بررسی می‌شود تا اگر کاربر فقط HTTPS_PROXY را
# ست کرده باشد، بی‌هیچ تنظیم اضافه‌ای کار کند.
PROXY_ENV_NAMES = (
    "NESHANE_LLM_PROXY",
    "NESHANE_HTTPS_PROXY",
    "HTTPS_PROXY",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
    "HTTP_PROXY",
    "http_proxy",
)


def proxy_setting() -> Tuple[str, str]:
    """آدرس پروکسی و نام متغیری که از آن آمده (برای نمایش در پنل ادمین)."""
    for name in PROXY_ENV_NAMES:
        value = (os.environ.get(name) or "").strip()
        if value and not value.lower().startswith("no_proxy"):
            return value, name
    return "", ""


def _mask_proxy(url: str) -> str:
    """رمز داخل آدرس پروکسی را پنهان می‌کند (اگر داشته باشد)."""
    if not url:
        return ""
    if "@" not in url:
        return url
    scheme, _, rest = url.partition("://")
    _, _, host = rest.rpartition("@")
    return f"{scheme}://***@{host}" if scheme else f"***@{host}"


def _post(url: str, body: Dict[str, Any], headers: Dict[str, str], timeout: float) -> Dict[str, Any]:
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    proxy, _ = proxy_setting()
    handlers: List[Any] = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        # بدون پروکسیِ صریح، متغیرهای استاندارد محیط رعایت می‌شوند؛ اگر هم هیچ‌کدام
        # نبود ProxyHandler خالی یعنی «مستقیم وصل شو».
        handlers.append(urllib.request.ProxyHandler())
    opener = urllib.request.build_opener(*handlers)
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
    except ssl.SSLError as exc:
        raise LLMError("network", f"خطای امنیتیِ اتصال (SSL): {exc}") from exc
    return json.loads(raw or "{}")


def _call_gemini(
    provider: Provider, model: str, system: str, user: str, temperature: float, max_tokens: int
) -> Dict[str, Any]:
    url = f"{provider.base}/models/{model}:generateContent"
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-goog-api-key": provider.api_key,
    }
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }
    try:
        data = _post(url, body, headers, provider.timeout)
    except urllib.error.HTTPError as exc:
        detail, kind = _read_error(exc)
        if kind:
            raise LLMError(_blocked_status(kind), _blocked_message("جمینای", kind, detail)) from exc
        status = f"http_{exc.code}"
        if exc.code in (401, 403):
            raise LLMError(status, f"کلید جمینای پذیرفته نشد: {detail}", retryable=False) from exc
        if exc.code == 404:
            raise LLMError("model_missing", f"مدل {model} در دسترس نیست: {detail}") from exc
        if exc.code == 429:
            raise LLMError("rate_limited", f"سهم جمینای پر شده است: {detail}", retryable=True) from exc
        raise LLMError(status, detail, retryable=exc.code >= 500) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise LLMError("timeout", "پاسخ جمینای در زمان مقرر نرسید.", retryable=True) from exc
    except urllib.error.URLError as exc:
        raise LLMError("network", f"ارتباط با جمینای برقرار نشد: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise LLMError("bad_json", "پاسخ جمینای قابل‌خواندن نبود.") from exc

    text = _gemini_text(data)
    usage = data.get("usageMetadata") or {}
    return {
        "text": text,
        "prompt_tokens": int(usage.get("promptTokenCount") or 0),
        "completion_tokens": int(usage.get("candidatesTokenCount") or 0),
        "total_tokens": int(usage.get("totalTokenCount") or 0),
        "finish": str((data.get("candidates") or [{}])[0].get("finishReason") or ""),
    }


def _gemini_text(data: Dict[str, Any]) -> str:
    candidates = data.get("candidates") or []
    if not candidates:
        raise LLMError("empty", "جمینای هیچ پاسخی نفرستاد.")
    parts = ((candidates[0].get("content") or {}).get("parts")) or []
    text = "".join(str(part.get("text") or "") for part in parts).strip()
    if not text:
        raise LLMError("empty", "پاسخ جمینای خالی بود.")
    return text


def _call_openai_like(
    provider: Provider, model: str, system: str, user: str, temperature: float, max_tokens: int
) -> Dict[str, Any]:
    url = f"{provider.base.rstrip('/')}/chat/completions"
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {provider.api_key}",
    }
    body: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    # مدل‌های استدلالیِ خانوادهٔ gpt-oss توکن‌های فکرکردن را از max_tokens کم می‌کنند؛
    # پس بودجهٔ بیشتری می‌گیرند تا متنِ نهایی خالی نماند.
    if "gpt-oss" in model:
        body["max_tokens"] = max(max_tokens, 1400)
        body["reasoning_effort"] = "low"
    try:
        data = _post(url, body, headers, provider.timeout)
    except urllib.error.HTTPError as exc:
        detail, kind = _read_error(exc)
        if kind:
            raise LLMError(_blocked_status(kind), _blocked_message("گروک", kind, detail)) from exc
        status = f"http_{exc.code}"
        if exc.code in (401, 403):
            raise LLMError(status, f"کلید گروک پذیرفته نشد: {detail}", retryable=False) from exc
        if exc.code == 404 or "model_not_found" in detail or "does not exist" in detail:
            raise LLMError("model_missing", f"مدل {model} در گروک نیست: {detail}") from exc
        if exc.code == 429:
            raise LLMError("rate_limited", f"سهم گروک پر شده است: {detail}", retryable=True) from exc
        if exc.code == 400:
            # بعضی مدل‌ها response_format را قبول نمی‌کنند؛ یک بار بدون آن تلاش می‌کنیم.
            raise LLMError("bad_request", detail) from exc
        raise LLMError(status, detail, retryable=exc.code >= 500) from exc
    except (socket.timeout, TimeoutError) as exc:
        raise LLMError("timeout", "پاسخ گروک در زمان مقرر نرسید.", retryable=True) from exc
    except urllib.error.URLError as exc:
        raise LLMError("network", f"ارتباط با گروک برقرار نشد: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise LLMError("bad_json", "پاسخ گروک قابل‌خواندن نبود.") from exc

    choices = data.get("choices") or []
    if not choices:
        raise LLMError("empty", "گروک هیچ پاسخی نفرستاد.")
    message = choices[0].get("message") or {}
    text = str(message.get("content") or "").strip()
    if not text:
        reason = str(message.get("reasoning") or "").strip()
        raise LLMError("empty", "پاسخ گروک خالی بود." + (f" (فکرکردن: {reason[:80]}…)" if reason else ""))
    usage = data.get("usage") or {}
    return {
        "text": text,
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
        "finish": str(choices[0].get("finish_reason") or ""),
    }


# نشانه‌های «صفحهٔ لبهٔ سرویس/فیلتر» (Cloudflare و مشابهش) در بدنهٔ خطا.
EDGE_MARKERS = (
    "cloudflare",
    "attention required",
    "just a moment",
    "error code: 1010",
    "error 1010",
    "error 1020",
    "cf-error",
    "ray id",
    "access denied",
    "request blocked",
    "blocked by",
)

# نشانه‌های «این منطقه پشتیبانی نمی‌شود» — با روشن‌کردن پروکسی حل می‌شود، پس
# نباید کلید را خراب فرض کنیم.
GEO_MARKERS = (
    "user location is not supported",
    "location is not supported",
    "not available in your country",
    "country not supported",
    "region is not supported",
    "isn't available in your region",
    "service is not available in",
)


def _read_error(exc: urllib.error.HTTPError) -> Tuple[str, str]:
    """متن خطای سرویس را برمی‌گرداند همراه با نوعش: «edge»، «geo» یا «».

    تفکیک این دو مهم است: خطای «edge/geo» یعنی مسیر شبکه بسته است و با پروکسی
    درست می‌شود، ولی خطای احراز هویت یعنی کلید مشکل دارد. اولی پنجرهٔ کوتاه مدار
    می‌گیرد تا سریع برگردیم، دومی پنجرهٔ بلند.
    """
    try:
        raw = exc.read().decode("utf-8", "replace")
    except Exception:  # pragma: no cover - نادر
        return str(exc.reason or exc), ""
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
            error = data.get("error") or {}
            message = str(error.get("message") if isinstance(error, dict) else error or raw)
            lowered = message.lower()
            if any(marker in lowered for marker in GEO_MARKERS):
                return message[:300], "geo"
            return message[:300], ""
        except Exception:  # pragma: no cover
            pass
    lowered = raw.lower()
    if any(marker in lowered for marker in EDGE_MARKERS) or "<html" in lowered:
        # صفحهٔ HTML لبهٔ سرویس: متن خوانا را جدا می‌کنیم.
        import re

        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = " ".join(text.split())
        return (text or str(exc.reason or ""))[:300], "edge"
    return raw[:300], ""


# --------------------------------------------------------------------------- #
# انتخاب ارائه‌دهنده، تلاش مجدد و ثبت در دیتابیس
# --------------------------------------------------------------------------- #


def _log(
    *,
    kind: str,
    provider: Provider,
    model: str,
    ok: bool,
    status: str,
    error: str,
    latency_ms: int,
    attempt: int,
    retries: int,
    prompt_text: str,
    response_text: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    user_id: Optional[int] = None,
) -> None:
    db.log_llm_call(
        {
            "kind": kind,
            "provider": provider.key,
            "provider_label": provider.label,
            "model": model,
            "role": provider.role,
            "ok": 1 if ok else 0,
            "status": status,
            "error": error[:400],
            "latency_ms": latency_ms,
            "attempt": attempt,
            "retries": retries,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "prompt_chars": len(prompt_text),
            "response_chars": len(response_text),
            "prompt_preview": prompt_text[:PREVIEW_CHARS],
            "response_preview": response_text[:PREVIEW_CHARS],
            "user_id": user_id,
        }
    )


def complete(
    kind: str,
    system: str,
    user: str,
    *,
    temperature: float = 0.9,
    max_tokens: int = 800,
    user_id: Optional[int] = None,
    providers_override: Optional[Sequence[Provider]] = None,
    timeout: Optional[float] = None,
    retries_allowed: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """پوستهٔ محافظ: هیچ خطایی از لایهٔ مدل به بیرون درز نمی‌کند.

    اگر شبکه بسته باشد، دیتابیس خطا بدهد یا هر چیز نامنتظره‌ای رخ دهد، خروجی
    ``None`` است و برنامه همان محتوای پایهٔ خودش را نشان می‌دهد. یعنی خرابی مدل
    هرگز به صفحهٔ کاربر یا خطای ۵۰۰ تبدیل نمی‌شود.
    """
    try:
        return _complete_inner(
            kind,
            system,
            user,
            temperature=temperature,
            max_tokens=max_tokens,
            user_id=user_id,
            providers_override=providers_override,
            timeout=timeout,
            retries_allowed=retries_allowed,
        )
    except Exception:  # pragma: no cover - محافظ نهایی
        return None


def _complete_inner(
    kind: str,
    system: str,
    user: str,
    *,
    temperature: float = 0.9,
    max_tokens: int = 800,
    user_id: Optional[int] = None,
    providers_override: Optional[Sequence[Provider]] = None,
    timeout: Optional[float] = None,
    retries_allowed: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """متن را از اولین ارائه‌دهندهٔ سالم می‌گیرد و همهٔ تلاش‌ها را ثبت می‌کند.

    خروجی: ``{"text", "provider", "provider_label", "model", "usage", "attempt", "latency_ms"}``
    یا ``None`` اگر هیچ ارائه‌دهنده‌ای جواب نداد.
    """
    if not enabled():
        return None

    attempt = 0
    for provider in providers_override or providers():
        if not provider.ready:
            continue
        blocked = _breaker_open(provider.key)
        if blocked:
            attempt += 1
            _log(
                kind=kind,
                provider=provider,
                model=provider.models[0],
                ok=False,
                status="skipped",
                error=f"مدار باز است: {blocked}",
                latency_ms=0,
                attempt=attempt,
                retries=0,
                prompt_text=user,
                response_text="",
                user_id=user_id,
            )
            continue

        if timeout:
            # سقف زمانی تنگ‌تر برای مسیرهایی که کاربر منتظر است (مثلاً گشودن فال).
            provider.timeout = min(provider.timeout, float(timeout))
        last_error: Optional[LLMError] = None
        provider_broken = False
        for model in provider.models:
            # اگر همین الان کلید این ارائه‌دهنده رد شد، مدل‌های دیگرش را هم امتحان نکن.
            if provider_broken:
                break
            retries = 0
            while True:
                attempt += 1
                started = time.time()
                try:
                    if provider.kind == "gemini":
                        result = _call_gemini(provider, model, system, user, temperature, max_tokens)
                    else:
                        result = _call_openai_like(provider, model, system, user, temperature, max_tokens)
                except LLMError as exc:
                    last_error = exc
                    latency_ms = int((time.time() - started) * 1000)
                    max_retries = MAX_RETRIES if retries_allowed is None else max(0, int(retries_allowed))
                    transient = exc.retryable or exc.status == "empty"
                    if retries < max_retries and transient:
                        retries += 1
                        time.sleep(0.5)
                        continue
                    _log(
                        kind=kind,
                        provider=provider,
                        model=model,
                        ok=False,
                        status=exc.status,
                        error=exc.message,
                        latency_ms=latency_ms,
                        attempt=attempt,
                        retries=retries,
                        prompt_text=user,
                        response_text="",
                        user_id=user_id,
                    )
                    if exc.status in PERMANENT_STATUSES or (
                        exc.status == "http_403" and provider.kind == "gemini"
                    ):
                        provider_broken = True
                        _breaker_trip(provider, f"کلید یا دسترسی رد شد ({exc.status})", exc.status)
                        break
                    if exc.status in LINK_STATUSES:
                        # مسیر شبکه بسته/کند است: مدل‌های دیگر همین ارائه‌دهنده از
                        # پشت همان مسیر می‌روند، پس فوراً به پشتیبان می‌رویم.
                        provider_broken = True
                        _breaker_trip(provider, f"مسیر ارتباطی بسته یا کند ({exc.status})", exc.status)
                        break
                    if exc.status in {"http_403", "http_429", "rate_limited"}:
                        # گذرا است: پنجرهٔ کوتاه می‌گیرد ولی همین درخواست سراغ پشتیبان می‌رود.
                        provider_broken = True
                        _breaker_trip(provider, f"پاسخ {exc.status} از لبهٔ سرویس", exc.status)
                        break
                    if exc.status == "model_missing":
                        break  # مدل بعدی همین ارائه‌دهنده را امتحان کن
                    break
                except Exception as exc:  # pragma: no cover - محافظ
                    last_error = LLMError("unexpected", f"{type(exc).__name__}: {exc}")
                    _log(
                        kind=kind,
                        provider=provider,
                        model=model,
                        ok=False,
                        status="unexpected",
                        error=last_error.message,
                        latency_ms=int((time.time() - started) * 1000),
                        attempt=attempt,
                        retries=retries,
                        prompt_text=user,
                        response_text="",
                        user_id=user_id,
                    )
                    # خطای نامنتظر (مثل بستن اتصال از سمت سرور) هم ارائه‌دهنده را
                    # چند دقیقه کنار می‌گذارد تا کاربر پشت آن معطل نماند.
                    provider_broken = True
                    _breaker_trip(provider, f"خطای نامنتظر ({type(exc).__name__})", "unexpected")
                    break

                latency_ms = int((time.time() - started) * 1000)
                text = str(result.get("text") or "").strip()
                if not text:
                    last_error = LLMError("empty", "پاسخ خالی بود.")
                    break
                _log(
                    kind=kind,
                    provider=provider,
                    model=model,
                    ok=True,
                    status="ok",
                    error="",
                    latency_ms=latency_ms,
                    attempt=attempt,
                    retries=retries,
                    prompt_text=user,
                    response_text=text,
                    prompt_tokens=int(result.get("prompt_tokens") or 0),
                    completion_tokens=int(result.get("completion_tokens") or 0),
                    total_tokens=int(result.get("total_tokens") or 0),
                    user_id=user_id,
                )
                return {
                    "text": text,
                    "provider": provider.key,
                    "provider_label": provider.label,
                    "model": model,
                    "role": provider.role,
                    "usage": {
                        "prompt_tokens": int(result.get("prompt_tokens") or 0),
                        "completion_tokens": int(result.get("completion_tokens") or 0),
                        "total_tokens": int(result.get("total_tokens") or 0),
                    },
                    "attempt": attempt,
                    "latency_ms": latency_ms,
                    "finish": result.get("finish", ""),
                }
        # پایان مدل‌ها/ارائه‌دهنده: سراغ پشتیبان می‌رویم.
        del last_error  # فقط برای خوانایی؛ هدف، رفتن به ارائه‌دهندهٔ بعدی است.
    return None


# --------------------------------------------------------------------------- #
# تجزیهٔ JSON
# --------------------------------------------------------------------------- #


def parse_json(text: str) -> Optional[Dict[str, Any]]:
    """JSON را از پاسخ مدل بیرون می‌کشد (حتی اگر داخل بلوک کد یا متن باشد)."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1] if "```" in cleaned[3:] else cleaned[3:]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    while start != -1:
        depth = 0
        for index in range(start, len(cleaned)):
            char = cleaned[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(cleaned[start : index + 1])
                        if isinstance(data, dict):
                            return data
                    except json.JSONDecodeError:
                        break
        start = cleaned.find("{", start + 1)
    return None


def _clean(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _string_list(value: Any, limit: int = 3, each: int = 120) -> List[str]:
    if isinstance(value, str):
        items = [item for item in value.replace("؛", "\n").split("\n") if item.strip()]
    elif isinstance(value, list):
        items = value
    else:
        return []
    cleaned = [_clean(item, each) for item in items]
    return [item for item in cleaned if item][:limit]


# --------------------------------------------------------------------------- #
# قابلیت‌های آماده: فال، تست، پاپ‌اپ
# --------------------------------------------------------------------------- #


def personalize_reading(
    symbols: str,
    base_text: str,
    context: Dict[str, Any],
    user_id: Optional[int] = None,
    timeout: Optional[float] = None,
    retries_allowed: int = 0,
) -> Optional[Dict[str, Any]]:
    """خوانش نهایی فال را با نیت کاربر شخصی می‌کند."""
    entry = prompts.get("fortune")
    user_prompt = prompts.render_user(
        "fortune",
        symbols=symbols,
        base_text=base_text,
        name=context.get("name") or "دوست من",
        gender=context.get("gender") or "—",
        city=context.get("city") or "—",
        sign=context.get("sign") or "—",
        topic=context.get("topic") or "—",
        intent=context.get("intent") or "بدون نیت مشخص",
        method=context.get("method") or "—",
        mood=context.get("mood") or "—",
        mood_line=context.get("mood_line") or "",
        overall=context.get("overall") or 0,
        overall_label=context.get("overall_label") or "",
        donts="، ".join(context.get("donts") or []) or "—",
    )
    answer = complete(
        "fortune",
        entry["system"],
        user_prompt,
        temperature=float(entry["temperature"]),
        max_tokens=int(entry["max_tokens"]),
        user_id=user_id,
        timeout=timeout,
        retries_allowed=retries_allowed,
    )
    if not answer:
        return None
    data = parse_json(answer["text"])
    if not data:
        return None
    personal = _clean(data.get("personal"), 700)
    headline = _clean(data.get("headline"), 140)
    if not personal and not headline:
        return None
    return {
        "headline": headline,
        "personal": personal,
        "guidance": _string_list(data.get("guidance"), 3, 140),
        "invitation": _clean(data.get("invitation"), 200),
        "provider": answer["provider"],
        "provider_label": answer["provider_label"],
        "model": answer["model"],
        "latency_ms": answer["latency_ms"],
        "tokens": answer["usage"].get("total_tokens", 0),
        "used_fallback": answer["role"] == "fallback",
    }


def interpret_test(breakdown: str, context: Dict[str, Any], user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """تفسیر پایانی تست شخصیت بر اساس پاسخ‌های واقعی کاربر."""
    entry = prompts.get("test_result")
    user_prompt = prompts.render_user(
        "test_result",
        breakdown=breakdown,
        name=context.get("name") or "دوست من",
        test_label=context.get("test_label") or "—",
        title=context.get("title") or "—",
        code=context.get("code") or "",
        answered=context.get("answered") or 0,
        tagline=context.get("tagline") or "",
        body=context.get("body") or "",
    )
    answer = complete(
        "test_result",
        entry["system"],
        user_prompt,
        temperature=float(entry["temperature"]),
        max_tokens=int(entry["max_tokens"]),
        user_id=user_id,
    )
    if not answer:
        return None
    data = parse_json(answer["text"])
    if not data:
        return None
    note = _clean(data.get("note"), 600)
    if not note:
        return None
    return {
        "note": note,
        "next_step": _clean(data.get("next_step"), 160),
        "provider": answer["provider"],
        "provider_label": answer["provider_label"],
        "model": answer["model"],
        "latency_ms": answer["latency_ms"],
        "tokens": answer["usage"].get("total_tokens", 0),
        "used_fallback": answer["role"] == "fallback",
    }


def feedback_invite(context: Dict[str, Any], user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """پیام متغیرِ پاپ‌اپ امتیازدهی."""
    entry = prompts.get("feedback")
    user_prompt = prompts.render_user(
        "feedback",
        name=context.get("name") or "دوست من",
        readings=context.get("readings") or 0,
        tests=context.get("tests") or 0,
        last_seen=context.get("last_seen") or "—",
    )
    answer = complete(
        "feedback",
        entry["system"],
        user_prompt,
        temperature=float(entry["temperature"]),
        max_tokens=int(entry["max_tokens"]),
        user_id=user_id,
    )
    if not answer:
        return None
    data = parse_json(answer["text"])
    if not data:
        return None
    title = _clean(data.get("title"), 90)
    body = _clean(data.get("body"), 260)
    if not title and not body:
        return None
    return {"title": title, "body": body, "provider": answer["provider"], "model": answer["model"]}


# --------------------------------------------------------------------------- #
# سلامت و آمار
# --------------------------------------------------------------------------- #


def health() -> Dict[str, Any]:
    """خلاصهٔ وضعیت لایهٔ مدل برای داشبورد ادمین."""
    stats = db.llm_stats()
    return {
        "enabled": enabled(),
        "timeout": DEFAULT_TIMEOUT,
        "breaker_minutes": BREAKER_MINUTES,
        "providers": provider_view(),
        "breakers": breaker_state(),
        "stats": stats,
    }
