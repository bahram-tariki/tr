from collections import Counter
from core import Params, MarketData, Engine, Context, load_candles

for mode in ("strict", "relaxed"):
    p = Params(); p.rto_mode = mode; p.allow_fib_fallback = (mode == "relaxed")
    p.allow_neutral_htf = True
    candles = load_candles("data/EURUSD_M5.csv")
    md = MarketData(candles, p)
    eng = Engine(p, symbol="EURUSD")
    sizes, rel = [], Counter()
    trig = 0
    for i in range(len(candles)):
        out = eng.step(md, i, Context(time=candles[i].time, spread_pips=0.6, htf_bias="NEUTRAL"))
        st = out["_internal"]["stage"]
        z = eng.zone
        if st in ("BMS_CONFIRMED", "IN_ZONE_WAIT") and z is not None:
            sizes.append(round((z.hi - z.lo) / 0.0001, 2))
        if st == "IN_ZONE_WAIT" and z is not None:
            c = candles[i].close
            rel["inside" if z.lo <= c <= z.hi else ("above" if c > z.hi else "below")] += 1
            if len(sizes) < 999 and candles[i].bullish and z.lo <= c <= z.hi:
                pass
        if out["signal"] != "WAIT":
            trig += 1
    print(f"--- {mode} --- zone pips:", Counter(min(s, 40) for s in sizes).most_common(6))
    print("    >=2pip zones:", sum(1 for s in sizes if s >= 2), "/", len(sizes), "| wait rel:", dict(rel),
          "| signals:", trig)
