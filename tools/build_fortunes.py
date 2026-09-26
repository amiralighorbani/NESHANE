"""سازندهٔ استخر فال: ۱۰۰ غزل واقعی حافظ را از نت می‌گیرد و فایل محتوا می‌سازد.

اجرا (از ریشهٔ پروژه):

    python tools/build_fortunes.py

خروجی: `app/content/ghazals.py` — فهرست ۱۰۰ غزل با ابیات واقعی.

منبع ابیات: مخزن `arsamadineh/Persian-Quote-API` (مجوز MIT) که متن دیوان حافظ را
به‌صورت JSON دارد. متن دیوان حافظ مالکیت عمومی است (قرن هشتم).

نکته: **تعبیرها از نت گرفته نمی‌شوند.** این اسکریپت فقط ابیات را می‌گیرد و تعبیر و
راهنما را با موتور تم (`app/content/fortune_themes.py`) می‌سازد؛ پس هیچ متن
شخص ثالثی در پروژه کپی نمی‌شود.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# کنسول ویندوز ممکن است کدپیج فارسی نداشته باشد؛ خروجی را امن می‌کنیم.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover - فقط برای محیط‌های قدیمی
    pass

from app.content import fortune_themes, hafez as curated  # noqa: E402
from app.utils import to_fa  # noqa: E402

SOURCE_URL = "https://raw.githubusercontent.com/arsamadineh/Persian-Quote-API/main/lib/data/hafez.json"
CACHE_PATH = ROOT / "data" / "_hafez_verses.json"
OUTPUT_PATH = ROOT / "app" / "content" / "ghazals.py"

WANTED = 200  # تعداد فال‌های واقعی (دو برابر نسخهٔ اول)
LINES_PER_CARD = 2  # مطلع + مقطع

# حروف عربی که در فارسی به شکل دیگری نوشته می‌شوند
_LETTER_FIXES = str.maketrans({"ي": "ی", "ك": "ک", "ﻻ": "لا"})


def normalize(text: str) -> str:
    """برای مقایسهٔ متنی: حروف عربی، نیم‌فاصله و فاصله‌ها را یکدست می‌کند."""
    text = text.translate(_LETTER_FIXES)
    for char in "‌‏‎\u200c\u200f\u200e ءأإآ\u064b\u064c\u064d\u064e\u064f\u0650\u0651\u0652":
        text = text.replace(char, "")
    text = text.replace("هٔ", "ه").replace("ة", "ه")
    return text


def polish(text: str) -> str:
    """نمایش تمیز: حروف عربی اصلاح و فاصله‌های اضافه حذف می‌شود."""
    text = text.translate(_LETTER_FIXES)
    return " ".join(text.split())


def load_source() -> List[Dict[str, Any]]:
    if not CACHE_PATH.exists():
        print(f"↓ دریافت منبع از {SOURCE_URL}")
        try:
            with urllib.request.urlopen(SOURCE_URL, timeout=60) as response:
                raw = response.read()
        except urllib.error.URLError as error:  # pragma: no cover - وابسته به شبکه
            raise SystemExit(f"دریافت منبع ناموفق بود: {error}") from error
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_bytes(raw)
    data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("ساختار منبع غیرمنتظره است (لیست نبود).")
    return data


def curated_openings() -> set:
    """مطلعِ کارت‌های دست‌نویس، تا در انتخاب ۱۰۰ غزل تکرار نشوند."""
    openings = set()
    for card in curated.HAFEZ_CARDS:
        verses = card.get("verses") or []
        if verses:
            openings.add(normalize(str(verses[0]))[:24])
    return openings


def select(ghazals: List[Dict[str, Any]], count: int) -> List[Dict[str, Any]]:  # noqa: D401
    """انتخاب یکنواخت در سراسر دیوان، بدون تکرار و بدون همپوشانی با دست‌نویس‌ها.

    اول فاصله‌های مساوی در کل دیوان امتحان می‌شود و بعد، اگر تعدادی رد شدند،
    نوبت بقیهٔ غزل‌ها می‌رسد؛ پس انتخاب هم پراکنده است و هم به `count` می‌رسد.
    """
    taken = curated_openings()
    spread = [int(position * len(ghazals) / count) for position in range(count)]
    order: List[int] = []
    for index in spread + list(range(len(ghazals))):
        if index not in order and 0 <= index < len(ghazals):
            order.append(index)

    picked: List[Dict[str, Any]] = []
    for index in order:
        if len(picked) >= count:
            break
        beyts = [beyt for beyt in ghazals[index].get("verses") or [] if isinstance(beyt, list) and len(beyt) == 2]
        if len(beyts) < 2:
            continue
        if normalize(str(beyts[0][0]))[:24] in taken:
            continue
        picked.append(ghazals[index])
    if len(picked) < count:
        raise SystemExit(f"فقط {len(picked)} غزل مناسب پیدا شد؛ داده کافی نیست.")
    return picked


def build_card(ghazal: Dict[str, Any]) -> Dict[str, Any]:
    source_id = int(ghazal.get("id") or 0)
    beyts = [[polish(str(mesra)) for mesra in beyt] for beyt in ghazal["verses"]]

    # تم را از کل غزل تشخیص می‌دهیم، ولی فقط مطلع و مقطع را نمایش می‌دهیم.
    full_text = " ".join(mesra for beyt in beyts for mesra in beyt)
    themes = fortune_themes.detect(full_text)
    theme = themes[0] if themes else fortune_themes.GENERIC_THEME
    # اگر تم دومی هم پررنگ باشد، بدنهٔ تعبیر از آن گرفته می‌شود تا متن‌ها تکراری نشوند.
    secondary = themes[1] if len(themes) > 1 else None
    body_theme = secondary or theme
    if secondary is not None:
        primary_score = fortune_themes.score_of(theme, full_text)
        secondary_score = fortune_themes.score_of(secondary, full_text)
        if secondary_score < primary_score * 0.8:
            body_theme = theme

    chosen = [beyts[0]]
    if len(beyts) > 1:
        chosen.append(beyts[-1])
    chosen = chosen[:LINES_PER_CARD]

    seed = source_id
    opening = theme["openings"][seed % len(theme["openings"])]
    middle = body_theme["middles"][(seed // 3) % len(body_theme["middles"])]
    closing = fortune_themes.CLOSINGS[(seed // 7) % len(fortune_themes.CLOSINGS)]
    guidance = theme["guidances"][(seed // 11) % len(theme["guidances"])]

    return {
        "key": f"ghazal-{source_id}",
        "id": source_id,
        "title": f"غزل شمارهٔ {to_fa(source_id)}",
        "theme": theme["key"],
        "theme_label": theme["label"],
        "verses": [mesra for beyt in chosen for mesra in beyt],
        "keywords": fortune_themes.keywords_for(themes),
        "interpretation": f"{opening} {middle} {closing}",
        "guidance": guidance,
    }


def render_module(cards: List[Dict[str, Any]]) -> str:
    from collections import Counter

    themes = Counter(str(card["theme_label"]) for card in cards)
    summary = "، ".join(f"{label}: {count}" for label, count in themes.most_common())

    body = []
    for card in cards:
        lines = ", ".join(f'"{line}"' for line in card["verses"])
        keywords = ", ".join(f'"{word}"' for word in card["keywords"])
        body.append(
            "    {\n"
            f'        "key": "{card["key"]}",\n'
            f'        "id": {card["id"]},\n'
            f'        "title": "{card["title"]}",\n'
            f'        "theme": "{card["theme"]}",\n'
            f'        "theme_label": "{card["theme_label"]}",\n'
            f'        "verses": [{lines}],\n'
            f'        "keywords": [{keywords}],\n'
            f'        "interpretation": "{card["interpretation"]}",\n'
            f'        "guidance": "{card["guidance"]}",\n'
            "    },"
        )

    return (
        '"""غزل‌های واقعی حافظ برای استخر فال — فایل تولیدشده، دستی ویرایش نکن.\n\n'
        "برای ساخت دوباره: `python tools/build_fortunes.py`\n\n"
        "منبع ابیات: دیوان حافظ (متن مالکیت عمومی)، از دیتاست JSON با مجوز MIT\n"
        f"({SOURCE_URL})\n"
        "تعبیر، کلیدواژه و راهنما با موتور تم پروژه (`app/content/fortune_themes.py`)\n"
        "ساخته شده‌اند و نقل از هیچ منبعی نیستند.\n\n"
        f"تعداد کارت: {len(cards)}\n"
        f"پراکنش تم‌ها: {summary}\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any, Dict, List\n\n"
        "GHAZAL_SOURCE = {\n"
        '    "name": "Persian-Quote-API (دیوان حافظ)",\n'
        f'    "url": "{SOURCE_URL}",\n'
        '    "license": "MIT (متن شعر مالکیت عمومی)",\n'
        f'    "count": {len(cards)},\n'
        "}\n\n"
        "GHAZALS: List[Dict[str, Any]] = [\n" + "\n".join(body) + "\n]\n\n"
        "GHAZAL_BY_KEY: Dict[str, Dict[str, Any]] = {str(card[\"key\"]): card for card in GHAZALS}\n"
    )


def main() -> None:
    source = load_source()
    print(f"منبع بار شد: {len(source)} غزل")
    picks = select(source, WANTED)
    cards = [build_card(ghazal) for ghazal in picks]
    OUTPUT_PATH.write_text(render_module(cards), encoding="utf-8")
    print(f"OK - {len(cards)} غزل نوشته شد -> {OUTPUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
