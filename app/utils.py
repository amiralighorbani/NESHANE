"""ابزارهای پایه: تاریخ جلالی، برج فلکی، ارقام فارسی و متن‌های نمایشی."""

from __future__ import annotations

import re
from datetime import date
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# ارقام و متن / digits & labels
# --------------------------------------------------------------------------- #

FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"


def to_fa(value: object) -> str:
    """ارقام لاتین را برای نمایش به فارسی برمی‌گرداند."""
    return str(value).translate(str.maketrans("0123456789", FA_DIGITS))


def to_fa_number(value: object, decimals: int = 0) -> str:
    """عدد را با جداکنندهٔ هزارگان و ارقام فارسی برمی‌گرداند (برای آمار زندگی)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return to_fa(value)
    text = f"{number:,.{decimals}f}" if decimals else f"{number:,.0f}"
    return to_fa(text.replace(",", "٬").replace(".", "٫"))


def from_fa(value: object) -> str:
    """ارقام فارسی/عربی را به لاتین برمی‌گرداند (برای پردازش ورودی کاربر)."""
    text = str(value)
    for index, digit in enumerate(FA_DIGITS):
        text = text.replace(digit, str(index))
    return text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))


WEEKDAYS_FA = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]
# date.weekday(): 0=Monday ... 6=Sunday
MONTHS_FA = [
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
]

WEEKDAY_PLANET: Dict[str, Dict[str, str]] = {
    "شنبه": {"planet": "کیوان (زحل)", "element": "خاک", "note": "روزی برای نظم، صبر و ساختن پایه‌های محکم."},
    "یکشنبه": {"planet": "خورشید", "element": "آتش", "note": "روزی برای دیده‌شدن، روشنی و تصمیم‌های قاطع."},
    "دوشنبه": {"planet": "ماه", "element": "آب", "note": "روزی برای احساس، خانه و مراقبت از خود."},
    "سه‌شنبه": {"planet": "بهرام (مریخ)", "element": "آتش", "note": "روزی برای حرکت، شجاعت و به پایان رساندن کارها."},
    "چهارشنبه": {"planet": "تیر (عطارد)", "element": "باد", "note": "روزی برای گفت‌وگو، نوشتن و جابه‌جایی اطلاعات."},
    "پنجشنبه": {"planet": "برجیس (مشتری)", "element": "باد", "note": "روزی برای گشایش، بخشش و فراخ‌کردن افق."},
    "جمعه": {"planet": "ناهید (زهره)", "element": "خاک", "note": "روزی برای مهر، زیبایی و نزدیک‌شدن به دل‌ها."},
}


_TIME_RE = re.compile(r"^\s*(\d{1,2})\s*[:.\u066B]\s*(\d{1,2})\s*$")


def parse_time_text(value: object) -> Optional[int]:
    """«۰۸:۳۰» یا "8:30" را به دقیقهٔ روز تبدیل می‌کند."""
    if value is None or value == "":
        return None
    text = str(value).translate(str.maketrans(FA_DIGITS + "٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    match = _TIME_RE.match(text.replace("٫", ":"))
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour * 60 + minute
    return None


# --------------------------------------------------------------------------- #
# تبدیل تاریخ جلالی <-> میلادی
# --------------------------------------------------------------------------- #


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> Tuple[int, int, int]:
    jy += 1595
    days = -355668 + (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + jd
    days += (jm - 1) * 31 if jm < 7 else ((jm - 7) * 30) + 186
    gy = 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0
    month_days = [0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 13 and gd > month_days[gm]:
        gd -= month_days[gm]
        gm += 1
    return gy, gm, gd


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> Tuple[int, int, int]:
    month_days = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2, gm2, gd2 = gy - 1600, gm - 1, gd - 1
    day_no = 365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
    day_no += month_days[gm2] + gd2
    if gm > 2 and ((gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0):
        day_no += 1
    day_no -= 79
    cycles = day_no // 12053
    day_no %= 12053
    jy = 979 + 33 * cycles + 4 * (day_no // 1461)
    day_no %= 1461
    if day_no >= 366:
        jy += (day_no - 1) // 365
        day_no = (day_no - 1) % 365
    if day_no < 186:
        jm = 1 + day_no // 31
        jd = 1 + day_no % 31
    else:
        jm = 7 + (day_no - 186) // 30
        jd = 1 + (day_no - 186) % 30
    return jy, jm, jd


def jalali_is_leap(jy: int) -> bool:
    """آیا این سال جلالی کبیسه است؟ (یعنی اسفند ۳۰ روز دارد)

    به‌جای جدول دستیِ سال‌های کبیسه، از تبدیل خودِ برنامه استفاده می‌کنیم: اگر فاصلهٔ
    «۱ فروردین امسال» تا «۱ فروردین سال بعد» ۳۶۶ روز باشد، امسال کبیسه است. این‌طور
    تقویم در کل برنامه یک‌دست می‌ماند و مقدار ثابتی هم هارد‌کد نمی‌شود.
    """
    try:
        start = date(*jalali_to_gregorian(int(jy), 1, 1))
        end = date(*jalali_to_gregorian(int(jy) + 1, 1, 1))
    except (TypeError, ValueError):  # pragma: no cover - ورودی غیرعددی
        return False
    return (end - start).days == 366


def is_valid_jalali(jy: int, jm: int, jd: int) -> bool:
    """آیا این تاریخ در تقویم جلالی وجود دارد؟

    تفاوت مهم با نسخهٔ قبل: اسفند در سال‌های **غیرکبیسه ۲۹ روز** دارد و فقط در
    سال‌های کبیسه ۳۰ روز. قبلاً همیشه ۳۰ روز پذیرفته می‌شد و تاریخ‌های ناممکن
    (مثل ۳۰ اسفند ۱۴۰۰) از فیلتر رد می‌شدند.
    """
    if not (1300 <= jy <= 1420):
        return False
    if not (1 <= jm <= 12):
        return False
    if jm <= 6:
        return 1 <= jd <= 31
    if jm <= 11:
        return 1 <= jd <= 30
    return 1 <= jd <= (30 if jalali_is_leap(jy) else 29)


def jalali_today(today: date | None = None) -> Tuple[int, int, int]:
    current = today or date.today()
    return gregorian_to_jalali(current.year, current.month, current.day)


def weekday_fa(target: date | None = None) -> str:
    current = target or date.today()
    return WEEKDAYS_FA[current.weekday()]


def jalali_label(jy: int, jm: int, jd: int) -> str:
    return f"{to_fa(jd)} {MONTHS_FA[jm - 1]} {to_fa(jy)}"


def today_label(target: date | None = None) -> str:
    current = target or date.today()
    jy, jm, jd = jalali_today(current)
    return f"{weekday_fa(current)} {jalali_label(jy, jm, jd)}"


# --------------------------------------------------------------------------- #
# برج فلکی / zodiac sign
# --------------------------------------------------------------------------- #

# ترتیب برج‌ها از ۲۱ مارس (اول حمل) به بعد
ZODIAC_ORDER: List[str] = [
    "hamal",
    "sowr",
    "jowza",
    "saratan",
    "asad",
    "sonbole",
    "mizan",
    "aqrab",
    "qows",
    "jadi",
    "dalu",
    "hut",
]

# آفست روزِ سالِ میلادی بدون احتساب کبیسه (۲۱ مارس = روز ۸۰)
_MONTH_OFFSETS = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
# فاصلهٔ شروع هر برج از ۲۱ مارس
_ZODIAC_STARTS = [0, 30, 61, 92, 124, 155, 186, 216, 246, 276, 305, 335]


def zodiac_key(month: int, day: int) -> str:
    """کلید برج فلکی بر اساس ماه و روز میلادی."""
    day_of_year = _MONTH_OFFSETS[month - 1] + day
    index = (day_of_year - 80) % 365
    picked = ZODIAC_ORDER[0]
    for position, start in enumerate(_ZODIAC_STARTS):
        if index >= start:
            picked = ZODIAC_ORDER[position]
    return picked


# --------------------------------------------------------------------------- #
# ساعت‌ها / time helpers
# --------------------------------------------------------------------------- #


def hour_slot_label(hour: int) -> str:
    hour = int(hour) % 24
    return f"{to_fa(f'{hour:02d}')}:۰۰"


def hour_window(start_hour: int) -> str:
    return f"{hour_slot_label(start_hour)} تا {hour_slot_label(start_hour + 2)}"
