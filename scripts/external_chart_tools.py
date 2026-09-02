from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SRLevel:
    level: float
    low: float
    high: float
    direction_hint: str
    touches: int
    first_index: str
    last_index: str
    source: str


def load_live_date_1m(symbol: str, market_date: str) -> pd.DataFrame:
    path = ROOT / "data" / "raw" / "binance_futures_live_dates" / market_date / f"{symbol}_1m_{market_date}_ny.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.sort_values("timestamp").set_index("timestamp")[["open", "high", "low", "close", "volume"]].astype(float)


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = df.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return out.dropna()


def true_range_atr(df: pd.DataFrame, period: int = 20) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(period, min_periods=max(3, period // 4)).mean()


def zigzag_reversal_points(close: pd.Series, min_retrace_pct: float = 0.12) -> pd.DataFrame:
    """Return reversal points using the MIT zig-zag grouping idea from BatuhanUsluel's S/R repo.

    This is adapted for existing OHLCV data and returns data instead of drawing charts.
    """
    if close.empty:
        return pd.DataFrame(columns=["dir", "value"])
    cur_val = float(close.iloc[0])
    cur_pos = close.index[0]
    cur_dir = 1
    rows: list[dict] = []
    for idx, value in close.items():
        value = float(value)
        if (value - cur_val) * cur_dir >= 0:
            cur_val = value
            cur_pos = idx
            continue
        retrace_pct = abs((value - cur_val) / cur_val * 100) if cur_val else 0.0
        if retrace_pct >= min_retrace_pct:
            rows.append({"timestamp": cur_pos, "dir": cur_dir, "value": cur_val})
            cur_val = value
            cur_pos = idx
            cur_dir *= -1
    if not rows:
        return pd.DataFrame(columns=["dir", "value"])
    return pd.DataFrame(rows).set_index("timestamp")


def detect_zigzag_sr_levels(
    df: pd.DataFrame,
    timeframe: str,
    min_retrace_pct: float = 0.12,
    max_pct_diff: float = 0.08,
    max_bars_between: int = 180,
    min_touches: int = 3,
) -> list[SRLevel]:
    points = zigzag_reversal_points(df["close"], min_retrace_pct=min_retrace_pct)
    if points.empty:
        return []
    used: set[pd.Timestamp] = set()
    levels: list[SRLevel] = []
    point_items = list(points.iterrows())
    for idx, row in point_items:
        if idx in used:
            continue
        values = [float(row["value"])]
        indexes = [idx]
        for idx2, row2 in point_items:
            if idx2 == idx or idx2 in used:
                continue
            if abs(df.index.get_loc(idx2) - df.index.get_loc(idx)) > max_bars_between:
                continue
            if int(row2["dir"]) != int(row["dir"]):
                continue
            value2 = float(row2["value"])
            if abs(float(row["value"]) / value2 - 1.0) < max_pct_diff / 100.0:
                values.append(value2)
                indexes.append(idx2)
        if len(values) < min_touches:
            continue
        for taken in indexes:
            used.add(taken)
        level = sum(values) / len(values)
        width = max(level * max_pct_diff / 100.0, float(true_range_atr(df).dropna().tail(1).iloc[0]) * 0.20)
        direction_hint = "resistance" if int(row["dir"]) == 1 else "support"
        levels.append(
            SRLevel(
                level=level,
                low=level - width,
                high=level + width,
                direction_hint=direction_hint,
                touches=len(values),
                first_index=min(indexes).isoformat(),
                last_index=max(indexes).isoformat(),
                source=f"algorithmic_sr_zigzag_{timeframe}",
            )
        )
    return sorted(levels, key=lambda x: (x.touches, x.last_index), reverse=True)


def detect_sr_flip_state(df: pd.DataFrame, level: SRLevel, lookback_bars: int = 24) -> str:
    recent = df.tail(lookback_bars)
    if recent.empty:
        return "unknown"
    closes = recent["close"]
    inside = ((recent["low"] <= level.high) & (recent["high"] >= level.low)).sum()
    last_close = float(closes.iloc[-1])
    prev_close = float(closes.iloc[max(0, len(closes) - min(lookback_bars, 8))])
    if inside == 0:
        return "level_away"
    if prev_close < level.low and last_close > level.high:
        return "resistance_to_support_flip"
    if prev_close > level.high and last_close < level.low:
        return "support_to_resistance_flip"
    if level.low <= last_close <= level.high:
        return "testing_level"
    if last_close > level.high:
        return "above_level_after_test"
    if last_close < level.low:
        return "below_level_after_test"
    return "unknown"
