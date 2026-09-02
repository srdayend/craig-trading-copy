#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROCESSED_ROOT = ROOT / "data/processed/binance_futures_continuous"
HTF_ZONES_PARQUET = ROOT / "outputs/craig_v1_2_htf_zones.parquet"
TRENDLINE_ZONES_PARQUET = ROOT / "outputs/craig_v1_2_trendline_zones.parquet"
BTC_CONTEXT_PARQUET = ROOT / "outputs/craig_v1_2_btc_context_snapshots.parquet"
OUT_TARGETS = ROOT / "outputs/craig_v1_2_target_pools.parquet"
OUT_SUMMARY = ROOT / "outputs/craig_v1_2_target_pool_summary.parquet"
OUT_AUDIT = ROOT / "outputs/craig_v1_2_target_pool_audit.csv"
OUT_REPORT = ROOT / "outputs/craig_v1_2_target_pool_build_report.md"

HEADLINE_SYMBOLS = ["SOLUSDT", "ETHUSDT"]
TIMEFRAME_MINUTES = {"15m": 15, "1h": 60, "4h": 240}
RESAMPLE_RULES = {"15m": "15T", "1h": "1H", "4h": "4H"}
TIMEFRAME_SCORE_BONUS = {"15m": 0.04, "1h": 0.10, "4h": 0.16}
TIMEFRAME_PRIORITY = {"4h": 0, "1h": 1, "15m": 2}
ATR_PERIOD = 14
MAX_TARGETS_PER_SIDE = 12
VISIBLE_TAIL = {
    "nearest_15m_unmitigated_fvg_mid": 160,
    "next_15m_fvg": 160,
    "next_1h_fvg": 130,
    "15m_sr_zone": 120,
    "1h_sr_zone": 120,
    "4h_sr_zone": 100,
    "day_high_low": 120,
    "previous_day_high_low": 120,
    "liquidity_pool": 140,
}
TRENDLINE_TAIL = {"15m": 80, "1h": 70, "4h": 60}
LOOKBACK_BY_TIMEFRAME = {
    "15m": pd.Timedelta(days=21),
    "1h": pd.Timedelta(days=90),
    "4h": pd.Timedelta(days=360),
}
FRESH_BY_TIMEFRAME = {
    "15m": pd.Timedelta(days=3),
    "1h": pd.Timedelta(days=14),
    "4h": pd.Timedelta(days=45),
}
ACTIVE_BY_TIMEFRAME = {
    "15m": pd.Timedelta(days=14),
    "1h": pd.Timedelta(days=60),
    "4h": pd.Timedelta(days=180),
}
TARGET_SOURCES = {
    "nearest_15m_unmitigated_fvg_mid",
    "15m_sr_zone",
    "1h_sr_zone",
    "4h_sr_zone",
    "day_high_low",
    "previous_day_high_low",
    "next_15m_fvg",
    "next_1h_fvg",
    "liquidity_pool",
    "trendline_projection",
    "fixed_R_placeholder",
    "none",
}
FAR_FUTURE_NS = pd.Timestamp("2262-04-11 00:00:00", tz="UTC").value


@dataclass(frozen=True)
class SourceTable:
    target_source: str
    target_side: str
    table: pd.DataFrame
    available_values: np.ndarray
    arrays: dict[str, np.ndarray]


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def stable_id(*parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def utc_timestamp(value: object) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def ns_to_utc(ns: int | np.integer) -> pd.Timestamp:
    return pd.Timestamp(int(ns), unit="ns", tz="UTC")


def compute_atr(bars: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    high_low = bars["high"] - bars["low"]
    high_close = (bars["high"] - bars["close"].shift(1)).abs()
    low_close = (bars["low"] - bars["close"].shift(1)).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=1).mean()


def resample_ohlcv(df_1m: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    minutes = TIMEFRAME_MINUTES[timeframe]
    grouped = df_1m.set_index("timestamp").sort_index().resample(
        RESAMPLE_RULES[timeframe], label="left", closed="left"
    )
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
    bars["bar_index"] = np.arange(len(bars))
    bars["atr"] = compute_atr(bars)
    bars["close_time_ns"] = pd.to_datetime(bars["close_time"], utc=True).astype("int64")
    bars.attrs["close_time_ns_values"] = bars["close_time_ns"].to_numpy(dtype="int64")
    bars.attrs["bar_index_values"] = bars["bar_index"].to_numpy(dtype="float64")
    return bars


def find_symbol_parquet(symbol: str) -> Path:
    candidates = sorted((PROCESSED_ROOT / symbol / "1m").glob(f"{symbol}_1m_*.parquet"))
    if not candidates:
        raise FileNotFoundError(f"No normalized continuous parquet found for {symbol}")
    return candidates[-1]


def load_symbol_bars(symbol: str) -> dict[str, pd.DataFrame]:
    path = find_symbol_parquet(symbol)
    df = pd.read_parquet(path, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")
    df = df.drop_duplicates("timestamp", keep="last").reset_index(drop=True)
    return {timeframe: resample_ohlcv(df, timeframe) for timeframe in ["15m", "1h", "4h"]}


def source_base_quality(target_source: str) -> float:
    return {
        "nearest_15m_unmitigated_fvg_mid": 0.78,
        "next_15m_fvg": 0.70,
        "next_1h_fvg": 0.76,
        "15m_sr_zone": 0.70,
        "1h_sr_zone": 0.76,
        "4h_sr_zone": 0.82,
        "day_high_low": 0.62,
        "previous_day_high_low": 0.68,
        "liquidity_pool": 0.72,
        "trendline_projection": 0.74,
        "fixed_R_placeholder": 0.0,
    }.get(target_source, 0.0)


def freshness_state(available_at: pd.Timestamp, decision_timestamp: pd.Timestamp, timeframe: str, fvg_unmitigated: bool = False) -> str:
    if fvg_unmitigated:
        return "unmitigated"
    age = decision_timestamp - available_at
    if age <= FRESH_BY_TIMEFRAME.get(timeframe, pd.Timedelta(days=7)):
        return "fresh"
    if age <= ACTIVE_BY_TIMEFRAME.get(timeframe, pd.Timedelta(days=30)):
        return "active"
    return "stale"


def target_quality(target_source: str, timeframe: str, freshness: str, distance_atr: float, trendline_score: float = 0.0) -> float:
    quality = source_base_quality(target_source) + TIMEFRAME_SCORE_BONUS.get(timeframe, 0.0)
    if freshness == "fresh":
        quality += 0.07
    elif freshness == "unmitigated":
        quality += 0.08
    elif freshness == "stale":
        quality -= 0.12
    if distance_atr < 0.25:
        quality -= 0.25
    elif 0.8 <= distance_atr <= 5.0:
        quality += 0.05
    if target_source == "trendline_projection":
        quality = max(quality, 0.50 + min(0.35, trendline_score * 0.35))
    return float(max(0.0, min(1.0, quality)))


def reaction_risk(target_source: str, timeframe: str, distance_atr: float) -> float:
    risk = 0.20
    if target_source in {"4h_sr_zone", "1h_sr_zone", "liquidity_pool", "previous_day_high_low"}:
        risk += 0.22
    if target_source in {"nearest_15m_unmitigated_fvg_mid", "next_1h_fvg"}:
        risk += 0.12
    if target_source == "trendline_projection":
        risk += 0.18
    if timeframe == "4h":
        risk += 0.12
    elif timeframe == "1h":
        risk += 0.07
    if distance_atr < 0.35:
        risk += 0.25
    return float(max(0.0, min(1.0, risk)))


def add_fvg_mitigation_times(zones: pd.DataFrame, bars_by_symbol: dict[str, dict[str, pd.DataFrame]]) -> pd.DataFrame:
    zones = zones.copy()
    zones["first_mitigated_at"] = pd.NaT
    fvg_mask = zones["object_type"].isin(["fvg_bearish", "fvg_bullish"])
    if not fvg_mask.any():
        return zones
    for (symbol, timeframe), idxs in zones[fvg_mask].groupby(["symbol", "timeframe"]).groups.items():
        bars = bars_by_symbol.get(symbol, {}).get(timeframe)
        if bars is None or bars.empty:
            continue
        close_times = bars["close_time"].values
        highs = bars["high"].astype(float).to_numpy()
        lows = bars["low"].astype(float).to_numpy()
        for idx in idxs:
            row = zones.loc[idx]
            start = int(np.searchsorted(close_times, pd.Timestamp(row["available_at"]).to_datetime64(), side="right"))
            if start >= len(bars):
                continue
            target_mid = float(row["zone_mid"])
            if row["object_type"] == "fvg_bearish":
                touched = highs[start:] >= target_mid
            else:
                touched = lows[start:] <= target_mid
            if touched.any():
                zones.at[idx, "first_mitigated_at"] = utc_timestamp(close_times[start + int(np.argmax(touched))])
    return zones


def prepare_static_source_tables(zones: pd.DataFrame, symbols: list[str]) -> dict[tuple[str, str, str], SourceTable]:
    rows = zones[zones["symbol"].isin(symbols)].copy()
    rows["available_at"] = pd.to_datetime(rows["available_at"], utc=True)
    rows["latest_source_candle_close_used"] = pd.to_datetime(rows["latest_source_candle_close_used"], utc=True)
    rows["target_mid"] = rows["zone_mid"].astype(float)
    rows["target_price"] = rows["zone_mid"].astype(float)
    records = []

    def append(mask: pd.Series, target_source: str, target_side: str) -> None:
        subset = rows[mask].copy()
        if subset.empty:
            return
        subset["target_source"] = target_source
        subset["target_side"] = target_side
        records.append(subset)

    append((rows["object_type"] == "fvg_bearish") & (rows["timeframe"] == "15m"), "nearest_15m_unmitigated_fvg_mid", "above")
    append((rows["object_type"] == "fvg_bearish") & (rows["timeframe"] == "15m"), "next_15m_fvg", "above")
    append((rows["object_type"] == "fvg_bearish") & (rows["timeframe"] == "1h"), "next_1h_fvg", "above")
    append((rows["object_type"] == "fvg_bullish") & (rows["timeframe"] == "15m"), "nearest_15m_unmitigated_fvg_mid", "below")
    append((rows["object_type"] == "fvg_bullish") & (rows["timeframe"] == "15m"), "next_15m_fvg", "below")
    append((rows["object_type"] == "fvg_bullish") & (rows["timeframe"] == "1h"), "next_1h_fvg", "below")

    append((rows["object_type"] == "sr_resistance") & (rows["timeframe"] == "15m"), "15m_sr_zone", "above")
    append((rows["object_type"] == "sr_resistance") & (rows["timeframe"] == "1h"), "1h_sr_zone", "above")
    append((rows["object_type"] == "sr_resistance") & (rows["timeframe"] == "4h"), "4h_sr_zone", "above")
    append((rows["object_type"] == "sr_support") & (rows["timeframe"] == "15m"), "15m_sr_zone", "below")
    append((rows["object_type"] == "sr_support") & (rows["timeframe"] == "1h"), "1h_sr_zone", "below")
    append((rows["object_type"] == "sr_support") & (rows["timeframe"] == "4h"), "4h_sr_zone", "below")

    append((rows["object_type"] == "current_day_high_so_far") & (rows["timeframe"] == "15m"), "day_high_low", "above")
    append((rows["object_type"] == "current_day_low_so_far") & (rows["timeframe"] == "15m"), "day_high_low", "below")
    append((rows["object_type"] == "previous_day_high") & (rows["timeframe"] == "15m"), "previous_day_high_low", "above")
    append((rows["object_type"] == "previous_day_low") & (rows["timeframe"] == "15m"), "previous_day_high_low", "below")

    append(rows["object_type"].eq("liquidity_equal_highs"), "liquidity_pool", "above")
    append(rows["object_type"].eq("liquidity_equal_lows"), "liquidity_pool", "below")

    if not records:
        return {}
    all_rows = pd.concat(records, ignore_index=True).sort_values("available_at").reset_index(drop=True)
    source_tables: dict[tuple[str, str, str], SourceTable] = {}
    keep_cols = [
        "object_id",
        "symbol",
        "timeframe",
        "object_type",
        "target_source",
        "target_side",
        "zone_low",
        "zone_high",
        "target_price",
        "target_mid",
        "available_at",
        "latest_source_candle_close_used",
        "first_mitigated_at",
    ]
    for key, group in all_rows[keep_cols].groupby(["symbol", "target_source", "target_side"]):
        group = group.sort_values("available_at").reset_index(drop=True)
        group["_available_ns"] = pd.to_datetime(group["available_at"], utc=True).astype("int64")
        group["_latest_ns"] = pd.to_datetime(group["latest_source_candle_close_used"], utc=True).astype("int64")
        mitigated = pd.to_datetime(group["first_mitigated_at"], utc=True, errors="coerce")
        group["_first_mitigated_ns"] = mitigated.astype("int64")
        group.loc[mitigated.isna(), "_first_mitigated_ns"] = FAR_FUTURE_NS
        arrays = {
            "object_id": group["object_id"].astype(str).to_numpy(),
            "timeframe": group["timeframe"].astype(str).to_numpy(),
            "object_type": group["object_type"].astype(str).to_numpy(),
            "zone_low": group["zone_low"].astype(float).to_numpy(),
            "zone_high": group["zone_high"].astype(float).to_numpy(),
            "target_price": group["target_price"].astype(float).to_numpy(),
            "target_mid": group["target_mid"].astype(float).to_numpy(),
            "available_ns": group["_available_ns"].to_numpy(dtype="int64"),
            "latest_ns": group["_latest_ns"].to_numpy(dtype="int64"),
            "first_mitigated_ns": group["_first_mitigated_ns"].to_numpy(dtype="int64"),
            "lookback_ns": np.array(
                [LOOKBACK_BY_TIMEFRAME.get(str(tf), pd.Timedelta(days=30)).value for tf in group["timeframe"]],
                dtype="int64",
            ),
        }
        source_tables[key] = SourceTable(
            target_source=key[1],
            target_side=key[2],
            table=group,
            available_values=group["_available_ns"].to_numpy(dtype="int64"),
            arrays=arrays,
        )
    return source_tables


def prepare_trendline_tables(trendlines: pd.DataFrame, symbols: list[str]) -> dict[tuple[str, str], SourceTable]:
    rows = trendlines[
        trendlines["symbol"].isin(symbols) & trendlines["object_type"].eq("trendline")
    ].copy()
    if rows.empty:
        return {}
    rows["available_at"] = pd.to_datetime(rows["available_at"], utc=True)
    rows["latest_source_candle_close_used"] = pd.to_datetime(rows["latest_source_candle_close_used"], utc=True)
    rows["target_source"] = "trendline_projection"
    rows["target_side"] = np.where(rows["line_side"].eq("resistance"), "above", "below")
    tables: dict[tuple[str, str], SourceTable] = {}
    keep_cols = [
        "object_id",
        "trendline_id",
        "symbol",
        "timeframe",
        "line_side",
        "target_source",
        "target_side",
        "available_at",
        "latest_source_candle_close_used",
        "slope",
        "intercept",
        "tolerance",
        "line_quality_score",
        "trendline_pa_zone_score",
    ]
    for key, group in rows[keep_cols].groupby(["symbol", "target_side"]):
        group = group.sort_values("available_at").reset_index(drop=True)
        group["_available_ns"] = pd.to_datetime(group["available_at"], utc=True).astype("int64")
        group["_latest_ns"] = pd.to_datetime(group["latest_source_candle_close_used"], utc=True).astype("int64")
        arrays = {
            "object_id": group["object_id"].astype(str).to_numpy(),
            "timeframe": group["timeframe"].astype(str).to_numpy(),
            "line_side": group["line_side"].astype(str).to_numpy(),
            "available_ns": group["_available_ns"].to_numpy(dtype="int64"),
            "latest_ns": group["_latest_ns"].to_numpy(dtype="int64"),
            "slope": group["slope"].astype(float).to_numpy(),
            "intercept": group["intercept"].astype(float).to_numpy(),
            "tolerance": group["tolerance"].astype(float).fillna(0.0).to_numpy(),
            "line_quality_score": group["line_quality_score"].astype(float).fillna(0.0).to_numpy(),
            "trendline_pa_zone_score": group["trendline_pa_zone_score"].astype(float).fillna(0.0).to_numpy(),
        }
        tables[key] = SourceTable(
            "trendline_projection",
            key[1],
            group,
            group["_available_ns"].to_numpy(dtype="int64"),
            arrays=arrays,
        )
    return tables


def pick_static_candidate(
    source_table: SourceTable,
    decision_timestamp: pd.Timestamp,
    side: str,
    reference_price: float,
    atr: float,
    skip_object_ids: set[str] | None = None,
) -> dict[str, object] | None:
    _ = side
    skip_object_ids = skip_object_ids or set()
    decision_ns = utc_timestamp(decision_timestamp).value
    pos = int(np.searchsorted(source_table.available_values, decision_ns, side="right"))
    if pos <= 0:
        return None
    tail = VISIBLE_TAIL.get(source_table.target_source, 120)
    start = max(0, pos - tail)
    if start >= pos:
        return None
    sl = slice(start, pos)
    arrays = source_table.arrays
    available_ns = arrays["available_ns"][sl]
    lookbacks = arrays["lookback_ns"][sl]
    target_prices = arrays["target_price"][sl]
    eligible = np.isfinite(target_prices) & (available_ns >= decision_ns - lookbacks)
    if source_table.target_side == "above":
        eligible = eligible & (target_prices > reference_price)
        distances = target_prices - reference_price
    else:
        eligible = eligible & (target_prices < reference_price)
        distances = reference_price - target_prices
    if source_table.target_source == "nearest_15m_unmitigated_fvg_mid":
        eligible = eligible & (arrays["first_mitigated_ns"][sl] > decision_ns)
    if skip_object_ids:
        eligible = eligible & (~np.isin(arrays["object_id"][sl], list(skip_object_ids)))
    if not eligible.any():
        return None
    eligible_positions = np.where(eligible)[0]
    best_local = int(eligible_positions[int(np.argmin(distances[eligible_positions]))])
    best_idx = start + best_local
    timeframe = str(arrays["timeframe"][best_idx])
    target_price = float(arrays["target_price"][best_idx])
    distance_abs = float(abs(target_price - reference_price))
    distance_atr = float(distance_abs / atr) if atr > 0 else np.nan
    fvg_unmitigated = source_table.target_source == "nearest_15m_unmitigated_fvg_mid"
    available_at = ns_to_utc(arrays["available_ns"][best_idx])
    freshness = freshness_state(available_at, decision_timestamp, timeframe, fvg_unmitigated)
    quality = target_quality(source_table.target_source, timeframe, freshness, distance_atr)
    return {
        "source_object_id": str(arrays["object_id"][best_idx]),
        "target_source": source_table.target_source,
        "target_timeframe": timeframe,
        "target_side": source_table.target_side,
        "zone_low": float(arrays["zone_low"][best_idx]),
        "zone_high": float(arrays["zone_high"][best_idx]),
        "target_price": target_price,
        "target_mid": float(arrays["target_mid"][best_idx]),
        "available_at": available_at,
        "latest_source_candle_close_used": ns_to_utc(arrays["latest_ns"][best_idx]),
        "freshness_state": freshness,
        "distance_abs": distance_abs,
        "distance_pct": float(distance_abs / reference_price) if reference_price else np.nan,
        "distance_atr": distance_atr,
        "target_quality_score": quality,
        "opposing_reaction_risk": reaction_risk(source_table.target_source, timeframe, distance_atr),
    }


def pick_trendline_candidate(
    source_table: SourceTable,
    bars_by_timeframe: dict[str, pd.DataFrame],
    decision_timestamp: pd.Timestamp,
    reference_price: float,
    atr: float,
) -> dict[str, object] | None:
    decision_ns = utc_timestamp(decision_timestamp).value
    pos = int(np.searchsorted(source_table.available_values, decision_ns, side="right"))
    if pos <= 0:
        return None
    start = max(0, pos - max(TRENDLINE_TAIL.values()))
    if start >= pos:
        return None
    sl = slice(start, pos)
    arrays = source_table.arrays
    candidates: list[dict[str, object]] = []
    for timeframe in ["15m", "1h", "4h"]:
        tf_local = np.where(arrays["timeframe"][sl] == timeframe)[0]
        if len(tf_local) == 0:
            continue
        bars = bars_by_timeframe.get(timeframe)
        if bars is None or bars.empty:
            continue
        close_time_ns = bars.attrs.get("close_time_ns_values")
        bar_index_values = bars.attrs.get("bar_index_values")
        if close_time_ns is None:
            close_time_ns = bars["close_time_ns"].to_numpy(dtype="int64")
        if bar_index_values is None:
            bar_index_values = bars["bar_index"].to_numpy(dtype="float64")
        bar_pos = int(np.searchsorted(close_time_ns, decision_ns, side="right")) - 1
        if bar_pos < 0:
            continue
        bar_index = float(bar_index_values[bar_pos])
        absolute_idx = start + tf_local
        available_ns = arrays["available_ns"][absolute_idx]
        lookback_ns = LOOKBACK_BY_TIMEFRAME.get(timeframe, pd.Timedelta(days=30)).value
        active = available_ns >= decision_ns - lookback_ns
        if not active.any():
            continue
        absolute_idx = absolute_idx[active]
        projected = arrays["intercept"][absolute_idx] + arrays["slope"][absolute_idx] * bar_index
        tolerance = np.maximum(arrays["tolerance"][absolute_idx], np.abs(projected) * 0.0005)
        if source_table.target_side == "above":
            eligible = projected > reference_price
            distance_abs_values = projected - reference_price
        else:
            eligible = projected < reference_price
            distance_abs_values = reference_price - projected
        eligible = eligible & np.isfinite(projected) & np.isfinite(distance_abs_values)
        if not eligible.any():
            continue
        eligible_idx = absolute_idx[np.where(eligible)[0]]
        eligible_distances = distance_abs_values[eligible]
        scores = np.maximum(
            arrays["trendline_pa_zone_score"][eligible_idx],
            arrays["line_quality_score"][eligible_idx],
        )
        order = np.lexsort(
            (
                np.full(len(eligible_idx), TIMEFRAME_PRIORITY.get(timeframe, 9)),
                -scores,
                eligible_distances,
            )
        )
        idx = int(eligible_idx[int(order[0])])
        projected_value = float(arrays["intercept"][idx] + arrays["slope"][idx] * bar_index)
        tolerance_value = max(float(arrays["tolerance"][idx]), abs(projected_value) * 0.0005)
        distance_abs = abs(projected_value - reference_price)
        distance_atr = distance_abs / atr if atr > 0 else np.nan
        available_at = ns_to_utc(arrays["available_ns"][idx])
        freshness = freshness_state(available_at, decision_timestamp, timeframe)
        quality = target_quality(
            "trendline_projection",
            timeframe,
            freshness,
            distance_atr,
            float(max(arrays["trendline_pa_zone_score"][idx], arrays["line_quality_score"][idx])),
        )
        candidates.append(
            {
                "source_object_id": str(arrays["object_id"][idx]),
                "target_source": "trendline_projection",
                "target_timeframe": timeframe,
                "target_side": source_table.target_side,
                "zone_low": projected_value - tolerance_value,
                "zone_high": projected_value + tolerance_value,
                "target_price": projected_value,
                "target_mid": projected_value,
                "available_at": available_at,
                "latest_source_candle_close_used": ns_to_utc(arrays["latest_ns"][idx]),
                "freshness_state": freshness,
                "distance_abs": float(distance_abs),
                "distance_pct": float(distance_abs / reference_price) if reference_price else np.nan,
                "distance_atr": float(distance_atr),
                "target_quality_score": quality,
                "opposing_reaction_risk": reaction_risk("trendline_projection", timeframe, distance_atr),
            }
        )
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item["distance_abs"], -item["target_quality_score"], TIMEFRAME_PRIORITY.get(item["target_timeframe"], 9)))
    return candidates[0]


def candidate_row(
    symbol: str,
    decision_timestamp: pd.Timestamp,
    side: str,
    reference_price: float,
    candidate: dict[str, object],
    rank: int,
) -> dict[str, object]:
    target_id = stable_id(symbol, decision_timestamp, side, candidate["target_source"], candidate.get("source_object_id", ""), rank)
    lookahead_pass = (
        pd.Timestamp(candidate["available_at"]) <= decision_timestamp
        and pd.Timestamp(candidate["latest_source_candle_close_used"]) <= decision_timestamp
    )
    conflict = "none"
    if candidate["target_source"] == "fixed_R_placeholder":
        conflict = "fixed_r_without_structure"
    elif candidate["distance_atr"] < 0.25:
        conflict = "nearest_target_too_close"
    return {
        "symbol": symbol,
        "decision_timestamp": decision_timestamp,
        "side": side,
        "reference_price": float(reference_price),
        "target_id": target_id,
        "source_object_id": candidate.get("source_object_id", ""),
        "target_source": candidate["target_source"],
        "target_timeframe": candidate["target_timeframe"],
        "target_side": candidate["target_side"],
        "zone_low": candidate["zone_low"],
        "zone_high": candidate["zone_high"],
        "target_price": candidate["target_price"],
        "target_mid": candidate["target_mid"],
        "available_at": candidate["available_at"],
        "latest_source_candle_close_used": candidate["latest_source_candle_close_used"],
        "freshness_state": candidate["freshness_state"],
        "distance_abs": candidate["distance_abs"],
        "distance_pct": candidate["distance_pct"],
        "distance_atr": candidate["distance_atr"],
        "distance_r": np.nan,
        "planned_rr": np.nan,
        "requires_entry_sl": True,
        "target_quality_score": candidate["target_quality_score"],
        "opposing_reaction_risk": candidate["opposing_reaction_risk"],
        "structural_target_rank": rank,
        "used_as_tp1_candidate": False,
        "used_as_core_candidate": False,
        "used_as_runner_candidate": False,
        "target_conflict_reason": conflict,
        "lookahead_pass": bool(lookahead_pass),
        "lookahead_violation_reason": "" if lookahead_pass else "target_source_after_decision_timestamp",
    }


def fixed_placeholder(symbol: str, decision_timestamp: pd.Timestamp, side: str, reference_price: float) -> dict[str, object]:
    return candidate_row(
        symbol,
        decision_timestamp,
        side,
        reference_price,
        {
            "source_object_id": "",
            "target_source": "fixed_R_placeholder",
            "target_timeframe": "none",
            "target_side": "above" if side == "long" else "below",
            "zone_low": np.nan,
            "zone_high": np.nan,
            "target_price": np.nan,
            "target_mid": np.nan,
            "available_at": decision_timestamp,
            "latest_source_candle_close_used": decision_timestamp,
            "freshness_state": "requires_entry_sl",
            "distance_abs": np.nan,
            "distance_pct": np.nan,
            "distance_atr": np.nan,
            "target_quality_score": 0.0,
            "opposing_reaction_risk": 1.0,
        },
        1,
    )


def summarize_side(symbol: str, decision_timestamp: pd.Timestamp, side: str, rows: list[dict[str, object]]) -> dict[str, object]:
    structural = [row for row in rows if row["target_source"] != "fixed_R_placeholder"]
    structural_present = bool(structural)
    if not structural_present:
        return {
            "symbol": symbol,
            "decision_timestamp": decision_timestamp,
            "side": side,
            "tp1_candidate_target_id": "",
            "core_candidate_target_id": "",
            "runner_candidate_target_id": "",
            "structural_target_pool_present": False,
            "nearest_target_too_close": False,
            "core_structural_source_present": False,
            "runner_structural_source_present": False,
            "fixed_r_only_warning": True,
            "target_pool_conflict_reason": "no_structural_target",
            "candidate_count": len(rows),
            "lookahead_pass": all(row["lookahead_pass"] for row in rows),
        }
    nearest = min(structural, key=lambda row: row["distance_abs"])
    tp1 = nearest
    core_candidates = [row for row in structural if row["distance_atr"] >= 1.5]
    runner_candidates = [row for row in structural if row["distance_atr"] >= 3.0]
    core = min(core_candidates, key=lambda row: (row["distance_atr"], -row["target_quality_score"])) if core_candidates else None
    runner = min(runner_candidates, key=lambda row: (row["distance_atr"], -row["target_quality_score"])) if runner_candidates else None
    for row in rows:
        row["used_as_tp1_candidate"] = row["target_id"] == tp1["target_id"]
        row["used_as_core_candidate"] = core is not None and row["target_id"] == core["target_id"]
        row["used_as_runner_candidate"] = runner is not None and row["target_id"] == runner["target_id"]
    nearest_too_close = bool(nearest["distance_atr"] < 0.25)
    conflict = "none"
    if nearest_too_close:
        conflict = "nearest_target_too_close"
    elif core is None:
        conflict = "no_core_distance_proxy_requires_entry_sl"
    elif runner is None:
        conflict = "no_runner_distance_proxy_requires_entry_sl"
    return {
        "symbol": symbol,
        "decision_timestamp": decision_timestamp,
        "side": side,
        "tp1_candidate_target_id": tp1["target_id"],
        "core_candidate_target_id": core["target_id"] if core else "",
        "runner_candidate_target_id": runner["target_id"] if runner else "",
        "structural_target_pool_present": True,
        "nearest_target_too_close": nearest_too_close,
        "core_structural_source_present": core is not None,
        "runner_structural_source_present": runner is not None,
        "fixed_r_only_warning": False,
        "target_pool_conflict_reason": conflict,
        "candidate_count": len(rows),
        "lookahead_pass": all(row["lookahead_pass"] for row in rows),
    }


def build_for_symbol(
    symbol: str,
    bars_by_timeframe: dict[str, pd.DataFrame],
    source_tables: dict[tuple[str, str, str], SourceTable],
    trendline_tables: dict[tuple[str, str], SourceTable],
    max_targets_per_side: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    snapshots = bars_by_timeframe["15m"][
        ["close_time", "close", "atr"]
    ].rename(columns={"close_time": "decision_timestamp", "close": "reference_price"}).copy()
    target_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    side_to_target_side = {"long": "above", "short": "below"}
    source_order = [
        "nearest_15m_unmitigated_fvg_mid",
        "15m_sr_zone",
        "1h_sr_zone",
        "4h_sr_zone",
        "day_high_low",
        "previous_day_high_low",
        "next_15m_fvg",
        "next_1h_fvg",
        "liquidity_pool",
    ]
    total = len(snapshots)
    for row_number, row in enumerate(snapshots.itertuples(index=False), 1):
        if row_number == 1 or row_number % 10000 == 0:
            print(f"  target_pool {symbol} rows={row_number}/{total}", flush=True)
        decision_timestamp = pd.Timestamp(row.decision_timestamp)
        reference_price = float(row.reference_price)
        atr = max(float(row.atr), 1e-12)
        for side, target_side in side_to_target_side.items():
            candidates: list[dict[str, object]] = []
            skip_fvg_ids: set[str] = set()
            for source in source_order:
                key = (symbol, source, target_side)
                table = source_tables.get(key)
                if table is None:
                    continue
                candidate = pick_static_candidate(
                    table,
                    decision_timestamp,
                    side,
                    reference_price,
                    atr,
                    skip_object_ids=skip_fvg_ids if source in {"next_15m_fvg", "next_1h_fvg"} else None,
                )
                if candidate is None:
                    continue
                candidates.append(candidate)
                if source == "nearest_15m_unmitigated_fvg_mid":
                    skip_fvg_ids.add(candidate["source_object_id"])
            trend_table = trendline_tables.get((symbol, target_side))
            if trend_table is not None:
                trend_candidate = pick_trendline_candidate(
                    trend_table,
                    bars_by_timeframe,
                    decision_timestamp,
                    reference_price,
                    atr,
                )
                if trend_candidate is not None:
                    candidates.append(trend_candidate)
            candidates.sort(
                key=lambda item: (
                    item["distance_abs"],
                    -item["target_quality_score"],
                    TIMEFRAME_PRIORITY.get(item["target_timeframe"], 9),
                    item["target_source"],
                )
            )
            selected = candidates[:max_targets_per_side]
            rows = [
                candidate_row(symbol, decision_timestamp, side, reference_price, candidate, rank)
                for rank, candidate in enumerate(selected, 1)
            ]
            if not rows:
                rows = [fixed_placeholder(symbol, decision_timestamp, side, reference_price)]
            summary = summarize_side(symbol, decision_timestamp, side, rows)
            target_rows.extend(rows)
            summary_rows.append(summary)
    return pd.DataFrame(target_rows), pd.DataFrame(summary_rows)


def build_audit(targets: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "symbol",
        "decision_timestamp",
        "side",
        "target_id",
        "target_source",
        "target_timeframe",
        "available_at",
        "latest_source_candle_close_used",
        "lookahead_pass",
        "lookahead_violation_reason",
    ]
    audit = targets[cols].copy()
    for column in ["decision_timestamp", "available_at", "latest_source_candle_close_used"]:
        audit[column] = pd.to_datetime(audit[column], utc=True, errors="coerce")
    audit["lookahead_pass"] = (audit["available_at"] <= audit["decision_timestamp"]) & (
        audit["latest_source_candle_close_used"] <= audit["decision_timestamp"]
    )
    audit.loc[audit["lookahead_pass"], "lookahead_violation_reason"] = ""
    audit.loc[~audit["lookahead_pass"], "lookahead_violation_reason"] = "target_source_after_decision_timestamp"
    return audit


def markdown_table(rows: Iterable[dict[str, object]], columns: list[str]) -> list[str]:
    rows = list(rows)
    if not rows:
        return ["_No rows._"]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return lines


def write_report(targets: pd.DataFrame, summary: pd.DataFrame, audit: pd.DataFrame, symbols: list[str]) -> None:
    source_counts = targets["target_source"].value_counts().reset_index()
    source_counts.columns = ["target_source", "rows"]
    side_counts = targets.groupby(["symbol", "side"]).size().reset_index(name="rows")
    conflict_counts = summary["target_pool_conflict_reason"].value_counts().reset_index()
    conflict_counts.columns = ["target_pool_conflict_reason", "rows"]
    fixed_rows = int(targets["target_source"].eq("fixed_R_placeholder").sum())
    fixed_pct = fixed_rows / len(targets) * 100 if len(targets) else 0
    violations = int((~audit["lookahead_pass"]).sum())
    role_counts = {
        "tp1_candidate_rows": int(targets["used_as_tp1_candidate"].sum()),
        "core_candidate_rows": int(targets["used_as_core_candidate"].sum()),
        "runner_candidate_rows": int(targets["used_as_runner_candidate"].sum()),
    }
    spot = []
    for symbol in symbols:
        for side in ["long", "short"]:
            sample = summary[(summary["symbol"].eq(symbol)) & (summary["side"].eq(side)) & (summary["target_pool_conflict_reason"].eq("none"))].head(1)
            if sample.empty:
                sample = summary[(summary["symbol"].eq(symbol)) & (summary["side"].eq(side))].head(1)
            if sample.empty:
                continue
            row = sample.iloc[0]
            selected = targets[targets["target_id"].isin([row["tp1_candidate_target_id"], row["core_candidate_target_id"], row["runner_candidate_target_id"]])]
            description = "; ".join(
                f"{target.side}:{target.target_source}@{target.target_timeframe} dist_atr={target.distance_atr:.2f}"
                for target in selected.itertuples()
            )
            spot.append(
                {
                    "symbol": symbol,
                    "decision_timestamp": row["decision_timestamp"],
                    "side": side,
                    "conflict": row["target_pool_conflict_reason"],
                    "selected_targets": description,
                }
            )
    lines = [
        "# Craig v1.2 Target Pool Build Report",
        "",
        "Generated by `scripts/build_craig_v1_2_target_pools.py`.",
        "",
        "## Verdict",
        "",
        "- Structural target pools were built for closed 15m decision timestamps.",
        "- The generator uses visible 15m/1h/4h PA-zone objects and trendline projections; BTC context is not used as a direct target filter in this stage.",
        "- Fixed-R is only a placeholder fallback and is not used as a primary target source.",
        f"- Lookahead violations: {violations}.",
        "",
        "## Dataset And Grain",
        "",
        f"- Symbols: {', '.join(symbols)}",
        f"- Target candidate rows: {len(targets)}",
        f"- Summary rows: {len(summary)}",
        "- Snapshot grain: closed 15m candle per symbol and side.",
        "- Entry/SL are not known yet, so `distance_r` and `planned_rr` remain null and `requires_entry_sl=true`.",
        "",
        "## Target Source Distribution",
        "",
        *markdown_table(source_counts.to_dict("records"), ["target_source", "rows"]),
        "",
        "## Side Counts",
        "",
        *markdown_table(side_counts.to_dict("records"), ["symbol", "side", "rows"]),
        "",
        "## Conflict Distribution",
        "",
        *markdown_table(conflict_counts.to_dict("records"), ["target_pool_conflict_reason", "rows"]),
        "",
        "## Candidate Role Counts",
        "",
        *markdown_table([role_counts], ["tp1_candidate_rows", "core_candidate_rows", "runner_candidate_rows"]),
        "",
        "## Fixed-R Placeholder",
        "",
        f"- fixed_R_placeholder rows: {fixed_rows}",
        f"- fixed_R_placeholder share: {fixed_pct:.4f}%",
        "- A non-zero value means the structural target pool was absent and later trade construction must not treat fixed R as Craig DNA target evidence.",
        "",
        "## Spot Checks",
        "",
        *markdown_table(spot, ["symbol", "decision_timestamp", "side", "conflict", "selected_targets"]),
        "",
        "## No-Lookahead Controls",
        "",
        "- Target `available_at` must be less than or equal to `decision_timestamp`.",
        "- `latest_source_candle_close_used` must be less than or equal to `decision_timestamp`.",
        "- Current day high/low rows are the HTF registry's cumulative `so_far` rows, not final-session extrema.",
        "- Previous day high/low rows are used only after the prior UTC day is closed in the registry.",
        "- FVG target rows use first-mitigation timestamps only as an as-of condition; a future mitigation time is never exposed as a signal at earlier decisions.",
        "- Gold labels, Craig action, result R, future outcome, entry/SL/TP, and PnL fields are not read.",
        "",
        "## Output Paths",
        "",
        f"- Target pools: `{rel(OUT_TARGETS)}`",
        f"- Target pool summary: `{rel(OUT_SUMMARY)}`",
        f"- Audit CSV: `{rel(OUT_AUDIT)}`",
        "",
        "## Next Step Recommendation",
        "",
        "Build the thesis generator before 1m precision entry. The system now has market structure, BTC context, and structural targets; the next gate should decide whether a side/setup has a valid Craig DNA thesis before any 1m entry mechanics are allowed to create trades.",
    ]
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=HEADLINE_SYMBOLS)
    parser.add_argument("--max-targets-per-side", type=int, default=MAX_TARGETS_PER_SIDE)
    parser.add_argument("--include-btc", action="store_true")
    args = parser.parse_args()
    symbols = [symbol.upper() for symbol in args.symbols]
    if args.include_btc and "BTCUSDT" not in symbols:
        symbols.append("BTCUSDT")

    print("load continuous bars", flush=True)
    bars_by_symbol = {symbol: load_symbol_bars(symbol) for symbol in symbols}
    print("load HTF zones", flush=True)
    htf_zones = pd.read_parquet(HTF_ZONES_PARQUET)
    print("load trendlines", flush=True)
    trendlines = pd.read_parquet(TRENDLINE_ZONES_PARQUET)
    print("load BTC context schema reference", flush=True)
    if BTC_CONTEXT_PARQUET.exists():
        _ = pd.read_parquet(BTC_CONTEXT_PARQUET, columns=["decision_timestamp", "btc_context_effect"]).head(1)

    print("compute FVG mitigation state", flush=True)
    htf_zones = add_fvg_mitigation_times(htf_zones, bars_by_symbol)
    print("prepare source tables", flush=True)
    source_tables = prepare_static_source_tables(htf_zones, symbols)
    trendline_tables = prepare_trendline_tables(trendlines, symbols)

    target_parts = []
    summary_parts = []
    for symbol in symbols:
        print(f"build target pools symbol={symbol}", flush=True)
        targets, summary = build_for_symbol(
            symbol,
            bars_by_symbol[symbol],
            source_tables,
            trendline_tables,
            args.max_targets_per_side,
        )
        target_parts.append(targets)
        summary_parts.append(summary)

    all_targets = pd.concat(target_parts, ignore_index=True)
    all_summary = pd.concat(summary_parts, ignore_index=True)
    audit = build_audit(all_targets)
    if not audit["lookahead_pass"].all():
        failures = int((~audit["lookahead_pass"]).sum())
        raise RuntimeError(f"Target pool lookahead audit failed for {failures} rows")

    OUT_TARGETS.parent.mkdir(parents=True, exist_ok=True)
    all_targets.to_parquet(OUT_TARGETS, index=False)
    all_summary.to_parquet(OUT_SUMMARY, index=False)
    audit.to_csv(OUT_AUDIT, index=False, encoding="utf-8-sig")
    write_report(all_targets, all_summary, audit, symbols)
    print(f"target_pools={OUT_TARGETS} rows={len(all_targets)}")
    print(f"summary={OUT_SUMMARY} rows={len(all_summary)}")
    print(f"audit={OUT_AUDIT} rows={len(audit)} lookahead_pass={int(audit['lookahead_pass'].sum())}/{len(audit)}")
    print(f"report={OUT_REPORT}")


if __name__ == "__main__":
    main()
