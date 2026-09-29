"""لایهٔ دادهٔ SQLite: کاربران، کدهای ورود، نشست‌ها، فال‌ها، تست‌ها و پیش‌نویس سفر.

همهٔ اطلاعاتی که کاربر وارد می‌کند (شماره، پروفایل، نیت، جواب تست‌ها و نتیجه‌ها)
اینجا ذخیره می‌شود. برای پروتوتایپ از sqlite3 استاندارد پایتون استفاده می‌کنیم.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(os.environ.get("NESHANE_DB", Path(__file__).resolve().parent.parent / "data" / "neshane.sqlite3"))

_LOCK = threading.Lock()
_connection: Optional[sqlite3.Connection] = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  phone         TEXT UNIQUE NOT NULL,
  username      TEXT DEFAULT '',
  password_hash TEXT DEFAULT '',
  phone_verified_at REAL,
  name          TEXT DEFAULT '',
  family        TEXT DEFAULT '',
  gender        TEXT DEFAULT '',
  jy            INTEGER,
  jm            INTEGER,
  jd            INTEGER,
  birth_time    TEXT DEFAULT '',
  city          TEXT DEFAULT '',
  created_at    REAL NOT NULL,
  updated_at    REAL NOT NULL,
  last_login_at REAL
);

CREATE TABLE IF NOT EXISTS otp_codes (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  phone      TEXT NOT NULL,
  code       TEXT NOT NULL,
  created_at REAL NOT NULL,
  expires_at REAL NOT NULL,
  used_at    REAL,
  attempts   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_otp_phone ON otp_codes(phone, created_at);

CREATE TABLE IF NOT EXISTS sessions (
  sid          TEXT PRIMARY KEY,
  user_id      INTEGER NOT NULL,
  created_at   REAL NOT NULL,
  last_seen_at REAL NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS readings (
  id           TEXT PRIMARY KEY,
  user_id      INTEGER NOT NULL,
  kind         TEXT NOT NULL,
  topic        TEXT NOT NULL,
  intent       TEXT DEFAULT '',
  headline     TEXT DEFAULT '',
  overall      INTEGER DEFAULT 0,
  payload      TEXT NOT NULL,
  created_at   REAL NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_readings_user ON readings(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS journey_state (
  user_id    INTEGER PRIMARY KEY,
  kind       TEXT DEFAULT '',
  topic      TEXT DEFAULT '',
  intent     TEXT DEFAULT '',
  updated_at REAL NOT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS test_attempts (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id      INTEGER NOT NULL,
  test_key     TEXT NOT NULL,
  answers      TEXT NOT NULL DEFAULT '{}',
  result_key   TEXT,
  scores       TEXT DEFAULT '{}',
  created_at   REAL NOT NULL,
  completed_at REAL,
  FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_attempts_user ON test_attempts(user_id, test_key, created_at DESC);

CREATE TABLE IF NOT EXISTS events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER,
  name       TEXT NOT NULL,
  created_at REAL NOT NULL
);

-- نشست‌های پنل ادمین (جدا از نشست کاربران)
CREATE TABLE IF NOT EXISTS admin_sessions (
  token        TEXT PRIMARY KEY,
  created_at   REAL NOT NULL,
  last_seen_at REAL NOT NULL,
  expires_at   REAL NOT NULL,
  ip           TEXT DEFAULT '',
  user_agent   TEXT DEFAULT ''
);

-- کارت‌های فال تازه‌ساختهٔ مدیر و ویرایش روی کارت‌های آماده
CREATE TABLE IF NOT EXISTS fortune_cards (
  key            TEXT PRIMARY KEY,
  title          TEXT DEFAULT '',
  theme_label    TEXT DEFAULT '',
  verses         TEXT NOT NULL DEFAULT '[]',
  keywords       TEXT NOT NULL DEFAULT '[]',
  interpretation TEXT DEFAULT '',
  guidance       TEXT DEFAULT '',
  builtin        INTEGER DEFAULT 0,
  hidden         INTEGER DEFAULT 0,
  created_at     REAL NOT NULL,
  updated_at     REAL NOT NULL
);

-- هر تماس با مدل زبانی (موفق یا ناموفق) یک ردیف اینجا می‌گذارد.
-- پنل ادمین روی همین جدول ساخته شده است.
CREATE TABLE IF NOT EXISTS llm_calls (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id           INTEGER,
  kind              TEXT NOT NULL,
  provider          TEXT NOT NULL DEFAULT '',
  provider_label    TEXT DEFAULT '',
  model             TEXT DEFAULT '',
  role              TEXT DEFAULT '',
  ok                INTEGER DEFAULT 0,
  status            TEXT DEFAULT '',
  error             TEXT DEFAULT '',
  latency_ms        INTEGER DEFAULT 0,
  attempt           INTEGER DEFAULT 1,
  retries           INTEGER DEFAULT 0,
  prompt_tokens     INTEGER DEFAULT 0,
  completion_tokens INTEGER DEFAULT 0,
  total_tokens      INTEGER DEFAULT 0,
  prompt_chars      INTEGER DEFAULT 0,
  response_chars    INTEGER DEFAULT 0,
  prompt_preview    TEXT DEFAULT '',
  response_preview  TEXT DEFAULT '',
  created_at        REAL NOT NULL
);

-- مدارشکن ارائه‌دهنده‌ها: کدام سرویس تا چه زمانی کنار گذاشته شده است.
-- جدا از لاگ تماس‌ها نگه داشته می‌شود تا با پاک‌شدن لاگ، تصمیمش گم نشود و
-- با ری‌استارت سرور هم از یاد نرود.
CREATE TABLE IF NOT EXISTS llm_breakers (
  provider   TEXT PRIMARY KEY,
  reason     TEXT DEFAULT '',
  until      REAL NOT NULL,
  created_at REAL NOT NULL
);

-- امتیاز و نظر کاربران (پاپ‌اپ بازگشت پس از ۲۴ ساعت)
CREATE TABLE IF NOT EXISTS feedback (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    INTEGER NOT NULL,
  rating     INTEGER DEFAULT 0,
  comment    TEXT DEFAULT '',
  page       TEXT DEFAULT '',
  created_at REAL NOT NULL
);

-- تبليغات: هر ردیف یک بنر/تبلیغ است که مدیر از پنل آپلود می‌کند.
-- زمانِ نمایش با ترکیب چند ستون کنترل می‌شود: بازهٔ تاریخ، ساعات شبانه‌روز،
-- روزهای هفته و سهمیهٔ روزانه؛ پس یک ردیف می‌تواند «از ۱ مهر تا ۳۰ مهر،
-- فقط ۱۸ تا ۲۳، شنبه تا چهارشنبه، حداکثر ۳ بار در روز» باشد.
CREATE TABLE IF NOT EXISTS ads (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  title         TEXT DEFAULT '',
  body          TEXT DEFAULT '',
  media_kind    TEXT DEFAULT 'image',   -- image | video
  media_file    TEXT DEFAULT '',        -- نام فایل ذخیره‌شده در data/ads_media
  media_name    TEXT DEFAULT '',        -- نام اصلی فایل (برای نمایش در پنل)
  media_bytes   INTEGER DEFAULT 0,
  link_url      TEXT DEFAULT '',        -- آدرس مقصد
  cta_label     TEXT DEFAULT '',        -- متن دکمهٔ «بیشتر بدانید»
  placement     TEXT DEFAULT 'popup',   -- popup | banner | both
  skip_allowed  INTEGER DEFAULT 1,
  skip_after    INTEGER DEFAULT 3,      -- از چند ثانیه بعد می‌شود رد کرد
  hold_seconds  INTEGER DEFAULT 8,      -- چند ثانیه دیده شود (ویدیو: تا پایان)
  dismiss_days  INTEGER DEFAULT 0,      -- «دیگر نشان نده» چند روز پنهان کند (۰ = بی‌گزینه)
  max_per_day   INTEGER DEFAULT 3,      -- سقف نمایش به هر بازدیدکننده در روز (۰ = بی‌سقف)
  starts_at     REAL,
  ends_at       REAL,
  hour_from     INTEGER DEFAULT 0,
  hour_to       INTEGER DEFAULT 24,     -- پشتیبانی از بازهٔ شب‌رو (مثل ۲۲ تا ۲)
  weekdays      TEXT DEFAULT '',        -- ''=همه؛ وگرنه رشتهٔ ارقام ۰..۶ (۰=شنبه)
  weight        INTEGER DEFAULT 1,      -- در انتخاب بین چند تبلیغ، وزن بیشتر جلوتر
  active        INTEGER DEFAULT 1,
  created_at    REAL NOT NULL,
  updated_at    REAL NOT NULL
);

-- رویدادهای تبلیغات: نمایش، کلیک، ردکردن و «دیگر نشان نده»
CREATE TABLE IF NOT EXISTS ad_events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ad_id      INTEGER NOT NULL,
  actor      TEXT DEFAULT '',   -- شناسهٔ بیننده: u<ident کاربر> یا v<browser id>
  kind       TEXT DEFAULT '',   -- impression | click | skip | dismiss
  created_at REAL NOT NULL
);

-- ایندکس‌های پنل ادمین: فهرست‌های بزرگ بدون اسکن کامل جدول خوانده می‌شوند
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_name ON events(name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_readings_created ON readings(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_attempts_created ON test_attempts(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_admin_sessions_expiry ON admin_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_fortune_cards_updated ON fortune_cards(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_calls_created ON llm_calls(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_calls_kind ON llm_calls(kind, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_calls_provider ON llm_calls(provider, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_calls_ok ON llm_calls(ok, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_calls_user ON llm_calls(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON feedback(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_user ON feedback(user_id, created_at DESC);
-- بازی «ذهن‌خوان»: هر دورِ بازی یک ردیف، و وضعیتش در یک ستون JSON می‌نشیند.
-- چرا نه کوکی؟ چون بازی چند مرحله‌ای است و کاربر می‌تواند وسط کار صفحه را ببندد؛
-- وضعیت سمت سرور می‌ماند تا هم جا نشکند، هم در پنل قابل بررسی باشد.
CREATE TABLE IF NOT EXISTS mind_games (
  id         TEXT PRIMARY KEY,
  user_id    INTEGER,
  visitor    TEXT DEFAULT '',   -- شناسهٔ مرورگر مهمان (برای بازی بدون ثبت‌نام)
  state      TEXT NOT NULL DEFAULT '{}',
  turns      INTEGER DEFAULT 0,
  guesses    INTEGER DEFAULT 0,
  solved     INTEGER DEFAULT 0, -- ۱ = درست حدس زد
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mind_games_visitor ON mind_games(visitor, created_at DESC);

-- شخصیت‌هایی که کاربران خودشان در پایان بازی اسم‌شان را نوشتند (یادگیری دیتاست).
CREATE TABLE IF NOT EXISTS mind_learned (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  game_id     TEXT DEFAULT '',
  user_id     INTEGER,
  name        TEXT NOT NULL,
  values_json TEXT NOT NULL DEFAULT '{}',
  created_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mind_learned_name ON mind_learned(name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_ads_active ON ads(active, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_ad_events_ad ON ad_events(ad_id, kind, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ad_events_actor ON ad_events(actor, kind, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ad_events_created ON ad_events(created_at DESC);
"""

# ستون‌هایی که بعداً به جدول‌ها اضافه شده‌اند (برای ارتقای دیتابیس‌های موجود)
MIGRATIONS = [
    ("users", "family", "TEXT DEFAULT ''"),
    ("users", "username", "TEXT DEFAULT ''"),
    ("users", "password_hash", "TEXT DEFAULT ''"),
    ("users", "phone_verified_at", "REAL"),
    # آخرین فعالیت کاربر (برای یادآوری «۲۴ ساعت نبودی»)، مستقل از نشست‌ها.
    ("users", "last_active_at", "REAL"),
    ("users", "feedback_asked_at", "REAL"),
    # متن شخصی‌شدهٔ پایان تست، تا هر بار مدل صدا زده نشود.
    ("test_attempts", "ai_note", "TEXT DEFAULT ''"),
    ("test_attempts", "ai_meta", "TEXT DEFAULT ''"),
]

# ایندکس‌هایی که به ستون‌های تازه وابسته‌اند؛ بعد از `_migrate` اجرا می‌شوند تا روی
# دیتابیس قدیمی (که هنوز آن ستون‌ها را ندارد) خطا ندهند.
POST_MIGRATIONS = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username
  ON users(lower(username)) WHERE username <> '';
"""


def now() -> float:
    return time.time()


def connect() -> sqlite3.Connection:
    global _connection
    with _LOCK:
        if _connection is None:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            _connection = sqlite3.connect(DB_PATH, check_same_thread=False)
            _connection.row_factory = sqlite3.Row
            _connection.execute("PRAGMA journal_mode=WAL")
            _connection.execute("PRAGMA foreign_keys=ON")
            # در حالت WAL، هم‌زمانیِ خواندن و نوشتن نیازی به fsync کامل ندارد.
            _connection.execute("PRAGMA synchronous=NORMAL")
            _connection.execute("PRAGMA busy_timeout=5000")
            _connection.executescript(SCHEMA)
            _migrate(_connection)
            _connection.executescript(POST_MIGRATIONS)
            _connection.commit()
        return _connection


def _migrate(connection: sqlite3.Connection) -> None:
    """ستون‌های تازه را به دیتابیس‌های موجود اضافه می‌کند.

    SQLite از `ALTER TABLE ... ADD COLUMN` پشتیبانی می‌کند؛ این تابع کاری می‌کند که
    ارتقای نسخه، داده‌های کاربران را از بین نبرد.
    """
    for table, column, declaration in MIGRATIONS:
        columns = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        if not columns or column in columns:
            continue
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")


def init() -> None:
    connect()


def _execute(sql: str, params: tuple = ()) -> sqlite3.Cursor:
    connection = connect()
    with _LOCK:
        cursor = connection.execute(sql, params)
        connection.commit()
        return cursor


def _query(sql: str, params: tuple = ()) -> List[sqlite3.Row]:
    connection = connect()
    with _LOCK:
        return list(connection.execute(sql, params).fetchall())


def _one(sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
    rows = _query(sql, params)
    return rows[0] if rows else None


def row_to_dict(row: Optional[sqlite3.Row]) -> Optional[Dict[str, Any]]:
    return dict(row) if row is not None else None


# --------------------------------------------------------------------------- #
# کاربران / users
# --------------------------------------------------------------------------- #


def get_or_create_user(phone: str) -> Dict[str, Any]:
    user = _one("SELECT * FROM users WHERE phone = ?", (phone,))
    if user:
        return dict(user)
    stamp = now()
    _execute(
        "INSERT INTO users (phone, created_at, updated_at) VALUES (?, ?, ?)",
        (phone, stamp, stamp),
    )
    return dict(_one("SELECT * FROM users WHERE phone = ?", (phone,)))


def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    return row_to_dict(_one("SELECT * FROM users WHERE id = ?", (user_id,)))


def has_credentials(user: Optional[Dict[str, Any]]) -> bool:
    """آیا کاربر نام کاربری و رمز عبور دارد (ثبت‌نامش کامل شده است)؟"""
    return bool(user) and bool(str(user.get("password_hash") or ""))


def user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """کاربر را با نام کاربری (بدون حساسیت به بزرگی/کوچکی حروف) پیدا می‌کند."""
    return row_to_dict(
        _one("SELECT * FROM users WHERE username <> '' AND lower(username) = lower(?)", (str(username or ""),))
    )


def username_taken(username: str, exclude_user_id: Optional[int] = None) -> bool:
    """نام کاربری برای کاربر دیگری رزرو شده است؟"""
    if exclude_user_id:
        row = _one(
            "SELECT 1 AS value FROM users WHERE username <> '' AND lower(username) = lower(?) AND id <> ?",
            (str(username or ""), exclude_user_id),
        )
    else:
        row = _one(
            "SELECT 1 AS value FROM users WHERE username <> '' AND lower(username) = lower(?)",
            (str(username or ""),),
        )
    return row is not None


def set_credentials(user_id: int, username: str, password_hash: str) -> bool:
    """نام کاربری و هش رمز عبور را ثبت می‌کند و شماره را تأییدشده علامت می‌زند.

    خروجی ``False`` یعنی نام کاربری در همین لحظه توسط کاربر دیگری گرفته شده است.
    چرا مهم است: بین «چک‌کردن آزاد بودن نام» و «نوشتن در دیتابیس» یک فاصلهٔ زمانی
    هست؛ اگر دو نفر همزمان یک نام را بفرستند (یا کاربر روی موبایل دکمه را دو بار
    بزند)، درخواست دوم به قید یکتاییِ دیتابیس می‌خورد و بدون این محافظ سرور با
    خطای ۵۰۰ می‌ترکید. اینجا خطا را می‌گیریم و به پیام روشن تبدیل می‌کنیم.
    """
    stamp = now()
    connection = connect()
    with _LOCK:
        try:
            if not connection.in_transaction:
                # قفل نوشتن را همین اول می‌گیریم تا بین «چک» و «نوشتن» کسی نپرد وسط.
                connection.execute("BEGIN IMMEDIATE")
            taken = connection.execute(
                "SELECT 1 FROM users WHERE username <> '' AND lower(username) = lower(?) AND id <> ?",
                (username, user_id),
            ).fetchone()
            if taken:
                connection.execute("ROLLBACK")
                return False
            connection.execute(
                """UPDATE users SET username = ?, password_hash = ?, phone_verified_at = ?, updated_at = ?
                   WHERE id = ?""",
                (username, password_hash, stamp, stamp, user_id),
            )
            connection.commit()
        except sqlite3.IntegrityError:
            # قید یکتاییِ دیتابیس (که با خودِ فایل محافظت می‌کند) اینجا هم گرفته می‌شود.
            connection.rollback()
            return False
        except sqlite3.Error:
            connection.rollback()
            raise
    return True


def phone_has_credentials(phone: str) -> bool:
    """آیا برای این شماره حساب کاملی ساخته شده است؟ (شماره‌ای که دیگر کد ورود نمی‌گیرد)"""
    row = _one(
        "SELECT 1 AS value FROM users WHERE phone = ? AND COALESCE(password_hash, '') <> ''",
        (phone,),
    )
    return row is not None


def update_profile(user_id: int, **fields: Any) -> None:
    allowed = {"name", "family", "gender", "jy", "jm", "jd", "birth_time", "city"}
    payload = {key: value for key, value in fields.items() if key in allowed}
    if not payload:
        return
    columns = ", ".join(f"{key} = ?" for key in payload)
    _execute(f"UPDATE users SET {columns}, updated_at = ? WHERE id = ?", (*payload.values(), now(), user_id))


def count_user_events_since(user_id: int, name: str, since: float) -> int:
    row = _one(
        "SELECT COUNT(*) AS value FROM events WHERE user_id = ? AND name = ? AND created_at >= ?",
        (user_id, name, since),
    )
    return int(row["value"]) if row else 0


def last_user_event_at(user_id: int, name: str) -> Optional[float]:
    row = _one(
        "SELECT created_at FROM events WHERE user_id = ? AND name = ? ORDER BY created_at DESC LIMIT 1",
        (user_id, name),
    )
    return float(row["created_at"]) if row else None


def touch_login(user_id: int) -> None:
    _execute("UPDATE users SET last_login_at = ?, updated_at = ? WHERE id = ?", (now(), now(), user_id))


def count_users() -> int:
    row = _one("SELECT COUNT(*) AS value FROM users")
    return int(row["value"]) if row else 0


# --------------------------------------------------------------------------- #
# کد ورود / OTP
# --------------------------------------------------------------------------- #


def create_otp(phone: str, code: str, ttl_seconds: int = 180) -> None:
    stamp = now()
    _execute("DELETE FROM otp_codes WHERE phone = ? AND used_at IS NULL", (phone,))
    _execute(
        "INSERT INTO otp_codes (phone, code, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (phone, code, stamp, stamp + ttl_seconds),
    )


def latest_active_otp(phone: str) -> Optional[Dict[str, Any]]:
    return row_to_dict(
        _one(
            "SELECT * FROM otp_codes WHERE phone = ? AND used_at IS NULL ORDER BY created_at DESC LIMIT 1",
            (phone,),
        )
    )


def bump_otp_attempt(otp_id: int) -> int:
    _execute("UPDATE otp_codes SET attempts = attempts + 1 WHERE id = ?", (otp_id,))
    row = _one("SELECT attempts FROM otp_codes WHERE id = ?", (otp_id,))
    return int(row["attempts"]) if row else 0


def consume_otp(otp_id: int) -> None:
    _execute("UPDATE otp_codes SET used_at = ? WHERE id = ?", (now(), otp_id))


# --------------------------------------------------------------------------- #
# نشست‌ها / sessions
# --------------------------------------------------------------------------- #


def create_session(sid: str, user_id: int) -> None:
    stamp = now()
    _execute(
        "INSERT OR REPLACE INTO sessions (sid, user_id, created_at, last_seen_at) VALUES (?, ?, ?, ?)",
        (sid, user_id, stamp, stamp),
    )


# آخرین بازدید هر نشست حداکثر هر یک دقیقه نوشته می‌شود؛ قبلاً هر درخواست یک
# نوشتن در SQLite داشت که در ترافیک واقعی گلوگاه می‌شد.
SESSION_TOUCH_SECONDS = 60


def session_user(sid: Optional[str]) -> Optional[Dict[str, Any]]:
    if not sid:
        return None
    row = _one(
        """SELECT s.last_seen_at AS session_seen_at, u.*
           FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.sid = ?""",
        (sid,),
    )
    if not row:
        return None
    data = dict(row)
    last_seen = float(data.pop("session_seen_at", 0) or 0)
    stamp = now()
    if stamp - last_seen >= SESSION_TOUCH_SECONDS:
        _execute("UPDATE sessions SET last_seen_at = ? WHERE sid = ?", (stamp, sid))
    return data


def drop_session(sid: str) -> None:
    _execute("DELETE FROM sessions WHERE sid = ?", (sid,))


# --------------------------------------------------------------------------- #
# فال‌ها / readings
# --------------------------------------------------------------------------- #


def save_reading(reading: Dict[str, Any], user_id: int, payload: Dict[str, Any]) -> None:
    _execute(
        """INSERT OR REPLACE INTO readings (id, user_id, kind, topic, intent, headline, overall, payload, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            reading["id"],
            user_id,
            reading["kind"],
            reading["topic_key"],
            reading.get("intent") or "",
            reading.get("headline") or "",
            int(reading.get("overall") or 0),
            json.dumps(payload, ensure_ascii=False),
            now(),
        ),
    )


def get_reading(reading_id: str) -> Optional[Dict[str, Any]]:
    """یک فال را با شناسه‌اش می‌خواند؛ اگر دادهٔ ذخیره‌شده خراب بود، ``None``.

    خرابیِ payload نباید صفحه را بترکاند؛ فرض می‌کنیم آن فال وجود ندارد و مسیر
    عادیِ «پیدا نشد» اجرا می‌شود.
    """
    row = _one("SELECT * FROM readings WHERE id = ?", (reading_id,))
    if not row:
        return None
    data = dict(row)
    try:
        data["payload"] = json.loads(data["payload"] or "{}")
    except (TypeError, ValueError):
        return None
    if not isinstance(data.get("payload"), dict):
        return None
    return data


def user_readings(user_id: int, limit: int = 50, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    if kind:
        rows = _query(
            "SELECT * FROM readings WHERE user_id = ? AND kind = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, kind, limit),
        )
    else:
        rows = _query(
            "SELECT * FROM readings WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
    return [dict(row) for row in rows]


def count_readings() -> int:
    row = _one("SELECT COUNT(*) AS value FROM readings")
    return int(row["value"]) if row else 0


def count_readings_by_kind() -> Dict[str, int]:
    rows = _query("SELECT kind, COUNT(*) AS value FROM readings GROUP BY kind")
    return {row["kind"]: int(row["value"]) for row in rows}


# --------------------------------------------------------------------------- #
# پیش‌نویس سفر / journey draft
# --------------------------------------------------------------------------- #


def get_journey(user_id: int) -> Dict[str, Any]:
    row = _one("SELECT * FROM journey_state WHERE user_id = ?", (user_id,))
    if row:
        return dict(row)
    return {"user_id": user_id, "kind": "", "topic": "", "intent": ""}


def set_journey(user_id: int, **fields: Any) -> Dict[str, Any]:
    current = get_journey(user_id)
    current.update({key: value for key, value in fields.items() if key in {"kind", "topic", "intent"}})
    _execute(
        """INSERT INTO journey_state (user_id, kind, topic, intent, updated_at) VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(user_id) DO UPDATE SET kind = excluded.kind, topic = excluded.topic,
           intent = excluded.intent, updated_at = excluded.updated_at""",
        (user_id, current["kind"], current["topic"], current["intent"], now()),
    )
    return current


# --------------------------------------------------------------------------- #
# تست‌ها / personality tests
# --------------------------------------------------------------------------- #


def create_attempt(user_id: int, test_key: str) -> int:
    cursor = _execute(
        "INSERT INTO test_attempts (user_id, test_key, answers, created_at) VALUES (?, ?, '{}', ?)",
        (user_id, test_key, now()),
    )
    return int(cursor.lastrowid)


def get_attempt(attempt_id: int) -> Optional[Dict[str, Any]]:
    row = _one("SELECT * FROM test_attempts WHERE id = ?", (attempt_id,))
    if not row:
        return None
    data = dict(row)
    data["answers"] = json.loads(data["answers"] or "{}")
    data["scores"] = json.loads(data["scores"] or "{}")
    return data


def save_answer(attempt_id: int, question_index: int, option_index: int) -> None:
    attempt = get_attempt(attempt_id)
    if not attempt:
        return
    answers = attempt["answers"]
    answers[str(question_index)] = option_index
    _execute("UPDATE test_attempts SET answers = ? WHERE id = ?", (json.dumps(answers), attempt_id))


def finish_attempt(attempt_id: int, result_key: str, scores: Dict[str, Any]) -> None:
    _execute(
        "UPDATE test_attempts SET result_key = ?, scores = ?, completed_at = ? WHERE id = ?",
        (result_key, json.dumps(scores, ensure_ascii=False), now(), attempt_id),
    )


def user_attempts(user_id: int, test_key: Optional[str] = None, limit: int = 40) -> List[Dict[str, Any]]:
    if test_key:
        rows = _query(
            """SELECT * FROM test_attempts WHERE user_id = ? AND test_key = ?
               AND completed_at IS NOT NULL ORDER BY completed_at DESC LIMIT ?""",
            (user_id, test_key, limit),
        )
    else:
        rows = _query(
            """SELECT * FROM test_attempts WHERE user_id = ? AND completed_at IS NOT NULL
               ORDER BY completed_at DESC LIMIT ?""",
            (user_id, limit),
        )
    collected: List[Dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        data["answers"] = json.loads(data["answers"] or "{}")
        data["scores"] = json.loads(data["scores"] or "{}")
        collected.append(data)
    return collected


def latest_results(user_id: int) -> Dict[str, Dict[str, Any]]:
    """آخرین نتیجهٔ هر تست برای نمایش در پروفایل."""
    rows = _query(
        """SELECT * FROM test_attempts t WHERE user_id = ? AND completed_at IS NOT NULL
           AND completed_at = (
             SELECT MAX(completed_at) FROM test_attempts x
             WHERE x.user_id = t.user_id AND x.test_key = t.test_key AND x.completed_at IS NOT NULL
           )""",
        (user_id,),
    )
    latest: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        data = dict(row)
        data["answers"] = json.loads(data["answers"] or "{}")
        data["scores"] = json.loads(data["scores"] or "{}")
        latest[data["test_key"]] = data
    return latest


def open_attempt(user_id: int, test_key: str) -> Optional[Dict[str, Any]]:
    row = _one(
        """SELECT * FROM test_attempts WHERE user_id = ? AND test_key = ? AND completed_at IS NULL
           ORDER BY created_at DESC LIMIT 1""",
        (user_id, test_key),
    )
    if not row:
        return None
    data = dict(row)
    data["answers"] = json.loads(data["answers"] or "{}")
    return data


# --------------------------------------------------------------------------- #
# رویدادها / events (برای آمار استاتیک صفحهٔ اول)
# --------------------------------------------------------------------------- #


def log_event(name: str, user_id: Optional[int] = None) -> None:
    _execute("INSERT INTO events (user_id, name, created_at) VALUES (?, ?, ?)", (user_id, name, now()))


def count_events(name: str) -> int:
    row = _one("SELECT COUNT(*) AS value FROM events WHERE name = ?", (name,))
    return int(row["value"]) if row else 0


def count_events_since(name: str, since: float) -> int:
    row = _one(
        "SELECT COUNT(*) AS value FROM events WHERE name = ? AND created_at >= ?", (name, since)
    )
    return int(row["value"]) if row else 0


def last_event_at(name: str) -> Optional[float]:
    row = _one("SELECT created_at FROM events WHERE name = ? ORDER BY created_at DESC LIMIT 1", (name,))
    return float(row["created_at"]) if row else None


# --------------------------------------------------------------------------- #
# پنل ادمین / admin reads & writes
# --------------------------------------------------------------------------- #


def count_users_filtered(search: str = "") -> int:
    if search:
        like = f"%{search}%"
        row = _one(
            """SELECT COUNT(*) AS value FROM users
               WHERE phone LIKE ? OR name LIKE ? OR family LIKE ? OR city LIKE ? OR username LIKE ?""",
            (like, like, like, like, like),
        )
    else:
        row = _one("SELECT COUNT(*) AS value FROM users")
    return int(row["value"]) if row else 0


def all_users(limit: int = 50, offset: int = 0, search: str = "") -> List[Dict[str, Any]]:
    if search:
        like = f"%{search}%"
        rows = _query(
            """SELECT * FROM users
               WHERE phone LIKE ? OR name LIKE ? OR family LIKE ? OR city LIKE ? OR username LIKE ?
               ORDER BY created_at DESC LIMIT ? OFFSET ?""",
            (like, like, like, like, like, limit, offset),
        )
    else:
        rows = _query("SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))
    return [dict(row) for row in rows]


def get_user_by_phone(phone: str) -> Optional[Dict[str, Any]]:
    return row_to_dict(_one("SELECT * FROM users WHERE phone = ?", (phone,)))


def user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    return row_to_dict(_one("SELECT * FROM users WHERE id = ?", (user_id,)))


def user_events(user_id: int, limit: int = 60) -> List[Dict[str, Any]]:
    rows = _query(
        "SELECT * FROM events WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (user_id, limit)
    )
    return [dict(row) for row in rows]


def recent_events(limit: int = 120) -> List[Dict[str, Any]]:
    rows = _query(
        """SELECT e.*, u.phone AS phone, u.name AS user_name FROM events e
           LEFT JOIN users u ON u.id = e.user_id ORDER BY e.created_at DESC LIMIT ?""",
        (limit,),
    )
    return [dict(row) for row in rows]


def all_attempts(user_id: int, limit: int = 60) -> List[Dict[str, Any]]:
    """همهٔ تلاش‌های تست، حتی نیمه‌کاره (برای دیدن جواب‌های ثبت‌شده)."""
    rows = _query(
        "SELECT * FROM test_attempts WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    )
    collected: List[Dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        data["answers"] = json.loads(data["answers"] or "{}")
        data["scores"] = json.loads(data["scores"] or "{}")
        collected.append(data)
    return collected


def all_readings(limit: int = 50, offset: int = 0, kind: Optional[str] = None) -> List[Dict[str, Any]]:
    if kind:
        rows = _query(
            "SELECT * FROM readings WHERE kind = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (kind, limit, offset),
        )
    else:
        rows = _query("SELECT * FROM readings ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset))
    collected = []
    for row in rows:
        data = dict(row)
        try:
            data["payload"] = json.loads(data["payload"])
        except (TypeError, ValueError):
            data["payload"] = {}
        collected.append(data)
    return collected


def count_readings_filtered(kind: Optional[str] = None) -> int:
    if kind:
        row = _one("SELECT COUNT(*) AS value FROM readings WHERE kind = ?", (kind,))
    else:
        row = _one("SELECT COUNT(*) AS value FROM readings")
    return int(row["value"]) if row else 0


def delete_reading(reading_id: str) -> None:
    _execute("DELETE FROM readings WHERE id = ?", (reading_id,))


def delete_user(user_id: int) -> None:
    """حذف کامل کاربر و همهٔ داده‌های وابسته (رویدادها برای آمار می‌ماند)."""
    user = _one("SELECT phone FROM users WHERE id = ?", (user_id,))
    phone = str(user["phone"]) if user else ""
    _execute("DELETE FROM readings WHERE user_id = ?", (user_id,))
    _execute("DELETE FROM test_attempts WHERE user_id = ?", (user_id,))
    _execute("DELETE FROM journey_state WHERE user_id = ?", (user_id,))
    _execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
    _execute("UPDATE events SET user_id = NULL WHERE user_id = ?", (user_id,))
    if phone:
        _execute("DELETE FROM otp_codes WHERE phone = ?", (phone,))
    _execute("DELETE FROM users WHERE id = ?", (user_id,))


def count_users_since(since: float) -> int:
    row = _one("SELECT COUNT(*) AS value FROM users WHERE created_at >= ?", (since,))
    return int(row["value"]) if row else 0


def count_attempts(completed_only: bool = False) -> int:
    if completed_only:
        row = _one("SELECT COUNT(*) AS value FROM test_attempts WHERE completed_at IS NOT NULL")
    else:
        row = _one("SELECT COUNT(*) AS value FROM test_attempts")
    return int(row["value"]) if row else 0


def count_attempts_by_test() -> Dict[str, int]:
    rows = _query(
        """SELECT test_key, COUNT(*) AS value FROM test_attempts
           WHERE completed_at IS NOT NULL GROUP BY test_key"""
    )
    return {str(row["test_key"]): int(row["value"]) for row in rows}


def journey_drafts(limit: int = 40) -> List[Dict[str, Any]]:
    rows = _query(
        """SELECT j.*, u.phone AS phone, u.name AS user_name FROM journey_state j
           LEFT JOIN users u ON u.id = j.user_id ORDER BY j.updated_at DESC LIMIT ?""",
        (limit,),
    )
    return [dict(row) for row in rows]


# --------------------------------------------------------------------------- #
# نشست پنل ادمین / admin sessions
# --------------------------------------------------------------------------- #


def create_admin_session(token: str, ttl_seconds: int, ip: str = "", user_agent: str = "") -> None:
    stamp = now()
    _execute(
        """INSERT OR REPLACE INTO admin_sessions
           (token, created_at, last_seen_at, expires_at, ip, user_agent) VALUES (?, ?, ?, ?, ?, ?)""",
        (token, stamp, stamp, stamp + ttl_seconds, ip[:64], user_agent[:200]),
    )


def admin_session(token: Optional[str]) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    row = _one("SELECT * FROM admin_sessions WHERE token = ?", (token,))
    if not row:
        return None
    data = dict(row)
    if float(data["expires_at"]) < now():
        _execute("DELETE FROM admin_sessions WHERE token = ?", (token,))
        return None
    _execute("UPDATE admin_sessions SET last_seen_at = ? WHERE token = ?", (now(), token))
    return data


def drop_admin_session(token: str) -> None:
    _execute("DELETE FROM admin_sessions WHERE token = ?", (token,))


def purge_admin_sessions() -> None:
    _execute("DELETE FROM admin_sessions WHERE expires_at < ?", (now(),))


def count_admin_sessions() -> int:
    row = _one("SELECT COUNT(*) AS value FROM admin_sessions WHERE expires_at >= ?", (now(),))
    return int(row["value"]) if row else 0


# --------------------------------------------------------------------------- #
# کارت‌های فال قابل ویرایش / editable fortune cards
# --------------------------------------------------------------------------- #


def _fortune_row(row: sqlite3.Row) -> Dict[str, Any]:
    data = dict(row)
    for field in ("verses", "keywords"):
        try:
            data[field] = json.loads(data.get(field) or "[]")
        except (TypeError, ValueError):
            data[field] = []
    data["hidden"] = bool(data.get("hidden"))
    data["builtin"] = bool(data.get("builtin"))
    return data


def fortune_cards() -> List[Dict[str, Any]]:
    """همهٔ کارت‌های ساخته/ویرایش‌شدهٔ مدیر (تازه‌ترین اول)."""
    rows = _query("SELECT * FROM fortune_cards ORDER BY updated_at DESC")
    return [_fortune_row(row) for row in rows]


def fortune_card(key: str) -> Optional[Dict[str, Any]]:
    row = _one("SELECT * FROM fortune_cards WHERE key = ?", (key,))
    return _fortune_row(row) if row else None


def save_fortune_card(
    key: str,
    *,
    title: str = "",
    theme_label: str = "",
    verses: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
    interpretation: str = "",
    guidance: str = "",
    builtin: bool = False,
    hidden: bool = False,
) -> None:
    """کارت فال را می‌سازد یا به‌روز می‌کند (UPSERT)."""
    stamp = now()
    existing = _one("SELECT created_at, builtin FROM fortune_cards WHERE key = ?", (key,))
    created = float(existing["created_at"]) if existing else stamp
    if existing and existing["builtin"]:
        builtin = True
    _execute(
        """INSERT INTO fortune_cards
             (key, title, theme_label, verses, keywords, interpretation, guidance,
              builtin, hidden, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET
             title = excluded.title, theme_label = excluded.theme_label,
             verses = excluded.verses, keywords = excluded.keywords,
             interpretation = excluded.interpretation, guidance = excluded.guidance,
             builtin = excluded.builtin, hidden = excluded.hidden,
             updated_at = excluded.updated_at""",
        (
            key,
            title,
            theme_label,
            json.dumps(verses or [], ensure_ascii=False),
            json.dumps(keywords or [], ensure_ascii=False),
            interpretation,
            guidance,
            1 if builtin else 0,
            1 if hidden else 0,
            created,
            stamp,
        ),
    )


def delete_fortune_card(key: str) -> None:
    _execute("DELETE FROM fortune_cards WHERE key = ?", (key,))


def count_fortune_cards() -> Dict[str, int]:
    rows = _query("SELECT builtin, hidden, COUNT(*) AS value FROM fortune_cards GROUP BY builtin, hidden")
    total = custom = edited = hidden = 0
    for row in rows:
        value = int(row["value"])
        total += value
        if row["hidden"]:
            hidden += value
        elif row["builtin"]:
            edited += value
        else:
            custom += value
    return {"total": total, "custom": custom, "edited": edited, "hidden": hidden}


# --------------------------------------------------------------------------- #
# مدل زبانی / LLM telemetry
# --------------------------------------------------------------------------- #

LLM_COLUMNS = (
    "kind, provider, provider_label, model, role, ok, status, error, latency_ms, "
    "attempt, retries, prompt_tokens, completion_tokens, total_tokens, "
    "prompt_chars, response_chars, prompt_preview, response_preview, user_id, created_at"
)


def log_llm_call(payload: Dict[str, Any]) -> int:
    """یک تماس با مدل زبانی را ثبت می‌کند و شناسهٔ ردیف را برمی‌گرداند."""
    cursor = _execute(
        f"INSERT INTO llm_calls ({LLM_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            str(payload.get("kind") or ""),
            str(payload.get("provider") or ""),
            str(payload.get("provider_label") or ""),
            str(payload.get("model") or ""),
            str(payload.get("role") or ""),
            int(payload.get("ok") or 0),
            str(payload.get("status") or ""),
            str(payload.get("error") or "")[:400],
            int(payload.get("latency_ms") or 0),
            int(payload.get("attempt") or 1),
            int(payload.get("retries") or 0),
            int(payload.get("prompt_tokens") or 0),
            int(payload.get("completion_tokens") or 0),
            int(payload.get("total_tokens") or 0),
            int(payload.get("prompt_chars") or 0),
            int(payload.get("response_chars") or 0),
            str(payload.get("prompt_preview") or ""),
            str(payload.get("response_preview") or ""),
            payload.get("user_id"),
            now(),
        ),
    )
    return int(cursor.lastrowid or 0)


def llm_calls(
    limit: int = 40,
    offset: int = 0,
    only_failures: bool = False,
    kind: Optional[str] = None,
    provider: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """فهرست تماس‌های مدل با فیلترهای ساده (تازه‌ترین اول)."""
    where: List[str] = []
    params: List[Any] = []
    if only_failures:
        where.append("ok = 0")
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if provider:
        where.append("provider = ?")
        params.append(provider)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    rows = _query(
        f"SELECT * FROM llm_calls {clause} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
        tuple(params + [limit, offset]),
    )
    return [dict(row) for row in rows]


def count_llm_calls(
    only_failures: bool = False, kind: Optional[str] = None, provider: Optional[str] = None
) -> int:
    where: List[str] = []
    params: List[Any] = []
    if only_failures:
        where.append("ok = 0")
    if kind:
        where.append("kind = ?")
        params.append(kind)
    if provider:
        where.append("provider = ?")
        params.append(provider)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    row = _one(f"SELECT COUNT(*) AS value FROM llm_calls {clause}", tuple(params))
    return int(row["value"]) if row else 0


def llm_call(call_id: int) -> Optional[Dict[str, Any]]:
    return row_to_dict(_one("SELECT * FROM llm_calls WHERE id = ?", (call_id,)))


def llm_stats() -> Dict[str, Any]:
    """آمار کلی مصرف مدل زبانی برای داشبورد پنل ادمین."""
    total = _one("SELECT COUNT(*) AS value FROM llm_calls")
    ok = _one("SELECT COUNT(*) AS value FROM llm_calls WHERE ok = 1")
    failed = _one("SELECT COUNT(*) AS value FROM llm_calls WHERE ok = 0")
    summed = _one(
        """SELECT COALESCE(SUM(total_tokens), 0) AS tokens,
                  COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                  COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                  COALESCE(AVG(CASE WHEN ok = 1 THEN latency_ms END), 0) AS avg_latency,
                  COALESCE(MAX(CASE WHEN ok = 1 THEN latency_ms END), 0) AS max_latency
           FROM llm_calls"""
    )
    fallback = _one("SELECT COUNT(*) AS value FROM llm_calls WHERE ok = 1 AND role = 'fallback'")
    primary = _one("SELECT COUNT(*) AS value FROM llm_calls WHERE ok = 1 AND role = 'primary'")
    skipped = _one("SELECT COUNT(*) AS value FROM llm_calls WHERE status = 'skipped'")
    day_start = now() - 24 * 3600
    today = _one("SELECT COUNT(*) AS value FROM llm_calls WHERE created_at >= ?", (day_start,))
    today_tokens = _one(
        "SELECT COALESCE(SUM(total_tokens), 0) AS value FROM llm_calls WHERE created_at >= ? AND ok = 1",
        (day_start,),
    )
    users = _one("SELECT COUNT(DISTINCT user_id) AS value FROM llm_calls WHERE user_id IS NOT NULL")
    last_ok = _one("SELECT * FROM llm_calls WHERE ok = 1 ORDER BY created_at DESC LIMIT 1")
    last_fail = _one("SELECT * FROM llm_calls WHERE ok = 0 ORDER BY created_at DESC LIMIT 1")

    total_calls = int(total["value"]) if total else 0
    ok_calls = int(ok["value"]) if ok else 0
    return {
        "total": total_calls,
        "ok": ok_calls,
        "failed": int(failed["value"]) if failed else 0,
        "success_rate": round(100 * ok_calls / total_calls) if total_calls else 0,
        "tokens": int(summed["tokens"]) if summed else 0,
        "prompt_tokens": int(summed["prompt_tokens"]) if summed else 0,
        "completion_tokens": int(summed["completion_tokens"]) if summed else 0,
        "avg_latency": int(summed["avg_latency"]) if summed else 0,
        "max_latency": int(summed["max_latency"]) if summed else 0,
        "fallback_ok": int(fallback["value"]) if fallback else 0,
        "primary_ok": int(primary["value"]) if primary else 0,
        "skipped": int(skipped["value"]) if skipped else 0,
        "today": int(today["value"]) if today else 0,
        "today_tokens": int(today_tokens["value"]) if today_tokens else 0,
        "users": int(users["value"]) if users else 0,
        "last_success": row_to_dict(last_ok),
        "last_failure": row_to_dict(last_fail),
    }


def llm_provider_stats(provider_key: str) -> Dict[str, Any]:
    row = _one(
        """SELECT COUNT(*) AS total,
                  COALESCE(SUM(CASE WHEN ok = 1 THEN 1 ELSE 0 END), 0) AS ok,
                  COALESCE(SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END), 0) AS failed,
                  COALESCE(SUM(total_tokens), 0) AS tokens,
                  COALESCE(AVG(CASE WHEN ok = 1 THEN latency_ms END), 0) AS avg_latency,
                  COALESCE(MAX(created_at), 0) AS last_at
           FROM llm_calls WHERE provider = ?""",
        (provider_key,),
    )
    last_error = _one(
        "SELECT error, status, created_at FROM llm_calls WHERE provider = ? AND ok = 0 ORDER BY created_at DESC LIMIT 1",
        (provider_key,),
    )
    data = dict(row) if row else {}
    total = int(data.get("total") or 0)
    oks = int(data.get("ok") or 0)
    return {
        "total": total,
        "ok": oks,
        "failed": int(data.get("failed") or 0),
        "tokens": int(data.get("tokens") or 0),
        "avg_latency": int(data.get("avg_latency") or 0),
        "success_rate": round(100 * oks / total) if total else 0,
        "last_at": float(data.get("last_at") or 0),
        "last_error": row_to_dict(last_error),
    }


def llm_kind_stats() -> List[Dict[str, Any]]:
    """مصرف به تفکیک نوع کاربرد (فال، تست، پاپ‌اپ)."""
    rows = _query(
        """SELECT kind,
                  COUNT(*) AS total,
                  COALESCE(SUM(CASE WHEN ok = 1 THEN 1 ELSE 0 END), 0) AS ok,
                  COALESCE(SUM(total_tokens), 0) AS tokens,
                  COALESCE(AVG(CASE WHEN ok = 1 THEN latency_ms END), 0) AS avg_latency
           FROM llm_calls GROUP BY kind ORDER BY total DESC"""
    )
    result: List[Dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        total = int(data["total"] or 0)
        oks = int(data["ok"] or 0)
        data["success_rate"] = round(100 * oks / total) if total else 0
        data["avg_latency"] = int(data["avg_latency"] or 0)
        result.append(data)
    return result


def llm_kind_stats_for(kind: str) -> Dict[str, Any]:
    """آمار یک کاربرد خاص (فال/تست/پاپ‌اپ) برای صفحهٔ پرامپت‌ها."""
    row = _one(
        """SELECT COUNT(*) AS total,
                  COALESCE(SUM(CASE WHEN ok = 1 THEN 1 ELSE 0 END), 0) AS ok,
                  COALESCE(SUM(total_tokens), 0) AS tokens,
                  COALESCE(AVG(CASE WHEN ok = 1 THEN latency_ms END), 0) AS avg_latency,
                  COALESCE(MAX(created_at), 0) AS last_at
           FROM llm_calls WHERE kind = ?""",
        (kind,),
    )
    data = dict(row) if row else {}
    total = int(data.get("total") or 0)
    oks = int(data.get("ok") or 0)
    return {
        "total": total,
        "ok": oks,
        "failed": total - oks,
        "tokens": int(data.get("tokens") or 0),
        "avg_latency": int(data.get("avg_latency") or 0),
        "success_rate": round(100 * oks / total) if total else 0,
        "last_at": float(data.get("last_at") or 0),
    }


def llm_model_stats() -> List[Dict[str, Any]]:
    """مصرف به تفکیک مدل؛ برای دیدن اینکه کدام مدل واقعاً جواب می‌دهد."""
    rows = _query(
        """SELECT provider, provider_label, model,
                  COUNT(*) AS total,
                  COALESCE(SUM(CASE WHEN ok = 1 THEN 1 ELSE 0 END), 0) AS ok,
                  COALESCE(SUM(total_tokens), 0) AS tokens,
                  COALESCE(AVG(CASE WHEN ok = 1 THEN latency_ms END), 0) AS avg_latency
           FROM llm_calls GROUP BY provider, model ORDER BY total DESC"""
    )
    result: List[Dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        total = int(data["total"] or 0)
        oks = int(data["ok"] or 0)
        data["success_rate"] = round(100 * oks / total) if total else 0
        data["avg_latency"] = int(data["avg_latency"] or 0)
        result.append(data)
    return result


def llm_daily(days: int = 14) -> List[Dict[str, Any]]:
    """نمودار مصرف روزانه (تعداد تماس، موفق، خطا، توکن)."""
    since = now() - days * 86400
    rows = _query(
        """SELECT CAST(created_at / 86400 AS INTEGER) AS bucket,
                  COUNT(*) AS total,
                  COALESCE(SUM(CASE WHEN ok = 1 THEN 1 ELSE 0 END), 0) AS ok,
                  COALESCE(SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END), 0) AS failed,
                  COALESCE(SUM(total_tokens), 0) AS tokens
           FROM llm_calls WHERE created_at >= ?
           GROUP BY bucket ORDER BY bucket DESC""",
        (since,),
    )
    result: List[Dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        data["stamp"] = float(data["bucket"]) * 86400
        data["total"] = int(data["total"] or 0)
        data["ok"] = int(data["ok"] or 0)
        data["failed"] = int(data["failed"] or 0)
        data["tokens"] = int(data["tokens"] or 0)
        result.append(data)
    return result


def open_breaker(provider_key: str, reason: str, seconds: float) -> None:
    """یک ارائه‌دهنده را برای مدتی کنار می‌گذارد (ثبت پایدار در دیتابیس)."""
    stamp = now()
    until = stamp + max(1.0, float(seconds))
    _execute(
        """INSERT INTO llm_breakers (provider, reason, until, created_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(provider) DO UPDATE SET
             reason = excluded.reason, until = excluded.until, created_at = excluded.created_at""",
        (provider_key, str(reason or "")[:300], until, stamp),
    )


def breaker_for(provider_key: str) -> Optional[Dict[str, Any]]:
    """اگر مدار این ارائه‌دهنده باز است، اطلاعاتش را برمی‌گرداند."""
    row = _one("SELECT * FROM llm_breakers WHERE provider = ?", (provider_key,))
    if not row:
        return None
    data = dict(row)
    if float(data["until"]) <= now():
        _execute("DELETE FROM llm_breakers WHERE provider = ?", (provider_key,))
        return None
    data["remaining"] = int(float(data["until"]) - now())
    return data


def close_breaker(provider_key: str) -> None:
    _execute("DELETE FROM llm_breakers WHERE provider = ?", (provider_key,))


def open_breakers() -> List[Dict[str, Any]]:
    """فهرست مدارهای باز (با پاک‌کردن منقضی‌ها)."""
    _execute("DELETE FROM llm_breakers WHERE until <= ?", (now(),))
    rows = _query("SELECT * FROM llm_breakers ORDER BY until DESC")
    result: List[Dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        data["remaining"] = int(float(data["until"]) - now())
        data["age"] = int(now() - float(data["created_at"]))
        result.append(data)
    return result


def llm_last_call(provider_key: str) -> Optional[Dict[str, Any]]:
    """آخرین تلاش (موفق یا ناموفق) با یک ارائه‌دهنده؛ برای مدارشکن پایدار."""
    return row_to_dict(
        _one(
            "SELECT * FROM llm_calls WHERE provider = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (provider_key,),
        )
    )


def llm_recent_failures(limit: int = 20) -> List[Dict[str, Any]]:
    rows = _query(
        "SELECT * FROM llm_calls WHERE ok = 0 ORDER BY created_at DESC, id DESC LIMIT ?", (limit,)
    )
    return [dict(row) for row in rows]


def purge_llm_calls(keep_days: int = 60) -> int:
    """ردیف‌های قدیمی لاگ مدل را پاک می‌کند تا دیتابیس بی‌نهایت رشد نکند."""
    cutoff = now() - keep_days * 86400
    cursor = _execute("DELETE FROM llm_calls WHERE created_at < ?", (cutoff,))
    return int(cursor.rowcount or 0)


# --------------------------------------------------------------------------- #
# فعالیت کاربر و بازخورد / activity + feedback
# --------------------------------------------------------------------------- #


def touch_user_activity(user_id: int, min_gap: float = 300.0) -> Optional[float]:
    """آخرین فعالیت کاربر را به‌روز می‌کند، ولی نه بیشتر از هر `min_gap` ثانیه.

    مقدار قبلی را برمی‌گرداند (برای تشخیص «چند وقت نبودی»). نوشتن در هر درخواست
    هم بی‌دلیل دیتابیس را قفل نمی‌کند.
    """
    row = _one("SELECT last_active_at FROM users WHERE id = ?", (user_id,))
    if row is None:
        return None
    previous = float(row["last_active_at"]) if row["last_active_at"] is not None else None
    stamp = now()
    if previous is not None and (stamp - previous) < min_gap:
        return previous
    _execute("UPDATE users SET last_active_at = ? WHERE id = ?", (stamp, user_id))
    return previous


def set_last_active(user_id: int, stamp: Optional[float] = None) -> None:
    _execute(
        "UPDATE users SET last_active_at = ? WHERE id = ?",
        (stamp if stamp is not None else now(), user_id),
    )


def mark_feedback_asked(user_id: int) -> None:
    _execute("UPDATE users SET feedback_asked_at = ? WHERE id = ?", (now(), user_id))


def save_feedback(user_id: int, rating: int, comment: str, page: str = "") -> int:
    cursor = _execute(
        "INSERT INTO feedback (user_id, rating, comment, page, created_at) VALUES (?, ?, ?, ?, ?)",
        (user_id, max(0, min(5, int(rating))), str(comment or "")[:2000], str(page or "")[:120], now()),
    )
    return int(cursor.lastrowid or 0)


def user_feedback(user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    rows = _query(
        "SELECT * FROM feedback WHERE user_id = ? ORDER BY created_at DESC LIMIT ?", (user_id, limit)
    )
    return [dict(row) for row in rows]


def count_feedback() -> int:
    row = _one("SELECT COUNT(*) AS value FROM feedback")
    return int(row["value"]) if row else 0


def all_feedback(limit: int = 50, offset: int = 0, only_comments: bool = False) -> List[Dict[str, Any]]:
    clause = "WHERE TRIM(comment) <> ''" if only_comments else ""
    rows = _query(
        f"""SELECT f.*, u.phone AS phone, u.name AS user_name, u.family AS user_family
            FROM feedback f LEFT JOIN users u ON u.id = f.user_id
            {clause} ORDER BY f.created_at DESC LIMIT ? OFFSET ?""",
        (limit, offset),
    )
    return [dict(row) for row in rows]


def count_feedback_filtered(only_comments: bool = False) -> int:
    clause = "WHERE TRIM(comment) <> ''" if only_comments else ""
    row = _one(f"SELECT COUNT(*) AS value FROM feedback {clause}")
    return int(row["value"]) if row else 0


def feedback_stats() -> Dict[str, Any]:
    """میانگین امتیاز و توزیع ستاره‌ها برای پنل ادمین."""
    row = _one(
        """SELECT COUNT(*) AS total,
                  COALESCE(AVG(CASE WHEN rating > 0 THEN rating END), 0) AS average,
                  COALESCE(SUM(CASE WHEN TRIM(comment) <> '' THEN 1 ELSE 0 END), 0) AS comments
           FROM feedback"""
    )
    distribution = {star: 0 for star in range(1, 6)}
    for item in _query(
        "SELECT rating, COUNT(*) AS value FROM feedback WHERE rating BETWEEN 1 AND 5 GROUP BY rating"
    ):
        distribution[int(item["rating"])] = int(item["value"])
    total = int(row["total"]) if row else 0
    return {
        "total": total,
        "average": round(float(row["average"] or 0), 2) if row else 0.0,
        "comments": int(row["comments"]) if row else 0,
        "distribution": distribution,
        "commented_rate": round(100 * int(row["comments"] or 0) / total) if row and total else 0,
    }


def set_attempt_ai_note(attempt_id: int, note: str, meta: str = "") -> None:
    _execute("UPDATE test_attempts SET ai_note = ?, ai_meta = ? WHERE id = ?", (note, meta, attempt_id))


def count_readings_by_user(user_id: int) -> int:
    row = _one("SELECT COUNT(*) AS value FROM readings WHERE user_id = ?", (user_id,))
    return int(row["value"]) if row else 0


def count_attempts_by_user(user_id: int, completed_only: bool = True) -> int:
    clause = "AND completed_at IS NOT NULL" if completed_only else ""
    row = _one(f"SELECT COUNT(*) AS value FROM test_attempts WHERE user_id = ? {clause}", (user_id,))
    return int(row["value"]) if row else 0


# --------------------------------------------------------------------------- #
# تبلیغات / ads
# --------------------------------------------------------------------------- #

# ستون‌هایی که مدیر می‌تواند بنویسد؛ بقیه (شناسه و آمار) دست‌نخورده می‌مانند.
AD_FIELDS = (
    "title",
    "body",
    "media_kind",
    "media_file",
    "media_name",
    "media_bytes",
    "link_url",
    "cta_label",
    "placement",
    "skip_allowed",
    "skip_after",
    "hold_seconds",
    "dismiss_days",
    "max_per_day",
    "starts_at",
    "ends_at",
    "hour_from",
    "hour_to",
    "weekdays",
    "weight",
    "active",
)


def ad_create(payload: Dict[str, Any]) -> int:
    """تبلیغ تازه می‌سازد و شناسه‌اش را برمی‌گرداند."""
    data = {key: payload.get(key) for key in AD_FIELDS if key in payload}
    stamp = now()
    columns = ", ".join(data) if data else "title"
    placeholders = ", ".join("?" for _ in data) if data else "?"
    values = tuple(data.values()) if data else ("",)
    cursor = _execute(
        f"INSERT INTO ads ({columns}, created_at, updated_at) VALUES ({placeholders}, ?, ?)",
        (*values, stamp, stamp),
    )
    return int(cursor.lastrowid or 0)


def ad_update(ad_id: int, payload: Dict[str, Any]) -> None:
    data = {key: payload.get(key) for key in AD_FIELDS if key in payload}
    if not data:
        return
    columns = ", ".join(f"{key} = ?" for key in data)
    _execute(f"UPDATE ads SET {columns}, updated_at = ? WHERE id = ?", (*data.values(), now(), ad_id))


def ad_get(ad_id: int) -> Optional[Dict[str, Any]]:
    return row_to_dict(_one("SELECT * FROM ads WHERE id = ?", (int(ad_id),)))


def ad_delete(ad_id: int) -> None:
    """تبلیغ و رویدادهایش را پاک می‌کند (فایل رسانه در لایهٔ `ads` پاک می‌شود)."""
    _execute("DELETE FROM ad_events WHERE ad_id = ?", (int(ad_id),))
    _execute("DELETE FROM ads WHERE id = ?", (int(ad_id),))


def ads_all(active_only: bool = False) -> List[Dict[str, Any]]:
    clause = "WHERE active = 1" if active_only else ""
    rows = _query(f"SELECT * FROM ads {clause} ORDER BY active DESC, weight DESC, updated_at DESC")
    return [dict(row) for row in rows]


def count_ads(active_only: bool = False) -> int:
    clause = "WHERE active = 1" if active_only else ""
    row = _one(f"SELECT COUNT(*) AS value FROM ads {clause}")
    return int(row["value"]) if row else 0


def ad_event_add(ad_id: int, actor: str, kind: str) -> None:
    _execute(
        "INSERT INTO ad_events (ad_id, actor, kind, created_at) VALUES (?, ?, ?, ?)",
        (int(ad_id), str(actor or "")[:64], str(kind or "")[:16], now()),
    )


def ad_event_count(ad_id: int, kind: str, since: Optional[float] = None, actor: str = "") -> int:
    """شمارش یک نوع رویداد؛ مثلاً «چند بار امروز به این کاربر نشان داده شده»."""
    clauses = ["ad_id = ?", "kind = ?"]
    params: List[Any] = [int(ad_id), str(kind)]
    if since is not None:
        clauses.append("created_at >= ?")
        params.append(float(since))
    if actor:
        clauses.append("actor = ?")
        params.append(str(actor))
    row = _one(f"SELECT COUNT(*) AS value FROM ad_events WHERE {' AND '.join(clauses)}", tuple(params))
    return int(row["value"]) if row else 0


def ad_last_event_at(ad_id: int, actor: str, kind: str) -> Optional[float]:
    row = _one(
        "SELECT created_at FROM ad_events WHERE ad_id = ? AND actor = ? AND kind = ? ORDER BY created_at DESC LIMIT 1",
        (int(ad_id), str(actor), str(kind)),
    )
    return float(row["created_at"]) if row else None


# --------------------------------------------------------------------------- #
# بازی «ذهن‌خوان» / mind-reader game
# --------------------------------------------------------------------------- #


def mind_create(user_id: Optional[int], visitor: str) -> str:
    """یک دورِ بازی تازه می‌سازد و شناسه‌اش را برمی‌گرداند."""
    game_id = uuid.uuid4().hex[:16]
    stamp = now()
    _execute(
        """INSERT INTO mind_games (id, user_id, visitor, state, created_at, updated_at)
           VALUES (?, ?, ?, '{}', ?, ?)""",
        (game_id, int(user_id) if user_id else None, str(visitor or "")[:48], stamp, stamp),
    )
    return game_id


def mind_get(game_id: str) -> Optional[Dict[str, Any]]:
    """یک دورِ بازی با وضعیتِ خوانده‌شده (JSON → دیکشنری)."""
    row = _one("SELECT * FROM mind_games WHERE id = ?", (str(game_id or ""),))
    if not row:
        return None
    data = dict(row)
    try:
        data["state"] = json.loads(data.get("state") or "{}")
    except (TypeError, ValueError):
        data["state"] = {}
    return data


def mind_save(
    game_id: str,
    state: Dict[str, Any],
    turns: int = 0,
    guesses: int = 0,
    solved: int = 0,
) -> None:
    """وضعیت بازی را ذخیره می‌کند (هر جواب، یک ذخیره)."""
    _execute(
        """UPDATE mind_games SET state = ?, turns = ?, guesses = ?, solved = MAX(solved, ?),
           updated_at = ? WHERE id = ?""",
        (
            json.dumps(state, ensure_ascii=False, separators=(",", ":")),
            int(turns),
            int(guesses),
            int(solved),
            now(),
            str(game_id),
        ),
    )


def mind_learn(game_id: str, user_id: Optional[int], name: str, values: Dict[str, Any]) -> None:
    """شخصیتی را که کاربر نامش را نوشت ذخیره می‌کند تا دیتاست بزرگ‌تر شود."""
    label = " ".join(str(name or "").split())[:60]
    if len(label) < 2:
        return
    _execute(
        "INSERT INTO mind_learned (game_id, user_id, name, values_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            str(game_id or ""),
            int(user_id) if user_id else None,
            label,
            json.dumps(values or {}, ensure_ascii=False, separators=(",", ":")),
            now(),
        ),
    )


def mind_learned(limit: int = 120) -> List[Dict[str, Any]]:
    """شخصیت‌های یادگرفته‌شده؛ برای هر نام فقط تازه‌ترین ردیف.

    (SQLite با `MAX(...)` و GROUP BY، مقادیر همان ردیفِ بیشینه را برمی‌گرداند.)
    """
    rows = _query(
        """SELECT name, values_json, MAX(created_at) AS created_at FROM mind_learned
           GROUP BY name ORDER BY created_at DESC LIMIT ?""",
        (max(1, min(500, int(limit))),),
    )
    collected: List[Dict[str, Any]] = []
    for row in rows:
        data = dict(row)
        try:
            data["values"] = json.loads(data.get("values_json") or "{}")
        except (TypeError, ValueError):
            data["values"] = {}
        if isinstance(data["values"], dict):
            collected.append({"name": data["name"], "values": data["values"]})
    return collected


def mind_count(games: bool = True) -> int:
    """شمارش دورهای بازی یا شخصیت‌های یادگرفته‌شده (برای آمار)."""
    table = "mind_games" if games else "mind_learned"
    row = _one(f"SELECT COUNT(*) AS value FROM {table}")
    return int(row["value"]) if row else 0


def ad_actor_events(actor: str, kinds: List[str], since: Optional[float] = None) -> Dict[str, Any]:
    """تعداد و آخرین زمانِ رویدادهای یک بازدیدکننده، در **همهٔ** تبلیغ‌ها.

    چرا لازم است: سقفِ هر تبلیغ (`max_per_day`) فقط می‌گوید «این تبلیغ چند بار»؛
    ولی سؤال «کاربر در کل چند پاپ‌اپ دیده» به یک تبلیغ خاص ربطی ندارد. این‌جا نوعِ
    رویداد صریح فرستاده می‌شود (مثلاً `["popup"]`) تا شمارشِ نمایشِ بنر با پاپ‌اپ
    قاطی نشود.

    خروجی: ``{"count": int, "last_at": float | None}``.
    """
    names = [str(kind) for kind in kinds if kind]
    if not actor or not names:
        return {"count": 0, "last_at": None}
    placeholders = ", ".join("?" for _ in names)
    clauses = ["actor = ?", f"kind IN ({placeholders})"]
    params: List[Any] = [str(actor), *names]
    if since is not None:
        clauses.append("created_at >= ?")
        params.append(float(since))
    row = _one(
        f"SELECT COUNT(*) AS value, MAX(created_at) AS last_at FROM ad_events WHERE {' AND '.join(clauses)}",
        tuple(params),
    )
    if not row or not int(row["value"] or 0):
        return {"count": 0, "last_at": None}
    last = row["last_at"]
    return {"count": int(row["value"]), "last_at": float(last) if last else None}


def ad_stats(ad_id: int, days: int = 30) -> Dict[str, Any]:
    """آمار یک تبلیغ: نمایش، کلیک، ردکردن و نرخ کلیک."""
    since = now() - days * 86400
    counts = {
        row["kind"]: int(row["value"])
        for row in _query(
            "SELECT kind, COUNT(*) AS value FROM ad_events WHERE ad_id = ? AND created_at >= ? GROUP BY kind",
            (int(ad_id), since),
        )
    }
    impressions = counts.get("impression", 0)
    clicks = counts.get("click", 0)
    return {
        "impressions": impressions,
        "clicks": clicks,
        "skips": counts.get("skip", 0),
        "dismisses": counts.get("dismiss", 0),
        "ctr": round(100 * clicks / impressions, 1) if impressions else 0.0,
    }


def ad_stats_all(days: int = 30) -> Dict[int, Dict[str, Any]]:
    """آمار همهٔ تبلیغ‌ها یک‌جا (برای فهرست پنل، بدون N+1)."""
    since = now() - days * 86400
    result: Dict[int, Dict[str, Any]] = {}
    for row in _query(
        """SELECT ad_id, kind, COUNT(*) AS value FROM ad_events
           WHERE created_at >= ? GROUP BY ad_id, kind""",
        (since,),
    ):
        bucket = result.setdefault(int(row["ad_id"]), {"impressions": 0, "clicks": 0, "skips": 0, "dismisses": 0, "ctr": 0.0})
        bucket[str(row["kind"])] = int(row["value"])
    for bucket in result.values():
        impressions = int(bucket.get("impressions") or 0)
        clicks = int(bucket.get("clicks") or 0)
        bucket["ctr"] = round(100 * clicks / impressions, 1) if impressions else 0.0
    return result


def ad_daily(ad_id: int, days: int = 14) -> List[Dict[str, Any]]:
    """نمایش و کلیک روزانهٔ یک تبلیغ (برای نمودار میله‌ای ساده در پنل)."""
    since = now() - days * 86400
    buckets: Dict[str, Dict[str, int]] = {}
    for row in _query(
        "SELECT kind, created_at FROM ad_events WHERE ad_id = ? AND created_at >= ? ORDER BY created_at",
        (int(ad_id), since),
    ):
        day = time.strftime("%Y-%m-%d", time.localtime(float(row["created_at"])))
        bucket = buckets.setdefault(day, {"impressions": 0, "clicks": 0})
        if row["kind"] in bucket:
            bucket[str(row["kind"])] += 1
    return [{"day": day, **bucket} for day, bucket in sorted(buckets.items())]


def recent_ad_events(limit: int = 40, ad_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """آخرین رویدادهای تبلیغات (اختیاری فقط برای یک تبلیغ)."""
    if ad_id:
        rows = _query(
            """SELECT e.*, a.title AS ad_title FROM ad_events e
               LEFT JOIN ads a ON a.id = e.ad_id
               WHERE e.ad_id = ? ORDER BY e.created_at DESC LIMIT ?""",
            (int(ad_id), limit),
        )
    else:
        rows = _query(
            """SELECT e.*, a.title AS ad_title FROM ad_events e
               LEFT JOIN ads a ON a.id = e.ad_id ORDER BY e.created_at DESC LIMIT ?""",
            (limit,),
        )
    return [dict(row) for row in rows]


