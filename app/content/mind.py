"""دیتاست بازی «ذهن‌خوان»: سؤال‌ها، ویژگی‌ها و شخصیت‌ها.

بازی یک درخت تصمیم دستی نیست؛ یک **دیتاستِ ویژگی** است:

* هر **سؤال** یک ویژگی (trait) است که فقط بله/نه/نمی‌دانم دارد.
* هر **شخصیت** فهرست ویژگی‌هایی را دارد که در او هست؛ ویژگی‌های یک «گروه» خودکار
  منفی می‌شوند (اگر کسی «واقعی» باشد، «داستانی» نیست). هر چیزی که نوشته نشود
  یعنی «نمی‌دانیم» و در امتیازدهی بی‌طرف است.

با همین ساختار، موتور (`app.mind`) می‌تواند بین هر شماری شخصیت، دقیق‌ترین سؤال
بعدی را خودش انتخاب کند و دیتاست با افزودن یک خط بزرگ می‌شود.

نکتهٔ مهم برای نگهداری: هر نامِ ویژگی که این‌جا در سؤال‌ها هست باید در `TRAITS`
هم باشد و بلعکس؛ ابزار `tools/mind_dataset.py` همین را چک می‌کند.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

# --------------------------------------------------------------------------- #
# گروه‌ها: ویژگی‌هایی که با هم جمع نمی‌شوند
# --------------------------------------------------------------------------- #
# اگر شخصیتی یکی از اعضای گروه را داشته باشد، بقیهٔ اعضا خودکار «نه» می‌شوند.
# این کار حجم دیتاست را کم و دقت را زیاد می‌کند: لازم نیست برای هر شخصیت بنویسیم
# «مرد است و زن نیست».
GROUPS: Dict[str, Tuple[str, ...]] = {
    "kind": ("real", "fictional", "myth"),
    "sex": ("man", "woman", "nonhuman"),
    "origin": ("iranian", "foreign"),
    "life": ("alive", "dead"),
    "field": ("entertainer", "athlete", "ruler", "thinker", "entrepreneur"),
    # خانهٔ ابرقهرمانی، استودیوی کارتون، رشتهٔ علمی و گونهٔ شعر: هر کدام باعث می‌شود
    # چند شخصیت هم‌ویژگیِ کنار هم از هم جدا شوند (وگرنه موتور نمی‌تواند بینشان انتخاب کند).
    "hero_house": ("marvel", "dc"),
    "studio": ("disney", "anime", "warner", "nick"),
    "science_field": ("physics", "electric", "math", "medicine"),
    "poetry": ("epic", "lyric", "mystic"),
}

# --------------------------------------------------------------------------- #
# سؤال‌ها (هر ویژگی = یک سؤال)
# --------------------------------------------------------------------------- #
QUESTIONS: List[Dict[str, str]] = [
    # کلی‌ترین سؤال‌ها اول می‌آیند؛ ولی ترتیب نهایی را موتور انتخاب می‌کند.
    {"key": "real", "text": "آیا این آدم، آدمِ واقعی است؟", "hint": "نه شخصیتی از فیلم، کتاب یا افسانه."},
    {"key": "fictional", "text": "آیا شخصیتی داستانی است؟", "hint": "فیلم، سریال، کتاب یا کمیک."},
    {"key": "myth", "text": "آیا از اسطوره‌ها و افسانه‌های کهن است؟", "hint": "داستان‌های خیلی قدیمی."},
    {"key": "man", "text": "آیا مرد است؟", "hint": ""},
    {"key": "woman", "text": "آیا زن است؟", "hint": ""},
    {"key": "nonhuman", "text": "آیا انسان نیست؟", "hint": "حیوان، عروسک، ربات یا موجود خیالی."},
    {"key": "iranian", "text": "آیا ایرانی است؟", "hint": ""},
    {"key": "foreign", "text": "آیا غیرایرانی است؟", "hint": ""},
    {"key": "alive", "text": "آیا الان زنده است؟", "hint": ""},
    {"key": "dead", "text": "آیا فوت کرده است؟", "hint": ""},
    {"key": "entertainer", "text": "آیا در دنیای هنر و سرگرمی است؟", "hint": "سینما، موسیقی یا تلویزیون."},
    {"key": "athlete", "text": "آیا ورزشکار است؟", "hint": ""},
    {"key": "ruler", "text": "آیا فرمانروا، پادشاه یا سیاستمدار است؟", "hint": ""},
    {"key": "thinker", "text": "آیا دانشمند، شاعر یا نویسنده است؟", "hint": ""},
    {"key": "entrepreneur", "text": "آیا کارآفرین یا تاجرِ معروف است؟", "hint": ""},
    {"key": "american", "text": "آیا اهل آمریکاست؟", "hint": ""},
    {"key": "european", "text": "آیا اروپایی است؟", "hint": ""},
    {"key": "arab", "text": "آیا عرب یا اهل خاورمیانه است؟", "hint": "غیر از ایران."},
    {"key": "ancient", "text": "آیا مربوط به زمان‌های خیلی قدیم است؟", "hint": "بیش از دویست سال پیش."},
    {"key": "kid", "text": "آیا کودک یا نوجوان است؟", "hint": ""},
    {"key": "warrior", "text": "آیا جنگاور، پهلوان یا قهرمانِ نبرد است؟", "hint": ""},
    {"key": "king", "text": "آیا شاه یا ملکه است؟", "hint": ""},
    {"key": "actor", "text": "آیا بازیگر است؟", "hint": ""},
    {"key": "singer", "text": "آیا خواننده است؟", "hint": ""},
    {"key": "director", "text": "آیا کارگردان است؟", "hint": ""},
    {"key": "comedian", "text": "آیا کمدین است؟", "hint": "کارش خنداندن آدم‌هاست."},
    {"key": "musician", "text": "آیا نوازنده یا آهنگ‌ساز است؟", "hint": ""},
    {"key": "pop", "text": "آیا موسیقی پاپ کار می‌کند؟", "hint": ""},
    {"key": "classic", "text": "آیا موسیقی سنتی یا کلاسیک کار می‌کند؟", "hint": ""},
    {"key": "rapper", "text": "آیا رپ می‌خواند؟", "hint": ""},
    {"key": "poet", "text": "آیا شاعر است؟", "hint": ""},
    {"key": "writer", "text": "آیا نویسنده است؟", "hint": ""},
    {"key": "scientist", "text": "آیا دانشمند یا مخترع است؟", "hint": ""},
    {"key": "footballer", "text": "آیا فوتبالیست است؟", "hint": ""},
    {"key": "forward", "text": "آیا مهاجم است؟", "hint": "کارش گل‌زدن است."},
    {"key": "midfielder", "text": "آیا هافبک است؟", "hint": "وسط زمین بازی می‌کند."},
    {"key": "goalkeeper", "text": "آیا دروازه‌بان است؟", "hint": ""},
    {"key": "coach", "text": "آیا مربیگری هم کرده است؟", "hint": ""},
    {"key": "combat", "text": "آیا کشتی، وزنه‌برداری یا ورزش رزمی کار می‌کند؟", "hint": ""},
    {"key": "olympic", "text": "آیا قهرمانی جهانی یا مدال المپیک دارد؟", "hint": ""},
    {"key": "basketball", "text": "آیا بسکتبالیست است؟", "hint": ""},
    {"key": "boxing", "text": "آیا بوکسور است؟", "hint": ""},
    {"key": "tennis", "text": "آیا تنیس‌باز است؟", "hint": ""},
    {"key": "superhero", "text": "آیا ابرقهرمان است؟", "hint": "قدرت خارق‌العاده دارد."},
    {"key": "villain", "text": "آیا شخصیت منفی یا شرور است؟", "hint": ""},
    {"key": "cartoon", "text": "آیا شخصیت کارتونی یا کودکانه است؟", "hint": "انیمیشن، عروسکی یا کمیک."},
    {"key": "detective", "text": "آیا کارآگاه یا مأمور مخفی است؟", "hint": ""},
    {"key": "wizard", "text": "آیا جادوگر است؟", "hint": ""},
    {"key": "marvel", "text": "آیا از دنیای ابرقهرمانی مارول است؟", "hint": ""},
    {"key": "dc", "text": "آیا از دنیای ابرقهرمانی دی‌سی است؟", "hint": "بتمن و سوپرمن."},
    {"key": "disney", "text": "آیا از کارتون‌های دیزنی است؟", "hint": ""},
    {"key": "anime", "text": "آیا از انیمه‌های ژاپنی است؟", "hint": ""},
    {"key": "warner", "text": "آیا از کارتون‌های لوونی تونز است؟", "hint": "مثل باگز بانی."},
    {"key": "nick", "text": "آیا از کارتون‌های نیکلودیون است؟", "hint": "مثل اسپانج‌باب."},
    {"key": "cat", "text": "آیا گربه است؟", "hint": ""},
    {"key": "mouse", "text": "آیا موش است؟", "hint": ""},
    {"key": "oscar", "text": "آیا جایزهٔ اسکار گرفته است؟", "hint": ""},
    {"key": "physics", "text": "آیا کارش فیزیک بوده است؟", "hint": ""},
    {"key": "electric", "text": "آیا با برق و الکتریسیته کار کرده است؟", "hint": ""},
    {"key": "math", "text": "آیا ریاضی‌دان بوده است؟", "hint": ""},
    {"key": "medicine", "text": "آیا پزشک بوده است؟", "hint": ""},
    {"key": "epic", "text": "آیا اثرش حماسی است؟", "hint": "مثل شاهنامه."},
    {"key": "lyric", "text": "آیا غزل یا شعر عاشقانه گفته است؟", "hint": ""},
    {"key": "mystic", "text": "آیا شعرش عرفانی است؟", "hint": "مثل مثنوی."},
]

TRAITS: List[str] = [question["key"] for question in QUESTIONS]

TRAIT_LABELS: Dict[str, str] = {question["key"]: question["text"] for question in QUESTIONS}

# --------------------------------------------------------------------------- #
# شخصیت‌ها: (نام، ویژگی‌ها، توضیح یک‌خطی)
# --------------------------------------------------------------------------- #
# «ویژگی‌ها» با فاصله جدا می‌شوند؛ فقط چیزهایی را بنویس که در این شخصیت **هست**.
ENTITIES: Tuple[Tuple[str, str, str], ...] = (
    # ---- سینما و تلویزیون ایران ----
    ("رضا عطاران", "real man iranian alive entertainer actor comedian director", "بازیگر و کارگردان کمدی؛ چهرهٔ محبوب سینمای طنز"),
    ("مهران مدیری", "real man iranian alive entertainer actor comedian director", "سلطان طنز تلویزیون؛ سازندهٔ «قهوهٔ تلخ»"),
    ("نوید محمدزاده", "real man iranian alive entertainer actor", "بازیگر نقش‌های سنگین؛ اهل ایلام"),
    ("ترانه علیدوستی", "real woman iranian alive entertainer actor", "بازیگر «فروشنده» و «چهارشنبه‌سوری»"),
    ("پرویز پرستویی", "real man iranian alive entertainer actor", "بازیگر «آژانس شیشه‌ای» و «مارمولک»"),
    ("حامد بهداد", "real man iranian alive entertainer actor", "بازیگر با صدای خاص؛ «هزارپا»"),
    ("بهرام رادان", "real man iranian alive entertainer actor", "بازیگر و خوانندهٔ جوان‌پسند سینمای ایران"),
    ("لیلا حاتمی", "real woman iranian alive entertainer actor", "بازیگر «جدایی نادر از سیمین»"),
    ("محمدرضا گلزار", "real man iranian alive entertainer actor singer pop", "بازیگر و خوانندهٔ پاپ"),
    ("سعید آقاخانی", "real man iranian alive entertainer actor director comedian", "بازیگر و کارگردان طنز؛ «نون.خ»"),
    ("علی نصیریان", "real man iranian alive entertainer actor", "پدر بازیگری ایران؛ «هملت» و «گاو»"),
    ("هومن سیدی", "real man iranian alive entertainer actor director", "بازیگر و کارگردان «مغزهای کوچک زنگ‌زده»"),
    # ---- موسیقی ایران ----
    ("محسن یگانه", "real man iranian alive entertainer singer pop musician", "خوانندهٔ پاپ با ترانه‌های عاشقانه"),
    ("محسن چاوشی", "real man iranian alive entertainer singer pop musician", "خوانندهٔ پاپ با صدای متمایز"),
    ("شادمهر عقیلی", "real man iranian alive entertainer singer pop musician", "خواننده و آهنگساز پاپ"),
    ("رضا صادقی", "real man iranian alive entertainer singer pop", "خوانندهٔ پاپ بندری‌خوان"),
    ("سیروان خسروی", "real man iranian alive entertainer singer pop musician", "خواننده و آهنگساز پاپ"),
    ("همایون شجریان", "real man iranian alive entertainer singer classic musician", "خوانندهٔ موسیقی ایرانی و آهنگساز"),
    ("محمدرضا شجریان", "real man iranian dead entertainer singer classic musician", "خسرو آواز ایران؛ «ربنا»"),
    ("علیرضا قربانی", "real man iranian alive entertainer singer classic", "خوانندهٔ موسیقی سنتی"),
    ("یاس", "real man iranian alive entertainer singer rapper pop", "خوانندهٔ رپ فارسی"),
    ("هیچ‌کس", "real man iranian alive entertainer singer rapper pop", "رپر قدیمی و تأثیرگذار فارسی"),
    # ---- موسیقی جهان ----
    ("تیلور سوئیفت", "real woman foreign american alive entertainer singer pop", "خوانندهٔ پاپ آمریکایی با تورهای پرفروش"),
    ("مایکل جکسون", "real man foreign american dead entertainer singer pop", "سلطان پاپ؛ رقص «مون‌واک»"),
    ("فردی مرکوری", "real man foreign european dead entertainer singer pop", "خوانندهٔ گروه کویین"),
    ("بیونس", "real woman foreign american alive entertainer singer pop", "خواننده و بازیگر آمریکایی"),
    ("آدل", "real woman foreign european alive entertainer singer pop", "خوانندهٔ انگلیسی با صدای قدرتمند"),
    ("امینم", "real man foreign american alive entertainer singer rapper pop", "رپر مشهور آمریکایی"),
    # ---- ورزش ایران ----
    ("علی دایی", "real man iranian alive athlete footballer forward coach", "آقای گل پیشین جهان و سرمربی سابق تیم ملی"),
    ("مهدی مهدوی‌کیا", "real man iranian alive athlete footballer midfielder", "بازیکن اسبق هامبورگ و تیم ملی"),
    ("علی پروین", "real man iranian alive athlete footballer midfielder coach", "کاپیتان و مربی افسانه‌ای پرسپولیس"),
    ("علی کریمی", "real man iranian alive athlete footballer midfielder", "هافبک خلاق سابق تیم ملی"),
    ("سردار آزمون", "real man iranian alive athlete footballer forward", "مهاجم تیم ملی ایران"),
    ("مهدی طارمی", "real man iranian alive athlete footballer forward", "مهاجم تیم ملی و باشگاه‌های اروپایی"),
    ("علیرضا بیرانوند", "real man iranian alive athlete footballer goalkeeper", "دروازه‌بان تیم ملی"),
    ("حسن یزدانی", "real man iranian alive athlete combat olympic", "کشتی‌گیر آزاد و مدال‌آور المپیک"),
    ("حسین رضازاده", "real man iranian alive athlete combat olympic", "قوی‌ترین مرد جهان در وزنه‌برداری"),
    ("بهداد سلیمی", "real man iranian alive athlete combat olympic", "وزنه‌بردار قهرمان المپیک"),
    ("کیمیا علیزاده", "real woman iranian alive athlete combat olympic", "تکواندوکار مدال‌آور المپیک"),
    ("سعید ملایی", "real man iranian alive athlete combat olympic", "جودوکار قهرمان جهان"),
    ("احسان حدادی", "real man iranian alive athlete olympic", "رکورددار پرتاب دیسک آسیا"),
    # ---- ورزش جهان ----
    ("کریستیانو رونالدو", "real man foreign european alive athlete footballer forward", "ستارهٔ پرتغالی و یکی از بهترین‌های تاریخ"),
    ("لیونل مسی", "real man foreign alive athlete footballer forward", "برندهٔ جام جهانی ۲۰۲۲ با آرژانتین"),
    ("نیمار", "real man foreign alive athlete footballer forward", "مهاجم برزیلی"),
    ("پله", "real man foreign dead athlete footballer forward", "اسطورهٔ فوتبال برزیل؛ سه‌بار قهرمان جهان"),
    ("دیه‌گو مارادونا", "real man foreign dead athlete footballer forward", "اسطورهٔ آرژانتینی و «گل قرن»"),
    ("محمد صلاح", "real man foreign arab alive athlete footballer forward", "ستارهٔ مصری لیورپول"),
    ("مایکل جردن", "real man foreign american alive athlete basketball olympic", "اسطورهٔ بسکتبال و شش‌بار قهرمان NBA"),
    ("لبرون جیمز", "real man foreign american alive athlete basketball olympic", "بسکتبالیست آمریکایی و رکورددار امتیاز"),
    ("محمدعلی کلی", "real man foreign american dead athlete boxing olympic", "بوکسور افسانه‌ای؛ «پروانه‌ای مثل پروانه»"),
    ("مایک تایسون", "real man foreign american alive athlete boxing", "بوکسور سنگین‌وزن معروف"),
    ("راجر فدرر", "real man foreign european alive athlete tennis olympic", "تنیس‌باز سوئیسی با سبک تماشایی"),
    ("رافائل نادال", "real man foreign european alive athlete tennis olympic", "تنیس‌باز اسپانیایی؛ سلطان خاک"),
    # ---- سینمای جهان ----
    ("تام کروز", "real man foreign american alive entertainer actor", "ستارهٔ «مأموریت غیرممکن»"),
    ("لئوناردو دی‌کاپریو", "real man foreign american alive entertainer actor oscar", "بازیگر «تایتانیک» و «بی‌میهن»"),
    ("کیانو ریوز", "real man foreign alive entertainer actor", "بازیگر «ماتریکس» و «جان ویک»"),
    ("رابرت داونی جونیور", "real man foreign american alive entertainer actor marvel", "آیرون‌من دنیای مارول"),
    ("دوئین جانسون", "real man foreign american alive entertainer actor combat", "کشتی‌گیر سابق که ستارهٔ سینما شد"),
    ("جکی چان", "real man foreign alive entertainer actor combat", "بازیگر هنرهای رزمی و کمدی اکشن"),
    ("مریل استریپ", "real woman foreign american alive entertainer actor oscar", "بازیگر پرافتخار؛ رکورددار نامزدی اسکار"),
    ("انجلینا جولی", "real woman foreign american alive entertainer actor oscar", "بازیگر و بشردوست آمریکایی"),
    ("برد پیت", "real man foreign american alive entertainer actor oscar", "بازیگر «باشگاه مشت‌زنی»"),
    ("استیون اسپیلبرگ", "real man foreign american alive entertainer director oscar", "کارگردان «ای.تی» و «فهرست شیندلر»"),
    ("جیم کری", "real man foreign american alive entertainer actor comedian", "کمدین صورت‌پلاستیکی سینما"),
    ("چارلی چاپلین", "real man foreign european dead entertainer actor director comedian oscar", "کمدین بی‌صدای تاریخ سینما"),
    # ---- دانش، کسب‌وکار و سیاست جهان ----
    ("آلبرت اینشتین", "real man foreign european dead thinker scientist physics", "نظریهٔ نسبیت"),
    ("ایزاک نیوتن", "real man foreign european dead thinker scientist physics ancient", "قانون جاذبه"),
    ("نیکولا تسلا", "real man foreign european dead thinker scientist electric ancient", "مخترع جریان متناوب"),
    ("استیو جابز", "real man foreign american dead entrepreneur", "بنیان‌گذار اپل و آیفون"),
    ("بیل گیتس", "real man foreign american alive entrepreneur", "بنیان‌گذار مایکروسافت"),
    ("ایلان ماسک", "real man foreign alive entrepreneur scientist", "تسلا و اسپیس‌ایکس"),
    ("مارک زاکربرگ", "real man foreign american alive entrepreneur", "بنیان‌گذار فیسبوک"),
    ("نلسون ماندلا", "real man foreign dead ruler", "رهبر ضدآپارتاید و رئیس‌جمهور آفریقای جنوبی"),
    ("باراک اوباما", "real man foreign american alive ruler", "رئیس‌جمهور پیشین آمریکا"),
    ("دونالد ترامپ", "real man foreign american alive ruler entrepreneur", "رئیس‌جمهور آمریکا و تاجر"),
    ("وینستون چرچیل", "real man foreign european dead ruler", "نخست‌وزیر بریتانیا در جنگ جهانی دوم"),
    ("ماهاتما گاندی", "real man foreign dead ruler", "رهبر استقلال هند با روش نافرمانی مدنی"),
    ("ملکه الیزابت دوم", "real woman foreign european dead ruler king", "ملکهٔ بریتانیا برای هفتاد سال"),
    # ---- تاریخ و فرهنگ ایران ----
    ("کوروش بزرگ", "real man iranian dead ruler king ancient", "بنیان‌گذار شاهنشاهی هخامنشی و منشور حقوق بشر"),
    ("داریوش بزرگ", "real man iranian dead ruler king ancient", "شاه هخامنشی؛ سازندهٔ تخت جمشید"),
    ("فردوسی", "real man iranian dead thinker poet epic ancient", "سرایندهٔ شاهنامه"),
    ("حافظ", "real man iranian dead thinker poet lyric ancient", "غزل‌سرای شیراز و فال حافظ"),
    ("سعدی", "real man iranian dead thinker poet writer lyric ancient", "نویسندهٔ گلستان و بوستان"),
    ("مولانا", "real man iranian dead thinker poet writer mystic ancient", "شاعر مثنوی معنوی"),
    ("عمر خیام", "real man iranian dead thinker poet scientist lyric math ancient", "شاعر رباعیات و ریاضی‌دان"),
    ("ابوعلی سینا", "real man iranian dead thinker scientist medicine ancient", "پزشک و فیلسوف؛ قانون در طب"),
    ("خوارزمی", "real man iranian dead thinker scientist math ancient", "پدر جبر و ریشهٔ واژهٔ الگوریتم"),
    ("امیرکبیر", "real man iranian dead ruler", "صدراعظم اصلاح‌گر و بنیان‌گذار دارالفنون"),
    ("نادر شاه", "real man iranian dead ruler king warrior ancient", "بنیان‌گذار دودمان افشاریه"),
    ("بابک خرمدین", "real man iranian dead warrior ancient", "رهبر خرمدینان در برابر خلافت عباسی"),
    ("ستارخان", "real man iranian dead warrior", "سردار ملی در انقلاب مشروطه"),
    # ---- اسطوره‌های ایران ----
    ("رستم", "myth man iranian warrior", "پهلوان بزرگ شاهنامه"),
    ("آرش کمانگیر", "myth man iranian warrior", "کمانگیر افسانه‌ای که مرز ایران را پراند"),
    ("سیاوش", "myth man iranian warrior", "شاهزادهٔ بی‌گناه شاهنامه"),
    ("فریدون", "myth man iranian warrior king", "شاه افسانه‌ای که ضحاک را شکست داد"),
    ("سیمرغ", "myth nonhuman", "پرندهٔ افسانه‌ای و دانا"),
    ("دیو سپید", "myth nonhuman warrior villain", "دیو مازندران در نبرد با رستم"),
    # ---- شخصیت‌های داستانی جهان ----
    ("سوپرمن", "fictional man foreign american superhero dc", "ابرقهرمان کریپتونی و پوشیده در شنل"),
    ("بتمن", "fictional man foreign american superhero dc", "شوالیهٔ تاریک گاتهام"),
    ("اسپایدرمن", "fictional man foreign american superhero marvel", "نوجوانی که با نیش عنکبوت قدرت گرفت"),
    ("آیرون‌من", "fictional man foreign american superhero marvel", "ابرقهرمان زره‌پوش و ثروتمند"),
    ("هالک", "fictional man foreign american superhero scientist marvel", "دانشمندی که با خشم غول می‌شود"),
    ("ثور", "fictional man foreign european superhero marvel", "خدای رعد در دنیای مارول"),
    ("جوکر", "fictional man foreign american villain dc", "دشمن اصلی بتمن"),
    ("دارث ویدر", "fictional man foreign villain", "شخصیت منفی جنگ ستارگان"),
    ("هری پاتر", "fictional man foreign european kid wizard", "پسر جادوگر با نشان صاعقه"),
    ("هرماینی گرنجر", "fictional woman foreign european kid wizard", "همکلاسی باهوش هری پاتر"),
    ("گندالف", "fictional man foreign ancient wizard", "جادوگر دانای ارباب حلقه‌ها"),
    ("شرلوک هلمز", "fictional man foreign european detective", "کارآگاه لندنی با گوش‌بینی خاص"),
    ("هرکول پوآرو", "fictional man foreign european detective", "کارآگاه بلژیکی با سبیل مشهور"),
    ("جیمز باند", "fictional man foreign european detective", "مأمور ۰۰۷"),
    ("دراکولا", "fictional man foreign european villain nonhuman", "خون‌آشام ترانسیلوانیا"),
    ("جک اسپارو", "fictional man foreign", "کاپیتان دزدان دریایی کاراییب"),
    # ---- کارتون، کودکانه و عروسکی ----
    ("میکی موس", "fictional nonhuman cartoon disney mouse", "موش مشهور دیزنی"),
    ("تام", "fictional nonhuman cartoon cat", "گربهٔ همیشه‌درتعقیب تام و جری"),
    ("جری", "fictional nonhuman cartoon mouse", "موش زرنگ و بامزه"),
    ("باگز بانی", "fictional nonhuman cartoon warner", "خرگوش بامزهٔ کارتون‌های لونی تونز"),
    ("اسپانج‌باب", "fictional nonhuman cartoon nick", "اسفنج زردِ زیر دریا"),
    ("پیکاچو", "fictional nonhuman cartoon anime", "پوکمون زردرنگ و برقی"),
    ("شرک", "fictional nonhuman cartoon", "اوگر دوست‌داشتنی باتلاق"),
    ("السا", "fictional woman cartoon disney", "ملکهٔ یخی دیزنی"),
    ("سیمبا", "fictional nonhuman cartoon kid disney", "شیر کوچکِ «شیرشاه»"),
    ("هومر سیمپسون", "fictional man cartoon", "پدر کارتون زردرنگ اسپرینگ‌فیلد"),
    ("ناروتو", "fictional man cartoon anime", "نینجای نوجوان دهکدهٔ برگ"),
    ("کلاه‌قرمزی", "fictional iranian nonhuman cartoon kid", "عروسک محبوب تلویزیون ایران"),
)


TRAIT_SET = set(TRAITS)


def entity_map() -> Dict[str, Dict[str, object]]:
    """شخصیت‌ها را با ویژگی‌های حل‌شده (گروه‌ها به «نه» تبدیل شده) برمی‌گرداند."""
    result: Dict[str, Dict[str, object]] = {}
    for name, raw, about in ENTITIES:
        values = {trait: 1 for trait in str(raw).split() if trait in TRAIT_SET}
        for members in GROUPS.values():
            present = [member for member in members if member in values]
            if len(present) != 1:
                continue
            for member in members:
                if member != present[0]:
                    values[member] = -1
        result[name] = {"name": name, "about": about, "values": values}
    return result

# نگاشت ویژگی به آیکون نتیجه؛ اولین موردی که بخورد برنده است.
ICON_RULES: Tuple[Tuple[str, str], ...] = (
    ("villain", "fa-solid fa-mask"),
    ("superhero", "fa-solid fa-bolt"),
    ("wizard", "fa-solid fa-hat-wizard"),
    ("cartoon", "fa-solid fa-palette"),
    ("detective", "fa-solid fa-magnifying-glass"),
    ("warrior", "fa-solid fa-shield-halved"),
    ("athlete", "fa-solid fa-medal"),
    ("tennis", "fa-solid fa-table-tennis-paddle-ball"),
    ("basketball", "fa-solid fa-basketball"),
    ("boxing", "fa-solid fa-hand-fist"),
    ("footballer", "fa-solid fa-futbol"),
    ("singer", "fa-solid fa-microphone-lines"),
    ("musician", "fa-solid fa-guitar"),
    ("actor", "fa-solid fa-masks-theater"),
    ("director", "fa-solid fa-clapperboard"),
    ("comedian", "fa-solid fa-face-laugh-squint"),
    ("poet", "fa-solid fa-feather-pointed"),
    ("writer", "fa-solid fa-book"),
    ("scientist", "fa-solid fa-flask"),
    ("entrepreneur", "fa-solid fa-briefcase"),
    ("ruler", "fa-solid fa-crown"),
    ("king", "fa-solid fa-crown"),
    ("myth", "fa-solid fa-dragon"),
    ("nonhuman", "fa-solid fa-paw"),
)
DEFAULT_ICON = "fa-solid fa-user-astronaut"


def icon_for(values: Dict[str, int]) -> str:
    """آیکون مناسب یک شخصیت، از روی ویژگی‌هایش."""
    for trait, icon in ICON_RULES:
        if int(values.get(trait) or 0) == 1:
            return icon
    return DEFAULT_ICON
