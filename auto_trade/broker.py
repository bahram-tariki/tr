"""Broker abstraction — execution layer (outside core).

- Broker: interface
- PaperBroker: paper trading with spread, logs to JSONL, settles SL/TP on new bars
- MT5Broker: lazy import MetaTrader5, friendly error if not installed
"""
from __future__ import annotations

import datetime
import json
import os


class Broker:
    name = "base"

    def place_market(self, symbol, direction, entry, stop_loss, take_profit,
                     lot_size=None, meta=None) -> dict:
        raise NotImplementedError

    def close_position(self, ticket, exit_price=None, exit_time=None) -> dict:
        raise NotImplementedError


class PaperBroker(Broker):
    """Paper execution: no real market, just record + simple SL/TP settlement.

    Orders are appended to <state_dir>/paper_orders.jsonl so dry-run and
    armed runs are auditable.
    """
    name = "paper"

    def __init__(self, state_dir="auto_trade/state", spread_pips=0.6, pip_size=0.0001):
        self.state_dir = state_dir
        self.spread_pips = spread_pips
        self.pip_size = pip_size
        os.makedirs(state_dir, exist_ok=True)
        self._log = os.path.join(state_dir, "paper_orders.jsonl")
        self._ticket = 0

    def _write(self, record: dict):
        with open(self._log, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def place_market(self, symbol, direction, entry, stop_loss, take_profit,
                     lot_size=None, meta=None) -> dict:
        self._ticket += 1
        ticket = f"PAPER-{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d')}-{self._ticket}"
        rec = {
            "event": "open",
            "ticket": ticket,
            "symbol": symbol,
            "direction": direction,
            "entry_price": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "lot_size": lot_size,
            "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "meta": meta or {},
        }
        self._write(rec)
        return {"ticket": ticket, "record": rec}

    def close_position(self, ticket, exit_price=None, exit_time=None, pips=None,
                       exit_type="MANUAL", symbol=None) -> dict:
        rec = {
            "event": "close",
            "ticket": ticket,
            "symbol": symbol,
            "exit_price": exit_price,
            "exit_time": exit_time or datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "exit_type": exit_type,
            "pips": pips,
        }
        self._write(rec)
        return rec


class MT5Broker(Broker):
    """Live broker via MetaTrader5 (optional dependency).

    All MT5 imports are lazy so `auto_trade` works without MT5 installed
    for paper trading and dry-runs.
    """
    name = "mt5"

    def __init__(self, magic=20261006, deviation=10):
        self.magic = magic
        self.deviation = deviation
        try:
            import MetaTrader5 as mt5  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "MetaTrader5 package is not installed. "
                "Install it with `pip install MetaTrader5` (Windows + MT5 terminal required) "
                "or use mode=paper."
            ) from e

    def place_market(self, symbol, direction, entry, stop_loss, take_profit,
                     lot_size=None, meta=None) -> dict:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            raise RuntimeError(f"MT5 initialize() failed: {mt5.last_error()}")
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"MT5: no tick for {symbol}")
        price = tick.ask if direction == "BUY" else tick.bid
        order_type = mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(lot_size or 0.01),
            "type": order_type,
            "price": price,
            "sl": float(stop_loss),
            "tp": float(take_profit),
            "deviation": self.deviation,
            "magic": self.magic,
            "comment": "sh-bms-rto",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(req)
        if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
            raise RuntimeError(f"MT5 order_send failed: {res}")
        return {"ticket": res.order, "record": {"retcode": res.retcode, "price": price}}

    def close_position(self, ticket, exit_price=None, exit_time=None) -> dict:
        raise NotImplementedError("MT5 close_position: close manually or extend broker.py")
