"""پارامترهای قابل تنظیم سیستم — معادل بخش ۱۲ سند SPEC-v2.

همه مقادیر پیش‌فرض دقیقاً از جدول پارامترهای سند آمده‌اند.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, fields


def pip_size_for(symbol: str) -> float:
    """اندازه یک پیپ بر اساس نماد."""
    s = (symbol or "").upper()
    if "XAU" in s or "XAG" in s or "GOLD" in s or "SILVER" in s:
        return 0.1
    if "JPY" in s:
        return 0.01
    return 0.0001


def digits_for(pip: float) -> float:
    """تعداد ارقام قیمت متناسب با pip_size."""
    if abs(pip - 0.01) < 1e-9:
        return 3
    if abs(pip - 0.1) < 1e-9:
        return 2
    return 5


@dataclass
class Params:
    # ---------- کلی ----------
    timeframe: str = "M5"
    # ---------- سویینگ ----------
    lookback: int = 2
    # ---------- SH ----------
    min_sweep_pips: float = 0.5
    max_sweep_pips: float = 10.0
    # ---------- BMS ----------
    structure_lookback: int = 10
    max_bms_delay_candles: int = 15
    displacement_factor: float = 1.0
    min_body_ratio: float = 0.60
    # ---------- نواحی (OB / FVG) ----------
    ob_zone_mode: str = "full_candle"  # full_candle (پیش‌فرض v2.2) | body
    ob_lookback: int = 20
    max_ob_age_candles: int = 50
    max_ob_mitigations: int = 1
    max_ob_size_pips: float = 50.0  # XAU fix: was 15 too small (1.5$), gold OB often 3-5$ => 30-50 pip
    max_ob_distance_pips: float = 150.0  # was 60 (6$ for gold) too tight
    min_fvg_size_pips: float = 2.0
    max_fvg_size_pips: float = 25.0
    require_fresh_fvg: bool = True
    # ---------- RTO ----------
    rto_mode: str = "strict"            # strict | relaxed
    rto_fib_low: float = 0.500
    rto_fib_high: float = 0.618
    allow_fib_fallback: bool = False    # در حالت strict = False
    # ---------- زمان / انقضا ----------
    max_wait_candles: int = 30
    max_total_setup_candles: int = 45
    # ---------- خروج / ریسک ----------
    sl_buffer_pips: float = 2.0
    invalidation_buffer_pips: float = 1.0
    rr_target: float = 2.0
    max_risk_pips: float = 80.0  # XAU fix: was 25 (2.5$) too small, gold risk often 5-8$ => 50-80 pip
    min_risk_pips: float = 8.0
    # ---------- فیلترها ----------
    max_spread_pips: float = 4.0  # XAU spread often 2-3 pip
    min_atr_pips: float = 5.0
    max_atr_pips: float = 100.0  # XAU ATR 20-60 pip normal, was 25 too small
    max_daily_losses: int = 3
    risk_per_trade_percent: float = 0.5
    only_trade_with_htf: bool = True
    allow_neutral_htf: bool = False
    news_buffer_minutes: float = 30.0
    max_signals_per_session: int = 3
    max_hold_candles: int = 200
    # ---------- امتیازدهی ----------
    equal_level_tolerance_pips: float = 1.0
    score_high_min: int = 75
    score_medium_min: int = 50

    # ------------------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict) -> "Params":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in (data or {}).items() if k in names})

    def to_dict(self) -> dict:
        return asdict(self)


    def for_symbol(self, symbol: str) -> "Params":
        """برگرداندن کپی پارامترها متناسب با نماد - برای XAU فیلترها بازتر میشوند."""
        import copy
        p = copy.copy(self)
        s = (symbol or "").upper()
        if "XAU" in s or "GOLD" in s:
            # طلا نوسان بیشتری دارد، فیلترهای سایز و ریسک باید بازتر باشد
            p.max_ob_size_pips = max(p.max_ob_size_pips, 50.0)
            p.max_ob_distance_pips = max(p.max_ob_distance_pips, 150.0)
            p.max_risk_pips = max(p.max_risk_pips, 80.0)
            p.min_risk_pips = max(p.min_risk_pips, 8.0)
            p.max_spread_pips = max(p.max_spread_pips, 4.0)
            p.max_atr_pips = max(p.max_atr_pips, 100.0)
            p.min_atr_pips = max(p.min_atr_pips, 5.0)
        return p

    def validate(self) -> None:
        if self.rto_mode not in ("strict", "relaxed"):
            raise ValueError("rto_mode must be 'strict' or 'relaxed'")
        if self.ob_zone_mode not in ("body", "full_candle"):
            raise ValueError("ob_zone_mode must be 'body' or 'full_candle'")
        if not (0.0 < self.rto_fib_low < self.rto_fib_high < 1.0):
            raise ValueError("rto_fib_low/rto_fib_high must satisfy 0 < low < high < 1")
        if self.rr_target <= 0:
            raise ValueError("rr_target must be positive")
        if self.min_risk_pips >= self.max_risk_pips:
            raise ValueError("min_risk_pips must be < max_risk_pips")
        if self.rto_mode == "strict" and self.allow_fib_fallback:
            # در حالت STRICT طبق تصمیم کاربر: بدون جایگزین فیبوناچی
            self.allow_fib_fallback = False