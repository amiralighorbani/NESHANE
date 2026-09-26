"""احراز هویت کاربر: ثبت‌نام با شمارهٔ تلفن + کد یک‌بارمصرف، ورود با نام کاربری و رمز.

قاعدهٔ امنیتی پروژه:
  * **شمارهٔ تلفن فقط برای ثبت‌نام است.** اولین تأیید کد، حساب را می‌سازد و در همان مسیر
    کاربر نام کاربری و رمز عبور انتخاب می‌کند.
  * از آن به بعد ورود فقط با **نام کاربری + رمز عبور** انجام می‌شود؛ پس کسی نمی‌تواند
    فقط با دانستن شمارهٔ تلفن دیگری به حساب او وارد شود.
  * برای شماره‌ای که حسابش کامل شده، اصلاً کد ورود صادر/نمایش داده نمی‌شود.

در این پروتوتایپ پیامک واقعی فرستاده نمی‌شود: کد در دیتابیس ذخیره می‌شود، در لاگ سرور
چاپ می‌شود و در صفحهٔ «پیامک‌های من» (/inbox) هم نمایش داده می‌شود تا بتوان ثبت‌نام کرد.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import random
import secrets
from typing import Tuple

from . import db

OTP_TTL_SECONDS = 180
MAX_ATTEMPTS = 5

# ورود با رمز عبور: هش PBKDF2-SHA256 (همان الگوی پنل ادمین) و قفل تلاش‌های ناموفق.
PBKDF2_ITERATIONS = 260000
HASH_ALGORITHM = "pbkdf2_sha256"
LOGIN_EVENT = "login"
LOGIN_FAIL_EVENT = "login_failed"
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_SECONDS = 15 * 60


def hash_password(password: str) -> str:
    """رمز را با نمک تصادفی هش می‌کند: `pbkdf2_sha256$iterations$salt$hash`."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", str(password or "").encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    ).hex()
    return f"{HASH_ALGORITHM}${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    """مقایسهٔ رمز با هش ذخیره‌شده (مقاوم به حملهٔ زمانی)."""
    try:
        algorithm, iterations, salt, digest = str(stored or "").split("$")
        if algorithm != HASH_ALGORITHM:
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", str(password or "").encode("utf-8"), bytes.fromhex(salt), int(iterations)
        ).hex()
    except (ValueError, TypeError, AttributeError):
        return False
    return hmac.compare_digest(candidate, digest)


def login_locked(user_id: int) -> Tuple[bool, int]:
    """آیا ورود با رمز برای این کاربر قفل است و چند ثانیه تا باز شدنش مانده؟"""
    since = db.now() - LOGIN_LOCK_SECONDS
    last_success = db.last_user_event_at(user_id, LOGIN_EVENT)
    if last_success and last_success > since:
        since = last_success
    if db.count_user_events_since(user_id, LOGIN_FAIL_EVENT, since) < LOGIN_MAX_FAILURES:
        return False, 0
    last_failure = db.last_user_event_at(user_id, LOGIN_FAIL_EVENT)
    if last_failure is None:
        return False, 0
    remaining = int(LOGIN_LOCK_SECONDS - (db.now() - last_failure))
    if remaining <= 0:
        return False, 0
    return True, remaining


def record_login_failure(user_id: int) -> None:
    db.log_event(LOGIN_FAIL_EVENT, user_id)

# در این پروتوتایپ پیامک واقعی فرستاده نمی‌شود، پس کد روی صفحه و در «پیامک‌های من»
# نمایش داده می‌شود. برای نسخهٔ واقعی با متغیر محیطی `NESHANE_SHOW_OTP=0` خاموشش کن
# تا کد فقط در لاگ سرور بماند و کلید ورود هر شماره، روی صفحه دیده نشود.
SHOW_CODE_ON_SCREEN = os.environ.get("NESHANE_SHOW_OTP", "1").strip().lower() not in {"0", "false", "no"}


def issue_code(phone: str) -> str:
    code = f"{random.randint(0, 999999):06d}"
    db.create_otp(phone, code, OTP_TTL_SECONDS)
    try:
        # فقط برای دیدن سریع کد در لاگ سرور؛ پیامک واقعی ارسال نمی‌شود.
        print(f"[neshane] login code for {phone}: {code}", flush=True)
    except Exception:
        pass
    return code


def can_register(phone: str) -> bool:
    """شماره برای ثبت‌نام آزاد است؟ (شماره‌ای که حسابش کامل شده، کد نمی‌گیرد)"""
    return not db.phone_has_credentials(phone)


def verify_code(phone: str, code: str) -> Tuple[bool, str]:
    record = db.latest_active_otp(phone)
    if not record:
        return False, "برای این شماره کد فعالی نیست. یک بار دیگر درخواست کن."
    if db.now() > float(record["expires_at"]):
        return False, "این کد منقضی شده است. کد تازه بگیر."
    if int(record["attempts"]) >= MAX_ATTEMPTS:
        return False, "تلاش‌های زیادی انجام شد. یک کد تازه بگیر."
    if str(record["code"]) != code:
        db.bump_otp_attempt(int(record["id"]))
        return False, "کد واردشده درست نیست."
    db.consume_otp(int(record["id"]))
    return True, ""


def code_for_phone(phone: str) -> str:
    """برای نمایش در «پیامک‌های من» (شبیه‌سازی پیامک).

    اگر `NESHANE_SHOW_OTP=0` باشد، کد روی صفحه نشان داده نمی‌شود. برای شماره‌ای که
    ثبت‌نامش کامل شده هم هیچ کدی نمایش داده نمی‌شود؛ چون آن حساب دیگر با پیامک
    وارد نمی‌شود و دیده‌شدن کد یعنی دیده‌شدن کلید ورودِ شمارهٔ کاربر.
    """
    if not SHOW_CODE_ON_SCREEN or not phone:
        return ""
    if db.phone_has_credentials(phone):
        return ""
    record = db.latest_active_otp(phone)
    if not record:
        return ""
    if db.now() > float(record["expires_at"]):
        return ""
    return str(record["code"])
