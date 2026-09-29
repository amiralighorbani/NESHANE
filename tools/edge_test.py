"""آزمون لبه‌ها (Edge Test) نشانه.

این فایل مسیرهای برنامه را با **ورودی‌های خراب و تهاجمی** می‌زند تا ببیند هیچ‌کدام
به خطای ۵۰۰ (ترکیدن سرور) نمی‌رسند. هدف: هر ورودی نامعتبر باید با یک پیام روشن و
صفحهٔ سالم رد شود، نه با Traceback.

اجرا (سرور باید بالا باشد):

    python tools/edge_test.py [base_url]

خروجی: برای هر مورد یک خط. «OK» یعنی ورودی به‌شکل آبرومند رد شده، «CRASH» یعنی
سرور ۵۰۰ داده یا صفحهٔ خطا برگشته، «نیز» یعنی نکته‌ای که ارزش دیدن دارد.
"""

from __future__ import annotations

import http.cookiejar
import random
import re
import sys
import uuid
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# import کردن `app` خودش فایل `.env` را می‌خواند؛ مسیر مخفی و رمز مدیر از آنجا می‌آید
# و در سورس هیچ‌کدام هاردکد نیست.
import os  # noqa: E402

from app import admin_auth as _admin_auth  # noqa: E402

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8020").rstrip("/")

ADMIN_USER = os.environ.get("NESHANE_ADMIN_USER", "").strip()
ADMIN_PASSWORD = os.environ.get("NESHANE_ADMIN_PASSWORD", "").strip()
ADMIN_PATH = _admin_auth.ADMIN_PATH

if not ADMIN_USER or not ADMIN_PASSWORD:
    print(
        "[!] رمز پنل ادمین تنظیم نشده است (فایل .env را بساز یا متغیر محیطی بده).\n"
        "    آزمون بدون ورود به پنل ادامه می‌دهد؛ بخش پنل رد می‌شود."
    )

FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"

# هر اجرا شماره‌ها و نام‌های تازه می‌سازد تا آزمون تکرارشدنی باشد و دیتابیس شلوغ نشود.
RUN = str(random.randint(1000, 9999))
USERNAME = "edge_taken_" + RUN


def phone_for(seed: int) -> str:
    return f"0912{seed:03d}{RUN}"

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass



# نشانه‌های «ترکیدن» در بدنهٔ پاسخ.
CRASH_MARKERS = ("Traceback (most recent call last)", "Internal Server Error", "sqlite3.OperationalError")

crashes: List[str] = []
notes: List[str] = []
checks = 0


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


class Client:
    def __init__(self) -> None:
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar), NoRedirect()
        )

    def request(
        self, method: str, path: str, data: Optional[Dict[str, Any]] = None, raw: Optional[str] = None
    ) -> Tuple[int, str, str]:
        url = path if path.startswith("http") else BASE + path
        body: Optional[bytes] = None
        headers: Dict[str, str] = {}
        if raw is not None:
            body = raw.encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif data is not None:
            body = urllib.parse.urlencode(data, doseq=True).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        request = urllib.request.Request(url, data=body, method=method)
        for key, value in headers.items():
            request.add_header(key, value)
        try:
            with self.opener.open(request, timeout=30) as response:
                return response.status, response.headers.get("Location", ""), response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            return error.code, error.headers.get("Location", ""), error.read().decode("utf-8", "replace")

    def get(self, path: str) -> Tuple[int, str, str]:
        return self.request("GET", path)

    def post(self, path: str, data: Optional[Dict[str, Any]] = None) -> Tuple[int, str, str]:
        return self.request("POST", path, data if data is not None else {})


def record(label: str, status: int, body: str, expect: str = "no-crash") -> None:
    """expect: no-crash | 200 | 3xx | 4xx | any"""
    global checks
    checks += 1
    crashed = status >= 500 or any(marker in body for marker in CRASH_MARKERS)
    if expect == "200":
        ok = status == 200 and not crashed
    elif expect == "3xx":
        ok = 300 <= status < 400 and not crashed
    elif expect == "4xx":
        ok = 400 <= status < 500 and not crashed
    else:
        ok = not crashed
    if not ok:
        crashes.append(label)
        head = " ".join(body.split())[:160]
        print(f"[CRASH] {label} — وضعیت {status} :: {head}")
    else:
        print(f"[OK ] {label} — {status}")
    return None


def note(label: str) -> None:
    notes.append(label)
    print(f"[نیز] {label}")


def to_ascii_digits(value: str) -> str:
    for index, digit in enumerate(FA_DIGITS):
        value = value.replace(digit, str(index))
    return value


def otp_from_page(html: str) -> str:
    match = re.search(r'کد فعال:\s*<b class="ltr">([۰-۹0-9]+)</b>', html)
    return to_ascii_digits(match.group(1)) if match else ""


def register(client: Client, phone: str) -> bool:
    client.get("/logout")
    status, location, _ = client.post("/register", {"phone": phone})
    if status != 303:
        return False
    status, _, page = client.get("/verify")
    code = otp_from_page(page)
    if not code:
        return False
    status, location, _ = client.post("/verify", {"code": code})
    return status == 303


# --------------------------------------------------------------------------- #
# ۱. ثبت‌نام، تأیید شماره و انتخاب نام کاربری
# --------------------------------------------------------------------------- #


def case_register() -> None:
    print("\n— ثبت‌نام و تأیید —")
    fresh = Client()
    fresh.get("/logout")

    status, _, body = fresh.post("/register", {"phone": ""})
    record("ثبت‌نام با شمارهٔ خالی", status, body)
    for label, phone in [
        ("شمارهٔ کوتاه", "0912"),
        ("شمارهٔ بلند", "0" * 60),
        ("شماره با حرف", "09abc123456"),
        ("شمارهٔ تکراری‌شماره‌های صفر", "0000000000"),
        ("شمارهٔ با فاصله", "0912 345 6789"),
        ("شمارهٔ با کاراکتر کنترل", "0912\t345\n678"),
        ("شمارهٔ خارج از قالب", "+989121234567"),
        ("شمارهٔ فارسی", "۰۹۱۲۱۲۳۴۵۶۷"),
    ]:
        status, _, body = fresh.post("/register", {"phone": phone})
        record(f"ثبت‌نام {label}", status, body)

    # تأیید کد با انواع ورودی خراب
    attacker = Client()
    attacker.get("/logout")
    attacker.post("/register", {"phone": phone_for(1)})
    for label, code in [
        ("کد خالی", ""),
        ("کد کوتاه", "12"),
        ("کد غلط شش‌رقمی", "999999"),
        ("کد با حرف", "abcdef"),
        ("کد خیلی بلند", "9" * 500),
        ("کد با کاراکتر خاص", "<script>alert(1)</script>"),
    ]:
        status, _, body = attacker.post("/verify", {"code": code})
        record(f"تأیید {label}", status, body)

    # تأیید بدون ثبت‌نام قبلی
    ghost = Client()
    ghost.get("/logout")
    status, _, body = ghost.post("/verify", {"code": "123456"})
    record("تأیید بدون ثبت‌نام", status, body)


def case_username(primary: Client) -> None:
    print("\n— نام کاربری و رمز —")
    # بدون ورود
    anon = Client()
    anon.get("/logout")
    status, _, body = anon.post("/signup", {"username": "x", "password": "Abcd1234!", "confirm": "Abcd1234!"})
    record("انتخاب نام کاربری بدون ورود", status, body, expect="3xx")

    other = Client()
    if not register(other, phone_for(2)):
        note("ثبت‌نام کاربر دوم انجام نشد")
        return

    taken = USERNAME
    status, _, body = other.post("/signup", {"username": taken, "password": "EdgeTest!234", "confirm": "EdgeTest!234"})
    record("اولین انتخاب نام کاربری", status, body, expect="3xx")

    second = Client()
    if register(second, phone_for(3)):
        for label, username in [
            ("نام تکراریِ دقیق", taken),
            ("نام تکراری با حروف بزرگ", taken.upper()),
            ("نام تکراری با فاصلهٔ ابتدا/انتها", f"  {taken}  "),
        ]:
            status, _, body = second.post(
                "/signup", {"username": username, "password": "EdgeTest!234", "confirm": "EdgeTest!234"}
            )
            record(f"رد {label}", status, body, expect="4xx" if "تکراری" in label else "no-crash")

        for label, username in [
            ("نام با فاصلهٔ وسط", "edge user"),
            ("نام با ایموجی", "edge😀user"),
            ("نام با کوتیشن", 'edge"user'),
            ("نام شبیه SQL", "edge'; DROP TABLE users;--"),
            ("نام با کاراکتر کنترل", "edge\u0000user"),
            ("نام خیلی بلند", "e" * 5000),
            ("نام با اسلش", "../../etc/passwd"),
            ("نام با RTL override", "edge\u202euser"),
        ]:
            status, _, body = second.post(
                "/signup", {"username": username, "password": "EdgeTest!234", "confirm": "EdgeTest!234"}
            )
            record(f"نام کاربری {label}", status, body)

        for label, payload in [
            ("رمز ناهمخوان", {"username": "edge_ok_user", "password": "EdgeTest!234", "confirm": "Other!2345"}),
            ("رمز خالی", {"username": "edge_ok_user", "password": "", "confirm": ""}),
            ("رمز کوتاه", {"username": "edge_ok_user", "password": "1", "confirm": "1"}),
            ("رمز بسیار بلند", {"username": "edge_ok_user", "password": "A1!" * 9000, "confirm": "A1!" * 9000}),
            ("همهٔ فیلدها خالی", {"username": "", "password": "", "confirm": ""}),
            ("فیلدهای غایب", {}),
        ]:
            status, _, body = second.post("/signup", payload)
            record(f"ثبت‌نام با {label}", status, body)


def case_login(primary: Client) -> None:
    print("\n— ورود —")
    client = Client()
    for label, payload in [
        ("نام کاربری ناشناس", {"username": "no_such_user_xyz", "password": "Abcd1234!"}),
        ("رمز غلط", {"username": USERNAME, "password": "wrong-password"}),
        ("فیلدهای خالی", {"username": "", "password": ""}),
        ("فیلدهای غایب", {}),
        ("رشته‌های بسیار بلند", {"username": "x" * 4000, "password": "y" * 4000}),
        ("ورودی شبیه SQL", {"username": "' OR 1=1 --", "password": "' OR 1=1 --"}),
        ("ورودی با NULL", {"username": "a\u0000b", "password": "c\u0000d"}),
    ]:
        status, _, body = client.post("/login", payload)
        record(f"ورود با {label}", status, body)


# --------------------------------------------------------------------------- #
# ۲. مسیر کاربر (نام، تولد، سفر، فال)
# --------------------------------------------------------------------------- #


def make_ready_client(phone: str, username: str) -> Optional[Client]:
    """کاربری که ثبت‌نامش کامل است و وارد شده."""
    client = Client()
    if not register(client, phone):
        # ممکن است حساب کامل باشد؛ با نام کاربری وارد شو
        status, location, _ = client.post("/login", {"username": username, "password": "EdgeTest!234"})
        if status not in (303, 302):
            return None
        return client
    status, _, _ = client.post("/signup", {"username": username, "password": "EdgeTest!234", "confirm": "EdgeTest!234"})
    if status not in (303, 302):
        return None
    return client


def case_onboarding() -> None:
    print("\n— نام، تولد، زندگی در عدد —")
    client = make_ready_client(phone_for(4), "edge_flow_" + RUN)
    if client is None:
        note("ساخت کاربر آزمون مسیر کامل نشد")
        return

    for label, payload in [
        ("نام خالی", {"name": "", "family": ""}),
        ("نام فقط فاصله", {"name": "   ", "family": "   "}),
        ("نام خیلی بلند", {"name": "ن" * 5000, "family": "ف" * 5000}),
        ("نام با تگ اسکریپت", {"name": "<script>alert(1)</script>", "family": "<img src=x onerror=alert(1)>"}),
        ("نام با ایموجی", {"name": "کاربر😀", "family": "تست🧪"}),
        ("نام با کاراکتر کنترل", {"name": "a\u0000b", "family": "c\nd"}),
        ("فیلدهای غایب", {}),
    ]:
        status, _, body = client.post("/welcome", payload)
        record(f"ثبت نام با {label}", status, body)

    for label, payload in [
        ("سال صفر", {"jy": "0", "jm": "1", "jd": "1", "birth_time": "12:00", "city": "تهران"}),
        ("سال آیندهٔ دور", {"jy": "1500", "jm": "1", "jd": "1", "birth_time": "12:00", "city": "تهران"}),
        ("ماه ۱۳", {"jy": "1370", "jm": "13", "jd": "1", "birth_time": "12:00", "city": "تهران"}),
        ("روز ۳۲", {"jy": "1370", "jm": "1", "jd": "32", "birth_time": "12:00", "city": "تهران"}),
        ("روز صفر", {"jy": "1370", "jm": "1", "jd": "0", "birth_time": "12:00", "city": "تهران"}),
        ("۳۱ اسفند غیرکبیسه", {"jy": "1370", "jm": "12", "jd": "31", "birth_time": "12:00", "city": "تهران"}),
        ("ماه منفی", {"jy": "1370", "jm": "-3", "jd": "1", "birth_time": "12:00", "city": "تهران"}),
        ("همه غیرعددی", {"jy": "abc", "jm": "def", "jd": "ghi", "birth_time": "??", "city": "تهران"}),
        ("ساعت ۲۵:۹۹", {"jy": "1370", "jm": "5", "jd": "5", "birth_time": "25:99", "city": "تهران"}),
        ("شهر خیلی بلند", {"jy": "1370", "jm": "5", "jd": "5", "birth_time": "12:00", "city": "ش" * 4000}),
        ("شهر با تگ", {"jy": "1370", "jm": "5", "jd": "5", "birth_time": "12:00", "city": "<script>x</script>"}),
        ("همهٔ فیلدها خالی", {"jy": "", "jm": "", "jd": "", "birth_time": "", "city": ""}),
        ("فیلدهای غایب", {}),
    ]:
        status, _, body = client.post("/birth", payload)
        record(f"تولد با {label}", status, body)

    status, _, body = client.get("/life")
    record("صفحهٔ زندگی در عدد", status, body, expect="200")
    status, _, body = client.get("/profile")
    record("صفحهٔ پروفایل", status, body, expect="200")


def case_journey() -> None:
    print("\n— سفر: روش، موضوع، نیت —")
    client = make_ready_client(phone_for(5), "edge_journey_" + RUN)
    if client is None:
        note("ساخت کاربر آزمون سفر نشد")
        return

    for path, payload, label in [
        ("/journey/method", {"method": ""}, "روش خالی"),
        ("/journey/method", {"method": "no_such_method"}, "روش ناشناس"),
        ("/journey/method", {"method": "<script>"}, "روش با تگ"),
        ("/journey/method", {"method": "hafez"}, "روش درست"),
        ("/journey/topic", {"topic": ""}, "موضوع خالی"),
        ("/journey/topic", {"topic": "no_such_topic"}, "موضوع ناشناس"),
        ("/journey/topic", {"topic": "love"}, "موضوع درست"),
        ("/journey/intent", {"intent": ""}, "نیت خالی"),
        ("/journey/intent", {"intent": "x" * 20000}, "نیت ۲۰ هزار کاراکتری"),
        ("/journey/intent", {"intent": "نیت با \"کوتیشن\" و \\ بک‌اسلش و {'json': true}"}, "نیت با کاراکترهای JSON"),
        ("/journey/intent", {"intent": "نیت\nبا\nخط‌های\nچندگانه"}, "نیت چندخطی"),
        ("/journey/intent", {"intent": "😀" * 500}, "نیت با ایموجی"),
        ("/journey/intent", {"intent": "a\u0000b"}, "نیت با NULL"),
        ("/journey/intent", {"intent": "\u202e" * 100}, "نیت با RTL override"),
        ("/journey/intent", {"intent": "سلام"}, "نیت درست"),
    ]:
        status, location, body = client.post(path, payload)
        record(f"سفر: {label}", status, body)

    # مسیر بدون انتخاب قبلی
    fresh = make_ready_client(phone_for(6), "edge_empty_journey_" + RUN)
    if fresh:
        status, _, body = fresh.get("/journey/topic")
        record("موضوع بدون انتخاب روش", status, body)
        status, _, body = fresh.get("/journey/intent")
        record("نیت بدون انتخاب موضوع", status, body)
        status, _, body = fresh.post("/journey/intent", {"intent": "نیت بی‌مقدمه"})
        record("فرستادن نیت بدون مراحل قبل", status, body)


def case_reading() -> None:
    print("\n— صفحهٔ فال و توکن‌های خراب —")
    client = make_ready_client(phone_for(7), "edge_reading_" + RUN)
    if client is None:
        note("ساخت کاربر آزمون فال نشد")
        return

    for label, token in [
        ("توکن ناشناس", "deadbeefdeadbeef"),
        ("توکن خالی", " "),
        ("توکن با اسلش", "%2e%2e%2f%2e%2e%2fetc"),
        ("توکن بسیار بلند", "a" * 5000),
        ("توکن با تگ", "%3Cscript%3E"),
        ("توکن با کاراکتر خاص", "'; DROP TABLE readings;--"),
        ("توکن با یونیکد", "%D8%B3%D9%84%D8%A7%D9%85"),
    ]:
        status, _, body = client.get(f"/r/{urllib.parse.quote(token, safe='')}")
        record(f"فال با {label}", status, body)

    # یک فال واقعی بساز و مسیرهای پیرامونش را بدقلق کن
    client.post("/journey/method", {"method": "tarot"})
    client.post("/journey/topic", {"topic": "love"})
    status, location, _ = client.post("/journey/intent", {"intent": "آیندهٔ رابطه‌ام چطور است؟"})
    token = location.rsplit("/", 1)[-1] if location else ""
    if token:
        status, _, body = client.get(f"/r/{token}")
        record("فال واقعی باز می‌شود", status, body, expect="200")
        status, _, body = client.post(f"/r/{token}/again", {})
        record("فال دوباره با همان توکن", status, body)
        status, _, body = client.post(f"/r/{token}/again", {})
        record("فال دوباره (بار سوم)", status, body)
    else:
        note("توکن فال ساخته نشد")

    status, _, body = client.get("/readings")
    record("فهرست فال‌ها", status, body, expect="200")
    status, _, body = client.get("/readings?page=99999")
    record("فهرست فال‌ها با شمارهٔ صفحهٔ بزرگ", status, body)
    status, _, body = client.get("/readings?page=abc")
    record("فهرست فال‌ها با صفحهٔ غیرعددی", status, body)


def case_tests() -> None:
    print("\n— تست‌های شخصیت —")
    client = make_ready_client(phone_for(8), "edge_tests_" + RUN)
    if client is None:
        note("ساخت کاربر آزمون تست نشد")
        return

    for key in ["no_such_test", "", "../../etc/passwd", "<script>", "mbti"]:
        status, _, body = client.get(f"/tests/{urllib.parse.quote(key, safe='')}")
        record(f"باز کردن تست «{key}»", status, body)

    for label, path in [
        ("شمارهٔ صفر", "/tests/mbti/q/0"),
        ("شمارهٔ منفی", "/tests/mbti/q/-1"),
        ("شمارهٔ بزرگ", "/tests/mbti/q/9999"),
        ("شمارهٔ غیرعددی", "/tests/mbti/q/abc"),
        ("شمارهٔ اعشاری", "/tests/mbti/q/1.5"),
    ]:
        status, _, body = client.get(path)
        record(f"سؤال تست با {label}", status, body)

    status, _, _ = client.post("/tests/mbti/start", {})
    for label, choice in [("خالی", ""), ("منفی", "-1"), ("بزرگ", "99"), ("غیرعددی", "abc"), ("درست", "1")]:
        status, _, body = client.post("/tests/mbti/q/0", {"choice": choice})
        record(f"پاسخ تست با گزینهٔ {label}", status, body)

    for label, path in [
        ("شناسهٔ صفر", "/tests/mbti/result/0"),
        ("شناسهٔ بزرگ", "/tests/mbti/result/999999"),
        ("شناسهٔ غیرعددی", "/tests/mbti/result/abc"),
        ("شناسهٔ منفی", "/tests/mbti/result/-5"),
    ]:
        status, _, body = client.get(path)
        record(f"نتیجهٔ تست با {label}", status, body)


def case_feedback() -> None:
    print("\n— پاپ‌اپ امتیاز و نظر —")
    anon = Client()
    anon.get("/logout")
    status, _, body = anon.post("/feedback", {"rating": "5", "comment": "بی‌ورود"})
    record("بازخورد بدون ورود", status, body)
    status, _, body = anon.get("/api/feedback/invite")
    record("درخواست پیام پاپ‌اپ بدون ورود", status, body)

    client = make_ready_client(phone_for(9), "edge_feedback_" + RUN)
    if client is None:
        note("ساخت کاربر آزمون بازخورد نشد")
        return
    for label, rating in [("صفر", "0"), ("بالاتر از پنج", "6"), ("منفی", "-3"), ("غیرعددی", "abc"), ("خالی", ""), ("درست", "4")]:
        status, _, body = client.post("/feedback", {"rating": rating, "comment": "نظر آزمون لبه"})
        record(f"امتیاز {label}", status, body)
    status, _, body = client.post("/feedback", {"rating": "5", "comment": "x" * 40000})
    record("نظر ۴۰ هزار کاراکتری", status, body)
    status, _, body = client.post("/feedback", {"rating": "5", "comment": "<script>alert(1)</script>"})
    record("نظر با تگ اسکریپت", status, body)
    for _ in range(4):
        status, _, body = client.post("/feedback", {"rating": "5", "comment": f"تکرار {_}"})
    record("بازخورد پشت‌سرهم چهاربار", status, body)
    status, _, body = client.get("/api/feedback/invite")
    record("درخواست پیام پاپ‌اپ با ورود", status, body)


# --------------------------------------------------------------------------- #
# ۳. کوکی، متد و مسیرهای نامعتبر
# --------------------------------------------------------------------------- #


def case_http_oddities() -> None:
    print("\n— کوکی، متد و مسیر —")
    forged = Client()
    forged.jar.set_cookie(
        http.cookiejar.Cookie(
            0, "nsh_sid", "forged-session-value", None, False, "127.0.0.1", False, False, "/", True,
            False, None, True, None, None, {},
        )
    )
    for path in ["/", "/profile", "/readings", "/tests", "/journey", "/life", "/welcome", "/birth"]:
        status, _, body = forged.get(path)
        record(f"کوکی جعلی روی {path}", status, body)

    status, _, body = forged.get("/static/../../app/db.py")
    record("عبور از مسیر فایل‌های ثابت", status, body)

    for path in ["/no-such-page", "/api/nope", "/r/", "/tests/", "/journey/"]:
        status, _, body = forged.get(path)
        record(f"مسیر ناموجود {path}", status, body)

    status, _, body = forged.request("GET", "/feedback")
    record("متد نادرست روی مسیر POST", status, body)
    status, _, body = forged.request("POST", "/", {})
    record("POST روی صفحهٔ اصلی", status, body)
    status, _, body = forged.request("PUT", "/health", {})
    record("PUT روی سلامت", status, body)
    status, _, body = forged.request("POST", "/api/zodiac", raw="{not json")
    record("بدنهٔ JSON خراب", status, body)

    status, _, body = forged.request("GET", "/health")
    record("سلامت سرویس", status, body, expect="200")
    status, _, body = forged.get("/api/zodiac?jy=" + "9" * 4000)
    record("پارامتر کوئری بسیار بلند", status, body)


def case_admin() -> None:
    print("\n— پنل ادمین —")
    anon = Client()
    anon.get("/logout")
    for path in [ADMIN_PATH, f"{ADMIN_PATH}users", f"{ADMIN_PATH}export/users.csv"]:
        status, location, body = anon.get(path)
        record(f"مهمان روی {path}", status, body)

    admin = Client()
    for _ in range(8):
        admin.post(f"{ADMIN_PATH}login", {"username": ADMIN_USER, "password": "definitely-wrong"})
    status, _, body = admin.post(
        f"{ADMIN_PATH}login", {"username": ADMIN_USER, "password": "definitely-wrong"}
    )
    record("قفل پس از تلاش‌های ناموفق", status, body)

    admin2 = Client()
    for label, payload in [
        ("نام کاربری خالی", {"username": "", "password": ""}),
        ("رشته‌های بلند", {"username": "u" * 5000, "password": "p" * 5000}),
        ("شبیه SQL", {"username": "' OR 1=1 --", "password": "x"}),
    ]:
        status, _, body = admin2.post(f"{ADMIN_PATH}login", payload)
        record(f"ورود ادمین با {label}", status, body)


# --------------------------------------------------------------------------- #
# ۴. تبلیغات: آپلود خراب، زمان‌بندی ناممکن و مسیرهای قلابی
# --------------------------------------------------------------------------- #


def admin_client() -> Client:
    """کلاینت وارد‌شده به پنل (برای آزمون مسیرهای تبلیغات)."""
    client = Client()
    client.post(f"{ADMIN_PATH}", {"username": ADMIN_USER, "password": ADMIN_PASSWORD})
    return client


def upload(client: Client, fields: Dict[str, Any], filename: str, content: bytes, mime: str) -> Tuple[int, str, str]:
    """POST چندبخشی با یک فایل (همان کاری که فرم پنل می‌کند)."""
    boundary = "----edge" + uuid.uuid4().hex
    parts: List[bytes] = []
    for key, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode("utf-8")
        )
    if filename:
        parts.append(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="media"; filename="{filename}"\r\n'
                f"Content-Type: {mime}\r\n\r\n"
            ).encode("utf-8")
        )
        parts.append(content)
        parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))

    request = urllib.request.Request(
        BASE + f"{ADMIN_PATH}ads/save",
        data=b"".join(parts),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with client.opener.open(request, timeout=60) as response:
            return response.status, response.headers.get("Location", ""), response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get("Location", ""), error.read().decode("utf-8", "replace")


def case_ads() -> None:
    """تبلیغات: هر ورودی خراب باید پیام روشن بگیرد و سرور نترکد."""
    print("\n— تبلیغات —")
    admin = admin_client()
    status, _, page = admin.get(f"{ADMIN_PATH}ads")
    record("صفحهٔ تبلیغات", status, page, expect="200")

    tiny_png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000a49444154789c63000100005d9b1c9a0000000049454e44ae426082"
    )

    base = {"id": "0", "placement": "popup", "hold_seconds": "8", "skip_after": "3", "max_per_day": "3"}
    for label, fields, filename, content, mime in [
        ("بدون عنوان", {**base, "title": ""}, "a.png", tiny_png, "image/png"),
        ("عنوان فقط فاصله", {**base, "title": "    "}, "a.png", tiny_png, "image/png"),
        ("لینک جاوااسکریپت", {**base, "title": "x", "link_url": "javascript:alert(1)"}, "a.png", tiny_png, "image/png"),
        ("لینک data:", {**base, "title": "x", "link_url": "data:text/html,<b>x"}, "a.png", tiny_png, "image/png"),
        ("عنوان بسیار بلند", {**base, "title": "x" * 5000}, "a.png", tiny_png, "image/png"),
        ("فایل pdf", {**base, "title": "x"}, "a.pdf", b"%PDF-1.4 junk", "application/pdf"),
        ("فایل sh", {**base, "title": "x"}, "run.sh", b"#!/bin/sh\nrm -rf /", "text/x-sh"),
        ("فایل بدون پسوند", {**base, "title": "x"}, "noext", tiny_png, "image/png"),
        ("فایل خالی", {**base, "title": "x"}, "empty.png", b"", "image/png"),
        ("بدون فایل", {**base, "title": "x"}, "", b"", ""),
        ("اعداد غیرعددی", {**base, "title": "x", "hold_seconds": "abc", "skip_after": "-9", "max_per_day": "؟"}, "a.png", tiny_png, "image/png"),
        ("ساعت ناممکن", {**base, "title": "x", "hour_from": "-5", "hour_to": "99"}, "a.png", tiny_png, "image/png"),
        ("روز هفته قلابی", {**base, "title": "x", "weekdays": "99"}, "a.png", tiny_png, "image/png"),
        ("تاریخ ناممکن", {**base, "title": "x", "start_jy": "1400", "start_jm": "13", "start_jd": "40"}, "a.png", tiny_png, "image/png"),
        ("۳۱ اسفند غیرکبیسه", {**base, "title": "x", "end_jy": "1400", "end_jm": "12", "end_jd": "31"}, "a.png", tiny_png, "image/png"),
        ("پایان قبل از شروع", {**base, "title": "x", "start_jy": "1405", "start_jm": "5", "start_jd": "1", "end_jy": "1400", "end_jm": "1", "end_jd": "1"}, "a.png", tiny_png, "image/png"),
        ("فرم غایب", {}, "", b"", ""),
    ]:
        status, _, body = upload(admin, fields, filename, content, mime)
        record(f"ساخت تبلیغ: {label}", status, body)

    # مسیرهای قلابی/خطرناک
    for label, path in [
        ("توگل تبلیغ ناموجود", f"{ADMIN_PATH}ads/999999/preview"),
        ("توگل تبلیغ با شناسهٔ غیرعددی", f"{ADMIN_PATH}ads/abc/preview"),
    ]:
        status, _, body = admin.get(path)
        record(label, status, body)

    for label, payload in [
        ("شناسهٔ ناموجود", f"{ADMIN_PATH}ads/999999/toggle"),
        ("شناسهٔ غیرعددی", f"{ADMIN_PATH}ads/abc/toggle"),
    ]:
        status, _, body = admin.post(payload, {})
        record(f"خاموش‌کردن: {label}", status, body)

    status, _, body = admin.post(f"{ADMIN_PATH}ads/999999/delete", {})
    record("حذف تبلیغ ناموجود", status, body)

    # API عمومی تبلیغ
    anon = Client()
    for label, path in [
        ("نوع جای نمایش نامعتبر", "/api/ad?placement=%3Cscript%3E"),
        ("پارامتر بسیار بلند", "/api/ad?placement=" + "a" * 5000),
        ("پارامتر تکراری", "/api/ad?placement=popup&placement=banner"),
    ]:
        status, _, body = anon.get(path)
        record(f"API تبلیغ: {label}", status, body)

    for label, kind in [("نوع نامعتبر", "hack"), ("خالی", "")]:
        status, _, body = anon.post("/api/ad/1/event", {"kind": kind})
        record(f"ثبت رویداد: {label}", status, body)

    status, _, body = anon.post("/api/ad/999999/event", {"kind": "impression"})
    record("ثبت رویداد برای تبلیغ ناموجود", status, body)

    status, _, body = anon.post("/api/ad/abc/event", {"kind": "impression"})
    record("ثبت رویداد با شناسهٔ غیرعددی", status, body)

    # رسانه: تلاش برای بیرون‌زدن از پوشه
    for label, path in [
        ("عبور از مسیر", "/media/ads/..%2f..%2fapp%2fdb.py"),
        ("مسیر مطلق", "/media/ads/../../app/db.py"),
        ("فایل ناشناس", "/media/ads/nope.png"),
        ("پوشه به‌جای فایل", "/media/ads/"),
    ]:
        status, _, body = anon.get(path)
        record(f"رسانه: {label}", status, body)
        if "import sqlite3" in body or "DB_PATH" in body:
            crashes.append(f"افشای فایل برنامه از مسیر رسانه ({label})")
            print("[CRASH] فایل پایتونی از مسیر رسانه لو رفت")

    # تمیزکاری: تبلیغ‌های آزمون (عنوان دقیقاً «x» یا بلند) پاک می‌شوند
    try:
        from app import ads as app_ads
        from app import db as app_db

        for row in app_db.ads_all():
            title = str(row.get("title") or "")
            # همهٔ تبلیغ‌های این آزمون عنوانی از جنس «x» دارند (حتماً کوتاه‌شده).
            if title and set(title) == {"x"}:
                app_db.ad_delete(int(row["id"]))
                app_ads.delete_media(str(row.get("media_file") or ""))
        print("[نیز] تبلیغ‌های آزمون پاک شدند")
    except Exception as exc:  # pragma: no cover
        print(f"[نیز] پاک‌سازی تبلیغ‌های آزمون نشد: {exc}")


# --------------------------------------------------------------------------- #
# ۵. مسابقهٔ زمانی (دو درخواست هم‌زمان) و توست‌ها
# --------------------------------------------------------------------------- #


import threading


def case_races() -> None:
    """هم‌زمانی: بارزترین جایی که «نام کاربری تکراری» سرور را می‌ترکاند.

    کاربر روی موبایل ممکن است دکمه را دو بار بزند، یا دو نفر دقیقاً هم‌زمان یک نام
    را انتخاب کنند. بین «چک‌کردن آزاد بودن» و «نوشتن در دیتابیس» فاصله هست؛ اگر
    قید یکتاییِ دیتابیس مدیریت نشود، درخواست دوم با ۵۰۰ می‌ترکد.
    """
    print("\n— هم‌زمانی —")

    # الف) دو کاربر جداگانه که هنوز نام کاربری انتخاب نکرده‌اند، یک نام، در یک لحظه
    first = Client()
    second = Client()
    if not register(first, phone_for(11)) or not register(second, phone_for(12)):
        note("ساخت کاربران آزمون هم‌زمانی نشد")
        return

    shared = "race_shared_" + RUN
    payload = {"username": shared, "password": "RaceTest!234", "confirm": "RaceTest!234"}
    outcomes: List[Tuple[int, str, str]] = []

    def submit(client: Client) -> None:
        outcomes.append(client.post("/signup", payload))

    threads = [threading.Thread(target=submit, args=(first,)), threading.Thread(target=submit, args=(second,))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    for index, (status, _, body) in enumerate(outcomes):
        record(f"مسابقهٔ نام کاربری، درخواست {index + 1}", status, body)

    # مهم‌ترین سنجه: در دیتابیس فقط یک کاربر این نام را داشته باشد.
    try:
        from app import db as app_db

        row = app_db._one("SELECT COUNT(*) AS c FROM users WHERE lower(username) = lower(?)", (shared,))
        count = int(row["c"]) if row else -1
    except Exception as exc:  # pragma: no cover - فقط برای گزارش
        count = -1
        note(f"خواندن مستقیم دیتابیس نشد: {exc}")
    if count == 1:
        print("[OK ] نام کاربری در دیتابیس دقیقاً یک‌بار ثبت شد")
    else:
        crashes.append("نام کاربری اشتراکی چند‌بار ثبت شد")
        print(f"[CRASH] نام کاربری مشترک {count} بار در دیتابیس هست")

    # ب) همان کاربر، همان دکمه، دو بار پشت‌سرهم
    double = Client()
    if register(double, phone_for(13)):
        for index in range(2):
            status, _, body = double.post(
                "/signup",
                {"username": "race_twice_" + RUN, "password": "RaceTest!234", "confirm": "RaceTest!234"},
            )
            record(f"زدن دوبارهٔ دکمهٔ ثبت‌نام، نوبت {index + 1}", status, body)


# آستانهٔ توست‌ها: پیام فلش در HTML به‌شکل JSON می‌آید تا JS انیمیشنش کند.
FLASH_RE = re.compile(r'id="flashData">(.*?)</script>', re.S)


def flash_of(html: str) -> List[Dict[str, Any]]:
    match = FLASH_RE.search(html)
    if not match:
        return []
    raw = match.group(1).strip()
    if not raw or raw == "[]":
        return []
    import json

    try:
        data = json.loads(raw)
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def case_toasts() -> None:
    print("\n— توست‌ها —")
    client = Client()
    status, _, body = client.get("/logout")
    record("خروج از حساب", status, body, expect="3xx")
    status, _, page = client.get("/")
    items = flash_of(page)
    record("توست خروج در صفحهٔ بعد هست", status, page, expect="200")
    if not items:
        crashes.append("توست خروج نمایش داده نشد")
        print("[CRASH] توست خروج در صفحهٔ بعد نیست")
    else:
        print(f"[OK ] توست خروج: {items[0].get('kind')} — {items[0].get('message')[:40]}")

    status, _, page = client.get("/")
    if flash_of(page):
        crashes.append("توست بعد از رفرش تکرار شد")
        print("[CRASH] توست بعد از رفرش باقی ماند")
    else:
        print("[OK ] توست با رفرش تکرار نمی‌شود")

    # خطای فرم باید هم متن خطا و هم توست داشته باشد.
    anon = Client()
    status, _, page = anon.post("/register", {"phone": "0912"})
    has_error = "خطا" in page or "درست وارد کنید" in page
    record("صفحهٔ خطای ثبت‌نام با توست", status, page, expect="4xx")
    if has_error and flash_of(page):
        print("[OK ] خطای فرم به توست تبدیل شد")
    else:
        crashes.append("خطای فرم توست نشد")
        print("[CRASH] خطای فرم در توست دیده نشد")

    # صفحهٔ ۴۰۵ باید برند‌دار باشد، نه پاسخ خام FastAPI.
    status, _, page = anon.request("GET", "/feedback")
    branded = "این آدرس با این روش باز نمی‌شود" in page
    record("صفحهٔ ۴۰۵ برند‌دار", status, page, expect="4xx")
    if not branded:
        crashes.append("صفحهٔ ۴۰۵ خام ماند")
        print("[CRASH] صفحهٔ ۴۰۵ ظاهر خودمان را ندارد")

    # شمارهٔ موبایل با ارقام فارسی باید مثل لاتین پذیرفته شود.
    fa_client = Client()
    fa_client.get("/logout")
    fa_phone = "".join(FA_DIGITS[int(ch)] for ch in phone_for(14))
    status, location, body = fa_client.post("/register", {"phone": fa_phone})
    record("ثبت‌نام با ارقام فارسی", status, body, expect="3xx")
    if status != 303:
        crashes.append("ارقام فارسی در ثبت‌نام پذیرفته نشد")


# --------------------------------------------------------------------------- #


def case_mind() -> None:
    """بازی «ذهن‌خوان» با ورودی‌های عجیب: شناسهٔ غلط، جواب جعلی، اسم بلند."""
    client = Client()
    status, body, _ = client.get("/mind")
    record("ذهن‌خوان: صفحهٔ معرفی", status, body)

    status, location, _ = client.post("/mind/start", {})
    record("ذهن‌خوان: شروع", status, location)
    game = urllib.parse.urlparse(location).path or "/mind/g/نامعتبر"

    # جواب با کلید و مقدار ساختگی نباید بازی را خراب کند
    for label, payload in (
        ("کلید ساختگی", {"key": "'; DROP TABLE users; --", "value": "yes"}),
        ("مقدار ساختگی", {"key": "real", "value": "maybe"}),
        ("بدون داده", {}),
    ):
        status, body, _ = client.post(game + "/answer", payload)
        record(f"ذهن‌خوان: {label}", status, body)

    status, body, _ = client.post(game + "/back", {})
    record("ذهن‌خوان: یک قدم عقب", status, body)
    status, body, _ = client.post(game + "/guess", {"correct": "هیچ", "name": ""})
    record("ذهن‌خوان: حدس خالی", status, body)
    status, body, _ = client.post(game + "/giveup", {})
    record("ذهن‌خوان: نمی‌دانم", status, body)
    status, body, _ = client.post(game + "/learn", {"name": "ا"})
    record("ذهن‌خوان: اسم یک‌حرفی", status, body)
    status, body, _ = client.post(game + "/learn", {"name": "الف" * 2000})
    record("ذهن‌خوان: اسم بسیار بلند", status, body)

    # مسیرهای خرابکارانه با درصد-انکدینگ فرستاده می‌شوند (مسیر HTTP فقط ASCII می‌پذیرد).
    for label, path in (
        ("شناسهٔ ناموجود", "/mind/g/deadbeefdeadbeef"),
        ("شناسهٔ فارسی", "/mind/g/" + urllib.parse.quote("ندارد")),
        ("شناسهٔ خالی‌سازی", "/mind/g/%2e%2e%2f%2e%2e%2fetc%2fpasswd"),
        ("نتیجهٔ ناموجود", "/mind/r/0"),
    ):
        status, body, _ = client.get(path)
        record(f"ذهن‌خوان: {label}", status, body)

    status, body, _ = client.post("/mind/g/invalidgameid1/answer", {"key": "real", "value": "yes"})
    record("ذهن‌خوان: جواب برای بازی نامعتبر", status, body)

    # بازی شخص دیگر نباید با همان نشست باز شود؛ ولی ساخت بازی تازه باید کار کند.
    other = Client()
    status, location, _ = other.post("/mind/start", {})
    other_game = urllib.parse.urlparse(location).path
    status, body, _ = client.get(other_game)
    record("ذهن‌خوان: بازی دیگری", status, body)


def cleanup() -> None:
    """دادهٔ آزمون را پاک می‌کند تا اجراهای پیاپی دیتابیس را شلوغ نکنند.

    فقط چیزی‌هایی پاک می‌شود که همین اجرا ساخته است: شماره‌های `0912xxxRUN` و
    نام‌های کاربری با پایانهٔ RUN. داده‌ی واقعی کاربران دست‌نخورده می‌ماند.
    """
    try:
        from app import db as app_db

        phones = tuple(phone_for(seed) for seed in range(1, 15))
        # حذف از مسیر خود برنامه (`delete_user`) تا فال‌ها و جواب‌های وابسته هم پاک شوند.
        rows = app_db._query(
            "SELECT id FROM users WHERE phone IN ({}) OR username LIKE ? OR username LIKE ?".format(
                ",".join("?" * len(phones))
            ),
            phones + ("edge\_%\_" + RUN, "race\_%\_" + RUN),
        )
        for row in rows:
            app_db.delete_user(int(row["id"]))
        app_db._execute("DELETE FROM feedback WHERE comment LIKE 'نظر آزمون لبه%' OR comment LIKE 'آزمون لبه%'")
        print(f"[نیز] {len(rows)} کاربر آزمون از دیتابیس پاک شد")
    except Exception as exc:  # pragma: no cover - فقط گزارش
        print(f"[نیز] پاک‌سازی دادهٔ آزمون انجام نشد: {exc}")


def main() -> int:
    print(f"آزمون لبه‌ها روی {BASE}")
    primary = Client()
    case_register()
    case_username(primary)
    case_login(primary)
    case_onboarding()
    case_journey()
    case_reading()
    case_tests()
    case_feedback()
    case_http_oddities()
    case_races()
    case_toasts()
    case_ads()
    case_mind()
    case_admin()

    cleanup()

    print("\n" + "=" * 60)
    print(f"مجموع بررسی‌ها: {checks}   ترکیده: {len(crashes)}   نکته: {len(notes)}")
    if crashes:
        print("\nمواردی که باید درست شوند:")
        for item in crashes:
            print(f"  • {item}")
        return 1
    print("هیچ ورودی‌ای سرور را نمی‌ترکاند. ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
