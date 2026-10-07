"""Live market data from MetaTrader 5 terminal (same machine).

All project data comes from here — no more synthetic CSV for analysis.
CSV files in data/ are only a cache/snapshot of MT5.

Functions:
    fetch_candles(symbol, timeframe, bars) -> List[Candle]
    get_spread_pips(symbol) -> float
    get_htf_bias(symbol, htf_timeframe="H1") -> BULLISH | BEARISH | NEUTRAL
    save_csv(candles, path)
"""
from __future__ import annotations

import datetime
from typing import List

from .config import pip_size_for
from .market import Candle


def _mt5():
    try:
        import MetaTrader5 as mt5
    except ImportError as e:
        raise RuntimeError(
            "MetaTrader5 package not installed. Run `pip install MetaTrader5`."
        ) from e
    return mt5


def _tf_map():
    mt5 = _mt5()
    return {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }


def ensure_init() -> None:
    mt5 = _mt5()
    if not mt5.initialize():
        raise RuntimeError(f"MT5 initialize() failed: {mt5.last_error()}")


def fetch_candles(symbol: str, timeframe: str = "M5", bars: int = 1000,
                  start_pos: int = 0) -> List[Candle]:
    """Fetch last `bars` CLOSED candles from MT5. The forming bar is dropped."""
    mt5 = _mt5()
    ensure_init()
    tf_map = _tf_map()
    tf = tf_map.get(timeframe.upper())
    if tf is None:
        raise ValueError(f"unsupported timeframe: {timeframe} (use M1/M5/M15/H1/H4/D1)")
    if not mt5.symbol_select(symbol, True):
        raise RuntimeError(f"MT5: symbol_select failed for {symbol}: {mt5.last_error()}")
    # +1 so we can drop the still-forming bar
    rates = mt5.copy_rates_from_pos(symbol, tf, start_pos, bars + 1)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"MT5 copy_rates failed for {symbol}: {mt5.last_error()}")
    out: List[Candle] = []
    # drop last (forming) bar
    for idx, r in enumerate(rates[:-1]):
        ts = datetime.datetime.fromtimestamp(
            int(r["time"]), tz=datetime.timezone.utc).isoformat()
        vol = float(r["tick_volume"]) if "tick_volume" in rates.dtype.names else 0.0
        out.append(Candle(
            i=idx,
            time=ts,
            open=float(r["open"]),
            high=float(r["high"]),
            low=float(r["low"]),
            close=float(r["close"]),
            volume=vol,
        ))
    # re-index (already 0..n-1)
    return out


def get_spread_pips(symbol: str) -> float:
    mt5 = _mt5()
    ensure_init()
    info = mt5.symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"MT5: no symbol_info for {symbol}")
    tick = mt5.symbol_info_tick(symbol)
    pip = pip_size_for(symbol)
    if tick is not None and tick.ask and tick.bid:
        return round((tick.ask - tick.bid) / pip, 2)
    # fallback: static spread in points
    point = info.point or pip / 10.0
    return round((info.spread * point) / pip, 2)


def get_htf_bias(symbol: str, htf_timeframe: str = "H1", ma_period: int = 50) -> str:
    """Simple HTF bias from MT5 HTF closes vs SMA.

    BULLISH if last close > SMA(ma), BEARISH if <, else NEUTRAL.
    This is a data feed (not a manual guess) for filter F3.
    """
    candles = fetch_candles(symbol, htf_timeframe, max(ma_period + 5, 60))
    closes = [c.close for c in candles]
    if len(closes) < ma_period:
        return "NEUTRAL"
    sma = sum(closes[-ma_period:]) / ma_period
    last = closes[-1]
    tol = (max(closes[-ma_period:]) - min(closes[-ma_period:])) * 0.02
    if last > sma + tol:
        return "BULLISH"
    if last < sma - tol:
        return "BEARISH"
    return "NEUTRAL"


def save_csv(candles: List[Candle], path: str) -> None:
    import os
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("time,open,high,low,close,volume\n")
        for c in candles:
            f.write(f"{c.time},{c.open:.5f},{c.high:.5f},{c.low:.5f},{c.close:.5f},{c.volume:g}\n")
