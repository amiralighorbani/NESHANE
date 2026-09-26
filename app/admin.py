"""پنل ادمین نشانه: همهٔ دادهٔ کاربران، از پروفایل و نیت تا جواب سوال‌ها و نتیجهٔ تست.

پنل روی یک مسیر مخفی نصب می‌شود (`admin_auth.ADMIN_PATH`) و هیچ‌جای برنامه به آن
لینک داده نشده است. ورود با نام کاربری و پسورد انجام می‌شود، پسورد هش شده است و
پنج تلاش ناموفق، ورود را ربع ساعت قفل می‌کند.

قابلیت‌ها:
  * داشبورد آماری (کاربر، خوانش، تست، رویداد)
  * فهرست و جست‌وجوی کاربران
  * پروندهٔ کامل هر کاربر: پروفایل، پیش‌نویس سفر، همهٔ فال‌ها،
    همهٔ تلاش‌های تست با متن سوال و گزینهٔ انتخاب‌شده، رویدادها
  * ویرایش پروفایل، حذف کاربر، صفرکردن پیش‌نویس سفر
  * ساخت لینک فال برای یک کاربر
  * فهرست همهٔ خوانش‌ها + مشاهدهٔ کامل یک خوانش
  * اطلاعات استخر فال (۱۱۷ کارت)
  * خروجی CSV کاربران، خوانش‌ها، تست‌ها و رویدادها
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
import urllib.parse
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from . import admin_auth, ads, db, forms as form_utils, life_stats, llm, prompts as prompt_book
from .content import fortunes as fortune_pool
from .content import lexicon
from .content import methods as method_catalogue
from .content import personality as test_catalogue
from .engine import build_reading, reading_from_payload, reading_payload
from .models import FortuneRequest
from .templating import render
from .utils import MONTHS_FA, gregorian_to_jalali, jalali_label, to_fa, today_label, weekday_fa

router = APIRouter()

BASE = admin_auth.ADMIN_PATH
PAGE_SIZE = 25


# --------------------------------------------------------------------------- #
# ابزارها / helpers
# --------------------------------------------------------------------------- #


def stamp_label(value: Any) -> str:
    """زمان یونیکس را به تاریخ جلالی خوانا تبدیل می‌کند."""
    try:
        moment = datetime.fromtimestamp(float(value))
    except (TypeError, ValueError, OSError):
        return "—"
    jy, jm, jd = gregorian_to_jalali(moment.year, moment.month, moment.day)
    clock = f"{moment.hour:02d}:{moment.minute:02d}"
    return f"{to_fa(jd)} {MONTHS_FA[jm - 1]} {to_fa(jy)} • {to_fa(clock)}"


def _admin_context(request: Request, active: str, **extra: Any) -> Dict[str, Any]:
    context: Dict[str, Any] = {
        "request": request,
        "admin_path": BASE,
        "active": active,
        "today": today_label(),
        "weekday": weekday_fa(),
        "stamp": stamp_label,
        "pool": fortune_pool.source_info(),
        "user_total": db.count_users_filtered(),
        # شمارندهٔ تبلیغ‌های فعال روی آیتم منو؛ سبک است و هر صفحه لازمش دارد.
        "ad_active": db.count_ads(active_only=True),
        "METHODS": method_catalogue.METHODS,
        "METHOD_ORDER": method_catalogue.METHOD_ORDER,
        "TESTS": test_catalogue.TESTS,
        "TEST_ORDER": test_catalogue.TEST_ORDER,
        "TOPICS": lexicon.TOPICS,
    }
    context.update(extra)
    return context


def page(request: Request, template: str, active: str, status_code: int = 200, **extra: Any) -> Response:
    response = render(request, template, _admin_context(request, active, **extra), status_code=status_code)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


def guard(request: Request) -> Optional[Response]:
    """اگر نشست ادمین معتبر نباشد، به صفحهٔ ورود پنل برمی‌گرداند."""
    if admin_auth.current_admin(request) is None:
        return redirect(BASE)
    return None


def redirect(url: str, status_code: int = 303) -> RedirectResponse:
    return RedirectResponse(url, status_code=status_code)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "")[:64]


def payload_of(row: Dict[str, Any]) -> Dict[str, Any]:
    """payload یک خوانش را از رشتهٔ JSON به دیکشنری تبدیل می‌کند."""
    payload = row.get("payload")
    if isinstance(payload, dict):
        return payload
    try:
        return json.loads(payload or "{}")
    except (TypeError, ValueError):
        return {}


def age_of(user: Dict[str, Any]) -> Optional[int]:
    if not user.get("jy"):
        return None
    jy, _, _ = gregorian_to_jalali(*_today_tuple())
    return max(0, int(jy) - int(user["jy"]))


def _today_tuple() -> tuple:
    now = datetime.now()
    return (now.year, now.month, now.day)


def answer_rows(test_key: str, answers: Dict[str, Any]) -> List[Dict[str, Any]]:
    """جواب‌های ثبت‌شدهٔ یک تست را با متن سوال و متن گزینه برمی‌گرداند."""
    test = test_catalogue.TESTS.get(test_key) or {}
    questions = test.get("questions") or []
    rows: List[Dict[str, Any]] = []
    for index, question in enumerate(questions):
        raw = answers.get(str(index))
        chosen_text = None
        if raw is not None:
            options = question.get("options") or []
            try:
                position = int(raw)
            except (TypeError, ValueError):
                position = -1
            if 0 <= position < len(options):
                chosen_text = str(options[position].get("text") or "")
        rows.append(
            {
                "number": index + 1,
                "question": str(question.get("text") or ""),
                "answer": chosen_text,
                "raw": "" if raw is None else str(raw),
            }
        )
    return rows


def attempt_view(attempt: Dict[str, Any]) -> Dict[str, Any]:
    test = test_catalogue.TESTS.get(str(attempt["test_key"])) or {}
    answers = attempt.get("answers") or {}
    rows = answer_rows(str(attempt["test_key"]), answers)
    answered = sum(1 for row in rows if row["answer"])
    return {
        "id": int(attempt["id"]),
        "test_key": str(attempt["test_key"]),
        "test_label": str(test.get("label") or attempt["test_key"]),
        "icon": str(test.get("icon") or "fa-solid fa-brain"),
        "created_label": stamp_label(attempt.get("created_at")),
        "finished_label": stamp_label(attempt["completed_at"]) if attempt.get("completed_at") else "",
        "completed": bool(attempt.get("completed_at")),
        "result_key": str(attempt.get("result_key") or ""),
        "result_label": str(
            (test.get("results") or {}).get(str(attempt.get("result_key") or ""), {}).get("title") or ""
        ),
        "scores": attempt.get("scores") or {},
        "rows": rows,
        "answered": answered,
        "total": len(rows),
    }


def csv_response(filename: str, header: List[str], rows: List[List[Any]]) -> Response:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    # BOM تا اکسل فارسی، UTF-8 را درست بخواند.
    body = "\ufeff" + buffer.getvalue()
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --------------------------------------------------------------------------- #
# ورود / login
# --------------------------------------------------------------------------- #


@router.get(BASE, response_class=HTMLResponse)
def admin_home(request: Request) -> Response:
    if admin_auth.current_admin(request):
        return dashboard(request)
    return page(
        request,
        "admin/login.html",
        "login",
        username="",
        error="",
        configured=admin_auth.configured(),
    )


@router.post(BASE, response_class=HTMLResponse)
def admin_login(request: Request, username: str = Form(""), password: str = Form("")) -> Response:
    # اگر رمز مدیر تنظیم نشده باشد (فایل .env نیست)، ورود بسته است و دلیلش گفته می‌شود
    # تا با «رمز اشتباه» قاطی نشود.
    if not admin_auth.configured():
        return page(
            request,
            "admin/login.html",
            "login",
            status_code=503,
            username=username,
            error="رمز مدیر تنظیم نشده است؛ فایل .env را از روی .env.example بساز.",
            configured=False,
        )

    locked, remaining = admin_auth.is_locked()
    if locked:
        minutes = max(1, remaining // 60)
        return page(
            request,
            "admin/login.html",
            "login",
            status_code=429,
            username=username,
            error=f"تلاش‌های ناموفق زیاد بود. حدود {to_fa(minutes)} دقیقه دیگر امتحان کن.",
            configured=True,
        )

    if not admin_auth.verify_credentials(username, password):
        admin_auth.record_failure()
        left = max(0, admin_auth.MAX_FAILED_ATTEMPTS - admin_auth.failed_attempts())
        note = f" {to_fa(left)} تلاش دیگر باقی مانده." if 0 < left < admin_auth.MAX_FAILED_ATTEMPTS else ""
        return page(
            request,
            "admin/login.html",
            "login",
            status_code=401,
            username=username,
            error="نام کاربری یا پسورد درست نیست." + note,
            configured=True,
        )

    token = admin_auth.record_success(client_ip(request), request.headers.get("user-agent", ""))
    response = redirect(BASE)
    response.set_cookie(
        admin_auth.SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        max_age=admin_auth.SESSION_TTL_SECONDS,
        path=BASE,
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post(f"{BASE}logout")
def admin_logout(request: Request) -> Response:
    admin_auth.logout(request.cookies.get(admin_auth.SESSION_COOKIE))
    response = redirect(BASE)
    response.delete_cookie(admin_auth.SESSION_COOKIE, path=BASE)
    return response


# --------------------------------------------------------------------------- #
# داشبورد / dashboard
# --------------------------------------------------------------------------- #


@router.get(f"{BASE}dashboard", response_class=HTMLResponse)
def dashboard(request: Request) -> Response:
    blocked = guard(request)
    if blocked:
        return blocked

    day_ago = time.time() - 24 * 60 * 60
    week_ago = time.time() - 7 * 24 * 60 * 60
    kind_counts = db.count_readings_by_kind()
    kind_rows = [
        {
            "key": key,
            "label": str(method_catalogue.METHODS.get(key, {}).get("label") or key),
            "icon": str(method_catalogue.METHODS.get(key, {}).get("icon") or "fa-solid fa-star"),
            "count": count,
        }
        for key, count in sorted(kind_counts.items(), key=lambda item: -item[1])
    ]

    attempt_counts = db.count_attempts_by_test()
    test_rows = [
        {
            "key": key,
            "label": str(test_catalogue.TESTS.get(key, {}).get("label") or key),
            "count": attempt_counts.get(key, 0),
        }
        for key in test_catalogue.TEST_ORDER
    ]

    stats = {
        "users": db.count_users_filtered(),
        "users_24h": db.count_users_since(day_ago),
        "users_7d": db.count_users_since(week_ago),
        "readings": db.count_readings_filtered(),
        "attempts": db.count_attempts(completed_only=True),
        "attempts_open": db.count_attempts() - db.count_attempts(completed_only=True),
        "sessions": db.count_admin_sessions(),
        "failed_logins": db.count_events_since(admin_auth.FAIL_EVENT, week_ago),
        "ok_logins": db.count_events_since(admin_auth.OK_EVENT, week_ago),
    }

    return page(
        request,
        "admin/dashboard.html",
        "dashboard",
        stats=stats,
        kind_rows=kind_rows,
        test_rows=test_rows,
        recent_users=[
            {**user, "created_label": stamp_label(user.get("created_at"))}
            for user in db.all_users(limit=8)
        ],
        recent_readings=db.all_readings(limit=8),
        drafts=db.journey_drafts(limit=6),
    )


# --------------------------------------------------------------------------- #
# کاربران / users
# --------------------------------------------------------------------------- #


@router.get(f"{BASE}users", response_class=HTMLResponse)
def users_page(request: Request, q: str = "", page_number: int = 1) -> Response:
    blocked = guard(request)
    if blocked:
        return blocked

    search = (q or "").strip()[:60]
    page_number = max(1, page_number)
    total = db.count_users_filtered(search)
    rows = db.all_users(limit=PAGE_SIZE, offset=(page_number - 1) * PAGE_SIZE, search=search)
    for row in rows:
        row["created_label"] = stamp_label(row.get("created_at"))
        row["last_login_label"] = stamp_label(row["last_login_at"]) if row.get("last_login_at") else "—"
        row["reading_count"] = len(db.user_readings(int(row["id"]), limit=200))
        row["attempt_count"] = len(db.user_attempts(int(row["id"]), limit=200))
        row["complete"] = bool(row.get("name")) and bool(row.get("jy"))

    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    return page(
        request,
        "admin/users.html",
        "users",
        users=rows,
        q=search,
        page_number=page_number,
        pages=pages,
        total=total,
    )


@router.get(f"{BASE}users/{{user_id}}", response_class=HTMLResponse)
def user_detail(request: Request, user_id: int) -> Response:
    blocked = guard(request)
    if blocked:
        return blocked

    user = db.get_user(user_id)
    if not user:
        return page(request, "admin/missing.html", "users", status_code=404)

    readings = []
    for row in db.user_readings(user_id, limit=60):
        readings.append(
            {
                "id": str(row["id"]),
                "kind": str(row["kind"]),
                "kind_label": str(method_catalogue.METHODS.get(row["kind"], {}).get("label") or row["kind"]),
                "topic": str(row["topic"]),
                "topic_label": str(lexicon.TOPICS.get(row["topic"], {}).get("label") or row["topic"]),
                "headline": str(row["headline"] or ""),
                "intent": str(row.get("intent") or ""),
                "overall": int(row.get("overall") or 0),
                "created_label": stamp_label(row.get("created_at")),
            }
        )

    attempts = [attempt_view(attempt) for attempt in db.all_attempts(user_id, limit=40)]
    draft = db.get_journey(user_id)
    events = [
        {"name": str(event["name"]), "created_label": stamp_label(event["created_at"])}
        for event in db.user_events(user_id, limit=50)
    ]

    life = (
        life_stats.build(
            int(user.get("jy") or 1370),
            int(user.get("jm") or 1),
            int(user.get("jd") or 1),
            str(user.get("birth_time") or ""),
            str(user.get("city") or ""),
        )
        if user.get("jy")
        else None
    )
    full = " ".join(part for part in (str(user.get("name") or ""), str(user.get("family") or "")) if part).strip()

    return page(
        request,
        "admin/user.html",
        "users",
        user=user,
        user_id=user_id,
        full_name=full or "بدون نام",
        life=life,
        birth_label=jalali_label(int(user.get("jy") or 1370), int(user.get("jm") or 1), int(user.get("jd") or 1))
        if user.get("jy")
        else "—",
        age=age_of(user),
        readings=readings,
        attempts=attempts,
        events=events,
        draft=draft,
        draft_kind_label=str(method_catalogue.METHODS.get(str(draft.get("kind") or ""), {}).get("label") or "—"),
        draft_topic_label=str(lexicon.TOPICS.get(str(draft.get("topic") or ""), {}).get("label") or "—"),
        created_label=stamp_label(user.get("created_at")),
        last_login_label=stamp_label(user["last_login_at"]) if user.get("last_login_at") else "—",
    )


@router.get(f"{BASE}users/{{user_id}}/dossier", response_class=HTMLResponse)
def user_dossier(request: Request, user_id: int) -> Response:
    """پروندهٔ کامل کاربر: هر چه از او گرفته‌ایم، یک‌جا و آمادهٔ چاپ برای خودش."""
    blocked = guard(request)
    if blocked:
        return blocked

    user = db.get_user(user_id)
    if not user:
        return page(request, "admin/missing.html", "users", status_code=404)

    readings = []
    for row in db.user_readings(user_id, limit=40):
        try:
            readings.append(
                {
                    "reading": reading_from_payload(payload_of(row)),
                    "created_label": stamp_label(row.get("created_at")),
                    "kind_label": str(method_catalogue.METHODS.get(row["kind"], {}).get("label") or row["kind"]),
                }
            )
        except Exception:  # نوشتهٔ فال ناقص یا قدیمی: رد می‌شویم
            continue

    attempts = [attempt_view(attempt) for attempt in db.all_attempts(user_id, limit=40) if attempt.get("completed_at")]
    draft = db.get_journey(user_id)
    life = None
    if user.get("jy"):
        life = life_stats.build(
            int(user.get("jy") or 1370),
            int(user.get("jm") or 1),
            int(user.get("jd") or 1),
            str(user.get("birth_time") or ""),
            str(user.get("city") or ""),
        )

    full = " ".join(part for part in (str(user.get("name") or ""), str(user.get("family") or "")) if part).strip()
    return page(
        request,
        "admin/dossier.html",
        "users",
        user=user,
        user_id=user_id,
        full_name=full or str(user.get("phone") or "کاربر"),
        birth_label=jalali_label(int(user.get("jy") or 1370), int(user.get("jm") or 1), int(user.get("jd") or 1))
        if user.get("jy")
        else "ثبت نشده",
        created_label=stamp_label(user.get("created_at")),
        last_login_label=stamp_label(user["last_login_at"]) if user.get("last_login_at") else "—",
        life=life,
        readings=readings,
        attempts=attempts,
        draft=draft,
        draft_kind_label=str(method_catalogue.METHODS.get(str(draft.get("kind") or ""), {}).get("label") or "—"),
        draft_topic_label=str(lexicon.TOPICS.get(str(draft.get("topic") or ""), {}).get("label") or "—"),
    )


@router.post(f"{BASE}users/{{user_id}}/profile", response_class=HTMLResponse)
def user_profile_save(
    request: Request,
    user_id: int,
    name: str = Form(""),
    gender: str = Form(""),
    jy: str = Form("1370"),
    jm: str = Form("1"),
    jd: str = Form("1"),
    birth_time: str = Form(""),
    city: str = Form(""),
) -> Response:
    blocked = guard(request)
    if blocked:
        return blocked
    if not db.get_user(user_id):
        return page(request, "admin/missing.html", "users", status_code=404)

    data, errors, _ = form_utils.validate_profile(
        {"name": name, "jy": jy, "jm": jm, "jd": jd, "gender": gender, "birth_time": birth_time, "city": city}
    )
    if data is None:
        return redirect(f"{BASE}users/{user_id}?error=" + ",".join(errors[:2]).replace(" ", "+"))

    db.update_profile(
        user_id,
        name=data["name"],
        gender=data["gender"],
        jy=data["jy"],
        jm=data["jm"],
        jd=data["jd"],
        birth_time=data["birth_time"],
        city=data["city"],
    )
    db.log_event("admin_profile_edited", user_id)
    return redirect(f"{BASE}users/{user_id}?ok=profile")


@router.post(f"{BASE}users/{{user_id}}/fortune", response_class=HTMLResponse)
def user_fortune(request: Request, user_id: int, method: str = Form("hafez"), topic: str = Form("general")) -> Response:
    """برای کاربر یک خوانش تازه می‌سازد و لینکش را نشان می‌دهد."""
    blocked = guard(request)
    if blocked:
        return blocked
    user = db.get_user(user_id)
    if not user:
        return page(request, "admin/missing.html", "users", status_code=404)

    if method not in method_catalogue.METHODS:
        method = "hafez"
    if topic not in lexicon.TOPICS:
        topic = "general"

    request_data = FortuneRequest(
        name=str(user.get("name") or "دوست"),
        gender=str(user.get("gender") or ""),
        jy=int(user.get("jy") or 1370),
        jm=int(user.get("jm") or 1),
        jd=int(user.get("jd") or 1),
        birth_time=str(user.get("birth_time") or ""),
        city=str(user.get("city") or ""),
        topic=topic,
        intent=str((db.get_journey(user_id) or {}).get("intent") or ""),
        method=method,
    )
    salt = f"admin-{int(time.time())}"
    reading = build_reading(request_data, salt=salt)
    db.save_reading(
        {
            "id": reading.token,
            "kind": reading.method_key,
            "topic_key": reading.topic_key,
            "intent": reading.intent,
            "headline": reading.headline,
            "overall": reading.overall,
        },
        user_id,
        reading_payload(reading, request_data, salt),
    )
    db.log_event("admin_reading_created", user_id)
    return redirect(f"{BASE}readings/{reading.token}?ok=created")


@router.post(f"{BASE}users/{{user_id}}/journey/reset", response_class=HTMLResponse)
def user_journey_reset(request: Request, user_id: int) -> Response:
    blocked = guard(request)
    if blocked:
        return blocked
    db.set_journey(user_id, kind="", topic="", intent="")
    db.log_event("admin_journey_reset", user_id)
    return redirect(f"{BASE}users/{user_id}?ok=journey")


@router.post(f"{BASE}users/{{user_id}}/delete", response_class=HTMLResponse)
def user_delete(request: Request, user_id: int, confirm: str = Form("")) -> Response:
    blocked = guard(request)
    if blocked:
        return blocked
    if (confirm or "").strip().lower() not in {"yes", "بله", "1", "true"}:
        return redirect(f"{BASE}users/{user_id}?error=confirm")
    user = db.get_user(user_id)
    if not user:
        return page(request, "admin/missing.html", "users", status_code=404)
    db.delete_user(user_id)
    db.log_event("admin_user_deleted")
    return redirect(f"{BASE}users?ok=deleted")


# --------------------------------------------------------------------------- #
# خوانش‌ها / readings
# --------------------------------------------------------------------------- #


@router.get(f"{BASE}readings", response_class=HTMLResponse)
def readings_page(request: Request, kind: str = "", page_number: int = 1) -> Response:
    blocked = guard(request)
    if blocked:
        return blocked

    kind_filter = kind if kind in method_catalogue.METHODS else ""
    page_number = max(1, page_number)
    total = db.count_readings_filtered(kind_filter or None)
    rows = db.all_readings(limit=PAGE_SIZE, offset=(page_number - 1) * PAGE_SIZE, kind=kind_filter or None)

    owners: Dict[int, Dict[str, Any]] = {}
    readings = []
    for row in rows:
        owner_id = int(row["user_id"])
        if owner_id not in owners:
            owners[owner_id] = db.get_user(owner_id) or {}
        owner = owners[owner_id]
        payload = payload_of(row)
        reading_part = payload.get("reading") or {}
        block_lines: List[str] = []
        for block in (reading_part.get("blocks") or [])[:1]:
            block_lines = [str(line) for line in (block.get("lines") or [])]
        readings.append(
            {
                "id": str(row["id"]),
                "user_id": owner_id,
                "user_label": str(owner.get("name") or "—"),
                "phone": str(owner.get("phone") or "—"),
                "kind": str(row["kind"]),
                "kind_label": str(method_catalogue.METHODS.get(row["kind"], {}).get("label") or row["kind"]),
                "topic_label": str(lexicon.TOPICS.get(row["topic"], {}).get("label") or row["topic"]),
                "headline": str(row["headline"] or ""),
                "intent": str(row.get("intent") or ""),
                "overall": int(row.get("overall") or 0),
                "created_label": stamp_label(row.get("created_at")),
                "lines": block_lines,
            }
        )

    pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    return page(
        request,
        "admin/readings.html",
        "readings",
        readings=readings,
        kind=kind_filter,
        page_number=page_number,
        pages=pages,
        total=total,
    )


@router.get(f"{BASE}readings/{{token}}", response_class=HTMLResponse)
def reading_detail(request: Request, token: str) -> Response:
    blocked = guard(request)
    if blocked:
        return blocked
    entry = db.get_reading(token)
    if not entry:
        return page(request, "admin/missing.html", "readings", status_code=404)

    user = db.get_user(int(entry["user_id"])) or {}
    reading = reading_from_payload(entry["payload"])
    return page(
        request,
        "admin/reading.html",
        "readings",
        reading=reading,
        owner=user,
        token=token,
        created_label=stamp_label(entry.get("created_at")),
        raw=json.dumps(entry["payload"], ensure_ascii=False, indent=2)[:20000],
    )


@router.post(f"{BASE}readings/{{token}}/delete", response_class=HTMLResponse)
def reading_delete(request: Request, token: str, user_id: int = Form(0)) -> Response:
    blocked = guard(request)
    if blocked:
        return blocked
    db.delete_reading(token)
    db.log_event("admin_reading_deleted")
    if user_id:
        return redirect(f"{BASE}users/{user_id}?ok=reading-deleted")
    return redirect(f"{BASE}readings?ok=deleted")


# --------------------------------------------------------------------------- #
# استخر فال و رویدادها / pool & audit
# --------------------------------------------------------------------------- #


@router.get(f"{BASE}fortunes", response_class=HTMLResponse)
def fortunes_page(
    request: Request,
    theme: str = "",
    source: str = "",
    q: str = "",
    show: str = "all",
    page_number: int = 1,
) -> Response:
    blocked = guard(request)
    if blocked:
        return blocked

    search = (q or "").strip()[:60]
    all_cards = _all_pool_cards()
    cards = [card for card in all_cards if _card_matches(card, theme, source, search, show)]

    page_number = max(1, page_number)
    pages = max(1, (len(cards) + PAGE_SIZE - 1) // PAGE_SIZE)
    page_number = min(page_number, pages)
    start = (page_number - 1) * PAGE_SIZE

    info = fortune_pool.source_info()
    return page(
        request,
        "admin/fortunes.html",
        "fortunes",
        info=info,
        cards=cards[start : start + PAGE_SIZE],
        total_cards=len(cards),
        page_number=page_number,
        pages=pages,
        theme=theme,
        source=source,
        q=search,
        show=show,
        ok=request.query_params.get("ok", ""),
        error=request.query_params.get("error", ""),
    )


def _all_pool_cards() -> List[Dict[str, Any]]:
    """کارت‌های پایه + ساخته/ویرایش‌شده‌ها + پنهان‌شده‌ها (برای فهرست پنل)."""
    cards: Dict[str, Dict[str, Any]] = {
        str(card["key"]): {**card, "hidden": False} for card in fortune_pool.effective()
    }
    for row in db.fortune_cards():
        if not row.get("hidden"):
            continue
        base = dict(fortune_pool.BY_KEY.get(str(row["key"])) or {})
        base.update(
            {
                "key": str(row["key"]),
                "hidden": True,
                "builtin": bool(row.get("builtin")),
                "title": str(row.get("title") or base.get("title") or "فال آماده"),
                "source": "edited" if row.get("builtin") else "custom",
                "source_label": fortune_pool.EDITED_LABEL if row.get("builtin") else fortune_pool.CUSTOM_LABEL,
            }
        )
        cards[str(row["key"])] = base
    return list(cards.values())


def _card_matches(card: Dict[str, Any], theme: str, source: str, search: str, show: str) -> bool:
    if show == "hidden" and not card.get("hidden"):
        return False
    if show == "visible" and card.get("hidden"):
        return False
    if source and str(card.get("source")) != source:
        return False
    if theme and str(card.get("theme")) != theme and str(card.get("theme_label")) != theme:
        return False
    if search:
        haystack = " ".join(
            [
                str(card.get("title") or ""),
                str(card.get("interpretation") or ""),
                " ".join(str(line) for line in card.get("verses") or []),
                " ".join(str(word) for word in card.get("keywords") or []),
            ]
        )
        if search not in haystack:
            return False
    return True


@router.get(f"{BASE}fortunes/new", response_class=HTMLResponse)
def fortune_new(request: Request) -> Response:
    blocked = guard(request)
    if blocked:
        return blocked
    return page(
        request,
        "admin/fortune_form.html",
        "fortunes",
        card={"key": "", "title": "", "theme_label": "", "verses": [], "keywords": [], "interpretation": "", "guidance": ""},
        mode="new",
        themes=sorted(fortune_pool.source_info()["themes"].keys()),
        error=request.query_params.get("error", ""),
        ok=request.query_params.get("ok", ""),
    )


@router.get(f"{BASE}fortunes/{{key}}/edit", response_class=HTMLResponse)
def fortune_edit(request: Request, key: str) -> Response:
    blocked = guard(request)
    if blocked:
        return blocked
    card = next((item for item in _all_pool_cards() if str(item["key"]) == key), None)
    if not card:
        return page(request, "admin/missing.html", "fortunes", status_code=404)
    return page(
        request,
        "admin/fortune_form.html",
        "fortunes",
        card=card,
        mode="edit",
        themes=sorted(fortune_pool.source_info()["themes"].keys()),
        overridden=bool(db.fortune_card(key)),
        error=request.query_params.get("error", ""),
        ok=request.query_params.get("ok", ""),
    )


@router.post(f"{BASE}fortunes/{{key}}/revert")
def fortune_revert(request: Request, key: str) -> Response:
    """ویرایش روی یک کارت آماده را برمی‌گرداند به متن اصلی پروژه."""
    blocked = guard(request)
    if blocked:
        return blocked
    if not fortune_pool.BY_KEY.get(key):
        return redirect(f"{BASE}fortunes?error=notfound")
    db.delete_fortune_card(key)
    fortune_pool.invalidate()
    db.log_event("admin_fortune_reverted")
    return redirect(f"{BASE}fortunes?ok=reverted")


@router.post(f"{BASE}fortunes/save")
def fortune_save(
    request: Request,
    key: str = Form(""),
    title: str = Form(""),
    theme_label: str = Form(""),
    verses: str = Form(""),
    keywords: str = Form(""),
    interpretation: str = Form(""),
    guidance: str = Form(""),
) -> Response:
    """ساخت یا ویرایش یک کارت فال."""
    blocked = guard(request)
    if blocked:
        return blocked

    lines = [line.strip() for line in (verses or "").replace("\r", "").split("\n") if line.strip()]
    words = [word.strip() for word in re.split(r"[,،\n]", keywords or "") if word.strip()]
    text = (interpretation or "").strip()
    target = (key or "").strip()

    if not lines or not text:
        back = f"{BASE}fortunes/{target}/edit" if target else f"{BASE}fortunes/new"
        return redirect(f"{back}?error=required")

    builtin = False
    if target:
        existing = next((item for item in _all_pool_cards() if str(item["key"]) == target), None)
        if existing:
            builtin = bool(existing.get("builtin"))
        elif not db.fortune_card(target):
            return redirect(f"{BASE}fortunes?error=notfound")
    else:
        target = f"custom-{uuid.uuid4().hex[:10]}"

    db.save_fortune_card(
        target,
        title=(title or "").strip() or "فال تازه",
        theme_label=(theme_label or "").strip(),
        verses=lines,
        keywords=words,
        interpretation=text,
        guidance=(guidance or "").strip(),
        builtin=builtin,
        hidden=False,
    )
    fortune_pool.invalidate()
    db.log_event("admin_fortune_saved")
    return redirect(f"{BASE}fortunes?ok=saved")


@router.post(f"{BASE}fortunes/{{key}}/delete")
def fortune_delete(request: Request, key: str) -> Response:
    """کارت ساختهٔ مدیر را حذف می‌کند و کارت آماده را پنهان می‌کند."""
    blocked = guard(request)
    if blocked:
        return blocked

    row = db.fortune_card(key)
    base = fortune_pool.BY_KEY.get(key)
    if base or (row and row.get("builtin")):
        # کارت آمادهٔ پروژه: پنهان می‌شود تا قابل بازگرداندن باشد.
        db.save_fortune_card(key, builtin=True, hidden=True)
        fortune_pool.invalidate()
        db.log_event("admin_fortune_hidden")
        return redirect(f"{BASE}fortunes?ok=hidden")

    db.delete_fortune_card(key)
    fortune_pool.invalidate()
    db.log_event("admin_fortune_deleted")
    return redirect(f"{BASE}fortunes?ok=deleted")


@router.post(f"{BASE}fortunes/{{key}}/restore")
def fortune_restore(request: Request, key: str) -> Response:
    """کارت پنهان‌شده را برمی‌گرداند."""
    blocked = guard(request)
    if blocked:
        return blocked

    row = db.fortune_card(key)
    if row and (row.get("verses") or row.get("interpretation")):
        db.save_fortune_card(
            key,
            title=str(row.get("title") or ""),
            theme_label=str(row.get("theme_label") or ""),
            verses=row.get("verses") or [],
            keywords=row.get("keywords") or [],
            interpretation=str(row.get("interpretation") or ""),
            guidance=str(row.get("guidance") or ""),
            builtin=bool(row.get("builtin")),
            hidden=False,
        )
    else:
        # سطری که فقط برای پنهان‌کردن ساخته شده بود، حذف می‌شود.
        db.delete_fortune_card(key)
    fortune_pool.invalidate()
    db.log_event("admin_fortune_restored")
    return redirect(f"{BASE}fortunes?ok=restored")


@router.get(f"{BASE}audit", response_class=HTMLResponse)
def audit_page(request: Request) -> Response:
    blocked = guard(request)
    if blocked:
        return blocked

    events = []
    for event in db.recent_events(limit=150):
        events.append(
            {
                "name": str(event["name"]),
                "created_label": stamp_label(event["created_at"]),
                "user_id": event.get("user_id"),
                "user_label": str(event.get("user_name") or event.get("phone") or "—"),
            }
        )
    return page(
        request,
        "admin/audit.html",
        "audit",
        events=events,
        drafts=db.journey_drafts(limit=15),
    )


# --------------------------------------------------------------------------- #
# خروجی CSV / exports
# --------------------------------------------------------------------------- #


@router.get(f"{BASE}users/{{user_id}}/dossier.csv")
def user_dossier_csv(request: Request, user_id: int) -> Response:
    """همهٔ داده‌ای که از یک کاربر داریم، در یک فایل CSV سه‌ستونی."""
    blocked = guard(request)
    if blocked:
        return blocked

    user = db.get_user(user_id)
    if not user:
        return page(request, "admin/missing.html", "users", status_code=404)

    rows: List[List[Any]] = []
    rows.append(["پروفایل", "موبایل", user.get("phone") or ""])
    rows.append(["پروفایل", "نام", user.get("name") or ""])
    rows.append(["پروفایل", "نام خانوادگی", user.get("family") or ""])
    rows.append(["پروفایل", "جنسیت", user.get("gender") or ""])
    if user.get("jy"):
        rows.append(["پروفایل", "تاریخ تولد (شمسی)", jalali_label(int(user["jy"]), int(user["jm"]), int(user["jd"]))])
    rows.append(["پروفایل", "ساعت تولد", user.get("birth_time") or ""])
    rows.append(["پروفایل", "شهر", user.get("city") or ""])
    rows.append(["پروفایل", "تاریخ ثبت‌نام", stamp_label(user.get("created_at"))])

    draft = db.get_journey(user_id)
    rows.append(["نیت", "روش", str(draft.get("kind") or "")])
    rows.append(["نیت", "موضوع", str(draft.get("topic") or "")])
    rows.append(["نیت", "متن نیت", str(draft.get("intent") or "")])

    if user.get("jy"):
        life = life_stats.build(
            int(user["jy"]), int(user["jm"]), int(user["jd"]),
            str(user.get("birth_time") or ""), str(user.get("city") or ""),
        )
        for card in life["identity"]:
            rows.append(["زندگی در عدد", str(card["label"]), f"{card['value']} — {card['hint']}".strip(" —")])
        for group in life["groups"]:
            for card in group["cards"]:
                rows.append([str(group["title"]), str(card["label"]), f"{card['value']} — {card['hint']}".strip(" —")])

    for row in db.user_readings(user_id, limit=500):
        try:
            reading = reading_from_payload(payload_of(row))
            verses = " / ".join(
                line for block in reading.blocks for line in (block.lines or [])
            )
            rows.append([
                "فال",
                f"{reading.method_label} | {reading.topic_label} | {stamp_label(row.get('created_at'))}",
                f"{reading.headline} — {reading.summary} — ابیات: {verses}",
            ])
            for block in reading.blocks:
                rows.append(["تعبیر فال", block.title, f"{block.body} — راهنما: {block.note}"])
        except Exception:
            continue

    for attempt in db.all_attempts(user_id, limit=200):
        if not attempt.get("completed_at"):
            continue
        view = attempt_view(attempt)
        for row in view["rows"]:
            rows.append([
                "جواب آزمون",
                f"{view['test_label']} | نتیجه {view['result_key']} | سوال {row['number']}",
                f"{row['question']} — جواب: {row['answer'] or 'بدون جواب'}",
            ])

    return csv_response(f"neshane-user-{user_id}-dossier.csv", ["بخش", "کلید", "مقدار"], rows)


@router.get(f"{BASE}export/{{name}}.csv")
def export_csv(request: Request, name: str) -> Response:
    blocked = guard(request)
    if blocked:
        return blocked

    if name == "users":
        rows = db.all_users(limit=5000)
        return csv_response(
            "neshane-users.csv",
            ["id", "phone", "username", "name", "gender", "birth_jalali", "birth_time", "city", "created", "last_login"],
            [
                [
                    row["id"],
                    row["phone"],
                    row.get("username") or "",
                    row.get("name") or "",
                    row.get("gender") or "",
                    jalali_label(int(row["jy"]), int(row["jm"]), int(row["jd"])) if row.get("jy") else "",
                    row.get("birth_time") or "",
                    row.get("city") or "",
                    stamp_label(row.get("created_at")),
                    stamp_label(row["last_login_at"]) if row.get("last_login_at") else "",
                ]
                for row in rows
            ],
        )

    if name == "readings":
        rows = db.all_readings(limit=5000)
        return csv_response(
            "neshane-readings.csv",
            ["token", "user_id", "method", "topic", "headline", "overall", "intent", "created"],
            [
                [
                    row["id"],
                    row["user_id"],
                    row["kind"],
                    row["topic"],
                    row.get("headline") or "",
                    row.get("overall") or 0,
                    row.get("intent") or "",
                    stamp_label(row.get("created_at")),
                ]
                for row in rows
            ],
        )

    if name == "attempts":
        header = ["attempt_id", "user_id", "phone", "test", "result", "completed"]
        longest = 0
        prepared = []
        for user in db.all_users(limit=2000):
            for attempt in db.all_attempts(int(user["id"]), limit=100):
                rows = attempt_view(attempt)
                prepared.append((attempt, user, rows))
                longest = max(longest, len(rows["rows"]))
        for position in range(longest):
            header.extend([f"Q{position + 1}", f"A{position + 1}"])
        body = []
        for attempt, user, view in prepared:
            line: List[Any] = [
                attempt["id"],
                user["id"],
                user["phone"],
                view["test_label"],
                view["result_key"],
                view["finished_label"] or view["created_label"],
            ]
            for row in view["rows"]:
                line.extend([row["question"], row["answer"] or ""])
            line.extend([""] * (longest * 2 - len(view["rows"]) * 2))
            body.append(line)
        return csv_response("neshane-tests.csv", header, body)

    if name == "ads":
        rows = db.ads_all()
        stats = db.ad_stats_all()
        return csv_response(
            "neshane-ads.csv",
            [
                "id", "title", "kind", "placement", "active", "status", "link",
                "skip", "skip_after", "hold_seconds", "max_per_day", "hour_from", "hour_to",
                "weekdays", "starts", "ends", "impressions", "clicks", "ctr", "created",
            ],
            [
                [
                    row["id"],
                    row.get("title") or "",
                    "video" if row.get("media_kind") == "video" else "image",
                    row.get("placement") or "",
                    int(row.get("active") or 0),
                    ads.status(row)["label"],
                    row.get("link_url") or "",
                    int(row.get("skip_allowed") or 0),
                    int(row.get("skip_after") or 0),
                    int(row.get("hold_seconds") or 0),
                    int(row.get("max_per_day") or 0),
                    int(row.get("hour_from") or 0),
                    row.get("hour_to") if row.get("hour_to") is not None else 24,
                    ",".join(str(day) for day in ads.weekday_list(row.get("weekdays"))),
                    stamp_label(row["starts_at"]) if row.get("starts_at") else "",
                    stamp_label(row["ends_at"]) if row.get("ends_at") else "",
                    stats.get(int(row["id"]), {}).get("impressions", 0),
                    stats.get(int(row["id"]), {}).get("clicks", 0),
                    stats.get(int(row["id"]), {}).get("ctr", 0),
                    stamp_label(row.get("created_at")),
                ]
                for row in rows
            ],
        )

    if name == "events":
        rows = db.recent_events(limit=5000)
        return csv_response(
            "neshane-events.csv",
            ["id", "name", "user_id", "phone", "created"],
            [
                [row["id"], row["name"], row.get("user_id") or "", row.get("phone") or "", stamp_label(row["created_at"])]
                for row in rows
            ],
        )

    if name == "feedback":
        rows = db.all_feedback(limit=5000)
        return csv_response(
            "neshane-feedback.csv",
            ["id", "user_id", "phone", "name", "rating", "comment", "created"],
            [
                [
                    row["id"],
                    row["user_id"],
                    row.get("phone") or "",
                    " ".join(part for part in (row.get("user_name") or "", row.get("user_family") or "") if part),
                    row.get("rating") or 0,
                    row.get("comment") or "",
                    stamp_label(row.get("created_at")),
                ]
                for row in rows
            ],
        )

    if name == "llm":
        rows = db.llm_calls(limit=5000)
        return csv_response(
            "neshane-llm-calls.csv",
            [
                "id", "kind", "provider", "model", "role", "ok", "status", "error",
                "latency_ms", "prompt_tokens", "completion_tokens", "total_tokens", "created",
            ],
            [
                [
                    row["id"],
                    row["kind"],
                    row["provider"],
                    row["model"],
                    row["role"],
                    row["ok"],
                    row["status"],
                    row["error"],
                    row["latency_ms"],
                    row["prompt_tokens"],
                    row["completion_tokens"],
                    row["total_tokens"],
                    stamp_label(row.get("created_at")),
                ]
                for row in rows
            ],
        )

    return page(request, "admin/missing.html", "dashboard", status_code=404)


# --------------------------------------------------------------------------- #
# هوش مصنوعی / LLM monitoring & prompts
# --------------------------------------------------------------------------- #


def _llm_kind_label(kind: str) -> str:
    entry = prompt_book.PROMPTS.get(kind)
    return str(entry["label"]) if entry else kind


def _llm_kind_icon(kind: str) -> str:
    entry = prompt_book.PROMPTS.get(kind)
    return str(entry["icon"]) if entry else "fa-solid fa-robot"


@router.get(f"{BASE}ai", response_class=HTMLResponse)
def ai_page(request: Request, kind: str = "", provider: str = "", failures: int = 0) -> Response:
    blocked = guard(request)
    if blocked:
        return blocked

    health = llm.health()
    stats = health["stats"]
    kind_rows = [
        {**row, "label": _llm_kind_label(str(row["kind"])), "icon": _llm_kind_icon(str(row["kind"]))}
        for row in db.llm_kind_stats()
    ]
    model_rows = db.llm_model_stats()
    daily = list(reversed(db.llm_daily(days=14)))
    peak = max([int(row["total"]) for row in daily] + [1])
    for row in daily:
        row["height"] = max(6, round(100 * int(row["total"]) / peak))
        row["label"] = stamp_label(row["stamp"]).split(" • ")[0]

    calls = db.llm_calls(
        limit=PAGE_SIZE,
        only_failures=bool(failures),
        kind=kind or None,
        provider=provider or None,
    )
    for call in calls:
        call["created_label"] = stamp_label(call.get("created_at"))
        call["kind_label"] = _llm_kind_label(str(call["kind"]))
        call["kind_icon"] = _llm_kind_icon(str(call["kind"]))

    return page(
        request,
        "admin/ai.html",
        "ai",
        health=health,
        stats=stats,
        providers=health["providers"],
        breakers=health["breakers"],
        kind_rows=kind_rows,
        model_rows=model_rows,
        daily=daily,
        calls=calls,
        total_calls=db.count_llm_calls(only_failures=bool(failures), kind=kind or None, provider=provider or None),
        filter_kind=kind,
        filter_provider=provider,
        only_failures=bool(failures),
        prompt_rows=prompt_book.catalogue(),
    )


@router.get(f"{BASE}ai/prompts", response_class=HTMLResponse)
def ai_prompts_page(request: Request) -> Response:
    """نمایش فقط-خواندنیِ دستورهای سیستمی که به مدل فرستاده می‌شوند."""
    blocked = guard(request)
    if blocked:
        return blocked
    rows = []
    for entry in prompt_book.catalogue():
        rows.append({**entry, "stats": db.llm_kind_stats_for(str(entry["key"]))})
    return page(request, "admin/prompts.html", "prompts", prompt_rows=rows)


@router.post(f"{BASE}ai/purge")
def ai_purge(request: Request, keep_days: int = Form(60)) -> Response:
    blocked = guard(request)
    if blocked:
        return blocked
    days = max(1, min(3650, int(keep_days or 60)))
    removed = db.purge_llm_calls(days)
    db.log_event("admin_llm_purge")
    response = redirect(f"{BASE}ai")
    return response


# --------------------------------------------------------------------------- #
# بازخورد کاربران / feedback
# --------------------------------------------------------------------------- #


@router.get(f"{BASE}feedback", response_class=HTMLResponse)
def feedback_page(request: Request, comments: int = 0, page_number: int = 1) -> Response:
    blocked = guard(request)
    if blocked:
        return blocked
    page_number = max(1, int(page_number or 1))
    only_comments = bool(comments)
    rows = db.all_feedback(
        limit=PAGE_SIZE, offset=(page_number - 1) * PAGE_SIZE, only_comments=only_comments
    )
    for row in rows:
        row["created_label"] = stamp_label(row.get("created_at"))
        row["name_label"] = " ".join(
            part for part in (row.get("user_name") or "", row.get("user_family") or "") if part
        ).strip()
        row["stars"] = list(range(1, max(0, int(row.get("rating") or 0)) + 1))
    total = db.count_feedback_filtered(only_comments=only_comments)
    return page(
        request,
        "admin/feedback.html",
        "feedback",
        rows=rows,
        stats=db.feedback_stats(),
        only_comments=only_comments,
        total=total,
        page_number=page_number,
        pages=max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
    )


# --------------------------------------------------------------------------- #
# تبلیغات / ads
# --------------------------------------------------------------------------- #


def _ad_public(row: Dict[str, Any]) -> Dict[str, Any]:
    """تبلیغ را برای نمایش در پنل آماده می‌کند (آدرس رسانه + وضعیت + بازهٔ نمایش)."""
    item = dict(row)
    item["media_url"] = ads.media_url(item)
    item["media_size"] = ads.human_size(item.get("media_bytes"))
    item["state"] = ads.status(item)
    item["window"] = ads.window_label(item, lambda value: stamp_label(value))
    item["kind_label"] = "ویدیو" if item.get("media_kind") == "video" else "عکس"
    item["placement_label"] = ads.PLACEMENTS.get(str(item.get("placement")), ads.PLACEMENTS["popup"])["label"]
    item["skip_label"] = (
        f"از ثانیهٔ {to_fa(int(item.get('skip_after') or 0))} قابل ردکردن"
        if int(item.get("skip_allowed") or 0)
        else "بدون امکان ردکردن"
    )
    item["weekday_list"] = ads.weekday_list(item.get("weekdays"))
    item["starts_label"] = stamp_label(item["starts_at"]) if item.get("starts_at") else ""
    item["ends_label"] = stamp_label(item["ends_at"]) if item.get("ends_at") else ""
    item["start_parts"] = _jalali_parts(item.get("starts_at"))
    item["end_parts"] = _jalali_parts(item.get("ends_at"))
    return item


def _jalali_parts(value: Any) -> Optional[Tuple[int, int, int]]:
    """زمان یونیکس را به سه عدد جلالی (سال، ماه، روز) تبدیل می‌کند تا فرم پرش کند."""
    if not value:
        return None
    try:
        moment = datetime.fromtimestamp(float(value))
    except (TypeError, ValueError, OSError):
        return None
    return gregorian_to_jalali(moment.year, moment.month, moment.day)


@router.get(f"{BASE}ads", response_class=HTMLResponse)
def ads_page(request: Request, ad_id: Optional[int] = None) -> Response:
    """فهرست تبلیغ‌ها + فرم ساخت/ویرایش در همان صفحه."""
    blocked = guard(request)
    if blocked:
        return blocked

    rows = [_ad_public(row) for row in db.ads_all()]
    stats = db.ad_stats_all()
    for row in rows:
        row["stats"] = stats.get(int(row["id"]), {"impressions": 0, "clicks": 0, "skips": 0, "dismisses": 0, "ctr": 0.0})

    editing = db.ad_get(int(ad_id)) if ad_id else None
    return page(
        request,
        "admin/ads.html",
        "ads",
        rows=rows,
        editing=_ad_public(editing) if editing else None,
        placements=ads.PLACEMENTS,
        placement_order=ads.PLACEMENT_ORDER,
        weekdays=ads.WEEKDAYS,
        media_limit_mb=round(ads.MAX_VIDEO_BYTES / 1024 / 1024),
        image_limit_mb=round(ads.MAX_IMAGE_BYTES / 1024 / 1024),
        totals={
            "all": len(rows),
            "active": sum(1 for row in rows if row["state"]["key"] == "active"),
            "impressions": sum(int(row["stats"]["impressions"]) for row in rows),
            "clicks": sum(int(row["stats"]["clicks"]) for row in rows),
        },
        ok=request.query_params.get("ok", ""),
        error=request.query_params.get("error", ""),
        error_text=request.query_params.get("text", ""),
    )


def _q(text: str) -> str:
    """متن را برای گذاشتن در آدرس (کوئری) امن می‌کند."""
    return urllib.parse.quote(str(text)[:200], safe="")


def _ad_form_values(payload: Dict[str, Any], weekday_values: Optional[List[str]] = None) -> Dict[str, Any]:
    """مقادیر فرم تبلیغ را از ورودی خام می‌سازد (با دورزدن ورودی‌های نامعتبر)."""
    def number(value: Any, default: int, low: int, high: int) -> int:
        try:
            result = int(form_utils.from_fa(str(value).strip()) or default)
        except (TypeError, ValueError):
            result = default
        return max(low, min(high, result))

    weekdays = [str(day) for day in (weekday_values or []) if str(day).isdigit() and 0 <= int(str(day)) <= 6]
    return {
        "title": (payload.get("title") or "").strip()[:80],
        "body": (payload.get("body") or "").strip()[:300],
        "link_url": (payload.get("link_url") or "").strip()[:400],
        "cta_label": (payload.get("cta_label") or "").strip()[:40],
        "placement": payload.get("placement") if payload.get("placement") in ads.PLACEMENTS else "popup",
        "skip_allowed": 1 if str(payload.get("skip_allowed") or "").lower() in {"1", "on", "true", "yes"} else 0,
        "skip_after": number(payload.get("skip_after"), 3, 0, ads.MAX_SKIP_AFTER),
        "hold_seconds": number(payload.get("hold_seconds"), 8, 1, ads.MAX_HOLD_SECONDS),
        "dismiss_days": number(payload.get("dismiss_days"), 0, 0, 365),
        "max_per_day": number(payload.get("max_per_day"), 3, 0, 50),
        "hour_from": number(payload.get("hour_from"), 0, 0, 24),
        "hour_to": number(payload.get("hour_to"), 24, 0, 24),
        "weight": number(payload.get("weight"), 1, 0, 100),
        "weekdays": "".join(sorted(set(weekdays))),
    }


def _ad_dates(payload: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], str]:
    """تاریخ‌های جلالی شروع/پایان را به زمان یونیکس تبدیل می‌کند.

    خروجی ``(starts_at, ends_at, error)``. روز شروع از ابتدای همان روز و روز پایان
    تا پایان همان روز حساب می‌شود تا بازه همان‌طور که انتظار می‌رود بسته شود.
    """
    from .utils import is_valid_jalali, jalali_to_gregorian

    stamps: List[Optional[float]] = []
    for name, label, day_end in (("start", "شروع", False), ("end", "پایان", True)):
        jy = (payload.get(f"{name}_jy") or "").strip()
        jm = (payload.get(f"{name}_jm") or "").strip()
        jd = (payload.get(f"{name}_jd") or "").strip()
        if not (jy and jm and jd):
            stamps.append(None)
            continue
        try:
            year = int(form_utils.from_fa(jy))
            month = int(form_utils.from_fa(jm))
            day = int(form_utils.from_fa(jd))
        except (TypeError, ValueError):
            return None, None, f"تاریخ {label} را درست وارد کن."
        if not is_valid_jalali(year, month, day):
            return None, None, f"تاریخ {label} در تقویم وجود ندارد."
        gy, gm, gd = jalali_to_gregorian(year, month, day)
        moment = datetime(gy, gm, gd, 23, 59, 59) if day_end else datetime(gy, gm, gd, 0, 0, 0)
        stamps.append(moment.timestamp())

    starts_at, ends_at = stamps
    if starts_at and ends_at and ends_at < starts_at:
        return None, None, "تاریخ پایان نمی‌تواند قبل از شروع باشد."
    return starts_at, ends_at, ""


@router.post(f"{BASE}ads/save", response_class=HTMLResponse)
async def ad_save(request: Request) -> Response:
    """ساخت یا ویرایش یک تبلیغ، همراه با آپلود عکس/ویدیو."""
    blocked = guard(request)
    if blocked:
        return blocked

    form = await request.form()
    payload = {key: form.get(key) for key in form.keys()}
    values = _ad_form_values(payload, form.getlist("weekdays"))
    ad_id = 0
    try:
        ad_id = int(form_utils.from_fa(str(form.get("id") or "0"))) or 0
    except (TypeError, ValueError):
        ad_id = 0

    existing = db.ad_get(ad_id) if ad_id else None
    back = f"{BASE}ads{'/' + str(ad_id) if ad_id else ''}"

    if not values["title"]:
        return redirect(f"{back}?error=title")
    if values["link_url"] and not re.match(r"^https?://", values["link_url"], re.I):
        return redirect(f"{back}?error=link")
    if values["hour_from"] == values["hour_to"]:
        # بازهٔ بسته یعنی «تمام شبانه‌روز»؛ برای اینکه ناخواسته خاموش نشود، صریح می‌کنیم.
        values["hour_from"], values["hour_to"] = 0, 24

    starts_at, ends_at, date_error = _ad_dates(payload)
    if date_error:
        return redirect(f"{back}?error=date&text=" + _q(date_error))
    values["starts_at"] = starts_at
    values["ends_at"] = ends_at

    upload = form.get("media")
    filename = getattr(upload, "filename", "") or ""
    if filename:
        info, error = ads.save_upload(upload.file, filename, getattr(upload, "content_type", "") or "")
        if error:
            return redirect(f"{back}?error=media&text=" + _q(error))
        values.update(
            {
                "media_kind": info["kind"],
                "media_file": info["file"],
                "media_name": info["name"],
                "media_bytes": info["bytes"],
            }
        )
    elif not existing:
        return redirect(f"{back}?error=media&text=" + _q("برای تبلیغ تازه باید یک عکس یا ویدیو آپلود کنی."))

    values["active"] = 1 if str(payload.get("active") or "").lower() in {"1", "on", "true", "yes"} else (int(existing["active"]) if existing else 1)

    if existing:
        db.ad_update(ad_id, values)
        old_file = str(existing.get("media_file") or "")
        if filename and old_file and old_file != values.get("media_file"):
            ads.delete_media(old_file)
        db.log_event("admin_ad_saved")
        return redirect(f"{BASE}ads?ok=saved")

    db.ad_create(values)
    db.log_event("admin_ad_created")
    return redirect(f"{BASE}ads?ok=created")


@router.post(f"{BASE}ads/{{ad_id}}/toggle")
def ad_toggle(request: Request, ad_id: int) -> Response:
    """روشن/خاموش‌کردن سریع یک تبلیغ از فهرست."""
    blocked = guard(request)
    if blocked:
        return blocked
    row = db.ad_get(int(ad_id))
    if not row:
        return redirect(f"{BASE}ads?error=notfound")
    db.ad_update(int(ad_id), {"active": 0 if int(row.get("active") or 0) else 1})
    db.log_event("admin_ad_toggled")
    return redirect(f"{BASE}ads?ok=" + ("paused" if int(row.get("active") or 0) else "resumed"))


@router.post(f"{BASE}ads/{{ad_id}}/delete")
def ad_delete(request: Request, ad_id: int) -> Response:
    """حذف تبلیغ همراه با فایل رسانه‌اش."""
    blocked = guard(request)
    if blocked:
        return blocked
    row = db.ad_get(int(ad_id))
    if not row:
        return redirect(f"{BASE}ads?error=notfound")
    db.ad_delete(int(ad_id))
    ads.delete_media(str(row.get("media_file") or ""))
    db.log_event("admin_ad_deleted")
    return redirect(f"{BASE}ads?ok=deleted")


@router.get(f"{BASE}ads/{{ad_id}}/preview", response_class=HTMLResponse)
def ad_preview(request: Request, ad_id: int) -> Response:
    """پیش‌نمایش دقیق همان چیزی که کاربر می‌بیند (عکس/ویدیو، دکمه‌ها و شمارش)."""
    blocked = guard(request)
    if blocked:
        return blocked
    row = db.ad_get(int(ad_id))
    if not row:
        return redirect(f"{BASE}ads?error=notfound")
    item = _ad_public(row)
    return page(
        request,
        "admin/ad_preview.html",
        "ads",
        ad=item,
        payload=ads.public_payload(row),
        daily=db.ad_daily(int(ad_id), days=14),
        stats=db.ad_stats(int(ad_id)),
        recent=db.recent_ad_events(limit=200, ad_id=int(ad_id)),
    )
