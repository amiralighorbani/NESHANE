"""ساخت تصاویر فروشگاهی (مارکت‌پلیس) از صفحات واقعی «نشانه».

مسیر کار:
  ۱) یک کاربر نمایشی می‌سازد (با نام، شهر و تاریخ تولد واقعی‌نما).
  ۲) با نشست خودش چند «خوانش» (حافظ، تاروت، تاس) و یک تست کامل می‌سازد.
  ۳) HTML همان صفحات را از سرور زنده می‌گیرد و ذخیره می‌کند.
  ۴) با کرومِ بی‌سر از هر صفحه اسکرین‌شات ۳۹۰×۸۴۴ (نسبت ۲ برابر) می‌گیرد.
  ۵) هر اسکرین را داخل ماکت سه‌بعدی گوشی می‌گذارد — با نوار وضعیت، ضخامت
     بدنه، بازتاب شیشه و سایهٔ عمیق — و با تیتر تبلیغاتی روی بوم ۱۰۸۰×۱۹۲۰
     می‌نشاند.

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
PHONE_TOP = 396
PHONE_DEPTH = 28                                 # ضخامت بدنه در راستای عمق
PHONE_RADIUS = 74
SCREEN_INNER = PHONE_W - 2 * PHONE_PAD           # ۶۳۴
STATUS_BAR_H = 78
SHOT_H = round(SCREEN_INNER * 1688 / 780)        # همان نسبت اسکرین‌شات دوبرابر
PHONE_H = STATUS_BAR_H + SHOT_H + 2 * PHONE_PAD

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

# (نامک، تیتر، زیرتیتر، آیکون کارت شناور، متن کارت شناور، آیکون نشان گوشه)
FRAME_COPY: List[Tuple[str, str, str, str, str, str]] = [
    (
        "01-start",
        "فالت را از دلِ نیتِ <em>امروزت</em> بگیر",
        "اول نیتت را می‌نویسی، بعد نشانه راهش را نشان می‌دهد. هفت روش، یک نیت.",
        "fa-wand-magic-sparkles",
        "هفت روش فال",
        "fa-star",
    ),
    (
        "02-hafez",
        "فال حافظ، با همهٔ <em>غزل</em> و تفسیر امروزت",
        "غزل را با کلیدواژه‌های نیتت می‌خوانیم و معنی‌اش را برای خودت می‌گوییم.",
        "fa-book-open-reader",
        "تفسیر روی نیت تو",
        "fa-feather-pointed",
    ),
    (
        "03-tarot",
        "کارت‌های تاروت <em>واقعاً</em> رو می‌شوند",
        "سه کارت با نام، جایگاه و راست یا برگشته بودن — هر فال شکل خودش را دارد.",
        "fa-clone",
        "سه کارت نمادین",
        "fa-hand-sparkles",
    ),
    (
        "04-dice",
        "تاس‌های نمادین، با همان <em>چشم‌ها</em>",
        "سه تاس واقعی می‌افتند و هر عدد معنی، جهت و تفسیر خودش را دارد.",
        "fa-dice",
        "سه تاس و معنی هر عدد",
        "fa-dice-five",
    ),
    (
        "05-methods",
        "هفت روش فال، هر کدام با <em>ابزار خودش</em>",
        "حافظ، تاروت، تاس، رون، عدد، طالع و چینی — از هم قابل تشخیص و متفاوت.",
        "fa-shapes",
        "ابزار جدا برای هر فال",
        "fa-layer-group",
    ),
    (
        "06-intent",
        "یک جمله از نیتت، <em>تفاوت</em> فال را می‌سازد",
        "تفسیر روی همان چیزی سوار می‌شود که خودت نوشته‌ای، نه روی یک متن آماده.",
        "fa-feather-pointed",
        "تفسیر شخصی‌سازی‌شده",
        "fa-quote-right",
    ),
    (
        "07-life",
        "<em>زندگی در عدد</em>؛ نگاهی آماری به خودت",
        "از ریتم قلب و عددِ غذا تا الگوهای رفتاری — همه از تولدِ خودت حساب می‌شود.",
        "fa-chart-simple",
        "بیش از ۵۰ کارت آماری",
        "fa-infinity",
    ),
    (
        "08-tests",
        "ده تستِ شخصیت، <em>در یک جا</em>",
        "MBTI، پنج عامل بزرگ، کهن‌الگوهای یونگ، انیاگرام، DISC، چاکرا و بیشتر.",
        "fa-brain",
        "ده آزمون معتبر",
        "fa-chart-pie",
    ),
    (
        "09-history",
        "همهٔ خوانش‌ها و نتیجه‌ها، <em>در پروندهٔ تو</em>",
        "هر فال و هر تست ذخیره می‌شود تا بعداً برگردی، مقایسه کنی و پرونده‌ات را ببینی.",
        "fa-clock-rotate-left",
        "تاریخچهٔ کامل",
        "fa-bookmark",
    ),
    (
        "10-result",
        "نتیجهٔ دقیق، با <em>نمرهٔ هر مؤلفه</em>",
        "نمودار محورها، تفسیر پاسخ‌ها و قدمِ بعدی — همه بر اساس جواب‌های خودت.",
        "fa-chart-column",
        "نمرهٔ هر مؤلفه",
        "fa-award",
    ),
]

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

FRAME_SCREEN = {
    "01-start": "start",
    "02-hafez": "hafez",
    "03-tarot": "tarot",
    "04-dice": "dice",
    "05-methods": "methods",
    "06-intent": "intent",
    "07-life": "life",
    "08-tests": "tests",
    "09-history": "history",
    "10-result": "result",
}

KICKER = "فال و تست شخصیت، فارسی و راست‌به‌چپ"


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
html, body { width: 1080px; height: 1920px; overflow: hidden; }
body {
  font-family: "Pinar FD", system-ui, sans-serif; direction: rtl; color: #12131a;
  background: #eeedea; -webkit-font-smoothing: antialiased;
}

/* ---------------------------------------------------- بوم و پس‌زمینه */
.canvas {
  position: relative; width: 1080px; height: 1920px; overflow: hidden;
  background:
    radial-gradient(880px 640px at 90% -12%, rgba(107, 79, 187, 0.36), transparent 66%),
    radial-gradient(780px 560px at 2% 106%, rgba(47, 143, 168, 0.34), transparent 68%),
    radial-gradient(620px 520px at 104% 42%, rgba(47, 143, 168, 0.20), transparent 70%),
    radial-gradient(720px 560px at 54% 40%, rgba(255, 255, 255, 0.94), transparent 74%),
    linear-gradient(170deg, #f7f5ff 0%, #efeee9 54%, #e8f3f1 100%);
}
.dots {
  position: absolute; inset: 0; opacity: 0.62;
  background-image: radial-gradient(rgba(107, 79, 187, 0.26) 1.6px, transparent 1.6px);
  background-size: 38px 38px;
  -webkit-mask-image: radial-gradient(820px 940px at 50% 60%, #000 20%, transparent 78%);
  mask-image: radial-gradient(820px 940px at 50% 60%, #000 20%, transparent 78%);
}
.rings { position: absolute; width: 1120px; height: 1120px; border-radius: 50%; left: -300px; top: 250px; }
.rings i { position: absolute; inset: 0; border-radius: 50%; border: 2px solid rgba(107, 79, 187, 0.32); }
.rings i:nth-child(2) { inset: 140px; border-color: rgba(47, 143, 168, 0.30); }
.rings i:nth-child(3) { inset: 280px; border-color: rgba(107, 79, 187, 0.22); }

/* ---------------------------------------------------- سرصفحه و متن */
.brand { position: absolute; top: 64px; inset-inline-start: 84px; display: flex; align-items: center; gap: 18px; }
.brand img { width: 70px; height: 70px; border-radius: 21px; box-shadow: 0 16px 32px rgba(58, 42, 110, 0.30); }
.brand b { font-size: 38px; font-weight: 700; letter-spacing: -0.4px; }
.head { position: absolute; top: 154px; inset-inline: 84px; }
.head h1 { font-size: 55px; font-weight: 700; line-height: 1.42; letter-spacing: -1.3px; }
.head h1 em { font-style: normal; color: #6b4fbb; }
.head p { margin-top: 16px; font-size: 26px; line-height: 1.8; color: #5b6070; }

/* ---------------------------------------------------- صحنهٔ سه‌بعدی */
.stage { position: absolute; inset: 0; perspective: 2100px; perspective-origin: 50% 46%; }

/* هالهٔ نرم پشت گوشی: قاب را از پس‌زمینه جدا می‌کند و عمق می‌سازد */
.glow {
  position: absolute; top: 560px; left: 50%; margin-left: -440px;
  width: 880px; height: 820px; border-radius: 50%;
  background: radial-gradient(closest-side, rgba(107, 79, 187, 0.30), rgba(47, 143, 168, 0.14) 58%, transparent 76%);
  filter: blur(30px);
}
/* سایهٔ تماس روی «زمین»: گوشی را به کادر می‌چسباند */
.ground {
  position: absolute; left: 50%; margin-left: -320px; top: 1778px;
  width: 640px; height: 88px; border-radius: 50%;
  background: radial-gradient(closest-side, rgba(38, 28, 76, 0.38), rgba(38, 28, 76, 0.14) 56%, transparent 78%);
  filter: blur(18px);
}

/* --- جعبهٔ سه‌بعدی گوشی --------------------------------------------------
   یک جعبهٔ واقعی: وجه جلو (قاب و صفحه)، وجه پشت، و نوارهای کناره در راستای
   عمق. با preserve-3d خودِ مرورگر عمق را می‌سازد، پس ضخامت گوشی واقعی است و
   لازم نیست چرخش را دستی جبران کنیم. */
.box {
  position: absolute; inset-inline: 0; margin-inline: auto; top: var(--phone-top);
  width: var(--phone-w); height: var(--phone-h);
  transform-style: preserve-3d;
  transform: translateX(-10px) rotateX(5deg) rotateY(-13deg) rotateZ(-1.5deg);
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

/* کارت‌های شناور: عمق را باورپذیر می‌کنند. جای هر دو طوری انتخاب شده که
   از کنارِ گوشی بیرون بزنند، نه روی محتوای صفحهٔ اپ. */
.float {
  position: absolute; display: flex; align-items: center; gap: 15px;
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.92); border: 1px solid rgba(255, 255, 255, 0.94);
  box-shadow: 0 28px 56px rgba(22, 18, 44, 0.24);
}
.float--card {
  top: 1688px; inset-inline-start: 56px; width: 372px; padding: 22px 28px;
  transform: translateZ(120px) rotateZ(3deg);
}
.float--badge {
  top: 430px; inset-inline-end: 150px; width: 112px; height: 112px; padding: 0;
  justify-content: center; border-radius: 34px; transform: translateZ(96px) rotateZ(-7deg);
  background: linear-gradient(150deg, #7b5ecb, #5b3fa6); color: #fff; border: 0;
  box-shadow: 0 24px 46px rgba(64, 44, 130, 0.40);
}
.float__icon {
  flex: none; width: 54px; height: 54px; border-radius: 18px; display: grid; place-items: center;
  background: rgba(107, 79, 187, 0.12); color: #6b4fbb; font-size: 24px;
}
.float--badge i { font-size: 41px; }
.float__text { display: grid; gap: 3px; }
.float__text b { font-size: 25px; font-weight: 700; letter-spacing: -0.3px; }
.float__text small { font-size: 19px; color: #6f7482; }

/* ---------------------------------------------------- هندسه و سرصفحه
   اندازه‌های ماکت از پایتون تزریق می‌شود تا یک منبعِ حقیقت بماند. */
:root {
{{GEOMETRY}}}
/* نشان و شعار دو عنصر جدا هستند تا هیچ‌وقت روی هم نیفتند. */
.brand { position: absolute; top: 54px; inset-inline-start: 86px; display: flex; align-items: center; gap: 16px; }
.brand__logo {
  width: 66px; height: 66px; border-radius: 20px; overflow: hidden; display: block;
  box-shadow: 0 14px 30px rgba(58, 42, 110, 0.26), inset 0 0 0 1px rgba(255, 255, 255, 0.6);
}
.brand img { width: 100%; height: 100%; border-radius: inherit; box-shadow: none; }
.brand b { font-size: 37px; font-weight: 700; letter-spacing: -0.4px; }
.kicker {
  position: absolute; top: 66px; inset-inline-end: 86px; max-width: 600px;
  font-size: 21px; color: #565c6d; background: rgba(255, 255, 255, 0.80);
  border: 1px solid rgba(107, 79, 187, 0.16); border-radius: 999px; padding: 10px 20px;
  box-shadow: 0 10px 22px rgba(58, 42, 110, 0.10);
}
.head { position: absolute; top: 128px; inset-inline: 86px; }
.head h1 { font-size: 52px; font-weight: 700; line-height: 1.42; letter-spacing: -1.2px; }
.head h1 em { font-style: normal; color: #6b4fbb; }
.head p { margin-top: 16px; font-size: 24px; line-height: 1.78; color: #5b6070; max-width: 900px; }
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
<div class="canvas" id="canvas"></div>
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
  var title = f.title;
  var alt = title.replace(/<[^>]+>/g, "");
  return '' +
  '<span class="dots"></span><span class="rings"><i></i><i></i><i></i></span>' +
  '<section class="brand"><span class="brand__logo"><img src="/static/icons/icon-192.png" alt="نشانه" /></span><b>نشانه</b></section>' +
  '<span class="kicker">' + (f.kicker || "") + '</span>' +
  '<div class="head"><h1>' + title + '</h1><p>' + f.sub + '</p></div>' +
  '<div class="stage">' +
    '<span class="glow"></span>' +
    '<span class="ground"></span>' +
    '<div class="box">' +
      '<span class="edge edge--left"></span><span class="edge edge--right"></span>' +
      '<span class="key key--v1"></span><span class="key key--v2"></span><span class="key key--power"></span>' +
      '<span class="face face--back"></span>' +
      '<div class="face face--front">' +
        '<div class="screen">' +
          '<span class="island"></span>' +
          '<div class="statusbar"><span class="time">' + (f.time || "۹:۴۱") + '</span>' +
            '<span class="icons">' + SIGNAL + WIFI + BATTERY + '</span></div>' +
          '<div class="shot"><img src="shots/' + f.screen + '.png" alt="' + alt + '" /></div>' +
          '<span class="glare"></span>' +
        '</div>' +
      '</div>' +
    '</div>' +
    '<div class="float float--card"><span class="float__icon"><i class="fa-solid ' + f.floatIcon + '"></i></span>' +
      '<span class="float__text"><b>' + f.floatText + '</b><small>در اپ نشانه</small></span></div>' +
    '<div class="float float--badge"><i class="fa-solid ' + f.badgeIcon + '"></i></div>' +
  '</div>';
}}).join('');
</script>
</body>
</html>
"""


def write_frames() -> None:
    frames = []
    for name, title, sub, float_icon, float_text, badge_icon in FRAME_COPY:
        frames.append(
            {
                "title": title,
                "sub": sub,
                "screen": FRAME_SCREEN[name],
                "kicker": KICKER,
                "floatIcon": float_icon,
                "floatText": float_text,
                "badgeIcon": badge_icon,
                "time": "۹:۴۱",
            }
        )
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
        for index, (name, _title, _sub, _fi, _ft, _bi) in enumerate(FRAME_COPY, start=1):
            url = f"http://127.0.0.1:{port}/marketing/frames.html?i={index}"
            out = FRAMES / f"{name}.png"
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
