"""
اسکریپت تست چند نمادی - اجرای خودکار بک‌تست روی تمام فایل‌های دیتا
نحوه استفاده:
    python run_multi_symbol.py
"""
from __future__ import annotations

import os
import re
import json
import sys
from datetime import datetime

from core import Params, load_candles, run_backtest, pip_size_for
from core.config import get_params_for_symbol


# ============================================================
# تنظیمات کلی تست
# ============================================================
DATA_DIR = "data"
DEFAULT_HTF = "NEUTRAL"      # می‌توانید BULLISH/BEARISH/AUTO بگذارید
DEFAULT_SPREAD = "auto"       # پخش به صورت خودکار یا عدد ثابت
OUTPUT_FILE = "multi_symbol_report.csv"


def detect_symbol_from_filename(filename: str) -> tuple[str, str]:
    """استخراج نماد و تایم‌فریم از نام فایل"""
    name = os.path.splitext(filename)[0]
    # الگوهای رایج: XAUUSD_M15_..., EURUSD_M5_..., GOLD_H1_...
    match = re.match(r'([A-Z]+[A-Z0-9]*)[_-]?(M\d+|H\d+|D\d+|W\d+)?', name, re.IGNORECASE)
    if match:
        symbol = match.group(1).upper()
        timeframe = match.group(2).upper() if match.group(2) else "M5"
        return symbol, timeframe
    # اگر الگو پیدا نشد، از نام فایل استفاده کن
    return name.upper()[:6], "M5"


def estimate_spread_for_symbol(symbol: str) -> float:
    """تخمین اسپرد بر اساس نماد (بر حسب پیپ)"""
    s = symbol.upper()
    if any(x in s for x in ("XAU", "GOLD", "XAG")):
        return 2.5  # طلا معمولاً ۲-۳ پیپ
    if any(x in s for x in ("NAS", "US30", "US500", "GER")):
        return 2.0  # شاخص‌ها
    if "JPY" in s:
        return 1.2
    return 0.8  # جفت‌ارزهای اصلی


def run_single_symbol(filepath: str) -> dict:
    """اجرای بک‌تست روی یک فایل دیتا"""
    filename = os.path.basename(filepath)
    symbol, timeframe = detect_symbol_from_filename(filename)
    
    result = {
        "file": filename,
        "symbol": symbol,
        "timeframe": timeframe,
        "status": "UNKNOWN",
        "bars": 0,
        "signals": 0,
        "buy_signals": 0,
        "sell_signals": 0,
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate": 0.0,
        "net_pips": 0.0,
        "profit_factor": 0.0,
        "max_drawdown": 0.0,
        "top_rejections": "",
        "error": ""
    }
    
    try:
        # بارگذاری دیتا
        candles = load_candles(filepath)
        result["bars"] = len(candles)
        
        if len(candles) < 30:
            result["status"] = "SKIP_LOW_DATA"
            result["error"] = "دیتا کمتر از ۳۰ کندل است"
            return result
        
        # دریافت پارامترهای مخصوص نماد
        params = get_params_for_symbol(symbol)
        params.timeframe = timeframe
        
        # تخمین اسپرد
        spread = estimate_spread_for_symbol(symbol)
        
        # اجرای بک‌تست
        report = run_backtest(
            candles,
            params=params,
            symbol=symbol,
            htf_bias=DEFAULT_HTF,
            spread_pips=spread,
            verbose=False,
        )
        
        # استخراج نتایج
        s = report["summary"]
        result["status"] = "OK"
        result["signals"] = s["signals"]
        
        # شمارش BUY و SELL
        by_dir = s.get("signals_by_direction", {})
        result["buy_signals"] = by_dir.get("BUY", 0)
        result["sell_signals"] = by_dir.get("SELL", 0)
        
        result["trades"] = s["trades"]
        result["wins"] = s["wins"]
        result["losses"] = s["losses"]
        result["win_rate"] = s["win_rate"]
        result["net_pips"] = s["net_pips"]
        result["profit_factor"] = s["profit_factor"] if s["profit_factor"] else 0.0
        result["max_drawdown"] = s["max_drawdown_pips"]
        
        # دلایل اصلی رد شدن سیگنال‌ها
        rejections = report.get("rejections", {})
        if rejections:
            top_3 = sorted(rejections.items(), key=lambda x: x[1], reverse=True)[:3]
            result["top_rejections"] = "; ".join([f"{k}({v})" for k, v in top_3])
        
    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)[:200]
    
    return result


def print_summary_table(results: list[dict]):
    """چاپ جدول خلاصه نتایج"""
    print("\n" + "="*120)
    print("📊 گزارش جامع تست چند نمادی")
    print("="*120)
    
    # هدر جدول
    header = f"{'نماد':<10} {'تایم':<5} {'کندل':<6} {'سیگنال':<7} {'خرید':<6} {'فروش':<6} " \
             f"{'معامله':<7} {'برد':<5} {'باخت':<5} {'نرخ برد':<9} {'پیپ خالص':<10} {'وضعیت':<12}"
    print(header)
    print("-"*120)
    
    total_signals = 0
    total_trades = 0
    total_wins = 0
    ok_count = 0
    
    for r in results:
        status_icon = "✅" if r["status"] == "OK" else "❌"
        row = f"{r['symbol']:<10} {r['timeframe']:<5} {r['bars']:<6} {r['signals']:<7} " \
              f"{r['buy_signals']:<6} {r['sell_signals']:<6} {r['trades']:<7} " \
              f"{r['wins']:<5} {r['losses']:<5} {r['win_rate']:<9.1f} {r['net_pips']:<10.1f} " \
              f"{status_icon} {r['status']}"
        print(row)
        
        if r["status"] == "OK":
            ok_count += 1
            total_signals += r["signals"]
            total_trades += r["trades"]
            total_wins += r["wins"]
    
    print("-"*120)
    
    # خلاصه کلی
    print(f"\n📈 خلاصه کلی:")
    print(f"   تعداد نمادهای تست شده موفق: {ok_count}/{len(results)}")
    print(f"   کل سیگنال‌ها: {total_signals}")
    print(f"   کل معاملات: {total_trades}")
    if total_trades > 0:
        print(f"   نرخ برد کلی: {(total_wins/total_trades*100):.1f}%")
    
    # نمایش خطاها
    errors = [r for r in results if r["status"] == "ERROR"]
    if errors:
        print(f"\n❌ نمادهای دارای خطا:")
        for e in errors:
            print(f"   {e['symbol']}: {e['error']}")
    
    # نمایش دلایل رد شدن
    print(f"\n🔍 دلایل رایج رد شدن سیگنال‌ها:")
    all_rejections = {}
    for r in results:
        if r["top_rejections"]:
            for item in r["top_rejections"].split("; "):
                if "(" in item:
                    key = item.split("(")[0]
                    all_rejections[key] = all_rejections.get(key, 0) + 1
    
    for key, count in sorted(all_rejections.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"   {key}: {count} نماد")


def main():
    print("🚀 شروع تست چند نمادی")
    print(f"📁 پوشه دیتا: {DATA_DIR}")
    
    # پیدا کردن تمام فایل‌های CSV
    if not os.path.exists(DATA_DIR):
        print(f"❌ پوشه {DATA_DIR} پیدا نشد!")
        return 1
    
    csv_files = sorted([
        os.path.join(DATA_DIR, f) 
        for f in os.listdir(DATA_DIR) 
        if f.lower().endswith('.csv') and not f.startswith('multi_symbol')
    ])
    
    if not csv_files:
        print(f"❌ هیچ فایل CSV در پوشه {DATA_DIR} پیدا نشد!")
        return 1
    
    print(f"✅ {len(csv_files)} فایل دیتا پیدا شد")
    
    # اجرای بک‌تست روی هر فایل
    results = []
    for filepath in csv_files:
        filename = os.path.basename(filepath)
        print(f"\n⏳ در حال پردازش {filename}...")
        result = run_single_symbol(filepath)
        results.append(result)
        print(f"   → {result['symbol']}: {result['status']} | سیگنال‌ها: {result['signals']}")
    
    # چاپ گزارش نهایی
    print_summary_table(results)
    
    # ذخیره گزارش در فایل
    try:
        import csv
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            if results:
                writer = csv.DictWriter(f, fieldnames=results[0].keys())
                writer.writeheader()
                writer.writerows(results)
        print(f"\n💾 گزارش کامل در فایل '{OUTPUT_FILE}' ذخیره شد.")
    except Exception as e:
        print(f"⚠️ خطا در ذخیره گزارش: {e}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())