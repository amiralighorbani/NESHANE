package app.neshane;

/**
 * نقطهٔ ورود اپ «نشانه».
 *
 * <p>هیچ منطقی اینجا نیست و لازم هم نیست: {@code androidbrowserhelper} همهٔ کار را
 * از روی مانیفست انجام می‌دهد — آدرس اپ، رنگ نوارها، صفحهٔ اسپلش و بازکردن
 * تمام‌صفحه. اگر دامنه با Digital Asset Links تأیید شود، نوار آدرس هم پنهان
 * می‌شود و کاربر فرق اپ و سایت را نمی‌فهمد.
 *
 * <p>نام کامل کلاس پدر عمداً نوشته شده است؛ اگر آن را import کنیم، نام
 * `LauncherActivity` به همین کلاس خودمان اشاره می‌کند و کامپایل نمی‌شود.
 */
public class LauncherActivity extends com.google.androidbrowserhelper.trusted.LauncherActivity {
}
