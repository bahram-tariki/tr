"""هسته محاسباتی سیستم SH + BMS + RTO.

این پکیج «قطعی» است: ورودی/خروجی مشخص، بدون دسترسی شبکه، بدون بروکر.
"""
from .config import Params, pip_size_for, digits_for
from .market import Candle, MarketData
from .engine import Engine, Context
from .backtest import run_backtest
from .io import load_candles, default_contexts

__all__ = [
    "Params",
    "pip_size_for",
    "digits_for",
    "Candle",
    "MarketData",
    "Engine",
    "Context",
    "run_backtest",
    "load_candles",
    "default_contexts",
]
