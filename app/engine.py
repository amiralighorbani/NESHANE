"""موتور فال: از اطلاعات کاربر به یک خوانش کامل، تکرارپذیر و روزانه می‌رسد.

هر خوانش با هشِ (نام + تاریخ تولد + ساعت تولد + شهر + موضوع + نیت + روش + تاریخ امروز + نمک)
ساخته می‌شود؛ یعنی همان اطلاعات و همان روز = همان فال، و «فال تازه» با نمکِ نو، خوانشی نو می‌دهد.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .content import astrology, chinese, dice, fortunes, lexicon, methods, numerology, runes
from .content import tarot as tarot_deck
from .forms import GENDERS
from .models import (
    CompatInfo,
    DayPhase,
    DayPlanet,
    EnergyReading,
    FortuneRequest,
    LuckyItem,
    MoodInfo,
    Reading,
    ReadingBlock,
    SignInfo,
)
from .utils import (
    WEEKDAY_PLANET,
    hour_slot_label,
    hour_window,
    jalali_label,
    jalali_today,
    today_label,
    to_fa,
    weekday_fa,
    zodiac_key,
)

PLANET_ICONS: Dict[str, str] = {
    "خورشید": "fa-solid fa-sun",
    "ماه": "fa-solid fa-moon",
    "بهرام (مریخ)": "fa-solid fa-fire",
    "تیر (عطارد)": "fa-solid fa-comment-dots",
    "برجیس (مشتری)": "fa-solid fa-crown",
    "ناهید (زهره)": "fa-solid fa-heart",
    "کیوان (زحل)": "fa-solid fa-ring",
    "پلوتو": "fa-solid fa-skull",
    "اورانوس": "fa-solid fa-wind",
    "نپتون": "fa-solid fa-water",
}

LUCKY_ICONS: Dict[str, str] = {
    "number": "fa-solid fa-hashtag",
    "color": "fa-solid fa-palette",
    "stone": "fa-solid fa-gem",
    "day": "fa-solid fa-calendar-day",
    "hour": "fa-solid fa-clock",
    "place": "fa-solid fa-location-dot",
    "flower": "fa-solid fa-seedling",
    "scent": "fa-solid fa-spray-can-sparkles",
}

ENERGY_WEIGHTS: Dict[str, float] = {
    "love": 0.22,
    "career": 0.24,
    "wealth": 0.16,
    "health": 0.20,
    "calm": 0.18,
}


# --------------------------------------------------------------------------- #
# کمکی‌ها / helpers
# --------------------------------------------------------------------------- #


def _sign_info(key: str) -> SignInfo:
    sign = astrology.get_sign(key)
    element = str(sign["element"])
    return SignInfo(
        key=key,
        name=str(sign["name"]),
        symbol=str(sign["symbol"]),
        range=str(sign["range"]),
        element=element,
        element_glyph=str(astrology.ELEMENTS[element]["glyph"]),
        planet=str(sign["planet"]),
        mode=str(sign["mode"]),
        traits=list(sign["traits"]),  # type: ignore[arg-type]
        strengths=list(sign["strengths"]),  # type: ignore[arg-type]
        shadow=str(sign["shadow"]),
        motto=str(sign["motto"]),
        love_style=str(sign["love_style"]),
        work_style=str(sign["work_style"]),
        care=str(sign["care"]),
        lucky_day=str(sign["lucky"]["day"]),  # type: ignore[index]
    )


def _band_for(value: int) -> Dict[str, Any]:
    for band in lexicon.ENERGY_BANDS:
        if value <= int(band["limit"]):
            return band
    return lexicon.ENERGY_BANDS[-1]


def _overall_label(value: int) -> str:
    if value < 45:
        return lexicon.OVERALL_LABELS["low"]
    if value < 72:
        return lexicon.OVERALL_LABELS["mid"]
    return lexicon.OVERALL_LABELS["high"]


def _energy(rng: random.Random, area: Dict[str, Any], boost: Dict[str, int]) -> EnergyReading:
    base = 44 + rng.randint(0, 46)
    value = max(9, min(98, base + int(boost.get(str(area["key"]), 0))))
    band = _band_for(value)
    return EnergyReading(
        key=str(area["key"]),
        label=str(area["label"]),
        icon=str(area["icon"]),
        value=value,
        band=str(band["label"]),
        note=rng.choice(list(area["notes"])),  # type: ignore[arg-type]
    )


def _power_note(energies: Sequence[EnergyReading], name: str) -> str:
    strongest = max(energies, key=lambda item: item.value)
    weakest = min(energies, key=lambda item: item.value)
    return (
        f"قوی‌ترین حوزهٔ امروز {name} «{strongest.label}» است ({strongest.band}) و "
        f"«{weakest.label}» بیش از همه به توجه نیاز دارد؛ انرژی‌ات را همان‌جا که می‌درخشد خرج کن."
    )


def _lucky_items(rng: random.Random, sign: SignInfo) -> Tuple[List[LuckyItem], str]:
    color = rng.choice(lexicon.LUCKY_COLORS)
    golden_hour = rng.choice(lexicon.HOUR_WINDOWS)
    items = [
        LuckyItem(label="عدد شانس", value=rng.choice(lexicon.LUCKY_NUMBERS), icon=LUCKY_ICONS["number"], hint="برای تصمیم‌های کوچک امروز"),
        LuckyItem(label="رنگ", value=color["label"], icon=LUCKY_ICONS["color"], hint="در لباس یا وسایلت باشد"),
        LuckyItem(label="سنگ", value=rng.choice(lexicon.LUCKY_STONES), icon=LUCKY_ICONS["stone"], hint="همراه‌داشتنش امروز خوب است"),
        LuckyItem(label="روز هفته", value=sign.lucky_day, icon=LUCKY_ICONS["day"], hint="روز پیگیری کارهای مهم"),
        LuckyItem(label="ساعت طلایی", value=hour_window(golden_hour), icon=LUCKY_ICONS["hour"], hint="بهترین بازه برای کار کلیدی"),
        LuckyItem(label="مکان", value=rng.choice(lexicon.LUCKY_PLACES), icon=LUCKY_ICONS["place"], hint="حال خوب آنجا سراغت می‌آید"),
        LuckyItem(label="گل", value=rng.choice(lexicon.LUCKY_FLOWERS), icon=LUCKY_ICONS["flower"], hint="یک شاخه برای خانه"),
        LuckyItem(label="رایحه", value=rng.choice(lexicon.LUCKY_SCENTS), icon=LUCKY_ICONS["scent"], hint="فضای امروزت را عوض می‌کند"),
    ]
    return items, color["hex"]


def _compat(rng: random.Random, sign: SignInfo) -> CompatInfo:
    candidates = astrology.compatible_signs(sign.key) or astrology.SIGN_ORDER[:3]
    partner_key = rng.choice(candidates)
    partner = astrology.get_sign(partner_key)
    tier = astrology.ELEMENT_AFFINITY.get((sign.element, str(partner["element"])), 1)
    score = (74 if tier == 1 else 66) + rng.randint(0, 22)
    return CompatInfo(
        sign_name=str(partner["name"]),
        symbol=str(partner["symbol"]),
        affinity=astrology.AFFINITY_LABEL[tier],
        line=astrology.AFFINITY_LINE[tier],
        score=min(99, score),
    )


def _day_planet(sign: SignInfo) -> DayPlanet:
    weekday = weekday_fa()
    meta = WEEKDAY_PLANET.get(weekday, WEEKDAY_PLANET["شنبه"])
    element = str(meta["element"])
    planet = str(meta["planet"])
    tier = astrology.ELEMENT_AFFINITY.get((sign.element, element), 2)
    if sign.planet.split(" ")[0] == planet.split(" ")[0]:
        tier = 1
    return DayPlanet(
        weekday=weekday,
        planet=planet,
        element=element,
        icon=PLANET_ICONS.get(planet, "fa-solid fa-star"),
        note=str(meta["note"]),
        affinity=astrology.AFFINITY_LABEL[tier],
        affinity_line=f"سیّارهٔ امروز با سیّارهٔ تولدت «{astrology.AFFINITY_LABEL[tier]}» است؛ {astrology.AFFINITY_LINE[tier]}",
    )


def _curve(rng: random.Random, peak_hour: int) -> Tuple[List[int], List[str]]:
    hours = [6, 8, 10, 12, 14, 16, 18, 20]
    values: List[int] = []
    for hour in hours:
        distance = abs(hour - peak_hour)
        base = 78 - distance * 6 + rng.randint(-9, 9)
        values.append(max(14, min(99, base)))
    return values, [hour_slot_label(hour) for hour in hours]


def _phases(rng: random.Random, curve: Sequence[int]) -> List[DayPhase]:
    points = [curve[index] for index in (0, 2, 4, 6)] if len(curve) >= 7 else [60, 70, 65, 55]
    ordered = sorted(range(len(points)), key=lambda index: -points[index])
    phases: List[DayPhase] = []
    for index, part in enumerate(lexicon.DAY_PARTS):
        note = str(part["note"])
        if index == ordered[0]:
            note = "اوج انرژی امروز همین‌جاست؛ مهم‌ترین کارت را اینجا بگذار. " + note
        phases.append(
            DayPhase(
                label=str(part["label"]),
                icon=str(part["icon"]),
                note=note,
                energy=int(points[index]),
            )
        )
    return phases


# --------------------------------------------------------------------------- #
# بلوک‌های هر روش فال / per-method blocks
# --------------------------------------------------------------------------- #


def _blocks_hafez(rng: random.Random) -> List[ReadingBlock]:
    """فال حافظ از استخر کامل (کارت‌های دست‌نویس + غزل‌های واقعی)."""
    card = fortunes.pick(rng)
    meta = {"کلیدواژه": "، ".join(str(item) for item in card["keywords"])}
    if card.get("theme_label"):
        meta["مضمون"] = str(card["theme_label"])
    meta["منبع ابیات"] = str(card.get("source_label") or "دیوان حافظ")
    return [
        ReadingBlock(
            key="hafez",
            title="غزل حافظ",
            icon="fa-solid fa-book-open",
            accent="#7c5cd6",
            lead=str(card.get("title") or f"غزل شمارهٔ {to_fa(card['id'])}"),
            lines=list(card["verses"]),
            body=str(card["interpretation"]),
            meta=meta,
            note=str(card["guidance"]),
            visual="verses",
            visual_label="ابلت درآمده",
            symbols=[
                {
                    "name": str(card.get("title") or f"غزل شمارهٔ {to_fa(card['id'])}"),
                    "glyph": "﷽",
                    "icon": "fa-solid fa-book-open",
                    "position": "غزل حافظ",
                    "position_note": "بیت اول، همان بیتی است که قفل را باز می‌کند",
                    "orientation": "upright",
                    "orientation_label": "رو‌به‌رو",
                    "keywords": "، ".join(str(item) for item in card["keywords"]),
                }
            ],
        )
    ]


# سه جایگاهِ خوانش تاروت: گذشته/اکنون، رهاکردنی، پیشِ‌رو.
TAROT_SPREAD: List[Tuple[str, str]] = [
    ("وضعیت کنونی", "نقطه‌ای که همین حالا در آن ایستاده‌ای"),
    ("چیزی که باید رها کنی", "باری که نگه‌داشتنش راه را تنگ کرده است"),
    ("مسیری که پیش روست", "جهتی که انرژی‌ات تو را می‌برد"),
]

# پیکانِ تاس‌ها: کدام خانه‌های ۳×۳ نقطه دارند (۱ تا ۶).
DICE_FACES: Dict[int, Tuple[int, ...]] = {
    1: (4,),
    2: (0, 8),
    3: (0, 4, 8),
    4: (0, 2, 6, 8),
    5: (0, 2, 4, 6, 8),
    6: (0, 2, 3, 5, 6, 8),
}

DICE_SLOTS: List[Tuple[str, str]] = [
    ("تاسِ یکم", "آن‌چه همین حالا داری"),
    ("تاسِ دوم", "آن‌چه در راه است"),
    ("تاسِ سوم", "سهمِ تو در این میان"),
]

RUNE_SLOTS: List[Tuple[str, str]] = [
    ("سنگ درآمده", "تنها سنگی که از کیسه بیرون آمد"),
]


def _blocks_tarot(rng: random.Random) -> List[ReadingBlock]:
    """سه کارتِ واقعی و متفاوت؛ هر کارت جایگاه و جهت خودش را دارد."""
    cards = rng.sample(tarot_deck.DECK, 3)
    theme = rng.choice(tarot_deck.CARD_BACK_THEMES)
    symbols: List[Dict[str, str]] = []
    lines: List[str] = []
    meanings: List[str] = []
    advices: List[str] = []
    for (position, position_note), card in zip(TAROT_SPREAD, cards):
        is_reversed = rng.random() < 0.3
        meaning = str(card["reversed"] if is_reversed else card["upright"])
        meanings.append(meaning)
        advices.append(str(card["advice"]))
        keywords = "، ".join(str(item) for item in card["keywords"])
        symbols.append(
            {
                "name": str(card["name"]),
                "numeral": str(card["numeral"]),
                "icon": str(card["icon"]),
                "position": position,
                "position_note": position_note,
                "orientation": "reversed" if is_reversed else "upright",
                "orientation_label": "وارونه" if is_reversed else "رو‌به‌رو",
                "keywords": keywords,
            }
        )
        lines.append(f"{position} — «{card['name']}» ({'وارونه' if is_reversed else 'رو‌به‌رو'}): {meaning}")

    names = " ← ".join(f"{card['name']}" for card in cards)
    body = (
        f"سه کارت روی میز است: {names}. "
        f"داستان این سه کارت با هم خوانده می‌شود، نه یکی‌یکی؛ {meanings[0]} و در ادامه، "
        f"مسیر بعدی را کارت سوم باز می‌کند."
    )
    return [
        ReadingBlock(
            key="tarot",
            title="سه کارت تاروت",
            icon="fa-solid fa-dice-d6",
            accent="#c0577f",
            lead=f"{names}",
            body=body,
            lines=lines,
            meta={
                "کارت‌های درآمده": names,
                "ترتیب خوانش": " ← ".join(position for position, _ in TAROT_SPREAD),
                "سفر انرژی": f"{theme['from']} ← {theme['to']}",
            },
            note=advices[0],
            visual="cards",
            visual_label="سه کارت روی میز",
            symbols=symbols,
        )
    ]


def _sign_field(key: str, field: str) -> str:
    """فیلد تازهٔ هر برج (پول، رفاقت، تندرستی، آیین) با جانشین امن."""
    return str(astrology.get_sign(key).get(field) or "—")


def _blocks_zodiac(sign: SignInfo) -> List[ReadingBlock]:
    return [
        ReadingBlock(
            key="sign",
            title=f"برج {sign.name}",
            icon=str(astrology.ELEMENTS[sign.element]["glyph"]),
            accent="#d99a1f",
            lead=f"{sign.symbol} {sign.range}",
            lines=list(sign.traits),
            body=sign.motto,
            meta={
                "عنصر": sign.element,
                "سیّاره": sign.planet,
                "کیفیت": sign.mode,
            },
            note=sign.shadow,
            visual="sign",
            visual_label="نماد برج تو",
            symbols=[
                {
                    "name": sign.name,
                    "glyph": sign.symbol,
                    "icon": str(astrology.ELEMENTS[sign.element]["glyph"]),
                    "position": "برج",
                    "position_note": sign.range,
                    "orientation": "upright",
                    "orientation_label": f"عنصر {sign.element}",
                    "keywords": "، ".join(sign.traits),
                }
            ],
        ),
        ReadingBlock(
            key="sign-life",
            title="عشق و کار",
            icon="fa-solid fa-compass",
            accent="#d99a1f",
            lines=[f"در عشق: {sign.love_style}", f"در کار: {sign.work_style}", f"توانمندی‌ها: {'، '.join(sign.strengths)}"],
            note=sign.care,
        ),
        ReadingBlock(
            key="sign-daily",
            title="پول، رفاقت و تن",
            icon="fa-solid fa-hand-holding-heart",
            accent="#d99a1f",
            lines=[
                f"پول: {_sign_field(sign.key, 'money')}",
                f"رفاقت: {_sign_field(sign.key, 'friendship')}",
                f"تن و تندرستی: {_sign_field(sign.key, 'health')}",
            ],
            meta={"عنصر": sign.element, "کیفیت": str(astrology.ELEMENTS[sign.element]['quality'])},
            note=f"آیین امروز: {_sign_field(sign.key, 'ritual')}",
        ),
    ]


def _blocks_numerology(gregorian: Tuple[int, int, int], current: date) -> List[ReadingBlock]:
    gy, gm, gd = gregorian
    path = numerology.life_path(gy, gm, gd)
    data = numerology.get_path(path)
    personal = numerology.personal_year(gy, gm, gd, current.year)
    personal_line = numerology.PERSONAL_YEAR_LINES.get(personal)
    personal_meta = data if personal == path else numerology.get_path(personal)
    return [
        ReadingBlock(
            key="life-path",
            title="عدد مسیر زندگی",
            icon="fa-solid fa-hashtag",
            accent="#2f8fa8",
            lead=f"عدد {to_fa(path)} • {data['title']}",
            body=str(data["body"]),
            lines=[
                f"توانمندی: {data['strength']}",
                f"سایه: {data['shadow']}",
                f"کار: {data.get('career', '')}",
                f"رابطه: {data.get('love', '')}",
                f"تندرستی: {data.get('health', '')}",
            ],
            meta={"کلیدواژه": "، ".join(str(item) for item in data["keywords"])},  # type: ignore[arg-type]
            note=f"{data['advice']} آیین روزانه: {data.get('ritual', '')}".strip(),
            visual="glyph",
            visual_label="عدد مسیر زندگی",
            symbols=[
                {
                    "name": str(data["title"]),
                    "glyph": to_fa(path),
                    "icon": "fa-solid fa-hashtag",
                    "position": "مسیر زندگی",
                    "position_note": "از مجموع ارقام تاریخ تولد",
                    "orientation": "upright",
                    "orientation_label": f"عدد {to_fa(path)}",
                    "keywords": "، ".join(str(item) for item in data["keywords"]),
                }
            ],
        ),
        ReadingBlock(
            key="personal-year",
            title=f"سال شخصی {to_fa(current.year)}",
            icon="fa-solid fa-arrows-spin",
            accent="#2f8fa8",
            lead=f"عدد {to_fa(personal)} • {personal_meta['title']}",
            body=personal_line or str(personal_meta["body"]),
            meta={"کلیدواژه": "، ".join(str(item) for item in personal_meta["keywords"])},  # type: ignore[arg-type]
            note="این چرخهٔ نُه‌ساله است؛ سال آینده جای دیگری ایستاده‌ای.",
            visual="glyph",
            visual_label="سال شخصی",
            symbols=[
                {
                    "name": str(personal_meta["title"]),
                    "glyph": to_fa(personal),
                    "icon": "fa-solid fa-arrows-spin",
                    "position": f"سال {to_fa(current.year)}",
                    "position_note": "چرخهٔ نُه‌سالهٔ شخصی",
                    "orientation": "upright",
                    "orientation_label": f"عدد {to_fa(personal)}",
                    "keywords": "، ".join(str(item) for item in personal_meta["keywords"]),
                }
            ],
        ),
    ]


def _blocks_runes(rng: random.Random) -> List[ReadingBlock]:
    rune = rng.choice(runes.RUNES)
    is_reversed = rng.random() < 0.3
    position, position_note = RUNE_SLOTS[0]
    return [
        ReadingBlock(
            key="rune",
            title="سنگ رون",
            icon="fa-solid fa-gem",
            accent="#3d7ad6",
            lead=f"{rune['glyph']}  {rune['name']}",
            body=str(rune["reversed"] if is_reversed else rune["upright"]),
            meta={
                "جهت": "وارونه" if is_reversed else "روبه‌رو",
                "کلیدواژه": "، ".join(str(item) for item in rune["keywords"]),  # type: ignore[arg-type]
            },
            note=str(rune["advice"]),
            visual="rune",
            visual_label="سنگِ درآمده",
            symbols=[
                {
                    "name": str(rune["name"]),
                    "glyph": str(rune["glyph"]),
                    "icon": "fa-solid fa-gem",
                    "position": position,
                    "position_note": position_note,
                    "orientation": "reversed" if is_reversed else "upright",
                    "orientation_label": "وارونه" if is_reversed else "رو‌به‌رو",
                    "keywords": "، ".join(str(item) for item in rune["keywords"]),
                }
            ],
        )
    ]


def _blocks_chinese(gy: int, current_year: int) -> List[ReadingBlock]:
    animal = chinese.animal_for_year(gy)
    element = chinese.element_for_year(gy)
    this_year = chinese.animal_for_year(current_year)
    this_element = chinese.element_for_year(current_year)
    return [
        ReadingBlock(
            key="animal",
            title="حیوان سال تولد",
            icon=str(animal["icon"]),
            accent="#c2483f",
            lead=str(animal["name"]),
            body=str(animal["body"]),
            lines=[f"هدیه: {animal['gift']}", f"سایه: {animal['shadow']}"],
            meta={
                "عنصر سال": f"{element['name']} — {element['note']}",
                "قطب سال": f"{animal.get('polarity', '')} — {animal.get('polarity_note', '')}".strip(" —"),
                "ویژگی‌ها": "، ".join(str(item) for item in animal["traits"]),  # type: ignore[arg-type]
            },
            note=str(animal["advice"]),
            visual="animal",
            visual_label="حیوان سال تولد",
            symbols=[
                {
                    "name": str(animal["name"]),
                    "glyph": str(animal["icon"]),
                    "icon": str(animal["icon"]),
                    "position": "سال تولد",
                    "position_note": f"عنصر {element['name']}",
                    "orientation": "upright",
                    "orientation_label": str(animal.get("polarity", "")),
                    "keywords": "، ".join(str(item) for item in animal["traits"]),
                }
            ],
        ),
        ReadingBlock(
            key="animal-year",
            title=f"طالع سال {to_fa(current_year)}",
            icon=str(this_year["icon"]),
            accent="#c2483f",
            lead=str(this_year["name"]),
            body=str(this_year["body"]),
            lines=[f"قطب سال: {this_year.get('polarity', '')}", f"عنصر سال: {this_element['name']}"],
            meta={
                "مجموع سال": f"{this_element['name']} — {this_element['note']}",
                "هم‌نشینی با طالع تولد": (
                    "هم‌جهت" if str(this_year["key"]) == str(animal["key"]) else "مکمل"
                ),
            },
            note=str(this_year["advice"]),
        ),
    ]


def _blocks_dice(rng: random.Random) -> List[ReadingBlock]:
    """سه تاسِ واقعی؛ هر تاس یک جایگاه و عدد خودش را دارد و مجموع، خانه را می‌سازد."""
    values = [rng.randint(1, 6) for _ in range(3)]
    total = sum(values)
    house = dice.house_for_total(total)
    symbols: List[Dict[str, str]] = []
    lines: List[str] = []
    for (label, caption), value in zip(DICE_SLOTS, values):
        symbols.append(
            {
                "name": to_fa(value),
                "label": label,
                "caption": caption,
                "pip": str(value),
                "dots": ",".join(str(index) for index in DICE_FACES[value]),
            }
        )
        lines.append(f"{label} ({to_fa(value)}): {caption}")
    return [
        ReadingBlock(
            key="dice",
            title=str(house["title"]),
            icon=str(house["icon"]),
            accent="#5c8f4a",
            lead=f"مجموع تاس‌ها: {to_fa(total)}  ({to_fa(values[0])} + {to_fa(values[1])} + {to_fa(values[2])})",
            body=str(house["body"]),
            lines=lines,
            meta={
                "کلیدواژه": "، ".join(str(item) for item in house["keywords"]),  # type: ignore[arg-type]
                "انرژی خانه": f"{to_fa(int(house['energy']))}٪",
            },
            note=str(house["advice"]),
            visual="dice",
            visual_label="سه تاسِ افتاده",
            symbols=symbols,
        )
    ]


# --------------------------------------------------------------------------- #
# ساخت خوانش / build the reading
# --------------------------------------------------------------------------- #


def build_reading(request: FortuneRequest, salt: str = "", today: Optional[date] = None) -> Reading:
    current = today or date.today()
    jy_today, jm_today, jd_today = jalali_today(current)
    gy, gm, gd = _birth_gregorian(request)
    sign = _sign_info(zodiac_key(gm, gd))
    topic = lexicon.TOPICS.get(request.topic) or lexicon.TOPICS["general"]
    method = methods.get_method(request.method)

    material = "|".join(
        [
            request.name.strip(),
            f"{request.jy}-{request.jm}-{request.jd}",
            request.birth_time,
            request.city,
            request.topic,
            request.intent.strip(),
            request.method,
            f"{jy_today}-{jm_today}-{jd_today}",
            salt,
        ]
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    rng = random.Random(int(digest[:16], 16))

    energies = [_energy(rng, area, topic["boost"]) for area in lexicon.ENERGY_AREAS]  # type: ignore[arg-type]
    overall = int(sum(item.value * ENERGY_WEIGHTS[item.key] for item in energies))
    mood = MoodInfo(**rng.choice(lexicon.MOODS))
    lucky, color_hex = _lucky_items(rng, sign)
    compat = _compat(rng, sign)
    day_planet = _day_planet(sign)

    peak_hour = rng.choice(lexicon.HOUR_WINDOWS)
    curve, curve_labels = _curve(rng, peak_hour)
    phases = _phases(rng, curve)
    peak_label = curve_labels[curve.index(max(curve))]

    key = request.method
    if key == "hafez":
        blocks = _blocks_hafez(rng)
    elif key == "tarot":
        blocks = _blocks_tarot(rng)
    elif key == "zodiac":
        blocks = _blocks_zodiac(sign)
    elif key == "numerology":
        blocks = _blocks_numerology((gy, gm, gd), current)
    elif key == "runes":
        blocks = _blocks_runes(rng)
    elif key == "chinese":
        blocks = _blocks_chinese(gy, current.year)
    elif key == "dice":
        blocks = _blocks_dice(rng)
    else:
        blocks = _blocks_hafez(rng)

    focus_line = str(topic["focus"])
    element_note = str(astrology.ELEMENTS[sign.element]["note"])
    power_note = _power_note(energies, request.name)
    headline = rng.choice(lexicon.HEADLINES).format(
        name=request.name,
        sign=sign.name,
        element=sign.element,
        mood_line=mood.line,
        topic_focus=focus_line,
    )
    summary = rng.choice(lexicon.SUMMARIES).format(
        name=request.name,
        sign=sign.name,
        focus_line=focus_line,
        planet=sign.planet,
        element_note=element_note,
        power_line=power_note,
    )

    token = digest[:14]
    reading = Reading(
        token=token,
        created_label=today_label(current),
        name=request.name,
        gender={item["value"]: item["label"] for item in GENDERS}.get(request.gender, ""),
        city=request.city,
        birth_label=request.birth_label,
        birth_time_label=request.birth_time,
        sign=sign,
        topic_key=request.topic,
        topic_label=str(topic["label"]),
        topic_icon=str(topic["icon"]),
        intent=request.intent,
        method_key=request.method,
        method_label=str(method["label"]),
        method_icon=str(method["icon"]),
        method_accent=str(method["accent"]),
        headline=headline,
        summary=summary,
        mood=mood,
        energies=energies,
        overall=overall,
        overall_label=_overall_label(overall),
        overall_note=str(_band_for(overall)["note"]),
        element_note=element_note,
        day_planet=day_planet,
        blocks=blocks,
        lucky=lucky,
        lucky_color_hex=color_hex,
        dos=_pick_pool(rng, topic, "dos"),
        donts=_pick_pool(rng, topic, "donts"),
        compat=compat,
        affirmation=rng.choice(lexicon.AFFIRMATIONS),
        phases=phases,
        curve=curve,
        curve_labels=curve_labels,
        peak_label=peak_label,
        power_note=power_note,
        seed=digest[:8],
    )
    reading.summary_text = _summary_text(reading)
    return reading


def _birth_gregorian(request: FortuneRequest) -> Tuple[int, int, int]:
    from .utils import jalali_to_gregorian

    return jalali_to_gregorian(request.jy, request.jm, request.jd)


def _pick_pool(rng: random.Random, topic: Dict[str, Any], field: str) -> List[str]:
    topic_items = [str(item) for item in (topic.get(field) or [])]
    pool_field = "DOS_POOL" if field == "dos" else "DONTS_POOL"
    pool = [item for item in getattr(lexicon, pool_field) if item not in topic_items]
    picked = topic_items[:2] + rng.sample(pool, k=min(2, len(pool)))
    rng.shuffle(picked)
    return picked[:4]


def _summary_text(reading: Reading) -> str:
    lines: List[str] = [
        f"فال {reading.name} — {reading.method_label} — {reading.created_label}",
        reading.headline,
        "",
        f"برج: {reading.sign.symbol} {reading.sign.name} | عنصر: {reading.sign.element} | سیّاره: {reading.sign.planet}",
        f"حال‌و‌هوا: {reading.mood.label}",
        f"انرژی کل روز: {to_fa(reading.overall)}٪ — {reading.overall_label}",
    ]
    if reading.intent:
        lines.append(f"نیت: {reading.intent}")
    for block in reading.blocks:
        lines.append("")
        lines.append(f"— {block.title} —")
        if block.lead:
            lines.append(block.lead)
        lines.extend(block.lines)
        if block.body:
            lines.append(block.body)
        for meta_key, meta_value in block.meta.items():
            lines.append(f"{meta_key}: {meta_value}")
        if block.note:
            lines.append(f"راهنما: {block.note}")
    lines.append("")
    lines.append("— انرژی‌ها —")
    for item in reading.energies:
        lines.append(f"{item.label}: {to_fa(item.value)}٪ ({item.band}) — {item.note}")
    lines.append("")
    lines.append("— شانس امروز —")
    for item in reading.lucky:
        lines.append(f"{item.label}: {item.value}")
    lines.append("")
    lines.append("— امروز انجام بده —")
    lines.extend(f"• {item}" for item in reading.dos)
    lines.append("— امروز انجام نده —")
    lines.extend(f"• {item}" for item in reading.donts)
    lines.append("")
    lines.append(f"هم‌نشینی خوب امروز: {reading.compat.symbol} {reading.compat.sign_name}")
    lines.append(f"جملهٔ امروز: «{reading.affirmation}»")
    lines.append("")
    lines.append("ساخته‌شده با نشانه (برای سرگرمی)")
    return "\n".join(lines)


def reading_payload(reading: Reading, request: FortuneRequest, salt: str) -> Dict[str, Any]:
    """بستهٔ ذخیره‌سازی در دیتابیس."""
    return {
        "reading": reading.model_dump(),
        "request": request.model_dump(),
        "salt": salt,
        "stamp": reading.created_label,
    }


def reading_from_payload(payload: Dict[str, Any]) -> Reading:
    return Reading.model_validate(payload["reading"])


# --------------------------------------------------------------------------- #
# پلِ مدل زبانی / what we hand to the LLM
# --------------------------------------------------------------------------- #


def symbol_digest(reading: Reading) -> str:
    """توصیف فشردهٔ نمادهای درآمده، تا مدل بداند دقیقاً چه چیزی کشیده شده است."""
    lines: List[str] = []
    for block in reading.blocks:
        if not block.symbols:
            lines.append(f"- {block.title}: {block.lead or block.body}")
            continue
        lines.append(f"- {block.title} ({block.visual_label or block.visual}):")
        for symbol in block.symbols:
            pieces = [
                str(symbol.get("position") or ""),
                str(symbol.get("name") or ""),
                str(symbol.get("orientation_label") or ""),
            ]
            head = " | ".join(piece for piece in pieces if piece)
            keywords = str(symbol.get("keywords") or "")
            caption = str(symbol.get("caption") or symbol.get("position_note") or "")
            tail = " — کلیدواژه: " + keywords if keywords else ""
            if caption:
                tail += " — " + caption
            lines.append(f"    * {head}{tail}")
    return "\n".join(lines)


def base_digest(reading: Reading) -> str:
    """متن پایهٔ فال که مدل آن را شخصی‌تر می‌کند."""
    parts: List[str] = [f"تیتر پایه: {reading.headline}", f"خلاصهٔ پایه: {reading.summary}"]
    for block in reading.blocks:
        chunk = [f"{block.title}:"]
        if block.lead:
            chunk.append(block.lead)
        if block.body:
            chunk.append(block.body)
        chunk.extend(block.lines)
        if block.note:
            chunk.append(f"راهنما: {block.note}")
        parts.append(" ".join(chunk))
    return "\n".join(parts)[:4000]


def apply_ai(reading: Reading, ai: Optional[Dict[str, Any]]) -> Reading:
    """خوانشِ نوشتهٔ مدل را روی فال می‌نشاند (اگر جواب داده باشد)."""
    if not ai:
        return reading
    reading.ai_note = str(ai.get("personal") or "")
    reading.ai_guidance = [str(item) for item in (ai.get("guidance") or [])]
    reading.ai_invitation = str(ai.get("invitation") or "")
    headline = str(ai.get("headline") or "").strip()
    reading.ai_meta = {
        "headline": headline or reading.headline,
        "provider": str(ai.get("provider") or ""),
        "provider_label": str(ai.get("provider_label") or ""),
        "model": str(ai.get("model") or ""),
        "latency_ms": int(ai.get("latency_ms") or 0),
        "tokens": int(ai.get("tokens") or 0),
        "used_fallback": bool(ai.get("used_fallback")),
    }
    if headline:
        reading.headline = headline
    reading.summary_text = _summary_text(reading)
    return reading
