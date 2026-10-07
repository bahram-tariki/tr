"""رابط خط فرمان (CLI) — فراخوانی پایتونی بخش‌های سند SPEC-v2.

مثال‌ها:
    python cli.py selftest
    python cli.py gendata --bars 3000 --seed 7
    python cli.py backtest --data data/EURUSD_M5.csv --htf BULLISH
    python cli.py scan --data data/EURUSD_M5.csv --last 400
    python cli.py example
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timedelta

from core import (
    Params, Candle, MarketData, Engine, Context,
    run_backtest, load_candles, pip_size_for, digits_for,
)
from core.filters import session_of, SESSION_WINDOWS
from core.structures import fib_band, intersect, retracement
from core.confidence import score_signal
from core.structures import Zone
from core.fixtures import buy_fixture
from core.io import default_contexts

EURUSD_PIP = 0.0001


# ---------------------------------------------------------------------- #
#  selftest — تأیید محاسبات با داده قطعی
# ---------------------------------------------------------------------- #
def cmd_selftest(_args) -> int:
    checks = []

    def ok(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        print(("  PASS  " if cond else "  FAIL  ") + name + (("  | " + str(detail)) if detail else ""))

    # 1) اندازه پیپ
    ok("pip EURUSD=0.0001", pip_size_for("EURUSD") == 0.0001)
    ok("pip USDJPY=0.01", pip_size_for("USDJPY") == 0.01)
    ok("pip XAUUSD=0.1", pip_size_for("XAUUSD") == 0.1)

    # 2) سویینگ + تأخیر تأیید (بدون Look-Ahead)
    p = Params()
    fx = buy_fixture()
    md = MarketData(fx, p)
    sw = {s[1]: s for s in md.swings}
    ok("swing high @3 price 1.05130", 3 in sw and sw[3][0] == "high" and abs(sw[3][2] - 1.05130) < 1e-9)
    ok("swing high confirm = 5", 3 in sw and sw[3][3] == 5)
    ok("swing low @8 price 1.04990", 8 in sw and sw[8][0] == "low" and abs(sw[8][2] - 1.04990) < 1e-9)
    ok("swing low confirm = 10", 8 in sw and sw[8][3] == 10)
    ok("no swing visible at i=4", md.last_high(4) is None or md.last_high(4)[1] != 3)
    ok("swing high visible at i=5", md.last_high(5) is not None and md.last_high(5)[1] == 3)

    # 3) ATR ساده ۱۴
    a14 = md.atr(14, 14)
    ok("ATR(14) in 4..8 pips", 0.0004 <= a14 <= 0.0008, f"{a14/EURUSD_PIP:.2f} pips")

    # 4) فیبوناچی و هم‌پوشانی
    band = fib_band(1.04950, 1.05195, "bull", p)
    ok("fib band lo = 1.050436", abs(band[0] - (1.05195 - 0.618 * 0.00245)) < 1e-12, f"{band[0]:.6f}")
    ok("fib band hi = 1.050725", abs(band[1] - (1.05195 - 0.500 * 0.00245)) < 1e-12, f"{band[1]:.6f}")
    ok("intersect non-empty", intersect(1.05060, 1.05075, band[0], band[1]) is not None)
    ok("intersect empty", intersect(1.04960, 1.04990, band[0], band[1]) is None)
    ok("retracement 50% at 1.050725", abs(retracement(band[1], 1.04950, 1.05195, "bull") - 0.5) < 1e-12)

    # 5) سطوح خروج و RR
    entry, sl = 1.05070, 1.04930
    risk = (entry - sl) / EURUSD_PIP
    tp = entry + 2.0 * (entry - sl)
    ok("risk = 14.0 pips", abs(risk - 14.0) < 1e-6, risk)
    ok("tp = 1.05350", abs(tp - 1.05350) < 1e-12, tp)
    ok("rr = 2.0", abs(((tp - entry) / (entry - sl)) - 2.0) < 1e-12)

    # 6) سشن‌ها
    ok("13:35 UTC = Overlap", session_of("2026-01-05T13:35:00+00:00")[0] == "Overlap")
    ok("02:00 UTC = Asia(block)", session_of("2026-01-05T02:00:00+00:00")[1] == "block")
    ok("22:00 UTC = Rollover(block)", session_of("2026-01-05T22:00:00+00:00")[1] == "block")
    ok("17:30 UTC = NY_Late(high_only)", session_of("2026-01-05T17:30:00+00:00")[1] == "high_only")
    ok("5 session windows", len(SESSION_WINDOWS) == 5)

    # 7) آستانه‌های confidence
    z = Zone(kind="ob", lo=1.05060, hi=1.050725, index=13, retr_shallow=0.5, fresh=True)
    class _C: pass
    c = _C(); c.htf_bias = "BULLISH"; c.htf4_bias = "BEARISH"
    c.sweep_pool_hint = None
    sc, lbl, _ = score_signal(direction="bull", ctx=c, params=p, zone=z,
                              displacement_ratio=1.9, risk_pips=14.0, session_name="Overlap")
    ok("score = 75 / High", sc == 75 and lbl == "High", f"{sc}/{lbl}")
    c.htf_bias = "BEARISH"
    sc2, lbl2, _ = score_signal(direction="bull", ctx=c, params=p, zone=z,
                                displacement_ratio=1.0, risk_pips=30.0, session_name="Asia")
    ok("aligned-miss => lower score", sc2 < 75, sc2)
    ok("Low below 50", score_signal(direction="bull", ctx=c, params=p,
                                    zone=Zone(kind="fib", lo=0, hi=1, index=0, retr_shallow=0.5, fallback=True),
                                    displacement_ratio=1.0, risk_pips=30.0, session_name="Asia")[1] == "Low")

    # 8) State Machine کامل روی داده قطعی → BUY
    eng = Engine(p, symbol="EURUSD")
    md2 = MarketData(fx, p)
    ctx = Context(time=fx[19].time, spread_pips=0.6, htf_bias="BULLISH",
                  balance=10000.0, risk_percent=0.5, pip_value_per_lot=10.0)
    sig = None
    for i in range(len(fx)):
        out = eng.step(md2, i, ctx if i == 19 else Context(time=fx[i].time, spread_pips=0.6, htf_bias="BULLISH"))
        if out["signal"] != "WAIT":
            sig = out
            sig_bar = i
    ok("state machine emits BUY", sig is not None and sig["signal"] == "BUY")
    if sig:
        ok("trigger bar = 19", sig_bar == 19, sig_bar)
        ok("entry = 1.05070", abs(sig["trade"]["entry_price"] - 1.05070) < 1e-9, sig["trade"]["entry_price"])
        ok("stop loss = 1.04930", abs(sig["trade"]["stop_loss"] - 1.04930) < 1e-9, sig["trade"]["stop_loss"])
        ok("take profit = 1.05350", abs(sig["trade"]["take_profit"] - 1.05350) < 1e-9, sig["trade"]["take_profit"])
        ok("risk 14.0 / reward 28.0", sig["trade"]["risk_pips"] == 14.0 and sig["trade"]["reward_pips"] == 28.0,
           (sig["trade"]["risk_pips"], sig["trade"]["reward_pips"]))
        ok("rr 2.0", sig["trade"]["risk_reward"] == 2.0)
        # v2.2: ناحیه full_candle است؛ لبه‌ی بالایی (سایه‌ی 1.05080) بیرون Discount
        # می‌افتد (retr_shallow≈0.469 < 0.5) پس بونوس discount_placement نیست: 65/Medium
        ok("confidence Medium/65 (v2.2 full_candle)", sig["confidence"] == "Medium" and sig["confidence_score"] == 65,
           (sig["confidence"], sig["confidence_score"]))
        ok("entry_type = OrderBlock", sig["setup"]["entry_type"] == "OrderBlock", sig["setup"]["entry_type"])
        zw = (sig["setup_trace"]["zone_top"] - sig["setup_trace"]["zone_bottom"]) / EURUSD_PIP
        ok("entry zone = full OB (>=1 pip)", zw >= 1.0, f"{zw:.2f} pips")
        ok("session Overlap", sig["filters"]["session"] == "Overlap")
        ok("lot = 0.36", sig["trade"]["lot_size"] == 0.36, sig["trade"]["lot_size"])
        ok("all 4 setup flags true", all(sig["setup"][k] for k in
           ("sh_detected", "bms_detected", "rto_detected", "entry_trigger")))
        json.dumps(sig)  # قابل سریال‌سازی

    # 9) فیلترها
    def run_all(htf, spread, when=None, balance=None):
        e = Engine(Params(), symbol="EURUSD")
        m = MarketData(fx, Params())
        last = None
        for i in range(len(fx)):
            tm = when or fx[i].time
            last = e.step(m, i, Context(time=tm, spread_pips=spread, htf_bias=htf,
                                        balance=balance, risk_percent=0.5 if balance else None))
        return last

    out = run_all("BULLISH", 3.0)
    ok("spread filter blocks", out["signal"] == "WAIT" and out["rejected_because"] == "spread_too_wide",
       out["rejected_because"])
    out = run_all("BEARISH", 0.6)
    ok("htf filter blocks", out["signal"] == "WAIT" and out["rejected_because"] == "htf_filter",
       out["rejected_because"])
    out = run_all("NEUTRAL", 0.6)
    ok("neutral htf blocks (strict)", out["signal"] == "WAIT" and out["rejected_because"] == "htf_filter",
       out["rejected_because"])
    out = run_all("BULLISH", 0.6, when="2026-01-05T02:10:00+00:00")
    ok("session filter blocks", out["signal"] == "WAIT" and out["rejected_because"] in
       ("out_of_session", "no_sh_detected"), out["rejected_because"])
    out = run_all("BULLISH", 0.6, balance=10000.0)
    ok("lot size present", out.get("trade", {}) and out["trade"]["lot_size"] == 0.36,
       out.get("trade", {}))

    failed = [n for n, cnd, _ in checks if not cnd]
    print(f"\n{len(checks) - len(failed)}/{len(checks)} checks passed.")
    if failed:
        print("FAILED: " + ", ".join(failed))
        return 1
    print("ALL OK")
    return 0


# ---------------------------------------------------------------------- #
#  example — بازتولید مثال‌های سند (بخش ۱۰)
# ---------------------------------------------------------------------- #
def cmd_example(_args) -> int:
    p = Params()
    data = buy_fixture()
    eng = Engine(p, symbol="EURUSD")
    md = MarketData(data, p)
    print("== BUY example (section 10.1 of SPEC) ==")
    sig = None
    for i in range(len(data)):
        out = eng.step(md, i, Context(time=data[i].time, spread_pips=0.6, htf_bias="BULLISH",
                                      balance=10000.0, risk_percent=0.5, pip_value_per_lot=10.0))
        if out["signal"] != "WAIT":
            sig = out
    print(json.dumps(sig, indent=2, ensure_ascii=False))
    return 0 if sig else 1


# ---------------------------------------------------------------------- #
#  gendata — داده مصنوعی برای تست دود (SMOKE)
# ---------------------------------------------------------------------- #
def cmd_gendata(args) -> int:
    """داده مصنوعی ساخت‌یافته (پاک‌شدن/ریتریس/امپالس) به‌جای نویز محض."""
    rnd = random.Random(args.seed)
    t0 = datetime(2026, 1, 5, 0, 0, 0)
    pip = EURUSD_PIP

    # 1) مسیر قیمت از پاک‌شدن‌های متناوب (Leg های صعودی/نزولی)
    path = [args.base]
    price = args.base
    direction = 1
    while len(path) < args.bars:
        leg_len = rnd.randint(8, 55)
        leg_size = rnd.uniform(8, 70) * pip * direction
        # شکل داخل لگ: شتاب اولیه، تصحیح جزئی، ادامه حرکت
        weights = [1.0 + 1.4 * ((k + 1) / leg_len) ** 0.6 for k in range(leg_len)]
        total = sum(weights)
        for k in range(leg_len):
            step = leg_size * weights[k] / total
            noise = rnd.gauss(0, 1.4 * pip)
            pullback = 0.0
            if rnd.random() < 0.18:
                pullback = -direction * rnd.uniform(0.2, 1.0) * pip
            price += step + noise + pullback
            path.append(price)
        direction *= -1
    path = path[: args.bars]

    # 2) ساخت OHLC
    rows = []
    prev = path[0]
    for i, c in enumerate(path):
        o = prev if i else path[0] - rnd.uniform(0.5, 2.0) * pip
        wick = abs(rnd.gauss(0, 1.1)) * pip
        h = max(o, c) + wick
        l = min(o, c) - abs(rnd.gauss(0, 1.1)) * pip
        rows.append((t0 + timedelta(minutes=5 * i), o, h, l, c))
        prev = c

    import os
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        f.write("time,open,high,low,close,volume\n")
        for t, o, h, l, c in rows:
            f.write(f"{t.isoformat()}+00:00,{o:.5f},{h:.5f},{l:.5f},{c:.5f},100\n")
    print(f"wrote {args.bars} candles -> {args.out}")
    return 0


# ---------------------------------------------------------------------- #
#  backtest
# ---------------------------------------------------------------------- #
def _resolve_candles(data_arg, symbol, bars=0):
    """data_arg can be a CSV/JSON path or mt5:SPEC. Returns (candles, source_desc)."""
    if data_arg.lower().startswith("mt5"):
        from core.mt5_data import fetch_candles
        # formats: "mt5" | "mt5:EURUSD" | "mt5:EURUSD:M5:2000"
        parts = data_arg.split(":")
        sym = parts[1] if len(parts) > 1 and parts[1] else symbol
        tf = parts[2] if len(parts) > 2 and parts[2] else "M5"
        n = int(parts[3]) if len(parts) > 3 and parts[3] else (bars or 2000)
        candles = fetch_candles(sym, tf, n)
        return candles, f"MT5 live {sym} {tf} x{n}"
    candles = load_candles(data_arg)
    if bars:
        candles = candles[-bars:]
    return candles, data_arg


def _resolve_htf(htf_arg, symbol):
    htf = str(htf_arg).upper()
    if htf == "AUTO":
        from core.mt5_data import get_htf_bias
        return get_htf_bias(symbol, "H1")
    return htf


def _resolve_spread(spread_arg, symbol):
    s = str(spread_arg).lower()
    if s == "auto":
        from core.mt5_data import get_spread_pips
        return float(get_spread_pips(symbol))
    return float(spread_arg)


def cmd_backtest(args) -> int:
    p = Params.from_dict(json.load(open(args.params, "r", encoding="utf-8")) if args.params else {})
    if args.relaxed:
        p.rto_mode = "relaxed"
        p.allow_fib_fallback = True
    p.validate()
    htf = _resolve_htf(args.htf, args.symbol)
    spread = _resolve_spread(args.spread, args.symbol)
    candles, src = _resolve_candles(args.data, args.symbol, args.bars)
    report = run_backtest(
        candles, params=p, symbol=args.symbol, htf_bias=htf,
        spread_pips=spread, verbose=args.verbose,
    )
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        s = report["summary"]
        print(f"\n== {args.symbol} {p.timeframe}  mode={p.rto_mode}  htf={htf} src={src} spread={spread} ==")
        print(f"bars        : {s['bars']}")
        print(f"signals     : {s['signals']}  {s['signals_by_direction']}")
        print(f"trades      : {s['trades']}  wins={s['wins']} losses={s['losses']}")
        print(f"win rate    : {s['win_rate']}%   (breakeven RR2 = {s['breakeven_win_rate']}%)")
        print(f"profit fact.: {s['profit_factor']}")
        print(f"expectancy  : {s['expectancy_pips']} pips/trade")
        print(f"net / maxDD : {s['net_pips']} / {s['max_drawdown_pips']} pips")
        print("\nby session:")
        for k, v in report["by_session"].items():
            print(f"  {k:12} n={v['trades']:<4} win={v['win_rate']:>5}%  pips={v['pips']}")
        print("by confidence:")
        for k, v in report["by_confidence"].items():
            print(f"  {k:12} n={v['trades']:<4} win={v['win_rate']:>5}%  pips={v['pips']}")
        print("rejections (setup reached, then dropped):")
        for k, v in list(report["rejections"].items())[:10]:
            print(f"  {k:28} {v}")
        print("stage coverage (bars):")
        for k, v in report["stage_coverage"].items():
            print(f"  {k:28} {v}")
        print()
    return 0


# ---------------------------------------------------------------------- #
#  scan — آخرین وضعیت روی داده
# ---------------------------------------------------------------------- #
def cmd_scan(args) -> int:
    p = Params()
    if args.relaxed:
        p.rto_mode = "relaxed"; p.allow_fib_fallback = True
    htf = _resolve_htf(args.htf, args.symbol)
    spread = _resolve_spread(args.spread, args.symbol)
    if str(args.data).lower().startswith("mt5"):
        candles, _ = _resolve_candles(f"{args.data}" if ":" in str(args.data) else f"mt5:{args.symbol}:M5:{args.last}", args.symbol, args.last)
    else:
        candles = load_candles(args.data)
        candles = candles[-args.last:]
    md = MarketData(candles, p)
    eng = Engine(p, symbol=args.symbol)
    last = None
    for i in range(len(candles)):
        last = eng.step(md, i, Context(time=candles[i].time, spread_pips=spread, htf_bias=htf,
                                       balance=args.balance, risk_percent=args.risk,
                                       minutes_to_red_news=args.news_in))
    print(json.dumps(last, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="cli.py", description="SH+BMS+RTO core runner")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("selftest", help="run deterministic checks")
    sub.add_parser("example", help="print the documented BUY example signal")

    g = sub.add_parser("gendata", help="generate synthetic M5 data")
    g.add_argument("--out", default="data/EURUSD_M5.csv")
    g.add_argument("--bars", type=int, default=3000)
    g.add_argument("--seed", type=int, default=7)
    g.add_argument("--base", type=float, default=1.05000)

    b = sub.add_parser("backtest", help="run a backtest")
    b.add_argument("--data", required=True, help="CSV path or mt5:SYM:TF:BARS (e.g. mt5:EURUSD:M5:2000)")
    b.add_argument("--symbol", default="EURUSD")
    b.add_argument("--htf", default="NEUTRAL", choices=["BULLISH", "BEARISH", "NEUTRAL", "AUTO"])
    b.add_argument("--spread", default="0.6", help="pips or 'auto' (live MT5 spread)")
    b.add_argument("--bars", type=int, default=0)
    b.add_argument("--params", default=None)
    b.add_argument("--relaxed", action="store_true")
    b.add_argument("--json", action="store_true")
    b.add_argument("--verbose", action="store_true")

    s = sub.add_parser("scan", help="latest signal/WAIT on the tail of a file")
    s.add_argument("--data", required=True, help="CSV path or mt5 (live)")
    s.add_argument("--symbol", default="EURUSD")
    s.add_argument("--last", type=int, default=400)
    s.add_argument("--htf", default="NEUTRAL", choices=["BULLISH", "BEARISH", "NEUTRAL", "AUTO"])
    s.add_argument("--spread", default="0.6", help="pips or 'auto' (live MT5 spread)")
    s.add_argument("--balance", type=float, default=10000.0)
    s.add_argument("--risk", type=float, default=0.5)
    s.add_argument("--news-in", type=float, default=None)
    s.add_argument("--relaxed", action="store_true")

    f = sub.add_parser("fetch", help="fetch candles from MT5 terminal (same machine)")
    f.add_argument("--symbol", default="EURUSD")
    f.add_argument("--timeframe", default="M5", choices=["M1", "M5", "M15", "H1", "H4", "D1"])
    f.add_argument("--bars", type=int, default=1000)
    f.add_argument("--out", default=None)
    return ap


def cmd_fetch(args) -> int:
    from core.mt5_data import fetch_candles, save_csv, get_spread_pips, get_htf_bias
    candles = fetch_candles(args.symbol, args.timeframe, args.bars)
    out = args.out or f"data/{args.symbol}_{args.timeframe}.csv"
    save_csv(candles, out)
    try:
        spread = get_spread_pips(args.symbol)
    except Exception:
        spread = float("nan")
    try:
        bias = get_htf_bias(args.symbol, "H1")
    except Exception as e:
        bias = f"unknown ({e})"
    print(f"fetched {len(candles)} closed {args.timeframe} bars {args.symbol} -> {out}")
    print(f"last: {candles[-1].time} O={candles[-1].open} H={candles[-1].high} "
          f"L={candles[-1].low} C={candles[-1].close}")
    print(f"live spread: {spread} pips | H1 bias: {bias}")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    handler = {
        "selftest": cmd_selftest,
        "example": cmd_example,
        "gendata": cmd_gendata,
        "backtest": cmd_backtest,
        "scan": cmd_scan,
        "fetch": cmd_fetch,
    }[args.cmd]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
