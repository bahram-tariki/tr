# auto_trade/ — معامله‌ی خودکار (تریگر دست کاربر و مدل)

> **قانون تریگر (غیرقابل مذاکره):** مدل هرگز خودبه‌خود شروع نمی‌کند.
> فقط وقتی کاربر صریحاً گفت «معامله خودکار را اجرا کن» و جمله‌ی تأیید را داد.

## ۱. راه‌اندازی (۵ مرحله)

1. **بپرس:** نمادها، حالت `paper`/`live`، ریسک هر معامله (٪)، سقف ضرر روزانه،
   حداکثر سیگنال در هر سشن.
2. **داده:** منبع اصلی **ترمینال MT5 همین سیستم (زنده)** است.
   در `config.json` برای هر نماد بنویس `"mt5:SYMBOL:M5:BARS"`
   (مثال `"EURUSD": "mt5:EURUSD:M5:1000"`)؛ `spread_pips: "auto"` و
   `htf_bias: {"EURUSD": "AUTO"}` هم از خود MT5 می‌آیند.
   CSV در `data/` فقط کش است (فرمت: `data/README.md`).
3. **تنظیم:**
   ```bash
   copy auto_trade\config.example.json auto_trade\config.json
   ```
   مقادیر کاربر را در `config.json` بگذار (نمادها، `mode`، `balance`،
   `risk_percent`، `htf_bias` هر نماد، مسیر `data` هر نماد).
4. **خشک (Dry-run) — بدون `--arm`:**
   ```bash
   python auto_trade/monitor.py --config auto_trade/config.json --once
   ```
   خروجی را به کاربر نشان بده: هر نماد WAIT است یا چه سفارشی *می‌شد* ثبت شود.
   هیچ سفارشی ثبت نمی‌شود.
5. **شروع — فقط با جمله‌ی تأیید کاربر** (توکن دقیق):
   ```bash
   python auto_trade/monitor.py --config auto_trade/config.json --arm ARMED
   ```
   پیش از Enter باید به کاربر بگویی دقیقاً چه چیزی با چه ریسکی شروع می‌شود.
   حالت پیش‌فرض `paper` است. برای `live` باید کاربر دلیل و ریسک را تأیید کند
   و `MetaTrader5` نصب باشد.

## ۲. توقف

```bash
python auto_trade/monitor.py --disarm
# یا دستی: ساخت فایل auto_trade/STOP
```

- `--disarm` فایل `STOP` می‌سازد.
- حلقه‌ی `--arm` فایل `STOP` را **بین دو نماد/کندل** چک می‌کند و فوری خارج می‌شود.
- توقف‌های خودکار: `max_daily_losses`، `max_total_losses`، نبود داده، خطای بروکر.
- برای شروع دوباره، فایل `STOP` را حذف کن.

## ۳. فایل‌ها

| فایل | نقش |
|---|---|
| `config.example.json` | الگو — کپی به `config.json` کن |
| `broker.py` | `PaperBroker` (کاغذی + اسپرد، لاگ `state/paper_orders.jsonl`) و `MT5Broker` (lazy import، خطای دوستانه اگر نصب نیست) |
| `journal.py` | یک پوزیشن باز در هر نماد، جهت قفل‌شده تا بسته‌شدن، سقف ضرر روزانه/کلی، شمارش سیگنال سشن، persist در `state/journal.json` |
| `monitor.py` | حلقه‌ی زنده: داده → `MarketData` → `Engine.step` → اجرا |
| `state/` | `journal.json`، `monitor.jsonl`، `paper_orders.jsonl` (خودکار ساخته می‌شود) |
| `STOP` | کلید اضطراری (وجود = توقف) |

## ۴. سوییچ‌ها

| سوییچ | معنا |
|---|---|
| `--config f.json` | فایل تنظیمات (پیش‌فرض `auto_trade/config.json`) |
| `--once` | فقط یک گذر (خشک یا armed-once) |
| `--arm ARMED` | تنها توکن مجاز برای ثبت سفارش |
| `--disarm` | ساخت فایل `STOP` و خروج |
| `--symbols EURUSD,GBPUSD` | override نمادها |
| `--mode paper\|live` | override حالت |

## ۵. نکته‌ی معماری

سفارش‌ها با `Context` لحظه‌ای ساخته می‌شوند (`spread_pips`، `htf_bias`،
`minutes_to_red_news`، `balance`، `risk_percent`، `daily_losses`،
`signals_this_session`، `blocked`) تا همه‌ی فیلترها دوباره روی لحظه‌ی اجرا
اعمال شوند — نه فقط روی لحظه‌ی سیگنال. پوزیشن باز هر نماد هم via
`blocked=open_position` جلوی سیگنال تکراری را می‌گیرد.
تسویه‌ی paper روی آخرین کندل انجام می‌شود (اولویت SL، مثل بک‌تست).

## ۶. عیب‌یابی

- `config not found` → اول `config.example.json` را کپی کن.
- `MetaTrader5 ... not installed` → یا `pip install MetaTrader5` (ویندوز + ترمینال MT5)
  یا `mode=paper` بگذار.
- `STOP file exists` → فایل `auto_trade/STOP` را حذف کن.
- `--arm token must be exactly ARMED` → توکن را دقیق بنویس.
