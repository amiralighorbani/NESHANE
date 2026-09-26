"""فهرست روش‌های فال: هر روش یک کارت در صفحهٔ انتخاب سفر است.

آیکون‌ها همه از Font Awesome (نسخهٔ ۶) و به‌صورت کلاس CSS ذخیره می‌شوند.
"""

from __future__ import annotations

from typing import Any, Dict, List

METHODS: Dict[str, Dict[str, Any]] = {
    "hafez": {
        "key": "hafez",
        "label": "فال حافظ",
        "short": "غزل",
        "icon": "fa-solid fa-book-open",
        "accent": "#7c5cd6",
        "tagline": "یک غزل از دیوان حافظ، با تعبیر و راهنمای امروز.",
        "about": "حافظ‌خوانی کهن‌ترین فال ایرانی است؛ غزلی که باز می‌شود، آینهٔ حال توست.",
        "steps": ["نیت کن", "غزل باز می‌شود", "تعبیر و راهنما"],
        "deck": "دیوان حافظ",
    },
    "tarot": {
        "key": "tarot",
        "label": "کارت تاروت",
        "short": "تاروت",
        "icon": "fa-solid fa-layer-group",
        "accent": "#c0577f",
        "tagline": "یکی از ۴۴ کارت (آرکانای بزرگ و خاندان‌ها)، با معنا و توصیه.",
        "about": "تاروت زبان نمادهاست؛ تصویر کارت، چیزی را که در ذهن داری روشن می‌کند.",
        "steps": ["نیت کن", "کارت کشیده می‌شود", "معنا و توصیه"],
        "deck": "۴۴ کارت تاروت",
    },
    "zodiac": {
        "key": "zodiac",
        "label": "طالع امروز",
        "short": "طالع",
        "icon": "fa-solid fa-sun",
        "accent": "#d99a1f",
        "tagline": "برج تولدت و انرژی امروز آسمان.",
        "about": "طالع‌بینی، ستون قدیمی فال‌گیری است؛ برج تو و سیّارهٔ امروز، لحن روزت را می‌سازند.",
        "steps": ["تاریخ تولد", "برج و عنصر", "طالع روز"],
        "deck": "دوازده برج، با تعبیر کامل",
    },
    "numerology": {
        "key": "numerology",
        "label": "عددشناسی",
        "short": "عدد",
        "icon": "fa-solid fa-hashtag",
        "accent": "#2f8fa8",
        "tagline": "عدد مسیر زندگی‌ات، از تاریخ تولد.",
        "about": "در عددشناسی، هر عدد یک شخصیت است؛ تاریخ تولدت مسیر زندگی‌ات را نشان می‌دهد و تعبیر هر عدد سه زاویه دارد: کار، رابطه و سلامت.",
        "steps": ["تاریخ تولد", "محاسبهٔ عدد", "تعبیر مسیر"],
        "deck": "یازده عدد، با تعبیر سه‌گانه",
    },
    "runes": {
        "key": "runes",
        "label": "سنگ رون",
        "short": "رون",
        "icon": "fa-solid fa-gem",
        "accent": "#3d7ad6",
        "tagline": "چهل‌و‌هشت سنگ رون: ۲۴ رون روشن و ۲۴ رون سایه.",
        "about": "رون‌ها سنگ‌های حکاکی‌شدهٔ شمال اروپا‌اند؛ هر رون یک پیام کوتاه و صریح دارد. سنگ‌های سایه، نیمهٔ سختِ همان رون را نشان می‌دهند.",
        "steps": ["نیت کن", "یک سنگ بیرون می‌آید", "پیام و توصیه"],
        "deck": "۴۸ سنگ رون",
    },
    "chinese": {
        "key": "chinese",
        "label": "طالع چینی",
        "short": "چینی",
        "icon": "fa-solid fa-dragon",
        "accent": "#c2483f",
        "tagline": "حیوان و قطب سال تولدت، به‌همراه عنصر سال.",
        "about": "در تقویم چینی، هر سال یک حیوان و یک قطب (یانگ/یین) دارد؛ جمع این دو، خوی غالب تو را می‌سازد.",
        "steps": ["سال تولد", "حیوان، قطب و عنصر", "طالع سال"],
        "deck": "۲۴ طالع (۱۲ حیوان × دو قطب)",
    },
    "dice": {
        "key": "dice",
        "label": "فال تاس",
        "short": "تاس",
        "icon": "fa-solid fa-dice",
        "accent": "#5c8f4a",
        "tagline": "سه تاس، یک خانه از ده خانه، یک پاسخ روشن.",
        "about": "فال تاس ساده و بی‌حاشیه است؛ مجموع سه تاس به تو می‌گوید امروز در کدام یک از ده خانه ایستاده‌ای.",
        "steps": ["نیت کن", "تاس‌ها ریخته می‌شوند", "خانه و توصیه"],
        "deck": "ده خانه",
    },
}

METHOD_ORDER: List[str] = ["hafez", "tarot", "zodiac", "numerology", "runes", "chinese", "dice"]

# گروه‌بندی برای نمایش در صفحهٔ انتخاب
METHOD_GROUPS: List[Dict[str, Any]] = [
    {"title": "فال‌های سنتی", "icon": "fa-solid fa-moon", "members": ["hafez", "tarot", "runes"]},
    {"title": "بر اساس تولد", "icon": "fa-solid fa-cake-candles", "members": ["zodiac", "numerology", "chinese"]},
    {"title": "فال‌های ساده", "icon": "fa-solid fa-dice", "members": ["dice"]},
]


def get_method(key: str) -> Dict[str, Any]:
    return METHODS.get(key) or METHODS["hafez"]


def catalogue() -> List[Dict[str, Any]]:
    return [METHODS[key] for key in METHOD_ORDER]
