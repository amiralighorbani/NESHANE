# اپ اندروید «نشانه» (APK از همان PWA)

این پوشه یک **Trusted Web Activity (TWA)** است: یک اپ اندروید واقعی که همان PWA
نشانه را تمام‌صفحه و بدون نوار آدرس باز می‌کند. هیچ کد رابطی اینجا نوشته نشده و
لازم هم نیست — یک نسخه از اپ نگه می‌داریم، نه دو تا.

```
android/
├── host.txt                 ← تنها تنظیم لازم: آدرس https اپ (یک خط)
├── app/build.gradle         ← آدرس، نسخه و امضا از همین‌جا خوانده می‌شود
├── app/src/main/            ← مانیفست، آیکون‌ها و یک کلاس خالی
├── keystore.properties      ← محلی و gitignore؛ رمز کلید امضا
└── neshane-release.p12      ← محلی و gitignore؛ کلید امضا (فقط در Secretها)
```

## تنظیم آدرس

برای این‌که APK جایی برود که اپ بالا است، فقط `host.txt` را پر کن:

```bash
echo "https://neshane.example.com" > android/host.txt
```

سه چیز باید رعایت شود، وگرنه اندروید اپ را «ناامن» می‌داند:

1. **https** باشد (اندروید برای PWA و سرویس‌ورکر فقط https را قبول می‌کند).
2. **گواهی معتبر** باشد (self-signed کار نمی‌کند).
3. همان دامنه `/.well-known/assetlinks.json` را با کد زیر سرو کند:

```json
[{
  "relation": ["delegate_permission/common.handle_all_urls"],
  "target": {
    "namespace": "android_app",
    "package_name": "app.neshane",
    "sha256_cert_fingerprints": ["<اثر انگشت گواهی امضا>"]
  }
}]
```

این فایل را خودِ نشانه می‌سازد و روی `/.well-known/assetlinks.json` سرو می‌کند
(`app/pwa.py`). اگر روزی کلید امضا عوض شد، با متغیر محیطی
`NESHANE_APP_SHA256` مقدار تازه را بده. **اگر این فایل نباشد، اپ باز می‌شود ولی
کروم یک نوار آدرس نازک بالا نشان می‌دهد.**

## ساخت

ساده‌ترین راه: push روی `main`. ورک‌فلوی
`.github/workflows/android-release.yml` خودش SDK و Gradle را می‌آورد، APK را
می‌سازد و به ریلیز همان نسخه (`v` + مقدار `__version__` در `app/__init__.py`)
می‌چسباند. اگر `host.txt` خالی باشد، با یک اعلان رد می‌شود و هیچ فایل خرابی
منتشر نمی‌کند.

ساخت محلی هم ممکن است، اگر Android SDK و Gradle داشته باشی:

```bash
cd android
gradle assembleRelease
# خروجی: app/build/outputs/apk/release/app-release.apk
```

## امضا (مهم)

APK بدون امضا روی گوشی نصب نمی‌شود. کلید امضا **در مخزن نیست** (در `.gitignore`
است) تا کسی نتواند نسخهٔ جعلی «نشانه» امضا کند. برای این‌که CI با همان کلید دائمی
امضا کند، سه Secret در تنظیمات مخزن بساز:

| Secret | مقدار |
| --- | --- |
| `ANDROID_KEYSTORE_BASE64` | خروجی `base64 -w0 neshane-release.p12` |
| `ANDROID_KEYSTORE_PASSWORD` | رمز کی‌استور (در `keystore.properties`) |
| `ANDROID_KEY_ALIAS` | `neshane` |

اگر این‌ها نباشند، ورک‌فلو APK را با **امضای دیباگ** می‌سازد تا خروجی همچنان
نصب‌شدنی باشد؛ ولی برای انتشار عمومی باید کلید دائمی را ست کنی. دلیلش ساده است:
اگر روزی کلید عوض شود، اندروید اجازهٔ آپدیت روی نسخهٔ قبلی را نمی‌دهد و کاربر
باید اپ را حذف و از نو نصب کند.

> ساخت کلید تازه (فقط یک‌بار در عمر اپ؛ آن را جای امنی نگه دار):
>
> ```bash
> keytool -genkeypair -v -storetype PKCS12 -keystore neshane-release.p12 \
>   -alias neshane -keyalg RSA -keysize 4096 -validity 10000
> keytool -list -v -keystore neshane-release.p12 -alias neshane | grep SHA256
> ```

## نکته‌ها

- **نام بسته** (`app.neshane`) بعد از انتشار در مارکت‌ها قابل تغییر نیست؛ اگر
  می‌خواهی عوضش کنی، همین حالا در `app/build.gradle` بگو.
- `versionCode` و `versionName` از `__version__` خودِ اپ خونده می‌شوند، پس یک
  منبع حقیقت است و APK و سایت هیچ‌وقت از هم جدا نمی‌شوند.
- حداقل اندروید ۵٫۰ (API 21) و هدف API 34 است.
