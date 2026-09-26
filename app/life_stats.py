"""«زندگی در عدد»: از تاریخ و ساعت تولد، آمار کامل عمر را حساب می‌کند.

همهٔ محاسبه‌ها از تاریخ تولد (شمسی) و ساعت تولد انجام می‌شود؛ هیچ داده‌ای از کاربر
اضافه‌تر از آنچه در پروفایل دارد لازم نیست. نرخ‌های بدنی و جمعیتی، میانگین‌های
عمومی و برای سرگرمی‌اند، نه اندازه‌گیری پزشکی.

خروجی `build()` یک دیکشنری با گروه‌های آماده برای نمایش است:
    identity  شناسنامهٔ لحظهٔ تولد (شمسی، میلادی، روز هفته، فصل، برج، حیوان سال، عدد مسیر)
    time      عمر سپری‌شده در مقیاس‌های مختلف
    body      ضربان قلب، نفس، وعدهٔ غذا، خواب، پلک، قدم، خونی که قلب پمپ کرده
    world     جمعیت روز تولد، نوزادان همان روز، مسافت سفر زمین، تعداد ماه کامل
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from .content import astrology, chinese, numerology
from .utils import (
    MONTHS_FA,
    WEEKDAY_PLANET,
    WEEKDAYS_FA,
    jalali_label,
    jalali_to_gregorian,
    parse_time_text,
    to_fa,
    to_fa_number,
    zodiac_key,
)

# --------------------------------------------------------------------------- #
# نرخ‌های تقریبی / average rates
# --------------------------------------------------------------------------- #

HEART_BEATS_PER_MINUTE = 72
BREATHS_PER_MINUTE = 16
MEALS_PER_DAY = 3
SLEEP_HOURS_PER_DAY = 8
BLINKS_PER_MINUTE = 15
WORDS_PER_DAY = 16000
STEPS_PER_DAY = 5000
BLOOD_LITRES_PER_DAY = 7000
HAIR_CM_PER_MONTH = 1.0
NAIL_MM_PER_MONTH = 3.5
FULL_MOONS_PER_YEAR = 12.37
OLYMPIC_POOL_LITRES = 2_500_000
EARTH_KM_PER_HOUR = 107_000
EARTH_KM_PER_YEAR = 940_000_000
LIFE_EXPECTANCY_YEARS = 76
WALK_TO_MOON_KM = 384_400
WORDS_PER_BOOK = 80_000
DREAMS_PER_NIGHT = 4
LAUGHS_PER_DAY = 20
SNEEZES_PER_DAY = 4
TEARS_PER_DAY = 15
HANDS_PER_DAY = 8
CALORIES_PER_DAY = 1800
WATER_LITRES_PER_DAY = 2.5
RED_CELLS_PER_SECOND = 2_400_000
ROTATION_KM_PER_DAY = 34_500  # مسافت چرخش زمین در عرض جغرافیایی ایران
SONGS_PER_DAY = 20
ECLIPSES_PER_YEAR = 2.4
SYNODIC_MONTH_DAYS = 29.530588853
KNOWN_NEW_MOON = date(2000, 1, 6)

MONTHS_GREGORIAN_FA: Dict[int, str] = {
    1: "ژانویه",
    2: "فوریه",
    3: "مارس",
    4: "آوریل",
    5: "مه",
    6: "ژوئن",
    7: "ژوئیه",
    8: "اوت",
    9: "سپتامبر",
    10: "اکتبر",
    11: "نوامبر",
    12: "دسامبر",
}

SEASON_MOOD: Dict[str, str] = {
    "بهار": "شروع و زایش؛ سالی که از نو جوان می‌شود",
    "تابستان": "اوج و گرما؛ بیشترین نور سال",
    "پاییز": "برداشت و تغییر؛ فصل رنگ‌های صادق",
    "زمستان": "سکوت و ذخیره؛ فصل شب‌های بلند",
}

# سنگ و گل ماه تولد (میلادی)
BIRTH_MONTH_LORE: Dict[int, Dict[str, str]] = {
    1: {"stone": "گارنت", "flower": "میخک"},
    2: {"stone": "آمیتیست", "flower": "بنفشه"},
    3: {"stone": "آکوامارین", "flower": "نرگس"},
    4: {"stone": "الماس", "flower": "گل مینا"},
    5: {"stone": "زمرد", "flower": "زنبق"},
    6: {"stone": "مروارید", "flower": "رز"},
    7: {"stone": "یاقوت سرخ", "flower": "نیلوفر"},
    8: {"stone": "زبرجد", "flower": "گلایول"},
    9: {"stone": "یاقوت کبود", "flower": "گل ستاره‌ای"},
    10: {"stone": "اپال", "flower": "همیشه‌بهار"},
    11: {"stone": "توپاز", "flower": "داوودی"},
    12: {"stone": "فیروزه", "flower": "نرگس زرد"},
}

# مضمون ماه‌های شمسی
MONTH_MOOD: Dict[int, str] = {
    1: "شروع و رویش",
    2: "گرمای اول سال",
    3: "اوج بهار",
    4: "طولانی‌ترین روزها",
    5: "گرمای تیرماه",
    6: "اوج تابستان",
    7: "اول مهر، اول پاییز",
    8: "برگ‌ریزان",
    9: "سرد شدن هوا",
    10: "شب‌های بلند",
    11: "سردترین روزها",
    12: "پایان و شروع تازه",
}

# جمعیت جهان بر حسب میلیون نفر (برآورد تاریخی)
WORLD_POPULATION_MILLIONS: Dict[int, float] = {
    1900: 1650, 1910: 1750, 1920: 1860, 1930: 2070, 1940: 2300, 1950: 2540,
    1960: 3040, 1970: 3700, 1980: 4450, 1990: 5320, 2000: 6140, 2010: 6950,
    2015: 7380, 2020: 7790, 2025: 8200,
}

# تولدهای جهان در سال، بر حسب میلیون نفر
WORLD_BIRTHS_MILLIONS: Dict[int, float] = {
    1950: 97, 1960: 110, 1970: 121, 1980: 128, 1990: 140,
    2000: 131, 2010: 136, 2020: 140, 2025: 132,
}


def _interpolate(table: Dict[int, float], year: int) -> float:
    """درون‌یابی خطی بین دو نقطهٔ جدول."""
    keys = sorted(table)
    if year <= keys[0]:
        # قبل از اولین نقطه، با نرخ رشد دههٔ اول به عقب برمی‌گردیم.
        return max(700.0, table[keys[0]] - 10.5 * (keys[0] - year))
    if year >= keys[-1]:
        return table[keys[-1]] + 26 * (year - keys[-1])
    for lower, upper in zip(keys, keys[1:]):
        if lower <= year <= upper:
            ratio = (year - lower) / (upper - lower)
            return table[lower] + ratio * (table[upper] - table[lower])
    return table[keys[-1]]


def _card(icon: str, value: str, label: str, hint: str = "") -> Dict[str, str]:
    return {"icon": icon, "value": value, "label": label, "hint": hint}


MOON_PHASES: List[Tuple[float, str, str]] = [
    (0.0625, "ماه نو", "fa-solid fa-circle"),
    (0.1875, "هلال افزاینده", "fa-solid fa-moon"),
    (0.3125, "نیمهٔ ماه (رشد)", "fa-solid fa-circle-half-stroke"),
    (0.4375, "ماه کوژ (رشد)", "fa-solid fa-moon"),
    (0.5625, "ماه کامل", "fa-solid fa-circle"),
    (0.6875, "ماه کوژ (کاهنده)", "fa-solid fa-moon"),
    (0.8125, "نیمهٔ ماه (کاهش)", "fa-solid fa-circle-half-stroke"),
    (0.9375, "هلال کاهنده", "fa-solid fa-moon"),
]


def _moon_phase(born: date) -> Dict[str, str]:
    """فاز تقریبی ماه در شب تولد (تقریب نجومی کافی برای سرگرمی)."""
    days = (born - KNOWN_NEW_MOON).days
    fraction = (days % SYNODIC_MONTH_DAYS) / SYNODIC_MONTH_DAYS
    name, icon = MOON_PHASES[-1][1], MOON_PHASES[-1][2]
    for limit, phase_name, phase_icon in MOON_PHASES:
        if fraction < limit:
            name, icon = phase_name, phase_icon
            break
    illumination = round(100 * (1 - math.cos(2 * math.pi * fraction)) / 2)
    return {
        "name": name,
        "icon": icon,
        "fraction": str(fraction),
        "illumination": to_fa_number(illumination),
    }


def _next_birthday(born: date, today: date) -> Tuple[int, int]:
    """روزهای مانده تا تولد بعدی و سال آن تولد."""
    for year in (today.year, today.year + 1):
        try:
            candidate = born.replace(year=year)
        except ValueError:  # ۲۹ فوریه در سال غیرکبیسه
            candidate = date(year, 2, 28)
        if candidate >= today:
            return (candidate - today).days, year
    return 365, today.year + 1


def _age_parts(birth: date, today: date) -> Tuple[int, int, int, int]:
    """سن کامل: سال، ماه، روز و روزهای کل."""
    total_days = (today - birth).days
    years = today.year - birth.year
    months = today.month - birth.month
    days = today.day - birth.day
    if days < 0:
        months -= 1
        previous_month = today.month - 1 or 12
        previous_year = today.year if today.month > 1 else today.year - 1
        days += (date(previous_year, previous_month % 12 + 1, 1) - date(previous_year, previous_month, 1)).days
    if months < 0:
        years -= 1
        months += 12
    return max(0, years), max(0, months), max(0, days), max(0, total_days)


def birth_moment(jy: int, jm: int, jd: int, birth_time: str = "") -> Tuple[date, Optional[int]]:
    """تاریخ میلادی تولد و دقیقهٔ روز (اگر ساعت داده شده باشد)."""
    gy, gm, gd = jalali_to_gregorian(int(jy), int(jm), int(jd))
    try:
        born = date(gy, gm, gd)
    except ValueError:
        born = date(1990, 1, 1)
    return born, parse_time_text(birth_time) if birth_time else None


def build(
    jy: int,
    jm: int,
    jd: int,
    birth_time: str = "",
    city: str = "",
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """گزارش کامل «زندگی در عدد» برای یک تاریخ تولد."""
    moment = now or datetime.now()
    born, minutes_of_day = birth_moment(jy, jm, jd, birth_time)
    today = moment.date()
    if born > today:
        born = today

    years, months, days, total_days = _age_parts(born, today)
    start = datetime(born.year, born.month, born.day, 12, 0)
    if minutes_of_day is not None:
        start = start.replace(hour=minutes_of_day // 60, minute=minutes_of_day % 60)
    lived = moment - start
    total_seconds = max(0.0, lived.total_seconds())
    total_minutes = total_seconds / 60
    total_hours = total_minutes / 60
    total_weeks = total_days // 7

    alive_years = max(0.0001, total_seconds / (365.2425 * 24 * 3600))

    # ---------------- شناسنامهٔ لحظهٔ تولد ----------------
    gy, gm, gd = born.year, born.month, born.day
    sign = astrology.get_sign(zodiac_key(gm, gd))
    animal = chinese.animal_for_year(gy)
    element = chinese.element_for_year(gy)
    path_number = numerology.life_path(gy, gm, gd)
    path = numerology.get_path(path_number)
    season = (
        "بهار" if jm <= 3 else "تابستان" if jm <= 6 else "پاییز" if jm <= 9 else "زمستان"
    )
    weekday = WEEKDAYS_FA[born.weekday()]
    planet = WEEKDAY_PLANET.get(weekday, {})

    identity: List[Dict[str, str]] = [
        _card("fa-solid fa-calendar-day", jalali_label(jy, jm, jd), "تاریخ تولد (شمسی)", f"{weekday} — {season}"),
        _card(
            "fa-solid fa-earth-asia",
            to_fa(f"{gd:02d}.{gm:02d}.{gy}"),
            "تاریخ تولد (میلادی)",
            "بر پایهٔ تقویم میلادی",
        ),
        _card("fa-solid fa-star", f"{sign['symbol']} {sign['name']}", "برج فلکی", str(sign["element"])),
        _card(
            "fa-solid fa-dragon",
            str(animal.get("name") or "—"),
            "حیوان سال چینی",
            f"{element.get('name', '')} — {element.get('note', '')}".strip(" —"),
        ),
        _card(
            "fa-solid fa-hashtag",
            f"{to_fa(path_number)} — {path.get('title', '')}".strip(" —"),
            "عدد مسیر زندگی",
            "محاسبه‌شده از تاریخ تولد میلادی",
        ),
        _card(
            "fa-solid fa-clock",
            to_fa(birth_time) if birth_time else "نامعلوم",
            "ساعت تولد",
            f"سیّارهٔ روز تولد: {planet.get('planet', '—')}" if planet else "سیّارهٔ روز تولد: —",
        ),
    ]
    # ---------------- داستان همان روز ---------------- #
    month_lore = BIRTH_MONTH_LORE.get(gm, {"stone": "—", "flower": "—"})
    day_of_year = born.timetuple().tm_yday
    week_of_year = born.isocalendar()[1]
    is_leap = born.year % 4 == 0 and (born.year % 100 != 0 or born.year % 400 == 0)
    year_days = 366 if is_leap else 365
    days_to_birthday, next_birthday_year = _next_birthday(born, today)
    phases = _moon_phase(born)
    month_mood = MONTH_MOOD.get(jm, "")
    birthday_day_number = numerology.reduce_number(int(gd))
    half_of_year = "نیمهٔ اول سال" if jm <= 6 else "نیمهٔ دوم سال"

    identity.extend(
        [
            _card(
                "fa-solid fa-leaf",
                f"{MONTHS_FA[max(0, min(11, jm - 1))]} و {MONTHS_GREGORIAN_FA.get(gm, '')}",
                "ماه تولدت",
                month_mood,
            ),
            _card(
                "fa-solid fa-hourglass-start",
                "سال کبیسه" if is_leap else "سال عادی",
                "سال تولدت",
                f"{to_fa_number(year_days)} روز داشت",
            ),
            _card(
                "fa-solid fa-scale-balanced",
                half_of_year,
                "جای تولدت در سال",
                f"{to_fa(jm)}اُمین ماه سال، از {to_fa(12)} ماه",
            ),
        ]
    )

    if city:
        identity.append(_card("fa-solid fa-location-dot", str(city), "شهر تولد", "همان‌جایی که اولین نفس را کشیدی"))

    # ---------------- گروه: روز تولدت ---------------- #
    birthday_cards: List[Dict[str, str]] = [
        _card(
            "fa-solid fa-calendar-day",
            f"{weekday}",
            "روز هفتهٔ تولدت",
            f"سیّارهٔ این روز: {planet.get('planet', '—')}" if planet else "",
        ),
        _card(
            "fa-solid fa-list-ol",
            f"{to_fa_number(day_of_year)}اُمین روز",
            "چندمین روز سال بود",
            f"شمرده از اول ژانویه؛ در تقویم شمسی، {to_fa(jm)}اُمین ماه سال",
        ),
        _card(
            "fa-solid fa-calendar-week",
            f"هفتهٔ {to_fa_number(week_of_year)}",
            "چندمین هفتهٔ سال",
            "شمرده با تقویم هفتهٔ بین‌المللی",
        ),
        _card(
            phases["icon"],
            phases["name"],
            "ماه در شب تولدت",
            f"حدود {phases['illumination']}٪ قرص ماه روشن بود",
        ),
        _card("fa-solid fa-gem", month_lore["stone"], "سنگ تولدت", "سنگ ماه تولدت در سنت غربی"),
        _card("fa-solid fa-spa", month_lore["flower"], "گل تولدت", "گلی که به ماه تولدت نسبت می‌دهند"),
        _card(
            "fa-solid fa-cake-candles",
            "امروز!" if days_to_birthday == 0 else f"{to_fa_number(days_to_birthday)} روز",
            "فاصله تا تولد بعدی",
            f"تولد بعدی‌ات را در سال {to_fa_number(next_birthday_year)} جشن می‌گیری",
        ),
        _card(
            "fa-solid fa-hashtag",
            to_fa(birthday_day_number),
            "عدد روز تولدت",
            "عدد یک‌رقمی روز تولد؛ در اعداد، رنگ و بوی آن روز را نشان می‌دهد",
        ),
        _card(
            "fa-solid fa-cloud-sun",
            season,
            "فصل تولدت",
            SEASON_MOOD.get(season, ""),
        ),
    ]

    # ---------------- عمر سپری‌شده ----------------
    time_cards: List[Dict[str, str]] = [
        _card(
            "fa-solid fa-cake-candles",
            f"{to_fa_number(years)} سال و {to_fa_number(months)} ماه",
            "سن دقیق",
            f"{to_fa_number(days)} روز هم اضافه بر آن",
        ),
        _card("fa-solid fa-sun", to_fa_number(total_days) + " روز", "روزهایی که زنده بوده‌ای", f"حدود {to_fa_number(total_weeks)} هفتهٔ کامل"),
        _card("fa-solid fa-calendar-week", to_fa_number(total_weeks) + " هفته", "هفته‌های عمر", "هر هفته، یک فصل تازه از زندگی"),
        _card("fa-solid fa-clock-rotate-left", to_fa_number(total_hours) + " ساعت", "ساعت‌های عمر", f"≈ {to_fa_number(total_minutes)} دقیقه"),
        _card(
            "fa-solid fa-hourglass-half",
            to_fa_number(total_seconds),
            "ثانیه‌هایی که گذشته",
            "و شمارش ادامه دارد",
        ),
        _card(
            "fa-solid fa-leaf",
            to_fa_number(alive_years * 4),
            "فصل‌هایی که دیده‌ای",
            "چهار فصل در هر سال، از بهار اول تا بهار امسال",
        ),
        _card(
            "fa-solid fa-moon",
            to_fa_number((total_days // 7) * 2),
            "آخر هفته‌ها",
            "شنبه‌ها و جمعه‌هایی که گذرانده‌ای",
        ),
        _card(
            "fa-solid fa-mountain-sun",
            to_fa_number(total_days),
            "طلوع‌هایی که دیده‌ای",
            "هر روز یک طلوع تازه، از اولین صبح تا امروز",
        ),
        _card(
            "fa-solid fa-bed-pulse",
            to_fa_number(round(total_days * (1 - SLEEP_HOURS_PER_DAY / 24))),
            "روزهای بیداری",
            "عمر بیداری‌ات، بعد از کسر خواب هر شب",
        ),
        _card(
            "fa-solid fa-calendar-minus",
            to_fa_number(round(alive_years * 12)),
            "ماه‌هایی که زندگی کرده‌ای",
            "از همان ماه اول، تا این ماه",
        ),
        _card(
            "fa-solid fa-layer-group",
            f"{to_fa_number(int(alive_years) // 10)} دهه و {to_fa(years % 10)} سال",
            "دهه‌های عمرت",
            "هر ده سال، یک فصل کاملاً تازه از تو",
        ),
        _card(
            "fa-solid fa-cake-candles",
            to_fa_number(years),
            "تولدهایی که جشن گرفته‌ای",
            f"تولد بعدی: {to_fa_number(days_to_birthday)} روز دیگر",
        ),
        _card(
            "fa-solid fa-seedling",
            to_fa_number(max(0, LIFE_EXPECTANCY_YEARS - years)),
            "سال‌های پیش رو",
            f"تا امید زندگی میانگین ({to_fa(LIFE_EXPECTANCY_YEARS)} سال) این‌قدر جا داری",
        ),
    ]

    # ---------------- بدن ----------------
    heartbeats = total_minutes * HEART_BEATS_PER_MINUTE
    body_cards: List[Dict[str, str]] = [
        _card(
            "fa-solid fa-heart-pulse",
            to_fa_number(heartbeats),
            "ضربان قلب تا امروز",
            f"حدود {to_fa_number(HEART_BEATS_PER_MINUTE * 60 * 24)} ضربان در شبانه‌روز، از روز اول",
        ),
        _card(
            "fa-solid fa-wind",
            to_fa_number(total_minutes * BREATHS_PER_MINUTE),
            "نفس‌هایی که کشیده‌ای",
            f"≈ {to_fa_number(BREATHS_PER_MINUTE * 60 * 24)} نفس در هر شبانه‌روز",
        ),
        _card(
            "fa-solid fa-utensils",
            to_fa_number(total_days * MEALS_PER_DAY),
            "وعده‌های غذایی",
            f"{to_fa(MEALS_PER_DAY)} وعده در روز، از روز اول تا امروز",
        ),
        _card(
            "fa-solid fa-bed",
            to_fa_number(total_days * SLEEP_HOURS_PER_DAY) + " ساعت",
            "ساعت‌هایی که خواب بوده‌ای",
            f"یعنی حدود {to_fa_number(total_days * SLEEP_HOURS_PER_DAY / 24 / 365.2425, 1)} سال از عمرت در خواب گذشته",
        ),
        _card(
            "fa-solid fa-eye",
            to_fa_number(total_minutes * BLINKS_PER_MINUTE * 2 / 3),
            "پلک‌زدن‌ها",
            "بر پایهٔ ۱۵ پلک در دقیقه در ساعات بیداری",
        ),
        _card(
            "fa-solid fa-shoe-prints",
            to_fa_number(total_days * STEPS_PER_DAY) + " قدم",
            "قدم‌هایی که برداشته‌ای",
            f"≈ {to_fa_number(total_days * STEPS_PER_DAY * 0.75 / 1000)} کیلومتر راه‌پیمایی",
        ),
        _card(
            "fa-solid fa-droplet",
            to_fa_number(total_days * BLOOD_LITRES_PER_DAY / OLYMPIC_POOL_LITRES, 2) + " استخر",
            "خونی که قلبت پمپ کرده",
            f"≈ {to_fa_number(total_days * BLOOD_LITRES_PER_DAY / 1000)} هزار لیتر (استخر المپیک: ۲.۵ میلیون لیتر)",
        ),
        _card(
            "fa-solid fa-scissors",
            to_fa_number(alive_years * 12 * HAIR_CM_PER_MONTH) + " سانتی‌متر",
            "رشد موی سرت",
            f"ناخن‌ها هم حدود {to_fa_number(alive_years * 12 * NAIL_MM_PER_MONTH)} میلی‌متر رشد کرده‌اند",
        ),
        _card(
            "fa-solid fa-dna",
            to_fa_number(total_seconds * RED_CELLS_PER_SECOND),
            "گلبول‌های قرمزی که ساخته‌ای",
            "بدنت هر ثانیه حدود ۲.۴ میلیون گلبول قرمز نو می‌سازد",
        ),
        _card(
            "fa-solid fa-fire-flame-simple",
            to_fa_number(total_days * CALORIES_PER_DAY) + " کالری",
            "انرژی‌ای که سوزانده‌ای",
            f"حدود {to_fa_number(CALORIES_PER_DAY)} کالری در شبانه‌روز، فقط برای زنده ماندن",
        ),
        _card(
            "fa-solid fa-glass-water",
            to_fa_number(total_days * WATER_LITRES_PER_DAY) + " لیتر",
            "آبی که نوشیده‌ای",
            "میانگین ۲.۵ لیتر در روز (آب و نوشیدنی‌ها)",
        ),
        _card(
            "fa-solid fa-cloud-moon",
            to_fa_number(total_days * DREAMS_PER_NIGHT),
            "رویاهایی که دیده‌ای",
            "هر شب چند خواب؛ بیشترشان پیش از صبح فراموش می‌شوند",
        ),
        _card(
            "fa-solid fa-face-laugh-beam",
            to_fa_number(total_days * LAUGHS_PER_DAY),
            "لبخندها و خنده‌ها",
            "با میانگین ۲۰ لبخند در روز؛ بدنت هر بار هورمون شادی می‌سازد",
        ),
        _card(
            "fa-solid fa-wind",
            to_fa_number(total_days * SNEEZES_PER_DAY),
            "عطسه‌ها",
            "حدود ۴ عطسه در روز؛ سریع‌ترین رفلکس بدن",
        ),
        _card(
            "fa-solid fa-hands-bubbles",
            to_fa_number(total_days * HANDS_PER_DAY),
            "دست‌هایی که شسته‌ای",
            "تخمینی با ۸ بار در روز",
        ),
    ]

    # ---------------- جهان ----------------
    population = _interpolate(WORLD_POPULATION_MILLIONS, gy) * 1_000_000
    population_now = _interpolate(WORLD_POPULATION_MILLIONS, today.year) * 1_000_000
    births_year = _interpolate(WORLD_BIRTHS_MILLIONS, gy) * 1_000_000
    same_day_births = births_year / 365.2425
    world_cards: List[Dict[str, str]] = [
        _card(
            "fa-solid fa-people-group",
            to_fa_number(population),
            "جمعیت جهان در روز تولدت",
            f"روزی که به دنیا آمدی، حدود {to_fa_number(population / 1e9, 2)} میلیارد نفر روی زمین بودند",
        ),
        _card(
            "fa-solid fa-baby",
            to_fa_number(same_day_births),
            "هم‌روزهای تو",
            "تعداد نوزادانی که همان روز با تو به دنیا آمدند",
        ),
        _card(
            "fa-solid fa-rocket",
            to_fa_number(alive_years * EARTH_KM_PER_YEAR),
            "کیلومتری که در فضا سفر کرده‌ای",
            "زمین با تو، هر سال ۹۴۰ میلیون کیلومتر دور خورشید می‌چرخد",
        ),
        _card(
            "fa-solid fa-moon",
            to_fa_number(alive_years * FULL_MOONS_PER_YEAR),
            "ماه‌های کامل",
            "تعداد باری که ماه کامل را دیده‌ای",
        ),
        _card(
            "fa-solid fa-shoe-prints",
            to_fa_number(alive_years * EARTH_KM_PER_HOUR * 24 * 365.2425 / WALK_TO_MOON_KM),
            "مسیر زمین تا ماه",
            "به این تعداد، مسافت زمین تا ماه را در فضا پیموده‌ای",
        ),
        _card(
            "fa-solid fa-chart-line",
            to_fa_number(100 * alive_years / LIFE_EXPECTANCY_YEARS) + "٪",
            "از عمر میانگین",
            f"بر پایهٔ امید زندگی {to_fa(LIFE_EXPECTANCY_YEARS)} سال",
        ),
        _card(
            "fa-solid fa-comment-dots",
            to_fa_number(total_days * WORDS_PER_DAY),
            "کلمه‌هایی که گفته‌ای",
            "تخمینی با میانگین ۱۶٬۰۰۰ کلمه در روز",
        ),
        _card(
            "fa-solid fa-mug-hot",
            to_fa_number(total_days),
            "شب‌هایی که سر بر بالین گذاشته‌ای",
            "هر شب، یک پایان و یک شروع تازه",
        ),
        _card(
            "fa-solid fa-earth-americas",
            to_fa_number(total_days * ROTATION_KM_PER_DAY) + " کیلومتر",
            "مسافتی که زمین تو را چرخاند",
            "هر شبانه‌روز، یک دور کامل زمین — از دید ناظر روی استوا",
        ),
        _card(
            "fa-solid fa-sun",
            to_fa_number(alive_years * EARTH_KM_PER_YEAR) + " کیلومتر",
            "سفرت دور خورشید",
            "در همین مدت، زمین این‌قدر در مدارش پیش رفته",
        ),
        _card(
            "fa-solid fa-circle-half-stroke",
            to_fa_number(alive_years * ECLIPSES_PER_YEAR, 1),
            "گرفتگی‌های آسمان",
            "میانگین گرفتگی خورشید و ماه در هر سال",
        ),
        _card(
            "fa-solid fa-baby-carriage",
            to_fa_number(alive_years * births_year),
            "کسانی که بعد از تو آمدند",
            "تخمین نوزادان جهان از روز تولدت تا امروز",
        ),
        _card(
            "fa-solid fa-users-line",
            to_fa_number(population_now),
            "جمعیت جهان امروز",
            f"آن روز {to_fa_number(population / 1e9, 2)} میلیارد بود؛ امروز بیشتر شده",
        ),
        _card(
            "fa-solid fa-book-open",
            to_fa_number(total_days * WORDS_PER_DAY / WORDS_PER_BOOK),
            "کتاب‌هایی که حرف زده‌ای",
            "هر کتاب را ۸۰ هزار کلمه حساب کرده‌ایم",
        ),
        _card(
            "fa-solid fa-music",
            to_fa_number(total_days * SONGS_PER_DAY),
            "آهنگ‌هایی که شنیده‌ای",
            "تخمینی با ۲۰ آهنگ در روز",
        ),
    ]

    headline = (
        f"{to_fa_number(total_days)} روز زندگی، {to_fa_number(heartbeats)} ضربان قلب "
        f"و {to_fa_number(total_days * MEALS_PER_DAY)} وعدهٔ غذا تا همین لحظه"
    )

    return {
        "years": years,
        "months": months,
        "days": days,
        "total_days": total_days,
        "total_weeks": total_weeks,
        "total_hours": total_hours,
        "total_seconds": total_seconds,
        "age_label": f"{to_fa(years)} سال و {to_fa(months)} ماه و {to_fa(days)} روز",
        "birth_label": jalali_label(jy, jm, jd),
        "birth_gregorian": to_fa(f"{gy}-{gm:02d}-{gd:02d}"),
        "weekday": weekday,
        "season": season,
        "sign": sign,
        "animal": animal,
        "element": element,
        "path": path,
        "life_path_number": path_number,
        "headline": headline,
        # درصدی از عمر میانگین که گذشته؛ برای حلقهٔ پیشرفت و نوارها
        "life_progress": max(0, min(100, round(100 * alive_years / LIFE_EXPECTANCY_YEARS))),
        "life_expectancy": LIFE_EXPECTANCY_YEARS,
        "heartbeats": total_days * HEART_BEATS_PER_MINUTE * 24 * 60,
        "meals": total_days * MEALS_PER_DAY,
        "same_day_people": same_day_births,
        "identity": identity,
        "time": time_cards,
        "body": body_cards,
        "world": world_cards,
        "groups": [
            {"key": "birthday", "title": "داستان روز تولدت", "icon": "fa-solid fa-cake-candles", "tint": "#c98a2e", "cards": birthday_cards},
            {"key": "time", "title": "عمر سپری‌شده", "icon": "fa-solid fa-hourglass-half", "tint": "#7c5cd6", "cards": time_cards},
            {"key": "body", "title": "بدن تو در عدد", "icon": "fa-solid fa-heart-pulse", "tint": "#d9534f", "cards": body_cards},
            {"key": "world", "title": "تو و جهان", "icon": "fa-solid fa-earth-asia", "tint": "#2f8fa8", "cards": world_cards},
        ],
        "days_to_birthday": days_to_birthday,
        "moon_phase": phases["name"],
        "stone": month_lore["stone"],
        "flower": month_lore["flower"],
    }


def month_name(jm: int) -> str:
    return MONTHS_FA[max(0, min(11, int(jm) - 1))]
