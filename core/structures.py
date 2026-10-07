"""ساخت نواحی: Order Block ، FVG ، Leg و ناحیه RTO (بخش ۱ و ۲ سند).

قانون نهایی RTO (حالت STRICT — نسخه ۲.۲):

    اعتبارسنجی:  (OB ∪ FVG)  ∩  [ fib 50% .. 61.8% ]  ≠  ∅   (فقط فیلتر کیفی)
    ناحیه ورود:  خودِ OB به حالت full_candle ([low, high]) یا خودِ FVG
    شرط لمس:     ویک کندل باید خودِ هم‌پوشانی دقیق را لمس کند
    تریگر:       کلوز کندل هم‌جهت داخل ناحیه‌ی ورود

یعنی فیبو «فیلتر کیفی» است (ناحیه باید در Discount باشد)، نه اینکه عرضِ باکس
ورود را تعیین کند. اگر ناحیه ورود را هم‌پوشانی می‌گرفتیم، باکس ۰٫۵ پیپی
می‌شد و عملاً هیچ تریگری ثبت نمی‌شد (۰ سیگنال از ۶۲ فرصت در تست ۳۰۰۰ کندلی).
OB نیز «آخرین کندل مخالف قبل از حرکت BMS» است و بالاتر از کف موج (SH)
قرار می‌گیرد، پس هم‌پوشانی‌اش با فیبو رخ می‌دهد.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .config import Params
from .market import Candle, MarketData


@dataclass
class Zone:
    kind: str            # "ob" | "fvg" | "fib"
    lo: float
    hi: float
    index: int           # ایندکس کندل سازنده ناحیه
    retr_shallow: float  # عمق ریتریسمنت نزدیک‌ترین لبه ناحیه ورود
    mitigations: int = 0
    fresh: bool = True
    has_both: bool = False   # هم OB و هم FVG در ناحیه فیبو بودند
    fallback: bool = False
    overlap_lo: float = None  # هم‌پوشانی با پنجره فیبو (فقط گزارش/اعتبار)
    overlap_hi: float = None

    @property
    def size_pips(self) -> float:
        return (self.hi - self.lo)


def retracement(price: float, leg_low: float, leg_high: float, direction: str) -> Optional[float]:
    rng = leg_high - leg_low
    if rng <= 0:
        return None
    if direction == "bull":
        return (leg_high - price) / rng
    return (price - leg_low) / rng


def fib_band(leg_low: float, leg_high: float, direction: str, params: Params) -> Optional[tuple]:
    """(lo, hi) قیمتی ناحیه فیبو — برای BUY: بالاتر = ریتریسمنت کمتر."""
    rng = leg_high - leg_low
    if rng <= 0:
        return None
    if direction == "bull":
        lo = leg_high - params.rto_fib_high * rng
        hi = leg_high - params.rto_fib_low * rng
    else:
        lo = leg_low + params.rto_fib_low * rng
        hi = leg_low + params.rto_fib_high * rng
    return (lo, hi)


def intersect(a_lo: float, a_hi: float, b_lo: float, b_hi: float) -> Optional[tuple]:
    lo = max(a_lo, b_lo)
    hi = min(a_hi, b_hi)
    return (lo, hi) if lo <= hi else None


# ----------------------------------------------------------------------
def ob_candidates(
    candles: List[Candle],
    data: MarketData,
    bms_index: int,
    sh_index: int,
    direction: str,
    leg_low: float,
    leg_high: float,
    params: Params,
    pip: float,
    current_index: int,
) -> List[dict]:
    """کندل‌های مخالف قبل از حرکت BMS که با ناحیه فیبو هم‌پوشانی دارند.

    اولین مورد (نزدیک‌ترین به BMS) به عنوان OB اصلی انتخاب می‌شود.
    """
    band = fib_band(leg_low, leg_high, direction, params)
    if band is None:
        return []
    out: List[dict] = []
    start = max(sh_index, bms_index - params.ob_lookback)
    for j in range(bms_index - 1, start - 1, -1):
        c = candles[j]
        if direction == "bull" and not c.bearish:
            continue
        if direction == "bear" and not c.bullish:
            continue

        if params.ob_zone_mode == "full_candle" or c.body < 1 * pip:
            z_lo, z_hi = c.low, c.high
        else:
            z_lo, z_hi = min(c.open, c.close), max(c.open, c.close)

        zone = intersect(z_lo, z_hi, band[0], band[1])
        if zone is None:
            continue  # این کندل در ناحیه فیبو نیست → سراغ کندل قبلی می‌رویم

        # قیدهای اعتبار
        age = current_index - j
        size_pips = (z_hi - z_lo) / pip
        mid = (z_lo + z_hi) / 2
        dist_pips = abs(candles[current_index].close - mid) / pip
        if age > params.max_ob_age_candles:
            continue
        if size_pips > params.max_ob_size_pips:
            continue
        if dist_pips > params.max_ob_distance_pips:
            continue

        mitig = 0
        for k in range(bms_index + 1, current_index):
            ck = candles[k]
            if direction == "bull" and ck.low <= z_hi:
                mitig += 1
            if direction == "bear" and ck.high >= z_lo:
                mitig += 1
        if mitig > params.max_ob_mitigations:
            continue

        out.append(
            {
                # ناحیه ورود = خودِ OB (کل کندل، v2.2) — فیبو فقط «کیفیت» است، نه عرض ورود
                "lo": z_lo,
                "hi": z_hi,
                # هم‌پوشانی با فیبو = شرط اعتبارسنجی (STRICT)
                "overlap_lo": zone[0],
                "overlap_hi": zone[1],
                "index": j,
                "mitigations": mitig,
                "fresh": mitig == 0,
            }
        )
    return out


def fvg_candidates(
    data: MarketData,
    candles: List[Candle],
    bms_index: int,
    sh_index: int,
    direction: str,
    leg_low: float,
    leg_high: float,
    params: Params,
    pip: float,
    current_index: int,
) -> List[dict]:
    band = fib_band(leg_low, leg_high, direction, params)
    if band is None:
        return []
    out: List[dict] = []
    for f in data.fvgs_upto(current_index, direction):
        if f["index"] < sh_index:
            continue
        size_pips = (f["hi"] - f["lo"]) / pip
        if size_pips < params.min_fvg_size_pips or size_pips > params.max_fvg_size_pips:
            continue
        zone = intersect(f["lo"], f["hi"], band[0], band[1])
        if zone is None:
            continue
        mitig = 0
        for k in range(f["confirm"] + 1, current_index):
            ck = candles[k]
            if direction == "bull" and ck.low <= f["lo"]:
                mitig += 1
            if direction == "bear" and ck.high >= f["hi"]:
                mitig += 1
        if params.require_fresh_fvg and mitig > 0:
            continue
        out.append(
            {
                # ناحیه ورود = خودِ FVG
                "lo": f["lo"],
                "hi": f["hi"],
                # هم‌پوشانی با فیبو = شرط اعتبارسنجی
                "overlap_lo": zone[0],
                "overlap_hi": zone[1],
                "index": f["index"],
                "mitigations": mitig,
                "fresh": mitig == 0,
            }
        )
    return out


def build_zone(
    data: MarketData,
    i: int,
    direction: str,
    sh_index: int,
    bms_index: int,
    leg_low: float,
    leg_high: float,
    params: Params,
    pip: float,
) -> Optional[Zone]:
    """ناحیه ورود = خودِ OB (full_candle) یا خودِ FVG، به شرط هم‌پوشانی با fib[0.5 .. 0.618] (STRICT)."""
    candles = data.candles
    band = fib_band(leg_low, leg_high, direction, params)
    if band is None:
        return None

    obs = ob_candidates(
        candles, data, bms_index, sh_index, direction, leg_low, leg_high, params, pip, i
    )
    fvgs = fvg_candidates(
        data, candles, bms_index, sh_index, direction, leg_low, leg_high, params, pip, i
    )

    if obs:
        z = obs[0]
        return Zone(
            kind="ob",
            lo=z["lo"],
            hi=z["hi"],
            index=z["index"],
            retr_shallow=_shallow_retr(z["hi"] if direction == "bull" else z["lo"], leg_low, leg_high, direction),
            mitigations=z["mitigations"],
            fresh=z["fresh"],
            has_both=bool(fvgs),
            overlap_lo=z["overlap_lo"],
            overlap_hi=z["overlap_hi"],
        )
    if fvgs:
        z = fvgs[0]
        return Zone(
            kind="fvg",
            lo=z["lo"],
            hi=z["hi"],
            index=z["index"],
            retr_shallow=_shallow_retr(z["hi"] if direction == "bull" else z["lo"], leg_low, leg_high, direction),
            mitigations=z["mitigations"],
            fresh=z["fresh"],
            has_both=False,
            overlap_lo=z["overlap_lo"],
            overlap_hi=z["overlap_hi"],
        )

    # حالت RELAXED (یا fallback اختیاری): خود ناحیه فیبو
    if params.allow_fib_fallback or params.rto_mode == "relaxed":
        return Zone(
            kind="fib",
            lo=band[0],
            hi=band[1],
            index=bms_index,
            retr_shallow=params.rto_fib_low,
            mitigations=0,
            fresh=True,
            has_both=False,
            fallback=True,
        )
    return None


def _shallow_retr(price: float, leg_low: float, leg_high: float, direction: str) -> float:
    r = retracement(price, leg_low, leg_high, direction)
    return 0.0 if r is None else r
