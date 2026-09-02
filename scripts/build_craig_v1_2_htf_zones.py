#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PROCESSED_ROOT = ROOT / "data/processed/binance_futures_continuous"
OUT_DIR = ROOT / "outputs"
HTF_ZONES_PARQUET = OUT_DIR / "craig_v1_2_htf_zones.parquet"
TRENDLINE_ZONES_PARQUET = OUT_DIR / "craig_v1_2_trendline_zones.parquet"
AUDIT_CSV = OUT_DIR / "craig_v1_2_htf_zone_audit.csv"
BUILD_REPORT_MD = OUT_DIR / "craig_v1_2_htf_zone_build_report.md"

CORE_SYMBOLS = ["SOLUSDT", "ETHUSDT", "BTCUSDT"]
TIMEFRAMES = ["15m", "1h", "4h"]
TIMEFRAME_MINUTES = {"15m": 15, "1h": 60, "4h": 240}
RESAMPLE_RULES = {"15m": "15T", "1h": "1H", "4h": "4H"}
PIVOT_LEFT = 3
PIVOT_RIGHT = 3
ATR_PERIOD = 14
SR_ATR_MULTIPLIER = 0.35
FVG_MIN_ATR_FRACTION = 0.02
TRENDLINE_NEAR_ATR_MULTIPLIER = 0.35
TRENDLINE_MIN_QUALITY = 0.55
TRENDLINE_MAX_PRIOR_ANCHORS = 16
TRENDLINE_TOP_PER_ANCHOR = 1
TRENDLINE_INTERACTION_BARS = {"15m": 24, "1h": 18, "4h": 12}
TRENDLINE_MAX_ANCHOR_AGE_BARS = {"15m": 192, "1h": 168, "4h": 120}
TRENDLINE_ENDPOINT_STEP = {"15m": 4, "1h": 2, "4h": 1}


@dataclass(frozen=True)
class BuildContext:
    symbol: str
    timeframe: str
    bars: pd.DataFrame


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def stable_id(*parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def find_symbol_parquet(symbol: str, start_date: str, end_date: str) -> Path:
    exact = PROCESSED_ROOT / symbol / "1m" / f"{symbol}_1m_{start_date}_{end_date}.parquet"
    if exact.exists():
        return exact
    candidates = sorted((PROCESSED_ROOT / symbol / "1m").glob(f"{symbol}_1m_*.parquet"))
    if not candidates:
        raise FileNotFoundError(f"No normalized continuous parquet found for {symbol}")
    return candidates[-1]


def load_1m(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    path = find_symbol_parquet(symbol, start_date, end_date)
    df = pd.read_parquet(path)
    if "timestamp" not in df.columns:
        raise ValueError(f"{path} missing timestamp column")
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")
    return df.drop_duplicates("timestamp", keep="last").reset_index(drop=True)


def compute_atr(bars: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    high_low = bars["high"] - bars["low"]
    high_close = (bars["high"] - bars["close"].shift(1)).abs()
    low_close = (bars["low"] - bars["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()


def resample_ohlcv(df_1m: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    minutes = TIMEFRAME_MINUTES[timeframe]
    indexed = df_1m.set_index("timestamp").sort_index()
    grouped = indexed.resample(RESAMPLE_RULES[timeframe], label="left", closed="left")
    bars = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        source_1m_count=("close", "count"),
    )
    bars = bars[bars["source_1m_count"] == minutes].dropna(subset=["open", "high", "low", "close"]).copy()
    bars["open_time"] = bars.index
    bars["close_time"] = bars["open_time"] + pd.Timedelta(minutes=minutes)
    bars = bars.reset_index(drop=True)
    bars["bar_index"] = range(len(bars))
    bars["atr"] = compute_atr(bars)
    bars["utc_date"] = bars["open_time"].dt.date.astype(str)
    return bars


def base_object(
    ctx: BuildContext,
    object_type: str,
    side: str,
    available_at: pd.Timestamp,
    latest_source: pd.Timestamp,
    zone_low: float,
    zone_high: float,
    source_bar_index: int,
    **extra: object,
) -> dict[str, object]:
    zone_mid = (zone_low + zone_high) / 2
    object_id = stable_id(ctx.symbol, ctx.timeframe, object_type, side, source_bar_index, available_at, zone_low, zone_high)
    row = {
        "object_id": object_id,
        "symbol": ctx.symbol,
        "timeframe": ctx.timeframe,
        "object_type": object_type,
        "side": side,
        "zone_low": float(min(zone_low, zone_high)),
        "zone_high": float(max(zone_low, zone_high)),
        "zone_mid": float(zone_mid),
        "price": float(zone_mid),
        "formed_at": available_at,
        "confirmed_at": available_at,
        "available_at": available_at,
        "latest_source_candle_close_used": latest_source,
        "source_bar_index": int(source_bar_index),
        "anchor_count": extra.pop("anchor_count", 0),
        "anchor_times": extra.pop("anchor_times", ""),
        "anchor_prices": extra.pop("anchor_prices", ""),
        "htf_trendline_4h": "",
        "htf_trendline_1h": "",
        "htf_trendline_15m": "",
        "trendline_interaction_type": "none",
        "trendline_pa_zone_score": 0.0,
        "trendline_zone_confluence_count": 0,
        "sr_trendline_overlap": False,
        "fvg_trendline_overlap": False,
        "liquidity_trendline_overlap": False,
        "lookahead_pass": latest_source <= available_at,
        "lookahead_violation_reason": "" if latest_source <= available_at else "latest_source_after_available_at",
    }
    row.update(extra)
    return row


def detect_fvg(ctx: BuildContext) -> list[dict[str, object]]:
    bars = ctx.bars
    rows: list[dict[str, object]] = []
    for i in range(2, len(bars)):
        left = bars.iloc[i - 2]
        current = bars.iloc[i]
        atr = max(float(current["atr"]), 1e-12)
        available_at = current["close_time"]
        if float(left["high"]) < float(current["low"]):
            gap = float(current["low"]) - float(left["high"])
            if gap >= atr * FVG_MIN_ATR_FRACTION:
                rows.append(
                    base_object(
                        ctx,
                        "fvg_bullish",
                        "support",
                        available_at,
                        available_at,
                        float(left["high"]),
                        float(current["low"]),
                        int(current["bar_index"]),
                        fvg_direction="bullish",
                        gap_size=gap,
                    )
                )
        if float(left["low"]) > float(current["high"]):
            gap = float(left["low"]) - float(current["high"])
            if gap >= atr * FVG_MIN_ATR_FRACTION:
                rows.append(
                    base_object(
                        ctx,
                        "fvg_bearish",
                        "resistance",
                        available_at,
                        available_at,
                        float(current["high"]),
                        float(left["low"]),
                        int(current["bar_index"]),
                        fvg_direction="bearish",
                        gap_size=gap,
                    )
                )
    return rows


def detect_swings(ctx: BuildContext) -> tuple[list[dict[str, object]], pd.DataFrame]:
    bars = ctx.bars.reset_index(drop=True)
    rows: list[dict[str, object]] = []
    swing_records: list[dict[str, object]] = []
    window_size = PIVOT_LEFT + PIVOT_RIGHT + 1
    rolling_high = bars["high"].rolling(window_size, center=True, min_periods=window_size).max()
    rolling_low = bars["low"].rolling(window_size, center=True, min_periods=window_size).min()
    swing_high_idx = bars.index[(bars["high"].eq(rolling_high)) & bars.index.to_series().between(PIVOT_LEFT, len(bars) - PIVOT_RIGHT - 1)]
    swing_low_idx = bars.index[(bars["low"].eq(rolling_low)) & bars.index.to_series().between(PIVOT_LEFT, len(bars) - PIVOT_RIGHT - 1)]
    pivot_events = [(int(i), "high") for i in swing_high_idx] + [(int(i), "low") for i in swing_low_idx]
    pivot_events.sort()
    for i, pivot_kind in pivot_events:
        pivot = bars.iloc[i]
        available_bar = bars.iloc[i + PIVOT_RIGHT]
        available_at = available_bar["close_time"]
        latest_source = available_at
        atr = max(float(available_bar["atr"]), 1e-12)
        width = max(atr * 0.08, float(pivot["close"]) * 0.0001)
        if pivot_kind == "high":
            row = base_object(
                ctx,
                "swing_high",
                "resistance",
                available_at,
                latest_source,
                float(pivot["high"]) - width,
                float(pivot["high"]) + width,
                int(pivot["bar_index"]),
                pivot_time=pivot["close_time"],
                pivot_available_at=available_at,
                pivot_price=float(pivot["high"]),
                anchor_count=1,
                anchor_times=str(pivot["close_time"]),
                anchor_prices=f"{float(pivot['high']):.10g}",
            )
            rows.append(row)
            swing_records.append(
                {
                    "side": "resistance",
                    "pivot_kind": "high",
                    "pivot_time": pivot["close_time"],
                    "available_at": available_at,
                    "latest_source_candle_close_used": latest_source,
                    "price": float(pivot["high"]),
                    "bar_index": int(pivot["bar_index"]),
                    "atr": atr,
                }
            )
        if pivot_kind == "low":
            row = base_object(
                ctx,
                "swing_low",
                "support",
                available_at,
                latest_source,
                float(pivot["low"]) - width,
                float(pivot["low"]) + width,
                int(pivot["bar_index"]),
                pivot_time=pivot["close_time"],
                pivot_available_at=available_at,
                pivot_price=float(pivot["low"]),
                anchor_count=1,
                anchor_times=str(pivot["close_time"]),
                anchor_prices=f"{float(pivot['low']):.10g}",
            )
            rows.append(row)
            swing_records.append(
                {
                    "side": "support",
                    "pivot_kind": "low",
                    "pivot_time": pivot["close_time"],
                    "available_at": available_at,
                    "latest_source_candle_close_used": latest_source,
                    "price": float(pivot["low"]),
                    "bar_index": int(pivot["bar_index"]),
                    "atr": atr,
                }
            )
    return rows, pd.DataFrame(swing_records)


def cluster_price_objects(ctx: BuildContext, swings: pd.DataFrame, object_type: str, side: str) -> list[dict[str, object]]:
    if swings.empty:
        return []
    side_swings = swings[swings["side"] == side].sort_values("price").reset_index(drop=True)
    if side_swings.empty:
        return []
    median_atr = max(float(side_swings["atr"].median()), 1e-12)
    tolerance = max(median_atr * SR_ATR_MULTIPLIER, float(side_swings["price"].median()) * 0.001)
    rows: list[dict[str, object]] = []
    cluster: list[dict[str, object]] = []

    def flush(current: list[dict[str, object]]) -> None:
        if len(current) < 2:
            return
        df = pd.DataFrame(current)
        latest_source = df["latest_source_candle_close_used"].max()
        available_at = df["available_at"].max()
        prices = df["price"].astype(float)
        source_bar_index = int(df["bar_index"].max())
        rows.append(
            base_object(
                ctx,
                object_type,
                side,
                available_at,
                latest_source,
                float(prices.min()),
                float(prices.max()),
                source_bar_index,
                anchor_count=len(df),
                anchor_times="|".join(pd.to_datetime(df["pivot_time"]).astype(str).tolist()),
                anchor_prices="|".join(f"{value:.10g}" for value in prices.tolist()),
                cluster_tolerance=tolerance,
            )
        )

    for _, swing in side_swings.iterrows():
        item = swing.to_dict()
        if not cluster:
            cluster.append(item)
            continue
        current_prices = [float(row["price"]) for row in cluster]
        if abs(float(item["price"]) - (sum(current_prices) / len(current_prices))) <= tolerance:
            cluster.append(item)
        else:
            flush(cluster)
            cluster = [item]
    flush(cluster)
    return rows


def build_day_levels(ctx: BuildContext) -> list[dict[str, object]]:
    bars = ctx.bars.copy()
    rows: list[dict[str, object]] = []
    grouped = bars.groupby("utc_date", sort=True)
    for _, day in grouped:
        day = day.sort_values("close_time").copy()
        day["day_high_so_far"] = day["high"].cummax()
        day["day_low_so_far"] = day["low"].cummin()
        for _, bar in day.iterrows():
            width = max(float(bar["atr"]) * 0.03, float(bar["close"]) * 0.00005)
            rows.append(
                base_object(
                    ctx,
                    "current_day_high_so_far",
                    "resistance",
                    bar["close_time"],
                    bar["close_time"],
                    float(bar["day_high_so_far"]) - width,
                    float(bar["day_high_so_far"]) + width,
                    int(bar["bar_index"]),
                    day_date=bar["utc_date"],
                )
            )
            rows.append(
                base_object(
                    ctx,
                    "current_day_low_so_far",
                    "support",
                    bar["close_time"],
                    bar["close_time"],
                    float(bar["day_low_so_far"]) - width,
                    float(bar["day_low_so_far"]) + width,
                    int(bar["bar_index"]),
                    day_date=bar["utc_date"],
                )
            )

    daily = grouped.agg(day_high=("high", "max"), day_low=("low", "min"), last_close_time=("close_time", "max"))
    daily = daily.sort_index()
    dates = list(daily.index)
    for idx in range(1, len(dates)):
        current_date = dates[idx]
        prev = daily.iloc[idx - 1]
        available_at = pd.Timestamp(f"{current_date} 00:00:00", tz="UTC")
        latest_source = min(pd.Timestamp(prev["last_close_time"]), available_at)
        # The previous day level is known at the UTC day boundary; duplicate by HTF for easier joins.
        for object_type, side, price in [
            ("previous_day_high", "resistance", float(prev["day_high"])),
            ("previous_day_low", "support", float(prev["day_low"])),
        ]:
            width = max(price * 0.00005, 1e-12)
            rows.append(
                base_object(
                    ctx,
                    object_type,
                    side,
                    available_at,
                    latest_source,
                    price - width,
                    price + width,
                    -1,
                    day_date=current_date,
                    previous_day=dates[idx - 1],
                )
            )
    return rows


def line_projection(anchor_a: pd.Series, anchor_b: pd.Series, x: float) -> float:
    x1 = float(anchor_a["bar_index"])
    x2 = float(anchor_b["bar_index"])
    y1 = float(anchor_a["price"])
    y2 = float(anchor_b["price"])
    if x2 == x1:
        return y2
    slope = (y2 - y1) / (x2 - x1)
    return y1 + slope * (x - x1)


def detect_trendlines_for_side(ctx: BuildContext, swings: pd.DataFrame, side: str) -> list[dict[str, object]]:
    if swings.empty:
        return []
    pivots = swings[swings["side"] == side].sort_values("available_at").reset_index(drop=True)
    if len(pivots) < 2:
        return []
    bar_index = pivots["bar_index"].astype(float).to_numpy()
    prices = pivots["price"].astype(float).to_numpy()
    atrs = pivots["atr"].astype(float).to_numpy()
    rows: list[dict[str, object]] = []
    max_age = TRENDLINE_MAX_ANCHOR_AGE_BARS[ctx.timeframe]
    endpoint_step = TRENDLINE_ENDPOINT_STEP[ctx.timeframe]
    for end_pos in range(1, len(pivots)):
        if end_pos % endpoint_step != 0 and end_pos != len(pivots) - 1:
            continue
        candidates = []
        start_floor = max(0, end_pos - TRENDLINE_MAX_PRIOR_ANCHORS)
        for start_pos in range(start_floor, end_pos):
            age = int(bar_index[end_pos] - bar_index[start_pos])
            if age <= 0 or age > max_age:
                continue
            x1 = bar_index[start_pos]
            x2 = bar_index[end_pos]
            y1 = prices[start_pos]
            y2 = prices[end_pos]
            slope = (y2 - y1) / (x2 - x1)
            intercept = y1 - slope * x1
            slice_idx = slice(start_pos, end_pos + 1)
            local_x = bar_index[slice_idx]
            local_prices = prices[slice_idx]
            atr = max(float(np.median(atrs[slice_idx])), 1e-12)
            tolerance = max(atr * TRENDLINE_NEAR_ATR_MULTIPLIER, float(prices[end_pos]) * 0.001)
            projected = intercept + slope * local_x
            touch_count = int((np.abs(local_prices - projected) <= tolerance).sum())
            if touch_count < 2:
                continue
            span_atr = abs(y2 - y1) / atr
            slope_penalty = min(0.25, max(0.0, (span_atr / max(age, 1) - 0.2) * 0.1))
            touch_score = min(0.5, 0.22 + touch_count * 0.09)
            age_score = min(0.2, age / max_age * 0.2)
            recency_score = 0.2
            quality = max(0.0, min(1.0, touch_score + age_score + recency_score - slope_penalty))
            if quality < TRENDLINE_MIN_QUALITY:
                continue
            anchor_a = pivots.iloc[start_pos]
            anchor_b = pivots.iloc[end_pos]
            available_index = int(anchor_b["bar_index"]) + PIVOT_RIGHT
            projected_available = intercept + slope * available_index
            available_at = pd.Timestamp(anchor_b["available_at"])
            latest_source = pd.Timestamp(anchor_b["latest_source_candle_close_used"])
            anchor_times = [str(anchor_a["pivot_time"]), str(anchor_b["pivot_time"])]
            anchor_prices = [float(anchor_a["price"]), float(anchor_b["price"])]
            line_side = "support" if side == "support" else "resistance"
            trendline_id = stable_id(
                ctx.symbol,
                ctx.timeframe,
                line_side,
                anchor_times[0],
                anchor_times[-1],
                f"{slope:.12g}",
                f"{intercept:.12g}",
            )
            candidates.append(
                {
                    "trendline_id": trendline_id,
                    "object_id": trendline_id,
                    "symbol": ctx.symbol,
                    "timeframe": ctx.timeframe,
                    "object_type": "trendline",
                    "line_side": line_side,
                    "side": side,
                    "zone_low": float(projected_available - tolerance),
                    "zone_high": float(projected_available + tolerance),
                    "zone_mid": float(projected_available),
                    "price": float(projected_available),
                    "formed_at": pd.Timestamp(anchor_b["pivot_time"]),
                    "confirmed_at": available_at,
                    "available_at": available_at,
                    "latest_source_candle_close_used": latest_source,
                    "source_bar_index": int(anchor_b["bar_index"]),
                    "anchor_count": touch_count,
                    "anchor_times": "|".join(anchor_times),
                    "anchor_available_times": "|".join([str(anchor_a["available_at"]), str(anchor_b["available_at"])]),
                    "anchor_prices": "|".join(f"{value:.10g}" for value in anchor_prices),
                    "slope": float(slope),
                    "intercept": float(intercept),
                    "projected_price_at_available": float(projected_available),
                    "line_quality_score": float(quality),
                    "trendline_interaction_type": "none",
                    "trendline_pa_zone_score": float(quality),
                    "trendline_zone_confluence_count": 0,
                    "sr_trendline_overlap": False,
                    "fvg_trendline_overlap": False,
                    "liquidity_trendline_overlap": False,
                    "htf_trendline_4h": trendline_id if ctx.timeframe == "4h" else "",
                    "htf_trendline_1h": trendline_id if ctx.timeframe == "1h" else "",
                    "htf_trendline_15m": trendline_id if ctx.timeframe == "15m" else "",
                    "lookahead_pass": latest_source <= available_at,
                    "lookahead_violation_reason": "" if latest_source <= available_at else "latest_source_after_available_at",
                    "tolerance": float(tolerance),
                    "available_bar_index": available_index,
                }
            )
        candidates.sort(key=lambda item: item["line_quality_score"], reverse=True)
        rows.extend(candidates[:TRENDLINE_TOP_PER_ANCHOR])
    return rows


def detect_trendline_interactions(ctx: BuildContext, trendlines: list[dict[str, object]]) -> list[dict[str, object]]:
    bars = ctx.bars.reset_index(drop=True)
    if not trendlines or bars.empty:
        return []
    rows: list[dict[str, object]] = []
    max_forward = TRENDLINE_INTERACTION_BARS[ctx.timeframe]
    for line in trendlines:
        start_idx = int(line["available_bar_index"])
        end_idx = min(len(bars) - 1, start_idx + max_forward)
        if start_idx >= len(bars):
            continue
        seen: set[str] = set()
        clean_break_side = ""
        for idx in range(start_idx, end_idx + 1):
            bar = bars.iloc[idx]
            projected = float(line["intercept"]) + float(line["slope"]) * float(bar["bar_index"])
            tolerance = float(line["tolerance"])
            atr = max(float(bar["atr"]), 1e-12)
            high = float(bar["high"])
            low = float(bar["low"])
            close = float(bar["close"])
            open_ = float(bar["open"])
            body = abs(close - open_)
            side = str(line["side"])
            line_side = str(line["line_side"])
            near = low - tolerance <= projected <= high + tolerance
            sweep = False
            clean_break = False
            rejection = False
            break_retest = False
            if side == "resistance":
                sweep = high > projected + tolerance and close < projected
                clean_break = close > projected + tolerance
                rejection = near and close < projected and close < open_ and body >= atr * 0.20
                break_retest = clean_break_side == "up" and low <= projected + tolerance and close >= projected
            else:
                sweep = low < projected - tolerance and close > projected
                clean_break = close < projected - tolerance
                rejection = near and close > projected and close > open_ and body >= atr * 0.20
                break_retest = clean_break_side == "down" and high >= projected - tolerance and close <= projected

            candidates = []
            if near:
                candidates.append("near_touch")
            if sweep:
                candidates.append("sweep")
            if rejection:
                candidates.append("rejection")
            if clean_break:
                candidates.append("clean_break")
                clean_break_side = "up" if side == "resistance" else "down"
            if break_retest:
                candidates.append("break_retest")

            for interaction in candidates:
                if interaction in seen:
                    continue
                seen.add(interaction)
                available_at = pd.Timestamp(bar["close_time"])
                latest_source = available_at
                trendline_id = str(line["trendline_id"])
                object_id = stable_id(trendline_id, interaction, available_at)
                rows.append(
                    {
                        **line,
                        "object_id": object_id,
                        "parent_trendline_id": trendline_id,
                        "object_type": "trendline_interaction",
                        "trendline_interaction_type": interaction,
                        "available_at": available_at,
                        "confirmed_at": available_at,
                        "latest_source_candle_close_used": latest_source,
                        "source_bar_index": int(bar["bar_index"]),
                        "projected_price_at_available": projected,
                        "price": projected,
                        "zone_low": projected - tolerance,
                        "zone_high": projected + tolerance,
                        "zone_mid": projected,
                        "lookahead_pass": latest_source <= available_at,
                        "lookahead_violation_reason": "" if latest_source <= available_at else "latest_source_after_available_at",
                    }
                )
            if len(seen) >= 5:
                break
    return rows


def attach_trendline_confluence(trendlines: pd.DataFrame, htf_zones: pd.DataFrame) -> pd.DataFrame:
    if trendlines.empty or htf_zones.empty:
        return trendlines
    trendlines = trendlines.copy()
    zone_groups = {}
    for key, group in htf_zones.groupby(["symbol", "timeframe"]):
        sorted_group = group.sort_values("available_at").reset_index(drop=True)
        available_values = pd.to_datetime(sorted_group["available_at"], utc=True).values
        zone_groups[key] = (sorted_group, available_values)
    confluence_by_line: dict[str, dict[str, object]] = {}
    base_lines = trendlines[trendlines["object_type"] == "trendline"]
    for idx, line in base_lines.iterrows():
        key = (line["symbol"], line["timeframe"])
        cached = zone_groups.get(key)
        if cached is None:
            continue
        zones, available_values = cached
        if zones.empty:
            continue
        line_available = pd.Timestamp(line["available_at"]).to_datetime64()
        pos = int(np.searchsorted(available_values, line_available, side="right"))
        prior = zones.iloc[max(0, pos - 300) : pos]
        if prior.empty:
            continue
        tolerance = max(float(line.get("tolerance", 0.0) or 0.0), abs(float(line["price"])) * 0.001)
        overlaps = (prior["zone_low"].astype(float) <= float(line["zone_high"]) + tolerance) & (
            prior["zone_high"].astype(float) >= float(line["zone_low"]) - tolerance
        )
        overlap_zones = prior[overlaps]
        sr = overlap_zones["object_type"].astype(str).str.startswith("sr_").any()
        fvg = overlap_zones["object_type"].astype(str).str.startswith("fvg_").any()
        liq = overlap_zones["object_type"].astype(str).str.contains("liquidity").any()
        count = int(sr) + int(fvg) + int(liq)
        trendlines.at[idx, "sr_trendline_overlap"] = bool(sr)
        trendlines.at[idx, "fvg_trendline_overlap"] = bool(fvg)
        trendlines.at[idx, "liquidity_trendline_overlap"] = bool(liq)
        trendlines.at[idx, "trendline_zone_confluence_count"] = count
        trendlines.at[idx, "trendline_pa_zone_score"] = min(1.0, float(line["line_quality_score"]) + count * 0.12)
        confluence_by_line[str(line["trendline_id"])] = {
            "sr_trendline_overlap": bool(sr),
            "fvg_trendline_overlap": bool(fvg),
            "liquidity_trendline_overlap": bool(liq),
            "trendline_zone_confluence_count": count,
            "trendline_pa_zone_score": min(1.0, float(line["line_quality_score"]) + count * 0.12),
        }
    if confluence_by_line:
        inherited_ids = trendlines.get("parent_trendline_id", trendlines.get("trendline_id")).fillna(trendlines["trendline_id"])
        for idx, trendline_id in inherited_ids.items():
            values = confluence_by_line.get(str(trendline_id))
            if not values:
                continue
            for column, value in values.items():
                trendlines.at[idx, column] = value
    return trendlines


def build_for_symbol_timeframe(symbol: str, timeframe: str, df_1m: pd.DataFrame) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    bars = resample_ohlcv(df_1m, timeframe)
    ctx = BuildContext(symbol=symbol, timeframe=timeframe, bars=bars)
    print(f"  bars={len(bars)}", flush=True)
    fvg_rows = detect_fvg(ctx)
    print(f"  fvg={len(fvg_rows)}", flush=True)
    swing_rows, swings = detect_swings(ctx)
    print(f"  swings={len(swing_rows)}", flush=True)
    sr_rows = [
        *cluster_price_objects(ctx, swings, "sr_resistance", "resistance"),
        *cluster_price_objects(ctx, swings, "sr_support", "support"),
    ]
    print(f"  sr={len(sr_rows)}", flush=True)
    liquidity_rows = [
        *cluster_price_objects(ctx, swings, "liquidity_equal_highs", "resistance"),
        *cluster_price_objects(ctx, swings, "liquidity_equal_lows", "support"),
    ]
    print(f"  liquidity={len(liquidity_rows)}", flush=True)
    day_rows = build_day_levels(ctx)
    print(f"  day_levels={len(day_rows)}", flush=True)
    zone_rows = [*fvg_rows, *swing_rows, *sr_rows, *liquidity_rows, *day_rows]
    trendline_rows = [
        *detect_trendlines_for_side(ctx, swings, "support"),
        *detect_trendlines_for_side(ctx, swings, "resistance"),
    ]
    print(f"  trendlines={len(trendline_rows)}", flush=True)
    interaction_rows = detect_trendline_interactions(ctx, trendline_rows)
    print(f"  interactions={len(interaction_rows)}", flush=True)
    summary = {
        "symbol": symbol,
        "timeframe": timeframe,
        "bars": len(bars),
        "fvg_zones": len(fvg_rows),
        "swings": len(swing_rows),
        "sr_zones": len(sr_rows),
        "liquidity_pools": len(liquidity_rows),
        "day_levels": len(day_rows),
        "trendlines": len(trendline_rows),
        "trendline_interactions": len(interaction_rows),
    }
    return zone_rows, [*trendline_rows, *interaction_rows], summary


def normalize_datetimes(df: pd.DataFrame) -> pd.DataFrame:
    for column in ["formed_at", "confirmed_at", "available_at", "latest_source_candle_close_used", "pivot_time", "pivot_available_at"]:
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], utc=True, errors="coerce")
    return df


def build_audit(htf_zones: pd.DataFrame, trendlines: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "object_id",
        "symbol",
        "timeframe",
        "object_type",
        "available_at",
        "latest_source_candle_close_used",
        "lookahead_pass",
        "lookahead_violation_reason",
    ]
    frames = []
    for df in [htf_zones, trendlines]:
        if not df.empty:
            frames.append(df[cols].copy())
    if not frames:
        return pd.DataFrame(columns=cols)
    audit = pd.concat(frames, ignore_index=True)
    audit["available_at"] = pd.to_datetime(audit["available_at"], utc=True)
    audit["latest_source_candle_close_used"] = pd.to_datetime(audit["latest_source_candle_close_used"], utc=True)
    audit["lookahead_pass"] = audit["latest_source_candle_close_used"] <= audit["available_at"]
    audit.loc[audit["lookahead_pass"], "lookahead_violation_reason"] = ""
    audit.loc[~audit["lookahead_pass"], "lookahead_violation_reason"] = "latest_source_after_available_at"
    return audit


def markdown_table(rows: Iterable[dict[str, object]], columns: list[str]) -> list[str]:
    rows = list(rows)
    if not rows:
        return ["_No rows._"]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return lines


def write_report(summaries: list[dict[str, object]], htf_zones: pd.DataFrame, trendlines: pd.DataFrame, audit: pd.DataFrame) -> None:
    total_rows = len(htf_zones) + len(trendlines)
    violations = int((~audit["lookahead_pass"]).sum()) if not audit.empty else 0
    object_counts = (
        htf_zones.groupby("object_type").size().sort_values(ascending=False).reset_index(name="rows").to_dict("records")
        if not htf_zones.empty
        else []
    )
    trendline_counts = (
        trendlines.groupby("object_type").size().sort_values(ascending=False).reset_index(name="rows").to_dict("records")
        if not trendlines.empty
        else []
    )
    interaction_counts = (
        trendlines.groupby("trendline_interaction_type").size().sort_values(ascending=False).reset_index(name="rows").to_dict("records")
        if not trendlines.empty and "trendline_interaction_type" in trendlines.columns
        else []
    )
    lines = [
        "# Craig v1.2 HTF Zone + Trendline Build Report",
        "",
        "Generated by `scripts/build_craig_v1_2_htf_zones.py`.",
        "",
        "## Verdict",
        "",
        "- HTF PA-zone registry built with event-time `available_at` fields.",
        "- Trendline interactions are represented as event rows, not hindsight labels smeared onto earlier candles.",
        f"- Lookahead violations: {violations}.",
        "",
        "## Inputs",
        "",
        "- Source: normalized continuous Binance USD-M 1m parquet files under `data/processed/binance_futures_continuous/<symbol>/1m/`.",
        "- HTF bars: 15m, 1h, and 4h resampled from complete 1m candles only.",
        "- No gold labels, result R, Craig action, future outcome, or strategy PnL fields are read.",
        "",
        "## Build Summary",
        "",
        *markdown_table(
            summaries,
            [
                "symbol",
                "timeframe",
                "bars",
                "fvg_zones",
                "swings",
                "sr_zones",
                "liquidity_pools",
                "day_levels",
                "trendlines",
                "trendline_interactions",
            ],
        ),
        "",
        "## HTF Object Counts",
        "",
        *markdown_table(object_counts, ["object_type", "rows"]),
        "",
        "## Trendline Object Counts",
        "",
        *markdown_table(trendline_counts, ["object_type", "rows"]),
        "",
        "## Trendline Interaction Distribution",
        "",
        *markdown_table(interaction_counts, ["trendline_interaction_type", "rows"]),
        "",
        "## No-Lookahead Controls",
        "",
        "- FVG zones become available only at the third candle close.",
        "- Swing highs/lows use `left=3/right=3`; pivot rows become available only after the right-side confirmation candle closes.",
        "- SR zones and equal-high/low liquidity pools are built from confirmed swing anchors; `available_at` is the latest anchor availability in the object.",
        "- Current day high/low rows are cumulative `so_far` rows through each closed HTF candle, not final-day extrema.",
        "- Previous day high/low is available only after the prior UTC day has fully closed.",
        "- Trendline candidates use confirmed swing anchors only. Later anchors create new line IDs rather than rewriting earlier rows.",
        "- `near_touch`, `sweep`, `break_retest`, `rejection`, and `clean_break` are event rows with their own `available_at`.",
        "",
        "## Outputs",
        "",
        f"- HTF zones: `{rel(HTF_ZONES_PARQUET)}`",
        f"- Trendline zones/events: `{rel(TRENDLINE_ZONES_PARQUET)}`",
        f"- Audit CSV: `{rel(AUDIT_CSV)}`",
        "",
        "## Next Step Recommendation",
        "",
        "Build the BTC context engine next. It can now consume the same SR/FVG/liquidity/trendline registry for BTC PA-zone interpretation, while the target pool generator should wait until BTC warnings/vetoes and leader context are available.",
    ]
    BUILD_REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=CORE_SYMBOLS)
    parser.add_argument("--timeframes", nargs="+", default=TIMEFRAMES)
    parser.add_argument("--start-date", default="2024-01-01")
    parser.add_argument("--end-date", default="2026-08-23")
    args = parser.parse_args()

    all_zone_rows: list[dict[str, object]] = []
    all_trendline_rows: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    for symbol in [value.upper() for value in args.symbols]:
        print(f"load_1m symbol={symbol}", flush=True)
        df_1m = load_1m(symbol, args.start_date, args.end_date)
        for timeframe in args.timeframes:
            print(f"build symbol={symbol} timeframe={timeframe}", flush=True)
            zone_rows, trendline_rows, summary = build_for_symbol_timeframe(symbol, timeframe, df_1m)
            all_zone_rows.extend(zone_rows)
            all_trendline_rows.extend(trendline_rows)
            summaries.append(summary)
            print(
                f"done symbol={symbol} timeframe={timeframe} zones={len(zone_rows)} trendline_rows={len(trendline_rows)}",
                flush=True,
            )

    print("materialize dataframes", flush=True)
    htf_zones = normalize_datetimes(pd.DataFrame(all_zone_rows))
    trendlines = normalize_datetimes(pd.DataFrame(all_trendline_rows))
    print(f"attach confluence trendline_rows={len(trendlines)} htf_zone_rows={len(htf_zones)}", flush=True)
    trendlines = attach_trendline_confluence(trendlines, htf_zones)
    print("build audit", flush=True)
    audit = build_audit(htf_zones, trendlines)
    if not audit.empty and not audit["lookahead_pass"].all():
        failures = int((~audit["lookahead_pass"]).sum())
        raise RuntimeError(f"HTF zone lookahead audit failed for {failures} rows")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("write outputs", flush=True)
    htf_zones.to_parquet(HTF_ZONES_PARQUET, index=False)
    trendlines.to_parquet(TRENDLINE_ZONES_PARQUET, index=False)
    audit.to_csv(AUDIT_CSV, index=False, encoding="utf-8-sig")
    write_report(summaries, htf_zones, trendlines, audit)
    print(f"htf_zones={HTF_ZONES_PARQUET} rows={len(htf_zones)}")
    print(f"trendline_zones={TRENDLINE_ZONES_PARQUET} rows={len(trendlines)}")
    print(f"audit={AUDIT_CSV} rows={len(audit)} lookahead_pass={int(audit['lookahead_pass'].sum())}/{len(audit)}")
    print(f"report={BUILD_REPORT_MD}")


if __name__ == "__main__":
    main()
