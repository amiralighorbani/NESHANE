"""ساخت تصاویر فروشگاهی (مارکت‌پلیس) از صفحات واقعی «نشانه».

مسیر کار:
  ۱) یک کاربر نمایشی می‌سازد (با نام، شهر و تاریخ تولد واقعی‌نما).
  ۲) با نشست خودش چند «خوانش» (حافظ، تاروت، تاس) و یک تست کامل می‌سازد.
  ۳) HTML همان صفحات را از سرور زنده می‌گیرد و ذخیره می‌کند.
  ۴) با کرومِ بی‌سر از هر صفحه اسکرین‌شات ۳۹۰×۸۴۴ (نسبت ۲ برابر) می‌گیرد.
  ۵) هر اسکرین را داخل ماکت سه‌بعدی گوشی می‌گذارد — با نوار وضعیت، ضخامت
     بدنه، بازتاب شیشه و سایهٔ عمیق — و با تیتر تبلیغاتی روی بوم ۱۰۸۰×۱۹۲۰
     می‌نشاند.

چیدمان بوم دوستونه است و عمداً «بیرون‌زدگی» دارد: گوشی از یک لبهٔ بوم کمی
بیرون می‌زند و ستون محتوای همان تصویر (نشان گام، سه کارت ویژگی و یک بلوک
امضای مخصوص همان صفحه) در ستون روبه‌رو می‌آید. ستون‌ها با فاصلهٔ امن از هم
جدا شده‌اند تا هیچ عنصری روی گوشی نیفتد و هیچ ناحیهٔ خالیِ بزرگی نماند.

هر تصویر تمِ خودش را دارد (رنگ تأکید، بافت پس‌زمینه، زاویهٔ گوشی و ستون
محتوا) ولی زبان بصری — فونت، کارت‌ها، سایه‌ها و نشان «نشانه» — در همه یکی است.

اجرا:  python tools/make_store_shots.py            (سرور نشانه باید بالا باشد)
اگر کروم جای دیگری است:  NESHANE_CHROME="مسیر کروم" python tools/make_store_shots.py
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import pathlib
import re
import shutil
import socket
import socketserver
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import smoke_test as st  # noqa: E402  (کلاینت و کمک‌کارهای ثبت‌نام/ورود)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

MARKETING = ROOT / "marketing"
SHOTS_HTML = MARKETING / "shots" / "html"
SHOTS = MARKETING / "shots"
FRAMES = MARKETING / "screenshots"
FONTS = MARKETING / "fonts"
FRAME_PAGE = MARKETING / "frames.html"

MIRROR_PORT = 8099
CANVAS_W, CANVAS_H = 1080, 1920
SCREEN_W, SCREEN_H = 390, 844  # اندازهٔ واقعی اپ (CSS px)

# --- هندسهٔ ماکت گوشی (پیکسل بوم ۱۰۸۰×۱۹۲۰) ------------------------------ #
PHONE_W = 660
PHONE_PAD = 13
PHONE_TOP = 388
PHONE_DEPTH = 28                                 # ضخامت بدنه در راستای عمق
PHONE_RADIUS = 74
SCREEN_INNER = PHONE_W - 2 * PHONE_PAD           # ۶۳۴
STATUS_BAR_H = 78
SHOT_H = round(SCREEN_INNER * 1688 / 780)        # همان نسبت اسکرین‌شات دوبرابر
PHONE_H = STATUS_BAR_H + SHOT_H + 2 * PHONE_PAD

# --- چیدمان دوستونه ------------------------------------------------------- #
# گوشی `PHONE_BLEED` از لبهٔ بوم بیرون می‌زند و ستون محتوا در طرف دیگر با
# فاصلهٔ امن می‌نشیند. با ۶۶۰ پیکسل عرض گوشی و ستون ۳۳۰ پیکسلی، ۶۴ پیکسل
# فاصلهٔ آزاد می‌ماند؛ چرخش سه‌بعدی حداکثر ~۳۰ پیکسل جابه‌جایی می‌دهد، پس
# برخوردی پیش نمی‌آید (این را با اندازه‌گیری پیکسلی هم چک می‌کنیم).
PHONE_BLEED = 30
RAIL_W = 330
RAIL_MARGIN = 56
RAIL_TOP = PHONE_TOP
RAIL_BOTTOM = 1880

DEMO = {
    "phone": "09120000077",
    "username": "neshane_demo",
    "password": "Neshane!2026",
    "name": "نیلوفر",
    "family": "احمدی",
    "gender": "f",
    "city": "تهران",
    "jy": "1372",
    "jm": "4",
    "jd": "18",
    "birth_time": "08:30",
}

INTENTS = {
    "hafez": "دلم می‌خواهد بدانم این پیامِ تازه‌ای که آمده، راهِ درست را نشان می‌دهد یا نه.",
    "tarot": "بین دو انتخاب مانده‌ام؛ کدام راه به حالِ این روزهایم بیشتر می‌خورد؟",
    "dice": "برای شروعِ کاری که چند وقته در ذهنم است، امروز وقتش هست یا صبر کنم؟",
}

KICKER = "فال و تست شخصیت، فارسی و راست‌به‌چپ"

# زاویهٔ گوشی: طرفِ بیرون‌زده به بیننده نزدیک‌تر می‌شود تا عمق باورپذیر بماند.
# (زاویه‌ها ملایم‌اند تا گوشی با احتساب پرسپکتیو داخل بوم بماند و لبه‌اش بریده نشود.)
TILT_RIGHT = "rotateX(4deg) rotateY(-12deg) rotateZ(-1deg)"     # گوشی به چپ بیرون زده
TILT_LEFT = "rotateX(4deg) rotateY(11deg) rotateZ(1deg)"        # گوشی به راست بیرون زده
TILT_RIGHT_SOFT = "rotateX(3deg) rotateY(-8deg) rotateZ(-0.6deg)"
TILT_LEFT_SOFT = "rotateX(5deg) rotateY(8deg) rotateZ(0.8deg)"

# بلوک «امضا»: هر صفحه یک قطعهٔ بصری مخصوص خودش دارد تا ده تصویر شبیه هم نشوند.
SIGN_ORBIT = """
<div class="sign mini">
<div class="mini__t">یک نیت، هفت مسیر</div>
<div class="orbit">
  <span style="width:132px;height:132px;left:calc(50% - 66px);top:calc(50% - 66px)"></span>
  <span style="width:186px;height:186px;left:calc(50% - 93px);top:calc(50% - 93px);border-color:var(--b-dot)"></span>
  <span style="width:240px;height:240px;left:calc(50% - 120px);top:calc(50% - 120px);border-color:var(--a-soft)"></span>
  <img src="/static/icons/icon-192.png" alt="" />
</div>
</div>
"""

SIGN_QUOTE = """
<div class="sign bubble" style="font-size:20px;line-height:1.85">
  «دلا بسوز که سوز تو کار‌ها بکند<br />نیاز نیم‌شبی دفعِ صد بلا بکند»
</div>
"""

SIGN_TAROT = """
<div class="sign mini">
<div class="mini__t">سه کارت، سه معنی</div>
<div class="fan">
  <i style="right:0;transform:rotate(-10deg)"></i>
  <i style="right:74px;bottom:16px"></i>
  <i style="right:148px;transform:rotate(10deg)"></i>
</div>
</div>
"""

SIGN_DICE = """
<div class="sign mini">
<div class="mini__t">تاس‌های امروز</div>
<div class="dice">
  <span class="die"><i class="fa-solid fa-dice-three"></i></span>
  <span class="die"><i class="fa-solid fa-dice-five"></i></span>
  <span class="die"><i class="fa-solid fa-dice-one"></i></span>
</div>
</div>
"""

SIGN_METHODS = """
<div class="sign mini">
<div class="mini__t">یک نیت، هفت روش</div>
<div class="pills">
  <span class="pill">حافظ</span><span class="pill">تاروت</span><span class="pill">تاس</span>
  <span class="pill">رون</span><span class="pill">عدد</span><span class="pill">طالع</span>
  <span class="pill">چینی</span>
</div>
</div>
"""

SIGN_INTENT = """
<div class="sign bubble" style="font-size:20px;line-height:1.8">
  «بین دو انتخاب مانده‌ام؛ کدام راه به حالم بیشتر می‌خورد؟»
</div>
"""

SIGN_STATS = """
<div class="sign mini" style="display:grid;gap:18px">
  <div class="stat"><b>۵۲+</b><small>کارت آماری در چهار دسته</small></div>
  <div class="stat"><b>۴</b><small>هویت، زمان، بدن و جهان</small></div>
</div>
"""

SIGN_BARS = """
<div class="sign mini">
  <div class="mini__t">نمرهٔ مؤلفه‌های تو</div>
  <div class="brow"><span>درون‌گرا</span><span>۶۲٪</span></div>
  <div class="bar"><i style="width:62%"></i></div>
  <div class="brow"><span>شهودی</span><span>۷۴٪</span></div>
  <div class="bar"><i style="width:74%"></i></div>
  <div class="brow"><span>احساسی</span><span>۵۸٪</span></div>
  <div class="bar"><i style="width:58%"></i></div>
</div>
"""

SIGN_TIMELINE = """
<div class="sign mini tl">
  <div><b></b><span>فال حافظ — امروز</span></div>
  <div><b></b><span>تاروت سه‌کارتی — دیروز</span></div>
  <div><b></b><span>تست MBTI — ۳ روز پیش</span></div>
  <div><b></b><span>زندگی در عدد — هفتهٔ پیش</span></div>
</div>
"""

# هر تصویر: نامک، تیتر، زیرتیتر، رنگ تأکید، رنگ دوم، بافت، طرف ستون، سبک
# ستون، سه کارت ویژگی، گام و برچسب گام، و بلوک امضای همان صفحه.
FRAME_SPECS: List[Dict[str, object]] = [
    {
        "name": "01-start",
        "tags": ["فال حافظ", "تاروت", "تست شخصیت"],
        "note": "نسخهٔ ۱٫۰ — همین حالا",
        "screen": "start",
        "step": "۰۱",
        "label": "شروع سفر",
        "title": "فالت را از دلِ نیتِ <em>امروزت</em> بگیر",
        "sub": "اول نیتت را می‌نویسی، بعد نشانه راهش را نشان می‌دهد. هفت روش، یک نیت.",
        "accent": "#6b4fbb",
        "accent2": "#2f8fa8",
        "motif": "motif--orbit",
        "side": "right",
        "rail": "stack",
        "tilt": TILT_RIGHT,
        "chips": [
            ("fa-wand-magic-sparkles", "هفت روش فال", "حافظ، تاروت، تاس و رون"),
            ("fa-brain", "ده تست شخصیت", "با فرمول واقعی هر آزمون"),
            ("fa-clock-rotate-left", "پروندهٔ خوانش‌ها", "همهٔ فال‌ها و نتیجه‌ها"),
        ],
        "sign": SIGN_ORBIT,
    },
    {
        "name": "02-hafez",
        "tags": ["غزل کامل", "تفسیر امروز", "کلیدواژه‌ها"],
        "note": "متن پایه، همیشه هست",
        "screen": "hafez",
        "step": "۰۲",
        "label": "فال حافظ",
        "title": "فال حافظ، با همهٔ <em>غزل</em> و تفسیر امروزت",
        "sub": "غزل را با کلیدواژه‌های نیتت می‌خوانیم و معنی‌اش را برای خودت می‌گوییم.",
        "accent": "#2f8fa8",
        "accent2": "#6b4fbb",
        "motif": "motif--arc",
        "side": "left",
        "rail": "timeline",
        "tilt": TILT_LEFT,
        "chips": [
            ("fa-book-open-reader", "غزل کامل", "با تفسیر همین امروز"),
            ("fa-key", "کلیدواژه‌های نیت", "روی همان جملهٔ تو"),
            ("fa-feather-pointed", "متن پایه هم هست", "حتی اگر مدل قطع باشد"),
        ],
        "sign": SIGN_QUOTE,
    },
    {
        "name": "03-tarot",
        "tags": ["یک یا سه کارت", "راست و برگشته", "سه کارت"],
        "note": "کارت‌ها واقعاً رو می‌شوند",
        "screen": "tarot",
        "step": "۰۳",
        "label": "کارت تاروت",
        "title": "کارت‌های تاروت <em>واقعاً</em> رو می‌شوند",
        "sub": "سه کارت با نام، جایگاه و راست یا برگشته بودن — هر فال شکل خودش را دارد.",
        "accent": "#c2456b",
        "accent2": "#6b4fbb",
        "motif": "motif--blobs",
        "side": "right",
        "rail": "pills",
        "tilt": TILT_RIGHT_SOFT,
        "chips": [
            ("fa-clone", "یک یا سه کارت", "به انتخاب خودت"),
            ("fa-arrows-rotate", "راست و برگشته", "جایگاه هر کارت مشخص"),
            ("fa-hand-sparkles", "کارت‌ها رو می‌شوند", "با انیمیشن واقعی"),
        ],
        "sign": SIGN_TAROT,
    },
    {
        "name": "04-dice",
        "tags": ["سه تاس", "چشم‌های واقعی", "جهت هر عدد"],
        "note": "هر عدد، یک معنی",
        "screen": "dice",
        "step": "۰۴",
        "label": "فال تاس",
        "title": "تاس‌های نمادین، با همان <em>چشم‌ها</em>",
        "sub": "سه تاس واقعی می‌افتند و هر عدد معنی، جهت و تفسیر خودش را دارد.",
        "accent": "#c98a2e",
        "accent2": "#b1541f",
        "motif": "motif--grid",
        "side": "left",
        "rail": "numbered",
        "tilt": TILT_LEFT_SOFT,
        "chips": [
            ("fa-dice", "سه تاس نمادین", "با چشم‌های واقعی"),
            ("fa-hashtag", "معنی هر عدد", "جهت و تفسیر خودش"),
            ("fa-dice-five", "هیچ فالی تکراری نیست", "هر بار از نو"),
        ],
        "sign": SIGN_DICE,
    },
    {
        "name": "05-methods",
        "tags": ["هفت روش", "یک نیت", "ابزار جدا"],
        "note": "هیچ دو فالی یکسان نیست",
        "screen": "methods",
        "step": "۰۵",
        "label": "روش‌های فال",
        "title": "هفت روش فال، هر کدام با <em>ابزار خودش</em>",
        "sub": "حافظ، تاروت، تاس، رون، عدد، طالع و چینی — از هم قابل تشخیص و متفاوت.",
        "accent": "#4b53c9",
        "accent2": "#2f8fa8",
        "motif": "motif--mesh",
        "side": "right",
        "rail": "pills",
        "tilt": TILT_LEFT_SOFT,
        "chips": [
            ("fa-book-open-reader", "حافظ و تاروت", "با نیت خودت"),
            ("fa-dice", "تاس و رون", "با ابزار مخصوصشان"),
            ("fa-star-and-crescent", "عدد، طالع و چینی", "همه در یک جا"),
        ],
        "sign": SIGN_METHODS,
    },
    {
        "name": "06-intent",
        "tags": ["نیت خودت", "تفسیر شخصی", "حریم خصوصی"],
        "note": "لینک فال فقط برای تو",
        "screen": "intent",
        "step": "۰۶",
        "label": "نوشتن نیت",
        "title": "یک جمله از نیتت، <em>تفاوت</em> فال را می‌سازد",
        "sub": "تفسیر روی همان چیزی سوار می‌شود که خودت نوشته‌ای، نه روی یک متن آماده.",
        "accent": "#8a4fc9",
        "accent2": "#c2456b",
        "motif": "motif--sparkle",
        "side": "left",
        "rail": "stack",
        "tilt": TILT_LEFT,
        "chips": [
            ("fa-feather-pointed", "نیت خودت", "یک جملهٔ کوتاه کافی است"),
            ("fa-wand-magic-sparkles", "تفسیر شخصی", "روی همان جمله"),
            ("fa-lock", "حریم خصوصی", "لینک فال فقط برای تو"),
        ],
        "sign": SIGN_INTENT,
    },
    {
        "name": "07-life",
        "tags": ["۵۲+ کارت", "چهار دسته", "آمار شخصی"],
        "note": "همه از تولد خودت",
        "screen": "life",
        "step": "۰۷",
        "label": "زندگی در عدد",
        "title": "<em>زندگی در عدد</em>؛ نگاهی آماری به خودت",
        "sub": "از ریتم قلب و عددِ غذا تا الگوهای رفتاری — همه از تولدِ خودت حساب می‌شود.",
        "accent": "#2f8f6b",
        "accent2": "#2f8fa8",
        "motif": "motif--waves",
        "side": "right",
        "rail": "numbered",
        "tilt": TILT_RIGHT_SOFT,
        "chips": [
            ("fa-chart-simple", "بیش از ۵۰ کارت", "در چهار دستهٔ جدا"),
            ("fa-heart-pulse", "هویت و بدن", "از تولد خودت"),
            ("fa-moon", "زمان و جهان", "فاز ماه و شمارش روزها"),
        ],
        "sign": SIGN_STATS,
    },
    {
        "name": "08-tests",
        "tags": ["MBTI", "پنج عامل بزرگ", "انیاگرام"],
        "note": "نتیجه با جواب‌های خودت",
        "screen": "tests",
        "step": "۰۸",
        "label": "تست‌های شخصیت",
        "title": "ده تستِ شخصیت، <em>در یک جا</em>",
        "sub": "MBTI، پنج عامل بزرگ، کهن‌الگوهای یونگ، انیاگرام، DISC، چاکرا و بیشتر.",
        "accent": "#2f7fc9",
        "accent2": "#6b4fbb",
        "motif": "motif--dots",
        "side": "left",
        "rail": "timeline",
        "tilt": TILT_LEFT_SOFT,
        "chips": [
            ("fa-brain", "ده آزمون معتبر", "MBTI، پنج عامل، DISC"),
            ("fa-compass", "نمرهٔ هر مؤلفه", "با نمودار محورها"),
            ("fa-chart-pie", "تفسیر و قدم بعدی", "روی جواب‌های خودت"),
        ],
        "sign": SIGN_BARS,
    },
    {
        "name": "09-history",
        "tags": ["تاریخچه", "مقایسه", "خروجی چاپ"],
        "note": "همه در یک پرونده",
        "screen": "history",
        "step": "۰۹",
        "label": "پروندهٔ خوانش‌ها",
        "title": "همهٔ خوانش‌ها و نتیجه‌ها، <em>در پروندهٔ تو</em>",
        "sub": "هر فال و هر تست ذخیره می‌شود تا بعداً برگردی، مقایسه کنی و پرونده‌ات را ببینی.",
        "accent": "#5b6070",
        "accent2": "#2f8fa8",
        "motif": "motif--bars",
        "side": "right",
        "rail": "timeline",
        "tilt": TILT_RIGHT,
        "chips": [
            ("fa-bookmark", "همهٔ فال‌ها", "با تاریخ و روش"),
            ("fa-chart-simple", "نتیجهٔ تست‌ها", "قابل مقایسه با هم"),
            ("fa-print", "پروندهٔ قابل چاپ", "برای خودت"),
        ],
        "sign": SIGN_TIMELINE,
    },
    {
        "name": "10-result",
        "tags": ["نمرهٔ مؤلفه", "نمودار محور", "قدم بعدی"],
        "note": "قدم بعدی هم می‌آید",
        "screen": "result",
        "step": "۱۰",
        "label": "نتیجهٔ دقیق",
        "title": "نتیجهٔ دقیق، با <em>نمرهٔ هر مؤلفه</em>",
        "sub": "نمودار محورها، تفسیر پاسخ‌ها و قدمِ بعدی — همه بر اساس جواب‌های خودت.",
        "accent": "#b8860b",
        "accent2": "#6b4fbb",
        "motif": "motif--burst",
        "side": "left",
        "rail": "numbered",
        "tilt": TILT_RIGHT,
        "chips": [
            ("fa-chart-column", "نمرهٔ هر مؤلفه", "عدد دقیق، نه حدس"),
            ("fa-award", "تیپ شخصیتی", "با نمودار محورها"),
            ("fa-route", "قدم بعدی", "پیشنهاد نشانه برای تو"),
        ],
        "sign": SIGN_BARS,
    },
]


def hex_rgba(value: str, alpha: float) -> str:
    """رنگ هگز را به rgba با شفافیت دلخواه تبدیل می‌کند."""
    raw = value.lstrip("#")
    red, green, blue = (int(raw[index : index + 2], 16) for index in (0, 2, 4))
    return f"rgba({red}, {green}, {blue}, {alpha})"


def frame_style(spec: Dict[str, object]) -> str:
    """متغیرهای CSS هر تصویر: رنگ‌ها، جای گوشی و زاویه‌اش."""
    accent = str(spec["accent"])
    second = str(spec["accent2"])
    rail_side = str(spec["side"])
    # گوشی به طرف مقابلِ ستونِ محتوا بیرون می‌زند تا هیچ‌وقت زیر کارت‌ها نرود.
    phone_left = -PHONE_BLEED if rail_side == "right" else CANVAS_W - PHONE_W + PHONE_BLEED
    parts = {
        "--a": accent,
        "--b": second,
        "--a-soft": hex_rgba(accent, 0.15),
        "--a-dot": hex_rgba(accent, 0.26),
        "--a-glow": hex_rgba(accent, 0.32),
        "--a-shadow": hex_rgba(accent, 0.40),
        "--b-soft": hex_rgba(second, 0.26),
        "--b-dot": hex_rgba(second, 0.24),
        "--phone-left": f"{phone_left}px",
        "--phone-tilt": str(spec["tilt"]),
    }
    return "; ".join(f"{name}: {value}" for name, value in parts.items())


def rail_html(spec: Dict[str, object]) -> str:
    """ستون محتوای همان تصویر: گام، سه کارت ویژگی و بلوک امضا."""
    style = str(spec["rail"])
    side = str(spec["side"])
    chips = []
    for index, (icon, label, sub) in enumerate(spec["chips"], start=1):  # type: ignore[misc]
        if style == "numbered":
            mark = f'<span class="chip__i">{"۱۲۳۴۵۶۷۸۹۰"[index - 1]}</span>'
        else:
            mark = f'<span class="chip__i"><i class="fa-solid {icon}"></i></span>'
        chips.append(
            f'<div class="chip">{mark}'
            f'<span class="chip__t"><b>{label}</b><small>{sub}</small></span></div>'
        )
    return (
        f'<aside class="rail rail--{side} rail--{style}">'
        f'<div class="rail__step"><b>{spec["step"]}</b><span>{spec["label"]}</span></div>'
        f'<div class="rail__chips">{"".join(chips)}</div>'
        f'<div class="rail__note"><b></b>{spec["note"]}</div>'
        f'{spec["sign"]}'
        f"</aside>"
    )


# نامک اسکرین → مسیر صفحه در اپ (توکن‌دارها بعداً پر می‌شوند)
SCREEN_URLS: Dict[str, Optional[str]] = {
    "start": "/",
    "intent": "/journey/intent",
    "hafez": None,
    "tarot": None,
    "dice": None,
    "methods": "/journey",
    "life": "/life",
    "tests": "/tests",
    "history": "/readings",
    "result": None,
}


# --------------------------------------------------------------------------- #
# سرور آینه: /static به پوشهٔ اپ وصل می‌شود تا صفحاتِ ذخیره‌شده مثل خود اپ
# (با همان CSS، همان فونت‌ها و بدون مشکل CORS) رندر شوند.
# --------------------------------------------------------------------------- #
class MirrorHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:  # noqa: D102
        clean = urllib.parse.urlsplit(path).path
        if clean.startswith("/static/"):
            return str(ROOT / "app" / "static" / clean[len("/static/") :])
        return str(ROOT / clean.lstrip("/"))

    def log_message(self, *args) -> None:  # noqa: D102
        pass


class Mirror(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def port_is_free(port: int) -> bool:
    """آیا چیزی روی این پورت گوش می‌دهد؟"""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.connect(("127.0.0.1", port))
        return False
    except OSError:
        return True
    finally:
        probe.close()


def free_port() -> int:
    probe = socketserver.TCPServer(("127.0.0.1", 0), MirrorHandler)
    try:
        return int(probe.server_address[1])
    finally:
        probe.server_close()


def start_mirror() -> Tuple[Mirror, int]:
    """سرور آینه را روی یک پورت آزاد بالا می‌آورد.

    نکتهٔ مهم: اگر پورت پیش‌فرض هنوز در دست یک اجرای قبلی باشد، ویندوز اجازهٔ
    bind دوباره می‌دهد و همان سرورِ قدیمی جواب می‌دهد؛ آن‌وقت CSS به ۴۰۴ می‌خورد
    و همهٔ اسکرین‌شات‌ها بی‌استایل و به‌هم‌ریخته در می‌آیند. پس اول پورت را
    امتحان می‌کنیم و اگر گرفته بود، یک پورت آزاد دیگر برمی‌داریم.
    """
    port = MIRROR_PORT
    if not port_is_free(port):
        port = free_port()
        print(f"  ! پورت {MIRROR_PORT} گرفته بود؛ سرور آینه روی پورت {port} بالا می‌آید.")
    server = Mirror(("127.0.0.1", port), MirrorHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def check_mirror(port: int) -> None:
    """قبل از عکس‌گرفتن مطمئن می‌شویم سرور آینه دارایی‌های اپ را درست می‌دهد.

    بدون CSS، صفحات خام و لبه‌بریده رندر می‌شوند و تصاویر فروشگاه بی‌ارزش
    می‌شوند؛ پس این شکست را همان اول و با پیام روشن نشان می‌دهیم.
    """
    assets = ("/static/css/app.css", "/static/vendor/fontawesome/css/all.min.css")
    for path in assets:
        url = f"http://127.0.0.1:{port}{path}"
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                size = len(response.read())
                status = response.status
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(
                f"سرور آینه {path} را نداد ({exc}).\n"
                f"پورت {port} را آزاد کن (یا اجرای قبلی را ببند) و دوباره اجرا کن."
            ) from exc
        if status != 200 or size < 1000:
            raise SystemExit(
                f"سرور آینه {path} را ناقص داد ({status}، {size} بایت)؛ "
                "احتمالاً یک اجرای قبلی روی همین پورت مانده است."
            )


# --------------------------------------------------------------------------- #
# کروم
# --------------------------------------------------------------------------- #
CHROME_CANDIDATES = (
    os.environ.get("NESHANE_CHROME", ""),
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)


def find_chrome() -> str:
    for candidate in CHROME_CANDIDATES:
        if candidate and pathlib.Path(candidate).is_file():
            return candidate
    raise SystemExit(
        "کروم پیدا نشد. مسیرش را با NESHANE_CHROME بده، مثل:\n"
        '  NESHANE_CHROME="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"'
    )


def shoot(chrome: str, url: str, out: pathlib.Path, width: int, height: int, scale: float) -> None:
    """یک صفحه را با کرومِ بی‌سر اسکرین‌شات می‌کند."""
    out.parent.mkdir(parents=True, exist_ok=True)
    command = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--hide-scrollbars",
        "--no-sandbox",
        "--disable-extensions",
        "--force-device-scale-factor=%s" % scale,
        "--window-size=%d,%d" % (width, height),
        "--virtual-time-budget=7000",
        "--screenshot=%s" % out,
        url,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if not out.is_file() or out.stat().st_size < 2000:
        raise SystemExit(f"اسکرین‌شات گرفته نشد: {out}\n{result.stdout}\n{result.stderr}")


# --------------------------------------------------------------------------- #
# گام ۱: کاربر نمایشی و دادهٔ نمونه
# --------------------------------------------------------------------------- #
def find_user(username: str) -> Optional[int]:
    from app import db

    row = db._execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    return int(row[0]) if row else None


def reset_demo(user_id: int) -> None:
    """خوانش‌ها و تلاش‌های قبلی کاربر نمایشی را پاک می‌کند تا تصاویر تکرارپذیر بمانند."""
    from app import db

    for table in ("readings", "test_attempts"):
        db._execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
    db._execute("DELETE FROM journey_state WHERE user_id = ?", (user_id,))
    db._execute("DELETE FROM events WHERE user_id = ?", (user_id,))


def prepare_user(client) -> int:
    """حساب نمایشی را وارد می‌کند، پروفایلش را کامل و داده‌اش را تازه می‌کند."""
    status, location, _ = st.ensure_account(client, DEMO["phone"], DEMO["username"], DEMO["password"])
    if status != 303:
        raise SystemExit(f"ورود کاربر نمایشی نشد: {status} {location}")

    if client.get("/welcome")[0] == 200:
        client.post(
            "/welcome",
            {"name": DEMO["name"], "family": DEMO["family"], "gender": DEMO["gender"]},
        )
    client.post(
        "/birth",
        {
            "jy": DEMO["jy"],
            "jm": DEMO["jm"],
            "jd": DEMO["jd"],
            "birth_time": DEMO["birth_time"],
            "city": DEMO["city"],
        },
    )
    user_id = find_user(DEMO["username"])
    if not user_id:
        raise SystemExit("کاربر نمایشی در دیتابیس پیدا نشد.")
    reset_demo(user_id)
    return user_id


def make_reading(client, method: str, topic: str, intent: str) -> str:
    """یک خوانش می‌سازد و توکنش را برمی‌گرداند."""
    client.post("/journey/method", {"method": method})
    client.post("/journey/topic", {"topic": topic})
    status, location, _ = client.post("/journey/intent", {"intent": intent})
    token = location.rsplit("/", 1)[-1].split("?")[0] if location else ""
    if status != 303 or not token:
        raise SystemExit(f"ساخت خوانش {method} نشد: {status} {location}")
    return token


# --------------------------------------------------------------------------- #
# گام ۲: گرفتن HTML صفحه‌ها
# --------------------------------------------------------------------------- #
def prefill(page: str, slug: str) -> str:
    """فرم‌های خالی را با یک نمونهٔ واقعی پر می‌کند.

    صفحهٔ نیت به‌صورت پیش‌فرض یک کادر خالی است؛ داخل عکس فروشگاه اما باید مثل
    یک استفادهٔ واقعی پر به نظر برسد، وگرنه نصف تصویر سفید می‌ماند.
    """
    if slug == "intent":
        page = re.sub(
            r'(<textarea[^>]*name="intent"[^>]*>)(.*?)(</textarea>)',
            lambda match: match.group(1) + INTENTS["hafez"] + match.group(3),
            page,
            count=1,
            flags=re.S,
        )
    return page


def capture_pages() -> Dict[str, str]:
    client = st.Client()
    prepare_user(client)

    make_reading(client, "hafez", "self", INTENTS["hafez"])
    tarot_token = make_reading(client, "tarot", "love", INTENTS["tarot"])
    dice_token = make_reading(client, "dice", "work", INTENTS["dice"])

    # یک تست کامل با پاسخ‌های متنوع تا صفحهٔ نتیجه پر و واقعی باشد
    status, location, _ = client.post("/tests/mbti/start", {})
    attempt = location.split("?a=", 1)[1] if "?a=" in location else ""
    result_url = ""
    for index in range(28):
        _status, location, _ = client.post(
            f"/tests/mbti/q/{index}", {"choice": str(index % 4), "a": attempt}
        )
        result_url = location or result_url
    if not result_url:
        raise SystemExit("صفحهٔ نتیجهٔ تست ساخته نشد.")

    urls = dict(SCREEN_URLS)
    urls["hafez"] = f"/r/{make_reading(client, 'hafez', 'self', INTENTS['hafez'])}"
    urls["tarot"] = f"/r/{tarot_token}"
    urls["dice"] = f"/r/{dice_token}"
    urls["result"] = result_url

    saved: Dict[str, str] = {}
    SHOTS_HTML.mkdir(parents=True, exist_ok=True)
    for slug, path in urls.items():
        if not path:
            continue
        status, _location, page = client.get(path)
        if status != 200 or len(page) < 500:
            raise SystemExit(f"صفحهٔ {slug} گرفته نشد ({status}) — {path}")
        (SHOTS_HTML / f"{slug}.html").write_text(prefill(page, slug), encoding="utf-8")
        saved[slug] = path
        print(f"  √ {slug:<9} {path}")
    return saved


# --------------------------------------------------------------------------- #
# گام ۳: بوم‌های تبلیغاتی
# --------------------------------------------------------------------------- #
FRAME_CSS = """
@font-face { font-family: "Pinar FD"; src: url("fonts/Pinar-FD-Regular.woff2") format("woff2"); font-weight: 400; }
@font-face { font-family: "Pinar FD"; src: url("fonts/Pinar-FD-SemiBold.woff2") format("woff2"); font-weight: 600; }
@font-face { font-family: "Pinar FD"; src: url("fonts/Pinar-FD-Bold.woff2") format("woff2"); font-weight: 700; }
@font-face { font-family: "YekanBakh FaNum"; src: url("fonts/YekanBakhFaNum-Bold.woff2") format("woff2"); font-weight: 700; }

* { box-sizing: border-box; margin: 0; padding: 0; }
html { width: 1080px; }
body {
  font-family: "Pinar FD", system-ui, sans-serif; direction: rtl; color: #12131a;
  background: #eeedea; -webkit-font-smoothing: antialiased;
}
.num { font-family: "YekanBakh FaNum", "Pinar FD", sans-serif; font-weight: 700; }

/* ---------------------------------------------------- بوم و بافت پس‌زمینه
   هر تصویر یک بافت مخصوص خودش دارد؛ همه کم‌رنگ‌اند تا متن روی‌شان خوانا بماند. */
.canvas {
  position: relative; width: 1080px; height: 1920px; overflow: hidden;
  background:
    radial-gradient(900px 660px at 88% -8%, var(--a-soft), transparent 66%),
    radial-gradient(760px 560px at 2% 104%, var(--b-soft), transparent 68%),
    linear-gradient(170deg, #f8f7ff 0%, #efeee9 52%, #e9f4f2 100%);
}
.canvas > * { position: absolute; }
.motif { inset: 0; pointer-events: none; }
.motif--dots {
  background-image: radial-gradient(var(--a-dot) 1.7px, transparent 1.8px);
  background-size: 40px 40px; opacity: 0.65;
  -webkit-mask-image: radial-gradient(720px 880px at 46% 56%, #000 18%, transparent 76%);
  mask-image: radial-gradient(720px 880px at 46% 56%, #000 18%, transparent 76%);
}
.motif--grid {
  background-image: linear-gradient(var(--a-dot) 1px, transparent 1px),
                    linear-gradient(90deg, var(--a-dot) 1px, transparent 1px);
  background-size: 84px 84px; opacity: 0.5;
  -webkit-mask-image: linear-gradient(160deg, #000 0%, transparent 62%);
  mask-image: linear-gradient(160deg, #000 0%, transparent 62%);
}
.motif--waves {
  background-image: repeating-radial-gradient(circle at 8% 102%, transparent 0 92px, var(--a-dot) 92px 95px);
  opacity: 0.62;
  -webkit-mask-image: linear-gradient(0deg, #000 6%, transparent 74%);
  mask-image: linear-gradient(0deg, #000 6%, transparent 74%);
}
.motif--orbit {
  background-image:
    radial-gradient(760px 760px at 96% 26%, transparent 0 74%, var(--a-dot) 74% 74.6%, transparent 74.6%),
    radial-gradient(1080px 1080px at 96% 26%, transparent 0 76%, var(--b-dot) 76% 76.4%, transparent 76.4%),
    radial-gradient(520px 520px at 6% 88%, transparent 0 70%, var(--a-dot) 70% 70.8%, transparent 70.8%);
  opacity: 0.9;
}
.motif--burst {
  background-image: repeating-conic-gradient(from 0deg at 84% -6%, var(--a-dot) 0 3deg, transparent 3deg 11deg);
  opacity: 0.45;
  -webkit-mask-image: radial-gradient(780px 720px at 84% -6%, #000 4%, transparent 72%);
  mask-image: radial-gradient(780px 720px at 84% -6%, #000 4%, transparent 72%);
}
.motif--mesh {
  background-image:
    repeating-linear-gradient(48deg, var(--a-dot) 0 1.5px, transparent 1.5px 62px),
    repeating-linear-gradient(-48deg, var(--b-dot) 0 1.5px, transparent 1.5px 62px);
  opacity: 0.45;
  -webkit-mask-image: linear-gradient(200deg, #000 0%, transparent 58%);
  mask-image: linear-gradient(200deg, #000 0%, transparent 58%);
}
.motif--blobs {
  background-image:
    radial-gradient(520px 460px at 6% 12%, var(--a-soft), transparent 70%),
    radial-gradient(620px 520px at 98% 62%, var(--b-soft), transparent 72%),
    radial-gradient(460px 420px at 30% 96%, var(--a-soft), transparent 70%);
}
.motif--sparkle {
  background-image:
    radial-gradient(var(--a-dot) 3px, transparent 3.4px),
    radial-gradient(var(--b-dot) 2.4px, transparent 2.8px);
  background-size: 220px 220px, 140px 140px;
  background-position: 40px 60px, 90px 130px;
  opacity: 0.8;
}
.motif--bars {
  background-image: repeating-linear-gradient(90deg, transparent 0 54px, var(--a-dot) 54px 60px);
  opacity: 0.5;
  -webkit-mask-image: linear-gradient(0deg, #000 4%, transparent 66%);
  mask-image: linear-gradient(0deg, #000 4%, transparent 66%);
}
.motif--arc {
  background-image:
    radial-gradient(880px 880px at 12% 104%, transparent 0 76%, var(--a-dot) 76% 76.5%, transparent 76.5%),
    radial-gradient(1240px 1240px at 12% 104%, transparent 0 78%, var(--b-dot) 78% 78.4%, transparent 78.4%);
  opacity: 0.9;
}

/* ---------------------------------------------------- سرصفحه و Tیتر */
.brand { top: 52px; right: 86px; display: flex; align-items: center; gap: 16px; z-index: 6; }
.brand__logo {
  width: 66px; height: 66px; border-radius: 20px; overflow: hidden; display: block;
  box-shadow: 0 14px 30px rgba(58, 42, 110, 0.26), inset 0 0 0 1px rgba(255, 255, 255, 0.6);
}
.brand img { width: 100%; height: 100%; display: block; border-radius: inherit; }
.brand b { font-size: 37px; font-weight: 700; letter-spacing: -0.4px; }
.kicker {
  top: 64px; left: 86px; max-width: 600px; font-size: 21px; color: #565c6d;
  background: rgba(255, 255, 255, 0.82); border: 1px solid var(--a-soft);
  border-radius: 999px; padding: 10px 20px;
}
.head { top: 140px; right: 86px; left: 86px; z-index: 6; }
.head h1 { font-size: 52px; font-weight: 700; line-height: 1.42; letter-spacing: -1.2px; max-width: 920px; }
.head h1 em { font-style: normal; color: var(--a); }
.head p { margin-top: 14px; font-size: 24px; line-height: 1.78; color: #5b6070; max-width: 880px; }
.tags { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }
.tag {
  display: inline-flex; align-items: center; padding: 9px 16px; border-radius: 999px;
  background: rgba(255, 255, 255, 0.86); border: 1px solid var(--a-soft);
  font-size: 19px; color: #4a4f60; box-shadow: 0 10px 20px rgba(24, 20, 46, 0.08);
}

/* ---------------------------------------------------- صحنهٔ سه‌بعدی */
.stage { inset: 0; perspective: 2400px; perspective-origin: 50% 40%; }
/* هالهٔ نرم پشت گوشی: قاب را از پس‌زمینه جدا می‌کند و عمق می‌سازد. */
.glow {
  top: 620px; left: calc(var(--phone-left) + (var(--phone-w) - 940px) / 2);
  width: 940px; height: 940px; border-radius: 50%; z-index: 1;
  background: radial-gradient(closest-side, var(--a-glow), transparent 76%);
  filter: blur(34px);
}
/* سایهٔ تماس روی «زمین»: گوشی را به کادر می‌چسباند. */
.ground {
  top: 1806px; left: calc(var(--phone-left) + (var(--phone-w) - 700px) / 2);
  width: 700px; height: 92px; border-radius: 50%; z-index: 2;
  background: radial-gradient(closest-side, rgba(38, 28, 76, 0.42), rgba(38, 28, 76, 0.14) 56%, transparent 78%);
  filter: blur(18px);
}

/* --- جعبهٔ سه‌بعدی گوشی --------------------------------------------------
   یک جعبهٔ واقعی: وجه جلو (قاب و صفحه)، وجه پشت، و نوارهای کناره در راستای
   عمق. با preserve-3d خودِ مرورگر عمق را می‌سازد، پس ضخامت گوشی واقعی است و
   لازم نیست چرخش را دستی جبران کنیم. */
.box {
  position: absolute; left: var(--phone-left); top: var(--phone-top);
  width: var(--phone-w); height: var(--phone-h);
  transform-style: preserve-3d; transform: var(--phone-tilt); z-index: 3;
}
.face { position: absolute; inset: 0; border-radius: var(--phone-r); }
.face--back {
  transform: translateZ(calc(var(--phone-d) / -2));
  background: linear-gradient(140deg, #383444 0%, #15131c 46%, #201e29 100%);
  box-shadow: 0 44px 78px rgba(18, 14, 38, 0.46);
}
.face--front {
  transform: translateZ(calc(var(--phone-d) / 2));
  padding: var(--phone-pad);
  background: linear-gradient(148deg, #7b7688 0%, #262430 14%, #100f16 46%, #37333f 80%, #7b7688 100%);
  box-shadow:
    inset 0 0 0 2px rgba(255, 255, 255, 0.22),
    inset 0 0 22px rgba(0, 0, 0, 0.55),
    0 26px 52px rgba(18, 14, 38, 0.30);
}
/* کناره‌ها: همان ضخامت بدنه، در صفحه‌ای عمود بر صفحهٔ نمایش */
.edge { background: linear-gradient(180deg, #7d7889, #2a2833 10%, #191820 48%, #3d3949 90%, #7d7889); position: absolute; }
.edge--right { top: 62px; bottom: 62px; right: calc(var(--phone-d) / -2); width: var(--phone-d); transform: rotateY(90deg); border-radius: 6px; }
.edge--left { top: 62px; bottom: 62px; left: calc(var(--phone-d) / -2); width: var(--phone-d); transform: rotateY(-90deg); border-radius: 6px; }
/* دکمه‌های کناری: روی همان صفحهٔ کناره و کمی بیرون‌آمده */
.key {
  position: absolute; width: var(--phone-d); border-radius: 5px;
  background: linear-gradient(180deg, #918c9e, #34313f 30%, #1b1a23 70%, #575365);
  box-shadow: 0 6px 12px rgba(0, 0, 0, 0.45);
}
.key--power { top: 286px; height: 112px; right: calc(var(--phone-d) / -2); transform: rotateY(90deg) translateZ(7px); }
.key--v1 { top: 214px; height: 68px; left: calc(var(--phone-d) / -2); transform: rotateY(-90deg) translateZ(7px); }
.key--v2 { top: 302px; height: 68px; left: calc(var(--phone-d) / -2); transform: rotateY(-90deg) translateZ(7px); }

.screen {
  position: relative; width: 100%; height: 100%; border-radius: var(--screen-r); overflow: hidden;
  background: #ffffff; display: flex; flex-direction: column;
  box-shadow: inset 0 0 0 2px rgba(0, 0, 0, 0.6);
}
.statusbar {
  /* نوار وضعیت در گوشی واقعی چپ‌به‌راست است: ساعت سمت چپ، آیکون‌ها سمت راست. */
  position: relative; direction: ltr;
  flex: none; height: var(--status-h); display: flex; align-items: center; justify-content: space-between;
  padding: 10px 34px 0 38px; background: #ffffff;
  font-family: "YekanBakh FaNum", "Pinar FD", sans-serif; font-size: 25px; font-weight: 700; color: #15161d;
}
.statusbar .icons { display: flex; align-items: center; gap: 10px; }
.statusbar svg { display: block; }
/* «جزیره»ی بالای صفحه — همان بریدگی کوچک گوشی‌های امروزی، داخل صفحه */
.island {
  position: absolute; top: 13px; left: 50%; margin-left: -64px; z-index: 5;
  width: 128px; height: 31px; border-radius: 999px; background: #0a0910;
}
.shot { flex: 1; overflow: hidden; background: #ffffff; }
.shot img { display: block; width: var(--screen-inner); height: var(--shot-h); }
.glare {
  position: absolute; inset: 0; z-index: 6; pointer-events: none; border-radius: inherit;
  background: linear-gradient(114deg, rgba(255, 255, 255, 0.30) 0%, rgba(255, 255, 255, 0.08) 17%, rgba(255, 255, 255, 0) 40%, rgba(255, 255, 255, 0) 74%, rgba(255, 255, 255, 0.17) 100%);
}

/* ---------------------------------------------------- ستون محتوای هر تصویر
   ستون در طرف مخالفِ گوشی می‌نشیند، پس هیچ کارتی روی صفحهٔ اپ نمی‌افتد.
   سه گروه با space-between پخش می‌شوند تا ستون هم خالی نماند. */
.rail {
  top: var(--rail-top); bottom: 40px; width: var(--rail-w);
  display: flex; flex-direction: column; justify-content: space-between; gap: 18px; z-index: 5;
}
.rail--right { right: var(--rail-margin); }
.rail--left { left: var(--rail-margin); }
/* رگهٔ نازک در سمتِ روبه‌روی گوشی: ستون را یکپارچه نشان می‌دهد و فاصلهٔ
   بین بلوک‌ها خالی به نظر نمی‌رسد. */
.rail::before {
  content: ""; position: absolute; top: 4px; bottom: 60px; width: 3px; border-radius: 3px;
  background: linear-gradient(var(--a-soft), var(--b-soft) 60%, transparent);
}
.rail--right::before { left: -26px; }
.rail--left::before { right: -26px; }
.rail__note {
  align-self: flex-start; display: inline-flex; align-items: center; gap: 10px;
  font-size: 19px; color: #5b6070; background: rgba(255, 255, 255, 0.72);
  border: 1px solid var(--a-soft); border-radius: 999px; padding: 10px 18px;
}
.rail__note b { display: block; width: 10px; height: 10px; border-radius: 50%; background: var(--a); }
.rail__step { display: flex; align-items: center; gap: 14px; }
.rail__step b {
  width: 78px; height: 78px; border-radius: 25px; background: var(--a); color: #fff;
  font-family: "YekanBakh FaNum", "Pinar FD", sans-serif; font-size: 34px; font-weight: 700;
  display: grid; place-items: center; box-shadow: 0 18px 34px var(--a-shadow);
}
.rail__step span { font-size: 26px; font-weight: 700; color: #3b3653; }
.rail__chips { display: grid; gap: 16px; }

.chip {
  display: flex; align-items: center; gap: 16px; padding: 19px 22px; border-radius: 26px;
  background: rgba(255, 255, 255, 0.94); border: 1px solid rgba(255, 255, 255, 0.96);
  box-shadow: 0 22px 44px rgba(24, 20, 46, 0.16);
}
.chip__i {
  flex: none; width: 56px; height: 56px; border-radius: 19px; display: grid; place-items: center;
  background: var(--a-soft); color: var(--a); font-size: 25px;
}
.chip__t { display: grid; gap: 3px; }
.chip__t b { font-size: 24px; font-weight: 700; letter-spacing: -0.3px; }
.chip__t small { font-size: 18px; color: #6f7482; }

/* سبک ستون: خط زمانی، شماره‌دار، قرص‌های جمع‌وجمع */
.rail--timeline .rail__chips { position: relative; padding-right: 26px; }
.rail--timeline .rail__chips::before {
  content: ""; position: absolute; right: 6px; top: 18px; bottom: 18px; width: 2px;
  background: linear-gradient(var(--a-dot), var(--b-dot));
}
.rail--timeline .chip { position: relative; }
.rail--timeline .chip::before {
  content: ""; position: absolute; right: -26px; top: 50%; margin-top: -7px;
  width: 14px; height: 14px; border-radius: 50%; background: var(--a);
  box-shadow: 0 0 0 5px var(--a-soft);
}
.rail--numbered .chip__i {
  background: var(--a); color: #fff; font-family: "YekanBakh FaNum", "Pinar FD", sans-serif;
  font-size: 26px; font-weight: 700;
}
.rail--pills .chip { padding: 12px 18px; border-radius: 999px; }
.rail--pills .chip__i { width: 44px; height: 44px; border-radius: 50%; font-size: 20px; }
.rail--pills .chip__t b { font-size: 22px; }

/* ---------------------------------------------------- بلوک‌های امضا */
.sign { width: 100%; }
.mini {
  border-radius: 26px; background: rgba(255, 255, 255, 0.94);
  border: 1px solid rgba(255, 255, 255, 0.96); box-shadow: 0 22px 44px rgba(24, 20, 46, 0.16);
  padding: 20px 22px;
}
.mini__t { font-size: 19px; color: #6f7482; margin-bottom: 14px; }
.brow { display: flex; justify-content: space-between; font-size: 20px; margin-bottom: 7px; }
.bar { height: 12px; border-radius: 999px; background: var(--a-soft); overflow: hidden; margin-bottom: 14px; }
.bar i { display: block; height: 100%; border-radius: 999px; background: linear-gradient(90deg, var(--a), var(--b)); }
.pills { display: flex; flex-wrap: wrap; gap: 10px; }
.pill {
  display: inline-flex; align-items: center; padding: 9px 17px; border-radius: 999px;
  background: rgba(255, 255, 255, 0.94); font-size: 19px; color: #3b3653;
  box-shadow: 0 12px 24px rgba(24, 20, 46, 0.12);
}
.fan { position: relative; height: 154px; }
.fan i {
  position: absolute; bottom: 0; width: 82px; height: 128px; border-radius: 14px;
  background: linear-gradient(160deg, var(--a), var(--b));
  box-shadow: 0 16px 30px rgba(24, 20, 46, 0.22), inset 0 0 0 3px rgba(255, 255, 255, 0.35);
}
.dice { display: flex; gap: 12px; }
.die {
  width: 78px; height: 78px; border-radius: 20px; background: #fff; display: grid; place-items: center;
  color: var(--a); font-size: 34px;
  box-shadow: 0 16px 30px rgba(24, 20, 46, 0.18), inset 0 0 0 1px var(--a-soft);
}
.bubble {
  position: relative; background: rgba(255, 255, 255, 0.96); border-radius: 26px;
  padding: 20px 22px; box-shadow: 0 22px 44px rgba(24, 20, 46, 0.16);
}
.bubble::after {
  content: ""; position: absolute; bottom: -14px; right: 44px; width: 0; height: 0;
  border-left: 16px solid transparent; border-right: 16px solid transparent;
  border-top: 16px solid rgba(255, 255, 255, 0.96);
}
.tl { display: grid; gap: 16px; }
.tl div { display: flex; align-items: center; gap: 12px; font-size: 20px; }
.tl div b { flex: none; width: 10px; height: 10px; border-radius: 50%; background: var(--a); box-shadow: 0 0 0 4px var(--a-soft); }
.stat { display: grid; gap: 4px; }
.stat b { font-family: "YekanBakh FaNum", "Pinar FD", sans-serif; font-size: 54px; font-weight: 700; color: var(--a); line-height: 1.1; }
.stat small { font-size: 19px; color: #6f7482; }
.orbit { position: relative; height: 268px; display: grid; place-items: center; }
.orbit span { position: absolute; border-radius: 50%; border: 2px solid var(--a-dot); }
.orbit img { width: 72px; height: 72px; border-radius: 22px; box-shadow: 0 14px 30px rgba(58, 42, 110, 0.3); }

/* ---------------------------------------------------- هندسه
   اندازه‌های ماکت از پایتون تزریق می‌شود تا یک منبعِ حقیقت بماند. */
:root {
{{GEOMETRY}}}
"""

FRAME_HTML = """<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8" />
<title>نشانه — تصاویر فروشگاه</title>
<link rel="stylesheet" href="/static/vendor/fontawesome/css/all.min.css" />
<style>{css}</style>
</head>
<body>
<div id="canvas"></div>
<script>
var FRAMES = {frames};
var params = new URLSearchParams(location.search);
var only = params.get("i");
var index = only ? Math.max(1, Math.min(FRAMES.length, parseInt(only, 10))) : null;
var items = index ? [FRAMES[index - 1]] : FRAMES;
var SIGNAL = '<svg width="22" height="16" viewBox="0 0 22 16" fill="currentColor"><rect x="0" y="10" width="4" height="6" rx="1.4"/><rect x="6" y="7" width="4" height="9" rx="1.4"/><rect x="12" y="4" width="4" height="12" rx="1.4"/><rect x="18" y="0" width="4" height="16" rx="1.4"/></svg>';
var WIFI = '<svg width="24" height="17" viewBox="0 0 24 17" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M1.6 5.6a15 15 0 0 1 20.8 0"/><path d="M5.8 9.6a9 9 0 0 1 12.4 0"/><circle cx="12" cy="13.6" r="1.7" fill="currentColor" stroke="none"/></svg>';
var BATTERY = '<svg width="34" height="17" viewBox="0 0 34 17"><rect x="0.8" y="0.8" width="27" height="15.4" rx="5" fill="none" stroke="currentColor" stroke-width="1.6" opacity="0.5"/><rect x="3.4" y="3.4" width="20" height="10.2" rx="2.6" fill="currentColor"/><path d="M31 5.4v6.2a3.4 3.4 0 0 0 0-6.2z" fill="currentColor" opacity="0.5"/></svg>';

var host = document.getElementById("canvas");
host.innerHTML = items.map(function (f) {{
  return '<section class="canvas" style="' + f.style + '">' +
    '<span class="motif ' + f.motif + '"></span>' +
    '<section class="brand"><span class="brand__logo"><img src="/static/icons/icon-192.png" alt="نشانه" /></span><b>نشانه</b></section>' +
    '<span class="kicker">' + f.kicker + '</span>' +
    '<div class="head"><h1>' + f.title + '</h1><p>' + f.sub + '</p>' +
      '<div class="tags">' + f.tags + '</div>' +
    '</div>' +
    '<div class="stage">' +
      '<span class="glow"></span><span class="ground"></span>' +
      '<div class="box">' +
        '<span class="edge edge--left"></span><span class="edge edge--right"></span>' +
        '<span class="key key--v1"></span><span class="key key--v2"></span><span class="key key--power"></span>' +
        '<span class="face face--back"></span>' +
        '<div class="face face--front">' +
          '<div class="screen">' +
            '<span class="island"></span>' +
            '<div class="statusbar"><span class="time">' + (f.time || "۹:۴۱") + '</span>' +
              '<span class="icons">' + SIGNAL + WIFI + BATTERY + '</span></div>' +
            '<div class="shot"><img src="shots/' + f.screen + '.png" alt="" /></div>' +
            '<span class="glare"></span>' +
          '</div>' +
        '</div>' +
      '</div>' +
    '</div>' +
    f.deco +
  '</section>';
}}).join("");
</script>
</body>
</html>
"""


def write_frames() -> None:
    frames = [
        {
            "screen": spec["screen"],
            "kicker": KICKER,
            "motif": spec["motif"],
            "style": frame_style(spec),
            "title": spec["title"],
            "sub": spec["sub"],
            "tags": "".join(f'<span class="tag">{tag}</span>' for tag in spec["tags"]),
            "deco": rail_html(spec),
            "time": "۹:۴۱",
        }
        for spec in FRAME_SPECS
    ]
    geometry = "".join(
        f"  {name}: {value}px;\n"
        for name, value in (
            ("--phone-w", PHONE_W),
            ("--phone-h", PHONE_H),
            ("--phone-pad", PHONE_PAD),
            ("--phone-top", PHONE_TOP),
            ("--phone-d", PHONE_DEPTH),
            ("--phone-r", PHONE_RADIUS),
            ("--status-h", STATUS_BAR_H),
            ("--shot-h", SHOT_H),
            ("--screen-inner", SCREEN_INNER),
            ("--screen-r", PHONE_RADIUS - PHONE_PAD),
            ("--rail-w", RAIL_W),
            ("--rail-margin", RAIL_MARGIN),
            ("--rail-top", RAIL_TOP),
        )
    )
    css = FRAME_CSS.replace("{{GEOMETRY}}", geometry)
    FRAME_PAGE.write_text(
        FRAME_HTML.format(css=css, frames=json.dumps(frames, ensure_ascii=False)),
        encoding="utf-8",
    )


def copy_fonts() -> None:
    FONTS.mkdir(parents=True, exist_ok=True)
    source = pathlib.Path(os.path.expanduser("~"))
    names = (
        "Pinar-FD-Regular.woff2",
        "Pinar-FD-SemiBold.woff2",
        "Pinar-FD-Bold.woff2",
        "YekanBakhFaNum-Bold.woff2",
    )
    for name in names:
        places = [source / name, ROOT / "app" / "static" / "fonts" / name]
        for place in places:
            if place.is_file():
                shutil.copy2(place, FONTS / name)
                break
        else:
            raise SystemExit(f"فونت {name} پیدا نشد (کنار پوشهٔ کاربر یا در app/static/fonts).")


# --------------------------------------------------------------------------- #
def main() -> int:
    parser = argparse.ArgumentParser(description="ساخت تصاویر فروشگاهی نشانه")
    parser.add_argument("--base", default="http://127.0.0.1:8020", help="آدرس سرور نشانه")
    parser.add_argument("--keep-html", action="store_true", help="HTML های گرفته‌شده پاک نشوند")
    args = parser.parse_args()
    st.BASE = args.base.rstrip("/")

    chrome = find_chrome()
    FRAMES.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    copy_fonts()

    print("== گرفتن صفحات واقعی اپ ==")
    saved = capture_pages()
    if not saved:
        return 1

    server, port = start_mirror()
    check_mirror(port)
    print(f"== اسکرین‌شات صفحات (سرور آینه روی {port}) ==")
    try:
        for slug in saved:
            url = f"http://127.0.0.1:{port}/marketing/shots/html/{slug}.html"
            out = SHOTS / f"{slug}.png"
            shoot(chrome, url, out, SCREEN_W, SCREEN_H, 2)
            print(f"  √ {out.relative_to(ROOT)}")

        write_frames()
        print("== ساخت بوم‌های تبلیغاتی (سه‌بعدی) ==")
        for index, spec in enumerate(FRAME_SPECS, start=1):
            url = f"http://127.0.0.1:{port}/marketing/frames.html?i={index}"
            out = FRAMES / f"{spec['name']}.png"
            shoot(chrome, url, out, CANVAS_W, CANVAS_H, 1)
            print(f"  √ {out.relative_to(ROOT)}")
    finally:
        server.shutdown()

    if not args.keep_html:
        shutil.rmtree(SHOTS_HTML, ignore_errors=True)

    print("")
    print("تمام شد ✅")
    print(f"  تصاویر نهایی: {FRAMES}")
    print(f"  متن فروشگاه:  {MARKETING / 'store-listing.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
