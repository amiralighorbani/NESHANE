"""دودی‌تست نشانه: مسیر واقعی کاربر و پنل ادمین را روی سرور در حال اجرا چک می‌کند.

اجرا (سرور باید بالا باشد):

    python tools/smoke_test.py [base_url]

مسیر آزمون:
  ۱. ثبت‌نام با شماره و کد پیامکی (کد از صفحهٔ /verify خوانده می‌شود، با ارقام لاتین و فارسی)
     و انتخاب نام کاربری و رمز عبور؛ بعد از آن ورود فقط با نام کاربری + رمز انجام می‌شود
  ۲. کامل‌کردن ثبت‌نام روی یک کاربر تازه: نام کاربری و رمز → نام و نام خانوادگی → تاریخ و ساعت تولد
  ۳. صفحهٔ «زندگی در عدد» و لینکش در پروفایل
  ۴. انتخاب روش و موضوع و نوشتن نیت → ساخت فال
  ۵. باز کردن صفحهٔ فال و بررسی ابیات
  ۶. جواب‌دادن به همهٔ ده تست شخصیت تا آخر و باز کردن نتیجهٔ هرکدام
  ۷. صفحهٔ «زندگی در عدد» با همهٔ گروه‌ها و سنجه‌هایش
  ۸. نصب‌شدنی بودن PWA: منیفست، سرویس‌ورکر و آیکون‌ها
  ۹. پنل ادمین: پروندهٔ کاربر، پروندهٔ کامل (فال + جواب سوال‌ها)، خروجی‌های CSV
  ۱۰. مدیریت استخر فال: ساخت، ویرایش، حذف، پنهان و بازگرداندن کارت
  ۱۱. دسترسی مهمان به پنل بسته است

نکته: کاربر آزمون تازه پیش از هر اجرا از پنل حذف می‌شود، پس اجرای مکرر دیتابیس را شلوغ نمی‌کند.
"""

from __future__ import annotations

import base64
import http.cookiejar
import json
import os
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

# import کردن `app` خودش فایل `.env` را می‌خواند (کلیدها و رمز مدیر از آنجا می‌آید).
import app  # noqa: E402,F401

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8020").rstrip("/")
PHONE = "09121234567"          # کاربر آزمون با پروفایل کامل
TEST_USER = "smoke_user"       # نام کاربری کاربر آزمون
TEST_PASSWORD = "SmokeTest!234"
FRESH_PHONE = "09120000001"    # کاربر تازه برای آزمون ثبت‌نام کامل
FRESH_USER = "smoke_fresh"
FRESH_PASSWORD = "SmokeFresh!234"
DUP_PHONE = "09120000002"      # شمارهٔ دوم برای آزمون نام کاربری تکراری

# یک PNG کوچک و معتبر برای آزمون آپلود تبلیغ (بدون نیاز به فایل بیرونی).
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAKklEQVR42u3NMQEAAAgDoJvc6P5h"
    "LwRg0wcbAAAAAAAAAAAAAAAAAAAA4NcAmLwAAWvx7CkAAAAASUVORK5CYII="
)
# رمز مدیر در سورس نیست؛ از `.env` یا متغیر محیطی می‌آید.
ADMIN_USER = os.environ.get("NESHANE_ADMIN_USER", "").strip()
ADMIN_PASSWORD = os.environ.get("NESHANE_ADMIN_PASSWORD", "").strip()

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"

failures: List[str] = []


def to_ascii_digits(value: str) -> str:
    for index, digit in enumerate(FA_DIGITS):
        value = value.replace(digit, str(index))
    return value


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


class Client:
    """کلاینت HTTP ساده با کوکی، بدون دنبال‌کردن خودکار ریدایرکت."""

    def __init__(self) -> None:
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar), NoRedirect()
        )

    def request(self, method: str, path: str, data: Optional[Dict[str, Any]] = None) -> Tuple[int, str, str]:
        url = path if path.startswith("http") else BASE + path
        body = urllib.parse.urlencode(data or {}).encode("utf-8") if data is not None else None
        request = urllib.request.Request(url, data=body, method=method)
        if body:
            request.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with self.opener.open(request, timeout=30) as response:
                return response.status, response.headers.get("Location", ""), response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            return error.code, error.headers.get("Location", ""), error.read().decode("utf-8", "replace")

    def get(self, path: str) -> Tuple[int, str, str]:
        return self.request("GET", path)

    def post(self, path: str, data: Dict[str, Any]) -> Tuple[int, str, str]:
        return self.request("POST", path, data)

    def post_files(
        self,
        path: str,
        fields: Dict[str, Any],
        files: Dict[str, Tuple[str, bytes, str]],
    ) -> Tuple[int, str, str]:
        """فرم چندبخشی (multipart) برای آپلود فایل — مثل ساخت تبلیغ در پنل."""
        boundary = "----neshane" + uuid.uuid4().hex
        parts: List[bytes] = []
        for key, value in fields.items():
            parts.append(
                (
                    f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n'
                    f"{value}\r\n"
                ).encode("utf-8")
            )
        for key, (filename, content, mime) in files.items():
            parts.append(
                (
                    f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'
                    f"Content-Type: {mime}\r\n\r\n"
                ).encode("utf-8")
            )
            parts.append(content)
            parts.append(b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))
        body = b"".join(parts)

        url = path if path.startswith("http") else BASE + path
        request = urllib.request.Request(url, data=body, method="POST")
        request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        try:
            with self.opener.open(request, timeout=60) as response:
                return response.status, response.headers.get("Location", ""), response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as error:
            return error.code, error.headers.get("Location", ""), error.read().decode("utf-8", "replace")


def check(label: str, condition: bool, detail: str = "") -> None:
    mark = "OK " if condition else "FAIL"
    print(f"[{mark}] {label}" + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(label)


def note(label: str, detail: str = "") -> None:
    """نکته‌ای که ارزش دیدن دارد ولی شکست حساب نمی‌شود (مثلاً وضعیت مدل زبانی)."""
    print(f"[نیز] {label}" + (f" — {detail}" if detail else ""))


def otp_from_page(html: str) -> str:
    match = re.search(r'کد فعال:\s*<b class="ltr">([۰-۹0-9]+)</b>', html)
    return to_ascii_digits(match.group(1)) if match else ""


def persian_digits(value: str) -> str:
    return "".join(FA_DIGITS[int(digit)] if digit.isdigit() else digit for digit in value)


def quote(value: str) -> str:
    """پارامترهای فارسی و فاصله‌دار جست‌وجو را کدگذاری می‌کند."""
    return urllib.parse.quote(value, safe="")


def register(client: Client, phone: str, as_persian: bool = False) -> Tuple[int, str, str]:
    """ثبت‌نام: درخواست کد، خواندنش از صفحهٔ تأیید و تأیید با ارقام لاتین یا فارسی."""
    client.get("/logout")
    status, location, _ = client.post("/register", {"phone": phone})
    if status != 303 or not location.endswith("/verify"):
        return status, location, ""
    _status, _location, page = client.get("/verify")
    code = otp_from_page(page)
    if not code:
        return 0, "", ""
    value = persian_digits(code) if as_persian else code
    status, location, _ = client.post("/verify", {"code": value})
    return status, location, code


def password_login(client: Client, username: str, password: str) -> Tuple[int, str, str]:
    """ورود با نام کاربری و رمز عبور (راه ورود حساب‌های کامل‌شده)."""
    client.get("/logout")
    return client.post("/login", {"username": username, "password": password})


def ensure_account(client: Client, phone: str, username: str, password: str) -> Tuple[int, str, str]:
    """حساب آزمون را آماده می‌کند: اگر رمز دارد وارد می‌شود، وگرنه ثبت‌نامش را کامل می‌کند."""
    status, location, _ = password_login(client, username, password)
    if status == 303:
        return status, location, ""
    client.get("/logout")
    status, location, code = register(client, phone)
    if status == 303 and location.endswith("/signup"):
        status, location, _ = client.post(
            "/signup", {"username": username, "password": password, "confirm": password}
        )
    return status, location, code


def complete_profile(user: Client) -> None:
    """مرحله‌های ثبت‌نام را (اگر جا مانده باشد) پر می‌کند: نام/فامیل، بعد تولد."""
    if user.get("/welcome")[0] == 200:
        user.post("/welcome", {"name": "کاربر آزمون", "family": "آزمونی", "gender": "f"})
    user.post(
        "/birth",
        {"jy": "1372", "jm": "4", "jd": "18", "birth_time": "08:30", "city": "شیراز"},
    )


def journey(user: Client, method: str = "hafez", topic: str = "love") -> str:
    """پروفایل را کامل می‌کند، نیت می‌نویسد و توکن فال را برمی‌گرداند."""
    complete_profile(user)
    user.post("/journey/method", {"method": method})
    user.post("/journey/topic", {"topic": topic})
    status, location, _ = user.post("/journey/intent", {"intent": "دلم می‌خواهد بدانم این روزها کدام راه درست است"})
    token = location.rsplit("/", 1)[-1].split("?")[0] if location else ""
    return token if status == 303 and token else ""


def answer_test(user: Client, key: str, count: int) -> str:
    status, location, _ = user.post(f"/tests/{key}/start", {})
    attempt = ""
    if "?a=" in location:
        attempt = location.split("?a=", 1)[1]
    for index in range(count):
        status, location, _ = user.post(f"/tests/{key}/q/{index}", {"choice": "0", "a": attempt})
    return location.rsplit("/", 1)[-1] if location else ""


def main() -> int:
    print(f"== دودی‌تست {BASE} ==")

    status, _, _ = Client().get("/health")
    check("سرور بالا است", status == 200)
    if status != 200:
        return 1

    # ---- پنل ادمین (زودتر وارد می‌شویم تا بتوانیم کاربر آزمون تازه را صفر کنیم) ----
    from app import admin_auth

    if not ADMIN_USER or not ADMIN_PASSWORD:
        print(
            "[!] رمز پنل ادمین تنظیم نشده است.\n"
            "    فایل .env را از .env.example بساز و NESHANE_ADMIN_USER و\n"
            "    NESHANE_ADMIN_PASSWORD را در آن بگذار، یا همان‌ها را به‌عنوان\n"
            "    متغیر محیطی ست کن. (بدون رمز، ورود پنل بسته است.)"
        )
        return 1

    panel = admin_auth.ADMIN_PATH
    admin = Client()
    status, _, page = admin.get(panel)
    check("صفحهٔ ورود پنل ادمین باز می‌شود", status == 200 and "پنل مدیریت" in page, str(status))

    status, _, _ = admin.post(panel, {"username": ADMIN_USER, "password": "wrong-password"})
    check("پسورد غلط رد می‌شود", status == 401, str(status))

    status, location, _ = admin.post(panel, {"username": ADMIN_USER, "password": ADMIN_PASSWORD})
    check("ورود مدیر پذیرفته می‌شود", status == 303, f"{status} {location}")

    check("داشبورد پنل باز می‌شود", admin.get(f"{panel}dashboard")[0] == 200)

    # کاربر آزمون تازهٔ اجرای قبلی را پاک می‌کنیم تا ثبت‌نام از صفر آزموده شود.
    status, _, fresh_list = admin.get(f"{panel}users?q={FRESH_PHONE}")
    fresh_row = re.search(r"users/(\d+)", fresh_list)
    if fresh_row:
        status, _, _ = admin.post(f"{panel}users/{fresh_row.group(1)}/delete", {"confirm": "بله"})
        check("صفرکردن کاربر آزمون تازه (حذف اجرای قبلی)", status == 303, str(status))

    # ---- ثبت‌نام کامل یک شمارهٔ تازه: کد → نام کاربری و رمز → نام و تولد ----
    fresh = Client()
    status, location, _ = fresh.post("/register", {"phone": FRESH_PHONE})
    check("ثبت‌نام با شماره", status == 303 and location.endswith("/verify"), f"{status} {location}")

    status, _, page = fresh.get("/verify")
    check("کد ثبت‌نام روی صفحهٔ تأیید دیده می‌شود", bool(otp_from_page(page)), "کد پیدا نشد")
    check("فرم کد، شش خانهٔ چپ‌به‌راست دارد", page.count('class="otp__input"') == 6 and 'dir="ltr"' in page)

    # ارقام فارسی باید هم‌ارز ارقام لاتین کار کنند (باگی که رفع شد).
    code = otp_from_page(page)
    status, location, _ = fresh.post("/verify", {"code": persian_digits(code)})
    check(
        "تأیید کد با ارقام فارسی و رفتن به قدم نام کاربری و رمز",
        status == 303 and location.endswith("/signup"),
        f"{status} {location}",
    )

    status, _, page = fresh.get("/signup")
    check(
        "قدم نام کاربری و رمز باز می‌شود",
        status == 200 and 'name="username"' in page and 'name="password"' in page,
        str(status),
    )

    status, _, _ = fresh.post("/signup", {"username": FRESH_USER, "password": "1234", "confirm": "1234"})
    check("رمز کوتاه رد می‌شود", status == 422, str(status))

    status, _, _ = fresh.post(
        "/signup", {"username": FRESH_USER, "password": FRESH_PASSWORD, "confirm": "چیز دیگری"}
    )
    check("تکرار ناهمخوان رمز رد می‌شود", status == 422, str(status))

    status, _, _ = fresh.post(
        "/signup", {"username": "سارا", "password": FRESH_PASSWORD, "confirm": FRESH_PASSWORD}
    )
    check("نام کاربری فارسی رد می‌شود", status == 422, str(status))

    status, location, _ = fresh.post(
        "/signup", {"username": FRESH_USER, "password": FRESH_PASSWORD, "confirm": FRESH_PASSWORD}
    )
    check(
        "ذخیرهٔ نام کاربری و رمز به قدم نام می‌رود",
        status == 303 and location.endswith("/welcome"),
        f"{status} {location}",
    )

    status, _, page = fresh.get("/welcome")
    check("صفحهٔ نام و نام خانوادگی باز می‌شود", status == 200 and 'name="family"' in page, str(status))
    check("فرم ثبت‌نام فامیل را اجباری کرده", "نام خانوادگی" in page)

    status, _, page = fresh.post("/welcome", {"name": "سارا", "family": "ا", "gender": "f"})
    check("نام خانوادگی کوتاه رد می‌شود", status == 422, str(status))

    status, location, _ = fresh.post("/welcome", {"name": "سارا", "family": "محمدی", "gender": "f"})
    check("ذخیرهٔ نام و فامیل به صفحهٔ تولد می‌رود", status == 303 and location.endswith("/birth"), f"{status} {location}")

    status, _, page = fresh.get("/birth")
    check("صفحهٔ اطلاعات تولد باز می‌شود", status == 200 and 'name="jy"' in page, str(status))
    check("فرم تولد ماه و روز و ساعت می‌گیرد", 'name="jm"' in page and 'name="jd"' in page and 'name="birth_time"' in page)

    status, location, _ = fresh.post(
        "/birth", {"jy": "1376", "jm": "3", "jd": "12", "birth_time": "09:15", "city": "اصفهان"}
    )
    check("ذخیرهٔ تولد به «زندگی در عدد» می‌رود", status == 303 and location.startswith("/life"), f"{status} {location}")

    status, _, life_html = fresh.get("/life")
    check("صفحهٔ زندگی در عدد باز می‌شود", status == 200, str(status))
    check("سن و ضربان قلب محاسبه شده", "ضربان" in life_html and "ساعت" in life_html)
    if status == 200:
        for needle in ("وعده", "هفته", "روز"):
            check(f"عدد «{needle}» در زندگی در عدد هست", needle in life_html)
    check("صفحهٔ زندگی در پروفایل هم لینک شده", "/life" in fresh.get("/profile")[2])

    # ---- از این به بعد ورود فقط با نام کاربری و رمز؛ شمارهٔ کامل‌شده کد نمی‌گیرد ----
    status, _, page = Client().post("/register", {"phone": FRESH_PHONE})
    check(
        "شمارهٔ ثبت‌نام‌شده دیگر کد نمی‌گیرد",
        status == 422 and "قبلاً ثبت‌نام کرده" in page,
        str(status),
    )

    status, location, _ = password_login(fresh, FRESH_USER, FRESH_PASSWORD)
    check("ورود با نام کاربری و رمز", status == 303 and location.endswith("/journey"), f"{status} {location}")

    status, _, page = fresh.post("/login", {"username": FRESH_USER, "password": "wrong-password"})
    check("رمز اشتباه رد می‌شود", status == 422 and "درست نیست" in page, str(status))

    status, _, _ = fresh.post("/login", {"username": "کاربر-ناموجود", "password": FRESH_PASSWORD})
    check("نام کاربری ناموجود رد می‌شود", status == 422, str(status))

    check("صفحهٔ پیامک‌ها کدی نشان نمی‌دهد", "کد ثبت‌نام شما" not in fresh.get("/inbox")[2])
    check("قدم نام کاربری و رمز برای حساب کامل تکرار نمی‌شود", fresh.get("/signup")[0] == 303, "باز شد")

    # ---- کاربر آزمون: اگر از نسخهٔ قبلی بدون رمز مانده باشد، همان‌جا رمز می‌گذارد ----
    user = Client()
    status, location, _ = ensure_account(user, PHONE, TEST_USER, TEST_PASSWORD)
    check("حساب کاربر آزمون آماده است", status == 303, f"{status} {location}")
    check("ورود کاربر برقرار است", user.get("/profile")[0] == 200)

    # ---- نام کاربری تکراری پذیرفته نمی‌شود ----
    other = Client()
    status, location, _ = register(other, DUP_PHONE)
    check(
        "ثبت‌نام دوم با شمارهٔ دیگر و ارقام لاتین",
        status == 303 and location.endswith("/signup"),
        f"{status} {location}",
    )
    status, _, page = other.post(
        "/signup", {"username": TEST_USER, "password": "Another!2345", "confirm": "Another!2345"}
    )
    check("نام کاربری تکراری رد می‌شود", status == 422 and "قبلاً انتخاب شده" in page, str(status))

    status, location, _ = other.post(
        "/signup", {"username": "smoke_other", "password": "Another!2345", "confirm": "Another!2345"}
    )
    check("دو حساب می‌توانند هم‌زمان نام کاربری جدا داشته باشند", status == 303, f"{status} {location}")

    token = journey(user, "hafez", "love")
    check("ساخت فال از مسیر سفر", bool(token), "توکن برنگشت")
    if token:
        status, _, reading_html = user.get(f"/r/{token}")
        check("صفحهٔ فال باز می‌شود", status == 200)
        check("ابیات واقعی روی صفحه هست", "غزل شمارهٔ" in reading_html)
        check("لینک فال در تاریخچه می‌آید", token[:6] in user.get("/readings")[2])

    from app.content import personality as test_catalogue

    tests_page_html = user.get("/tests")[2]
    check("فهرست تست‌ها باز می‌شود", "خودشناسی" in tests_page_html)
    check(
        f"هر ده تست در فهرست هست ({len(test_catalogue.TEST_ORDER)})",
        all(test["label"] in tests_page_html for test in test_catalogue.catalogue()),
    )
    check(
        "گروه‌بندی تست‌ها در فهرست دیده می‌شود",
        all(group["title"] in tests_page_html for group in test_catalogue.TEST_GROUPS),
    )

    done = []
    for test in test_catalogue.catalogue():
        key = str(test["key"])
        opened = user.get(f"/tests/{key}")[0]
        result = answer_test(user, key, len(test["questions"]))
        if opened == 200 and result and not result.startswith("q"):
            if user.get(f"/tests/{key}/result/{result}")[0] == 200:
                done.append(key)
    check(
        f"هر ده تست تا آخر جواب داده و نتیجه‌اش باز شد ({len(done)}/{len(test_catalogue.TEST_ORDER)})",
        len(done) == len(test_catalogue.TEST_ORDER),
        "، ".join(sorted(set(test_catalogue.TEST_ORDER) - set(done))),
    )

    key = test_catalogue.TEST_ORDER[0]
    result = ""
    profile_html = user.get("/profile")[2]
    check("نتیجهٔ تست‌ها در پروفایل می‌آید", test_catalogue.TESTS[key]["label"] in profile_html)

    # ---- زندگی در عدد: تاریخ تولد و آمار عمر ----
    life_html = user.get("/life")[2]
    check("صفحهٔ زندگی در عدد باز می‌شود", "شناسنامهٔ لحظهٔ تولد" in life_html)
    check("داستان روز تولد در گزارش هست", "داستان روز تولدت" in life_html)
    check(
        "گزارش زندگی بیش از پنجاه سنجه دارد",
        life_html.count('class="life-card__label"') >= 50,
        str(life_html.count('class="life-card__label"')),
    )
    check("سنگ و گل تولد نمایش داده می‌شود", "سنگ تولدت" in life_html and "گل تولدت" in life_html)

    # ---- PWA: نصب‌شدنی روی گوشی ----
    status, _, manifest = Client().get("/manifest.webmanifest")
    check("منیفست PWA سرو می‌شود", status == 200 and "نشانه" in manifest, str(status))
    status, _, service_worker = Client().get("/sw.js")
    check("سرویس‌ورکر سرو می‌شود", status == 200 and "addEventListener" in service_worker, str(status))
    for size in (192, 512):
        status, _, _ = Client().get(f"/static/icons/icon-{size}.png")
        check(f"آیکون {size} در دسترس است", status == 200, str(status))

    # ---- فال‌های نمادین: هر روش شیءِ خودش را می‌اندازد ----
    from app.content import methods as method_catalogue
    from app.engine import build_reading
    from app.models import FortuneRequest
    import uuid as _uuid

    sample = {
        "name": "کاربر آزمون",
        "jy": 1372,
        "jm": 4,
        "jd": 18,
        "birth_time": "08:30",
        "city": "شیراز",
        "topic": "love",
        "intent": "دلم می‌خواهد بدانم این روزها کدام راه درست است",
    }
    visuals: Dict[str, List[str]] = {}
    symbol_counts: Dict[str, int] = {}
    for method_key in method_catalogue.METHOD_ORDER:
        reading = build_reading(
            FortuneRequest(**{**sample, "method": method_key}), salt=_uuid.uuid4().hex[:8]
        )
        visuals[method_key] = [block.visual for block in reading.blocks if block.visual]
        symbol_counts[method_key] = sum(len(block.symbols) for block in reading.blocks)

    check(
        f"هر هفت روش فال نماد بصری خودش را دارد ({len(visuals)})",
        all(visuals.get(key) for key in method_catalogue.METHOD_ORDER),
        str({key: visuals.get(key) for key in method_catalogue.METHOD_ORDER}),
    )
    check("هر فال شیء نمادین واقعی می‌اندازد", all(count > 0 for count in symbol_counts.values()), str(symbol_counts))
    distinct = {tuple(visuals[key]) for key in method_catalogue.METHOD_ORDER}
    check(
        f"وجه تمایز روش‌ها یکتاست ({len(distinct)} الگوی متفاوت)",
        len(distinct) == len(method_catalogue.METHOD_ORDER),
        str(visuals),
    )

    tarot_reading = build_reading(FortuneRequest(**{**sample, "method": "tarot"}), salt="smoke-tarot")
    tarot_block = next((block for block in tarot_reading.blocks if block.visual == "cards"), None)
    tarot_names = [symbol["name"] for symbol in (tarot_block.symbols if tarot_block else [])]
    check("فال تاروت سه کارت واقعی می‌اندازد", len(tarot_names) == 3, str(tarot_names))
    check("کارت‌های تاروت تکراری نیستند", len(set(tarot_names)) == len(tarot_names), str(tarot_names))
    check(
        "هر کارت تاروت جایگاه و جهت دارد",
        bool(tarot_block)
        and all(symbol.get("position") and symbol.get("orientation_label") for symbol in tarot_block.symbols),
    )

    dice_reading = build_reading(FortuneRequest(**{**sample, "method": "dice"}), salt="smoke-dice")
    dice_block = next((block for block in dice_reading.blocks if block.visual == "dice"), None)
    pips = [int(symbol["pip"]) for symbol in (dice_block.symbols if dice_block else [])]
    check("فال تاس سه تاس می‌اندازد", len(pips) == 3, str(pips))
    check("عدد هر تاس بین ۱ تا ۶ است", bool(pips) and all(1 <= pip <= 6 for pip in pips), str(pips))
    check(
        "نقطه‌های تاس با عددش می‌خواند",
        bool(dice_block)
        and all(len(symbol["dots"].split(",")) == int(symbol["pip"]) for symbol in dice_block.symbols),
    )

    rune_reading = build_reading(FortuneRequest(**{**sample, "method": "runes"}), salt="smoke-rune")
    rune_block = next((block for block in rune_reading.blocks if block.visual == "rune"), None)
    check("فال رون یک سنگ با نمادش می‌آورد", bool(rune_block) and len(rune_block.symbols) == 1 and bool(rune_block.symbols[0].get("glyph")))

    # ---- امتیازدهی تست‌ها: از پاسخ‌های واقعی به نتیجهٔ واقعی ----
    from app import personality as personality_engine
    from app.content import personality as test_catalogue_local

    mbti_key = "mbti"
    mbti_total = len(test_catalogue_local.TESTS[mbti_key]["questions"])
    mbti_result = personality_engine.build_result(
        mbti_key, {str(index): index % 2 for index in range(mbti_total)}
    )
    check(
        "نتیجهٔ MBTI از پاسخ‌های واقعی درمی‌آید",
        mbti_result.answered == mbti_total,
        str(mbti_result.answered),
    )
    check("هر چهار محور MBTI درصد و قدرت ترجیح دارند", len(mbti_result.axes) == 4 and all(axis.get("strength") for axis in mbti_result.axes))
    check(
        "درصد محورها همیشه صد جمع می‌زند",
        all(int(axis["left_pct"]) + int(axis["right_pct"]) == 100 for axis in mbti_result.axes),
    )

    big5_key = "big5"
    big5_total = len(test_catalogue_local.TESTS[big5_key]["questions"])
    big5_result = personality_engine.build_result(
        big5_key, {str(index): index % 4 for index in range(big5_total)}
    )
    big5_pcts = [int(item["pct"]) for item in big5_result.ranked]
    check("پنج عامل بزرگ رتبه‌بندی می‌شود", len(big5_pcts) >= 2, str(big5_pcts))
    check("درصد عامل‌ها از سقف حساب می‌شود (نه همه ۱۰۰)", all(0 <= value <= 100 for value in big5_pcts) and max(big5_pcts) <= 100)
    check("رتبهٔ عامل‌ها نزولی است", big5_pcts == sorted(big5_pcts, reverse=True), str(big5_pcts))
    check("هر عامل برچسب سطح دارد", all(item.get("level") for item in big5_result.ranked))

    # ---- پاپ‌اپ امتیاز و نظر ----
    from app import db as app_db
    from app import llm as llm_layer

    note("وضعیت لایهٔ مدل زبانی", "روشن" if llm_layer.enabled() else "خاموش (NESHANE_LLM=0)")
    note("ارائه‌دهنده‌های تنظیم‌شده", "، ".join(item["label"] for item in llm_layer.provider_view() if item["configured"]))

    account = app_db.user_by_username(TEST_USER) or {}
    if account.get("id"):
        target = int(account["id"])
        app_db.set_last_active(target, app_db.now() - 30 * 3600)
        app_db._execute("UPDATE users SET feedback_asked_at = NULL WHERE id = ?", (target,))

        status, _, popup_page = user.get("/profile")
        check("پاپ‌اپ امتیاز پس از ۲۴ ساعت غیبت نمایش داده می‌شود", status == 200 and "data-rate-modal" in popup_page, str(status))
        check("پاپ‌اپ ستاره‌های ۱ تا ۵ را دارد", all(f'value="{star}"' in popup_page for star in range(1, 6)))
        check("فرم پاپ‌اپ به مسیر بازخورد می‌رود", 'action="/feedback"' in popup_page)
        check("متن ترغیبی روی پاپ‌اپ هست", "نشانه را برای همین دغدغه‌های تو ساخته‌ایم" in popup_page)

        _status, _, second_page = user.get("/profile")
        check("پاپ‌اپ در بازدید بعدی تکرار نمی‌شود", "data-rate-modal" not in second_page)

        status, location, _ = user.post(
            "/feedback",
            {"rating": "۴", "comment": "آزمون خودکار: خوانش کارت‌های تاروت دقیق بود", "back": "/profile"},
        )
        check("ثبت امتیاز و نظر", status == 303, f"{status} {location}")
        # پیام تشکر حالا به‌شکل توستِ انیمیشنیِ سمت مرورگر نشان داده می‌شود؛
        # کوکی فلش در صفحهٔ بعدی خوانده و به JSON انگلیسی‌نویسی‌شده تبدیل می‌شود.
        _status, _, after_feedback = user.get(location or "/profile")
        flash_raw = re.search(r'id="flashData">(.*?)</script>', after_feedback, re.S)
        try:
            flash_items = json.loads(flash_raw.group(1)) if flash_raw else []
        except ValueError:
            flash_items = []
        check(
            "پیام تشکر پس از ثبت نظر به‌شکل توست می‌آید",
            any("نظرت ثبت شد" in str(item.get("message") or "") for item in flash_items),
            str(flash_items)[:120],
        )

        stats_after = app_db.feedback_stats()
        check("امتیاز در دیتابیس ذخیره شد", stats_after["total"] >= 1 and stats_after["comments"] >= 1, str(stats_after))

        status, _, invite = user.get("/api/feedback/invite")
        check("مسیر پیام پاپ‌اپ پاسخ می‌دهد", status == 200 and "invite" in invite, str(status))

    # ---- پنل ادمین: پروندهٔ کاربر اصلی ----
    status, _, users_html = admin.get(f"{panel}users?q={PHONE}")
    check("کاربر در فهرست پنل پیدا می‌شود", status == 200 and PHONE in to_ascii_digits(users_html), str(status))

    match = re.search(rf"users/(\d+)", users_html)
    user_id = match.group(1) if match else ""
    check("شناسهٔ کاربر از فهرست خوانده شد", bool(user_id))

    if user_id:
        status, _, detail = admin.get(f"{panel}users/{user_id}")
        check("پروندهٔ کاربر باز می‌شود", status == 200)
        check("نیت کاربر در پرونده هست", "کدام راه درست است" in detail)
        check("تاریخ تولد و شهر در پرونده هست", "شیراز" in detail and "۱۸" in detail)
        check("جواب سوال‌های تست در پرونده هست", "جواب تست‌های شخصیت" in detail)
        question_text = test_catalogue.TESTS[key]["questions"][0]["text"]
        check("متن سوال اول تست نمایش داده می‌شود", question_text[:20] in detail)
        first_option = test_catalogue.TESTS[key]["questions"][0]["options"][0]["text"]
        check("گزینهٔ انتخاب‌شدهٔ کاربر نمایش داده می‌شود", first_option[:18] in detail)

        status, created, _ = admin.post(f"{panel}users/{user_id}/fortune", {"method": "tarot", "topic": "career"})
        check("ساخت فال برای کاربر از پنل", status == 303 and "/readings/" in created, f"{status} {created}")
        if "/readings/" in created:
            token_created = created.split("/readings/", 1)[1].split("?")[0]
            status, _, created_page = admin.get(f"{panel}readings/{token_created}")
            check("خوانش ساخته‌شده در پنل باز می‌شود", status == 200 and "کارت تاروت" in created_page, str(status))

    # ---- پروندهٔ کامل کاربر ----
    if user_id:
        status, _, dossier = admin.get(f"{panel}users/{user_id}/dossier")
        check("پروندهٔ کامل کاربر باز می‌شود", status == 200 and "پروندهٔ کامل کاربر" in dossier, str(status))
        check("پرونده بخش زندگی در عدد دارد", "زندگی در عدد" in dossier)
        check("پرونده جواب آزمون‌ها را کنار سوال می‌آورد", "آزمون‌های شخصیت" in dossier and "جواب" in dossier)
        check("پرونده فال‌های کاربر را می‌آورد", "فال‌های گرفته‌شده" in dossier)
        status, _, dossier_csv = admin.get(f"{panel}users/{user_id}/dossier.csv")
        check(
            "خروجی CSV پرونده شامل فال و جواب آزمون است",
            status == 200 and "جواب آزمون" in dossier_csv and "فال" in dossier_csv,
            str(status),
        )

    # ---- مدیریت استخر فال: افزودن، ویرایش، حذف، پنهان و بازگردانی ----
    status, location, _ = admin.post(
        f"{panel}fortunes/save",
        {
            "key": "",
            "title": "کارت آزمون",
            "theme_label": "امید، گشایش و بخت",
            "verses": "ابیات آزمون\nمصرع دوم آزمون",
            "keywords": "آزمون, بخت",
            "interpretation": "این یک تعبیر آزمون است.",
            "guidance": "یک قدم کوچک بردار.",
        },
    )
    check("ساخت کارت فال تازه", status == 303 and "ok=saved" in location, f"{status} {location}")

    status, _, pool_html = admin.get(f"{panel}fortunes?q={quote('کارت آزمون')}")
    match = re.search(r"custom-[0-9a-f]{6,}", to_ascii_digits(pool_html))
    new_key = match.group(0) if match else ""
    check("کارت تازه در استخر دیده می‌شود", bool(new_key) and "این یک تعبیر آزمون است" in pool_html, new_key)

    if new_key:
        status, _, form_html = admin.get(f"{panel}fortunes/{new_key}/edit")
        check("فرم ویرایش کارت باز می‌شود", status == 200 and "کارت آزمون" in form_html, str(status))

        status, location, _ = admin.post(
            f"{panel}fortunes/save",
            {
                "key": new_key,
                "title": "کارت آزمون ویرایش‌شده",
                "theme_label": "امید، گشایش و بخت",
                "verses": "ابیت ویرایش‌شده",
                "keywords": "ویرایش",
                "interpretation": "تعبیر ویرایش‌شدهٔ آزمون.",
                "guidance": "",
            },
        )
        check("ویرایش کارت فال", status == 303 and "ok=saved" in location, f"{status} {location}")
        status, _, pool_html = admin.get(f"{panel}fortunes?q={quote('کارت آزمون ویرایش‌شده')}")
        check("متن ویرایش‌شده در استخر دیده می‌شود", "تعبیر ویرایش‌شدهٔ آزمون" in pool_html, str(status))

        status, location, _ = admin.post(f"{panel}fortunes/{new_key}/delete", {})
        check("حذف کارت ساختهٔ مدیر", status == 303 and "ok=deleted" in location, f"{status} {location}")
        status, _, pool_html = admin.get(f"{panel}fortunes?q={quote('کارت آزمون ویرایش‌شده')}")
        check("کارت حذف‌شده دیگر در استخر نیست", "تعبیر ویرایش‌شدهٔ آزمون" not in pool_html, str(status))

    # کارت آماده: پنهان می‌شود و باز می‌گردد.
    status, _, pool_html = admin.get(f"{panel}fortunes?source=curated")
    builtin_match = re.search(r"fortunes/(curated-\d+)/edit", pool_html)
    builtin_key = builtin_match.group(1) if builtin_match else ""
    check("کلید کارت آماده پیدا شد", bool(builtin_key), builtin_key)
    if builtin_key:
        status, location, _ = admin.post(f"{panel}fortunes/{builtin_key}/delete", {})
        check("پنهان‌کردن کارت آماده", status == 303 and "ok=hidden" in location, f"{status} {location}")
        status, _, hidden_html = admin.get(f"{panel}fortunes?show=hidden")
        check("کارت پنهان در فهرست پنهان‌ها هست", builtin_key in hidden_html, str(status))
        status, location, _ = admin.post(f"{panel}fortunes/{builtin_key}/restore", {})
        check("بازگرداندن کارت آماده", status == 303 and "ok=restored" in location, f"{status} {location}")

    check("فهرست خوانش‌ها", admin.get(f"{panel}readings")[0] == 200)
    check("استخر فال", admin.get(f"{panel}fortunes")[0] == 200)
    check("رویدادها", admin.get(f"{panel}audit")[0] == 200)

    # ---- مانیتورینگ مدل زبانی ----
    status, _, ai_html = admin.get(f"{panel}ai")
    check("صفحهٔ مانیتورینگ هوش مصنوعی باز می‌شود", status == 200, str(status))
    check("مانیتورینگ، ارائه‌دهندهٔ اصلی و پشتیبان را نشان می‌دهد", "ارائه‌دهندهٔ اصلی" in ai_html and "پشتیبان" in ai_html)
    check("مانیتورینگ مصرف توکن و تأخیر را می‌آورد", "توکن مصرفی" in ai_html and "میانگین تأخیر" in ai_html)
    check("مانیتورینگ فهرست ناموفق‌ها را دارد", "فقط ناموفق‌ها" in ai_html)
    check("مانیتورینگ تفکیک کاربرد و مدل دارد", "مصرف به تفکیک کاربرد" in ai_html and "مصرف به تفکیک مدل" in ai_html)

    status, _, failures_html = admin.get(f"{panel}ai?failures=1")
    check("فیلتر ناموفق‌ها کار می‌کند", status == 200, str(status))

    status, _, prompts_html = admin.get(f"{panel}ai/prompts")
    check("صفحهٔ دستورهای سیستم باز می‌شود", status == 200, str(status))
    from app import prompts as prompt_book

    missing_prompts = [
        entry["label"]
        for entry in prompt_book.catalogue()
        if entry["system"].splitlines()[0][:24] not in prompts_html
    ]
    check(
        f"متن کامل همهٔ سیستم‌پرامپت‌ها نمایش داده می‌شود ({len(prompt_book.PROMPT_ORDER)})",
        not missing_prompts,
        "، ".join(missing_prompts),
    )
    check("قالب پیام کاربر هم نمایش داده می‌شود", prompts_html.count("قالب پیام کاربر") == len(prompt_book.PROMPT_ORDER))

    status, _, llm_csv = admin.get(f"{panel}export/llm.csv")
    check("خروجی CSV تماس‌های مدل", status == 200 and "latency_ms" in llm_csv, str(status))

    # ---- امتیاز و نظر در پنل ----
    status, _, feedback_html = admin.get(f"{panel}feedback")
    check("صفحهٔ امتیاز و نظر در پنل باز می‌شود", status == 200, str(status))
    check("میانگین امتیاز در پنل هست", "میانگین امتیاز" in feedback_html)
    check("نظر نوشته‌شدهٔ کاربر در پنل دیده می‌شود", "آزمون خودکار" in feedback_html)

    status, _, comments_html = admin.get(f"{panel}feedback?comments=1")
    check("فیلتر «فقط نظرهای نوشته‌شده» کار می‌کند", status == 200, str(status))

    status, _, feedback_csv = admin.get(f"{panel}export/feedback.csv")
    check("خروجی CSV بازخورد", status == 200 and "rating" in feedback_csv, str(status))

    status, _, csv_body = admin.get(f"{panel}export/users.csv")
    check("خروجی CSV کاربران", status == 200 and PHONE in to_ascii_digits(csv_body), str(status))

    status, _, csv_tests = admin.get(f"{panel}export/attempts.csv")
    check("خروجی CSV جواب تست‌ها", status == 200 and "Q1" in csv_tests, str(status))

    # کاربر آزمون نام کاربری تکراری را از پنل پاک می‌کنیم تا دیتابیس شلوغ نشود.
    status, _, dup_list = admin.get(f"{panel}users?q={DUP_PHONE}")
    dup_row = re.search(r"users/(\d+)", dup_list)
    if dup_row:
        status, _, _ = admin.post(f"{panel}users/{dup_row.group(1)}/delete", {"confirm": "بله"})
        check("پاک‌کردن کاربر آزمون نام کاربری تکراری", status == 303, str(status))

    status, _, csv_users = admin.get(f"{panel}export/users.csv")
    check("نام کاربری در خروجی CSV کاربران هست", status == 200 and FRESH_USER in to_ascii_digits(csv_users), str(status))

    # دادهٔ آزمونی بازخورد را پاک می‌کنیم تا آمار واقعی کاربران شلوغ نشود.
    from app import db as app_db_cleanup

    try:
        app_db_cleanup._execute(
            "DELETE FROM feedback WHERE comment LIKE 'آزمون خودکار:%'"
        )
        note("بازخورد آزمونی پاک شد")
    except Exception as exc:  # pragma: no cover
        note("پاک‌سازی بازخورد آزمونی انجام نشد", str(exc))

    # ---- تبلیغات: آپلود، زمان‌بندی، نمایش و آمار ----
    status, _, ads_html = admin.get(f"{panel}ads")
    check("صفحهٔ تبلیغات در پنل باز می‌شود", status == 200 and "تبلیغ تازه" in ads_html, str(status))

    ad_title = "آزمون خودکار: تخفیف فال تاروت"
    fields = {
        "id": "0",
        "title": ad_title,
        "body": "یک متن کوتاه برای آزمون",
        "link_url": "https://example.com/neshane-test",
        "cta_label": "ببین",
        "placement": "both",
        "hold_seconds": "6",
        "skip_allowed": "1",
        "skip_after": "2",
        "dismiss_days": "1",
        "max_per_day": "5",
        "hour_from": "0",
        "hour_to": "24",
        "weight": "3",
        "active": "1",
    }
    status, location, _ = admin.post_files(
        f"{panel}ads/save", fields, {"media": ("offer.png", TINY_PNG, "image/png")}
    )
    check("ساخت تبلیغ با آپلود عکس", status == 303 and "ok=created" in location, f"{status} {location}")

    from app import ads as app_ads
    from app import db as app_db_ads

    created = next((row for row in app_db_ads.ads_all() if row["title"] == ad_title), None)
    check("تبلیغ در دیتابیس ثبت شد", created is not None)
    check("نوع فایل درست تشخیص داده شد", bool(created) and created["media_kind"] == "image")
    if created:
        check("فایل رسانه روی دیسک هست", app_ads.media_path(str(created["media_file"])).is_file())

    status, _, ads_html = admin.get(f"{panel}ads")
    check("تبلیغ در فهرست پنل دیده می‌شود", status == 200 and ad_title in ads_html)
    check("پنل وضعیت «فعال» را نشان می‌دهد", "فعال" in ads_html)

    if created:
        ad_id = int(created["id"])
        status, _, preview = admin.get(f"{panel}ads/{ad_id}/preview")
        check("پیش‌نمایش تبلیغ باز می‌شود", status == 200 and "ad-stage" in preview, str(status))
        check("پیش‌نمایش لینک مقصد را دارد", "https://example.com/neshane-test" in preview)

        status, _, media_body = admin.get(f"/media/ads/{created['media_file']}")
        check("فایل تبلیغ از مسیر عمومی سرو می‌شود", status == 200, str(status))

        # نمایش به بازدیدکنندهٔ تازه
        visitor = Client()
        status, _, ad_json = visitor.get("/api/ad?placement=popup")
        payload = json.loads(ad_json or "{}").get("ad") or {}
        check("تبلیغ برای بازدیدکننده برمی‌گردد", status == 200 and payload.get("id") == ad_id, str(status))
        check("اطلاعات نمایش درست است", payload.get("placement") == "both" and payload.get("skip_after") == 2)
        check("لینک و متن دکمه همراه تبلیغ است", payload.get("link") == "https://example.com/neshane-test")

        status, _, _ = visitor.post(f"/api/ad/{ad_id}/event", {"kind": "impression"})
        check("ثبت نمایش تبلیغ", status == 200, str(status))
        status, _, _ = visitor.post(f"/api/ad/{ad_id}/event", {"kind": "click"})
        check("ثبت کلیک تبلیغ", status == 200, str(status))
        stats = app_db_ads.ad_stats(ad_id)
        check("آمار نمایش و کلیک درست است", stats["impressions"] >= 1 and stats["clicks"] >= 1, str(stats))

        # بنر سرور-ساید صفحهٔ خانه (چون جای نمایش «هر دو» انتخاب شده)
        status, _, landing = visitor.get("/")
        check("بنر تبلیغ در صفحهٔ خانه می‌آید", status == 200 and "ad-banner" in landing, str(status))

        # خاموش‌کردن از پنل باید همان لحظه اثر بگذارد
        status, _, _ = admin.post(f"{panel}ads/{ad_id}/toggle", {})
        check("خاموش‌کردن تبلیغ", status == 303, str(status))
        status, _, ad_json = visitor.get("/api/ad?placement=popup")
        check("تبلیغ خاموش نمایش داده نمی‌شود", (json.loads(ad_json or "{}").get("ad")) is None, ad_json[:80])

        status, _, _ = admin.post(f"{panel}ads/{ad_id}/toggle", {})
        check("روشن‌کردن دوبارهٔ تبلیغ", status == 303, str(status))

        # حذف تبلیغ باید فایلش را هم ببرد
        media_file = str(created["media_file"])
        status, _, _ = admin.post(f"{panel}ads/{ad_id}/delete", {})
        check("حذف تبلیغ", status == 303, str(status))
        check("فایل رسانهٔ تبلیغ هم پاک شد", not app_ads.media_path(media_file).is_file())
        check("تبلیغ از دیتابیس پاک شد", app_db_ads.ad_get(ad_id) is None)

    status, _, ads_csv = admin.get(f"{panel}export/ads.csv")
    check("خروجی CSV تبلیغات", status == 200 and "impressions" in ads_csv, str(status))

    stranger = Client()
    status, location, _ = stranger.get(f"{panel}dashboard")
    check("کاربر مهمان به داشبورد پنل راه ندارد", status == 303 and location.endswith(panel), f"{status} {location}")
    status, _, _ = stranger.post(f"{panel}users/1/delete", {"confirm": "بله"})
    check("کاربر مهمان نمی‌تواند کاربر حذف کند", status == 303, str(status))

    print()
    if failures:
        print(f"!! {len(failures)} مورد شکست خورد: " + " | ".join(failures))
        return 1
    print("همهٔ مراحل موفق بود ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
