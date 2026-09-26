"""استخر فال حافظ: کارت‌های دست‌نویس پروژه + غزل‌های واقعی گرفته‌شده از نت.

هر فال یک ساختار یکسان دارد تا هر جای برنامه (صفحهٔ نتیجه، پنل ادمین) بتواند
بدون دانستن منبعش با آن کار کند:

    key            شناسهٔ یکتا
    id             شمارهٔ غزل (برای نمایش)
    title          عنوان کارت، مثل «غزل شمارهٔ ۴۹۰»
    verses         مصراع‌ها (۴ مصراع = مطلع + مقطع)
    keywords       برچسب‌های موضوعی
    interpretation تعبیر
    guidance       راهنمای عملی
    theme          کلید تم
    theme_label    نام تم
    source         "curated" یا "web"
    source_label   متن نمایشی منبع

کارت‌های دست‌نویس، تعبیر نوشتهٔ خود پروژه را دارند؛ غزل‌های گرفته‌شده از نت،
ابیات واقعی‌اند و تعبیرشان با موتور تم (`fortune_themes.py`) ساخته شده است.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from .. import db
from . import ghazals, hafez

CURATED_LABEL = "منتخب پروژه"
WEB_LABEL = "دیوان حافظ"
CUSTOM_LABEL = "ساختهٔ مدیر"
EDITED_LABEL = "ویرایش‌شده در پنل"


def _normalize(card: Dict[str, Any], source: str) -> Dict[str, Any]:
    item: Dict[str, Any] = dict(card)
    item["source"] = source
    item["source_label"] = CURATED_LABEL if source == "curated" else WEB_LABEL
    item.setdefault("theme", source)
    item.setdefault("theme_label", CURATED_LABEL if source == "curated" else "")
    item.setdefault("title", f"غزل شمارهٔ {item.get('id', '')}")
    item.setdefault("keywords", [])
    item["verses"] = [str(line) for line in item.get("verses") or []]
    item["keywords"] = [str(word) for word in item["keywords"]]
    item["builtin"] = True
    item["editable"] = True
    if source == "curated":
        item["key"] = f"curated-{item.get('id')}"
    return item


FORTUNES: List[Dict[str, Any]] = [
    _normalize(card, "curated") for card in hafez.HAFEZ_CARDS
] + [
    _normalize(card, "web") for card in ghazals.GHAZALS
]

BY_KEY: Dict[str, Dict[str, Any]] = {str(card["key"]): card for card in FORTUNES}

TOTAL = len(FORTUNES)
WEB_TOTAL = sum(1 for card in FORTUNES if card["source"] == "web")
CURATED_TOTAL = TOTAL - WEB_TOTAL


# --------------------------------------------------------------------------- #
# استخر مؤثر: کارت‌های پایه + کارت‌های ساختهٔ مدیر + ویرایش‌ها - پنهان‌شده‌ها
# --------------------------------------------------------------------------- #

_cache: Optional[List[Dict[str, Any]]] = None


def _from_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """سطر جدول `fortune_cards` را به شکل کارت استخر درمی‌آورد."""
    builtin = bool(row.get("builtin"))
    key = str(row["key"])
    base = dict(BY_KEY.get(key) or {})
    card: Dict[str, Any] = {
        "key": key,
        "id": base.get("id", 0),
        "title": str(row.get("title") or base.get("title") or "فال تازه"),
        "verses": [str(line) for line in (row.get("verses") or base.get("verses") or [])],
        "keywords": [str(word) for word in (row.get("keywords") or base.get("keywords") or [])],
        "interpretation": str(row.get("interpretation") or base.get("interpretation") or ""),
        "guidance": str(row.get("guidance") or base.get("guidance") or ""),
        "theme": str(base.get("theme") or "custom"),
        "theme_label": str(row.get("theme_label") or base.get("theme_label") or ""),
        "source": "edited" if builtin else "custom",
        "source_label": EDITED_LABEL if builtin else CUSTOM_LABEL,
        "builtin": builtin,
        "editable": True,
    }
    return card


def effective() -> List[Dict[str, Any]]:
    """استخر نهایی برای ساخت فال: پایه + تغییرهای پنل.

    نتیجه کش می‌شود؛ پنل پس از هر تغییر `invalidate()` را صدا می‌زند.
    """
    global _cache
    if _cache is not None:
        return _cache

    cards: Dict[str, Dict[str, Any]] = {str(card["key"]): dict(card) for card in FORTUNES}
    for row in db.fortune_cards():
        key = str(row["key"])
        if row.get("hidden"):
            cards.pop(key, None)
            continue
        cards[key] = _from_row(row)
    _cache = list(cards.values())
    return _cache


def invalidate() -> None:
    """پس از هر تغییر در پنل ادمین صدا زده می‌شود تا استخر دوباره ساخته شود."""
    global _cache
    _cache = None


def pick(rng: random.Random) -> Dict[str, Any]:
    """یک فال تصادفی از استخر مؤثر (با مولد قابل تکرار)."""
    return rng.choice(effective())


def get(key: str) -> Dict[str, Any]:
    for card in effective():
        if str(card["key"]) == key:
            return card
    return effective()[0]


def theme_counts() -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for card in effective():
        label = str(card.get("theme_label") or card.get("theme") or "نامشخص")
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: -item[1]))


def source_info() -> Dict[str, Any]:
    """اطلاعات منبع، برای نمایش در پنل ادمین و صفحهٔ روش‌ها."""
    cards = effective()
    labels: Dict[str, int] = {}
    for card in cards:
        label = str(card.get("theme_label") or card.get("theme") or "نامشخص")
        labels[label] = labels.get(label, 0) + 1
    made = db.count_fortune_cards()
    return {
        "total": len(cards),
        "web": sum(1 for card in cards if card.get("source") == "web"),
        "curated": sum(1 for card in cards if card.get("source") == "curated"),
        "custom": sum(1 for card in cards if card.get("source") == "custom"),
        "edited": sum(1 for card in cards if card.get("source") == "edited"),
        "hidden": made["hidden"],
        "base_total": TOTAL,
        "source": ghazals.GHAZAL_SOURCE,
        "themes": dict(sorted(labels.items(), key=lambda item: -item[1])),
    }
