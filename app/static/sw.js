/* نشانه — سرویس‌ورکر PWA
   استراتژی:
   * دارایی‌های استاتیک (css/js/فونت/آیکون): cache-first + تازه‌سازی در پس‌زمینه
   * صفحه‌ها (navigation): network-first، اگر اینترنت نبود همان صفحه از کش،
     و در نهایت صفحهٔ «آفلاین»
   * پاسخ‌های داینامیک (پنل ادمین، خروجی CSV، API): هرگز کش نمی‌شوند
*/

var VERSION = "neshane-v4";
var STATIC_CACHE = VERSION + "-static";
var PAGE_CACHE = VERSION + "-pages";
var OFFLINE_URL = "/static/offline.html";

var PRECACHE = [
  OFFLINE_URL,
  "/static/favicon.svg",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/manifest.webmanifest"
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then(function (cache) {
        return cache.addAll(PRECACHE);
      })
      .then(function () {
        return self.skipWaiting();
      })
      .catch(function () {
        return self.skipWaiting();
      })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches
      .keys()
      .then(function (keys) {
        return Promise.all(
          keys.map(function (key) {
            if (key !== STATIC_CACHE && key !== PAGE_CACHE) return caches.delete(key);
            return null;
          })
        );
      })
      .then(function () {
        return self.clients.claim();
      })
  );
});

function isStatic(url) {
  return url.pathname.indexOf("/static/") === 0;
}

function isPrivate(url) {
  // پنل ادمین، ورود/ثبت‌نام و خروجی‌ها را هرگز کش نکن.
  // مسیر پنل مخفی است و در سورس نمی‌آید؛ پس تشخیصش به عهدهٔ سرور است:
  // هر پاسخ پنل با هدر «Cache-Control: no-store» می‌آید و همان را می‌بینیم.
  return (
    /^\/(login|verify|signup|register|logout|inbox|health)/.test(url.pathname) ||
    /(\.csv|\/export\/)/.test(url.pathname)
  );
}

function cacheable(response) {
  // پاسخ‌های «no-store» هرگز کش نمی‌شوند (پنل مدیریت و صفحه‌های حساب).
  if (!response || response.status !== 200 || response.type !== "basic") return false;
  var control = (response.headers.get("cache-control") || "").toLowerCase();
  return control.indexOf("no-store") === -1 && control.indexOf("private") === -1;
}

self.addEventListener("fetch", function (event) {
  var request = event.request;
  if (request.method !== "GET") return;

  var url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (isPrivate(url)) return;

  // دارایی‌های استاتیک: اول از کش، بعد شبکه (و کش را تازه کن)
  if (isStatic(url)) {
    event.respondWith(
      caches.open(STATIC_CACHE).then(function (cache) {
        return cache.match(request).then(function (cached) {
          var network = fetch(request)
            .then(function (response) {
              if (response && response.status === 200) cache.put(request, response.clone());
              return response;
            })
            .catch(function () {
              return cached;
            });
          return cached || network;
        });
      })
    );
    return;
  }

  // صفحه‌ها: شبکه اول؛ اگر نبود کش، و در نهایت صفحهٔ آفلاین
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then(function (response) {
          if (cacheable(response)) {
            var copy = response.clone();
            caches.open(PAGE_CACHE).then(function (cache) {
              cache.put(request, copy);
            });
          }
          return response;
        })
        .catch(function () {
          return caches.match(request).then(function (cached) {
            return cached || caches.match(OFFLINE_URL);
          });
        })
    );
  }
});
