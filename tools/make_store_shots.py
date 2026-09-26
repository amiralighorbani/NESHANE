"""ساخت تصاویر فروشگاهی (مارکت‌پلیس) از صفحات واقعی «نشانه».

مسیر کار:
  ۱) یک کاربر نمایشی می‌سازد (با نام و شهر و تاریخ تولد واقعی‌نما).
  ۲) با نشست خودش چند «خوانش» (حافظ، تاروت، تاس) و یک تست کامل می‌سازد.
  ۳) HTML همان صفحات را از سرور زنده می‌گیرد و ذخیره می‌کند.
  ۴) با کرومِ بی‌سر از هر صفحه اسکرین‌شات ۳۹۰×۸۴۴ (نسبت ۲ برابر) می‌گیرد.
  ۵) هر اسکرین را داخل ماکت گوشی می‌گذارد و با تیترِ تبلیغاتی روی بومِ
     1080×1920 می‌نشاند → تصاویر آمادهٔ بارگذاری در مارکت‌پلیس.

اجرا:  python tools/make_store_shots.py            (سرور نشانه باید بالا باشد)
اگر کروم جای دیگری است:  NESHANE_CHROME="مسیر کروم" python tools/make_store_shots.py
"""

from __future__ import annotations

import argparse
import http.server
import os
import pathlib
import shutil
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
SCREEN_W, SCREEN_H = 390, 844

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

# (نامکِ تصویر، تیتر، زیرتیتر)
FRAME_COPY: List[Tuple[str, str, str]] = [
    (
        "01-start",
        "فالت را از دلِ نیتِ امروزت بگیر",
        "اول نیتت را می‌نویسی، بعد نشانه راهش را نشان می‌دهد. هفت روش، یک نیت.",
    ),
    (
        "02-hafez",
        "فال حافظ، با تفسیری که به نیت تو می‌خورد",
        "غزل را با کلیدواژه‌های نیتت می‌خوانیم و معنی‌اش را برای سؤال خودت می‌گوییم.",
    ),
    (
        "03-tarot",
        "تاروت سه‌کارتی؛ کارت‌ها واقعاً رو می‌شوند",
        "هر کارت با نام، جایگاه و راست یا برگشته بودنش نمایش داده می‌شود.",
    ),
    (
        "04-dice",
        "تاس‌های نمادین، با همان چشم‌ها",
        "سه تاس واقعی می‌افتند و هر عدد معنی، جهت و تفسیر خودش را دارد.",
    ),
    (
        "05-methods",
        "هفت روش فال، هر کدام با ابزارِ خودش",
        "حافظ، تاروت، تاس، رون، عدد، طالع و چینی — از هم قابل تشخیص و متفاوت.",
    ),
    (
        "06-intent",
        "یک جمله از نیتت، تفاوتِ فال را می‌سازد",
        "تفسیر روی همان چیزی سوار می‌شود که خودت نوشته‌ای، نه روی یک متن آماده.",
    ),
    (
        "07-life",
        "زندگی در عدد: نگاهی آماری به خودت",
        "از ریتم قلب و عددِ غذا تا الگوهای رفتاری — همه از تاریخ تولدِ خودت حساب می‌شود.",
    ),
    (
        "08-tests",
        "ده تستِ شخصیت، در یک جا",
        "MBTI، پنج عامل بزرگ، کهن‌الگوهای یونگ، انیاگرام، DISC، چاکرا و هوش‌های چندگانه.",
    ),
    (
        "09-question",
        "جواب‌هایت، نتیجه‌ات را می‌سازند",
        "هر گزینه وزن واقعی خودش را دارد و نتیجه با فرمول همان آزمون محاسبه می‌شود.",
    ),
    (
        "10-result",
        "نتیجهٔ دقیق، با نمرهٔ هر مؤلفه",
        "نمودار، تفسیر و قدمِ بعدی — همه بر اساس پاسخ‌های خودت.",
    ),
]

# نامکِ اسکرین → مسیر صفحه در اپ
SCREEN_URLS: Dict[str, str] = {
    "start": "/",
    "intent": "/journey/intent",
    "hafez": None,  # با توکن پر می‌شود
    "tarot": None,
    "dice": None,
    "methods": "/journey",
    "life": "/life",
    "tests": "/tests",
    "question": None,
    "result": None,
}

FRAME_SCREEN = {
    "01-start": "start",
    "02-hafez": "hafez",
    "03-tarot": "tarot",
    "04-dice": "dice",
    "05-methods": "methods",
    "06-intent": "intent",
    "07-life": "life",
    "08-tests": "tests",
    "09-question": "question",
    "10-result": "result",
}


# --------------------------------------------------------------------------- #
# سرور آینه: /static به پوشهٔ اپ وصل می‌شود تا صفحاتِ ذخیره‌شده مثل خود اپ
# (با همان CSS و همان فونت‌ها و بدون مشکل CORS) رندر شوند.
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


def start_mirror() -> Mirror:
    server = Mirror(("127.0.0.1", MIRROR_PORT), MirrorHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


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
        "کروم پیدا نشد. مسیرش را با NESHANE_CHROME بده، مثلاً:\n"
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


def prepare_user(client) -> Tuple[int, Dict[str, str]]:
    """حساب نمایشی را وارد می‌کند، پروفایلش را کامل و داده‌اش را تازه می‌کند."""
    status, location, _ = st.ensure_account(client, DEMO["phone"], DEMO["username"], DEMO["password"])
    if status != 303:
        raise SystemExit(f"ورود کاربر نمایشی نشد: {status} {location}")

    # نام/فامیل و تولد با مقدارهای خوانا (به‌جای «کاربر آزمون»).
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
    return user_id, {"name": DEMO["name"], "family": DEMO["family"], "city": DEMO["city"]}


def make_reading(client, method: str, topic: str, intent: str) -> str:
    """یک خوانش می‌سازد و توکنش را برمی‌گرداند."""
    client.post("/journey/method", {"method": method})
    client.post("/journey/topic", {"topic": topic})
    status, location, _ = client.post("/journey/intent", {"intent": intent})
    token = location.rsplit("/", 1)[-1].split("?")[0] if location else ""
    if status != 303 or not token:
        raise SystemExit(f"ساخت خوانش {method} نشد: {status} {location}")
    return token


def run_test(client, key: str, answers: int) -> str:
    """تست را با پاسخ‌های متنوع پر می‌کند؛ شناسهٔ نتیجه را برمی‌گرداند."""
    status, location, _ = client.post(f"/tests/{key}/start", {})
    attempt = ""
    if "?a=" in location:
        attempt = location.split("?a=", 1)[1]
    for index in range(answers):
        step = index % 4
        status, location, _ = client.post(
            f"/tests/{key}/q/{index}", {"choice": str(step), "a": attempt}
        )
    result_url = location or ""
    return result_url


# --------------------------------------------------------------------------- #
# گام ۲: گرفتن HTML صفحه‌ها
# --------------------------------------------------------------------------- #
def capture_pages(user_id: int) -> Dict[str, str]:
    client = st.Client()
    prepare_user(client)
    make_reading(client, "hafez", "self", INTENTS["hafez"])
    tarot_token = make_reading(client, "tarot", "love", INTENTS["tarot"])
    dice_token = make_reading(client, "dice", "work", INTENTS["dice"])

    # تست: صفحهٔ سؤال (تلاش نیمه‌کاره) و صفحهٔ نتیجه
    status, location, _ = client.post("/tests/greek/start", {})
    attempt = location.split("?a=", 1)[1] if "?a=" in location else ""
    question_url = f"/tests/greek/q/0" + (f"?a={attempt}" if attempt else "")
    client.get(question_url)
    result_url = ""
    for index in range(10):
        _s, location, _ = client.post(f"/tests/greek/q/{index}", {"choice": str(index % 4), "a": attempt})
        result_url = location or result_url
    if not result_url:
        raise SystemExit("صفحهٔ نتیجهٔ تست ساخته نشد.")

    urls = dict(SCREEN_URLS)
    urls["hafez"] = f"/r/{make_reading(client, 'hafez', 'self', INTENTS['hafez'])}"
    urls["tarot"] = f"/r/{tarot_token}"
    urls["dice"] = f"/r/{dice_token}"
    urls["question"] = question_url
    urls["result"] = result_url

    saved: Dict[str, str] = {}
    SHOTS_HTML.mkdir(parents=True, exist_ok=True)
    for slug, path in urls.items():
        if not path:
            continue
        status, _location, page = client.get(path)
        if status != 200 or len(page) < 500:
            raise SystemExit(f"صفحهٔ {slug} گرفته نشد ({status}) — {path}")
        target = SHOTS_HTML / f"{slug}.html"
        target.write_text(page, encoding="utf-8")
        saved[slug] = path
        print(f"  √ {slug:<10} {path}")
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
html, body { width: 1080px; height: 1920px; overflow: hidden; }
body {
  font-family: "Pinar FD", system-ui, sans-serif;
  direction: rtl;
  color: #131419;
  background: #f2f1f8;
}
.canvas {
  position: relative; width: 1080px; height: 1920px; overflow: hidden;
  background:
    radial-gradient(760px 560px at 92% -6%, rgba(107, 79, 187, 0.20), transparent 70%),
    radial-gradient(720px 520px at 4% 104%, rgba(47, 143, 168, 0.18), transparent 72%),
    linear-gradient(168deg, #f7f5ff 0%, #efeee9 52%, #e8f4f2 100%);
}
.brand { position: absolute; top: 74px; inset-inline-start: 88px; display: flex; align-items: center; gap: 16px; }
.brand img { width: 74px; height: 74px; border-radius: 22px; box-shadow: 0 14px 34px rgba(107, 79, 187, 0.28); }
.brand b { font-size: 40px; font-weight: 700; letter-spacing: -0.5px; }
.brand span { font-size: 24px; color: #5b6070; }

.head { position: absolute; top: 190px; inset-inline: 84px; }
.head h1 {
  font-size: 60px; font-weight: 700; line-height: 1.42; letter-spacing: -1.2px;
}
.head h1 em { font-style: normal; color: #6b4fbb; }
.head p { margin-top: 20px; font-size: 29px; line-height: 1.8; color: #5b6070; }

/* ماکت گوشی: کل ارتفاع صفحهٔ اپ جا می‌شود (نوار پایین اپ بریده نمی‌شود). */
.phone {
  position: absolute; top: 556px; inset-inline: 0; margin-inline: auto;
  width: 588px; height: 1244px;
  border-radius: 66px; padding: 14px;
  background: linear-gradient(160deg, #2a2735, #14131b 45%, #2f2b3d);
  box-shadow: 0 56px 110px rgba(24, 20, 46, 0.32), inset 0 0 0 2px rgba(255, 255, 255, 0.10);
}
.screen {
  position: relative; width: 100%; height: 100%; border-radius: 53px; overflow: hidden;
  background: #eeedea;
}
/* عرض ۵۶۰ = ۳۹۰ (عرض واقعی اپ) × ۱٫۴۳۶ → همان نسبت تصویر، بدون کشیدگی یا برش. */
.screen img { display: block; width: 560px; height: auto; }
.island {
  position: absolute; top: 22px; inset-inline: 0; margin-inline: auto;
  width: 146px; height: 30px; border-radius: 999px; background: #0e0d13; z-index: 3;
}
.chips {
  position: absolute; bottom: 46px; inset-inline: 84px;
  display: flex; gap: 14px; flex-wrap: wrap; justify-content: center;
}
.chip {
  font-size: 25px; font-weight: 600; color: #4b3f7d;
  background: rgba(107, 79, 187, 0.12); border-radius: 999px; padding: 14px 26px;
}
"""

FRAME_HTML = """<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8" />
<title>نشانه — تصاویر فروشگاه</title>
<style>{css}</style>
</head>
<body>
<div class="canvas" id="canvas"></div>
<script>
var FRAMES = {frames};
var params = new URLSearchParams(location.search);
var only = params.get("i");
var index = only ? Math.max(1, Math.min(FRAMES.length, parseInt(only, 10))) : null;
var items = index ? [FRAMES[index - 1]] : FRAMES;
var host = document.getElementById("canvas");
var html = items.map(function (f) {{
  return '' +
  '<section class="brand"><img src="/static/icons/icon-192.png" alt="نشانه" /><b>نشانه</b><span>' + (f.kicker || "") + '</span></section>' +
  '<div class="head"><h1>' + f.title + '</h1><p>' + f.sub + '</p></div>' +
  '<div class="phone"><div class="screen"><span class="island"></span><img src="shots/' + f.screen + '.png" alt="' + f.title.replace(/<[^>]+>/g, "") + '" /></div></div>' +
  '<div class="chips">' + (f.chips || []).map(function (c) {{ return '<span class="chip">' + c + '</span>'; }}).join("") + '</div>';
}}).join('');
host.innerHTML = html;
</script>
</body>
</html>
"""

KICKER = "فال، تست شخصیت و شناخت خودت"
CHIPS = {
    "01-start": ["فال با نیت", "هفت روش", "فارسی و راست‌به‌چپ"],
    "02-hafez": ["کلیدواژه‌های نیت", "معنی برای امروز", "بدون تکرار"],
    "03-tarot": ["سه کارت", "راست / برگشته", "جایگاه هر کارت"],
    "04-dice": ["سه تاس", "چشم‌های واقعی", "معنی هر عدد"],
    "05-methods": ["ابزار جدا برای هر فال", "نماد واقعی", "ظاهر متفاوت"],
    "06-intent": ["نیت کوتاه", "تفسیر شخصی", "بدون متن آماده"],
    "07-life": ["از تاریخ تولد", "کارت‌های آماری", "زبان ساده"],
    "08-tests": ["ده آزمون", "نمرهٔ هر مؤلفه", "نتیجهٔ قابل‌فهم"],
    "09-question": ["گزینه‌های خوانا", "وزن واقعی هر پاسخ", "روی موبایل روان"],
    "10-result": ["نمودار محورها", "تفسیر پاسخ‌ها", "قدم بعدی"],
}


def write_frames() -> None:
    frames = []
    for name, title, sub in FRAME_COPY:
        frames.append(
            {
                "title": title,
                "sub": sub,
                "screen": FRAME_SCREEN[name],
                "kicker": KICKER,
                "chips": CHIPS.get(name, []),
            }
        )
    import json

    FRAME_PAGE.write_text(
        FRAME_HTML.format(css=FRAME_CSS, frames=json.dumps(frames, ensure_ascii=False)),
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
    parser.add_argument("--keep-html", action="store_true", help="HTMLهای گرفته‌شده پاک نشوند")
    args = parser.parse_args()
    st.BASE = args.base.rstrip("/")

    chrome = find_chrome()
    FRAMES.mkdir(parents=True, exist_ok=True)
    SHOTS.mkdir(parents=True, exist_ok=True)
    copy_fonts()

    print("== گرفتن صفحات واقعی اپ ==")
    saved = capture_pages(0)
    if not saved:
        return 1

    server = start_mirror()
    print(f"== اسکرین‌شات صفحات (سرور آینه روی {MIRROR_PORT}) ==")
    try:
        for slug in saved:
            url = f"http://127.0.0.1:{MIRROR_PORT}/marketing/shots/html/{slug}.html"
            out = SHOTS / f"{slug}.png"
            shoot(chrome, url, out, SCREEN_W, SCREEN_H, 2)
            print(f"  √ {out.relative_to(ROOT)}")

        write_frames()
        print("== ساخت بوم‌های تبلیغاتی ==")
        for index, (name, _title, _sub) in enumerate(FRAME_COPY, start=1):
            url = f"http://127.0.0.1:{MIRROR_PORT}/marketing/frames.html?i={index}"
            out = FRAMES / f"{name}.png"
            shoot(chrome, url, out, CANVAS_W, CANVAS_H, 1)
            print(f"  √ {out.relative_to(ROOT)}")
    finally:
        server.shutdown()

    if not args.keep_html:
        shutil.rmtree(SHOTS_HTML, ignore_errors=True)

    print("\nتمام شد ✅")
    print(f"  تصاویر نهایی: {FRAMES}")
    print(f"  متن فروشگاه:  {MARKETING / 'store-listing.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
