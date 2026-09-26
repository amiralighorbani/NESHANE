"""نشانه — پلتفرم فال و تست شخصیت (FastAPI + Jinja2، سرور-رندر، موبایل‌فرست)."""

from __future__ import annotations

import json
import sqlite3
import traceback
import uuid
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import admin, admin_auth, ads, auth, db, flash, forms as form_utils, life_stats, llm, pwa
from . import personality as personality_engine
from .content import astrology, lexicon
from .content import fortunes as fortune_pool
from .content import methods as method_catalogue
from .content import personality as test_catalogue
from .engine import (
    apply_ai,
    base_digest,
    build_reading,
    reading_from_payload,
    reading_payload,
    symbol_digest,
)
from .models import FortuneRequest, Reading
from .templating import BASE_DIR, render as _render, templates
from .utils import (
    MONTHS_FA,
    is_valid_jalali,
    jalali_label,
    jalali_to_gregorian,
    to_fa,
    today_label,
    weekday_fa,
    zodiac_key,
)

# --------------------------------------------------------------------------- #
# تنظیمات پاپ‌اپ امتیاز و نظر
# --------------------------------------------------------------------------- #

# کاربر بعد از این مدت نبودن، پاپ‌اپ امتیاز را می‌بیند.
FEEDBACK_IDLE_SECONDS = 24 * 3600
# یک کاربر حداکثر این فاصله یک‌بار دوباره پرسیده می‌شود (بیش از این زورگو می‌شود).
FEEDBACK_REPEAT_SECONDS = 30 * 86400
# سقف زمانی خواندن نیت و نوشتن خوانش شخصی.
# کاربر پشت پردهٔ «در حال گشودن» نشسته است، پس کوتاه نگه می‌داریم؛ اگر مدل در
# همین فرصت جواب ندهد، فال پایه نشان داده می‌شود (تجربهٔ کاربر خراب نمی‌شود).
READING_AI_TIMEOUT = 6.0

# مسیرهایی که روی آن‌ها پاپ‌اپ نشان داده نمی‌شود.
FEEDBACK_SKIP_PREFIXES = (
    "/static",
    "/api",
    "/health",
    "/sw.js",
    "/manifest",
    "/.well-known",
    "/feedback",
    "/inbox",
    "/logout",
    "/offline",
    "/favicon",
)

app = FastAPI(title="نشانه — فال و خودشناسی", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# فایل رسانهٔ تبلیغات. StaticFiles خودش مسیر را امن نگه می‌دارد و برای ویدیو
# درخواست‌های Range (پخش مرحله‌به‌مرحله) را هم درست پاسخ می‌دهد.
ADS_DIR = ads.MEDIA_DIR
ADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media/ads", StaticFiles(directory=ADS_DIR), name="ad-media")

# پنل ادمین روی مسیر مخفی خودش سوار می‌شود (هیچ‌جای برنامه به آن لینک نمی‌دهد).
app.include_router(admin.router)


@app.middleware("http")
async def admin_csrf_guard(request: Request, call_next):
    """درخواست‌های POST پنل ادمین را به همین دامنه محدود می‌کند (محافظت CSRF).

    کوکی پنل با SameSite=Lax ست می‌شود؛ این لایه جلوی ارسال فرم از دامنهٔ
    دیگر را هم می‌گیرد، حتی اگر مرورگری کوکی را بفرستد.
    """
    if request.method == "POST" and request.url.path.startswith(admin_auth.ADMIN_PATH):
        source = request.headers.get("origin") or request.headers.get("referer") or ""
        if source:
            host = request.headers.get("host", "")
            origin_host = urlparse(source).netloc
            if origin_host and host and origin_host != host:
                return Response("درخواست نامعتبر", status_code=403)
    return await call_next(request)


@app.middleware("http")
async def flash_guard(request: Request, call_next):
    """پیام‌های فلش را می‌خواند و بعد از نمایش، کوکی‌شان را پاک می‌کند.

    بدون پاک‌کردن، پیام با هر رفرش دوباره نشان داده می‌شد؛ با پاک‌کردنِ زودهنگام
    (قبل از رندر)، پیام به صفحهٔ مقصد هم نمی‌رسید. پس این‌جا فقط خوانده می‌شود و
    پاک‌کردن بعد از ساخت پاسخ انجام می‌گیرد — آن هم فقط وقتی صفحهٔ نهایی ساخته
    شده باشد، نه وقتی پاسخ یک ریدایرکت است (چون پیام باید به صفحهٔ بعد برود).
    """
    request.state.flash = flash.decode(request.cookies.get(flash.COOKIE))
    response = await call_next(request)
    if request.state.flash and response.status_code < 400:
        location = response.headers.get("location", "")
        if not (300 <= response.status_code < 400 and location):
            response.delete_cookie(flash.COOKIE, path="/")
    return response


@app.middleware("http")
async def feedback_gate_guard(request: Request, call_next):
    """فعالیت کاربر را ثبت می‌کند و در صورت لزوم پرچم پاپ‌اپ امتیاز را می‌گذارد.

    این وسط‌کار روی درخواست‌های GET صفحات انجام می‌شود؛ پاپ‌اپ روی APIها، فایل‌های
    ثابت و مسیرهای ثبت‌نام نشان داده نمی‌شود تا مزاحم نشود.
    """
    request.state.feedback_prompt = None
    path = request.url.path
    if (
        request.method == "GET"
        and admin_auth.ADMIN_PATH not in path
        and not path.startswith(FEEDBACK_SKIP_PREFIXES)
    ):
        try:
            request.state.feedback_prompt = _feedback_gate(request)
        except Exception:
            # هیچ‌وقت به‌خاطر یک پاپ‌اپ، صفحهٔ کاربر را نمی‌خوابانیم.
            request.state.feedback_prompt = None
    return await call_next(request)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """مرورگرها همیشه سراغ /favicon.ico می‌روند؛ به آیکون واقعی هدایتشان می‌کنیم."""
    return RedirectResponse("/static/favicon.svg", status_code=308)


# --------------------------------------------------------------------------- #
# PWA: مانیفست، سرویس‌ورکر و صفحهٔ آفلاین
# --------------------------------------------------------------------------- #


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest() -> Response:
    """مانیفست نصب اپ؛ با mime درست سرو می‌شود تا نصب PWA فعال شود."""
    return JSONResponse(
        pwa.MANIFEST,
        media_type="application/manifest+json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@app.get("/sw.js", include_in_schema=False)
def service_worker() -> Response:
    """سرویس‌ورکر از ریشه سرو می‌شود تا کل دامنه (نه فقط /static) را بگیرد."""
    return FileResponse(
        pwa.SERVICE_WORKER_PATH,
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
    )


@app.get("/offline", include_in_schema=False)
def offline_page() -> Response:
    """صفحهٔ جایگزین وقتی اینترنت قطع است (خودش بدون شبکه کار می‌کند)."""
    return FileResponse(pwa.OFFLINE_PATH, media_type="text/html")


@app.get("/.well-known/assetlinks.json", include_in_schema=False)
def assetlinks() -> Response:
    """اثبات مالکیت دامنه برای اپ اندروید (TWA).

    کروم با این فایل مطمئن می‌شود همان APK امضاشده صاحب این دامنه است و بعد صفحه
    را تمام‌صفحه و بدون نوار آدرس باز می‌کند.
    """
    return Response(
        pwa.assetlinks(),
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=3600"},
    )

SESSION_COOKIE = "neshane_session"
PHONE_COOKIE = "neshane_phone"

YEAR_CHOICES: List[int] = list(range(1300, 1421))
BIRTH_TIME_SLOTS: List[str] = [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in (0, 30)]


# --------------------------------------------------------------------------- #
# ابزارها / helpers
# --------------------------------------------------------------------------- #


def session_id(request: Request) -> Optional[str]:
    return request.cookies.get(SESSION_COOKIE)


def current_user(request: Request) -> Optional[Dict[str, Any]]:
    return db.session_user(session_id(request))


def profile_complete(user: Dict[str, Any]) -> bool:
    return bool(user.get("name")) and bool(user.get("jy"))


def has_identity(user: Dict[str, Any]) -> bool:
    """نام و نام خانوادگی ثبت شده است؟"""
    return len(str(user.get("name") or "").strip()) >= 2 and len(str(user.get("family") or "").strip()) >= 2


def has_birth(user: Dict[str, Any]) -> bool:
    return bool(user.get("jy"))


def onboarding_target(user: Dict[str, Any]) -> str:
    """قدم بعدی ثبت‌نام؛ رشتهٔ خالی یعنی حساب و پروفایل کامل است.

    ترتیب مهم است: تا وقتی کاربر نام کاربری و رمز ندارد، هر مسیر دیگری به همان قدم
    اول برمی‌گردد؛ پس کسی وسط ثبت‌نام بدون رمز رها نمی‌شود و از حساب بی‌رمز استفاده نمی‌کند.
    """
    if not db.has_credentials(user):
        return "/signup"
    if not has_identity(user):
        return "/welcome"
    if not has_birth(user):
        return "/birth"
    return ""


def full_name(user: Dict[str, Any]) -> str:
    return " ".join(part for part in (str(user.get("name") or ""), str(user.get("family") or "")) if part).strip()


# همهٔ صفحات از همین یک قیف رندر می‌شوند؛ `templating.render` پیام‌های توست را
# (فلش‌ها و خطاهای فرم) جمع می‌کند و به قالب می‌دهد.
render = _render


def redirect(url: str, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(url, status_code=status_code)


def base_context(request: Request, user: Optional[Dict[str, Any]] = None, active: str = "") -> Dict[str, Any]:
    return {
        "request": request,
        "user": user,
        "active": active,
        "today": today_label(),
        "weekday": weekday_fa(),
        "year_choices": YEAR_CHOICES,
        "birth_time_slots": BIRTH_TIME_SLOTS,
        "month_labels": [(index + 1, name) for index, name in enumerate(MONTHS_FA)],
        "feedback_prompt": getattr(request.state, "feedback_prompt", None),
    }


def require_login(request: Request) -> Optional[Response]:
    """محافظ مسیرهای خصوصی؛ و اگر کاربر وارد نشده باشد، دلیلش را هم می‌گوید.

    پیش‌تر کاربر بی‌هیچ توضیحی به صفحهٔ ورود پرت می‌شد و نمی‌دانست چه شد؛ این‌ک را
    یک پیام کوتاه همراه می‌کند.
    """
    if current_user(request) is None:
        return flash.redirect("/login", "برای دیدن این بخش باید وارد حساب‌ت شوی.", "info", "ورود لازم است")
    return None


def _feedback_gate(request: Request) -> Optional[Dict[str, Any]]:
    """آیا الان وقتِ پرسیدن «امتیاز و نظر» است؟

    شرط‌ها: کاربر وارد شده باشد، برای اولین بار بیش از ۲۴ ساعت غایب بوده باشد و
    در ۳۰ روز گذشته نپرسیده باشیم. به‌محض تصمیم به نمایش، «پرسیده‌شده» ثبت می‌شود
    تا با یک رفرش تکراری نشود.
    """
    user = current_user(request)
    if not user:
        return None
    user_id = int(user["id"])
    previous = db.touch_user_activity(user_id)
    if previous is None:
        return None
    idle = db.now() - float(previous)
    if idle < FEEDBACK_IDLE_SECONDS:
        return None
    asked_at = user.get("feedback_asked_at")
    if asked_at and (db.now() - float(asked_at)) < FEEDBACK_REPEAT_SECONDS:
        return None
    db.mark_feedback_asked(user_id)
    return {
        "user_id": user_id,
        "idle_hours": int(idle // 3600),
        "idle_days": int(idle // 86400),
        "name": str(user.get("name") or "").strip(),
        "readings": db.count_readings_by_user(user_id),
        "tests": db.count_attempts_by_user(user_id),
    }


def history_entries(user_id: int, limit: int = 30, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for row in db.user_readings(user_id, limit=limit, kind=kind):
        payload = row["payload"]
        entries.append(
            {
                "id": row["id"],
                "kind": row["kind"],
                "topic": row["topic"],
                "headline": row["headline"],
                "overall": row["overall"],
                "created_at": row["created_at"],
                "method": method_catalogue.METHODS.get(row["kind"], {}),
                "payload": payload,
            }
        )
    return entries


# --------------------------------------------------------------------------- #
# ویترین / public
# --------------------------------------------------------------------------- #


@app.get("/", response_class=HTMLResponse)
def landing(request: Request) -> Response:
    user = current_user(request)
    context = base_context(request, user, "home")
    context["sample_signs"] = [astrology.get_sign(key) for key in astrology.SIGN_ORDER[:6]]
    # نمونهٔ فال برای ویترین: یک کارت دست‌نویس ثابت (نه تصادفی) تا صفحه پایداری داشته باشد.
    cards = fortune_pool.effective()
    context["sample_fortune"] = next(
        (card for card in cards if card.get("source") == "curated" and int(card.get("id") or 0) == 10),
        cards[0] if cards else None,
    )
    # نمونهٔ «زندگی در عدد» برای بازدیدکنندهٔ مهمان (یا خود کاربر اگر پروفایل دارد).
    if user and has_birth(user):
        context["life_sample"] = life_stats.build(
            int(user.get("jy") or 1370),
            int(user.get("jm") or 1),
            int(user.get("jd") or 1),
            str(user.get("birth_time") or ""),
            str(user.get("city") or ""),
        )
    else:
        context["life_sample"] = life_stats.build(1372, 4, 18, "08:30", "شیراز")

    # بنر تبلیغاتی به‌صورت سمت‌سرور رندر می‌شود تا صفحه بی‌جهش (بدون پرشِ چیدمان)
    # بیاید؛ همان لحظهٔ رندر هم یک «نمایش» ثبت می‌شود.
    visitor = visitor_id(request)
    context["banner"] = None
    try:
        banner_ad = ads.pick(
            user_id=int(user["id"]) if user else None, visitor=visitor, placement="banner"
        )
        if banner_ad:
            context["banner"] = ads.public_payload(banner_ad)
            ads.record(
                int(banner_ad["id"]), "impression", user_id=int(user["id"]) if user else None, visitor=visitor
            )
    except Exception:
        context["banner"] = None

    response = render(request, "landing.html", context)
    if _visitor_changed(request, visitor):
        response.set_cookie(
            VISITOR_COOKIE, visitor, max_age=180 * 86400, httponly=True, samesite="lax", path="/"
        )
    return response


@app.get("/methods", response_class=HTMLResponse)
def methods_page(request: Request) -> Response:
    context = base_context(request, current_user(request), "methods")
    return render(request, "methods.html", context)


@app.get("/faq", response_class=HTMLResponse)
def faq_page(request: Request) -> Response:
    context = base_context(request, current_user(request), "faq")
    return render(request, "faq.html", context)


# --------------------------------------------------------------------------- #
# ثبت‌نام و ورود / auth
#
# قاعده: شمارهٔ تلفن فقط برای **ثبت‌نام** است (شمارهٔ یکتا + کد تأیید). بعد از تأیید کد،
# کاربر نام کاربری و رمز برمی‌گزیند و از آن به بعد فقط با «نام کاربری + رمز» وارد می‌شود.
# پس هیچ‌کس نمی‌تواند تنها با دانستن شمارهٔ تلفنِ دیگری سر از حساب او دربیاورد.
# --------------------------------------------------------------------------- #


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request) -> Response:
    """قدم اول ثبت‌نام: شمارهٔ موبایل (فقط برای شماره‌ای که حساب کاملی ندارد)."""
    if current_user(request):
        return redirect("/journey")
    context = base_context(request, None, "login")
    context["errors"] = []
    context["phone"] = ""
    return render(request, "register.html", context)


@app.post("/register", response_class=HTMLResponse)
def register_submit(request: Request, phone: str = Form("")) -> Response:
    normalized = form_utils.normalize_phone(phone)
    errors: List[str] = []
    if not normalized:
        errors.append("شمارهٔ موبایل را به شکل درست وارد کنید (مثلاً ۰۹۱۲۳۴۵۶۷۸۹).")
    elif not auth.can_register(normalized):
        # این شماره ثبت‌نامش کامل شده؛ کلید ورودش نام کاربری و رمز است، نه پیامک.
        errors.append("این شماره قبلاً ثبت‌نام کرده است. از صفحهٔ ورود، با نام کاربری و رمز عبور وارد شوید.")
    if errors:
        context = base_context(request, None, "login")
        context["errors"] = errors
        context["phone"] = phone
        return render(request, "register.html", context, status_code=422)

    auth.issue_code(normalized)
    response = flash.redirect(
        "/verify", "کد تأیید را فرستادیم؛ پیامکت را ببین.", "info", "یک قدم مانده"
    )
    response.set_cookie(PHONE_COOKIE, normalized, httponly=True, samesite="lax", max_age=600, path="/")
    return response


@app.get("/verify", response_class=HTMLResponse)
def verify_page(request: Request) -> Response:
    phone = request.cookies.get(PHONE_COOKIE, "")
    if not phone:
        return redirect("/register")
    context = base_context(request, None, "login")
    context["phone"] = phone
    context["errors"] = []
    context["code_hint"] = auth.code_for_phone(phone)
    return render(request, "verify.html", context)


@app.post("/verify", response_class=HTMLResponse)
def verify_submit(request: Request, code: str = Form("")) -> Response:
    phone = request.cookies.get(PHONE_COOKIE, "")
    if not phone:
        return redirect("/register")
    cleaned = form_utils.normalize_otp(code)
    ok, message = auth.verify_code(phone, cleaned)
    if not ok:
        context = base_context(request, None, "login")
        context["phone"] = phone
        context["errors"] = [message]
        context["code_hint"] = auth.code_for_phone(phone)
        return render(request, "verify.html", context, status_code=422)

    if not auth.can_register(phone):
        # شماره‌ای که حسابش کامل شده حتی کد هم نمی‌گیرد؛ این مسیر برایش بسته است.
        context = base_context(request, None, "login")
        context["phone"] = phone
        context["errors"] = ["این شماره ثبت‌نامش کامل شده است؛ با نام کاربری و رمز عبور وارد شوید."]
        return render(request, "verify.html", context, status_code=403)

    user = db.get_or_create_user(phone)
    sid = uuid.uuid4().hex
    db.create_session(sid, int(user["id"]))
    db.touch_login(int(user["id"]))
    db.log_event("login", int(user["id"]))

    # کاربر تازه به /signup (نام کاربری و رمز) می‌رود؛ حساب کامل‌شده به مسیر خودش.
    target = onboarding_target(user) or "/journey"
    response = flash.redirect(target, "شماره‌ات تأیید شد.", "success", "خوش آمدی")
    response.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30, path="/")
    response.delete_cookie(PHONE_COOKIE, path="/")
    return response


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> Response:
    """ورود کاربرانی که ثبت‌نامشان کامل شده: نام کاربری + رمز عبور."""
    if current_user(request):
        return redirect("/journey")
    context = base_context(request, None, "login")
    context["errors"] = []
    context["username"] = ""
    return render(request, "login.html", context)


@app.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
) -> Response:
    username = username.strip()
    invalid = "نام کاربری یا رمز عبور درست نیست."
    user = db.user_by_username(username)

    def rejected(message: str, status_code: int = 422) -> Response:
        context = base_context(request, None, "login")
        context["errors"] = [message]
        context["username"] = username
        return render(request, "login.html", context, status_code=status_code)

    if user is None or not db.has_credentials(user):
        # پیام یکسان با «رمز اشتباه» تا معلوم نشود کدام نام کاربری وجود دارد.
        if user is not None:
            auth.record_login_failure(int(user["id"]))
        return rejected(invalid)

    user_id = int(user["id"])
    locked, remaining = auth.login_locked(user_id)
    if locked:
        minutes = max(1, (remaining + 59) // 60)
        return rejected(f"تلاش‌های ناموفق زیاد بوده است؛ {to_fa(minutes)} دقیقهٔ دیگر امتحان کنید.", 429)

    if not auth.verify_password(password, str(user.get("password_hash") or "")):
        auth.record_login_failure(user_id)
        return rejected(invalid)

    sid = uuid.uuid4().hex
    db.create_session(sid, user_id)
    db.touch_login(user_id)
    db.log_event(auth.LOGIN_EVENT, user_id)

    greeting = str(user.get("name") or "").strip()
    response = flash.redirect(
        onboarding_target(user) or "/journey",
        "خوش برگشتی" + (f" {greeting}" if greeting else "") + "!",
        "success",
        "وارد شدی",
    )
    response.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="lax", max_age=60 * 60 * 24 * 30, path="/")
    response.delete_cookie(PHONE_COOKIE, path="/")
    return response


@app.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request) -> Response:
    """قدم پس از تأیید شماره: انتخاب نام کاربری و رمز عبور."""
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    if db.has_credentials(user):
        return redirect(onboarding_target(user) or "/journey")
    context = base_context(request, user, "signup")
    context["values"] = {"username": ""}
    context["errors"] = []
    return render(request, "signup.html", context)


@app.post("/signup", response_class=HTMLResponse)
def signup_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    confirm: str = Form(""),
) -> Response:
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    user_id = int(user["id"])
    if db.has_credentials(user):
        return redirect(onboarding_target(user) or "/journey")

    data, errors, values = form_utils.validate_credentials(
        {"username": username, "password": password, "confirm": confirm}
    )
    if data is not None and db.username_taken(data["username"], exclude_user_id=user_id):
        values = {"username": data["username"]}
        data = None
        errors = ["این نام کاربری قبلاً انتخاب شده است؛ یکی دیگر امتحان کنید."]
    if data is None:
        context = base_context(request, user, "signup")
        context["values"] = values
        context["errors"] = errors
        return render(request, "signup.html", context, status_code=422)

    # ثبت نهایی؛ اگر در همین لحظه کسی همان نام را گرفته باشد، `False` برمی‌گردد و
    # به‌جای خطای ۵۰۰ (یا نام کاربری تکراریِ بی‌صدا) پیام روشن نشان می‌دهیم.
    saved = db.set_credentials(user_id, data["username"], auth.hash_password(data["password"]))
    if not saved:
        context = base_context(request, user, "signup")
        context["values"] = {"username": data["username"]}
        context["errors"] = ["یک لحظه پیش همین نام کاربری گرفته شد؛ یکی دیگر امتحان کن."]
        return render(request, "signup.html", context, status_code=422)
    db.log_event("credentials_set", user_id)
    updated = db.get_user(user_id) or user
    return flash.redirect(
        onboarding_target(updated) or "/journey",
        f"خوش آمدی {data['username']}! حساب‌ت ساخته شد.",
        "success",
        "ثبت‌نام کامل شد",
    )


@app.get("/inbox", response_class=HTMLResponse)
def inbox_page(request: Request) -> Response:
    """شبیه‌سازی صندوق پیامک: کد ثبت‌نام اینجا دیده می‌شود (نه برای حساب‌های کامل)."""
    phone = request.cookies.get(PHONE_COOKIE, "")
    if not phone:
        user = current_user(request)
        # فقط کاربری که هنوز نام کاربری/رمز ندارد کدی می‌بیند؛ حساب کامل با پیامک وارد نمی‌شود.
        if user and not db.has_credentials(user):
            phone = str(user["phone"])
    code = auth.code_for_phone(phone) if phone else ""
    context = base_context(request, current_user(request), "")
    context["phone"] = phone
    context["code"] = code
    context["messages"] = (
        [
            {
                "sender": "نشانه",
                "icon": "fa-solid fa-star",
                "text": f"کد ثبت‌نام شما در نشانه: {to_fa(code) if code else '—'}  (اعتبار: ۳ دقیقه)",
            }
        ]
        if phone
        else []
    )
    return render(request, "inbox.html", context)


@app.get("/logout")
def logout(request: Request) -> Response:
    sid = session_id(request)
    if sid:
        db.drop_session(sid)
    response = flash.redirect("/", "بیرون آمدی؛ هر وقت خواستی برگرد.", "info", "خدانگهدار")
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


# --------------------------------------------------------------------------- #
# پروفایل / profile
# --------------------------------------------------------------------------- #


@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request) -> Response:
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    user_id = int(user["id"])

    results: List[Dict[str, Any]] = []
    for test_key, attempt in db.latest_results(user_id).items():
        result = personality_engine.build_result(test_key, attempt.get("answers") or {}, attempt_id=int(attempt["id"]))
        results.append(result.model_dump())
    results.sort(key=lambda item: item["test_key"])

    context = base_context(request, user, "profile")
    context["sign"] = None
    if user.get("jy"):
        context["sign"] = astrology.get_sign(user_sign_key(user))
    context["birth_label"] = jalali_label(int(user.get("jy") or 1370), int(user.get("jm") or 1), int(user.get("jd") or 1))
    context["results"] = results
    context["readings"] = history_entries(user_id, limit=12)
    context["reading_count"] = len(db.user_readings(user_id, limit=200))
    context["test_count"] = len(db.user_attempts(user_id, limit=200))
    context["full_name"] = full_name(user)
    context["pending_step"] = onboarding_target(user)
    context["life"] = (
        life_stats.build(
            int(user.get("jy") or 1370),
            int(user.get("jm") or 1),
            int(user.get("jd") or 1),
            str(user.get("birth_time") or ""),
            str(user.get("city") or ""),
        )
        if has_birth(user)
        else None
    )
    return render(request, "profile.html", context)


@app.get("/api/zodiac")
def zodiac_api(jy: int = 1370, jm: int = 1, jd: int = 1) -> Dict[str, Any]:
    """پیش‌نمایش زندهٔ برج در صفحهٔ اطلاعات تولد."""
    if not is_valid_jalali(jy, jm, jd):
        return {"ok": False}
    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
    sign = astrology.get_sign(zodiac_key(gm, gd))
    element = str(sign.get("element") or "")
    return {
        "ok": True,
        "name": str(sign.get("name") or ""),
        "symbol": str(sign.get("symbol") or ""),
        "element": element,
        "planet": str(sign.get("planet") or ""),
        "range": str(sign.get("range") or ""),
        "motto": str(sign.get("motto") or ""),
    }


# --------------------------------------------------------------------------- #
# ثبت‌نام دو مرحله‌ای: نام و فامیل، بعد اطلاعات تولد
# --------------------------------------------------------------------------- #


@app.get("/welcome", response_class=HTMLResponse)
def welcome_page(request: Request) -> Response:
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    context = base_context(request, user, "welcome")
    context["values"] = {
        "name": user.get("name") or "",
        "family": user.get("family") or "",
        "gender": user.get("gender") or "",
    }
    context["errors"] = []
    context["editing"] = has_identity(user)
    return render(request, "welcome.html", context)


@app.post("/welcome", response_class=HTMLResponse)
def welcome_submit(
    request: Request,
    name: str = Form(""),
    family: str = Form(""),
    gender: str = Form(""),
) -> Response:
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    data, errors, values = form_utils.validate_identity({"name": name, "family": family, "gender": gender})
    if data is None:
        context = base_context(request, user, "welcome")
        context["values"] = values
        context["errors"] = errors
        context["editing"] = has_identity(user)
        return render(request, "welcome.html", context, status_code=422)

    db.update_profile(
        int(user["id"]),
        name=data["name"],
        family=data["family"],
        gender=data["gender"],
    )
    db.log_event("identity_saved", int(user["id"]))
    if has_birth(user):
        return flash.redirect("/journey", f"{data['name']} جان، اسمت را ثبت کردم.", "success", "ثبت شد")
    return flash.redirect("/birth", "یک قدم دیگر تا فالت مانده.", "success", "ثبت شد")


@app.get("/birth", response_class=HTMLResponse)
def birth_page(request: Request) -> Response:
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    if not has_identity(user):
        return redirect("/welcome")
    context = base_context(request, user, "birth")
    context["values"] = {
        "jy": user.get("jy") or 1370,
        "jm": user.get("jm") or 1,
        "jd": user.get("jd") or 1,
        "birth_time": user.get("birth_time") or "",
        "city": user.get("city") or "",
    }
    context["errors"] = []
    context["editing"] = has_birth(user)
    context["preview_sign"] = astrology.get_sign(user_sign_key(user)) if user.get("jy") else None
    return render(request, "birth.html", context)


@app.post("/birth", response_class=HTMLResponse)
def birth_submit(
    request: Request,
    jy: str = Form("1370"),
    jm: str = Form("1"),
    jd: str = Form("1"),
    birth_time: str = Form(""),
    city: str = Form(""),
) -> Response:
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    if not has_identity(user):
        return redirect("/welcome")
    data, errors, values = form_utils.validate_birth(
        {"jy": jy, "jm": jm, "jd": jd, "birth_time": birth_time, "city": city}
    )
    if data is None:
        context = base_context(request, user, "birth")
        context["values"] = values
        context["errors"] = errors
        context["editing"] = has_birth(user)
        context["preview_sign"] = None
        return render(request, "birth.html", context, status_code=422)

    db.update_profile(
        int(user["id"]),
        jy=data["jy"],
        jm=data["jm"],
        jd=data["jd"],
        birth_time=data["birth_time"],
        city=data["city"],
    )
    db.log_event("birth_saved", int(user["id"]))
    return flash.redirect(
        "/life?first=1", "زادروزت ثبت شد؛ ببین ستاره‌ها چه می‌گویند.", "success", "ثبت شد"
    )


@app.get("/life", response_class=HTMLResponse)
def life_page(request: Request) -> Response:
    """«زندگی در عدد»: همهٔ آمار قابل‌محاسبه از تاریخ و ساعت تولد."""
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    if not has_birth(user):
        return redirect("/birth")
    stats = life_stats.build(
        int(user.get("jy") or 1370),
        int(user.get("jm") or 1),
        int(user.get("jd") or 1),
        str(user.get("birth_time") or ""),
        str(user.get("city") or ""),
    )
    context = base_context(request, user, "life")
    context["stats"] = stats
    context["full_name"] = full_name(user)
    context["is_first"] = request.query_params.get("first") == "1"
    return render(request, "life.html", context)


def user_sign_key(user: Dict[str, Any]) -> str:
    from .utils import jalali_to_gregorian, zodiac_key

    gy, gm, gd = jalali_to_gregorian(int(user.get("jy") or 1370), int(user.get("jm") or 1), int(user.get("jd") or 1))
    return zodiac_key(gm, gd)


# --------------------------------------------------------------------------- #
# سفر فال / fortune journey
# --------------------------------------------------------------------------- #


@app.get("/journey", response_class=HTMLResponse)
def journey_start(request: Request) -> Response:
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    pending = onboarding_target(user)
    if pending:
        return redirect(pending)
    context = base_context(request, user, "journey")
    context["step"] = 1
    context["draft"] = db.get_journey(int(user["id"]))
    return render(request, "journey_method.html", context)


@app.post("/journey/method", response_class=HTMLResponse)
def journey_method(request: Request, method: str = Form("hafez")) -> Response:
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    if method not in method_catalogue.METHODS:
        # انتخاب نامعتبر را بی‌صدا جای‌گزین نمی‌کنیم؛ کاربر باید بفهمد چه شد.
        return flash.redirect(
            "/journey", "این روش فال را نداریم؛ یکی از روش‌های فهرست را انتخاب کن.", "warning", "روش پیدا نشد"
        )
    db.set_journey(int(user["id"]), kind=method)
    return flash.redirect(
        "/journey/topic",
        f"روش «{method_catalogue.METHODS[method]['label']}» انتخاب شد.",
        "success",
        "مرحلهٔ ۱ از ۳",
    )


@app.get("/journey/topic", response_class=HTMLResponse)
def journey_topic_page(request: Request) -> Response:
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    draft = db.get_journey(int(user["id"]))
    if not draft.get("kind"):
        return flash.redirect("/journey", "اول روش فال را انتخاب کن.", "info", "یک قدم عقب‌تر")
    context = base_context(request, user, "journey")
    context["step"] = 2
    context["draft"] = draft
    context["method"] = method_catalogue.METHODS[draft["kind"]]
    return render(request, "journey_topic.html", context)


@app.post("/journey/topic", response_class=HTMLResponse)
def journey_topic(request: Request, topic: str = Form("general")) -> Response:
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    if topic not in lexicon.TOPICS:
        return flash.redirect(
            "/journey/topic", "این موضوع را نداریم؛ یکی از موضوع‌های فهرست را انتخاب کن.", "warning", "موضوع پیدا نشد"
        )
    db.set_journey(int(user["id"]), topic=topic)
    return flash.redirect(
        "/journey/intent",
        f"موضوع «{lexicon.TOPICS[topic]['label']}» انتخاب شد.",
        "success",
        "مرحلهٔ ۲ از ۳",
    )


@app.get("/journey/intent", response_class=HTMLResponse)
def journey_intent_page(request: Request) -> Response:
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    draft = db.get_journey(int(user["id"]))
    if not draft.get("kind") or not draft.get("topic"):
        return flash.redirect("/journey", "اول روش فال و موضوع را انتخاب کن.", "info", "یک قدم عقب‌تر")
    context = base_context(request, user, "journey")
    context["step"] = 3
    context["draft"] = draft
    context["method"] = method_catalogue.METHODS[draft["kind"]]
    context["topic"] = lexicon.TOPICS[draft["topic"]]
    context["intent"] = draft.get("intent") or ""
    return render(request, "journey_intent.html", context)


@app.post("/journey/intent", response_class=HTMLResponse)
def journey_intent(request: Request, intent: str = Form("")) -> Response:
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    user_id = int(user["id"])
    draft = db.get_journey(user_id)
    if not draft.get("kind") or not draft.get("topic"):
        return flash.redirect("/journey", "اول روش فال و موضوع را انتخاب کن.", "info", "یک قدم عقب‌تر")

    db.set_journey(user_id, intent=intent.strip()[:form_utils.MAX_INTENT])
    draft = db.get_journey(user_id)
    request_data, errors, values = form_utils.validate_fortune(draft, user)
    if request_data is None:
        context = base_context(request, user, "journey")
        context["step"] = 3
        context["draft"] = draft
        context["method"] = method_catalogue.METHODS[draft["kind"]]
        context["topic"] = lexicon.TOPICS[draft["topic"]]
        context["intent"] = values["intent"]
        context["errors"] = errors
        return render(request, "journey_intent.html", context, status_code=422)

    salt = uuid.uuid4().hex[:8]
    reading = build_reading(request_data, salt=salt)
    reading = _personalize_reading(reading, user_id)
    db.save_reading(_reading_row(reading), user_id, reading_payload(reading, request_data, salt))
    db.log_event("reading_created", user_id)
    return redirect(f"/r/{reading.token}?fresh=1")


def _personalize_reading(reading: Reading, user_id: int) -> Reading:
    """خوانش پایه را بر پایهٔ نیت کاربر شخصی می‌کند.

    هر خطایی (قطعی شبکه، اتمام سهم، پاسخ نامعتبر) بی‌صدا رد می‌شود و همان فال
    پایه نشان داده می‌شود؛ پس کاربر هیچ‌وقت صفحهٔ خطا نمی‌بیند.
    """
    try:
        ai = llm.personalize_reading(
            symbol_digest(reading),
            base_digest(reading),
            {
                "name": reading.name,
                "gender": reading.gender,
                "city": reading.city,
                "sign": f"{reading.sign.symbol} {reading.sign.name}",
                "topic": reading.topic_label,
                "intent": reading.intent,
                "method": reading.method_label,
                "mood": reading.mood.label,
                "mood_line": reading.mood.line,
                "overall": reading.overall,
                "overall_label": reading.overall_label,
                "donts": reading.donts,
            },
            user_id=user_id,
            timeout=READING_AI_TIMEOUT,
            retries_allowed=0,
        )
    except Exception:
        ai = None
    return apply_ai(reading, ai)


def _reading_row(reading: Any) -> Dict[str, Any]:
    return {
        "id": reading.token,
        "kind": reading.method_key,
        "topic_key": reading.topic_key,
        "intent": reading.intent,
        "headline": reading.headline,
        "overall": reading.overall,
    }


@app.get("/r/{token}", response_class=HTMLResponse)
def show_reading(request: Request, token: str) -> Response:
    """صفحهٔ فال؛ فقط صاحب فال می‌تواند آن را ببیند.

    توکن‌ها تصادفی‌اند، ولی توکنِ لو‌رفته نباید فالِ کاربر دیگری را نشان بدهد. پس
    مالکیت چک می‌شود و برای دیگران همان «پیدا نشد» می‌آید (نه ۴۰۳ که وجودش را لو
    بدهد).
    """
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    entry = db.get_reading(token)
    if not entry or int(entry.get("user_id") or 0) != int(user["id"]):
        return not_found(request)
    try:
        reading = reading_from_payload(entry["payload"])
    except Exception:
        # payload قدیمی/ناسازگار: به‌جای خطا، صفحهٔ پیدا‌نشد.
        return not_found(request)
    context = base_context(request, user, "")
    context["reading"] = reading
    context["is_fresh"] = request.query_params.get("fresh") == "1"
    context["back_url"] = "/readings"
    return render(request, "result.html", context)


@app.post("/r/{token}/again", response_class=HTMLResponse)
def again(request: Request, token: str) -> Response:
    """همان فال را با نمادهای تازه دوباره می‌گشاید."""
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    user_id = int(user["id"])
    entry = db.get_reading(token)
    if not entry or int(entry.get("user_id") or 0) != user_id:
        return flash.redirect(
            "/readings", "این فال پیدا نشد؛ شاید پاک شده باشد.", "warning", "فال پیدا نشد"
        )

    stored = entry.get("payload") or {}
    try:
        request_data = FortuneRequest.model_validate(stored.get("request") or {})
    except Exception:
        # اطلاعات ذخیره‌شده ناقص است؛ به‌جای ۵۰۰، به سفر فال برمی‌گردانیم.
        return flash.redirect(
            "/journey", "اطلاعات این فال کامل نیست؛ یک فال تازه بگیر.", "warning", "یک بار دیگر"
        )

    salt = uuid.uuid4().hex[:8]
    reading = build_reading(request_data, salt=salt)
    reading = _personalize_reading(reading, user_id)
    db.save_reading(_reading_row(reading), user_id, reading_payload(reading, request_data, salt))
    db.log_event("reading_created", user_id)
    return flash.redirect(
        f"/r/{reading.token}?fresh=1", "کارت‌ها از نو چیده شدند.", "success", "فال تازهٔ تو"
    )


# --------------------------------------------------------------------------- #
# امتیاز و نظر / rating + feedback
# --------------------------------------------------------------------------- #


def _wants_json(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "application/json" in accept or request.headers.get("x-requested-with") == "fetch"


@app.post("/feedback", response_class=HTMLResponse)
def feedback_submit(
    request: Request,
    rating: str = Form("0"),
    comment: str = Form(""),
    back: str = Form("/"),
) -> Response:
    """امتیاز و نظر کاربر را ذخیره می‌کند (هم با فرم ساده، هم با fetch)."""
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    user_id = int(user["id"])
    try:
        stars = int(form_utils.from_fa(str(rating).strip()) or 0)
    except (TypeError, ValueError):
        stars = 0
    stars = max(0, min(5, stars))
    text = str(comment or "").strip()[:2000]

    if not stars and not text:
        # بی‌صدا رد نمی‌کنیم؛ کاربر باید بداند چرا ثبت نشد.
        if _wants_json(request):
            return JSONResponse({"ok": False, "message": "لطفاً اول امتیازت را انتخاب کن."}, status_code=422)
        target = back if str(back).startswith("/") else "/"
        return flash.redirect(target, "لطفاً اول از یک تا پنج ستاره بده.", "warning", "امتیاز را انتخاب کن")

    db.save_feedback(user_id, stars, text)
    db.log_event("feedback_given", user_id)
    db.set_last_active(user_id)

    message = "ممنون که وقت گذاشتی؛ نظرت ثبت شد و توی مسیر نشانه استفاده می‌شود."
    if _wants_json(request):
        return JSONResponse({"ok": True, "rating": stars, "message": message})
    target = back if str(back).startswith("/") else "/"
    return flash.redirect(target, message, "success", "ثبت شد")


# --------------------------------------------------------------------------- #
# تبلیغات / ads
# --------------------------------------------------------------------------- #
#
# بازدیدکنندهٔ وارد‌شده با شناسهٔ کاربر و مهمان با یک کوکی تصادفی شمرده می‌شود؛
# همین شناسه پایهٔ سهمیهٔ روزانه و «دیگر نشان نده» است.

VISITOR_COOKIE = "nsh_visitor"


def visitor_id(request: Request) -> str:
    """شناسهٔ کوتاهِ مرورگرِ مهمان (اگر نباشد ساخته می‌شود)."""
    existing = (request.cookies.get(VISITOR_COOKIE) or "").strip()
    if existing and len(existing) <= 40 and existing.isalnum():
        return existing
    return uuid.uuid4().hex[:16]


def _visitor_changed(request: Request, visitor: str) -> bool:
    return (request.cookies.get(VISITOR_COOKIE) or "") != visitor


@app.get("/api/ad")
def ad_live(request: Request) -> Response:
    """تبلیغ مناسبِ همین لحظه را برای این بازدیدکننده برمی‌گرداند.

    اگر چیزی برای نشان‌دادن نباشد (خاموش، خارج از بازه، سهمیه پر)، ``ad: null``
    می‌آید و مرورگر بی‌صدا کاری نمی‌کند.
    """
    placement = (request.query_params.get("placement") or "popup").strip()
    if placement not in ads.PLACEMENTS:
        placement = "popup"

    user = current_user(request)
    visitor = visitor_id(request)
    try:
        picked = ads.pick(
            user_id=int(user["id"]) if user else None,
            visitor=visitor,
            placement=placement,
        )
    except Exception:
        # تبلیغ نباید باعث خطای صفحه شود.
        picked = None

    response = JSONResponse({"ad": ads.public_payload(picked) if picked else None})
    if _visitor_changed(request, visitor):
        response.set_cookie(
            VISITOR_COOKIE, visitor, max_age=180 * 86400, httponly=True, samesite="lax", path="/"
        )
    return response


@app.post("/api/ad/{ad_id}/event")
def ad_event(request: Request, ad_id: int, kind: str = Form("")) -> Response:
    """ثبت رویداد تبلیغ: نمایش، کلیک، ردکردن یا «دیگر نشان نده»."""
    user = current_user(request)
    event = (kind or "").strip()
    if event not in {"impression", "click", "skip", "dismiss"}:
        return JSONResponse({"ok": False, "error": "نوع رویداد نامعتبر است."}, status_code=422)
    if not db.ad_get(int(ad_id)):
        return JSONResponse({"ok": False, "error": "تبلیغ پیدا نشد."}, status_code=404)
    try:
        ads.record(int(ad_id), event, user_id=int(user["id"]) if user else None, visitor=visitor_id(request))
    except Exception:
        return JSONResponse({"ok": False}, status_code=200)
    return JSONResponse({"ok": True})


@app.get("/api/feedback/invite")
def feedback_invite(request: Request) -> Response:
    """متن متغیرِ پاپ‌اپ امتیاز؛ اگر مدل جواب ندهد، متن آمادهٔ سمت کلاینت می‌ماند."""
    user = current_user(request)
    if not user:
        return JSONResponse({"ok": False}, status_code=401)
    user_id = int(user["id"])
    context = {
        "name": str(user.get("name") or "").strip() or "دوست من",
        "readings": db.count_readings_by_user(user_id),
        "tests": db.count_attempts_by_user(user_id),
        "last_seen": "چند روز پیش",
    }
    try:
        invite = llm.feedback_invite(context, user_id)
    except Exception:
        invite = None
    return JSONResponse({"ok": bool(invite), "invite": invite or {}})


@app.get("/readings", response_class=HTMLResponse)
def readings_page(request: Request) -> Response:
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    context = base_context(request, user, "readings")
    context["readings"] = history_entries(int(user["id"]), limit=40)
    return render(request, "readings.html", context)


# --------------------------------------------------------------------------- #
# تست‌های شخصیت / personality tests
# --------------------------------------------------------------------------- #


@app.get("/tests", response_class=HTMLResponse)
def tests_page(request: Request) -> Response:
    context = base_context(request, current_user(request), "tests")
    return render(request, "tests.html", context)


@app.get("/tests/{key}", response_class=HTMLResponse)
def test_intro(request: Request, key: str) -> Response:
    if key not in test_catalogue.TESTS:
        return not_found(request)
    user = current_user(request)
    test = test_catalogue.get_test(key)
    context = base_context(request, user, "tests")
    context["test"] = test
    context["question_count"] = len(test["questions"])
    open_attempt = db.open_attempt(int(user["id"]), key) if user else None
    context["open_attempt"] = open_attempt
    session = db.latest_results(int(user["id"])).get(key) if user else None
    context["last_result"] = session
    return render(request, "test_intro.html", context)


@app.post("/tests/{key}/start", response_class=HTMLResponse)
def test_start(request: Request, key: str) -> Response:
    if key not in test_catalogue.TESTS:
        return not_found(request)
    guard = require_login(request)
    if guard:
        return redirect(f"/tests/{key}?need_login=1")
    user = current_user(request) or {}
    attempt_id = db.create_attempt(int(user["id"]), key)
    db.log_event("test_started", int(user["id"]))
    return flash.redirect(
        f"/tests/{key}/q/0?a={attempt_id}", "با آرامش جواب بده؛ عجله نکن.", "info", "شروع شد"
    )


def _owned_attempt(user_id: int, key: str, candidate: int = 0, *, create: bool = False) -> int:
    """شناسهٔ تلاشِ همین کاربر را برمی‌گرداند (۰ اگر نداشته باشد).

    چرا لازم است: شناسهٔ تلاش در آدرس می‌آید. اگر فقط به آن اعتماد کنیم، کاربری
    می‌تواند با تغییر عدد، جواب‌هایش را داخل تلاش کاربر دیگری بنویسد. پس هر بار
    مالکیت چک می‌شود و در صورت تخلف، تلاش خودش استفاده می‌شود.
    """
    if candidate:
        attempt = db.get_attempt(int(candidate))
        if attempt and int(attempt.get("user_id") or 0) == int(user_id):
            return int(candidate)
    existing = db.open_attempt(int(user_id), key)
    if existing:
        return int(existing["id"])
    if create:
        return int(db.create_attempt(int(user_id), key))
    return 0


@app.get("/tests/{key}/q/{index}", response_class=HTMLResponse)
def test_question(request: Request, key: str, index: int, a: int = 0) -> Response:
    if key not in test_catalogue.TESTS:
        return not_found(request)
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    user_id = int(user["id"])
    test = test_catalogue.get_test(key)
    questions = test["questions"]
    if not 0 <= index < len(questions):
        # نه بی‌صدا و نه صفحهٔ ۴۰۴: یا نتیجه‌اش را می‌بیند یا پیام روشن می‌گیرد.
        attempt_id = _owned_attempt(user_id, key, a)
        if attempt_id:
            return flash.redirect(
                f"/tests/{key}/result/{attempt_id}",
                "سؤال‌ها تمام شدند؛ نتیجه‌ات آماده است.",
                "success",
                "رسیدی به پایان",
            )
        return flash.redirect(
            f"/tests/{key}", "شمارهٔ سؤال نامعتبر بود؛ از اول شروع کن.", "warning", "سؤال پیدا نشد"
        )

    attempt_id = _owned_attempt(user_id, key, a)
    context = base_context(request, user, "tests")
    context["test"] = test
    context["question"] = questions[index]
    context["index"] = index
    context["total"] = len(questions)
    context["progress"] = round(100 * index / len(questions))
    context["attempt_id"] = attempt_id
    return render(request, "test_question.html", context)


@app.post("/tests/{key}/q/{index}", response_class=HTMLResponse)
def test_answer(request: Request, key: str, index: int, choice: str = Form("0"), a: int = Form(0)) -> Response:
    if key not in test_catalogue.TESTS:
        return not_found(request)
    guard = require_login(request)
    if guard:
        return guard
    user = current_user(request) or {}
    user_id = int(user["id"])
    test = test_catalogue.get_test(key)
    questions = test["questions"]
    if not 0 <= index < len(questions):
        attempt_id = _owned_attempt(user_id, key, a)
        if attempt_id:
            return flash.redirect(
                f"/tests/{key}/result/{attempt_id}", "سؤال‌ها تمام شدند؛ نتیجه‌ات آماده است.", "success", "پایان تست"
            )
        return flash.redirect(f"/tests/{key}", "شمارهٔ سؤال نامعتبر بود؛ از اول شروع کن.", "warning", "سؤال پیدا نشد")

    attempt_id = _owned_attempt(user_id, key, a, create=True)
    try:
        chosen = int(form_utils.from_fa(str(choice).strip()))
    except (TypeError, ValueError):
        chosen = -1

    # گزینه‌ای که وجود ندارد نباید در امتیازها بنشیند؛ کاربر را به همان سؤال
    # برمی‌گردانیم و با توست می‌گوییم چرا.
    option_count = len(questions[index].get("options") or [])
    if not 0 <= chosen < option_count:
        return flash.redirect(
            f"/tests/{key}/q/{index}?a={attempt_id}",
            "یکی از گزینه‌های همین سؤال را انتخاب کن.",
            "warning",
            "پاسخی انتخاب نشد",
        )
    db.save_answer(attempt_id, index, chosen)

    if index + 1 >= len(questions):
        attempt = db.get_attempt(attempt_id) or {"answers": {}}
        result = personality_engine.build_result(key, attempt["answers"], attempt_id=attempt_id)
        db.finish_attempt(attempt_id, result.code, result.scores)
        _annotate_result(result, attempt_id, user)
        db.log_event("test_finished", int(user["id"]))
        return redirect(f"/tests/{key}/result/{attempt_id}")
    return redirect(f"/tests/{key}/q/{index + 1}?a={attempt_id}")


@app.get("/tests/{key}/result/{attempt_id}", response_class=HTMLResponse)
def test_result(request: Request, key: str, attempt_id: int) -> Response:
    if key not in test_catalogue.TESTS:
        return not_found(request)
    guard = require_login(request)
    if guard:
        return redirect(f"/tests/{key}?need_login=1")
    attempt = db.get_attempt(attempt_id)
    if not attempt or int(attempt["user_id"]) != int((current_user(request) or {})["id"]):
        return not_found(request)
    result = personality_engine.build_result(key, attempt.get("answers") or {}, attempt_id=attempt_id)
    # تفسیرِ نوشته‌شده هنگام ثبت نتیجه را دوباره نشان می‌دهیم (بازتولید نمی‌کنیم).
    _attach_saved_note(result, attempt)
    context = base_context(request, current_user(request), "tests")
    context["test"] = test_catalogue.get_test(key)
    context["result"] = result
    return render(request, "test_result.html", context)


def _attach_saved_note(result: Any, attempt: Dict[str, Any]) -> Any:
    """متن شخصی ذخیرهشدهٔ همان تلاشِ تست را روی نتیجه می‌نشاند."""
    note = str(attempt.get("ai_note") or "")
    if not note:
        return result
    result.ai_note = note
    meta = attempt.get("ai_meta") or ""
    if meta:
        try:
            data = json.loads(meta)
            if isinstance(data, dict):
                result.ai_meta = data
                result.ai_next_step = str(data.get("next_step") or "")
        except (TypeError, ValueError):
            pass
    return result


def _annotate_result(result: Any, attempt_id: int, user: Dict[str, Any]) -> None:
    """تفسیر شخصیِ نتیجه را با مدل زبانی می‌نویسد و ذخیره می‌کند.

    شکست در این مرحله هیچ اثری روی نتیجهٔ تست ندارد؛ فقط بخش تفسیر خالی می‌ماند.
    """
    try:
        ai = llm.interpret_test(
            result.breakdown,
            {
                "name": full_name(user) or str(user.get("name") or "دوست من"),
                "test_label": result.test_label,
                "title": result.title,
                "code": result.code,
                "answered": result.answered,
                "tagline": result.tagline,
                "body": result.body,
            },
            user_id=int(user["id"]),
        )
    except Exception:
        ai = None
    if not ai:
        return
    result.ai_note = str(ai.get("note") or "")
    result.ai_next_step = str(ai.get("next_step") or "")
    result.ai_meta = {
        "provider": str(ai.get("provider") or ""),
        "provider_label": str(ai.get("provider_label") or ""),
        "model": str(ai.get("model") or ""),
        "latency_ms": int(ai.get("latency_ms") or 0),
        "tokens": int(ai.get("tokens") or 0),
        "used_fallback": bool(ai.get("used_fallback")),
        "next_step": str(ai.get("next_step") or ""),
    }
    db.set_attempt_ai_note(attempt_id, result.ai_note, json.dumps(result.ai_meta, ensure_ascii=False))


# --------------------------------------------------------------------------- #
# خطا / errors
# --------------------------------------------------------------------------- #
#
# اصل کار: کاربر هرگز صفحهٔ خشک مرورگر (مثل «Internal Server Error») نمی‌بیند.
# هر خطا به یک صفحهٔ برند‌دار با توستِ انیمیشنی تبدیل می‌شود که راه ادامه را
# نشان می‌دهد — و در لاگ سرور، Traceback کامل برای برنامه‌نویس می‌ماند.


def wants_json(request: Request) -> bool:
    """درخواست‌هایی که پاسخ HTML برایشان بی‌فایده است (فراخوانی‌های JS)."""
    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept and "text/html" not in accept:
        return True
    if (request.headers.get("x-requested-with") or "").lower() == "fetch":
        return True
    return request.url.path.startswith(("/api/", admin_auth.ADMIN_PATH + "api/"))


def not_found(request: Request) -> Response:
    context = base_context(request, current_user(request), "")
    return render(request, "404.html", context, status_code=404)


def error_page(
    request: Request,
    *,
    status_code: int,
    heading: str,
    lead: str,
    message: str,
    icon: str = "fa-solid fa-triangle-exclamation",
    accent: str = "#b57613",
    kind: str = "warning",
) -> Response:
    """صفحهٔ خطای یکدست با یک توست که علت را می‌گوید."""
    if wants_json(request):
        return JSONResponse(
            {"ok": False, "error": message, "status": status_code, "kind": kind},
            status_code=status_code,
        )
    context = base_context(request, current_user(request), "")
    context["heading"] = heading
    context["lead"] = lead
    context["note"] = message
    context["icon"] = icon
    context["accent"] = accent
    context["toasts"] = [{"message": message, "kind": kind, "title": ""}]
    return render(request, "error.html", context, status_code=status_code)


@app.exception_handler(404)
def handle_404(request: Request, exc: Exception) -> Response:
    return not_found(request)


@app.exception_handler(sqlite3.IntegrityError)
def handle_integrity(request: Request, exc: sqlite3.IntegrityError) -> Response:
    """تضاد داده (نوعاً نام کاربری/شمارهٔ تکراری که همزمان فرستاده شده).

    بدون اینجا، خطای قید یکتاییِ دیتابیس به ۵۰۰ تبدیل می‌شد و صفحه می‌ترکید؛
    دقیقاً همان چیزی که وقتی دو نفر یک نام را همزمان می‌گیرند یا کاربر روی موبایل
    دکمه را دو بار می‌زند اتفاق می‌افتد.
    """
    traceback.print_exc()
    return error_page(
        request,
        status_code=409,
        heading="این اطلاعات همین حالا ثبت شد",
        lead="به‌نظر می‌رسد همین لحظه با یک درخواست دیگر تکراری شده است.",
        message="لطفاً یک بار دیگر تلاش کن؛ اگر نام کاربری بود، نام دیگری انتخاب کن.",
        icon="fa-solid fa-user-lock",
        accent="#b57613",
        kind="warning",
    )


@app.exception_handler(sqlite3.Error)
def handle_db_error(request: Request, exc: sqlite3.Error) -> Response:
    """مشکل دیتابیس (قفل موقت فایل، کمبود فضا و…): صفحهٔ آرام به‌جای ۵۰۰."""
    traceback.print_exc()
    return error_page(
        request,
        status_code=503,
        heading="یک لحظه نفس بکش",
        lead="پایگاه داده همین لحظه نمی‌تواند پاسخ بدهد؛ داده‌ای از دست نرفته است.",
        message="چند ثانیه دیگر دوباره تلاش کن.",
        icon="fa-solid fa-database",
        accent="#b57613",
        kind="warning",
    )


@app.exception_handler(StarletteHTTPException)
def handle_http_error(request: Request, exc: StarletteHTTPException) -> Response:
    """خطاهای استاندارد HTTP (۴۰۴، ۴۰۵، ۴۰۳، …) با ظاهر خودمان."""
    code = int(getattr(exc, "status_code", 500) or 500)
    if code == 404:
        return not_found(request)
    if code == 405:
        return error_page(
            request,
            status_code=405,
            heading="این آدرس با این روش باز نمی‌شود",
            lead="شاید لینک را دستی تایپ کرده‌ای یا فرم قدیمی مانده است.",
            message="به صفحهٔ اصلی برگرد و مسیر را از نو انتخاب کن.",
            icon="fa-solid fa-route",
            accent="#6b4fbb",
            kind="info",
        )
    if code == 403:
        return error_page(
            request,
            status_code=403,
            heading="این مسیر برای تو باز نیست",
            lead="برای دیدن این صفحه باید وارد حساب خودت شوی.",
            message="یک بار وارد شو و دوباره تلاش کن.",
            icon="fa-solid fa-lock",
            accent="#b57613",
            kind="warning",
        )
    return error_page(
        request,
        status_code=code,
        heading="مسیر عوض شد",
        lead="درخواست تو به سرانجام نرسید.",
        message="به خانه برگرد و از آنجا مسیر را ادامه بده.",
        icon="fa-solid fa-compass",
        accent="#8a8f98",
        kind="info",
    )


@app.exception_handler(Exception)
def handle_unexpected(request: Request, exc: Exception) -> Response:
    """آخرین تور محافظ: هر خطای پیش‌بینی‌نشده به صفحهٔ آرام تبدیل می‌شود.

    Traceback در لاگ سرور می‌ماند (تا رفع شود)، ولی کاربر فقط پیام انسانی می‌بیند
    و برنامهٔ در حال اجرا سالم می‌ماند.
    """
    traceback.print_exc()
    return error_page(
        request,
        status_code=500,
        heading="یک تکه‌اش جا ماند",
        lead="خطای پیش‌بینی‌نشده‌ای رخ داد؛ تیم نشانه آن را ثبت کرد.",
        message="یک بار دیگر تلاش کن؛ اگر تکرار شد به ما خبر بده.",
        icon="fa-solid fa-heart-crack",
        accent="#c2384a",
        kind="error",
    )


@app.get("/health")
def health() -> Dict[str, Any]:
    pool = fortune_pool.source_info()
    return {
        "status": "ok",
        "app": "neshane",
        "users": db.count_users(),
        "readings": db.count_readings(),
        "readings_by_kind": db.count_readings_by_kind(),
        "methods": len(method_catalogue.METHODS),
        "tests": len(test_catalogue.TESTS),
        "fortunes": {
            "total": pool["total"],
            "web": pool["web"],
            "curated": pool["curated"],
            "custom": pool["custom"],
            "edited": pool["edited"],
            "hidden": pool["hidden"],
        },
    }


db.init()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8020, reload=False)
