"""دودی‌تست ساینج: ورود، دستگاه، گروه، رسانه، لیست، اسکژول، الرت، استریم.

توجه: اپ «ساینج» در این ریپازیتوری نیست (یک پروژهٔ جدا روی پورت ۸۰۱۰ است).
این ابزار برای وقتی نگه داشته شده که آن پروژه کنار نشانه اجرا شود. رمز مدیر
در سورس نیست و از `.env`/محیط خوانده می‌شود.
"""

import io
import os
import struct
import sys
import zlib

import urllib.request
import http.cookiejar
import json

BASE = "http://127.0.0.1:8010"

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

PASS = 0
FAIL = 0


def req(method, path, body=None, raw=False, headers=None):
    global PASS, FAIL
    data = None
    h = headers or {}
    if body is not None and not raw:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    elif raw:
        data = body
    r = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        resp = opener.open(r)
        out = resp.read()
        status = resp.status
    except urllib.error.HTTPError as e:
        out = e.read()
        status = e.code
    try:
        parsed = json.loads(out) if out else {}
    except Exception:
        parsed = out
    return status, parsed


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {extra}")


def make_png(w=64, h=48):
    def chunk(tag, payload):
        c = struct.pack(">I", len(payload)) + tag + payload
        return c + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = b""
    for _ in range(h):
        raw += b"\x00" + bytes([120, 80, 200]) * w
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


print("== ورود ==")
s, d = req("POST", "/api/login", {"username": SIGN_USER, "password": SIGN_PASSWORD})
check("login success", s == 200 and d.get("ok"), f"status={s} {d}")
s, d = req("POST", "/api/login", {"username": SIGN_USER, "password": "WRONG"})
check("wrong password rejected", s == 401, f"status={s}")
s, d = req("POST", "/api/login", {"username": SIGN_USER, "password": SIGN_PASSWORD})
check("re-login after failure (not locked)", s == 200, f"status={s} {d}")
s, d = req("GET", "/api/me")
check("me", s == 200 and d.get("username") == SIGN_USER)

# الرت‌های باقی‌مانده از اجراهای قبلی پاک شوند تا اعداد تست دقیق بمانند
_, old_alerts = req("GET", "/api/alerts")
for a in old_alerts or []:
    req("DELETE", f"/api/alerts/{a['id']}")

print("== داشبورد ==")
s, d = req("GET", "/api/stats")
check("stats", s == 200 and "devices_total" in d, f"status={s}")

print("== رسانه (آپلود عکس) ==")
png = make_png()
boundary = "----sgboundary7MA4YWxkTrZu0gW"
body = (
    f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"test.png\"\r\n"
    f"Content-Type: image/png\r\n\r\n".encode() + png + f"\r\n--{boundary}--\r\n".encode()
)
s, d = req("POST", "/api/media", body, raw=True, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
check("upload image", s == 200 and d.get("created"), f"status={s} {d}")
media_id = d["created"][0] if d.get("created") else None
s, d2 = req("GET", "/api/media")
if s == 200 and d2:
    m = d2[0]
    check("image dims probed", m["width"] == 64 and m["height"] == 48, f"got {m['width']}x{m['height']}")

print("== استریم با Range ==")
r = urllib.request.Request(f"{BASE}/stream/{media_id}", headers={"Range": "bytes=0-99"})
resp = opener.open(r)
check("range 206", resp.status == 206, f"status={resp.status}")
check("content-range", (resp.headers.get("Content-Range") or "").startswith("bytes 0-99/"), resp.headers.get("Content-Range"))
check("accept-ranges", resp.headers.get("Accept-Ranges") == "bytes")
check("payload size", len(resp.read()) == 100)
resp = opener.open(urllib.request.Request(f"{BASE}/stream/{media_id}", headers={"Range": "bytes=10-"}))
check("open range from 10", resp.status == 206)

print("== گروه / لیست پخش / دستگاه ==")
s, d = req("POST", "/api/groups", {"name": "گروه تست", "color": "#ff00aa"})
check("create group", s == 200 and d.get("id"), f"status={s} {d}")
gid = d["id"]

s, d = req("POST", "/api/playlists", {"name": "لیست تست", "shuffle": False, "transition": "fade"})
check("create playlist", s == 200 and d.get("id"))
pid = d["id"]

s, d = req("POST", f"/api/playlists/{pid}/items", {"media_id": media_id, "duration": 5, "fit": "cover"})
check("add item", s == 200 and len(d.get("items", [])) == 1, f"status={s} {d}")
item_id = d["items"][0]["item_id"]

s, d = req("POST", f"/api/playlists/{pid}/reorder", {"order": [item_id]})
check("reorder", s == 200)

s, d = req("POST", "/api/devices", {"name": "تلویزیون تست", "group_id": gid, "playlist_id": pid,
                                    "width": 1920, "height": 1080, "volume": 70})
check("create device", s == 200 and d.get("code"), f"status={s} {d}")
code = d["code"]
did = d["id"]

s, d = req("GET", "/api/devices")
created = [x for x in d if x["id"] == did]
check("device list resolves playlist", s == 200 and created and created[0]["effective_playlist"] == "لیست تست",
      created[0]["effective_playlist"] if created else "not found")

print("== اسکژول ==")
s, d = req("POST", "/api/schedules", {"name": "کاری", "target_type": "device", "target_id": did,
                                      "days": "0123456", "on_time": "00:00", "off_time": "23:59"})
check("create schedule", s == 200 and d.get("id"), f"status={s} {d}")
s, d = req("POST", "/api/schedules", {"name": "بدون ساعت", "on_time": "bad", "off_time": "22:00"})
check("invalid time rejected", s == 400, f"status={s}")

print("== الرت ==")
s, d = req("POST", "/api/alerts", {"title": "تست الرت", "message": "سلام", "level": "warn",
                                   "target_type": "device", "target_id": did, "duration": 8})
check("create alert", s == 200 and d.get("id"), f"status={s} {d}")

print("== API پخش‌کننده ==")
s, d = req("GET", f"/api/player/{code}/config")
check("player config", s == 200 and d.get("ok"), f"status={s}")
check("power on within schedule", d.get("power", {}).get("on") is True, d.get("power"))
check("playlist items delivered", len(d.get("playlist", {}).get("items", [])) == 1)
it = d["playlist"]["items"][0]
check("item has stream url", it["url"] == f"/stream/{media_id}", it["url"])
check("item duration override", it["duration"] == 5.0, it["duration"])
check("item fit cover", it["fit"] == "cover")
check("alert delivered", len(d.get("alerts", [])) == 1 and d["alerts"][0]["title"] == "تست الرت", d.get("alerts"))
alert_ids = [a["id"] for a in d.get("alerts", [])]

# پخش‌کننده بعد از نمایش، الرت را با هرت‌بیت تأیید می‌کند
s, d = req("POST", f"/api/player/{code}/heartbeat", {"state": {}, "alert_ids": alert_ids})
check("alert acked via heartbeat", s == 200)

s, d2 = req("GET", f"/api/player/{code}/config")
check("alert delivered only once", len(d2.get("alerts", [])) == 0, d2.get("alerts"))

s, d = req("POST", f"/api/player/{code}/heartbeat", {"state": {"title": "کلیپ اول", "playing": True}})
check("heartbeat", s == 200 and d.get("commands") is not None)

s, d = req("POST", f"/api/devices/{did}/command", {"command": "volume", "payload": {"value": 40}})
check("queue command", s == 200)
s, d = req("POST", f"/api/player/{code}/heartbeat", {"state": {}})
check("command delivered", len(d.get("commands", [])) == 1 and d["commands"][0]["command"] == "volume", d)
s, d = req("POST", f"/api/player/{code}/ack", {"command_ids": [d["commands"][0]["id"]]})
check("ack", s == 200)
s, d = req("POST", f"/api/player/{code}/heartbeat", {"state": {}})
check("command cleared", len(d.get("commands", [])) == 0)

s, d = req("GET", "/api/player/NOPE/config")
check("bad device code 404", s == 404, f"status={s}")

print("== دسترسی بدون ورود ==")
noauth = urllib.request.build_opener()  # بدون کوکی
try:
    r = noauth.open(urllib.request.Request(f"{BASE}/api/devices"))
    check("admin api blocked w/o session", False, f"status={r.status}")
except urllib.error.HTTPError as e:
    check("admin api blocked w/o session", e.code == 401, f"code={e.code}")

print("== لوگو / صفحات ==")
resp = opener.open(f"{BASE}/logo")
check("logo endpoint", resp.status == 200 and "svg" in (resp.headers.get("Content-Type") or ""))
for path in ("/admin/", "/player", "/static/admin/css/admin.css", "/static/admin/js/app.js",
             "/static/player.html", "/static/fontawesome/css/all.min.css",
             "/static/fonts/Pinar-FD-Bold.woff2", "/static/fonts/YekanBakhFaNum-Bold.woff2"):
    resp = opener.open(BASE + path)
    check(f"GET {path}", resp.status == 200)

print("== تنظیمات / زیرنویس / تغییر رمز ==")
s, d = req("PUT", "/api/settings", {"values": {"ticker": "خبر فوری", "default_image_duration": "8"}})
check("settings saved", s == 200 and d.get("ticker") == "خبر فوری")
s, d = req("POST", "/api/change-password", {"old_password": "bad", "new_password": "xxxxxxxx"})
check("wrong old password", s == 400, f"status={s}")

vtt = "WEBVTT\n\n00:00:00,000 --> 00:00:02,000\nسلام دنیا\n".encode()
srt = "1\n00:00:01,500 --> 00:00:03,000\nزيرنويس فارسي\n"
boundary = "----sgsub9x"
body = (
    f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"sub.srt\"\r\n"
    f"Content-Type: text/plain\r\n\r\n".encode() + srt.encode() + f"\r\n--{boundary}--\r\n".encode()
)
s, d = req("POST", f"/api/media/{media_id}/subtitle", body, raw=True,
           headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
check("subtitle upload (srt)", s == 200, f"status={s} {d}")
resp = opener.open(f"{BASE}/stream/sub/{media_id}")
txt = resp.read().decode()
check("subtitle served as vtt", txt.startswith("WEBVTT") and "00:00:01.500" in txt, txt[:60])

print("== حذف ==")
s, d = req("DELETE", f"/api/playlists/{pid}/items/{item_id}")
check("remove item", s == 200)
s, d = req("DELETE", f"/api/devices/{did}")
check("delete device", s == 200)
s, d = req("DELETE", f"/api/groups/{gid}")
check("delete group", s == 200)
s, d = req("DELETE", f"/api/playlists/{pid}")
check("delete playlist", s == 200)
s, d = req("DELETE", f"/api/media/{media_id}")
check("delete media", s == 200)
s, d = req("GET", f"/stream/{media_id}")
check("stream after delete 404", s == 404, f"status={s}")

print()
print(f"نتیجه: {PASS} موفق، {FAIL} ناموفق")
sys.exit(1 if FAIL else 0)
