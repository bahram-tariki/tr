from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .config import Params, pip_size_for, digits_for
from .market import Candle, MarketData
from .structures import build_zone, retracement, Zone
from .filters import outer_filters, htf_allows, session_of
from .confidence import score_signal

IDLE = "IDLE"
SH_CONFIRMED = "SH_CONFIRMED"
BMS_CONFIRMED = "BMS_CONFIRMED"
IN_ZONE_WAIT = "IN_ZONE_WAIT"
TURTLE_SOUP_CONFIRMED = "TURTLE_SOUP_CONFIRMED"  # ✅ FIX: ستاپ مستقل ترتل سوپ

NOTES = {
    "insufficient_data": "Not enough closed candles to evaluate the setup.",
    "no_sh_detected": "No valid stop hunt (liquidity sweep) detected.",
    "no_reference_swing": "No confirmed reference swing available for BMS.",
    "no_bms_within_max_delay": "Stop hunt detected but BMS did not confirm in time.",
    "no_valid_zone": "No Order Block / FVG intersecting the 50%-61.8% retracement zone.",
    "zone_not_reached": "Price did not return to the RTO zone within the allowed window.",
    "invalidated": "Setup invalidated by a candle closing beyond the sweep level.",
    "expired": "Setup expired before the entry trigger.",
    "risk_too_small": "Risk is below the minimum pip threshold (spread/noise).",
    "risk_too_large": "Risk exceeds the maximum pip limit for scalping.",
    "htf_filter": "Signal direction is against the H1 trend filter.",
    "low_confidence": "Confidence score below the tradeable threshold.",
    "atr_out_of_range": "ATR outside the allowed volatility window.",
    "session_signal_limit": "Maximum number of signals this session already used.",
    "red_folder_news": "Red folder news inside the news buffer window.",
    "out_of_session": "Outside the allowed London / New York session window.",
    "spread_too_wide": "Spread above the maximum allowed value.",
    "daily_loss_limit": "Daily loss limit reached.",
    "conflicting_signals": "Valid BUY and SELL setups on the same candle.",
    "blocked": "Trading blocked by the execution layer.",
    "waiting": "Setup in progress — waiting for the next stage.",
    "open_position": "An open position already exists for this symbol.",
    "turtle_soup_triggered": "Turtle Soup reversal confirmed after liquidity sweep.",
}

# دلایلی که یک ستاپِ شروع‌شده را «ریخته‌اند» (برای آمار بک‌تست)
DROP_REASONS = {
    "no_bms_within_max_delay", "no_valid_zone", "zone_not_reached", "invalidated",
    "expired", "risk_too_small", "risk_too_large", "htf_filter", "low_confidence",
    "atr_out_of_range", "conflicting_signals", "no_reference_swing",
}


@dataclass
class Context:
    """اطلاعات لحظه‌ای که مدل/کاربر فراهم می‌کند (فیلترها و امتیازدهی)."""
    time: Optional[str] = None
    spread_pips: float = 0.0
    htf_bias: str = "NEUTRAL"          # BULLISH | BEARISH | NEUTRAL
    htf4_bias: str = "NEUTRAL"
    minutes_to_red_news: Optional[float] = None
    sweep_pool_hint: Optional[str] = None
    balance: Optional[float] = None
    risk_percent: Optional[float] = None
    pip_value_per_lot: Optional[float] = 10.0
    daily_losses: int = 0
    signals_this_session: int = 0
    blocked: Optional[str] = None


class Engine:
    def __init__(self, params: Optional[Params] = None, symbol: str = "EURUSD",
                 pip_size: Optional[float] = None, digits: Optional[int] = None):
        self.params = params or Params()
        self.params.validate()
        self.symbol = symbol
        self.pip = pip_size or pip_size_for(symbol)
        self.digits = digits if digits is not None else digits_for(self.pip)
        self.reset()

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self.stage = IDLE
        self.direction: Optional[str] = None      # "bull" | "bear"
        self.sh_index: Optional[int] = None
        self.sweep_level: Optional[float] = None  # L یا H سویینگ مرجع
        self.sweep_price: Optional[float] = None  # کف/سقف شکارشده
        self.sweep_depth_pips: float = 0.0
        self.pool: str = "swing"
        self.ref_level: Optional[float] = None    # سطح مرجع برای BMS
        self.bms_index: Optional[int] = None
        self.bms_level: Optional[float] = None
        self.bms_body: float = 0.0
        self.bms_ratio: float = 0.0
        self.leg_low: Optional[float] = None
        self.leg_high: Optional[float] = None
        self.zone: Optional[Zone] = None
        self.used_sweep_index: int = -1
        # ✅ FIX: فیلدهای جدید برای ترتل سوپ مستقل
        self.ts_direction: Optional[str] = None
        self.ts_sweep_price: Optional[float] = None
        self.ts_index: Optional[int] = None

    # ------------------------------------------------------------------
    def step(self, data: MarketData, i: int, ctx: Optional[Context] = None) -> dict:
        ctx = ctx or Context()
        p = self.params
        candles = data.candles
        if i < max(10, p.lookback * 3):
            return self._wait("insufficient_data", i, ctx)
        c = candles[i]

        self._last_time = c.time
        if ctx.time is None:
            ctx = _with_time(ctx, c.time)

        # ---------- ۰) فیلترهای بیرونی ----------
        blocked = outer_filters(ctx, p)
        if blocked:
            return self._wait(blocked, i, ctx)

        # ---------- ۱) SH ----------
        if self.stage == IDLE:
            found = self._find_sh(data, i, ctx)
            if found == "conflicting":
                return self._wait("conflicting_signals", i, ctx)
            if found is None:
                return self._wait("no_sh_detected", i, ctx)

        # ✅ FIX: ---------- ۱.۵) بررسی ترتل سوپ مستقل ----------
        if self.stage == SH_CONFIRMED:
            ts_result = self._try_turtle_soup(data, i, ctx)
            if ts_result == "__trigger__":
                return self._build_turtle_soup_signal(data, i, ctx)
            # اگر ترتل سوپ رد شد، ادامه به BMS

        # ---------- ۲) BMS ----------
        if self.stage == SH_CONFIRMED:
            self._try_bms(data, i)
            if self.stage == IDLE:                    # منقضی شد
                return self._wait("no_bms_within_max_delay", i, ctx)

        # ---------- ۳) RTO + ۴) TRIGGER ----------
        if self.stage in (BMS_CONFIRMED, IN_ZONE_WAIT):
            reason = self._advance_rto(data, i, ctx)
            if reason == "__trigger__":
                return self._build_signal(data, i, ctx)
            if reason:
                return self._wait(reason, i, ctx)

        return self._wait("waiting", i, ctx)

    # ==================================================================
    # مرحله ۱ — Stop Hunt
    # ==================================================================
    def _find_sh(self, data: MarketData, i: int, ctx: Context) -> Optional[str]:
        p = self.params
        pip = self.pip
        candles = data.candles
        bull = None
        bear = None

        # ✅ FIX: تحمل نفوذ کلوز برای تشخیص بهتر ترتل سوپ
        sh_close_tolerance = getattr(p, 'sh_close_tolerance_pips', 3.0) * pip

        L = data.last_low(i)
        if L is not None:
            start = max(L[3], L[1] + 1)
            for j in range(start, i + 1):
                if j <= self.used_sweep_index:
                    continue
                if i - j > p.max_bms_delay_candles:
                    continue
                c = candles[j]
                depth = L[2] - c.low
                if depth < p.min_sweep_pips * pip:
                    continue
                if depth > p.max_sweep_pips * pip:
                    continue
                # ✅ FIX: قبلی: if c.close <= L[2]: continue
                if c.close < L[2] - sh_close_tolerance:
                    continue
                hint = ctx.sweep_pool_hint
                if hint is None and data.other_equal_levels(
                    i, "low", L[1], L[2], p.equal_level_tolerance_pips * pip
                ):
                    hint = "equal_lows"
                bull = {
                    "direction": "bull",
                    "level": L[2],
                    "sweep": min(c.low, L[2]),
                    "index": j,
                    "depth_pips": depth / pip,
                    "pool": hint or "swing",
                    "ref": data.last_swing_before(i, "high", j),
                }
                break

        H = data.last_high(i)
        if H is not None:
            start = max(H[3], H[1] + 1)
            for j in range(start, i + 1):
                if j <= self.used_sweep_index:
                    continue
                if i - j > p.max_bms_delay_candles:
                    continue
                c = candles[j]
                depth = c.high - H[2]
                if depth < p.min_sweep_pips * pip:
                    continue
                if depth > p.max_sweep_pips * pip:
                    continue
                # ✅ FIX: قبلی: if c.close >= H[2]: continue
                if c.close > H[2] + sh_close_tolerance:
                    continue
                hint = ctx.sweep_pool_hint
                if hint is None and data.other_equal_levels(
                    i, "high", H[1], H[2], p.equal_level_tolerance_pips * pip
                ):
                    hint = "equal_highs"
                bear = {
                    "direction": "bear",
                    "level": H[2],
                    "sweep": max(c.high, H[2]),
                    "index": j,
                    "depth_pips": depth / pip,
                    "pool": hint or "swing",
                    "ref": data.last_swing_before(i, "low", j),
                }
                break

        if bull and bear:
            return "conflicting"
        pick = bull or bear
        if pick is None:
            return None
        
        # ✅ FIX: اگر ref وجود نداشت، برای بررسی‌های بعدی نگه می‌داریم ولی به مرحله بعد نمی‌رویم
        if pick["ref"] is None:
            self.used_sweep_index = max(self.used_sweep_index, pick["index"])
            return None

        self.stage = SH_CONFIRMED
        self.direction = pick["direction"]
        self.sh_index = pick["index"]
        self.sweep_level = pick["level"]
        self.sweep_price = pick["sweep"]
        self.sweep_depth_pips = pick["depth_pips"]
        self.pool = pick["pool"]
        self.ref_level = pick["ref"][2]
        self.used_sweep_index = pick["index"]
        if self.direction == "bull":
            self.leg_low = self.sweep_price
        else:
            self.leg_high = self.sweep_price
        return "ok"
    # ==================================================================
    # ✅ FIX: مرحله ۱.۵ — بررسی ترتل سوپ مستقل (بدون نیاز به BMS)
    # ==================================================================
    def _try_turtle_soup(self, data: MarketData, i: int, ctx: Context) -> Optional[str]:
        """
        اگر SH شناسایی شد و کندل بعد از آن یک کندل ریجکشن قوی در جهت مخالف باشد،
        بدون نیاز به BMS، سیگنال ترتل سوپ صادر می‌شود.
        
        شرایط:
        - برای Bull TS: کندل فعلی باید صعودی باشد و بالای سطح بسته شود
        - برای Bear TS: کندل فعلی باید نزولی باشد و زیر سطح بسته شود
        - حداقل ۱ کندل از SH گذشته باشد
        """
        p = self.params
        pip = self.pip
        c = data.candles[i]
        
        # حداقل ۱ کندل از SH گذشته باشد
        if i <= self.sh_index:
            return None
        
        # حداکثر ۵ کندل فرصت برای تایید ترتل سوپ
        if i - self.sh_index > 5:
            return None
        
        # ✅ شرط تایید: کندل فعلی باید در جهت معکوس حرکت کند
        if self.direction == "bull":
            # برای TS Long: کندل باید صعودی باشد و کلوز بالای سطح SH
            if c.bullish and c.close > self.sweep_level:
                self.ts_direction = "bull"
                self.ts_sweep_price = self.sweep_price
                self.ts_index = self.sh_index
                return "__trigger__"
        elif self.direction == "bear":
            # برای TS Short: کندل باید نزولی باشد و کلوز زیر سطح SH
            if c.bearish and c.close < self.sweep_level:
                self.ts_direction = "bear"
                self.ts_sweep_price = self.sweep_price
                self.ts_index = self.sh_index
                return "__trigger__"
        
        return None

    # ==================================================================
    # ✅ FIX: ساخت سیگنال ترتل سوپ مستقل
    # ==================================================================
    def _build_turtle_soup_signal(self, data: MarketData, i: int, ctx: Context) -> dict:
        p = self.params
        pip = self.pip
        c = data.candles[i]
        atr = data.atr(i)
        atr_pips = atr / pip

        if atr_pips < p.min_atr_pips or atr_pips > p.max_atr_pips:
            self.reset()
            return self._wait("atr_out_of_range", i, ctx)

        buffer_pips = max(p.sl_buffer_pips, (ctx.spread_pips or 0.0) * 1.5, 0.3 * atr_pips)
        entry = c.close
        
        if self.ts_direction == "bull":
            sl = self.ts_sweep_price - buffer_pips * pip
            risk = entry - sl
            tp = entry + p.rr_target * risk
            signal = "BUY"
        else:
            sl = self.ts_sweep_price + buffer_pips * pip
            risk = sl - entry
            tp = entry - p.rr_target * risk
            signal = "SELL"

        risk_pips = risk / pip
        reward_pips = abs(tp - entry) / pip

        if risk_pips < p.min_risk_pips:
            self.reset()
            return self._wait("risk_too_small", i, ctx)
        if risk_pips > p.max_risk_pips:
            self.reset()
            return self._wait("risk_too_large", i, ctx)
        if not htf_allows(self.ts_direction, ctx, p):
            self.reset()
            return self._wait("htf_filter", i, ctx)

        session_name, session_mode = session_of(c.time)
        
        # ✅ برای ترتل سوپ، confidence متوسط در نظر می‌گیریم
        score = 60
        label = "Medium"
        if session_name in ("London", "Overlap", "NY_AM"):
            score = 70
        det = {"setup": "turtle_soup", "session": session_name}
        
        if label == "Low":
            self.reset()
            return self._wait("low_confidence", i, ctx)

        lot = None
        if ctx.balance and ctx.risk_percent and ctx.pip_value_per_lot and risk_pips > 0:
            lot = (ctx.balance * ctx.risk_percent / 100.0) / (risk_pips * ctx.pip_value_per_lot)
            lot = round(lot, 2)

        out = {
            "schema_version": "2.1",
            "timestamp": c.time,
            "symbol": self.symbol,
            "timeframe": p.timeframe,
            "signal": signal,
            "confidence": label,
            "confidence_score": score,
            "setup": {
                "sh_detected": True,
                "bms_detected": False,  # ✅ ترتل سوپ نیاز به BMS ندارد
                "rto_detected": False,
                "entry_trigger": True,
                "entry_type": "TurtleSoup",
            },
            "setup_trace": {
                "sh_sweep_level": r(self.sweep_level, self.digits),
                "sweep_price": r(self.ts_sweep_price, self.digits),
                "sweep_depth_pips": r(self.sweep_depth_pips, 1),
                "sweep_pool": self.pool,
                "setup_age_candles": i - self.ts_index,
            },
            "trade": {
                "entry_price": r(entry, self.digits),
                "stop_loss": r(sl, self.digits),
                "take_profit": r(tp, self.digits),
                "risk_reward": round(p.rr_target, 2),
                "risk_pips": r(risk_pips, 1),
                "reward_pips": r(reward_pips, 1),
                "lot_size": lot,
            },
            "invalidation": {
                "cancel_if_close_below": r(self.ts_sweep_price - p.invalidation_buffer_pips * pip, self.digits)
                if self.ts_direction == "bull" else None,
                "cancel_if_close_above": r(self.ts_sweep_price + p.invalidation_buffer_pips * pip, self.digits)
                if self.ts_direction == "bear" else None,
                "expiry_candles": 5,
            },
            "filters": {
                "htf_bias": ctx.htf_bias,
                "htf_alignment": True,
                "session": session_name,
                "news_block": False,
                "risk_pips_ok": True,
                "spread_pips": ctx.spread_pips,
                "atr_pips": r(atr_pips, 1),
                "sl_buffer_pips": r(buffer_pips, 2),
            },
            "notes": f"Turtle Soup {'Long' if self.ts_direction == 'bull' else 'Short'}: "
                     f"Liquidity swept {r(self.sweep_depth_pips, 1)} pips, rejection confirmed.",
            "_internal": {
                "stage": "TRIGGERED",
                "score_breakdown": det,
                "direction": self.ts_direction,
            },
        }
        self.reset()
        return out

    # ==================================================================
    # مرحله ۲ — BMS
    # ==================================================================
    def _try_bms(self, data: MarketData, i: int) -> None:
        p = self.params
        c = data.candles[i]
        atr = data.atr(i)
        ok_body = c.body >= p.displacement_factor * atr
        ok_ratio = c.rng > 0 and (c.body / c.rng) >= p.min_body_ratio
        displacement = ok_body or ok_ratio

        # ✅ FIX: اگر ref_level وجود ندارد، نمی‌توان BMS زد
        if self.ref_level is None:
            if i - self.sh_index > p.max_bms_delay_candles:
                self.reset()
            return

        broke = False
        if self.direction == "bull" and c.close > self.ref_level:
            broke = True
            level = self.ref_level
        elif self.direction == "bear" and c.close < self.ref_level:
            broke = True
            level = self.ref_level

        if broke and displacement:
            if i - self.sh_index > p.max_bms_delay_candles:
                self.reset()
                return
            self.stage = BMS_CONFIRMED
            self.bms_index = i
            self.bms_level = level
            self.bms_body = c.body
            self.bms_ratio = (c.body / atr) if atr > 0 else 0.0
            # leg نهایی (بخش ۱.۴)
            seg = data.candles[self.sh_index : i + 1]
            if self.direction == "bull":
                self.leg_high = max(x.high for x in seg)
                self.leg_low = self.sweep_price
            else:
                self.leg_low = min(x.low for x in seg)
                self.leg_high = self.sweep_price
            return

        if i - self.sh_index > p.max_bms_delay_candles:
            self.reset()

    # ==================================================================
    # مرحله ۳ و ۴ — RTO + Trigger
    # ==================================================================
    def _advance_rto(self, data: MarketData, i: int, ctx: Context) -> Optional[str]:
        p = self.params
        pip = self.pip
        c = data.candles[i]

        # باطل‌شدن
        buf = p.invalidation_buffer_pips * pip
        if self.direction == "bull" and c.close < self.sweep_price - buf:
            self.reset()
            return "invalidated"
        if self.direction == "bear" and c.close > self.sweep_price + buf:
            self.reset()
            return "invalidated"

        if self.stage == BMS_CONFIRMED:
            # leg را تا قبل از لمس اول ناحیه زنده نگه می‌داریم
            if self.direction == "bull":
                self.leg_high = max(self.leg_high, c.high)
            else:
                self.leg_low = min(self.leg_low, c.low)

            zone = build_zone(
                data, i, self.direction, self.sh_index, self.bms_index,
                self.leg_low, self.leg_high, p, pip,
            )
            if zone is None:
                self.reset()
                return "no_valid_zone"
            self.zone = zone

            # v2.2: باید خودِ هم‌پوشانی دقیق با پنجره‌ی فیبو را لمس کند؛
            # لمس لبه‌ی دور OB بدون رسیدن به هم‌پوشانی کافی نیست.
            t_lo = zone.overlap_lo if zone.overlap_lo is not None else zone.lo
            t_hi = zone.overlap_hi if zone.overlap_hi is not None else zone.hi
            if c.low <= t_hi and c.high >= t_lo:
                self.stage = IN_ZONE_WAIT

        if self.stage == IN_ZONE_WAIT and self.zone is not None:
            z = self.zone
            inside = z.lo <= c.close <= z.hi
            if self.direction == "bull" and c.bullish and inside:
                return "__trigger__"
            if self.direction == "bear" and c.bearish and inside:
                return "__trigger__"

        # انقضا
        if i - self.bms_index > p.max_wait_candles:
            self.reset()
            return "zone_not_reached"
        if i - self.sh_index > p.max_total_setup_candles:
            self.reset()
            return "expired"
        return None

    # ==================================================================
    # ساخت سیگنال (بخش ۴ و ۵ و ۷)
    # ==================================================================
    def _build_signal(self, data: MarketData, i: int, ctx: Context) -> dict:
        p = self.params
        pip = self.pip
        c = data.candles[i]
        atr = data.atr(i)
        atr_pips = atr / pip

        if atr_pips < p.min_atr_pips or atr_pips > p.max_atr_pips:
            self.reset()
            return self._wait("atr_out_of_range", i, ctx)

        buffer_pips = max(p.sl_buffer_pips, (ctx.spread_pips or 0.0) * 1.5, 0.3 * atr_pips)
        entry = c.close
        if self.direction == "bull":
            sl = self.sweep_price - buffer_pips * pip
            risk = entry - sl
            tp = entry + p.rr_target * risk
            signal = "BUY"
        else:
            sl = self.sweep_price + buffer_pips * pip
            risk = sl - entry
            tp = entry - p.rr_target * risk
            signal = "SELL"

        risk_pips = risk / pip
        reward_pips = abs(tp - entry) / pip

        if risk_pips < p.min_risk_pips:
            self.reset()
            return self._wait("risk_too_small", i, ctx)
        if risk_pips > p.max_risk_pips:
            self.reset()
            return self._wait("risk_too_large", i, ctx)
        if not htf_allows(self.direction, ctx, p):
            self.reset()
            return self._wait("htf_filter", i, ctx)

        session_name, session_mode = session_of(c.time)
        score, label, det = score_signal(
            direction=self.direction,
            ctx=ctx,
            params=p,
            zone=self.zone,
            displacement_ratio=self.bms_ratio,
            risk_pips=risk_pips,
            session_name=session_name,
        )
        if label == "Low":
            self.reset()
            return self._wait("low_confidence", i, ctx)
        if session_mode == "high_only" and label != "High":
            self.reset()
            return self._wait("out_of_session", i, ctx)

        lot = None
        if ctx.balance and ctx.risk_percent and ctx.pip_value_per_lot and risk_pips > 0:
            lot = (ctx.balance * ctx.risk_percent / 100.0) / (risk_pips * ctx.pip_value_per_lot)
            lot = round(lot, 2)

        zone = self.zone
        entry_type = {"ob": "OrderBlock", "fvg": "FVG", "fib": "FibRetracement"}[zone.kind]
        if zone.has_both:
            entry_type = "OrderBlock+FVG"

        retr_at_entry = retracement(entry, self.leg_low, self.leg_high, self.direction)

        out = {
            "schema_version": "2.0",
            "timestamp": c.time,
            "symbol": self.symbol,
            "timeframe": p.timeframe,
            "signal": signal,
            "confidence": label,
            "confidence_score": score,
            "setup": {
                "sh_detected": True,
                "bms_detected": True,
                "rto_detected": True,
                "entry_trigger": True,
                "entry_type": entry_type,
            },
            "setup_trace": {
                "sh_sweep_level": r(self.sweep_level, self.digits),
                "sweep_price": r(self.sweep_price, self.digits),
                "sweep_depth_pips": r(self.sweep_depth_pips, 1),
                "sweep_pool": self.pool,
                "bms_break_level": r(self.ref_level, self.digits),
                "displacement_atr_ratio": r(self.bms_ratio, 2),
                "leg_low": r(self.leg_low, self.digits),
                "leg_high": r(self.leg_high, self.digits),
                "retracement_at_entry": r(retr_at_entry, 3),
                "zone_type": entry_type,
                "zone_bottom": r(zone.lo, self.digits),
                "zone_top": r(zone.hi, self.digits),
                "ob_fresh": zone.fresh,
                "ob_mitigations": zone.mitigations,
                "setup_age_candles": i - self.sh_index,
            },
            "trade": {
                "entry_price": r(entry, self.digits),
                "stop_loss": r(sl, self.digits),
                "take_profit": r(tp, self.digits),
                "risk_reward": round(p.rr_target, 2),
                "risk_pips": r(risk_pips, 1),
                "reward_pips": r(reward_pips, 1),
                "lot_size": lot,
            },
            "invalidation": {
                "cancel_if_close_below": r(self.sweep_price - p.invalidation_buffer_pips * pip, self.digits)
                if self.direction == "bull" else None,
                "cancel_if_close_above": r(self.sweep_price + p.invalidation_buffer_pips * pip, self.digits)
                if self.direction == "bear" else None,
                "expiry_candles": p.max_total_setup_candles,
            },
            "filters": {
                "htf_bias": ctx.htf_bias,
                "htf_alignment": True,
                "session": session_name,
                "news_block": False,
                "risk_pips_ok": True,
                "spread_pips": ctx.spread_pips,
                "atr_pips": r(atr_pips, 1),
                "sl_buffer_pips": r(buffer_pips, 2),
            },
            "notes": "",
            "_internal": {
                "stage": "TRIGGERED",
                "score_breakdown": det,
                "direction": self.direction,
            },
        }
        out["notes"] = _notes(out)
        self.reset()
        return out

    # ==================================================================
    def _wait(self, reason: str, i: int, ctx: Context) -> dict:
        ts = ctx.time if ctx.time is not None else getattr(self, "_last_time", None)
        return {
            "schema_version": "2.0",
            "timestamp": ts,
            "symbol": self.symbol,
            "timeframe": self.params.timeframe,
            "signal": "WAIT",
            "confidence": "None",
            "confidence_score": 0,
            "setup": {
                "sh_detected": self.stage != IDLE,
                "bms_detected": self.stage in (BMS_CONFIRMED, IN_ZONE_WAIT),
                "rto_detected": self.stage == IN_ZONE_WAIT,
                "entry_trigger": False,
                "entry_type": None,
            },
            "trade": None,
            "invalidation": None,
            "rejected_because": reason,
            "notes": NOTES.get(reason, reason),
            "_internal": {
                "stage": self.stage,
                "direction": self.direction,
                "dropped": reason in DROP_REASONS,
            },
        }


# ----------------------------------------------------------------------
def r(value, digits):
    if value is None:
        return None
    return round(float(value), digits)


def _with_time(ctx: Context, time_value) -> Context:
    ctx.time = time_value
    return ctx


def _notes(sig: dict) -> str:
    d = sig["setup_trace"]
    t = sig["trade"]
    direction = "bullish" if sig["_internal"]["direction"] == "bull" else "bearish"
    return (
        f"Liquidity swept {d['sweep_depth_pips']} pips {'below' if direction == 'bullish' else 'above'} "
        f"the confirmed swing ({d['sh_sweep_level']}); {direction} BMS with "
        f"{d['displacement_atr_ratio']}x ATR displacement; RTO to {d['zone_type']} at "
        f"{round(d['retracement_at_entry'] * 100, 1)}% retracement; confidence "
        f"{sig['confidence']} ({sig['confidence_score']}), risk {t['risk_pips']} pips RR 2.0."
    )