"""سنجش دیتاست بازی «ذهن‌خوان».

این ابزار سؤال‌های بی‌مصرف، ویژگی‌های ناشناخته و مهم‌تر از همه «شخصیت‌های
دقیقاً هم‌ویژگی» را پیدا می‌کند؛ همان چیزی که باعث می‌شود بازی بین چند نفر
بماند و نتواند یکی را انتخاب کند. با افزودن یک ویژگی تازه به همان چند نفر،
دقت بازی واقعاً بالا می‌رود.

    python tools/mind_dataset.py
"""

from __future__ import annotations

import pathlib
import sys
from collections import Counter, defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import mind  # noqa: E402
from app.content import mind as data  # noqa: E402


def main() -> int:
    pool = mind.pool()
    traits = list(data.TRAITS)
    print(f"شخصیت‌ها: {len(pool)} | ویژگی‌ها: {len(traits)} | گروه‌ها: {len(data.GROUPS)}")

    used = Counter()
    for entry in pool.values():
        for trait in entry["values"]:
            used[trait] += 1

    unused = [trait for trait in traits if not used.get(trait)]
    print(f"ویژگی‌هایی که به هیچ شخصیتی نخورده‌اند: {len(unused)} {unused if unused else ''}")

    # ویژگی‌هایی که فقط یک شخصیت دارد: سؤالش هیچ‌وقت پرسیده نمی‌شود، چون طرف دوم ندارد.
    lonely = [(trait, used[trait]) for trait in traits if used.get(trait) == 1]
    print(f"ویژگی‌های تک‌نفره (بی‌اثر در وسط بازی): {len(lonely)}")
    for trait, count in lonely:
        print(f"   - {trait}: {count} نفر")

    groups: dict[tuple, list[str]] = defaultdict(list)
    for name, entry in pool.items():
        key = tuple(sorted((trait, value) for trait, value in entry["values"].items()))
        groups[key].append(name)
    tied = sorted(((len(names), names) for names in groups.values() if len(names) > 1), reverse=True)
    print(f"گروه‌های هم‌ویژگی (ریفکتوری نشده): {len(tied)} | بزرگ‌ترین گروه: {tied[0][0] if tied else 1}")
    for size, names in tied[:8]:
        print(f"   - {size}: {'، '.join(names)}")

    # اندیشهٔ سلامت داده: هر شخصیت باید واقعی/داستانی، جنسیت و ملیت داشته باشد.
    # بقیهٔ گروه‌ها (حرفه، زنده/مرده، استودیو و…) اختیاری‌اند.
    core = ("kind", "sex", "origin")
    missing = []
    for name, entry in pool.items():
        values = entry["values"]
        for group in core:
            if group == "origin" and values.get("nonhuman"):
                continue  # یک موجود کارتونی/افسانه‌ای ملیت ندارد
            if not any(values.get(member) == 1 for member in data.GROUPS[group]):
                missing.append((name, group))
    print(f"شخصیت‌های ناقص (گروه اصلی خالی): {len(missing)} {missing[:6]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
