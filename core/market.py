"""ساختار داده کندل و پیش‌حساب‌های بدون Look-Ahead.

نکته کلیدی: هر سویینگ فقط بعد از بسته‌شدن `lookback` کندل بعد از آن
«تأیید» می‌شود. بنابراین `confirm_index = index + lookback` ثبت می‌شود
و مصرف‌کننده فقط سویینگ‌هایی را می‌بیند که `confirm_index <= i` باشد.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import List, Optional, Tuple

from .config import Params


@dataclass
class Candle:
    i: int
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def bullish(self) -> bool:
        return self.close > self.open

    @property
    def bearish(self) -> bool:
        return self.close < self.open

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def rng(self) -> float:
        return self.high - self.low


# (kind, index, price, confirm_index)
Swing = Tuple[str, int, float, int]


class MarketData:
    """همه محاسبات قطعی بازار یک‌بار و در O(n) پیش‌محاسبه می‌شوند."""

    def __init__(self, candles: List[Candle], params: Params):
        if not candles:
            raise ValueError("candles is empty")
        self.candles = candles
        self.params = params
        n = len(candles)
        lb = max(1, int(params.lookback))

        # ---------------- swings ----------------
        swings: List[Swing] = []
        for i in range(lb, n - lb):
            h = candles[i].high
            lo = candles[i].low
            hi_ok = all(h > candles[i - d].high for d in range(1, lb + 1)) and all(
                h > candles[i + d].high for d in range(1, lb + 1)
            )
            lo_ok = all(lo < candles[i - d].low for d in range(1, lb + 1)) and all(
                lo < candles[i + d].low for d in range(1, lb + 1)
            )
            if hi_ok:
                swings.append(("high", i, h, i + lb))
            if lo_ok:
                swings.append(("low", i, lo, i + lb))
        swings.sort(key=lambda s: s[1])
        self.swings: List[Swing] = swings
        self._swing_indices: List[int] = [s[1] for s in swings]

        # آخرین سویینگ تأییدشده برای هر ایندکس (O(n))
        self._last_high: List[Optional[Swing]] = [None] * n
        self._last_low: List[Optional[Swing]] = [None] * n
        ptr = 0
        cur_h: Optional[Swing] = None
        cur_l: Optional[Swing] = None
        for i in range(n):
            while ptr < len(swings) and swings[ptr][3] <= i:
                if swings[ptr][0] == "high":
                    cur_h = swings[ptr]
                else:
                    cur_l = swings[ptr]
                ptr += 1
            self._last_high[i] = cur_h
            self._last_low[i] = cur_l

        # ---------------- true range / ATR ----------------
        self.tr: List[float] = []
        for i, c in enumerate(candles):
            if i == 0:
                self.tr.append(c.high - c.low)
            else:
                pc = candles[i - 1].close
                self.tr.append(max(c.high - c.low, abs(c.high - pc), abs(c.low - pc)))
        self._atr_cache: dict = {}

        # ---------------- FVG ----------------
        self.fvgs: List[dict] = []
        for i in range(0, n - 2):
            a, c3 = candles[i], candles[i + 2]
            if c3.low > a.high:
                self.fvgs.append(
                    {"dir": "bull", "lo": a.high, "hi": c3.low, "index": i + 1, "confirm": i + 2}
                )
            if c3.high < a.low:
                self.fvgs.append(
                    {"dir": "bear", "lo": c3.high, "hi": a.low, "index": i + 1, "confirm": i + 2}
                )
        self._fvg_confirms = [f["confirm"] for f in self.fvgs]

    # ------------------------------------------------------------------
    def last_high(self, i: int) -> Optional[Swing]:
        return self._last_high[i] if 0 <= i < len(self._last_high) else None

    def last_low(self, i: int) -> Optional[Swing]:
        return self._last_low[i] if 0 <= i < len(self._last_low) else None

    def last_swing_before(self, i: int, kind: str, max_index: int) -> Optional[Swing]:
        """آخرین سویینگ از نوع kind که هم تأییدشده تا i است و هم ایندکسش < max_index."""
        pos = bisect.bisect_left(self._swing_indices, max_index) - 1
        while pos >= 0:
            s = self.swings[pos]
            if s[0] == kind and s[3] <= i:
                return s
            pos -= 1
        return None

    def atr(self, i: int, period: int = 14) -> float:
        key = (i, period)
        if key in self._atr_cache:
            return self._atr_cache[key]
        start = max(0, i - period + 1)
        seg = self.tr[start : i + 1]
        val = sum(seg) / len(seg)
        self._atr_cache[key] = val
        return val

    def fvgs_upto(self, i: int, direction: str, limit: int = 40) -> List[dict]:
        """آخرین FVGهای تأییدشده تا کندل i در جهت دلخواه (بازه محدود)."""
        end = bisect.bisect_right(self._fvg_confirms, i)
        out: List[dict] = []
        for k in range(end - 1, max(-1, end - 1 - limit * 3), -1):
            f = self.fvgs[k]
            if f["dir"] != direction:
                continue
            out.append(f)
            if len(out) >= limit:
                break
        return out

    def other_equal_levels(
        self, i: int, kind: str, exclude_index: int, level: float, tol_price: float
    ) -> bool:
        """آیا سویینگ هم‌سطح دیگری (Equal Lows/Highs) در بازه اخیر هست؟"""
        lo_pos = bisect.bisect_left(self._swing_indices, i - self.params.structure_lookback * 4)
        hi_pos = bisect.bisect_left(self._swing_indices, i + 1)
        for k in range(hi_pos - 1, lo_pos - 1, -1):
            s = self.swings[k]
            if s[3] > i:
                continue
            if s[1] == exclude_index:
                continue
            if s[0] == kind and abs(s[2] - level) <= tol_price:
                return True
        return False
