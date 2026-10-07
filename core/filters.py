"""فیلترهای ایمنی — بخش ۶ سند (F1..F8 + جدول سشن)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from .config import Params

# پنجره‌های سشن بر اساس UTC (جدول ۶.۲ سند).
# mode: "block" = ممنوع | "trade" = آزاد | "high_only" = فقط با confidence بالا
SESSION_WINDOWS = [
    (0, 7, "Asia", "block"),
    (7, 12, "London", "trade"),
    (12, 16, "Overlap", "trade"),
    (16, 21, "NY_Late", "high_only"),
    (21, 24, "Rollover", "block"),
]

BLOCKED_SESSIONS = {"Asia", "Rollover"}


def parse_ts(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    s = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def session_of(ts) -> Tuple[str, str]:
    """(نام سشن، حالت) — نامشخص → ("Unknown", "trade")."""
    dt = parse_ts(ts)
    if dt is None:
        return ("Unknown", "trade")
    hour = dt.utctimetuple().tm_hour
    for start, end, name, mode in SESSION_WINDOWS:
        if start <= hour < end:
            return (name, mode)
    return ("Unknown", "trade")


def outer_filters(ctx, params: Params) -> Optional[str]:
    """فیلترهای اجباری قبل از اجرای State Machine. خروجی: دلیل رد یا None."""
    if ctx.minutes_to_red_news is not None:
        if ctx.minutes_to_red_news <= params.news_buffer_minutes:
            return "red_folder_news"
    name, mode = session_of(ctx.time)
    if mode == "block":
        return "out_of_session"
    if ctx.spread_pips is not None and ctx.spread_pips > params.max_spread_pips:
        return "spread_too_wide"
    if ctx.daily_losses is not None and ctx.daily_losses >= params.max_daily_losses:
        return "daily_loss_limit"
    if ctx.signals_this_session is not None and ctx.signals_this_session >= params.max_signals_per_session:
        return "session_signal_limit"
    if ctx.blocked:
        return ctx.blocked
    return None


def htf_allows(direction: str, ctx, params: Params) -> bool:
    """F3 — فقط در جهت روند H1 (پیش‌فرض اجباری)."""
    if not params.only_trade_with_htf:
        return True
    bias = (ctx.htf_bias or "NEUTRAL").upper()
    if direction == "bull":
        if bias == "BULLISH":
            return True
        return params.allow_neutral_htf and bias == "NEUTRAL"
    if bias == "BEARISH":
        return True
    return params.allow_neutral_htf and bias == "NEUTRAL"
