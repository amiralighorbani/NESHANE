"""PWA: مانیفست، میان‌بر‌ها و سرویس‌ورکر.

نشانه باید روی موبایل مثل یک اپ نصب شود: آیکون روی صفحهٔ اصلی، بدون نوار آدرس،
و یک صفحهٔ «آفلاین» وقتی اینترنت نیست.

نکتهٔ مهم: مرورگرها نصب PWA و سرویس‌ورکر را فقط روی **https** یا **localhost**
فعال می‌کنند. برای تست روی گوشی واقعی، برنامه را از طریق یک تونل https باز کن
(یا روی همان گوشی از localhost استفاده کن).

سرویس‌ورکر باید از ریشه (`/sw.js`) سرو شود تا کل دامنه را بگیرد؛ اگر زیر
`/static/` باشد، اسکوپش فقط همان پوشه می‌شود.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

BASE_DIR = Path(__file__).resolve().parent
SERVICE_WORKER_PATH = BASE_DIR / "static" / "sw.js"
OFFLINE_PATH = BASE_DIR / "static" / "offline.html"

APP_NAME = "نشانه — فال و خودشناسی"
APP_SHORT = "نشانه"
THEME_COLOR = "#6b4fbb"
BACKGROUND_COLOR = "#f6f5f2"

ICON_192 = "/static/icons/icon-192.png"
ICON_512 = "/static/icons/icon-512.png"
ICON_MASKABLE = "/static/icons/icon-maskable-512.png"


def _icon(src: str, sizes: str, purpose: str = "any") -> Dict[str, str]:
    return {"src": src, "sizes": sizes, "type": "image/png", "purpose": purpose}


MANIFEST: Dict[str, Any] = {
    "id": "/",
    "name": APP_NAME,
    "short_name": APP_SHORT,
    "description": "فال حافظ، تاروت، طالع و تست‌های خودشناسی — با خوانش کامل روزانه.",
    "lang": "fa",
    "dir": "rtl",
    "start_url": "/?src=pwa",
    "scope": "/",
    "display": "standalone",
    "display_override": ["standalone", "minimal-ui"],
    "orientation": "portrait",
    "background_color": BACKGROUND_COLOR,
    "theme_color": THEME_COLOR,
    "categories": ["lifestyle", "entertainment"],
    "icons": [
        _icon(ICON_192, "192x192"),
        _icon(ICON_512, "512x512"),
        _icon(ICON_MASKABLE, "512x512", "maskable"),
        {"src": "/static/favicon.svg", "sizes": "any", "type": "image/svg+xml"},
    ],
    "shortcuts": [
        {"name": "فال امروز", "short_name": "فال", "url": "/journey", "icons": [_icon(ICON_192, "192x192")]},
        {"name": "زندگی در عدد", "short_name": "زندگی", "url": "/life", "icons": [_icon(ICON_192, "192x192")]},
        {"name": "تست‌های خودشناسی", "short_name": "تست‌ها", "url": "/tests", "icons": [_icon(ICON_192, "192x192")]},
    ],
}


def service_worker_source() -> str:
    """متن سرویس‌ورکر از فایل استاتیک خوانده می‌شود تا کش شود."""
    return SERVICE_WORKER_PATH.read_text(encoding="utf-8")
