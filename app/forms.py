"""اعتبارسنجی فرم‌ها با پیام‌های فارسی: شمارهٔ تلفن، کد ورود، نام کاربری/رمز، پروفایل و فال."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .content import methods as method_catalogue
from .content.lexicon import TOPICS
from .models import FortuneRequest
from .utils import from_fa, is_valid_jalali, parse_time_text

GENDERS: List[Dict[str, str]] = [
    {"value": "", "label": "نگفتن"},
    {"value": "f", "label": "خانم"},
    {"value": "m", "label": "آقا"},
]

MAX_INTENT = 180
PHONE_PREFIXES = ("091", "092", "093", "090", "099", "098", "094", "095")


def _to_int(value: Any, default: int) -> int:
    try:
        return int(from_fa(str(value)).replace("٬", "").replace("،", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def normalize_phone(value: Any) -> Optional[str]:
    """شمارهٔ موبایل ایران را به شکل استاندارد ۰۹xxxxxxxxx برمی‌گرداند."""
    text = from_fa(str(value or "")).strip()
    for char in " ()-_.\u200c":
        text = text.replace(char, "")
    if text.startswith("+98"):
        text = "0" + text[3:]
    elif text.startswith("0098"):
        text = "0" + text[4:]
    elif text.startswith("98") and len(text) == 12:
        text = "0" + text[2:]
    elif text.startswith("9") and len(text) == 10:
        text = "0" + text
    if len(text) != 11 or not text.isdigit():
        return None
    if not text.startswith(PHONE_PREFIXES):
        return None
    return text


def normalize_otp(value: Any) -> str:
    return "".join(char for char in from_fa(str(value or "")) if char.isdigit())[:6]


MAX_NAME = 40

# نام کاربری و رمز عبور حساب کاربر (ورود بعد از ثبت‌نام با شمارهٔ تلفن)
USERNAME_MIN = 3
USERNAME_MAX = 24
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._]+$")
PASSWORD_MIN = 8
PASSWORD_MAX = 128


def validate_credentials(
    form: Mapping[str, Any],
) -> Tuple[Optional[Dict[str, str]], List[str], Dict[str, str]]:
    """قدم ثبت‌نام: انتخاب نام کاربری و رمز عبور.

    نام کاربری عمداً انگلیسی است تا تایپ‌کردنش روی موبایل و ورود بعدی ساده باشد؛
    بزرگی/کوچکی حروف در ورود مهم نیست.
    """
    username = str(form.get("username") or "").strip()
    password = str(form.get("password") or "")
    confirm = str(form.get("confirm") or "")
    values = {"username": username}

    errors: List[str] = []
    if not (USERNAME_MIN <= len(username) <= USERNAME_MAX) or not USERNAME_PATTERN.match(username):
        errors.append(
            f"نام کاربری باید {USERNAME_MIN} تا {USERNAME_MAX} نویسهٔ انگلیسی باشد "
            "(حرف، رقم، نقطه یا زیرخط)."
        )
    if len(password) < PASSWORD_MIN:
        errors.append(f"رمز عبور باید حداقل {PASSWORD_MIN} نویسه باشد.")
    if len(password) > PASSWORD_MAX:
        errors.append("رمز عبور بیش از حد بلند است.")
    if password and username and password.lower() == username.lower():
        errors.append("رمز عبور نباید با نام کاربری یکی باشد.")
    if password != confirm:
        errors.append("تکرار رمز عبور یکسان نیست.")
    if errors:
        return None, errors, values
    return {"username": username, "password": password}, [], values


def validate_identity(form: Mapping[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[str], Dict[str, Any]]:
    """قدم اول ثبت‌نام: نام و نام خانوادگی (هر دو اجباری) و جنسیت."""
    name = str(form.get("name") or "").strip()
    family = str(form.get("family") or "").strip()
    gender = str(form.get("gender") or "")
    values = {
        "name": name,
        "family": family,
        "gender": gender if gender in {item["value"] for item in GENDERS} else "",
    }

    errors: List[str] = []
    if len(name) < 2:
        errors.append("نام را کامل بنویسید (حداقل دو حرف).")
    if len(name) > MAX_NAME:
        errors.append("نام بیش از حد بلند است.")
    if len(family) < 2:
        errors.append("نام خانوادگی را کامل بنویسید (حداقل دو حرف).")
    if len(family) > MAX_NAME:
        errors.append("نام خانوادگی بیش از حد بلند است.")
    if errors:
        return None, errors, values
    return values, [], values


def validate_birth(form: Mapping[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[str], Dict[str, Any]]:
    """قدم دوم: تاریخ دقیق تولد (شمسی)، ساعت تولد و شهر."""
    jy = _to_int(form.get("jy"), 1370)
    jm = _to_int(form.get("jm"), 1)
    jd = _to_int(form.get("jd"), 1)
    birth_time = str(form.get("birth_time") or "").strip()
    city = str(form.get("city") or "").strip()
    values = {"jy": jy, "jm": jm, "jd": jd, "birth_time": birth_time, "city": city}

    errors: List[str] = []
    if not is_valid_jalali(jy, jm, jd):
        errors.append("تاریخ تولد را درست انتخاب کنید (سال ۱۳۰۰ تا ۱۴۲۰).")
    if birth_time and parse_time_text(birth_time) is None:
        errors.append("ساعت تولد نامعتبر است.")
    if len(city) > MAX_NAME:
        errors.append("نام شهر بیش از حد بلند است.")
    if errors:
        return None, errors, values
    return values, [], values


def validate_profile(form: Mapping[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[str], Dict[str, Any]]:
    """بررسی کامل پروفایل (نام + تولد)؛ در پنل ادمین استفاده می‌شود."""
    identity, identity_errors, identity_values = validate_identity(form)
    birth, birth_errors, birth_values = validate_birth(form)
    values = {**identity_values, **birth_values}
    errors = list(identity_errors) + list(birth_errors)
    if errors or identity is None or birth is None:
        return None, errors, values
    return {**identity, **birth}, [], values


def validate_fortune(form: Mapping[str, Any], profile: Mapping[str, Any]) -> Tuple[Optional[FortuneRequest], List[str], Dict[str, Any]]:
    """ترکیب پروفایل ذخیره‌شده با انتخاب‌های این سفر."""
    # پیش‌نویس سفر، روش را در کلید «kind» نگه می‌دارد؛ فرم مستقیم از «method» می‌آید.
    method = str(form.get("method") or form.get("kind") or "hafez")
    topic = str(form.get("topic") or "general")
    intent = str(form.get("intent") or "").strip()

    values = {
        "method": method if method in method_catalogue.METHODS else "hafez",
        "topic": topic if topic in TOPICS else "general",
        "intent": intent,
    }
    errors: List[str] = []
    if len(intent) > MAX_INTENT:
        errors.append(f"متن نیت باید کمتر از {MAX_INTENT} حرف باشد.")
    if errors:
        return None, errors, values

    values["intent"] = intent
    request = FortuneRequest(
        name=str(profile.get("name") or "دوست"),
        gender=str(profile.get("gender") or ""),
        jy=int(profile.get("jy") or 1370),
        jm=int(profile.get("jm") or 1),
        jd=int(profile.get("jd") or 1),
        birth_time=str(profile.get("birth_time") or ""),
        city=str(profile.get("city") or ""),
        topic=values["topic"],
        intent=values["intent"],
        method=values["method"],
    )
    return request, [], values
