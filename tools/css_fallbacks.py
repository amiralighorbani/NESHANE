"""یکبارمصرف: پیش از هر خط `color-mix(...)` یک مقدار جانشین ساده می‌گذارد.

مرورگرهای قدیمی موبایل (Chrome < 111، Samsung Internet قدیمی، WebViewهای کهنه)
`color-mix()` را نمی‌شناسند؛ وقتی اعلان نامعتبر باشد، پس‌زمینه/حاشیهٔ آن عنصر
اصلاً رنگ نمی‌گیرد و جعبه‌ها خالی و بی‌رنگ می‌مانند. با گذاشتن یک مقدار ساده
**قبل** از خط color-mix، مرورگر قدیمی همان را می‌گیرد و مرورگر تازه مقدار دقیق‌تر را.

اجرا:  python tools/css_fallbacks.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS_PATH = ROOT / "app" / "static" / "css" / "app.css"

FALLBACKS = {
    "background": "var(--surface-2)",
    "border-color": "var(--line-strong)",
    "color": "var(--ink-2)",
    "box-shadow": "var(--shadow-sm)",
    "border": "1px solid var(--line-strong)",
}

LINE = re.compile(r"^(?P<indent>\s*)(?P<prop>[a-z-]+)\s*:\s*(?P<value>.*color-mix.*);\s*$")


def fallback_for(prop: str, value: str) -> str:
    if prop == "background" and "gradient" in value:
        return "var(--accent)"
    return FALLBACKS.get(prop, "none")


def main() -> None:
    source = CSS_PATH.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    added = 0
    for line in source:
        match = LINE.match(line)
        if match:
            indent = match.group("indent")
            prop = match.group("prop")
            declaration = f"{indent}{prop}: {fallback_for(prop, match.group('value'))};"
            # اگر جانشین از قبل هست، دوباره اضافه نشود (اجرای مکرر بی‌خطر باشد).
            if not (output and output[-1].strip() == declaration.strip()):
                output.append(declaration)
                added += 1
        output.append(line)
    CSS_PATH.write_text("\n".join(output) + "\n", encoding="utf-8")
    print(f"fallbacks added: {added} -> {CSS_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
