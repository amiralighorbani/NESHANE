"""فهرست تست‌های شخصیت‌شناسی و روان‌شناسی.

ده تست در چهار خانواده:

* کهن‌الگو و تیپ: MBTI، کهن‌الگوهای یونگ، کهن‌الگوهای یونانی، انیاگرام
* علمی و رفتاری: پنج عامل بزرگ (Big Five)، DISC
* رابطه و احساس: زبان عشق، هفت چاکرا
* استعداد و سرشت: هوش‌های چندگانه (گاردنر)، مزاج‌های چهارگانه
"""

from __future__ import annotations

from typing import Any, Dict, List

from . import archetype, big5, chakra, disc, enneagram, gardner, greek, love, mbti, mizaj

TESTS: Dict[str, Dict[str, Any]] = {
    "mbti": mbti.TEST,
    "big5": big5.TEST,
    "greek": greek.TEST,
    "archetype": archetype.TEST,
    "enneagram": enneagram.TEST,
    "chakra": chakra.TEST,
    "love": love.TEST,
    "gardner": gardner.TEST,
    "disc": disc.TEST,
    "mizaj": mizaj.TEST,
}

TEST_ORDER: List[str] = [
    "mbti",
    "big5",
    "greek",
    "archetype",
    "enneagram",
    "chakra",
    "love",
    "gardner",
    "disc",
    "mizaj",
]

TEST_GROUPS: List[Dict[str, Any]] = [
    {
        "key": "type",
        "title": "تیپ و کهن‌الگو",
        "icon": "fa-solid fa-masks-theater",
        "members": ["mbti", "greek", "archetype", "enneagram"],
    },
    {
        "key": "science",
        "title": "علمی و رفتاری",
        "icon": "fa-solid fa-flask",
        "members": ["big5", "disc"],
    },
    {
        "key": "feeling",
        "title": "رابطه و احساس",
        "icon": "fa-solid fa-heart",
        "members": ["love", "chakra"],
    },
    {
        "key": "talent",
        "title": "استعداد و سرشت",
        "icon": "fa-solid fa-seedling",
        "members": ["gardner", "mizaj"],
    },
]


def get_test(key: str) -> Dict[str, Any]:
    return TESTS.get(key) or TESTS["mbti"]


def catalogue() -> List[Dict[str, Any]]:
    return [TESTS[key] for key in TEST_ORDER]


def question_count(key: str) -> int:
    return len(get_test(key)["questions"])
