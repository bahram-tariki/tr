"""Live monitor: data -> core Engine -> broker (paper/MT5).

Safety model (non-negotiable, see SKILL.md section 7):
- NEVER places an order without `--arm ARMED` + explicit user confirmation.
- Default mode is `paper`. `live` requires config mode=live AND --arm ARMED.
- STOP file (`auto_trade/STOP`) is checked between symbols/bars -> immediate exit.
- All filters are re-applied at execution time via a fresh Context
  (spread, htf_bias, news, balance, risk, daily_losses, session count, blocked).

Usage:
    # dry-run (no arm — only report what WOULD be ordered)
    python auto_trade/monitor.py --config auto_trade/config.json --once
    # start only after explicit user approval
    python auto_trade/monitor.py --config auto_trade/config.json --arm ARMED
    # stop
    python auto_trade/monitor.py --disarm        # creates STOP file
    # (or manually create file auto_trade/STOP)
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import Params, MarketData, Engine, Context, load_candles, pip_size_for
from core.filters import session_of

try:
    from .broker import PaperBroker, MT5Broker
    from .journal import Journal
except ImportError:
    from broker import PaperBroker, MT5Broker
    from journal import Journal

STOP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "STOP")
STATE_DIR_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state")


def stop_requested() -> bool:
    return os.path.exists(STOP_FILE)


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_symbol_candles(cfg, symbol):
    """CSV path or live MT5 (data value 'mt5:SYM:TF:BARS' or config mt5_bars)."""
    src = cfg.get("data", {}).get(symbol, "")
    if isinstance(src, str) and src.lower().startswith("mt5"):
        from core.mt5_data import fetch_candles
        parts = src.split(":")
        sym = parts[1] if len(parts) > 1 and parts[1] else symbol
        tf = parts[2] if len(parts) > 2 and parts[2] else "M5"
        try:
            n = int(parts[3]) if len(parts) > 3 and parts[3] else int(cfg.get("mt5_bars", 1000))
        except ValueError:
            n = 1000
        return fetch_candles(sym, tf, n)
    if not src or not os.path.exists(src):
        raise FileNotFoundError(f"[{symbol}] data not found: {src!r} (use mt5:SYM:M5:BARS for live)")
    return load_candles(src)


def _live_spread(cfg, symbol, default=0.6) -> float:
    sp = cfg.get("spread_pips", default)
    if isinstance(sp, str) and sp.lower() == "auto":
        try:
            from core.mt5_data import get_spread_pips
            return float(get_spread_pips(symbol))
        except Exception:
            return float(default)
    return float(sp)


def _live_htf(cfg, symbol, default="NEUTRAL") -> str:
    htf_map = cfg.get("htf_bias", {})
    htf = htf_map.get(symbol, cfg.get("htf_bias_default", default))
    if isinstance(htf, dict):
        htf = htf.get("bias", default)
    htf = str(htf).upper()
    if htf == "AUTO":
        try:
            from core.mt5_data import get_htf_bias
            return get_htf_bias(symbol, cfg.get("htf_timeframe", "H1"))
        except Exception:
            return str(default).upper()
    return htf


def build_context(cfg, symbol, journal, session_name=None) -> Context:
    return Context(
        time=None,  # filled per-bar from candle time
        spread_pips=_live_spread(cfg, symbol),
        htf_bias=_live_htf(cfg, symbol),
        htf4_bias=str(cfg.get("htf4_bias", "NEUTRAL")).upper(),
        minutes_to_red_news=cfg.get("minutes_to_red_news"),
        balance=cfg.get("balance"),
        risk_percent=cfg.get("risk_percent", 0.5),
        pip_value_per_lot=cfg.get("pip_value_per_lot", 10.0),
        daily_losses=int(journal.data.get("daily_losses", 0)),
        signals_this_session=int(journal.data.get("signals_this_session", 0)),
        blocked=None,
    )


def scan_symbol(symbol, data_path, params, ctx_template, journal, cfg=None) -> dict:
    """Full rebuild O(n): MarketData once, Engine.step per bar, return last output."""
    if cfg is not None:
        try:
            candles = _load_symbol_candles(cfg, symbol)
        except Exception as e:
            print(str(e))
            return {"signal": "WAIT", "rejected_because": "no_data",
                    "notes": str(e), "_internal": {"stage": "IDLE"}}
    else:
        candles = load_candles(data_path)
    md = MarketData(candles, params)
    eng = Engine(params, symbol=symbol)
    last = None
    for i in range(len(candles)):
        if stop_requested():
            break
        ctx = copy.copy(ctx_template)
        ctx.time = candles[i].time
        ctx.daily_losses = int(journal.data.get("daily_losses", 0))
        ctx.signals_this_session = int(journal.data.get("signals_this_session", 0))
        if journal.has_open(symbol):
            ctx.blocked = "open_position"
        last = eng.step(md, i, ctx)
        last["_meta_bar"] = {"index": i, "time": candles[i].time}
    # strip helper before returning
    return last


def settle_open_positions(cfg, journal, broker):
    """Check latest bar of each symbol against open SL/TP (paper settlement)."""
    pip_cache = {}
    for symbol, pos in list(journal.data.get("open", {}).items()):
        try:
            candles = _load_symbol_candles(cfg, symbol)
        except Exception:
            continue
        bar = candles[-1]
        pip = pip_cache.setdefault(symbol, pip_size_for(symbol))
        direction = pos["direction"]
        hit_sl = hit_tp = False
        if direction == "BUY":
            hit_sl = bar.low <= pos["sl"]
            hit_tp = bar.high >= pos["tp"]
        else:
            hit_sl = bar.high >= pos["sl"]
            hit_tp = bar.low <= pos["tp"]
        # SL has priority (conservative, same as backtest)
        if hit_sl:
            pips = -abs(pos["entry"] - pos["sl"]) / pip
            journal.register_close(symbol, "SL", round(pips, 2))
            broker.close_position(pos["ticket"], bar.close, bar.time,
                                  pips=round(pips, 2), exit_type="SL", symbol=symbol)
            print(f"[{symbol}] SL hit: {pips:.1f} pips @ {bar.time}")
        elif hit_tp:
            pips = abs(pos["tp"] - pos["entry"]) / pip
            journal.register_close(symbol, "TP", round(pips, 2))
            broker.close_position(pos["ticket"], bar.close, bar.time,
                                  pips=round(pips, 2), exit_type="TP", symbol=symbol)
            print(f"[{symbol}] TP hit: +{pips:.1f} pips @ {bar.time}")


def run_once(cfg, params, journal, broker, armed: bool, log_path: str) -> int:
    symbols = cfg.get("symbols", [])
    results = []
    for symbol in symbols:
        if stop_requested():
            print("STOP file detected — exiting between symbols.")
            break
        ctx_template = build_context(cfg, symbol, journal)
        out = scan_symbol(symbol, cfg.get("data", {}).get(symbol), params, ctx_template, journal, cfg)
        # remove internal helper, strip _internal keys starting with _ before execution
        out.pop("_meta_bar", None)
        signal = out.get("signal", "WAIT")
        entry_info = None
        if signal in ("BUY", "SELL"):
            ok, reason = journal.can_open(symbol)
            if not ok:
                entry_info = {"blocked_by_journal": reason}
                print(f"[{symbol}] {signal} blocked by journal: {reason}")
            elif not armed:
                entry_info = {"dry_run": True,
                              "would_place": out.get("trade")}
                print(f"[{symbol}] {signal} DRY-RUN (no --arm): "
                      f"entry={out['trade']['entry_price']} "
                      f"sl={out['trade']['stop_loss']} tp={out['trade']['take_profit']} "
                      f"conf={out.get('confidence')}/{out.get('confidence_score')}")
            else:
                t = out["trade"]
                res = broker.place_market(symbol, signal, t["entry_price"],
                                          t["stop_loss"], t["take_profit"],
                                          t.get("lot_size"), meta={"confidence": out.get("confidence")})
                journal.register_open(symbol, res["ticket"], signal,
                                      t["entry_price"], t["stop_loss"], t["take_profit"])
                entry_info = {"ticket": res["ticket"], "placed": True}
                print(f"[{symbol}] {signal} PLACED ticket={res['ticket']} "
                      f"entry={t['entry_price']} sl={t['stop_loss']} tp={t['take_profit']}")
        else:
            print(f"[{symbol}] WAIT — {out.get('rejected_because')}")
        # log JSONL (strip _internal before external sink)
        public = {k: v for k, v in out.items() if not k.startswith("_")}
        rec = {"symbol": symbol, "armed": armed, "result": public,
               "execution": entry_info}
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        results.append(rec)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="auto_trade/monitor.py")
    ap.add_argument("--config", required=False, default="auto_trade/config.json")
    ap.add_argument("--once", action="store_true", help="single dry-run/scan pass")
    ap.add_argument("--arm", default=None, help="must be exactly ARMED to place orders")
    ap.add_argument("--disarm", action="store_true", help="create STOP file and exit")
    ap.add_argument("--symbols", default=None, help="comma-separated symbol override")
    ap.add_argument("--mode", default=None, choices=["paper", "live"])
    args = ap.parse_args(argv)

    if args.disarm:
        os.makedirs(os.path.dirname(STOP_FILE) or ".", exist_ok=True)
        with open(STOP_FILE, "w", encoding="utf-8") as f:
            f.write("stopped by --disarm\n")
        print(f"STOP file created: {STOP_FILE}")
        return 0

    armed = (args.arm == "ARMED")
    if args.arm is not None and not armed:
        print(f"ERROR: --arm token must be exactly ARMED (got {args.arm!r}). Nothing placed.")
        return 2

    if not os.path.exists(args.config):
        print(f"ERROR: config not found: {args.config}\n"
              f"Copy auto_trade/config.example.json -> {args.config} first.")
        return 2
    cfg = load_config(args.config)
    if args.symbols:
        cfg["symbols"] = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if args.mode:
        cfg["mode"] = args.mode

    mode = str(cfg.get("mode", "paper")).lower()
    if mode == "live" and not armed:
        print("mode=live but no --arm ARMED — running as dry-run only.")

    params = Params.from_dict(cfg.get("params", {}))
    params.validate()

    state_dir = cfg.get("state_dir", STATE_DIR_DEFAULT)
    os.makedirs(state_dir, exist_ok=True)
    journal = Journal(path=os.path.join(state_dir, "journal.json"),
                      max_daily_losses=int(cfg.get("max_daily_losses", 3)),
                      max_total_losses=int(cfg.get("max_total_losses", 6)),
                      max_signals_per_session=int(cfg.get("max_signals_per_session", 3)))
    log_path = os.path.join(state_dir, "monitor.jsonl")

    if mode == "live":
        broker = MT5Broker() if armed else PaperBroker(state_dir=state_dir)
        if not armed:
            print("WARNING: live config without --arm -> PaperBroker dry-run only.")
    else:
        try:
            first_sym = (cfg.get("symbols") or ["EURUSD"])[0]
            init_spread = _live_spread(cfg, first_sym)
        except Exception:
            init_spread = 0.6
        broker = PaperBroker(state_dir=state_dir, spread_pips=init_spread)

    if stop_requested():
        print(f"STOP file exists ({STOP_FILE}) — remove it to resume. Exiting.")
        return 3

    # settle any open paper positions on latest bar before new signals
    if armed:
        try:
            settle_open_positions(cfg, journal, broker)
        except Exception as e:  # never let settlement crash the loop
            print(f"settle error: {e}")

    if args.once or not armed:
        # single pass: dry-run or armed-once
        return run_once(cfg, params, journal, broker, armed, log_path)

    # armed continuous loop
    poll = int(cfg.get("poll_seconds", 60))
    print(f"ARMED loop started: mode={mode} symbols={cfg.get('symbols')} "
          f"poll={poll}s. STOP file: {STOP_FILE}")
    try:
        while True:
            if stop_requested():
                print("STOP file detected — armed loop exiting.")
                break
            settle_open_positions(cfg, journal, broker)
            run_once(cfg, params, journal, broker, True, log_path)
            for _ in range(poll):
                if stop_requested():
                    break
                time.sleep(1)
    except KeyboardInterrupt:
        print("KeyboardInterrupt — armed loop stopped.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
