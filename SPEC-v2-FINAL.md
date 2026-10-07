# 📋 System Specification — SMC Scalper (SH + BMS + RTO) — v2.0 FINAL

> **نام استراتژی:** SMC Scalper — Stop Hunt → Break of Market Structure → Return to Origin
> **نسخه سند:** `2.0` (فایل مرجع نهایی — جایگزین هر سه فایل قبلی)
> **نوع سند:** مشخصات فنی قابل ارائه به مدل زبانی یا برنامه‌نویس برای پیاده‌سازی / بک‌تست
> **تاریخ ایجاد:** 2026-10-06
> **منابع ادغام‌شده:** `SMC-Scalper-Spec-SH-BMS-RTO-mus.md` (مادر) + `qean.md` (مکمل) — فایل `SH-BMS-RTO-SKILL.md` **کنار گذاشته شد** (ستاپ متفاوت: 1H/4H، بدون فیبو، بدون تریگر)

**فهرست بخش‌ها:**

| بخش | عنوان | بخش | عنوان |
|---|---|---|---|
| ۰ | مشخصات کلی | ۸ | پسودوکد اجرایی |
| ۱ | تعاریف و پارامترهای ورودی | ۹ | پروتکل بک‌تست LLM |
| ۲ | منطق الگوریتم (۴ شرط) | ۱۰ | مثال‌های عددی BUY و SELL |
| ۳ | زمان، انقضا، باطل‌شدن | ۱۱ | Edge Cases |
| ۴ | خروج و مدیریت ریسک (RR=2) | ۱۲ | جدول پارامترها |
| ۵ | ورودی/خروجی استاندارد (JSON) | ۱۳ | اصطلاح‌نامه |
| ۶ | فیلترهای ایمنی | ۱۴ | پرامپت آماده |
| ۷ | مدل امتیازدهی Confidence | ۱۵ | جدول تصمیم نهایی + چک‌لیست |

---

## 🎯 TL;DR — خلاصه یک خطی

یک ستاپ معکوس‌شدن نقدینگی (Liquidity Reversal) در تایم‌فریم **M5** (گزینه M15): ابتدا استاپ‌های زیر Swing Low شکار می‌شود (SH)، سپس ساختار با قدرت شکسته می‌شود (BMS)، قیمت به ناحیه شروع حرکت برمی‌گردد (RTO = **هم‌زمان** OB/FVG **و** فیبوی ۵۰٪–۶۱.۸٪) و با یک کندل تأییدیه داخل ناحیه، ورود گرفته می‌شود با **RR ثابت ۲.۰**.

---

## ⚙️ بخش ۰: مشخصات کلی سیستم

| پارامتر | مقدار |
|---|---|
| بازار هدف | فارکس — جفت‌ارزهای اصلی با اسپرد پایین (`EURUSD`, `GBPUSD`, `USDJPY`, `AUDUSD`) + `XAUUSD` |
| تایم‌فریم اجرا | **`M5`** (پیش‌فرض) یا `M15` — حالت ترکیبی: ساختار روی M15، تریگر روی M5 |
| تایم‌فریم جهت‌ده (HTF Bias) | **`H1` (اجباری)** + `H4`/`D1` (اختیاری) |
| Risk:Reward | ثابت `2.0` |
| سشن معاملاتی | لندن + اوورلپ لندن/نیویورک (جدول بخش ۶.۲) |
| خروجی | JSON — بخش ۵ |
| حداکثر ریسک هر ترید | `25` پیپ (فیلتر F2) |
| حداقل ریسک هر ترید | `5` پیپ (فیلتر F5) |
| حداقل Win-Rate سر‌به‌سری | `1 / (1 + 2.0) = 33.33%` |
| ریسک هر معامله | `0.5%` سرمایه (محدوده 0.25–1%) |

> 💡 با RR=2.0، هر Win-Rate بالای **۳۳.۳٪** سودده است. هدف واقع‌بینانه برای این ستاپ: **۴۰–۵۵٪** با Profit Factor > ۱.۵.

---

## 📥 بخش ۱: تعاریف و پارامترهای ورودی (Input Definitions)

مدل/ربات باید این متغیرها را از دیتای OHLCV (کندل **بسته‌شده**) استخراج کند.

### ۱.۱ Swing Points (نقاط چرخشی)

```text
Swing High (i) ⟺  high[i] > high[i-1] AND high[i] > high[i-2]
                      AND high[i] > high[i+1] AND high[i] > high[i+2]

Swing Low  (i) ⟺  low[i]  < low[i-1]  AND low[i]  < low[i-2]
                      AND low[i]  < low[i+1]  AND low[i]  < low[i+2]
```

| متغیر | توضیح |
|---|---|
| `lookback` | تعداد کندل‌های چپ/راست = `2` (قابل تنظیم `2..3`) |
| `swing_high` / `swing_low` | قیمت سطح |
| `swing_index` | ایندکس کندل سویینگ |
| `last_swing_low` | آخرین Swing Low **تأییدشده** معتبر |
| `last_swing_high` | آخرین Swing High **تأییدشده** معتبر |

> ⚠️ **نکته بسیار مهم (لگ تشخیص):** یک سویینگ فقط **۲ کندل بعد** قابل تشخیص است.
> یعنی در لحظه بسته‌شدن کندل `i`، هنوز نمی‌دانیم سویینگ است یا نه.
> در بک‌تست **ممنوع است** از کندل‌های آینده (`i+1`, `i+2`) قبل از بسته‌شدن‌شان استفاده کنید (look-ahead bias).
>
> **راه‌حل عملی برای لایو:** از قانون `Confirmed Only` پیروی کنید یا از نسخه «لغزنده» (`repainting swing`) استفاده کنید و نتایج هر دو را **جداگانه** گزارش کنید.

### ۱.۲ Order Block (OB) — ناحیه RTO

| جهت | تعریف |
|---|---|
| **Bullish OB** (برای BUY) | آخرین کندل نزولی (قرمز) **قبل از شروع موج صعودی‌ای** که منجر به BMS شده است. |
| **Bearish OB** (برای SELL) | آخرین کندل صعودی (سبز) **قبل از شروع موج نزولی‌ای** که منجر به BMS شده است. |

**نحوه محاسبه ناحیه OB (پیش‌فرض v2.2 = کل کندل):**

```text
ob_low  = low
ob_high = high
```

> پارامتر `ob_zone_mode`: `full_candle` (پیش‌فرض از v2.2 — عرض واقعی ناحیه‌ی ICT،
> حدود ۳–۸ پیپ در M5) یا `body` (`[min(open,close), max(open,close)]` — تنگ‌تر و سخت‌گیرانه‌تر).

**قیدهای اعتبار OB (حذف ناحیه بی‌کیفیت):**

```text
valid_ob ⟺  ob_age_candles <= max_ob_age (default: 50)
        AND ob_mitigations <= 1            (بیش از ۱ بار تست شده → ناحیه ضعیف)
        AND ob_distance_to_price <= max_ob_distance_pips (default: 60)
        AND ob_size <= max_ob_size_pips    (default: 15 — OB خیلی بزرگ = ناحیه مبهم)
```

**اولویت انتخاب ناحیه (ترتیب اجباری):**

```text
1) اگر Bullish/Bearish OB معتبر وجود داشت → OB
2) اگر OB نبود ولی FVG باز وجود داشت → FVG
3) اگر هیچ‌کدام نبود → ستاپ رد می‌شود  (حالت strict)
   (در حالت RELAXED: ناحیه فیبوی 50%–61.8% به تنهایی قابل قبول است — بخش ۲ شرط ۳)
```

### ۱.۳ FVG (Fair Value Gap)

```text
Bullish FVG (سه کندل متوالی i, i+1, i+2):
    fvg_low  = high[i]
    fvg_high = low[i+2]
    شرط:  low[i+2] > high[i]

Bearish FVG:
    fvg_low  = high[i+2]
    fvg_high = low[i]
    شرط:  high[i+2] < low[i]
```

| متغیر | توضیح | حد پیشنهادی |
|---|---|---|
| `min_fvg_size_pips` | حداقل اندازه گپ | `2` پیپ (کوچک‌تر = نویز) |
| `max_fvg_size_pips` | حداکثر اندازه گپ | `25` پیپ |
| `fvg_state` | `open` / `partially_mitigated` / `filled` | فقط `open` قابل استفاده |

### ۱.۴ Leg / ناحیه شروع حرکت (Origin)

```text
LONG setup:
    leg_low  = sweep_low                                    # ثابت بعد از SH
    leg_high = بالاترین high از کندل SH تا کندلی که اولین بار
               قیمت وارد ناحیه RTO می‌شود                    # running max — بدون نگاه به آینده

SHORT setup:
    leg_high = sweep_high                                   # ثابت بعد از SH
    leg_low  = پایین‌ترین low از کندل SH تا کندلی که اولین بار
               قیمت وارد ناحیه RTO می‌شود                    # running min
```

> 📌 `leg_high`/`leg_low` در لحظه **اولین لمس ناحیه** نهایی (freeze) می‌شوند و تا پایان ستاپ تغییر نمی‌کنند.
> این تعریف هم بدون Look-Ahead است و هم نوسانات بعد از BMS را پوشش می‌دهد.

**محاسبه ریتریسمنت:**

```text
# برای LONG   (0 = سقف موج ، 1 = کف موج)
retracement = (leg_high - price) / (leg_high - leg_low)

# برای SHORT
retracement = (price - leg_low)  / (leg_high - leg_low)

# ناحیه فیبوی RTO
RTO_fib_zone = [0.500, 0.618]   # حالت STRICT  (پیش‌فرض)
RTO_fib_zone = [0.500, 0.790]   # حالت RELAXED / OTE (اختیاری)
```

### ۱.۵ سایر ورودی‌های محاسباتی

| ورودی | فرمول/مقدار |
|---|---|
| `pip_size` | چهاررقمی (EURUSD): `0.0001` — JPY: `0.01` — XAUUSD: `0.1` |
| `digits` | تعداد ارقام قیمت بروکر (مثلاً `5` برای 1.05500) |
| `ATR(14)` | ATR تایم‌فریم اجرایی — برای فیلتر دیسپلیسمنت و بافر SL |
| `spread` | اسپرد لحظه‌ای به پیپ |
| `session` | سشن فعلی بر اساس UTC + قواعد DST |
| `h1_bias` | `BULLISH` / `BEARISH` / `NEUTRAL` از ساختار H1 |
| `balance`, `risk_percent` | برای محاسبه حجم معامله (بخش ۴) |

---

## 🧠 بخش ۲: منطق الگوریتم (Algorithmic Logic)

الگوریتم یک **State Machine** است که در **هر بار بسته‌شدن کندل جدید** اجرا می‌شود.
ترتیب شرط‌ها اجباری است و هیچ مرحله‌ای نباید رد شود.

```text
IDLE → SH_CONFIRMED → BMS_CONFIRMED → IN_ZONE_WAIT → TRIGGERED
                     ↘ EXPIRED / INVALIDATED (در هر مرحله)
```

### 🟢 شرایط ورود خرید (LONG / BUY)

#### شرط ۱ — شکار نقدینگی (SH - Stop Hunt)

```text
inputs: last_swing_low = L
1. پیدا کردن اولین کندل j بعد از شکل‌گیری L که  low[j] < L
2. شرط نفوذ:   (L - low[j]) >= min_sweep_pips            (پیش‌فرض 0.5 پیپ)
3. شرط ریجکت:  close[j] > L                               (کندل بالای L بسته شود)
4. کیفیت شکار: (L - low[j]) <= max_sweep_pips             (پیش‌فرض 10 پیپ)
5. سطح شکار:   sweep_low = min(low[j], L)
```

**توضیح منطقی:** استاپ‌ها زیر L فعال شدند، اما فروشندگان نتوانستند قیمت را پایین L نگه دارند → نقدینگی جمع شده و جهت در حال بازگشت است.

**قیدهای کیفیت SH:**

| پارامتر | پیش‌فرض | دلیل |
|---|---|---|
| `min_sweep_pips` | `0.5` | نفوذ واقعی لازم است؛ لمس دقیق = شکار نیست |
| `max_sweep_pips` | `10.0` | نفوذ عمیق = شکست واقعی، نه شکار نقدینگی |
| `require_close_above` | `true` | بدنه کندل باید بالای سطح بسته شود (فقط ویک کافی نیست) |
| `sweep_pool_type` | `asian_range_low` / `equal_lows` / `pdl` | امتیاز اضافه اگر سطح شکارشده استخر نقدینگی شناخته‌شده باشد |

> 🔎 **امتیاز کیفیت:** شکار زیر **کف رنج آسیا**، **Equal Lows (EQL)** یا **Previous Day Low** از شکار زیر یک سویینگ معمولی باکیفیت‌تر است.

#### شرط ۲ — شکست ساختار (BMS - Break of Market Structure)

```text
inputs: H = آخرین Swing High معتبری که قبل از ریزش اخیر تشکیل شده
        (یا در نبود سویینگ: بالاترین high در `structure_lookback` کندل قبل از SH)
1. وجود کندل k > j که  close[k] > H            (کلوز بالای H — نه فقط ویک)
2. دیسپلیسمنت (جابه‌جایی قوی):
       body[k] = |close[k] - open[k]|
       شرط:  body[k] >= displacement_factor * ATR14      (پیش‌فرض 1.0)
       یا:   body[k] / (high[k]-low[k]) >= 0.60          (نسبت بدنه به رنج)
3. اولین شکست H بعد از SH (شکست‌های قبلی حساب نمی‌شوند)
4. فاصله زمانی: k - j <= max_bms_delay_candles            (پیش‌فرض 15 کندل M5)
5. سطح شکست:   bms_level = H
```

> ⚠️ **تفاوت BMS و CHOCH:** اگر روند جاری نزولی باشد و قیمت بالا بشکند، برخی آن را CHOCH می‌نامند. در این سند هر دو = `BMS` صعودی. مدل باید هر دو را بپذیرد.

#### شرط ۳ — بازگشت به مبدا (RTO - Return to Origin)

```text
1. leg_low و leg_high را از موج بین SH تا BMS استخراج کن (بخش ۱.۴)
2. ناحیه OB/FVG را با اولویت بخش ۱.۲ پیدا کن (OB به حالت `full_candle`: `[low, high]`)
3. اعتبارسنجی (STRICT — پیش‌فرض):
       (OB ∪ FVG باز)  ∩  [ retracement ∈ (0.500, 0.618) ]  ≠  ∅
   یعنی ناحیه باید حداقل بخشی از خودش در پنجره‌ی ۵۰٪–۶۱.۸٪ (Discount) داشته باشد.
   اگر هم‌پوشانی نبود → ناحیه رد است و سراغ ناحیه‌ی بعدی (یا ردِ کامل) برو.
   این اعتبارسنجی فقط فیلتر کیفی است و عرض باکس ورود را تعیین نمی‌کند.
4. ناحیه‌ی ورود (entry_zone) = خودِ OB به حالت `full_candle` (یا خودِ FVG)، نه هم‌پوشانی:
       entry_zone = OB[low, high]     ← عرض باکس = عرض کل کندل OB
5. شرط لمس (v2.2): ویک کندل باید خودِ هم‌پوشانی دقیق را لمس کند:
       low[i] <= overlap_top  AND  high[i] >= overlap_bottom
   (لمس لبه‌ی دور OB بدون رسیدن قیمت به پنجره‌ی فیبو کافی نیست)
6. حد انتظار: حداکثر `max_wait_candles` بعد از BMS (پیش‌فرض 30)
7. انقضا: اگر قیمت بدون اصلاح مستقیم بالا رفت و ناحیه لمس نشد → EXPIRED
```

**تفسیر دقیق قید «۵۰٪ تا ۶۱.۸٪» (تصمیم نهایی — نسخه ۲.۲):**

| حالت | قاعده اعتبارسنجی | ناحیه‌ی ورود (entry_zone) | وضعیت |
|---|---|---|---|
| **STRICT** | `(OB ∪ FVG) ∩ فیبوی 50–61.8٪ ≠ ∅` — اگر هم‌پوشانی نبود → رد | **خودِ OB به حالت `full_candle`** (یا خودِ FVG) + **لمس ویک روی خودِ هم‌پوشانی** | **پیش‌فرض** ✅ |
| **RELAXED** | کافی است داخل فیبوی 50–79٪ (OTE) باشد؛ OB/FVG ترجیحی ولی اجباری نیست | خودِ ناحیه، وگرنه خودِ پنجره‌ی فیبو | اختیاری (`rto_mode = "relaxed"`) |

> ⛔ در حالت STRICT هیچ استثنایی قائل نشوید: **نبود هم‌پوشانی = رد سیگنال.**
> این مهم‌ترین فیلتر کیفیت این ستاپ است.
>
> ⚠️ **نکته‌ی پیاده‌سازی (خیلی مهم):** فیبو **فقط فیلتر کیفی** است (ناحیه باید در
> Discount باشد) و **عرضِ باکس ورود را تعیین نمی‌کند.** اگر `entry_zone` را
> همان هم‌پوشانی بگیرید، باکس ۰٫۵–۱ پیپی می‌شود و عملاً هیچ کندلی داخلش
> نمی‌بسته است: در تست ۳۰۰۰ کندلی، **۰ سیگنال از ۶۲ فرصتِ لمس ناحیه** ثبت شد.
> علت اینکه هم‌پوشانی رخ می‌دهد هم مشخص است: OB = «آخرین کندل مخالف قبل از
> حرکت BMS» است و بالاتر از کف موج (SH) قرار می‌گیرد، پس در پنجره‌ی فیبو می‌افتد.

#### شرط ۴ — تریگر ورود (Entry Trigger)

```text
1. قیمت وارد entry_zone شده باشد (شرط ۳ برقرار؛ entry_zone = خودِ OB/FVG به حالت full_candle)
2. کندل بسته‌شده صعودی باشد:  close > open   (کندل سبز)
3. کلوز کندل باید داخل entry_zone باشد:
       zone_bottom <= close <= zone_top
   (zone_bottom/zone_top = لبه‌های کل کندل OB — نه لبه‌های هم‌پوشانی با فیبو.
    کلوز کاملاً بالای ناحیه = رد. کلوز زیر ناحیه = رد.)
4. BUY صادر می‌شود →  Entry = close کندل تریگر
```

### 🔴 شرایط ورود فروش (SHORT / SELL)

دقیقاً عکس حالت بالا:

| مرحله | شرط |
|---|---|
| **۱ — SH** | `high[j] > H` (نفوذ `0.5..10` پیپ) اما `close[j] < H` → ریجکت. `sweep_high = max(high[j], H)` |
| **۲ — BMS** | کندل k با `close[k] < last_swing_low` + دیسپلیسمنت + در بازه `max_bms_delay` |
| **۳ — RTO** | اعتبار: `(Bearish OB ∪ Bearish FVG) ∩ [ retracement ∈ (0.500, 0.618) ] ≠ ∅`؛ **entry_zone = خودِ OB/FVG** |
| **۴ — Trigger** | یک کندل نزولی (قرمز) که **کلوزش داخل entry_zone** باشد → **SELL**. `Entry = close` |

---

## ⏱️ بخش ۳: مدیریت زمان، انقضا و باطل‌شدن

| رویداد | قاعده |
|---|---|
| `max_bms_delay_candles` | بعد از SH، حداکثر `15` کندل برای تأیید BMS |
| `max_wait_candles` | بعد از BMS، حداکثر `30` کندل برای رسیدن به ناحیه RTO |
| `max_total_setup_candles` | کل عمر ستاپ از SH تا Trigger ≤ `45` کندل (M5 ≈ ۳.۷ ساعت) |
| `invalidated` | **بسته‌شدن کندل** زیر `sweep_low` (در BUY) یا بالای `sweep_high` (در SELL) با بافر `1` پیپ → ستاپ باطل |
| `re-arm` | اگر SH اتفاق افتاد ولی BMS نیامد → State به `IDLE` برمی‌گردد و فقط با **یک SH جدید** دوباره فعال می‌شود |
| `news_lock` | در بازه خبری (فیلتر F1 بخش ۶.۱) State فریز است؛ Trigger صادر نمی‌شود |
| `one_position` | همزمان فقط یک ستاپ فعال برای یک نماد |
| `cancel_if_close_below` | BUY: `sweep_low - 1 pip` |
| `cancel_if_close_above` | SELL: `sweep_high + 1 pip` |

---

## 🎯 بخش ۴: محاسبات خروج و مدیریت ریسک (RR = 2)

### BUY

```text
Entry_Price = close کندل تریگر (داخل entry_zone)
SL          = sweep_low - buffer
buffer      = max(2 پیپ, 1.5 × spread, 0.3 × ATR14)      # پیش‌فرض 2 تا 3 پیپ
TP          = Entry_Price + (2 × (Entry_Price - SL))
```

### SELL

```text
Entry_Price = close کندل تریگر (داخل entry_zone)
SL          = sweep_high + buffer
TP          = Entry_Price - (2 × (SL - Entry_Price))
```

> 🔒 **لنگر SL همیشه `sweep_low` / `sweep_high` (کف/سقف شکارشده) است — نه کف OB.** این قانون ثابت است و تغییر نمی‌کند.

### محاسبات جانبی

```text
pips_risk    = |Entry - SL| / pip_size
pips_reward  = |TP - Entry| / pip_size
RR_actual    = pips_reward / pips_risk          # باید = 2.0 باشد

# سایز لات:
risk_amount  = balance × risk_percent / 100
lots         = risk_amount / (pips_risk × pip_value_per_pip)
# مثال: balance=10,000$ , risk=0.5% , pips_risk=11 , pip_value=10$/lot
#        lots = 50 / (11 × 10) = 0.45 lot
# اگر pip_value مشخص نبود → فقط entry/sl/tp برگردد و حجم محاسبه نشود.
```

**قوانین خروج:**

| قانون | مقدار |
|---|---|
| Exit پیش‌فرض | برخورد با TP یا SL (بدون trailing) |
| حداقل `pips_risk` | `5` پیپ (کمتر = اسپرد و نویز RR را مخدوش می‌کند) |
| حداکثر `pips_risk` | `25` پیپ (فیلتر F2 بخش ۶.۱) |
| نسخه اختیاری مدیریت | بستن ۵۰٪ در 1R و انتقال SL به Entry (آمار را تغییر می‌دهد؛ **جدا** گزارش شود) |
| هزینه واقعی | اسپرد + کمیسیون در ارزیابی بک‌تست لحاظ شود |

---

## 📤 بخش ۵: فرمت ورودی و خروجی استاندارد (JSON)

### ۵.۱ ورودی مدل

```json
{
  "symbol": "EURUSD",
  "timeframe": "M5",
  "pip_size": 0.0001,
  "spread": 0.6,
  "session": "London_NewYork_Overlap",
  "balance": 10000,
  "risk_percent": 0.5,
  "htf": {"timeframe": "H1", "candles": []},
  "news": {"next_red_folder_utc": null, "minutes_to_event": null},
  "candles": [
    {"time": "2026-01-01T08:00:00Z", "open": 1.05000, "high": 1.05030, "low": 1.04980, "close": 1.05020}
  ]
}
```

> فیلدهای `spread` / `session` / `balance` / `risk_percent` / `htf` / `news` اختیاری‌اند؛
> اگر داده نشدند، فیلتر مربوطه **غیرفعال** می‌شود ولی سیگنال از دست نمی‌رود (به جز F1 که در بک‌تست حتماً داده شود).

### ۵.۲ خروجی — سیگنال معتبر (BUY)

```json
{
  "schema_version": "2.0",
  "timestamp": "2026-01-01T08:30:00Z",
  "symbol": "EURUSD",
  "timeframe": "M5",
  "signal": "BUY",
  "confidence": "High",
  "confidence_score": 85,
  "setup": {
    "sh_detected": true,
    "bms_detected": true,
    "rto_detected": true,
    "entry_trigger": true,
    "entry_type": "OrderBlock+FVG"
  },
  "setup_trace": {
    "sh_sweep_level": 1.05300,
    "sweep_low": 1.05270,
    "sweep_depth_pips": 3.0,
    "bms_break_level": 1.05420,
    "displacement_atr_ratio": 1.72,
    "leg_low": 1.05270,
    "leg_high": 1.05460,
    "retracement_at_entry": 0.526,
    "zone_type": "OrderBlock",
    "zone_bottom": 1.05320,
    "zone_top": 1.05380,
    "setup_age_candles": 21
  },
  "trade": {
    "entry_price": 1.05360,
    "stop_loss": 1.05250,
    "take_profit": 1.05580,
    "risk_reward": 2.0,
    "risk_pips": 11.0,
    "reward_pips": 22.0,
    "lot_size": 0.45
  },
  "invalidation": {
    "cancel_if_close_below": 1.05260,
    "cancel_if_close_above": null,
    "expiry_candles": 45
  },
  "filters": {
    "htf_bias": "BULLISH",
    "htf_alignment": true,
    "session": "London_NewYork_Overlap",
    "news_block": false,
    "risk_pips_ok": true,
    "spread_pips": 0.6
  },
  "notes": "Liquidity swept 3.0 pips below recent swing low, bullish BMS with 1.72x ATR displacement, RTO to bullish OB overlapping open FVG at 54.7% retracement."
}
```

### ۵.۳ خروجی — سیگنال فروش (SELL)

همان ساختار بالا با `signal: "SELL"`، `cancel_if_close_above` مقدار می‌گیرد و `cancel_if_close_below` می‌شود `null`.

### ۵.۴ خروجی — بدون سیگنال (WAIT)

```json
{
  "schema_version": "2.0",
  "timestamp": "2026-01-01T08:30:00Z",
  "symbol": "EURUSD",
  "timeframe": "M5",
  "signal": "WAIT",
  "confidence": "None",
  "confidence_score": 0,
  "setup": {
    "sh_detected": true,
    "bms_detected": false,
    "rto_detected": false,
    "entry_trigger": false,
    "entry_type": null
  },
  "trade": null,
  "invalidation": null,
  "rejected_because": "no_bms_within_max_delay",
  "notes": "Stop hunt detected but bullish BMS did not confirm within 15 candles."
}
```

**قواعد صدور JSON:**

1. فیلدهای `setup.*` فقط وقتی `true` می‌شوند که همان مرحله واقعاً رخ داده باشد (لاگ صادقانه).
2. `confidence` ∈ `High | Medium | Low | None` (جدول بخش ۷).
3. `rejected_because` باید یکی از کدهای خروجی پسودوکد بخش ۸ باشد.
4. `notes` یک جمله انگلیسی توصیفی از چرایی سیگنال/رد است.
5. خروجی همیشه و فقط JSON است — بدون متن اضافه.

---

## 🛡️ بخش ۶: فیلترهای ایمنی (Anti-Fake Filters)

### ۶.۱ فیلترهای اجباری (هر کدام = رد کامل سیگنال)

| # | فیلتر | قاعده |
|---|---|---|
| F1 | **خبر قرمز (Red Folder News)** | اگر تا ۳۰ دقیقه آینده خبر مهمی (CPI, NFP, FOMC, ECB/BOE rate) در راه است → سیگنال نادیده گرفته شود. بازه: `T-30min` تا `T+15min`. |
| F2 | **ریسک زیاد** | اگر فاصله Entry تا sweep (ریسک) **بیش از ۲۵ پیپ** بود → صرف‌نظر شود. |
| F3 | **جهت روند H1** | اگر در H1 روند نزولی است، سیگنال BUY **فیلتر** شود (و برعکس). پیش‌فرض: `only_trade_with_htf = true` → **فقط در جهت H1**. حالت ملایم (`with_caution`) = کاهش یک درجه confidence. |
| F4 | **خارج از سشن** | خارج از پنجره لندن/نیویورک سیگنال صادر نشود (جدول ۶.۲). |
| F5 | **ریسک خیلی کم** | `pips_risk < 5` → رد (اسپرد RR را می‌شکند). |
| F6 | **پوزیشن باز** | پوزیشن باز دیگر روی همین نماد یا نماد هم‌جهت (EURUSD + GBPUSD همزمان) → رد. |
| F7 | **حد ضرر روزانه** | رسیدن به `max_daily_loss` (پیش‌فرض ۲٪ حساب یا `3` ضرر متوالی) → تا شروع روز بعد سیگنال جدید صادر نشود. |
| F8 | **اسپرد** | `spread > max_spread_pips` (پیش‌فرض ۱.۵ پیپ) یا `spread > 20٪ pips_risk` → رد. مخصوصاً رول‌اور و اوپن سشن. |

### ۶.۲ پنجره سشن (بر اساس UTC — با رعایت DST)

| سشن | بازه (UTC تابستان) | وضعیت |
|---|---|---|
| آسیا | 23:00 – 06:00 | ❌ ترید نکن (فقط برای تعیین استخر نقدینگی: کف/سقف رنج آسیا) |
| لندن (اوپن) | 07:00 – 11:00 | ✅ بهترین بازه شکار نقدینگی |
| اوورلپ لندن/نیویورک | 12:00 – 16:00 | ✅✅ **بهترین بازدهی** |
| بعد از نیویورک | 16:00 – 20:00 | ⚠️ فقط با `confidence = High` |
| رول‌اور / بسته شدن | ~21:00 – 23:00 | ❌ خودداری (اسپرد بالا) |

> 🕐 ساعت‌ها نیم‌ساله عوض می‌شوند (DST اروپا/آمریکا)؛ حتماً با `IANA timezone` محاسبه کنید نه ساعت ثابت.
> اگر `session` نامشخص بود → سیگنال صادر می‌شود ولی `confidence` یک درجه پایین می‌آید.

### ۶.۳ فیلترهای کیفیت (توصیه‌شده — حذف سیگنال‌های فیک)

```text
Q1. تایم‌فریم بالاتر (H4) مخالف نباشد یا حداقل در سطح Weekly OB مهم نباشد.
Q2. OB هدف قبلاً تست نشده باشد (mitigations <= 1) یا تازه (fresh) باشد.
Q3. ناحیه RTO نباید با یک OB/FVG مخالف هم‌پوشانی داشته باشد.
Q4. در حالت STRICT حداقل یک FVG باز یا OB معتبر داخل ناحیه وجود داشته باشد.
Q5. حداکثر ۳ سیگنال در هر جهت در یک سشن (جلوگیری از overtrading).
Q6. ATR14 در M5 باید بین ۳ تا ۲۵ پیپ باشد (بازار مرده یا اخباری → رد).
Q7. عدم ورود در ۱۵ دقیقه اول بازگشایی لندن (فیک‌اوپن/شکار کاذب).
Q8. اگر قیمت در ۳ کندل اخیر بیش از ۲٪ جابه‌جا شده → ورود ممنوع (news volatility).
Q9. داده‌های کندل ناقص، تایم‌فریم یا نماد نامشخص → سیگنال نده.
```

---

## 📈 بخش ۷: مدل امتیازدهی Confidence

هر سیگنال باید امتیاز بگیرد (صفر تا صد). فقط `Medium` و `High` قابل معامله‌اند.

| معیار | امتیاز |
|---|---|
| هم‌جهت با روند H1 | `+25` |
| هم‌جهت با روند H4/D1 | `+15` |
| شکار زیر/بالای کف رنج آسیا، PDL/PDH یا Equal Lows | `+15` |
| دیسپلیسمنت BMS > ۱.۵ × ATR | `+15` |
| هم‌پوشانی OB + FVG در ناحیه RTO | `+10` |
| OB تازه (بدون تست قبلی) | `+10` |
| ورود در اوورلپ لندن/نیویورک | `+10` |
| ریتریسمنت دقیقاً در 50–61.8٪ (بدون انحراف) | `+10` |
| ریسک بین ۸ تا ۲۰ پیپ | `+5` |

| مجموع امتیاز | `confidence` | اقدام |
|---|---|---|
| `>= 75` | **High** | ✅ ورود کامل |
| `50 – 74` | **Medium** | ✅ ورود (اختیاری: نصف حجم) |
| `< 50` | **Low** | ❌ سیگنال صادر نشود |
| شرطی برقرار نشد | **None** | ❌ خروجی `WAIT` |

**توصیف کیفی معادل:**

- **High:** SH واضح با ویک بلند و برگشت سریع + BMS قدرتمند + RTO دقیقاً به OB/FVG + کندل تریگر قوی + هم‌جهت H1 + سشن لندن/نیویورک.
- **Medium:** SH و BMS معتبر، ناحیه RTO کمی مبهم یا کندل تریگر متوسط.
- **Low:** خلاف جهت H1، ناحیه فقط با فیبو ساخته شده، اسپرد بالا، بازار رنج.

---

## 🧩 بخش ۸: پسودوکد اجرایی (Python-like)

```python
def evaluate_signal(candles, params, context):
    if len(candles) < min_candles or incomplete(candles):
        return WAIT("insufficient_data")

    c = candles[-1]                       # کندل تازه بسته‌شده
    state.update_swings(candles)          # با رعایت لگ ۲ کندلی

    # ---------- ۰) فیلترهای بیرونی ----------
    if news_in_window(minutes=30):         return WAIT("red_folder_news")
    if not in_session():                   return WAIT("out_of_session")
    if spread_pips() > params.max_spread:  return WAIT("spread_too_wide")
    if daily_loss_hit():                   return WAIT("daily_loss_limit")

    h1 = htf_bias("H1")

    # ---------- ۱) SH ----------
    if state.stage == IDLE:
        sh = detect_stop_hunt(candles, state.last_swing_low, params)
        if sh:
            state.stage = SH_CONFIRMED
            state.sh = sh
        else:
            return WAIT("no_sh_detected")

    # ---------- ۲) BMS ----------
    elif state.stage == SH_CONFIRMED:
        bms = detect_bms(candles, state.sh, params)   # close > H + displacement
        if bms:
            state.stage = BMS_CONFIRMED
            state.leg  = build_leg(state.sh, bms)
            state.zone = find_rto_zone(state.leg, params)   # اعتبار: (OB ∪ FVG) ∩ fib ≠ ∅ ; ورود: خودِ OB/FVG
            if state.zone is None: state.reset(); return WAIT("no_valid_zone")
        elif c.index - state.sh.index > params.max_bms_delay:
            state.reset(); return WAIT("no_bms_within_max_delay")

    # ---------- ۳) RTO ----------
    elif state.stage == BMS_CONFIRMED:
        if close_beyond(c, state.sh.sweep, params.invalidation_buffer):
            state.reset(); return WAIT("invalidated")
        if price_enters(c, state.zone):
            state.stage = IN_ZONE_WAIT
        elif c.index - state.bms.index > params.max_wait:
            state.reset(); return WAIT("zone_not_reached")

    # ---------- ۴) TRIGGER ----------
    elif state.stage == IN_ZONE_WAIT:
        if is_bullish(c) and inside_zone(c.close, state.zone):
            sig = build_signal(state, h1, params)      # → JSON BUY/SELL
            if sig["trade"]["risk_pips"] < params.min_risk: state.reset(); return WAIT("risk_too_small")
            if sig["trade"]["risk_pips"] > params.max_risk: state.reset(); return WAIT("risk_too_large")
            if not htf_alignment(sig, params):         state.reset(); return WAIT("htf_filter")
            if sig["confidence"] == "Low":             state.reset(); return WAIT("low_confidence")
            state.reset(); return sig
        if close_beyond(c, state.sh.sweep, params.invalidation_buffer):
            state.reset(); return WAIT("invalidated")
        if c.index - state.bms.index > params.max_wait:
            state.reset(); return WAIT("expired")

    return WAIT("waiting")
```

**ساختار State:**

```python
state = {
  "stage": "IDLE | SH_CONFIRMED | BMS_CONFIRMED | IN_ZONE_WAIT",
  "sh":   {"level": ..., "sweep": ..., "index": ..., "depth_pips": ...},
  "bms":  {"level": ..., "index": ..., "atr_ratio": ...},
  "leg":  {"low": ..., "high": ...},
  "zone": {"bottom": ..., "top": ..., "type": "ob|fvg|overlap|fib", "fib": ...},
  "expiry_index": int,
}
```

**کدهای `rejected_because`:**
`insufficient_data` · `no_sh_detected` · `no_bms_within_max_delay` · `no_valid_zone` · `zone_not_reached` · `invalidated` · `expired` · `risk_too_small` · `risk_too_large` · `htf_filter` · `low_confidence` · `red_folder_news` · `out_of_session` · `spread_too_wide` · `daily_loss_limit` · `conflicting_signals`

---

## 🔁 بخش ۹: پروتکل بک‌تست با مدل زبانی (LLM Backtest Protocol)

### ۹.۱ فرمت ورودی (JSONL — یک خط برای هر کندل، به ترتیب زمانی)

```json
{"i": 184195, "t": "2026-01-01T08:05:00Z", "o": 1.05410, "h": 1.05435, "l": 1.05385, "c": 1.05430, "v": 1204, "atr14": 0.00042, "spread": 0.6}
```

### ۹.۲ قواعد اجباری برای مدل

```text
R1. فقط از کندل i به قبل اطلاعات بگیر. دیدن i+1, i+2 ممنوع (look-ahead).
R2. Swing فقط بعد از بسته‌شدن i+2 قابل استفاده است.
R3. State بین کندل‌ها حفظ شود؛ هر کندل یک‌بار State Machine را اجرا کن.
R4. اگر اطلاعات کافی نیست → WAIT خروجی بده، نه حدس.
R5. هر سیگنال باید دقیقاً یک JSON از بخش ۵ باشد.
R6. سیگنال‌ها در یک Ledger جمع شوند: ورود، خروج (TP/SL)، پیپ، زمان خروج.
R7. کندلی که هم SL و هم TP را لمس کند → SL اول لمس شده (محافظه‌کارانه).
R8. اسپرد در Entry اعمال شود: BUY در `close + spread`، SELL در `close - spread`.
R9. اگر سیگنال BUY و SELL هم‌زمان معتبر شدند → `conflicting_signals` و صبر.
```

### ۹.۳ معیارهای ارزیابی اجباری

```text
- تعداد تریدها, Win-Rate, Profit Factor
- Expectancy (پیپ به ازای هر ترید)
- Max Drawdown (پیپ و درصد)
- تفکیک: لندن vs نیویورک / EURUSD vs GBPUSD / High vs Medium confidence
- تعداد سیگنال‌های ردشده به تفکیک کد `rejected_because` (برای پیدا کردن فیلتر پررها)
- مقایسه با baseline: "چند ترید در جهت H1 بودند؟"
- گزارش جداگانه حالت STRICT و RELAXED
```

> ⚠️ **هشدار صادقانه:** بک‌تست یک LLM **تقریبی** است و جایگزین بک‌تست روی دیتای واقعی نیست. برای تصمیم سرمایه‌ای حتماً روی `MT5 / Histdata / Dukascopy` با اسپرد واقعی و کمیسیون تست کنید.

---

## 🧾 بخش ۱۰: مثال‌های عددی گام‌به‌گام

### ۱۰.۱ مثال BUY (EURUSD)

```text
1) Swing Low  L   = 1.05300   (تأییدشده)
2) SH: کندل j: low = 1.05270 , close = 1.05340
      نفوذ = 3.0 پیپ (بین 0.5 و 10 ✅) و close > L ✅  → sweep_low = 1.05270
3) Swing High H   = 1.05420
4) BMS: کندل k: close = 1.05450 > H با بدنه 1.72 × ATR ✅ (کلوز، نه ویک)
5) Leg: low = 1.05270 , high = 1.05460 → رنج موج = 19.0 پیپ
6) ناحیه‌ها:
      Bullish OB (بدنه)      = [1.05320, 1.05380]
      فیبوی 50%–61.8%        = [1.05343, 1.05365]      ← (1.05460 − 61.8%·0.00190) تا (1.05460 − 50%·0.00190)
      اعتبارسنجی (STRICT)    = [1.05343, 1.05365] ≠ ∅ ✅
      entry_zone (ورود)      = [1.05320, 1.05380]  ← کل بدنه‌ی OB (6.0 پیپ)
7) Trigger: کندل: open = 1.05340 , close = 1.05360 (سبز) و close داخل entry_zone ✅
8) Levels:
      Entry = 1.05360
      SL    = 1.05270 − 0.00020 = 1.05250   → 11.0 پیپ ریسک
      TP    = 1.05360 + 2 × 0.00110 = 1.05580 → 22.0 پیپ پاداش
      RR    = 2.0 ✅   (5 < 11 < 25 ✅)
9) سایز لات: 10,000$ × 0.5% / (11 × 10$) = 0.45 lot
10) F1..F8 → همه pass. H1 = BULLISH. اوورلپ لندن/نیویورک. OB تازه + FVG هم‌پوشان.
11) confidence = High (85) → خروجی JSON بخش ۵.۲
```

### ۱۰.۲ مثال SELL (EURUSD)

```text
1) Swing High H   = 1.05800
2) SH: کندل j: high = 1.05840 , close = 1.05760
      نفوذ = 4.0 پیپ ✅ و close < H ✅   → sweep_high = 1.05840
3) Swing Low  L   = 1.05680
4) BMS: کندل k: close = 1.05650 < L ✅ با بدنه کافی
5) Leg: high = 1.05840 , low = 1.05640 → رنج موج = 20.0 پیپ
6) ناحیه‌ها:
      Bearish OB (بدنه)    = [1.05740, 1.05780]
      فیبوی 50%–61.8%      = [1.05740, 1.05764]
      اعتبارسنجی (STRICT)  = [1.05740, 1.05764] ≠ ∅ ✅
      entry_zone (ورود)    = [1.05740, 1.05780]  ← کل بدنه‌ی OB (4.0 پیپ)
7) Trigger: کندل: open = 1.05760 , close = 1.05750 (قرمز) و close داخل entry_zone ✅
8) Levels:
      Entry = 1.05750
      SL    = 1.05840 + 0.00020 = 1.05860   → 11.0 پیپ ریسک
      TP    = 1.05750 − 2 × 0.00110 = 1.05530 → 22.0 پیپ پاداش
      RR    = 2.0 ✅
9) F1..F8 → pass. H1 = BEARISH ✅. confidence = High
```

---

## ⚠️ بخش ۱۱: Edge Cases و قواعد باطل‌شدن

| # | وضعیت | تصمیم |
|---|---|---|
| E1 | قیمت دقیقاً لمس Swing بدون نفوذ | ❌ SH نیست (`< min_sweep_pips`) |
| E2 | SH اتفاق افتاد، BMS هرگز نیامد | ⟳ برگشت به `IDLE`؛ منتظر SH جدید |
| E3 | BMS آمد، قیمت بدون اصلاح بالا رفت | ⟳ `EXPIRED` — سوار روند نشوید |
| E4 | قیمت از ناحیه رد شد و پایین‌تر رفت (بدون کلوز زیر sweep) | ⏳ صبر تا `max_wait`؛ اگر برگشت وارد شوید |
| E5 | کلوز زیر `sweep_low - 1pip` (یا بالای `sweep_high + 1pip`) | ❌ `INVALIDATED` قطعی |
| E6 | OB قبلاً ۲ بار تست شده | ❌ رد (ناحیه ضعیف) |
| E7 | هم‌پوشانی OB/FVG با فیبو در حالت STRICT وجود ندارد | ❌ رد — حتی اگر بقیه شرط‌ها کامل باشد |
| E8 | Zone داخل بازه خبر ساخته/لمس شد | ❌ رد تا اتمام بازه خبر (F1) |
| E9 | هم‌زمان BUY و SELL معتبر شدند | ❌ `conflicting_signals` — جهت H1 اولویت دارد |
| E10 | دو ستاپ هم‌جهت روی EURUSD و GBPUSD | ⚠️ فقط یکی (یا نصف حجم هر کدام) |
| E11 | Gap آخر هفته (Open خیلی دور از Close قبلی) | ❌ اولین ستاپ بعد از گپ رد می‌شود |
| E12 | `pips_risk < 5` یا SL داخل اسپرد | ❌ رد |
| E13 | سویینگ قدیمی‌تر از `max_ob_age` | ❌ ساختار کهنه، ستاپ غیرفعال |
| E14 | داده ناقص / نامشخص بودن نماد یا تایم‌فریم | ❌ سیگنال نده |
| E15 | کندل تریگر خلاف جهت بسته شد (مثلاً قرمز در BUY) | ❌ تریگر نیست — در ناحیه بمان تا `max_wait` |

---

## 🎛️ بخش ۱۲: جدول پارامترها (قابل تنظیم)

| پارامتر | پیش‌فرض | محدوده پیشنهادی |
|---|---|---|
| `timeframe` | `M5` | M5 / M15 |
| `lookback` (سویینگ) | `2` | 2 – 3 |
| `min_sweep_pips` | `0.5` | 0.3 – 1.0 |
| `max_sweep_pips` | `10.0` | 5 – 12 |
| `structure_lookback` | `10` | 8 – 20 |
| `max_bms_delay_candles` | `15` | 8 – 20 |
| `displacement_factor` (×ATR) | `1.0` | 0.8 – 1.5 |
| `min_body_ratio` | `0.60` | 0.5 – 0.75 |
| `rto_mode` | `strict` | strict / relaxed |
| `rto_fib_low` | `0.500` | 0.500 – 0.618 |
| `rto_fib_high` (strict) | `0.618` | 0.618 – 0.790 (relaxed) |
| `max_wait_candles` | `30` | 12 – 40 |
| `max_total_setup_candles` | `45` | 30 – 60 |
| `ob_zone_mode` | `full_candle` | full_candle / body |
| `sl_buffer_pips` | `2.0` | 1.5 – 3.0 |
| `invalidation_buffer_pips` | `1.0` | 0.5 – 2.0 |
| `rr_target` | `2.0` | ثابت (طبق Spec) |
| `max_risk_pips` | `25.0` | 20 – 30 |
| `min_risk_pips` | `5.0` | 4 – 8 |
| `max_spread_pips` | `1.5` | بسته به بروکر |
| `min_atr_m5_pips` | `3.0` | 2 – 5 |
| `max_atr_m5_pips` | `25.0` | 15 – 35 |
| `max_ob_age_candles` | `50` | 30 – 80 |
| `max_ob_mitigations` | `1` | 0 – 1 |
| `max_daily_losses` | `3` | 2 – 4 |
| `risk_per_trade_%` | `0.5` | 0.25 – 1.0 |
| `only_trade_with_htf` | `true` | true / false |
| `news_buffer_minutes` | `30` | 20 – 45 |
| `max_signals_per_session` | `3` | 2 – 5 |

---

## 📚 بخش ۱۳: اصطلاح‌نامه (Glossary)

| اصطلاح | معنی |
|---|---|
| **SH (Stop Hunt)** | حرکت قیمت برای تریگر شدن استاپ‌های جمع‌شده، سپس بازگشت |
| **BMS (Break of Market Structure)** | کلوز کندل بالای Swing High قبلی (یا پایین Swing Low قبلی) |
| **CHOCH (Change of Character)** | اولین شکست ساختار خلاف روند جاری |
| **MSS (Market Structure Shift)** | معادل CHOCH در بعضی منابع |
| **RTO (Return to Origin)** | بازگشت قیمت به ناحیه شروع موج (OB/FVG) |
| **OB (Order Block)** | آخرین کندل مخالف قبل از حرکت قوی منجر به BMS |
| **FVG (Fair Value Gap)** | ناهم‌خوانی قیمت بین سه کندل متوالی |
| **OTE (Optimal Trade Entry)** | ناحیه فیبوناچی ۶۱.۸٪–۷۹٪ |
| **Displacement** | کندل با بدنه بسیار بزرگ = تأیید قدرت |
| **Liquidity Pool** | ناحیه تجمع استاپ‌ها (Equal Lows/Highs، PDL/PDH، کف رنج آسیا) |
| **Mitigation** | بازگشت قیمت به OB قبلاً تشکیل‌شده |
| **Premium/Discount** | نیمه بالایی/پایینی رنج آخرین موج |
| **RR** | نسبت سود به زیان (Risk:Reward) |

---

## 📝 بخش ۱۴: پرامپت آماده (Quick Prompt)

مستقیماً به مدل بدهید:

```text
You are a mechanical forex trading engine.

Use the SH + BMS + RTO setup on M5/M15. Fixed RR = 2.0.

For BUY:
1. Detect a stop hunt: a candle whose low breaks the last confirmed swing low by
   0.5-10 pips, but closes back above that swing low.
2. Confirm bullish BMS: a later candle CLOSES above the last swing high with
   a strong body (>= 1.0 x ATR14), within 15 candles of the SH.
3. Define the leg: sweep_low to the high of the impulsive move.
4. Build the entry zone: (Bullish OB OR open FVG) INTERSECTED with the
   50%-61.8% retracement of the leg. If there is no overlap, no trade.
5. Enter only when a BULLISH candle CLOSES inside that zone.
6. Entry = that candle's close.
7. Stop loss = sweep low - 2 pips.
8. Take profit = entry + 2 * (entry - stop loss).
9. Skip if risk > 25 pips or risk < 5 pips.
10. Skip if a red-folder news event is within 30 minutes.
11. Skip if H1 trend is bearish.

For SELL: mirror everything.

If no valid setup exists, output signal "WAIT" with rejected_because.
Always output JSON only (schema v2.0). Never change RR.
```

---

## ✅ بخش ۱۵: جدول تصمیم نهایی (حل تناقض سه فایل) + چک‌لیست

### ۱۵.۱ تناقض‌ها و تصمیم اتخاذشده

| موضوع | `mus` | `qean` | `skill` | **تصمیم نهایی v2.2** | دلیل |
|---|---|---|---|---|---|
| تایم‌فریم | M5/M15 | M5 | 1H/4H | **M5** (M15 اختیاری) | درخواست اسکیلپ؛ `skill` ستاپ متفاوتی بود |
| لنگر SL | sweep ± بافر | sweep ± 2 پیپ | OB ± 8 پیپ | **sweep_low/high − buffer (≥2 پیپ)** | فرمول اصلی خودت؛ SL پشت ناحیه شکار = منطقی‌تر |
| نقطه Entry | close تریگر | close تریگر | `ob_mid` لیمیت | **close کندل تریگر داخل ناحیه** | شرط ۴ شما: «کندل سبز بسته شود» |
| شرط تریگر | داخل یا بالای ناحیه | `close >= zone_low` | ندارد | **کلوز باید `داخل` ناحیه باشد** | نسخه قبلی خیلی شل بود و بعد از خروج قیمت هم تریگر می‌زد |
| فیلتر RTO | 50–61.8 ∩ OB/FVG | زنجیره جایگزین | ندارد | **اعتبار = هم‌پوشانی اجباری؛ entry_zone = خودِ OB/FVG (`full_candle`)؛ لمس = ویک روی خودِ هم‌پوشانی** + حالت RELAXED اختیاری | متن اصلی: «اصلاح ۵۰-۶۱.۸٪ **و** ورود به OB/FVG». اگر entry_zone = هم‌پوشانی می‌شد → باکس ۰٫۵ پیپی و **۰ سیگنال** (تست ۳۰۰۰ کندلی) |
| تعریف OB | `[low, high]` | بدنه با fallback | `[low,high]` | **کل کندل `[low, high]` (پیش‌فرض `full_candle` از v2.2)** | ناحیه‌ی واقعی ICT؛ بدنه خیلی تنگ بود و تریگر را خفه می‌کرد |
| Swing | 2/2 | 2/2 | window=5 | **2/2** | متن اصلی |
| انقضای ستاپ | 15/30/45 | 12 | 50 | **15 / 30 / 45** | `12` برای M5 خیلی تنگ، `50` خیلی باز |
| فیلتر خبر | F1 اجباری | فقط هشدار | ندارد | **F1 اجباری** | فیلتر اول خودت |
| فیلتر H1 | اجباری | اختیاری | اختیاری | **اجباری (`only_trade_with_htf=true`)** | خودت گفتی «فقط در جهت H1» |
| سشن | جدول DST | نرم | ندارد | **جدول DST + تنزل confidence در نامشخصی** | ترکیب هر دو |
| Confidence | عددی 0-100 | کیفی | ندارد | **عددی + توصیف کیفی معادل** | ترکیب هر دو |
| خروجی | JSON کامل + trace | BUY/SELL/WAIT | فرمت متفاوت | **JSON ورودی/خروجی با ۳ حالت + `rejected_because`** | ترکیب هر دو |
| خروج | فقط TP/SL | TP/SL + lot | TP/SL | **TP/SL + فرمول lot** | از qean |
| سایر | State machine, edge cases, بک‌تست, پارامترها | مثال SELL، پرامپت آماده، قواعد لغو، ورودی مدل | کد پایتون خام (دارای look-ahead bias) | **همه به جز کد `skill`** | `skill` با باگ Look-Ahead بازنویسی شود |

### ۱۵.۲ چک‌لیست تحویل به برنامه‌نویس / مدل

- [ ] تشخیص سویینگ با لگ ۲ کندلی و **بدون Look-Ahead**
- [ ] State Machine با ۴ مرحله + انقضا + باطل‌شدن + `re-arm`
- [ ] تشخیص OB (کل کندل `full_candle`)، FVG، Leg و محاسبه ریتریسمنت
- [ ] ناحیه RTO در حالت STRICT: **اعتبار = هم‌پوشانی OB/FVG با فیبوی 50–61.8٪ ≠ ∅** و **entry_zone = خودِ OB/FVG (`full_candle`)** و **لمس ویک روی خودِ هم‌پوشانی**
- [ ] تریگر = کندل هم‌جهت که **کلوزش داخل ناحیه** باشد
- [ ] فرمول Entry/SL/TP با RR=2 و لنگر sweep و بافر اسپرد/ATR
- [ ] ۸ فیلتر اجباری F1–F8 + جدول سشن با DST
- [ ] مدل امتیازدهی Confidence (بخش ۷) و قید `Low = بدون ترید`
- [ ] خروجی JSON نسخه ۲.۰ با ۳ حالت BUY/SELL/WAIT
- [ ] محاسبه `lot_size` در صورت داشتن `balance` و `pip_value`
- [ ] بک‌تست با دیتای واقعی + اسپرد واقعی + معیارهای بخش ۹.۳
- [ ] گزارش جداگانه حالت STRICT و RELAXED

---

## 🗂️ بخش ۱۶: نقشه‌ی پیاده‌سازی (کجا چه چیزی است)

پیاده‌سازی قطعی این سند در پایتون نوشته شده و از طریق `SKILL.md` فراخوانی می‌شود:

| ماژول | مسئولیت | معادل بخش سند |
|---|---|---|
| `core/config.py` | پارامترها + `pip_size` | بخش ۱۲ |
| `core/market.py` | کندل، سویینگ (تأیید با تأخیر، بدون Look-Ahead)، ATR، FVG | بخش ۱.۱ / ۶.۳ |
| `core/structures.py` | OB، FVG، Leg، فیبو، **قانون RTO (اعتبار = هم‌پوشانی / ورود = خودِ OB)** | بخش ۱.۲–۱.۴، شرط ۳ |
| `core/engine.py` | State Machine `IDLE→SH→BMS→RTO→TRIGGER` + ساخت JSON | بخش ۲–۵ |
| `core/filters.py` | F1–F8 + جدول سشن | بخش ۶ |
| `core/confidence.py` | امتیاز ۰–۱۰۰ و برچسب High/Medium/Low | بخش ۷ |
| `core/backtest.py` | بک‌تست، اسپرد، اولویت SL، معیارها | بخش ۹ |
| `cli.py` | `selftest` / `example` / `gendata` / `backtest` / `scan` | — |
| `auto_trade/` | معامله خودکار با **تریگر صریح کاربر** (`--arm`) | — |
| `SKILL.md` | پروتکل مدل: خواندن پروژه، گرفتن ورودی، اجرا، گزارش | بخش ۱۴ |

راستی‌آزمایی: `python cli.py selftest` باید `ALL OK` بدهد (۴۴ چک قطعی، شامل
مثال عددی بخش ۱۰.۱ با Entry=1.05070 / SL=1.04930 / RR=2.0).

---

*این سند (`v2.2`) مرجع نهایی است و جایگزین سه فایل قبلی می‌شود. تغییر نسخه‌ی ۲.۲
نسبت به ۲.۱: **پیش‌فرض `ob_zone_mode` از `body` به `full_candle` برگشت** (ناحیه‌ی
ورود = کل کندل OB، مطابق PDF اصلی ICT) **و شرط لمس سخت‌گیرانه‌تر شد** (ویک باید
خودِ هم‌پوشانی دقیق با فیبو را لمس کند)؛ اعتبارسنجی، تریگر، لنگر SL و RR=2
بدون تغییر ماندند. ساختار JSON همچنان `schema_version: "2.0"` است.* تغییر نسخه‌ی ۲.۱
نسبت به ۲.۰ فقط در **تعریف ناحیه‌ی RTO** است: «اعتبار = هم‌پوشانی، entry_zone = خودِ OB/FVG»
(به شرط ۳ و جدول ۱۵.۱ نگاه کنید)؛ ساختار JSON همچنان `schema_version: "2.0"` است.
هر پیاده‌سازی باید دقیقاً مطابق همین قواعد باشد و انحراف فقط با بروزرسانی
`schema_version` مجاز است.*
