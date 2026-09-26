"""بارگذاری متغیرهای محیطی از فایل `.env` — بدون هیچ وابستگی بیرونی.

هیچ کلید و رمزی در سورس پروژه نیست؛ همه در `.env` می‌مانند (فایل در
`.gitignore` است و هرگز کامیت نمی‌شود) یا در متغیرهای محیطی سرور.

اولویت:
  ۱) متغیر محیطی واقعیِ سیستم/سرور (همیشه برنده است)
  ۲) مقادیر فایل `.env`

ترتیب جست‌وجوی فایل:
  ۱) `NESHANE_ENV_FILE` اگر ست شده باشد
  ۲) `.env` کنار ریشهٔ پروژه
  ۳) `.env` در پوشهٔ جاری

نمونهٔ خط‌های پذیرفته‌شده::

    # توضیح
    NESHANE_GEMINI_KEY=abc123
    NESHANE_ADMIN_PATH="/panel/"
    export NESHANE_LLM=on
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

ENV_FILE_VAR = "NESHANE_ENV_FILE"
ROOT = Path(__file__).resolve().parents[1]

_loaded_once = False


def _parse(text: str) -> Dict[str, str]:
    """خط‌های فایل را به دیکشنری کلید/مقدار تبدیل می‌کند."""
    values: Dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def candidates() -> list:
    """فایل‌هایی که برای خواندن `.env` امتحان می‌شوند، به ترتیب اولویت."""
    places = []
    custom = os.environ.get(ENV_FILE_VAR)
    if custom:
        places.append(Path(custom))
    places.append(ROOT / ".env")
    cwd = Path.cwd() / ".env"
    if cwd not in places:
        places.append(cwd)
    return places


def load(override: bool = False, quiet: bool = True) -> Dict[str, str]:
    """مقادیر `.env` را در محیط می‌ریزد و فهرست مقادیر خوانده‌شده را برمی‌گرداند.

    به‌صورت پیش‌فرض متغیرهای موجود را دست نمی‌زند (سرور مقدم است).
    """
    for place in candidates():
        try:
            if not place.is_file():
                continue
            values = _parse(place.read_text(encoding="utf-8"))
        except OSError:
            continue
        for key, value in values.items():
            if override or key not in os.environ:
                os.environ[key] = value
        return values
    return {}


def ensure_loaded() -> None:
    """یک‌بار در طول اجرا `.env` را می‌خواند (از `app/__init__.py` صدا زده می‌شود)."""
    global _loaded_once
    if _loaded_once:
        return
    _loaded_once = True
    load()


def secret(name: str, default: str = "") -> str:
    """یک مقدار حساس را از محیط می‌خواند و دور و برش را تمیز می‌کند."""
    value = os.environ.get(name)
    if value is None:
        return default
    value = value.strip()
    return value or default
