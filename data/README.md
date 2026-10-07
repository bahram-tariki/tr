# data/

**منبع اصلی داده: ترمینال MT5 همین سیستم (زنده).**
CSVهای این پوشه فقط کش/اسنپ‌شات MT5 هستند، نه منبع تحلیل.

## دریافت زنده از MT5

```bash
# کش ۲۰۰۰ کندل M5 از MT5
python cli.py fetch --symbol EURUSD --timeframe M5 --bars 2000 --out data/EURUSD_M5_live.csv

# بک‌تست مستقیم روی MT5 (بدون CSV واسط) + سوگیری H1 و اسپرد زنده
python cli.py backtest --data mt5:EURUSD:M5:10000 --symbol EURUSD --htf AUTO --spread auto
python cli.py backtest --data mt5:EURUSD:M5:10000 --symbol EURUSD --htf AUTO --spread auto --relaxed

# اسکن لحظه‌ای زنده
python cli.py scan --data mt5 --symbol EURUSD --last 1000 --htf AUTO --spread auto --balance 100000 --risk 0.5
```

- `--data mt5:SYM:TF:BARS` یعنی مستقیم از ترمینال بخوان (کندل در حال ساخت حذف می‌شود).
- `--htf AUTO` یعنی سوگیری H1 از خود MT5 (کلوز H1 در برابر SMA50).
- `--spread auto` یعنی اسپرد لحظه‌ای ask-bid از MT5.

## فرمت CSV (برای کش/بک‌تست آفلاین)

هدر اجباری:

```
time,open,high,low,close[,volume]
```

- `time`: ایزو۸۶۰۱ با منطقه زمانی (خروجی MT5 به UTC تبدیل می‌شود، مثال `2026-10-06T21:35:00+00:00`)
- قیمت‌ها: عدد اعشاری متناسب با نماد (EURUSD → ۵ رقم، USDJPY → ۳ رقم)
- JSON هم پذیرفته می‌شود (آرایه‌ای از همین فیلدها، یا شیء با کلید `candles`)

## نتیجه‌ی مرجع روی داده‌ی واقعی (2026-10-06، ‏EURUSD M5 ‏x10000 از MT5 دمو، ‏v2.2)

```
strict  htf=BULLISH spread~0.1: signals=2 (BUY Medium/Overlap، هر دو SL، net −20.7p) | IN_ZONE_WAIT=776
relaxed htf=BULLISH spread~0.1: signals=2 (BUY Medium/Overlap، هر دو SL، net −20.7p) | IN_ZONE_WAIT=1382
```

یعنی موتور روی داده‌ی واقعی تریگر می‌زند ولی بسیار گزینشی است (~۱ سیگنال در ۱۰۰۰۰ کندل).
`gendata` فقط برای smoke-test است و نتیجه‌ی تحلیلی ندارد.
