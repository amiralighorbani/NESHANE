"""موتور تبلیغات: آپلود رسانه، زمان‌بندی نمایش و انتخاب تبلیغ مناسب هر بازدید.

سه بخش دارد:

1. **رسانه** — مدیر عکس یا ویدیوی چند‌ثانیه‌ای را از پنل آپلود می‌کند. اینجا فقط
   پسوند و نوعِ شناخته‌شده پذیرفته می‌شود، حجم سقف دارد و نام فایل همیشه تازه
   ساخته می‌شود (به نام فرستادهٔ کاربر اعتماد نمی‌کنیم).
2. **زمان‌بندی** — زمانِ نمایش با ترکیب چند شرط تعیین می‌شود: بازهٔ تاریخ، ساعات
   شبانه‌روز (با پشتیبانی از بازهٔ شب‌رو مثل ۲۲ تا ۲)، روزهای هفته و سهمیهٔ روزانه.
   «چه زمانی نشان بده و چه زمانی نده» فقط یک ستون نیست؛ همین ترکیب است.
3. **انتخاب و ثبت رویداد** — بین تبلیغ‌های واجد شرط، آن‌که کمتر دیده شده جلو می‌افتد
   تا همه سهم ببرند؛ هر نمایش/کلیک/رد‌کردن در `ad_events` ثبت می‌شود.
"""

from __future__ import annotations

import os
import secrets
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import db


def _env_int(name: str, default: int) -> int:
    """عدد محیطی را می‌خواند؛ هر مقدار نامعتبر (خالی، متن، منفی) پیش‌فرض می‌گیرد."""
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return max(0, int(float(str(raw).strip())))
    except (TypeError, ValueError):
        return default

# پوشهٔ رسانه‌ها کنار دیتابیس می‌نشیند تا پشتیبان‌گیری از `data/` همه‌چیز را ببرد.
MEDIA_DIR = Path(os.environ.get("NESHANE_ADS_DIR", db.DB_PATH.parent / "ads_media"))

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_VIDEO_BYTES = 32 * 1024 * 1024
CHUNK = 1024 * 256

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
VIDEO_EXTENSIONS = {".mp4", ".webm", ".ogv", ".mov", ".m4v"}

# اگر مرورگر نوع فایل را اشتباه بفرستد، از پسوند + این فهرست کمکی استفاده می‌کنیم.
IMAGE_MIME = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"}
VIDEO_MIME = {"video/mp4", "video/webm", "video/ogg", "video/quicktime", "video/x-m4v"}

PLACEMENTS = {
    "popup": {"key": "popup", "label": "پاپ‌اپ (روی همهٔ صفحه‌ها)", "icon": "fa-solid fa-window-restore"},
    "banner": {"key": "banner", "label": "بنر صفحهٔ خانه", "icon": "fa-solid fa-rectangle-ad"},
    "both": {"key": "both", "label": "هم پاپ‌اپ هم بنر", "icon": "fa-solid fa-clone"},
}
PLACEMENT_ORDER = ("popup", "banner", "both")

# ۰ = شنبه ... ۶ = جمعه (هفتهٔ ایرانی)
WEEKDAYS = (
    ("شنبه", "fa-solid fa-calendar-day"),
    ("یک‌شنبه", "fa-solid fa-calendar-day"),
    ("دوشنبه", "fa-solid fa-calendar-day"),
    ("سه‌شنبه", "fa-solid fa-calendar-day"),
    ("چهارشنبه", "fa-solid fa-calendar-day"),
    ("پنج‌شنبه", "fa-solid fa-calendar-day"),
    ("جمعه", "fa-solid fa-calendar-day"),
)

MAX_HOLD_SECONDS = 180
MAX_SKIP_AFTER = 60

# --------------------------------------------------------------------------- #
# سقف کلی پاپ‌اپ / global popup throttle
# --------------------------------------------------------------------------- #
# «روی هر صفحه یک پاپ‌اپ» یک تنظیمِ تبلیغ نیست، یک سیاست کلّی است: چون پاپ‌اپ روی
# همهٔ صفحه‌ها نشان داده می‌شود، کاربر با چند کلیک پشت سر هم چند پنجره می‌دید.
# این دو عدد همان سیاست کلّی‌اند و به تنظیم هیچ تبلیغی وابسته نیستند:
#   * فاصلهٔ حداقلی بین دو پاپ‌اپ برای یک نفر (پیش‌فرض ۴۵ دقیقه)
#   * سقف پاپ‌اپ در یک روز برای یک نفر (پیش‌فرض ۴ بار)
# هر دو با متغیر محیطی قابل تغییرند؛ صفر یعنی «بی‌سقف».
POPUP_COOLDOWN_SECONDS = _env_int("NESHANE_AD_COOLDOWN_MINUTES", 45) * 60
POPUP_DAILY_CAP = _env_int("NESHANE_AD_POPUPS_PER_DAY", 4)
# رویدادی که «یک پاپ‌اپ تازه به این نفر داده شد» را ثبت می‌کند؛ فقط برای همین سقف.
POPUP_EVENT = "popup"


# --------------------------------------------------------------------------- #
# رسانه / media
# --------------------------------------------------------------------------- #


def media_path(filename: str) -> Path:
    return MEDIA_DIR / filename


def media_url(ad: Dict[str, Any]) -> str:
    """آدرس عمومی فایل رسانه (پوشه در `main.py` سوار شده است)."""
    name = str(ad.get("media_file") or "")
    return f"/media/ads/{name}" if name else ""


def _extension(filename: str) -> str:
    return Path(str(filename or "").replace("\\", "/")).suffix.lower()


def media_kind_for(filename: str, content_type: str = "") -> Tuple[str, str]:
    """نوع رسانه را تشخیص می‌دهد.

    خروجی: ``(kind, error)`` که kind یکی از `image`/`video`/`` و error پیام فارسی است.
    اگر پسوند و نوعِ اعلامی مرورگر با هم نخوانند، به پسوند اعتماد می‌کنیم (بعضی
    مرورگرها mime مبهم می‌فرستند) ولی پسوند ناشناخته پذیرفته نمی‌شود.
    """
    extension = _extension(filename)
    mime = (content_type or "").split(";")[0].strip().lower()
    if extension in IMAGE_EXTENSIONS:
        return "image", ""
    if extension in VIDEO_EXTENSIONS:
        return "video", ""
    if mime in IMAGE_MIME:
        return "image", ""
    if mime in VIDEO_MIME:
        return "video", ""
    if extension:
        return "", f"پسوند «{extension}» پشتیبانی نمی‌شود. عکس (jpg، png، webp) یا ویدیو (mp4، webm)."
    return "", "نوع فایل را نمی‌شناسم؛ عکس یا ویدیو با پسوند درست بفرست."


def save_upload(source: Any, original_name: str, content_type: str = "") -> Tuple[Dict[str, Any], str]:
    """فایل آپلودی را در پوشهٔ رسانه ذخیره می‌کند.

    خروجی ``(info, error)``؛ اگر error خالی باشد، info شامل ``kind``، ``file``،
    ``name`` و ``bytes`` است. فایل نیمه‌کاره در صورت خطا پاک می‌شود تا زباله نماند.
    """
    kind, error = media_kind_for(original_name, content_type)
    if error:
        return {}, error

    limit = MAX_VIDEO_BYTES if kind == "video" else MAX_IMAGE_BYTES
    extension = _extension(original_name) or (".mp4" if kind == "video" else ".jpg")
    filename = f"{kind}-{int(time.time())}-{secrets.token_hex(6)}{extension}"

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    target = media_path(filename)
    written = 0
    try:
        source.seek(0) if hasattr(source, "seek") else None
        with open(target, "wb") as handle:
            while True:
                chunk = source.read(CHUNK)
                if not chunk:
                    break
                written += len(chunk)
                if written > limit:
                    raise ValueError(_too_big_message(kind, limit))
                handle.write(chunk)
    except ValueError as exc:
        target.unlink(missing_ok=True)
        return {}, str(exc)
    except OSError as exc:  # pragma: no cover - خطای دیسک
        target.unlink(missing_ok=True)
        return {}, f"ذخیرهٔ فایل ممکن نشد: {exc}"
    finally:
        try:
            source.close()
        except Exception:
            pass

    if not written:
        target.unlink(missing_ok=True)
        return {}, "فایل خالی بود؛ یک عکس یا ویدیو انتخاب کن."
    if written > limit:
        target.unlink(missing_ok=True)
        return {}, _too_big_message(kind, limit)

    return {
        "kind": kind,
        "file": filename,
        "name": Path(str(original_name).replace("\\", "/")).name[:120],
        "bytes": written,
    }, ""


def _too_big_message(kind: str, limit: int) -> str:
    label = "ویدیو" if kind == "video" else "عکس"
    return f"حجم {label} بیشتر از حد مجاز است (سقف {round(limit / 1024 / 1024)} مگابایت)."


def delete_media(filename: str) -> None:
    """فایل رسانه را پاک می‌کند (اگر وجود نداشته باشد، بی‌صدا رد می‌شود)."""
    name = Path(str(filename or "")).name
    if not name:
        return
    try:
        media_path(name).unlink(missing_ok=True)
    except OSError:  # pragma: no cover
        pass


def human_size(value: Any) -> str:
    size = float(value or 0)
    if size < 1024:
        return f"{int(size)} بایت"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} کیلوبایت"
    return f"{size / 1024 / 1024:.1f} مگابایت"


# --------------------------------------------------------------------------- #
# زمان‌بندی / scheduling
# --------------------------------------------------------------------------- #


def weekday_index(stamp: Optional[float] = None) -> int:
    """روز هفتهٔ ایرانی: ۰ = شنبه … ۶ = جمعه.

    `time.localtime().tm_wday` دوشنبه را ۰ می‌گیرد؛ این‌جا به شنبه جابه‌جا می‌شود تا
    با چیزی که در پنل می‌بینی یکی باشد.
    """
    monday_based = time.localtime(stamp if stamp is not None else time.time()).tm_wday
    return (monday_based + 2) % 7


def weekday_list(value: Any) -> List[int]:
    """رشتهٔ روزها را به فهرست عدد تبدیل می‌کند (هر چیز نامعتبر نادیده می‌ماند)."""
    text = str(value or "").strip()
    if not text:
        return []
    days: List[int] = []
    for char in text:
        if char.isdigit() and 0 <= int(char) <= 6 and int(char) not in days:
            days.append(int(char))
    return sorted(days)


def hour_in_window(hour: int, hour_from: int, hour_to: int) -> bool:
    """آیا این ساعت داخل بازه است؟ بازهٔ شب‌رو (۲۲ تا ۲) هم درست حساب می‌شود."""
    start = max(0, min(23, int(hour_from)))
    end = max(0, min(24, int(hour_to)))
    if start == end:
        return True  # بازهٔ بسته: یعنی تمام شبانه‌روز
    if end == 24:
        return hour >= start
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end  # شب‌رو


def status(ad: Dict[str, Any], stamp: Optional[float] = None) -> Dict[str, str]:
    """وضعیت یک تبلیغ در همین لحظه، برای نمایش در پنل.

    خروجی ``{"key", "label", "icon"}``. کلیدها: active / off / scheduled / expired /
    hour / weekday.
    """
    moment = stamp if stamp is not None else time.time()
    if not int(ad.get("active") or 0):
        return {"key": "off", "label": "خاموش", "icon": "fa-solid fa-circle-pause"}
    starts = ad.get("starts_at")
    ends = ad.get("ends_at")
    if starts and moment < float(starts):
        return {"key": "scheduled", "label": "در انتظار شروع", "icon": "fa-solid fa-hourglass-start"}
    if ends and moment > float(ends):
        return {"key": "expired", "label": "تمام‌شده", "icon": "fa-solid fa-hourglass-end"}
    if not hour_in_window(time.localtime(moment).tm_hour, ad.get("hour_from") or 0, ad.get("hour_to") if ad.get("hour_to") is not None else 24):
        return {"key": "hour", "label": "خارج از ساعت", "icon": "fa-solid fa-clock"}
    days = weekday_list(ad.get("weekdays"))
    if days and weekday_index(moment) not in days:
        return {"key": "weekday", "label": "خارج از روزهای انتخابی", "icon": "fa-solid fa-calendar-xmark"}
    return {"key": "active", "label": "فعال", "icon": "fa-solid fa-circle-play"}


def window_label(ad: Dict[str, Any], jalali_label: Any = None) -> List[str]:
    """توضیح خوانا از شرایط نمایش (برای فهرست پنل)."""
    parts: List[str] = []
    if jalali_label is not None:
        if ad.get("starts_at"):
            parts.append(f"از {jalali_label(float(ad['starts_at']))}")
        if ad.get("ends_at"):
            parts.append(f"تا {jalali_label(float(ad['ends_at']))}")

    hour_from = int(ad.get("hour_from") or 0)
    hour_to = 24 if ad.get("hour_to") in (None, "") else int(ad.get("hour_to"))
    if not (hour_from == 0 and hour_to == 24):
        if hour_from == hour_to:
            parts.append("تمام شبانه‌روز")
        else:
            parts.append(f"ساعت {hour_from} تا {hour_to}")

    days = weekday_list(ad.get("weekdays"))
    if days:
        parts.append("، ".join(WEEKDAYS[index][0] for index in days))
    else:
        parts.append("همهٔ روزها")

    if int(ad.get("max_per_day") or 0):
        parts.append(f"حداکثر {int(ad['max_per_day'])} بار در روز برای هر نفر")
    return parts


def schedule_ok(ad: Dict[str, Any], stamp: Optional[float] = None) -> bool:
    """آیا الان داخل پنجرهٔ زمانی این تبلیغ هستیم؟"""
    state = status(ad, stamp)
    return state["key"] == "active"


# --------------------------------------------------------------------------- #
# انتخاب تبلیغ / selection
# --------------------------------------------------------------------------- #


def _actor(user_id: Optional[int], visitor: str) -> str:
    if user_id:
        return f"u{int(user_id)}"
    return f"v{str(visitor or 'anon')[:48]}"


def popup_throttle(actor: str, stamp: Optional[float] = None) -> Dict[str, Any]:
    """وضعیت سقف کلی پاپ‌اپ برای این بازدیدکننده (برای پنل و آزمون).

    خروجی: ``{"allowed", "reason", "cooldown_seconds", "daily_cap", "seen_today", "retry_in"}``.
    """
    moment = stamp if stamp is not None else time.time()
    day_start = moment - (moment % 86400)
    state: Dict[str, Any] = {
        "allowed": True,
        "reason": "ok",
        "cooldown_seconds": POPUP_COOLDOWN_SECONDS,
        "daily_cap": POPUP_DAILY_CAP,
        "seen_today": 0,
        "retry_in": 0,
    }
    if not actor:
        return state
    if POPUP_DAILY_CAP:
        state["seen_today"] = db.ad_actor_events(actor, [POPUP_EVENT], day_start)["count"]
    if POPUP_COOLDOWN_SECONDS:
        recent = db.ad_actor_events(actor, [POPUP_EVENT], moment - POPUP_COOLDOWN_SECONDS)
        if recent["last_at"]:
            state["allowed"] = False
            state["reason"] = "cooldown"
            state["retry_in"] = int(max(1, POPUP_COOLDOWN_SECONDS - (moment - float(recent["last_at"]))))
            return state
    if POPUP_DAILY_CAP and state["seen_today"] >= POPUP_DAILY_CAP:
        state["allowed"] = False
        state["reason"] = "daily"
        state["retry_in"] = int(day_start + 86400 - moment)
    return state


def eligible(
    user_id: Optional[int] = None,
    visitor: str = "",
    placement: str = "popup",
    stamp: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """همهٔ تبلیغ‌های واجد شرط این بازدیدکننده، به ترتیب اولویت.

    شرط‌ها: روشن باشد، داخل پنجرهٔ زمانی باشد، جای نمایشش با این جای بخواند و
    سهمیهٔ روزانه و «دیگر نشان نده» نقض نشده باشد. پاپ‌اپ‌ها یک سقف کلّی هم دارند
    (فاصلهٔ بین دو پاپ‌اپ + سقف روزانه) که در `popup_throttle` حساب می‌شود.
    """
    moment = stamp if stamp is not None else time.time()
    day_start = moment - (moment % 86400)  # ابتدای روز محلی (تقریبی، برای سهمیه)
    actor = _actor(user_id, visitor)
    # سقف کلّی پاپ‌اپ، پیش از هر محاسبهٔ دیگری. بنر این سقف را ندارد.
    if placement == "popup" and not popup_throttle(actor, moment)["allowed"]:
        return []
    rows: List[Dict[str, Any]] = []

    for ad in db.ads_all(active_only=True):
        if ad.get("placement") not in (placement, "both"):
            continue
        if not schedule_ok(ad, moment):
            continue
        media = str(ad.get("media_file") or "")
        if not media:
            continue

        cap = int(ad.get("max_per_day") or 0)
        if cap and db.ad_event_count(int(ad["id"]), "impression", day_start, actor) >= cap:
            continue

        dismiss_days = int(ad.get("dismiss_days") or 0)
        if dismiss_days:
            last = db.ad_last_event_at(int(ad["id"]), actor, "dismiss")
            if last and moment - last < dismiss_days * 86400:
                continue

        rows.append(ad)

    # وزن بیشتر جلوتر، ولی در وزن مساوی آن‌که امروز کمتر دیده شده جلو می‌افتد
    # تا یک تبلیغ همیشه بقیه را کنار نزند.
    def sort_key(item: Dict[str, Any]) -> Tuple[int, int, float]:
        seen = db.ad_event_count(int(item["id"]), "impression", day_start, actor)
        return (-int(item.get("weight") or 1), seen, -float(item.get("updated_at") or 0))

    rows.sort(key=sort_key)
    return rows


def pick(
    user_id: Optional[int] = None,
    visitor: str = "",
    placement: str = "popup",
    stamp: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """یک تبلیغ برای نمایش انتخاب می‌کند (یا ``None`` اگر چیزی برای نشان‌دادن نیست)."""
    rows = eligible(user_id, visitor, placement, stamp)
    return rows[0] if rows else None


def public_payload(ad: Dict[str, Any]) -> Dict[str, Any]:
    """اطلاعاتی که مرورگر برای نمایش تبلیغ لازم دارد (بدون دادهٔ داخلی پنل)."""
    return {
        "id": int(ad["id"]),
        "title": str(ad.get("title") or ""),
        "body": str(ad.get("body") or ""),
        "kind": str(ad.get("media_kind") or "image"),
        "media": media_url(ad),
        "link": str(ad.get("link_url") or ""),
        "cta": str(ad.get("cta_label") or ""),
        "skip_allowed": bool(int(ad.get("skip_allowed") or 0)),
        "skip_after": max(0, min(MAX_SKIP_AFTER, int(ad.get("skip_after") or 0))),
        "hold_seconds": max(1, min(MAX_HOLD_SECONDS, int(ad.get("hold_seconds") or 8))),
        "dismiss_days": int(ad.get("dismiss_days") or 0),
        "placement": str(ad.get("placement") or "popup"),
    }


def record(ad_id: int, kind: str, user_id: Optional[int] = None, visitor: str = "") -> None:
    """یک رویداد تبلیغ را ثبت می‌کند (نمایش، کلیک، ردکردن، دیگر نشان نده).

    `POPUP_EVENT` رویدادی داخلی است که سرور هنگام تحویل پاپ‌اپ ثبت می‌کند تا سقف
    کلّی (فاصله و سقف روزانه) درست شمرده شود؛ در آمار پنل به‌عنوان «نمایش» شمرده
    نمی‌شود.
    """
    if kind not in {"impression", "click", "skip", "dismiss", POPUP_EVENT}:
        return
    db.ad_event_add(int(ad_id), _actor(user_id, visitor), kind)
