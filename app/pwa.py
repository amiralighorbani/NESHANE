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

import json
import os
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


# --------------------------------------------------------------------------- #
# Digital Asset Links — اثبات این‌که APK اندروید همان صاحب این دامنه است
# --------------------------------------------------------------------------- #
#
# کروم وقتی اپ اندروید آدرسی را باز می‌کند، اول `/.well-known/assetlinks.json`
# همان دامنه را می‌خواند. اگر نام بسته و اثر انگشت گواهی امضا آنجا باشد، صفحه
# تمام‌صفحه و بدون نوار آدرس باز می‌شود (حس یک اپ واقعی)؛ اگر نباشد، فقط یک
# نوار آدرس کوچک بالا می‌آید و اپ باز می‌شود.
#
# اثر انگشت «راز» نیست؛ داخل خودِ APK منتشر می‌شود. اگر روزی کلید امضا عوض شد،
# فقط این مقدار را با متغیر محیطی `NESHANE_APP_SHA256` عوض کن.
APP_PACKAGE = os.environ.get("NESHANE_APP_PACKAGE", "app.neshane").strip()
APP_SHA256 = os.environ.get(
    "NESHANE_APP_SHA256",
    "1B:F2:0E:9A:5B:E3:AD:7B:6A:36:3C:B9:B0:F4:51:11:AC:A5:BD:11:67:66:2D:40:7D:2C:F8:37:0E:0A:84:CA",
).strip()


def assetlinks() -> str:
    """محتوای `/.well-known/assetlinks.json` بر اساس بسته و اثر انگشت امضا."""
    statements = [
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": APP_PACKAGE,
                "sha256_cert_fingerprints": [APP_SHA256],
            },
        }
    ]
    return json.dumps(statements, ensure_ascii=False)
