"""مدل امتیازدهی Confidence — بخش ۷ سند."""
from __future__ import annotations

from typing import Tuple

from .config import Params
from .structures import Zone


def score_signal(
    *,
    direction: str,
    ctx,
    params: Params,
    zone: Zone,
    displacement_ratio: float,
    risk_pips: float,
    session_name: str,
) -> Tuple[int, str, dict]:
    """(امتیاز, برچسب, جزئیات) — برچسب: High | Medium | Low."""
    s = 0
    det = {}

    want = "BULLISH" if direction == "bull" else "BEARISH"
    if (ctx.htf_bias or "").upper() == want:
        s += 25
        det["htf_H1"] = 25
    if (ctx.htf4_bias or "").upper() == want:
        s += 15
        det["htf_H4_D1"] = 15

    pool = (ctx.sweep_pool_hint or "").lower()
    if pool in ("equal_lows", "equal_highs", "pdl", "pdh",
                "asian_range_low", "asian_range_high", "eql", "eqh"):
        s += 15
        det["liquidity_pool"] = 15

    if displacement_ratio >= 1.5:
        s += 15
        det["displacement"] = 15

    if zone.has_both:
        s += 10
        det["ob_fvg_overlap"] = 10

    if zone.kind == "ob" and zone.fresh:
        s += 10
        det["fresh_ob"] = 10

    if session_name == "Overlap":
        s += 10
        det["session_overlap"] = 10

    if params.rto_mode == "strict" and not zone.fallback and zone.retr_shallow >= params.rto_fib_low:
        # کل ناحیه ورود داخل Discount است (هم‌پوشانی با ۵۰٪–۶۱٫۸٪ قبلاً تأیید شده)
        s += 10
        det["discount_placement"] = 10

    if 8.0 <= risk_pips <= 20.0:
        s += 5
        det["risk_sweet_spot"] = 5

    if zone.fallback:
        s -= 10
        det["fib_fallback_penalty"] = -10

    if s >= params.score_high_min:
        label = "High"
    elif s >= params.score_medium_min:
        label = "Medium"
    else:
        label = "Low"
    return s, label, det
