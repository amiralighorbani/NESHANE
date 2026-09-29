"""موتور بازی «ذهن‌خوان»: از چند جواب بله/نه، شخصیتِ توی ذهن کاربر را پیدا می‌کند.

الگوریتم، ساده ولی درست است (همان ایدهٔ آکیناتور):

1. هر شخصیت یک **امتیاز** دارد که از ۱ شروع می‌شود.
2. با هر جواب، امتیاز شخصیت‌هایی که با آن جواب می‌خوانند بزرگ می‌شود و بقیه کوچک.
3. برای «سؤال بعدی» همهٔ سؤال‌های نپرسیده را می‌سنجیم و آن‌که **بیشترین اطلاعات**
   را می‌دهد (بیشترین آنتروپی) انتخاب می‌کنیم؛ نه ترتیب ثابت و نه درخت دستی.
4. وقتی یک نفر با فاصلهٔ واضح جلو افتاد، حدس می‌زنیم؛ اگر کاربر بگوید «نه»، همان
   شخصیت کنار گذاشته می‌شود و بازی با نفر بعدی ادامه پیدا می‌کند.

هر تابع **خالص** است: فقط `state` (دیکشنری قابل تبدیل به JSON) می‌گیرد و برمی‌گرداند؛
پس ذخیره/بازیابی‌اش در دیتابیس یک خط است و آزمون‌کردنش هم ساده.

«یادگیری»: شخصیت‌هایی که کاربر خودش در پایان بازی اسم‌شان را می‌نویسد، با وزن کمتر
به استخر اضافه می‌شوند (`LEARNED_WEIGHT`) تا دیتاست با گذر زمان بزرگ‌تر شود، ولی
دادهٔ دستی‌شده جایگاهش را از دست ندهد.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .content import mind as data

# سقف سؤال‌ها: بیش از این، بازی خسته‌کننده می‌شود. پیش‌فرض آکیناتور هم حدود بیست است.
MAX_QUESTIONS = 22
# کمترین آنتروپیِ قابل‌قبول برای پرسیدن (بیت). زیر این مقدار، جوابش چیز زیادی
# روشن نمی‌کند و بهتر است برویم سر حدس.
MIN_ENTROPY = 0.10
# اگر یک نفر این‌قدر از کل وزن را داشته باشد، با اطمینان حدس می‌زنیم.
CONFIDENT = 0.85
# زیر این حد، حدس را «صندلی داغ» نمی‌کنیم: فهرست چند گزینهٔ صدر را هم نشان می‌دهیم.
LOW_CONFIDENCE = 0.35
# یا اگر گزینهٔ صدر این‌قدر از نفر دوم جلو باشد، همان حدس را با اطمینان نشان می‌دهیم.
CLEAR_AHEAD = 3.0
# «گزینهٔ زنده» = شخصیتی که امتیازش نزدیک صدر است (نه فقط بیشتر از صفر؛ چون
# ضرب‌های کوچک هیچ‌وقت صفر نمی‌شوند و شمارشِ «بیشتر از صفر» همیشه ۱۲۵ می‌ماند).
NEAR_TOP = 0.5
# پیش از این تعداد جواب، حتی با اطمینان بالا حدس نمی‌زنیم (حدسِ زودهنگام بد است).
MIN_ASKED = 4
# اگر تعداد گزینه‌های زنده به این برسد، حدس می‌زنیم.
SMALL_POOL = 3

# وزنِ «خواندن» و «نخواندن» با یک جواب. نسبتشان ≈ ۶؛ نه آن‌قدر تند که یک جوابِ
# اشتباهی همه‌چیز را نابود کند، نه آن‌قدر نرم که بازی طول بکشد.
HIT = 2.4
MISS = 0.4
# اگر دیتاست دربارهٔ ویژگی‌ای برای شخصیتی چیزی ننوشته باشد، آن جواب برایش بی‌طرف
# است (نه امتیاز می‌گیرد، نه از دست می‌دهد). آزمون نشان داد سخت‌گیری روی این حالت
# نتیجه را بهتر نمی‌کند، پس همان بی‌طرفی می‌ماند.
NEUTRAL = 1.0
# سقف "فهرست کوتاه": وقتی چند نفر دقیقاً هم‌امتیاز می‌مانند، همهٔ گروه تا این تعداد
# نشان داده می‌شود (بیشتر از این، فهرست طولانی و خسته‌کننده می‌شود).
SHORTLIST_LIMIT = 12
# وزن شخصیت‌هایی که کاربر خودش افزوده (یادگیری) نسبت به دیتاست دستی.
LEARNED_WEIGHT = 0.55
# امتیازهای کوچک‌تر از این کسرِ بهترین امتیاز، صفر می‌شوند (تمیزکاری عددی).
EPS_RATIO = 1e-9

ANSWER_VALUES = ("yes", "no", "unknown")


# --------------------------------------------------------------------------- #
# استخر شخصیت‌ها / pool
# --------------------------------------------------------------------------- #


def pool(learned: Optional[Iterable[Dict[str, Any]]] = None) -> Dict[str, Dict[str, Any]]:
    """استخر شخصیت‌ها: دیتاست دستی + شخصیت‌هایی که کاربران افزوده‌اند.

    «learned» فهرستی از ``{"name": str, "values": {trait: 1|-1}}`` است.
    """
    result: Dict[str, Dict[str, Any]] = {}
    for name, entity in data.entity_map().items():
        result[name] = {"about": entity["about"], "values": dict(entity["values"]), "weight": 1.0}
    for entry in learned or []:
        name = str(entry.get("name") or "").strip()
        if not name or name in result:
            continue
        values = entry.get("values")
        if not isinstance(values, dict) or len(values) < 4:
            continue
        clean = {str(key): int(value) for key, value in values.items() if int(value or 0) in (1, -1)}
        result[name] = {"about": "شخصیتی که کاربران خودشان افزوده‌اند", "values": clean, "weight": LEARNED_WEIGHT}
    return result


def icon_of(pool_map: Dict[str, Dict[str, Any]], name: str) -> str:
    entry = pool_map.get(name) or {}
    return data.icon_for(dict(entry.get("values") or {}))


def about_of(pool_map: Dict[str, Dict[str, Any]], name: str) -> str:
    return str((pool_map.get(name) or {}).get("about") or "")


# --------------------------------------------------------------------------- #
# وضعیت بازی / state
# --------------------------------------------------------------------------- #


def new_state() -> Dict[str, Any]:
    """بازی تازه: بدون پاسخ، بدون حدس."""
    return {"answers": [], "excluded": [], "guessed": []}


def normalize(state: Any) -> Dict[str, Any]:
    """هر دادهٔ خراب یا قدیمی را به وضعیت سالم تبدیل می‌کند (بازی هرگز نمی‌شکند)."""
    raw = state if isinstance(state, dict) else {}
    answers: List[Dict[str, str]] = []
    for item in raw.get("answers") or []:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "")
        value = str(item.get("value") or "")
        if key in data.TRAIT_SET and value in ANSWER_VALUES:
            answers.append({"key": key, "value": value})
    excluded = [str(name) for name in (raw.get("excluded") or []) if str(name)]
    guessed = [str(name) for name in (raw.get("guessed") or []) if str(name)]
    return {"answers": answers[:MAX_QUESTIONS], "excluded": excluded[:40], "guessed": guessed[:40]}


def scores_of(state: Dict[str, Any], pool_map: Dict[str, Dict[str, Any]]) -> Dict[str, float]:
    """امتیاز هر شخصیت را از صفر (با بازپخش پاسخ‌ها) حساب می‌کند.

    «بازپخش» به‌جای ضربِ تدریجی، هم ساده‌تر است و هم «یک قدم عقب» را بی‌دردسر
    ممکن می‌کند؛ هزینه‌اش هم ناچیز است (چند هزار ضرب).
    """
    excluded = set(state.get("excluded") or [])
    scores: Dict[str, float] = {
        name: float(entry["weight"]) for name, entry in pool_map.items() if name not in excluded
    }
    for item in state.get("answers") or []:
        key = str(item.get("key") or "")
        value = str(item.get("value") or "")
        if value not in ("yes", "no"):
            continue  # «نمی‌دانم» هیچ اطلاعاتی نمی‌دهد
        for name, score in scores.items():
            if score <= 0:
                continue
            trait = int((pool_map[name]["values"] or {}).get(key) or 0)
            if trait == 0:
                # دیتاست دربارهٔ این ویژگی چیزی نمی‌گوید: بی‌طرف، ولی کمی عقب‌تر.
                scores[name] = score * NEUTRAL
                continue
            hit = (trait == 1 and value == "yes") or (trait == -1 and value == "no")
            scores[name] = score * (HIT if hit else MISS)

    top = max(scores.values(), default=0.0)
    if top <= 0:
        return {name: 0.0 for name in scores}
    return {name: (value / top if value > top * EPS_RATIO else 0.0) for name, value in scores.items()}


def ranking(state: Dict[str, Any], pool_map: Dict[str, Dict[str, Any]], count: int = 3) -> List[Dict[str, Any]]:
    """بهترین گزینه‌ها با سهم درصدی (برای صفحهٔ حدس و نتیجه)."""
    scores = scores_of(state, pool_map)
    total = sum(scores.values())
    rows = sorted(scores.items(), key=lambda item: item[1], reverse=True)[: max(1, count)]
    return [
        {
            "name": name,
            "score": float(score),
            "share": (score / total) if total > 0 else 0.0,
            "icon": icon_of(pool_map, name),
            "about": about_of(pool_map, name),
        }
        for name, score in rows
        if score > 0
    ]


def confidence(state: Dict[str, Any], pool_map: Dict[str, Dict[str, Any]]) -> float:
    """اطمینانِ بهترین گزینه: سهمش از کل وزنِ باقی‌مانده."""
    rows = ranking(state, pool_map, 1)
    return float(rows[0]["share"]) if rows else 0.0


def candidates(state: Dict[str, Any], pool_map: Dict[str, Dict[str, Any]]) -> int:
    """گزینه‌هایی که واقعاً نزدیک صدر هستند (برای نشان‌دادن «چند نفر روی میز است»)."""
    scores = scores_of(state, pool_map)
    return sum(1 for value in scores.values() if value >= NEAR_TOP)


# --------------------------------------------------------------------------- #
# انتخاب سؤال / question
# --------------------------------------------------------------------------- #


def _entropy(state: Dict[str, Any], pool_map: Dict[str, Dict[str, Any]], key: str) -> float:
    """اطلاعاتِ مورد انتظارِ این سؤال: آنتروپیِ دودویی، وزن‌دار با پوشش.

    فقط شخصیت‌هایی که دربارهٔ این ویژگی چیزی می‌گویند شمرده می‌شوند؛ در پایان در
    نسبتِ «وزنِ همین‌ها به کل وزنِ زنده» ضرب می‌شود تا سؤالی که فقط دو نفر را از هم
    جدا می‌کند، بی‌دلیل جلو نیفتد.
    """
    scores = scores_of(state, pool_map)
    total = sum(scores.values())
    if total <= 0:
        return -1.0
    yes = 0.0
    no = 0.0
    for name, score in scores.items():
        if score <= 0:
            continue
        trait = int((pool_map[name]["values"] or {}).get(key) or 0)
        if trait == 1:
            yes += score
        elif trait == -1:
            no += score
    informed = yes + no
    if informed <= 0:
        return -1.0
    coverage = informed / total
    p = yes / informed
    if p <= 0 or p >= 1:
        return 0.0
    entropy = -(p * math.log2(p) + (1 - p) * math.log2(1 - p))
    return entropy * coverage


def next_question(state: Dict[str, Any], pool_map: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """سؤال بعدی؛ یا ``None`` اگر سؤال مفیدی نمانده باشد."""
    asked = {str(item.get("key")) for item in state.get("answers") or []}
    best: Optional[Dict[str, Any]] = None
    best_score = MIN_ENTROPY
    for index, question in enumerate(data.QUESTIONS):
        key = question["key"]
        if key in asked:
            continue
        score = _entropy(state, pool_map, key)
        if score <= best_score:
            continue
        best_score = score
        best = {
            "key": key,
            "text": question["text"],
            "hint": question.get("hint") or "",
            "index": index,
        }
    return best


# --------------------------------------------------------------------------- #
# تصمیم بازی / stage
# --------------------------------------------------------------------------- #


def stage(state: Dict[str, Any], pool_map: Dict[str, Dict[str, Any]]) -> str:
    """بازی الان در چه مرحله‌ای است: ``question`` | ``guess`` | ``done``."""
    asked_count = len(state.get("answers") or [])
    live = [name for name, value in scores_of(state, pool_map).items() if value > 0]

    if not live:
        return "done"  # چیزی نمانده؛ کاربر باید راهنمایی کند
    if asked_count >= MAX_QUESTIONS or len(live) <= 1:
        return "guess"
    share = confidence(state, pool_map)
    if share >= CONFIDENT and asked_count >= MIN_ASKED:
        return "guess"
    if len(live) <= SMALL_POOL and asked_count >= MIN_ASKED + 2:
        return "guess"
    if next_question(state, pool_map) is None and asked_count >= 2:
        return "guess"
    return "question"


def snapshot(state: Dict[str, Any], pool_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """خلاصهٔ کاملِ بازی برای ساختن صفحه (تنها نقطهٔ تماس مسیرها با موتور به‌جز تغییر حالت)."""
    clean = normalize(state)
    current = stage(clean, pool_map)
    asked_count = len(clean.get("answers") or [])
    rows = ranking(clean, pool_map, 3)
    question = next_question(clean, pool_map) if current == "question" else None
    if current == "question" and question is None:
        current = "guess"
    shortlist = ranking(clean, pool_map, SHORTLIST_LIMIT)
    top_share = float(rows[0]["share"]) if rows else 0.0
    second = float(rows[1]["score"]) if len(rows) > 1 else 0.0
    ahead = (float(rows[0]["score"]) / second) if (rows and second > 0) else 99.0
    return {
        "stage": current,
        "question": question,
        "asked": asked_count,
        "max_questions": MAX_QUESTIONS,
        "progress": min(100, int(round(100 * asked_count / MAX_QUESTIONS))),
        "confidence": top_share,
        "ahead": ahead,
        "low_confidence": top_share < LOW_CONFIDENCE and ahead < CLEAR_AHEAD,
        "behind": (100 - int(round(100 * top_share))),
        "guess": rows[0] if rows else None,
        "alternatives": rows[1:],
        "shortlist": shortlist,
        "candidates": candidates(clean, pool_map),
        "answers": list(clean.get("answers") or []),
        "guessed": list(clean.get("guessed") or []),
        "turns": asked_count + len(clean.get("guessed") or []),
    }


# --------------------------------------------------------------------------- #
# تغییر حالت / mutations
# --------------------------------------------------------------------------- #


def answer(state: Any, key: str, value: str) -> Dict[str, Any]:
    """ثبت یک جواب (بله/نه/نمی‌دانم) و برگرداندن وضعیت تازه."""
    clean = normalize(state)
    if str(key) not in data.TRAIT_SET or str(value) not in ANSWER_VALUES:
        return clean
    if any(item["key"] == key for item in clean["answers"]):
        return clean  # همان سؤال دوبار پرسیده نمی‌شود
    if len(clean["answers"]) >= MAX_QUESTIONS:
        return clean
    clean["answers"].append({"key": str(key), "value": str(value)})
    return clean


def undo(state: Any) -> Dict[str, Any]:
    """یک قدم عقب: آخرین جواب برداشته می‌شود (حدس‌ها دست‌نخورده می‌مانند)."""
    clean = normalize(state)
    if clean["answers"]:
        clean["answers"].pop()
    return clean


def wrong_guess(state: Any, name: str) -> Dict[str, Any]:
    """حدس اشتباه بود: این شخصیت کنار گذاشته می‌شود و بازی ادامه دارد."""
    clean = normalize(state)
    target = str(name)
    if not target:
        return clean
    if target not in clean["excluded"]:
        clean["excluded"].append(target)
    if target not in clean["guessed"]:
        clean["guessed"].append(target)
    return clean


def right_guess(state: Any, name: str) -> Dict[str, Any]:
    """حدس درست بود: نامش وارد فهرست حدس‌ها می‌شود تا صفحهٔ نتیجه همان را بخواند."""
    clean = normalize(state)
    target = str(name or "").strip()
    if target and target not in clean["guessed"]:
        clean["guessed"].append(target)
    return clean


def traits_from_answers(state: Any) -> Dict[str, int]:
    """ویژگی‌های یک شخصیتِ تازه را از جواب‌های همین بازی می‌سازد (یادگیری)."""
    clean = normalize(state)
    values: Dict[str, int] = {}
    for item in clean["answers"]:
        if item["value"] == "yes":
            values[item["key"]] = 1
        elif item["value"] == "no":
            values[item["key"]] = -1
    return values


def coverage_share(state: Any, pool_map: Dict[str, Dict[str, Any]]) -> int:
    """چند درصد از شخصیت‌های دیتاست هنوز زنده‌اند (برای نمایش پیشرفت بازی)."""
    if not pool_map:
        return 0
    live = sum(1 for value in scores_of(state, pool_map).values() if value > 0)
    return max(0, min(100, int(round(100 * live / len(pool_map)))))


def answer_labels(state: Any, pool_map: Dict[str, Dict[str, Any]]) -> List[Tuple[str, str]]:
    """فهرست «سؤال → جواب» برای صفحهٔ نتیجه (نمایش مسیر بازی)."""
    rows: List[Tuple[str, str]] = []
    for item in normalize(state)["answers"]:
        text = data.TRAIT_LABELS.get(item["key"], item["key"])
        verb = {"yes": "بله", "no": "نه", "unknown": "نمی‌دانم"}[item["value"]]
        rows.append((text, verb))
    return rows
