"""Journal — risk guards + persistence (auto_trade/state/journal.json).

Rules enforced here (mirrors SPEC F6/F7 + SKILL section 7):
- one open position per symbol
- direction locked until that position closes
- daily loss cap (max_daily_losses) and total loss cap (max_total_losses)
- count of signals per session (max_signals_per_session)
"""
from __future__ import annotations

import datetime
import json
import os


def _today_utc():
    return datetime.datetime.now(datetime.timezone.utc).date().isoformat()


class Journal:
    def __init__(self, path="auto_trade/state/journal.json",
                 max_daily_losses=3, max_total_losses=6,
                 max_signals_per_session=3):
        self.path = path
        self.max_daily_losses = max_daily_losses
        self.max_total_losses = max_total_losses
        self.max_signals_per_session = max_signals_per_session
        self.data = {
            "open": {},               # symbol -> {ticket, direction, entry, sl, tp, time}
            "daily_date": _today_utc(),
            "daily_losses": 0,
            "total_losses": 0,
            "signals_this_session": 0,
            "session_name": None,
            "closed": [],
        }
        self.load()

    # ---------- persistence ----------
    def load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self.data.update(saved)
            except (json.JSONDecodeError, OSError):
                pass
        # new UTC day -> reset daily counter
        if self.data.get("daily_date") != _today_utc():
            self.data["daily_date"] = _today_utc()
            self.data["daily_losses"] = 0
            self.data["signals_this_session"] = 0

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    # ---------- guards ----------
    def can_open(self, symbol) -> tuple:
        """Return (ok, reason)."""
        if symbol in self.data["open"]:
            return False, "open_position"
        if self.data["daily_losses"] >= self.max_daily_losses:
            return False, "daily_loss_limit"
        if self.data["total_losses"] >= self.max_total_losses:
            return False, "max_total_losses"
        if self.data["signals_this_session"] >= self.max_signals_per_session:
            return False, "session_signal_limit"
        return True, ""

    def register_open(self, symbol, ticket, direction, entry, sl, tp):
        self.data["open"][symbol] = {
            "ticket": ticket,
            "direction": direction,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        self.data["signals_this_session"] += 1
        self.save()

    def register_close(self, symbol, exit_type, pips):
        pos = self.data["open"].pop(symbol, None)
        if exit_type == "SL":
            self.data["daily_losses"] += 1
            self.data["total_losses"] += 1
        self.data["closed"].append({"symbol": symbol, "exit": exit_type,
                                    "pips": pips, "position": pos})
        self.save()
        return pos

    def has_open(self, symbol) -> bool:
        return symbol in self.data["open"]
