"""موتور بک‌تست — بخش ۹ سند.

قواعد:
  * هیچ Look-Ahead: سویینگ فقط بعد از confirm_index دیده می‌شود.
  * اسپرد در Entry اعمال می‌شود و TP از Entry واقعی محاسبه می‌گردد (RR=2 می‌ماند).
  * اگر یک کندل هم SL و هم TP را لمس کند → SL اول لمس شده (محافظه‌کارانه).
"""
from __future__ import annotations

from collections import Counter
from typing import List, Optional

from .config import Params, pip_size_for, digits_for
from .engine import Engine, Context
from .market import Candle, MarketData
from .filters import session_of


def _settle(bar: Candle, trade: dict) -> Optional[dict]:
    if trade["direction"] == "BUY":
        if bar.low <= trade["stop_loss"]:
            return _close(trade, "SL", -trade["risk_pips"])
        if bar.high >= trade["take_profit"]:
            return _close(trade, "TP", trade["reward_pips"])
    else:
        if bar.high >= trade["stop_loss"]:
            return _close(trade, "SL", -trade["risk_pips"])
        if bar.low <= trade["take_profit"]:
            return _close(trade, "TP", trade["reward_pips"])
    return None


def _close(trade: dict, exit_type: str, pips: float, exit_price: float = None, exit_time=None) -> dict:
    trade = dict(trade)
    trade["exit_type"] = exit_type
    trade["pips"] = round(pips, 2)
    trade["exit_price"] = exit_price
    trade["exit_time"] = exit_time
    return trade


def run_backtest(
    candles: List[Candle],
    params: Optional[Params] = None,
    symbol: str = "EURUSD",
    contexts: Optional[List[Context]] = None,
    htf_bias: str = "NEUTRAL",
    spread_pips: float = 0.6,
    verbose: bool = False,
) -> dict:
    params = Params().for_symbol("XAUUSD")
    params.validate()
    pip = pip_size_for(symbol)
    digits = digits_for(pip)
    data = MarketData(candles, params)
    engine = Engine(params, symbol=symbol, pip_size=pip, digits=digits)

    if contexts is None:
        contexts = [
            Context(time=c.time, spread_pips=spread_pips, htf_bias=htf_bias)
            for c in candles
        ]

    trades: List[dict] = []
    open_trade: Optional[dict] = None
    rejections: Counter = Counter()
    signals_seen = Counter()
    coverage: Counter = Counter()

    for i in range(len(candles)):
        bar = candles[i]

        # ۱) تسویه پوزیشن باز با کندل جاری (اولویت با SL)
        if open_trade is not None and i > open_trade["entry_index"]:
            res = _settle(bar, open_trade)
            if res is not None:
                trades.append(res)
                open_trade = None
            elif i - open_trade["entry_index"] >= params.max_hold_candles:
                trades.append(
                    _close(
                        open_trade, "TIME", (bar.close - open_trade["entry_price"]) / pip
                        if open_trade["direction"] == "BUY"
                        else (open_trade["entry_price"] - bar.close) / pip,
                        exit_price=bar.close, exit_time=bar.time,
                    )
                )
                open_trade = None

        # ۲) اجرای State Machine
        out = engine.step(data, i, contexts[i])
        coverage[out.get("_internal", {}).get("stage", "?")] += 1
        if out["signal"] == "WAIT":
            if out.get("_internal", {}).get("dropped"):
                rejections[out["rejected_because"]] += 1
            continue

        signals_seen[out["signal"]] += 1
        if open_trade is not None:
            continue

        # ۳) اجرای سفارش با اسپرد
        if out["signal"] == "BUY":
            entry = bar.close + contexts[i].spread_pips * pip
            sl = out["trade"]["stop_loss"]
            risk = entry - sl
            tp = entry + params.rr_target * risk
            direction = "BUY"
        else:
            entry = bar.close - contexts[i].spread_pips * pip
            sl = out["trade"]["stop_loss"]
            risk = sl - entry
            tp = entry - params.rr_target * risk
            direction = "SELL"

        sname, _ = session_of(bar.time)
        open_trade = {
            "direction": direction,
            "symbol": symbol,
            "entry_time": bar.time,
            "entry_index": i,
            "entry_price": round(entry, digits),
            "stop_loss": round(sl, digits),
            "take_profit": round(tp, digits),
            "risk_pips": round(risk / pip, 2),
            "reward_pips": round(abs(tp - entry) / pip, 2),
            "confidence": out["confidence"],
            "confidence_score": out["confidence_score"],
            "session": sname,
            "entry_type": out["setup"]["entry_type"],
        }
        if verbose:
            print(f"  [{bar.time}] {direction} entry={entry:.5f} sl={sl:.5f} tp={tp:.5f}")

    # بستن پوزیشن باز در انتهای دیتا
    if open_trade is not None:
        last = candles[-1]
        pips = (
            (last.close - open_trade["entry_price"]) / pip
            if open_trade["direction"] == "BUY"
            else (open_trade["entry_price"] - last.close) / pip
        )
        trades.append(_close(open_trade, "EOD", pips, exit_price=last.close, exit_time=last.time))

    return _report(trades, rejections, signals_seen, len(candles), params, coverage)


def _report(trades, rejections, signals_seen, bars, params, coverage=None) -> dict:
    wins = [t for t in trades if t["pips"] > 0]
    losses = [t for t in trades if t["pips"] <= 0]
    gross_win = sum(t["pips"] for t in wins)
    gross_loss = abs(sum(t["pips"] for t in losses))

    # منحنی سرمایه و Drawdown
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for t in trades:
        equity += t["pips"]
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)

    def pct(x):
        return round(x, 2)

    def split(key):
        out = {}
        for t in trades:
            k = t.get(key)
            b = out.setdefault(k, {"trades": 0, "wins": 0, "pips": 0.0})
            b["trades"] += 1
            b["wins"] += 1 if t["pips"] > 0 else 0
            b["pips"] = pct(b["pips"] + t["pips"])
        for v in out.values():
            v["win_rate"] = round(100.0 * v["wins"] / v["trades"], 1) if v["trades"] else 0.0
        return out

    return {
        "summary": {
            "bars": bars,
            "signals": sum(signals_seen.values()),
            "signals_by_direction": dict(signals_seen),
            "trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(100.0 * len(wins) / len(trades), 1) if trades else 0.0,
            "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
            "expectancy_pips": round(sum(t["pips"] for t in trades) / len(trades), 2) if trades else 0.0,
            "net_pips": pct(sum(t["pips"] for t in trades)),
            "max_drawdown_pips": pct(max_dd),
            "best_pips": pct(max([t["pips"] for t in trades], default=0)),
            "worst_pips": pct(min([t["pips"] for t in trades], default=0)),
            "breakeven_win_rate": round(100.0 / (1.0 + params.rr_target), 1),
        },
        "by_session": split("session"),
        "by_confidence": split("confidence"),
        "by_entry_type": split("entry_type"),
        "rejections": dict(rejections.most_common()),
        "stage_coverage": dict(coverage or {}),
        "trades": trades,
    }
