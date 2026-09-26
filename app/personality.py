"""موتور تست‌های شخصیت: از پاسخ‌های واقعی کاربر به نتیجهٔ تفسیرشده می‌رسد.

دو خانوادهٔ تست داریم و هر کدام فرمول خودش را دارد:

* **pair** (مثل MBTI): پرسش‌ها دوگزینه‌ای و اجباری‌اند. هر گزینه به یک قطب امتیاز
  می‌دهد؛ نتیجهٔ هر محور درصدِ گرایش به هر قطب است و «قدرت ترجیح» از اختلاف دو قطب
  درمی‌آید (غالب / ملایم / مرزی). این همان چیزی است که در MBTI «شدت ترجیح» نامیده
  می‌شود و دو نفر با تیپ یکسان را از هم جدا می‌کند.
* **max** (مثل پنج عامل بزرگ، گاردنر، چاکرا، انیاگرام): هر پرسش چند گزینه دارد و هر
  گزینه به یک عامل امتیاز می‌دهد. امتیاز هر عامل بر **بیشترین امتیازِ قابل‌کسب همان
  عامل** تقسیم می‌شود؛ پس عددِ به‌دست‌آمده واقعاً «درصد از سقف» است و هیچ‌وقت
  مصنوعی ۱۰۰٪ نمی‌شود.

در هر دو حالت، اگر کاربر پرسشی را بی‌جواب بگذارد، آن پرسش هم از صورت و هم از مخرج
حساب حذف می‌شود؛ پس نتیجه هرگز به‌خاطر جواب‌های خالی وارونه نمی‌شود.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence, Tuple

from .content import personality as content
from .models import TestResult
from .utils import to_fa, today_label

# برچسب قدرت ترجیح روی محورهای دوگزینه‌ای
STRENGTH_LABELS: List[Tuple[float, str]] = [
    (0.5, "ترجیح غالب"),
    (0.25, "ترجیح ملایم"),
    (0.0, "ترجیح مرزی"),
]

# برچسب سطح برای عامل‌های چندگزینه‌ای (بر پایهٔ درصد از سقف)
LEVEL_BANDS: List[Tuple[int, str, str]] = [
    (78, "بالا", "good"),
    (58, "میانه", "mid"),
    (0, "در حال رشد", "low"),
]


def _questions(test: Dict[str, Any]) -> List[Dict[str, Any]]:
    return test.get("questions") or []


def _clean_answers(answers: Dict[str, int], total: int) -> Dict[int, int]:
    """پاسخ‌های معتبر را به شکل {شمارهٔ پرسش: شمارهٔ گزینه} برمی‌گرداند."""
    cleaned: Dict[int, int] = {}
    for index_key, option_index in (answers or {}).items():
        try:
            question_index = int(index_key)
            chosen = int(option_index)
        except (TypeError, ValueError):
            continue
        if 0 <= question_index < total:
            cleaned[question_index] = chosen
    return cleaned


def _max_scores(test: Dict[str, Any]) -> Dict[str, int]:
    """بیشترین امتیازی که هر عامل می‌توانست از این پرسش‌ها بگیرد («سقف»)."""
    maxima: Dict[str, int] = {}
    for question in _questions(test):
        options = question.get("options") or []
        best: Dict[str, int] = {}
        for option in options:
            for key, value in (option.get("scores") or {}).items():
                best[key] = max(best.get(key, 0), int(value))
        for key, value in best.items():
            if value > 0:
                maxima[key] = maxima.get(key, 0) + value
    return maxima


def score_test(test_key: str, answers: Dict[str, int]) -> Tuple[str, Dict[str, int]]:
    """پاسخ‌ها را جمع می‌زند و کلید نتیجه را برمی‌گرداند."""
    test = content.get_test(test_key)
    questions = _questions(test)
    chosen_answers = _clean_answers(answers, len(questions))
    totals: Dict[str, int] = {}

    for question_index, chosen in chosen_answers.items():
        options = questions[question_index].get("options") or []
        if not 0 <= chosen < len(options):
            continue
        for key, value in (options[chosen].get("scores") or {}).items():
            totals[key] = totals.get(key, 0) + int(value)

    if test.get("mode") == "pair":
        code = ""
        for left, right in test.get("axes") or []:
            # تساویِ کامل دو قطب: قطب اول انتخاب می‌شود تا نتیجه پایدار بماند و
            # با تغییر ترتیب پرسش‌ها عوض نشود.
            code += left if totals.get(left, 0) >= totals.get(right, 0) else right
        return code, totals

    if not totals:
        return "", totals
    # برنده همان چیزی است که در صفحه نشان داده می‌شود: **درصد از سقف**، نه خامِ امتیاز.
    # اگر این دو یکی نبودند، تیتر نتیجه با رتبهٔ فهرست نمی‌خواند. در تساوی، امتیاز
    # خام و بعد ترتیبِ الفبایی تعیین‌کننده است تا نتیجه به ترتیبِ پرسش‌ها وابسته نباشد.
    maxima = _max_scores(test)
    ranked = sorted(
        totals.items(),
        key=lambda item: (-_share(item[1], maxima.get(item[0], 0)), -item[1], str(item[0])),
    )
    return (str(ranked[0][0]) if ranked else ""), totals


def _share(value: int, ceiling: int) -> int:
    """سهمِ یک عامل از سقفِ قابل‌کسبش (۰ تا ۱۰۰)."""
    if ceiling <= 0:
        return 0
    return max(0, min(100, round(100 * int(value) / int(ceiling))))


def _percent_of_max(totals: Dict[str, int], maxima: Dict[str, int], keys: Sequence[str]) -> Dict[str, int]:
    """درصدِ امتیاز هر عامل از سقفِ قابل‌کسبِ همان عامل."""
    return {key: _share(totals.get(key, 0), maxima.get(key, 0)) for key in keys}


def _level_for(percent: int) -> Tuple[str, str]:
    for limit, label, tone in LEVEL_BANDS:
        if percent >= limit:
            return label, tone
    return LEVEL_BANDS[-1][1], LEVEL_BANDS[-1][2]


def _strength_label(left_value: int, right_value: int) -> str:
    total = left_value + right_value
    if total <= 0:
        return STRENGTH_LABELS[-1][1]
    gap = abs(left_value - right_value) / total
    for limit, label in STRENGTH_LABELS:
        if gap >= limit:
            return label
    return STRENGTH_LABELS[-1][1]


def _axis_detail(test: Dict[str, Any], totals: Dict[str, int]) -> List[Dict[str, str]]:
    pairs: List[Dict[str, str]] = test.get("axis_pairs") or [
        {"left": left, "right": right, "title": ""} for left, right in test.get("axes") or []
    ]
    labels: Dict[str, str] = test.get("axis_labels", {})
    detail: List[Dict[str, str]] = []
    for pair in pairs:
        left, right = pair["left"], pair["right"]
        left_value, right_value = totals.get(left, 0), totals.get(right, 0)
        total = (left_value + right_value) or 1
        left_pct = round(100 * left_value / total)
        detail.append(
            {
                "title": str(pair.get("title", "")),
                "left": left,
                "right": right,
                "left_label": labels.get(left, left),
                "right_label": labels.get(right, right),
                "left_pct": str(left_pct),
                "right_pct": str(100 - left_pct),
                "winner": left if left_value >= right_value else right,
                "strength": _strength_label(left_value, right_value),
            }
        )
    return detail


RANKED_LIMIT = 9


def _ranked_detail(test: Dict[str, Any], totals: Dict[str, int], maxima: Dict[str, int], code: str) -> List[Dict[str, str]]:
    results: Dict[str, Any] = test.get("results") or {}
    keys = sorted(
        results.keys(),
        key=lambda key: (-_share(totals.get(key, 0), maxima.get(key, 0)), -totals.get(key, 0), str(key)),
    )
    percents = _percent_of_max(totals, maxima, keys)
    detail: List[Dict[str, str]] = []
    for key in keys[:RANKED_LIMIT]:
        observed = totals.get(key, 0)
        if observed <= 0:
            continue
        percent = percents[key]
        level, tone = _level_for(percent)
        detail.append(
            {
                "key": str(key),
                "title": str(results[key].get("title", key)),
                "icon": str(results[key].get("icon", "")),
                "glyph": str(results[key].get("glyph", "")),
                "pct": str(percent),
                "raw": str(observed),
                "level": level,
                "tone": tone,
                "top": "1" if str(key) == str(code) else "0",
            }
        )
    return detail


def _breakdown(axes: List[Dict[str, str]], ranked: List[Dict[str, str]]) -> str:
    """خلاصهٔ خوانا از نتیجه برای مدل زبانی."""
    lines: List[str] = []
    for axis in axes:
        lines.append(
            f"{axis['title']}: {axis['left_label']} {axis['left_pct']}٪ / "
            f"{axis['right_label']} {axis['right_pct']}٪ — غالب: {axis['winner']} ({axis['strength']})"
        )
    for index, item in enumerate(ranked, start=1):
        lines.append(f"{to_fa(index)}. {item['title']} — {item['pct']}٪ ({item['level']})")
    return "\n".join(lines)


def build_result(test_key: str, answers: Dict[str, int], attempt_id: int = 0) -> TestResult:
    test = content.get_test(test_key)
    questions = _questions(test)
    code, totals = score_test(test_key, answers)
    results: Dict[str, Any] = test.get("results") or {}
    data: Dict[str, Any] = results.get(code) or next(iter(results.values()))
    if not results.get(code):
        code = next(iter(results.keys()))

    maxima = _max_scores(test)
    strengths = [str(item) for item in data.get("strengths", [])]
    careers = [str(item) for item in data.get("careers", [])]
    axes = _axis_detail(test, totals) if test.get("mode") == "pair" else []
    ranked = _ranked_detail(test, totals, maxima, code) if test.get("mode") != "pair" else []

    return TestResult(
        test_key=str(test["key"]),
        test_label=str(test["label"]),
        test_icon=str(test["icon"]),
        accent=str(test["accent"]),
        code=str(code),
        title=str(data.get("title", "")),
        icon=str(data.get("icon", "")),
        glyph=str(data.get("glyph", "")),
        tagline=str(data.get("tagline", "")),
        body=str(data.get("body", "")),
        gift=str(data.get("gift", "")) or "، ".join(strengths),
        shadow=str(data.get("shadow", "")),
        advice=str(data.get("advice", "")),
        partner=str(data.get("partner", "")),
        strengths=strengths,
        careers=careers,
        love=str(data.get("love", "")),
        scores={key: int(value) for key, value in totals.items()},
        axes=axes,
        ranked=ranked,
        created_label=today_label(),
        attempt_id=attempt_id,
        answered=len(_clean_answers(answers, len(questions))),
        breakdown=_breakdown(axes, ranked),
        has_signal=bool(totals),
    )


def progress_label(test_key: str, answered: int) -> str:
    total = content.question_count(test_key)
    return f"پرسش {to_fa(min(answered + 1, total))} از {to_fa(total)}"
