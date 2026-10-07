"""خواندن داده کندل از CSV / JSON."""
from __future__ import annotations

import csv
import json
import os
from typing import List, Optional

from .market import Candle

REQUIRED = ("time", "open", "high", "low", "close")


def _to_float(v) -> float:
    return float(str(v).strip())


def load_candles(path: str) -> List[Candle]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"data file not found: {path}")
    if path.lower().endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            rows = json.load(f)
        if isinstance(rows, dict):
            rows = rows.get("candles") or rows.get("data") or []
        return _rows_to_candles(rows)

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        sample = f.read(2048)
        f.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(f, dialect=dialect)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")
        rows = [{(k or "").strip().lower(): v for k, v in row.items()} for row in reader]
    return _rows_to_candles(rows)


def _rows_to_candles(rows) -> List[Candle]:
    out: List[Candle] = []
    for idx, row in enumerate(rows):
        missing = [k for k in REQUIRED if k not in row or row[k] in (None, "")]
        if missing:
            raise ValueError(f"row {idx}: missing fields {missing}")
        out.append(
            Candle(
                i=idx,
                time=str(row["time"]).strip(),
                open=_to_float(row["open"]),
                high=_to_float(row["high"]),
                low=_to_float(row["low"]),
                close=_to_float(row["close"]),
                volume=_to_float(row.get("volume") or 0),
            )
        )
    if not out:
        raise ValueError("no candles found in file")
    return out


def default_contexts(candles: List[Candle], htf_bias: str = "NEUTRAL",
                     spread_pips: float = 0.6) -> List:
    from .engine import Context

    return [
        Context(time=c.time, spread_pips=spread_pips, htf_bias=htf_bias)
        for c in candles
    ]
