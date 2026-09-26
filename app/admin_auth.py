"""احراز هویت پنل ادمین: مسیر مخفی، پسورد هش‌شده و قفل تلاش‌های ناموفق.

نکات امنیتی:
  * **هیچ رمز و مسیر مخفی‌ای در سورس نیست.** همه از `.env` (کامیت نمی‌شود) یا از
    متغیر محیطی سرور می‌آید:
        NESHANE_ADMIN_USER / NESHANE_ADMIN_PASSWORD
        NESHANE_ADMIN_PATH   (مسیر مخفی پنل)
  * اگر «NESHANE_ADMIN_PASSWORD» ندهی، می‌توانی فقط هش بدهی:
        NESHANE_ADMIN_PASSWORD_HASH  (+ NESHANE_ADMIN_PASSWORD_SALT)
    هش با PBKDF2-SHA256 و ۲۶۰٫۰۰۰ تکرار ساخته می‌شود.
  * مقایسهٔ هش با `hmac.compare_digest` انجام می‌شود (مقاوم به حملهٔ زمانی).
  * اگر هیچ رمزی تنظیم نشده باشد، ورود به پنل **بسته** است (fail-closed)؛ هیچ
    رمز پیش‌فرضی وجود ندارد که کسی بتواند حدس بزند.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time
from typing import Optional, Tuple

from . import db


def _clean_secret(value: Optional[str]) -> str:
    return (value or "").strip()

# --------------------------------------------------------------------------- #
# مسیر مخفی پنل
# --------------------------------------------------------------------------- #

# اگر مسیری تنظیم نشده باشد، این مسیر جایگزین می‌شود. خودِ مسیر واقعی در `.env`
# است تا از اسکنرها پنهان بماند؛ این مقدار فقط برای «بالا آمدن بدون تنظیمات» است
# و چون رمز پیش‌فرضی وجود ندارد، خطرناک نیست.
FALLBACK_ADMIN_PATH = "/panel/"


def _clean_path(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return FALLBACK_ADMIN_PATH
    if not text.startswith("/"):
        text = "/" + text
    if not text.endswith("/"):
        text = text + "/"
    # فقط نویسه‌های امن مسیر؛ جلوی تزریق الگوی مسیر را می‌گیرد.
    if not re.fullmatch(r"/[A-Za-z0-9._~/-]{1,120}/", text):
        return FALLBACK_ADMIN_PATH
    return text


ADMIN_PATH = _clean_path(os.environ.get("NESHANE_ADMIN_PATH", ""))

# --------------------------------------------------------------------------- #
# کاربر و پسورد
# --------------------------------------------------------------------------- #

PBKDF2_ITERATIONS = 260000

ADMIN_USER = _clean_secret(os.environ.get("NESHANE_ADMIN_USER", ""))

# رمز می‌تواند ساده (متن در `.env`) یا فقط هش‌شده باشد؛ هر دو حالت پشتیبانی می‌شود.
_ENV_PASSWORD = _clean_secret(os.environ.get("NESHANE_ADMIN_PASSWORD", ""))
_ENV_HASH = _clean_secret(os.environ.get("NESHANE_ADMIN_PASSWORD_HASH", "")).lower()
_ENV_SALT = _clean_secret(os.environ.get("NESHANE_ADMIN_PASSWORD_SALT", "")).lower()

# نمکِ در حافظه: چون هشِ مرجع و هشِ ورودی در همین پروسه ساخته می‌شوند، یک نمک
# تصادفیِ هر اجرا کافی است و باعث می‌شود هیچ نمکی هم در سورس نماند.
_RUNTIME_SALT_HEX = secrets.token_hex(16)

SESSION_COOKIE = "neshane_admin"
SESSION_TTL_SECONDS = 60 * 60 * 8  # هشت ساعت
MAX_FAILED_ATTEMPTS = 5
LOCK_WINDOW_SECONDS = 15 * 60
FAIL_EVENT = "admin_login_failed"
OK_EVENT = "admin_login_ok"


def _derive(password: str, salt_hex: str) -> str:
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        salt = salt_hex.encode("utf-8")
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return digest.hex()


def configured() -> bool:
    """آیا رمز مدیر تنظیم شده است؟ (بدون رمز، پنل قفل می‌ماند.)"""
    return bool(ADMIN_USER and (_ENV_PASSWORD or _ENV_HASH))


def _expected() -> Tuple[str, str]:
    """(هش مرجع، نمک مرجع) — از رمزِ ساده یا از هشِ ذخیره‌شده."""
    if _ENV_HASH:
        return _ENV_HASH, (_ENV_SALT or _RUNTIME_SALT_HEX)
    if _ENV_PASSWORD:
        return _derive(_ENV_PASSWORD, _RUNTIME_SALT_HEX), _RUNTIME_SALT_HEX
    return "", _RUNTIME_SALT_HEX


def verify_credentials(username: str, password: str) -> bool:
    if not configured():
        return False
    expected_hash, salt = _expected()
    user_ok = hmac.compare_digest(str(username or ""), ADMIN_USER)
    password_ok = hmac.compare_digest(_derive(str(password or ""), salt), expected_hash)
    # هر دو شرط محاسبه می‌شوند تا زمان پاسخ، وجود کاربر را لو ندهد.
    return bool(user_ok and password_ok)


def make_hash(password: str, salt_hex: Optional[str] = None) -> Tuple[str, str]:
    """ساخت هش و نمک برای گذاشتن در `.env` (با `NESHANE_ADMIN_PASSWORD_HASH`)."""
    salt = salt_hex or secrets.token_hex(16)
    return _derive(password, salt), salt


# --------------------------------------------------------------------------- #
# قفل تلاش ناموفق
# --------------------------------------------------------------------------- #


def failed_attempts() -> int:
    """تلاش‌های ناموفقِ پس از آخرین ورود موفق، در پنجرهٔ قفل."""
    since = time.time() - LOCK_WINDOW_SECONDS
    last_success = db.last_event_at(OK_EVENT)
    if last_success and last_success > since:
        since = last_success
    return db.count_events_since(FAIL_EVENT, since)


def is_locked() -> Tuple[bool, int]:
    """آیا ورود قفل است و چند ثانیه تا باز شدنش مانده؟"""
    if failed_attempts() < MAX_FAILED_ATTEMPTS:
        return False, 0
    last = db.last_event_at(FAIL_EVENT)
    if last is None:
        return False, 0
    remaining = int(LOCK_WINDOW_SECONDS - (time.time() - last))
    if remaining <= 0:
        return False, 0
    return True, remaining


def record_failure() -> None:
    db.log_event(FAIL_EVENT)


def record_success(client_ip: str = "", user_agent: str = "") -> str:
    """نشست تازه می‌سازد، نشست‌های منقضی را پاک می‌کند و لاگ می‌گذارد."""
    token = secrets.token_urlsafe(32)
    db.purge_admin_sessions()
    db.create_admin_session(token, SESSION_TTL_SECONDS, ip=client_ip, user_agent=user_agent)
    db.log_event(OK_EVENT)
    return token


def current_admin(request) -> Optional[str]:
    """اگر نشست ادمین معتبر باشد، توکن را برمی‌گرداند."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    session = db.admin_session(token)
    return token if session else None


def logout(token: Optional[str]) -> None:
    if token:
        db.drop_admin_session(token)
