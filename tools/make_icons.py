"""سازندهٔ آیکون‌های PWA — بدون هیچ کتابخانهٔ بیرونی (فقط zlib و ساختار PNG).

چون پروژه «بدون build و بدون وابستگی» است، آیکون‌ها را همین‌جا پیکسل‌به‌پیکسل می‌سازیم:
پس‌زمینهٔ گرادیانی گردگوشه + ستارهٔ سفید نشانه (همان نشان برند در `favicon.svg`).

اجرا:

    python tools/make_icons.py

خروجی: `app/static/icons/` شامل ۱۹۲، ۵۱۲، مَسکِبل ۵۱۲ و ۱۸۰ (برای iOS).
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "app" / "static" / "icons"

# رنگ‌های برند (هم‌راستا با app.css: --accent و قاب تیرهٔ آن)
TOP_COLOR = (124, 92, 214)     # #7c5cd6
BOTTOM_COLOR = (69, 52, 138)   # #45348a
STAR_COLOR = (255, 255, 255)
SUPERSAMPLE = 2                # ضدلبه، بدون کندشدن


# --------------------------------------------------------------------------- #
# PNG خام / raw PNG writer
# --------------------------------------------------------------------------- #


def write_png(path: Path, width: int, height: int, pixels: bytearray) -> None:
    """RGBA را به‌صورت PNG می‌نویسد (بدون فشرده‌سازی هوشمند، فقط zlib)."""
    raw = bytearray()
    stride = width * 4
    for row in range(height):
        raw.append(0)  # فیلتر «بدون فیلتر»
        raw.extend(pixels[row * stride : (row + 1) * stride])

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    payload = b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", header),
            chunk(b"IDAT", zlib.compress(bytes(raw), 9)),
            chunk(b"IEND", b""),
        ]
    )
    path.write_bytes(payload)


# --------------------------------------------------------------------------- #
# شکل‌ها / shapes
# --------------------------------------------------------------------------- #


def star_polygon(cx: float, cy: float, radius: float) -> list[tuple[float, float]]:
    """ده رأس ستارهٔ پنج‌پر (نوک‌ها و گودی‌ها)."""
    inner = radius * 0.395
    points: list[tuple[float, float]] = []
    for index in range(10):
        angle = -math.pi / 2 + index * math.pi / 5
        length = radius if index % 2 == 0 else inner
        points.append((cx + length * math.cos(angle), cy + length * math.sin(angle)))
    return points


def polygon_spans(points: list[tuple[float, float]], y: float) -> list[tuple[float, float]]:
    """بازه‌های افقیِ داخلِ چندضلعی در این ارتفاع (قاعدهٔ even-odd)."""
    crossings: list[float] = []
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        if y1 == y2:
            continue
        if min(y1, y2) <= y < max(y1, y2):
            ratio = (y - y1) / (y2 - y1)
            crossings.append(x1 + ratio * (x2 - x1))
    crossings.sort()
    return [(crossings[i], crossings[i + 1]) for i in range(0, len(crossings) - 1, 2)]


def rounded_span(y: float, size: float, radius: float) -> tuple[float, float]:
    """بازهٔ افقی یک مربع گردگوشه در ارتفاع y."""
    if y < radius:
        dy = radius - y
        inset = radius - math.sqrt(max(0.0, radius * radius - dy * dy))
    elif y > size - radius:
        dy = y - (size - radius)
        inset = radius - math.sqrt(max(0.0, radius * radius - dy * dy))
    else:
        inset = 0.0
    return inset, size - inset


def blend(pixel: list[int], color: tuple[int, int, int], alpha: float) -> None:
    for channel in range(3):
        pixel[channel] = int(pixel[channel] * (1 - alpha) + color[channel] * alpha)


def render(size: int, *, maskable: bool = False) -> bytearray:
    """یک آیکون RGBA می‌سازد؛ `maskable` یعنی پس‌زمینهٔ تمام‌صفحه و ستارهٔ کوچک‌تر."""
    scale = SUPERSAMPLE
    big = size * scale
    radius = 0.0 if maskable else big * 0.22
    star_radius = big * (0.24 if maskable else 0.30)
    star = star_polygon(big / 2, big / 2 + big * 0.015, star_radius)

    # لایهٔ بزرگ (با ضدلبه) — بعد میانگین‌گیری می‌شود
    rows: list[bytearray] = []
    for y in range(big):
        row = bytearray(big * 4)
        left, right = rounded_span(y + 0.5, big, radius)
        spans = polygon_spans(star, y + 0.5)
        ratio = y / max(1, big - 1)
        base = tuple(
            int(TOP_COLOR[channel] + (BOTTOM_COLOR[channel] - TOP_COLOR[channel]) * ratio)
            for channel in range(3)
        )
        for x in range(big):
            pixel = [0, 0, 0, 0]
            if left <= x + 0.5 <= right:
                pixel = [base[0], base[1], base[2], 255]
                for start, end in spans:
                    if start <= x + 0.5 <= end:
                        blend(pixel, STAR_COLOR, 1.0)
                        break
            offset = x * 4
            row[offset : offset + 4] = bytes(pixel)
        rows.append(row)

    # میانگین‌گیری بلوک‌ها برای نرم‌کردن لبه‌ها
    out = bytearray(size * size * 4)
    area = scale * scale
    for y in range(size):
        for x in range(size):
            total = [0, 0, 0, 0]
            for sy in range(scale):
                row = rows[y * scale + sy]
                for sx in range(scale):
                    offset = (x * scale + sx) * 4
                    for channel in range(4):
                        total[channel] += row[offset + channel]
            offset = (y * size + x) * 4
            out[offset : offset + 4] = bytes(value // area for value in total)
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    jobs = [
        ("icon-192.png", 192, False),
        ("icon-512.png", 512, False),
        ("icon-maskable-512.png", 512, True),
        ("apple-touch-icon-180.png", 180, False),
    ]
    for name, size, maskable in jobs:
        write_png(OUT_DIR / name, size, size, render(size, maskable=maskable))
        print(f"icon written: {name} ({size}x{size})")


if __name__ == "__main__":
    main()
