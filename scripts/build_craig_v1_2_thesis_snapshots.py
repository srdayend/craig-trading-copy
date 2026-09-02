#!/usr/bin/env python3
from __future__ import annotations

import argparse
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
TARGET_POOL_SUMMARY_PARQUET = ROOT / "outputs/craig_v1_2_target_pool_summary.parquet"
TARGET_POOLS_PARQUET = ROOT / "outputs/craig_v1_2_target_pools.parquet"

OUT_SNAPSHOTS = ROOT / "outputs/craig_v1_2_thesis_snapshots.parquet"
OUT_AUDIT = ROOT / "outputs/craig_v1_2_thesis_audit.csv"
OUT_REPORT = ROOT / "outputs/craig_v1_2_thesis_build_report.md"

HEADLINE_SYMBOLS = ["SOLUSDT", "ETHUSDT"]
TIMEFRAME_MINUTES = {"15m": 15, "1h": 60, "4h": 240}
RESAMPLE_RULES = {"15m": "15T", "1h": "1H", "4h": "4H"}
TIMEFRAME_BONUS = {"15m": 0.03, "1h": 0.08, "4h": 0.12}
TIMEFRAME_PRIORITY = {"4h": 0, "1h": 1, "15m": 2}
ATR_PERIOD = 14

ZONE_TAIL = 360
TRENDLINE_TAIL = 240
ZONE_LOOKBACK_NS = {
    "15m": pd.Timedelta(days=14).value,
    "1h": pd.Timedelta(days=60).value,
    "4h": pd.Timedelta(days=180).value,
}
TRENDLINE_EVENT_LOOKBACK_NS = {
    "15m": pd.Timedelta(days=3).value,
    "1h": pd.Timedelta(days=14).value,
    "4h": pd.Timedelta(days=45).value,
}

THESIS_MODES = {
    "R1_reversal_extreme_sr_fvg",
    "R2_sweep_reversal",
    "R3_trendline_reversal",
    "R4_break_retest_reversal",
    "C1_htf_aligned_fvg_pullback",
    "C2_breakout_retest_continuation",
    "C3_channel_or_trendline_continuation",
    "reject",
}
BTC_EFFECTS = {"confirm", "warn", "veto", "neutral"}
TRENDLINE_INTERACTIONS = {"near_touch", "sweep", "break_retest", "rejection", "clean_break", "none"}


@dataclass(frozen=True)
class ArrayTable:
    values: np.ndarray
    arrays: dict[str, np.ndarray]


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def utc_timestamp(value: object) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def ns_to_utc(ns: int | np.integer | float) -> pd.Timestamp:
    if pd.isna(ns):
        return pd.NaT
    return pd.Timestamp(int(ns), unit="ns", tz="UTC")


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    if pd.isna(value):
        return low
    return float(max(low, min(high, value)))


def markdown_table(rows: Iterable[dict[str, object]], columns: list[str]) -> list[str]:
    rows = list(rows)
    if not rows:
        return ["_No rows._"]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return lines


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
    bars["atr"] = compute_atr(bars)
    bars["decision_timestamp"] = pd.to_datetime(bars["close_time"], utc=True)
    bars["decision_ns"] = bars["decision_timestamp"].astype("int64")
    bars["symbol"] = str(df_1m["symbol"].iloc[0]) if "symbol" in df_1m.columns else ""
    return bars


def find_symbol_parquet(symbol: str) -> Path:
    candidates = sorted((PROCESSED_ROOT / symbol / "1m").glob(f"{symbol}_1m_*.parquet"))
    if not candidates:
        raise FileNotFoundError(f"No normalized continuous parquet found for {symbol}")
    return candidates[-1]


def load_15m_bars(symbols: list[str]) -> pd.DataFrame:
    frames = []
    for symbol in symbols:
        path = find_symbol_parquet(symbol)
        df = pd.read_parquet(path, columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        for column in ["open", "high", "low", "close", "volume"]:
            df[column] = pd.to_numeric(df[column], errors="coerce")
        df = df.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")
        bars = resample_ohlcv(df, "15m")
        bars["symbol"] = symbol
        frames.append(
            bars[
                [
                    "symbol",
                    "decision_timestamp",
                    "decision_ns",
                    "open",
                    "high",
                    "low",
                    "close",
                    "atr",
                ]
            ].rename(columns={"close": "reference_price", "open": "bar_open", "high": "bar_high", "low": "bar_low"})
        )
    return pd.concat(frames, ignore_index=True)


def zone_kind(object_type: str, timeframe: str) -> str:
    if object_type in {"fvg_bullish", "fvg_bearish"}:
        return f"{timeframe}_fvg"
    if object_type in {"sr_support", "sr_resistance"}:
        return f"{timeframe}_sr_zone"
    if object_type in {"liquidity_equal_highs", "liquidity_equal_lows"}:
        return "liquidity_pool"
    if object_type in {"current_day_high_so_far", "current_day_low_so_far"}:
        return "day_high_low"
    if object_type in {"previous_day_high", "previous_day_low"}:
        return "previous_day_high_low"
    if object_type in {"swing_high", "swing_low"}:
        return f"{timeframe}_swing"
    return "none"


def category_for_object(object_type: str) -> str:
    if object_type in {"sr_support", "sr_resistance"}:
        return "sr"
    if object_type in {"fvg_bullish", "fvg_bearish"}:
        return "fvg"
    if object_type in {
        "liquidity_equal_highs",
        "liquidity_equal_lows",
        "current_day_high_so_far",
        "current_day_low_so_far",
        "previous_day_high",
        "previous_day_low",
        "swing_high",
        "swing_low",
    }:
        return "liquidity"
    return "none"


def base_zone_score(object_type: str) -> float:
    return {
        "sr_support": 0.68,
        "sr_resistance": 0.68,
        "fvg_bullish": 0.66,
        "fvg_bearish": 0.66,
        "liquidity_equal_lows": 0.70,
        "liquidity_equal_highs": 0.70,
        "previous_day_low": 0.72,
        "previous_day_high": 0.72,
        "current_day_low_so_far": 0.62,
        "current_day_high_so_far": 0.62,
        "swing_low": 0.58,
        "swing_high": 0.58,
    }.get(object_type, 0.0)


def distance_score(distance_atr: float) -> float:
    if pd.isna(distance_atr):
        return 0.0
    if distance_atr <= 0.08:
        return 1.0
    if distance_atr <= 0.35:
        return 0.85
    if distance_atr <= 0.75:
        return 0.55
    if distance_atr <= 1.25:
        return 0.25
    return 0.0


def prepare_zone_tables(zones: pd.DataFrame, symbols: list[str]) -> dict[tuple[str, str], ArrayTable]:
    rows = zones[zones["symbol"].isin(symbols)].copy()
    rows["available_at"] = pd.to_datetime(rows["available_at"], utc=True)
    rows["latest_source_candle_close_used"] = pd.to_datetime(rows["latest_source_candle_close_used"], utc=True)
    rows["_available_ns"] = rows["available_at"].astype("int64")
    rows["_latest_ns"] = rows["latest_source_candle_close_used"].astype("int64")
    rows["_lookback_ns"] = rows["timeframe"].map(ZONE_LOOKBACK_NS).fillna(pd.Timedelta(days=30).value).astype("int64")
    tables: dict[tuple[str, str], ArrayTable] = {}
    keep = rows[
        [
            "object_id",
            "symbol",
            "timeframe",
            "object_type",
            "side",
            "zone_low",
            "zone_high",
            "zone_mid",
            "available_at",
            "latest_source_candle_close_used",
            "trendline_pa_zone_score",
            "trendline_zone_confluence_count",
            "sr_trendline_overlap",
            "fvg_trendline_overlap",
            "liquidity_trendline_overlap",
            "_available_ns",
            "_latest_ns",
            "_lookback_ns",
        ]
    ].sort_values("_available_ns")
    for key, group in keep.groupby(["symbol", "side"], sort=False):
        group = group.reset_index(drop=True)
        arrays = {
            "object_id": group["object_id"].astype(str).to_numpy(),
            "timeframe": group["timeframe"].astype(str).to_numpy(),
            "object_type": group["object_type"].astype(str).to_numpy(),
            "zone_low": group["zone_low"].astype(float).to_numpy(),
            "zone_high": group["zone_high"].astype(float).to_numpy(),
            "zone_mid": group["zone_mid"].astype(float).to_numpy(),
            "available_ns": group["_available_ns"].to_numpy(dtype="int64"),
            "latest_ns": group["_latest_ns"].to_numpy(dtype="int64"),
            "lookback_ns": group["_lookback_ns"].to_numpy(dtype="int64"),
            "trendline_pa_zone_score": group["trendline_pa_zone_score"].astype(float).fillna(0.0).to_numpy(),
            "trendline_zone_confluence_count": group["trendline_zone_confluence_count"].astype(float).fillna(0.0).to_numpy(),
            "sr_trendline_overlap": group["sr_trendline_overlap"].fillna(False).astype(bool).to_numpy(),
            "fvg_trendline_overlap": group["fvg_trendline_overlap"].fillna(False).astype(bool).to_numpy(),
            "liquidity_trendline_overlap": group["liquidity_trendline_overlap"].fillna(False).astype(bool).to_numpy(),
        }
        tables[key] = ArrayTable(group["_available_ns"].to_numpy(dtype="int64"), arrays)
    return tables


def prepare_trendline_event_tables(trendlines: pd.DataFrame, symbols: list[str]) -> dict[str, ArrayTable]:
    rows = trendlines[
        trendlines["symbol"].isin(symbols) & trendlines["object_type"].eq("trendline_interaction")
    ].copy()
    rows["available_at"] = pd.to_datetime(rows["available_at"], utc=True)
    rows["latest_source_candle_close_used"] = pd.to_datetime(rows["latest_source_candle_close_used"], utc=True)
    rows["_available_ns"] = rows["available_at"].astype("int64")
    rows["_latest_ns"] = rows["latest_source_candle_close_used"].astype("int64")
    rows["_lookback_ns"] = rows["timeframe"].map(TRENDLINE_EVENT_LOOKBACK_NS).fillna(pd.Timedelta(days=7).value).astype("int64")
    tables: dict[str, ArrayTable] = {}
    keep = rows[
        [
            "object_id",
            "symbol",
            "timeframe",
            "line_side",
            "side",
            "trendline_interaction_type",
            "zone_low",
            "zone_high",
            "zone_mid",
            "available_at",
            "latest_source_candle_close_used",
            "trendline_pa_zone_score",
            "trendline_zone_confluence_count",
            "sr_trendline_overlap",
            "fvg_trendline_overlap",
            "liquidity_trendline_overlap",
            "_available_ns",
            "_latest_ns",
            "_lookback_ns",
        ]
    ].sort_values("_available_ns")
    for symbol, group in keep.groupby("symbol", sort=False):
        group = group.reset_index(drop=True)
        arrays = {
            "object_id": group["object_id"].astype(str).to_numpy(),
            "timeframe": group["timeframe"].astype(str).to_numpy(),
            "line_side": group["line_side"].astype(str).to_numpy(),
            "side": group["side"].astype(str).to_numpy(),
            "interaction": group["trendline_interaction_type"].astype(str).to_numpy(),
            "zone_low": group["zone_low"].astype(float).to_numpy(),
            "zone_high": group["zone_high"].astype(float).to_numpy(),
            "zone_mid": group["zone_mid"].astype(float).to_numpy(),
            "available_ns": group["_available_ns"].to_numpy(dtype="int64"),
            "latest_ns": group["_latest_ns"].to_numpy(dtype="int64"),
            "lookback_ns": group["_lookback_ns"].to_numpy(dtype="int64"),
            "trendline_pa_zone_score": group["trendline_pa_zone_score"].astype(float).fillna(0.0).to_numpy(),
            "trendline_zone_confluence_count": group["trendline_zone_confluence_count"].astype(float).fillna(0.0).to_numpy(),
            "sr_trendline_overlap": group["sr_trendline_overlap"].fillna(False).astype(bool).to_numpy(),
            "fvg_trendline_overlap": group["fvg_trendline_overlap"].fillna(False).astype(bool).to_numpy(),
            "liquidity_trendline_overlap": group["liquidity_trendline_overlap"].fillna(False).astype(bool).to_numpy(),
        }
        tables[symbol] = ArrayTable(group["_available_ns"].to_numpy(dtype="int64"), arrays)
    return tables


def zone_features(
    table: ArrayTable | None,
    decision_ns: int,
    reference_price: float,
    atr: float,
) -> dict[str, object]:
    default = {
        "htf_zone_kind": "none",
        "htf_zone_timeframe": "none",
        "htf_zone_object_id": "",
        "htf_zone_available_at": pd.NaT,
        "htf_zone_latest_source_candle_close_used": pd.NaT,
        "htf_location_score": 0.0,
        "sr_zone_score": 0.0,
        "fvg_zone_score": 0.0,
        "liquidity_score": 0.0,
        "htf_zone_distance_atr": np.nan,
        "htf_zone_category_count": 0,
    }
    if table is None or len(table.values) == 0:
        return default
    pos = int(np.searchsorted(table.values, decision_ns, side="right"))
    if pos <= 0:
        return default
    start = max(0, pos - ZONE_TAIL)
    arrays = table.arrays
    idx = np.arange(start, pos)
    active = arrays["available_ns"][idx] >= decision_ns - arrays["lookback_ns"][idx]
    if not active.any():
        return default
    idx = idx[active]
    lows = arrays["zone_low"][idx]
    highs = arrays["zone_high"][idx]
    below = np.maximum(lows - reference_price, 0.0)
    above = np.maximum(reference_price - highs, 0.0)
    distance_abs = below + above
    distance_atr = distance_abs / atr if atr > 0 else np.full(len(idx), np.nan)
    distance_component = np.array([distance_score(value) for value in distance_atr], dtype="float64")
    object_types = arrays["object_type"][idx]
    timeframes = arrays["timeframe"][idx]
    base = np.array([base_zone_score(object_type) for object_type in object_types], dtype="float64")
    tf_bonus = np.array([TIMEFRAME_BONUS.get(str(tf), 0.0) for tf in timeframes], dtype="float64")
    overlap_bonus = (
        arrays["sr_trendline_overlap"][idx].astype(float) * 0.05
        + arrays["fvg_trendline_overlap"][idx].astype(float) * 0.05
        + arrays["liquidity_trendline_overlap"][idx].astype(float) * 0.05
        + np.minimum(arrays["trendline_zone_confluence_count"][idx], 2.0) * 0.03
    )
    scores = np.clip(base * distance_component + tf_bonus + overlap_bonus, 0.0, 1.0)

    category_scores = {"sr": 0.0, "fvg": 0.0, "liquidity": 0.0}
    for category in category_scores:
        mask = np.array([category_for_object(object_type) == category for object_type in object_types])
        if mask.any():
            category_scores[category] = float(np.nanmax(scores[mask]))
    meaningful_count = int(sum(value >= 0.35 for value in category_scores.values()))
    if not np.isfinite(scores).any() or float(np.nanmax(scores)) < 0.18:
        return {
            **default,
            "sr_zone_score": category_scores["sr"],
            "fvg_zone_score": category_scores["fvg"],
            "liquidity_score": category_scores["liquidity"],
            "htf_zone_category_count": meaningful_count,
        }
    best_local = int(np.nanargmax(scores))
    best_idx = int(idx[best_local])
    best_object_type = str(arrays["object_type"][best_idx])
    best_timeframe = str(arrays["timeframe"][best_idx])
    htf_location_score = clamp(float(scores[best_local]) + max(0, meaningful_count - 1) * 0.04)
    return {
        "htf_zone_kind": zone_kind(best_object_type, best_timeframe),
        "htf_zone_timeframe": best_timeframe,
        "htf_zone_object_id": str(arrays["object_id"][best_idx]),
        "htf_zone_available_at": ns_to_utc(arrays["available_ns"][best_idx]),
        "htf_zone_latest_source_candle_close_used": ns_to_utc(arrays["latest_ns"][best_idx]),
        "htf_location_score": htf_location_score,
        "sr_zone_score": category_scores["sr"],
        "fvg_zone_score": category_scores["fvg"],
        "liquidity_score": category_scores["liquidity"],
        "htf_zone_distance_atr": float(distance_atr[best_local]),
        "htf_zone_category_count": meaningful_count,
    }


def trendline_features(table: ArrayTable | None, symbol: str, side: str, decision_ns: int) -> dict[str, object]:
    _ = symbol
    default = {
        "trendline_event_id": "",
        "trendline_event_available_at": pd.NaT,
        "trendline_event_latest_source_candle_close_used": pd.NaT,
        "trendline_interaction_type": "none",
        "trendline_pa_zone_score": 0.0,
        "trendline_zone_confluence_count": 0,
        "trendline_supportive_role": "none",
        "trendline_clean_break_against_side": False,
    }
    if table is None or len(table.values) == 0:
        return default
    pos = int(np.searchsorted(table.values, decision_ns, side="right"))
    if pos <= 0:
        return default
    start = max(0, pos - TRENDLINE_TAIL)
    arrays = table.arrays
    idx = np.arange(start, pos)
    active = arrays["available_ns"][idx] >= decision_ns - arrays["lookback_ns"][idx]
    if not active.any():
        return default
    idx = idx[active]

    desired_reversal_line = "support" if side == "long" else "resistance"
    desired_break_line = "resistance" if side == "long" else "support"
    against_line = desired_reversal_line
    interactions = arrays["interaction"][idx]
    line_sides = arrays["line_side"][idx]
    timeframes = arrays["timeframe"][idx]
    age_ratio = np.clip((decision_ns - arrays["available_ns"][idx]) / arrays["lookback_ns"][idx], 0.0, 1.0)
    age_score = np.maximum(0.0, 1.0 - age_ratio * 0.85)
    base = np.zeros(len(idx), dtype="float64")
    role = np.array(["none"] * len(idx), dtype=object)

    reversal_mask = (line_sides == desired_reversal_line) & np.isin(interactions, ["near_touch", "sweep", "rejection"])
    break_mask = (line_sides == desired_break_line) & np.isin(interactions, ["clean_break", "break_retest"])
    against_mask = (line_sides == against_line) & np.isin(interactions, ["clean_break", "break_retest"])

    interaction_base = {
        "rejection": 0.82,
        "sweep": 0.78,
        "near_touch": 0.56,
        "break_retest": 0.76,
        "clean_break": 0.64,
    }
    for interaction, value in interaction_base.items():
        base[reversal_mask & (interactions == interaction)] = value
        base[break_mask & (interactions == interaction)] = value
        base[against_mask & (interactions == interaction)] = max(value - 0.12, 0.0)
    role[reversal_mask] = "reversal"
    role[break_mask] = "continuation_break"
    role[against_mask] = "against_clean_break"

    tf_bonus = np.array([TIMEFRAME_BONUS.get(str(tf), 0.0) for tf in timeframes], dtype="float64")
    confluence = arrays["trendline_zone_confluence_count"][idx].astype(float)
    overlap_bonus = (
        np.minimum(confluence, 2.0) * 0.05
        + arrays["sr_trendline_overlap"][idx].astype(float) * 0.04
        + arrays["fvg_trendline_overlap"][idx].astype(float) * 0.04
        + arrays["liquidity_trendline_overlap"][idx].astype(float) * 0.04
    )
    detector_score = arrays["trendline_pa_zone_score"][idx]
    blended_base = np.maximum(base * 0.70 + detector_score * 0.30, base * 0.85)
    scores = np.clip(blended_base * age_score + tf_bonus * 0.60 + overlap_bonus * 0.50, 0.0, 1.0)
    candidate_mask = role != "none"
    if not candidate_mask.any():
        return default
    local_candidates = np.where(candidate_mask)[0]
    order = np.lexsort(
        (
            np.array([TIMEFRAME_PRIORITY.get(str(tf), 9) for tf in timeframes[local_candidates]]),
            -(role[local_candidates] != "against_clean_break").astype(int),
            -scores[local_candidates],
        )
    )
    best_local = int(local_candidates[int(order[0])])
    best_idx = int(idx[best_local])
    interaction = str(arrays["interaction"][best_idx])
    if interaction not in TRENDLINE_INTERACTIONS:
        interaction = "none"
    return {
        "trendline_event_id": str(arrays["object_id"][best_idx]),
        "trendline_event_available_at": ns_to_utc(arrays["available_ns"][best_idx]),
        "trendline_event_latest_source_candle_close_used": ns_to_utc(arrays["latest_ns"][best_idx]),
        "trendline_interaction_type": interaction,
        "trendline_pa_zone_score": float(scores[best_local]),
        "trendline_zone_confluence_count": int(max(0, confluence[best_local])),
        "trendline_supportive_role": str(role[best_local]),
        "trendline_clean_break_against_side": bool(role[best_local] == "against_clean_break"),
    }


def structural_path_score(row: pd.Series) -> float:
    score = 0.0
    if bool(row["structural_target_pool_present"]):
        score += 0.22
    if str(row.get("tp1_candidate_target_id", "")):
        score += 0.10
    if bool(row["core_structural_source_present"]):
        score += 0.34
    if bool(row["runner_structural_source_present"]):
        score += 0.34
    if bool(row["nearest_target_too_close"]):
        score -= 0.10
    if bool(row["fixed_r_only_warning"]):
        score -= 0.40
    return clamp(score)


def btc_effect_for_side(row: pd.Series, side: str) -> tuple[str, str, float]:
    long_effect = str(row.get("btc_long_context_effect", "neutral") or "neutral")
    short_effect = str(row.get("btc_short_context_effect", "neutral") or "neutral")
    if long_effect not in BTC_EFFECTS:
        long_effect = "neutral"
    if short_effect not in BTC_EFFECTS:
        short_effect = "neutral"
    signed_score = float(row.get("btc_leader_context_score", 0.0) or 0.0)
    side_score = signed_score if side == "long" else -signed_score
    return long_effect, short_effect, clamp(side_score, -1.0, 1.0)


def classify_mode(
    side: str,
    zone: dict[str, object],
    trendline: dict[str, object],
    target: pd.Series,
) -> str:
    _ = side
    location = float(zone["htf_location_score"])
    sr = float(zone["sr_zone_score"])
    fvg = float(zone["fvg_zone_score"])
    liquidity = float(zone["liquidity_score"])
    trend_score = float(trendline["trendline_pa_zone_score"])
    interaction = str(trendline["trendline_interaction_type"])
    trend_role = str(trendline["trendline_supportive_role"])
    has_core_or_runner = bool(target["core_structural_source_present"]) or bool(target["runner_structural_source_present"])
    zone_kind_text = str(zone["htf_zone_kind"])
    distance_atr = float(zone.get("htf_zone_distance_atr", np.nan))
    close_to_zone = pd.notna(distance_atr) and distance_atr <= 0.35
    very_close_to_zone = pd.notna(distance_atr) and distance_atr <= 0.18
    at_extreme = liquidity >= 0.45 or zone_kind_text in {"day_high_low", "previous_day_high_low"} or "swing" in zone_kind_text
    major_extreme = zone_kind_text in {"liquidity_pool", "previous_day_high_low", "day_high_low"} or "swing" in zone_kind_text

    if interaction == "sweep" or (major_extreme and very_close_to_zone and liquidity >= 0.68):
        return "R2_sweep_reversal"
    if trend_role == "continuation_break" and interaction == "break_retest" and trend_score >= 0.58 and (at_extreme or liquidity >= 0.35):
        return "R4_break_retest_reversal"
    if trend_role == "reversal" and interaction in {"near_touch", "sweep", "rejection"} and trend_score >= 0.58 and close_to_zone:
        return "R3_trendline_reversal"
    if at_extreme and close_to_zone and (sr >= 0.42 or fvg >= 0.48 or liquidity >= 0.62 or location >= 0.62):
        return "R1_reversal_extreme_sr_fvg"
    if trend_role == "continuation_break" and interaction in {"clean_break", "break_retest"} and trend_score >= 0.58 and (sr >= 0.32 or fvg >= 0.40 or has_core_or_runner):
        return "C2_breakout_retest_continuation"
    if trend_role == "continuation_break" and trend_score >= 0.55 and close_to_zone:
        return "C3_channel_or_trendline_continuation"
    if fvg >= 0.58 and location >= 0.50 and has_core_or_runner:
        return "C1_htf_aligned_fvg_pullback"
    return "reject"


def mode_quality_pass(mode: str, zone: dict[str, object], trendline: dict[str, object]) -> bool:
    sr = float(zone["sr_zone_score"])
    fvg = float(zone["fvg_zone_score"])
    liquidity = float(zone["liquidity_score"])
    location = float(zone["htf_location_score"])
    trend_score = float(trendline["trendline_pa_zone_score"])
    interaction = str(trendline["trendline_interaction_type"])
    trend_role = str(trendline["trendline_supportive_role"])
    distance_atr = float(zone.get("htf_zone_distance_atr", np.nan))
    close_to_zone = pd.notna(distance_atr) and distance_atr <= 0.35
    very_close_to_zone = pd.notna(distance_atr) and distance_atr <= 0.18
    confluence = int(trendline["trendline_zone_confluence_count"])
    zone_kind_text = str(zone["htf_zone_kind"])
    major_extreme = zone_kind_text in {"liquidity_pool", "previous_day_high_low", "day_high_low"} or "swing" in zone_kind_text
    if mode == "R2_sweep_reversal":
        return interaction == "sweep" or (major_extreme and very_close_to_zone and liquidity >= 0.68)
    if mode == "R3_trendline_reversal":
        return trend_role == "reversal" and interaction in {"near_touch", "sweep", "rejection"} and trend_score >= 0.62 and confluence >= 1 and max(sr, fvg, liquidity) >= 0.35
    if mode == "R4_break_retest_reversal":
        return trend_role == "continuation_break" and interaction == "break_retest" and trend_score >= 0.62 and max(sr, fvg, liquidity, location) >= 0.45
    if mode == "R1_reversal_extreme_sr_fvg":
        return major_extreme and close_to_zone and max(sr, fvg, liquidity) >= 0.50
    if mode == "C1_htf_aligned_fvg_pullback":
        return fvg >= 0.62 and location >= 0.55
    if mode == "C2_breakout_retest_continuation":
        return trend_role == "continuation_break" and interaction in {"clean_break", "break_retest"} and trend_score >= 0.62 and max(sr, fvg, liquidity) >= 0.35
    if mode == "C3_channel_or_trendline_continuation":
        return trend_role == "continuation_break" and trend_score >= 0.62 and close_to_zone
    return False


def score_thesis(
    mode: str,
    zone: dict[str, object],
    trendline: dict[str, object],
    path_score: float,
    btc_side_effect: str,
    btc_side_score: float,
) -> float:
    if mode == "reject":
        return 0.0
    local_location = max(
        float(zone["htf_location_score"]),
        float(zone["sr_zone_score"]),
        float(zone["fvg_zone_score"]),
        float(zone["liquidity_score"]),
        float(trendline["trendline_pa_zone_score"]),
    )
    confluence = min(0.08, max(0, int(zone["htf_zone_category_count"]) - 1) * 0.035)
    if int(trendline["trendline_zone_confluence_count"]) > 0:
        confluence += 0.03
    mode_bonus = {
        "R1_reversal_extreme_sr_fvg": 0.05,
        "R2_sweep_reversal": 0.07,
        "R3_trendline_reversal": 0.06,
        "R4_break_retest_reversal": 0.06,
        "C1_htf_aligned_fvg_pullback": 0.03,
        "C2_breakout_retest_continuation": 0.04,
        "C3_channel_or_trendline_continuation": 0.03,
    }.get(mode, 0.0)
    btc_bonus = {"confirm": 0.08, "neutral": 0.02, "warn": -0.04, "veto": -0.14}.get(btc_side_effect, 0.0)
    btc_bonus += clamp(btc_side_score, -1.0, 1.0) * 0.04
    raw = local_location * 0.40 + path_score * 0.25 + float(trendline["trendline_pa_zone_score"]) * 0.10 + confluence + mode_bonus + btc_bonus
    return clamp(raw)


def confidence_bucket(score: float, thesis_valid: bool) -> str:
    if not thesis_valid:
        return "reject"
    if score >= 0.78:
        return "high"
    if score >= 0.64:
        return "medium"
    return "low"


def evaluate_row(row: pd.Series, zone: dict[str, object], trendline: dict[str, object]) -> dict[str, object]:
    side = str(row["side"])
    long_effect, short_effect, btc_side_score = btc_effect_for_side(row, side)
    btc_effect = long_effect if side == "long" else short_effect
    path_score = structural_path_score(row)
    mode = classify_mode(side, zone, trendline, row)
    mode_pass = mode_quality_pass(mode, zone, trendline)
    score = score_thesis(mode, zone, trendline, path_score, btc_effect, btc_side_score)

    local_strength = max(
        float(zone["htf_location_score"]),
        float(zone["sr_zone_score"]),
        float(zone["fvg_zone_score"]),
        float(zone["liquidity_score"]),
        float(trendline["trendline_pa_zone_score"]),
    )
    strong_local_reversal = mode in {
        "R1_reversal_extreme_sr_fvg",
        "R2_sweep_reversal",
        "R3_trendline_reversal",
        "R4_break_retest_reversal",
    } and local_strength >= 0.72

    hard_btc_veto = btc_effect == "veto" and not strong_local_reversal
    soft_btc_veto = btc_effect == "veto" and strong_local_reversal
    if hard_btc_veto:
        side_permission = "hard_veto"
    elif soft_btc_veto:
        side_permission = "soft_veto"
    elif btc_effect == "warn":
        side_permission = "conditional"
    elif btc_effect in {"confirm", "neutral"}:
        side_permission = "allow"
    else:
        side_permission = "conditional"

    reject_reasons: list[str] = []
    if mode == "reject":
        reject_reasons.append("middle_of_range_no_extreme")
    if mode != "reject" and not mode_pass:
        reject_reasons.append("insufficient_mode_quality")
    if str(zone["htf_zone_kind"]) == "none" or float(zone["htf_location_score"]) < 0.20:
        reject_reasons.append("no_htf_pa_zone")
    if max(float(zone["sr_zone_score"]), float(zone["fvg_zone_score"]), float(zone["liquidity_score"]), float(trendline["trendline_pa_zone_score"])) < 0.35:
        reject_reasons.append("middle_of_range_no_extreme")
    if not bool(row["structural_target_pool_present"]):
        reject_reasons.append("no_structural_target_pool")
    if bool(row["fixed_r_only_warning"]):
        reject_reasons.append("fixed_r_only_target")
    if bool(row["nearest_target_too_close"]) and path_score < 0.60:
        reject_reasons.append("nearest_target_too_close_only")
    if not (bool(row["core_structural_source_present"]) or bool(row["runner_structural_source_present"])):
        reject_reasons.append("insufficient_core_runner_path")
    if hard_btc_veto:
        reject_reasons.append("btc_hard_veto")
    if bool(trendline["trendline_clean_break_against_side"]):
        reject_reasons.append("trendline_clean_break_against_side")
    if not bool(row["target_lookahead_pass"]) or not bool(row["btc_lookahead_pass"]):
        reject_reasons.append("lookahead_violation")

    lookahead_sources = [
        row["decision_timestamp"],
        row.get("latest_source_candle_close_used", pd.NaT),
        zone["htf_zone_available_at"],
        zone["htf_zone_latest_source_candle_close_used"],
        trendline["trendline_event_available_at"],
        trendline["trendline_event_latest_source_candle_close_used"],
    ]
    valid_times = [utc_timestamp(value) for value in lookahead_sources if pd.notna(value)]
    decision_timestamp = utc_timestamp(row["decision_timestamp"])
    lookahead_pass = all(value <= decision_timestamp for value in valid_times)
    lookahead_pass = bool(lookahead_pass and bool(row["target_lookahead_pass"]) and bool(row["btc_lookahead_pass"]))
    if not lookahead_pass and "lookahead_violation" not in reject_reasons:
        reject_reasons.append("lookahead_violation")

    has_location = str(zone["htf_zone_kind"]) != "none" and local_strength >= 0.35
    has_path = bool(row["structural_target_pool_present"]) and (
        bool(row["core_structural_source_present"]) or bool(row["runner_structural_source_present"])
    )
    score_pass = score >= 0.62
    thesis_valid = bool(
        lookahead_pass
        and mode != "reject"
        and mode_pass
        and has_location
        and has_path
        and not reject_reasons
        and not hard_btc_veto
        and not bool(trendline["trendline_clean_break_against_side"])
        and not bool(row["fixed_r_only_warning"])
        and score_pass
    )
    craig_dna_pass_proxy = thesis_valid
    bucket = confidence_bucket(score, thesis_valid)
    if not thesis_valid and not reject_reasons:
        reject_reasons.append("insufficient_local_confluence")
    final_mode = mode if thesis_valid else "reject"

    return {
        "thesis_valid": thesis_valid,
        "thesis_mode": final_mode,
        "candidate_thesis_mode": mode if mode in THESIS_MODES else "reject",
        "thesis_score": score,
        "thesis_confidence_bucket": bucket,
        "thesis_side_permission": side_permission,
        "reject_reasons": "|".join(dict.fromkeys(reject_reasons)) if reject_reasons else "none",
        "btc_long_context_effect": long_effect,
        "btc_short_context_effect": short_effect,
        "btc_context_effect_for_side": btc_effect,
        "btc_leader_context_score_for_side": btc_side_score,
        "structural_path_score": path_score,
        "craig_dna_pass_proxy": craig_dna_pass_proxy,
        "lookahead_pass": lookahead_pass,
        "latest_thesis_source_close_used": max(valid_times) if valid_times else decision_timestamp,
    }


def load_inputs(symbols: list[str]) -> tuple[pd.DataFrame, dict[tuple[str, str], ArrayTable], dict[str, ArrayTable]]:
    print("load target summary", flush=True)
    target_summary = pd.read_parquet(TARGET_POOL_SUMMARY_PARQUET)
    target_summary = target_summary[target_summary["symbol"].isin(symbols)].copy()
    target_summary["decision_timestamp"] = pd.to_datetime(target_summary["decision_timestamp"], utc=True)
    target_summary["target_lookahead_pass"] = target_summary["lookahead_pass"].fillna(False).astype(bool)
    target_summary = target_summary.drop(columns=["lookahead_pass"])

    print("load 15m bars", flush=True)
    bars_15m = load_15m_bars(symbols)
    base = target_summary.merge(
        bars_15m,
        on=["symbol", "decision_timestamp"],
        how="left",
        validate="many_to_one",
    )
    if base["reference_price"].isna().any() or base["atr"].isna().any():
        missing = int(base["reference_price"].isna().sum() + base["atr"].isna().sum())
        raise RuntimeError(f"Missing 15m reference bar fields for {missing} merged cells")

    print("load BTC context", flush=True)
    btc = pd.read_parquet(BTC_CONTEXT_PARQUET)
    btc["decision_timestamp"] = pd.to_datetime(btc["decision_timestamp"], utc=True)
    btc = btc.rename(columns={"lookahead_pass": "btc_lookahead_pass"})
    btc_keep = [
        "decision_timestamp",
        "btc_htf_zone_kind",
        "btc_trendline_interaction_type",
        "btc_pa_reaction_state",
        "btc_context_effect",
        "btc_long_context_effect",
        "btc_short_context_effect",
        "btc_context_reason",
        "btc_leader_context_score",
        "btc_lookahead_pass",
        "latest_source_candle_close_used",
    ]
    base = base.merge(btc[btc_keep], on="decision_timestamp", how="left", validate="many_to_one")
    base["btc_lookahead_pass"] = base["btc_lookahead_pass"].fillna(False).astype(bool)

    print("load HTF zones", flush=True)
    htf_zones = pd.read_parquet(HTF_ZONES_PARQUET)
    zone_tables = prepare_zone_tables(htf_zones, symbols)

    print("load trendline interactions", flush=True)
    trendlines = pd.read_parquet(TRENDLINE_ZONES_PARQUET)
    trendline_tables = prepare_trendline_event_tables(trendlines, symbols)
    return base.sort_values(["symbol", "decision_timestamp", "side"]).reset_index(drop=True), zone_tables, trendline_tables


def build_snapshots(base: pd.DataFrame, zone_tables: dict[tuple[str, str], ArrayTable], trendline_tables: dict[str, ArrayTable]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    total = len(base)
    for row_number, row in enumerate(base.itertuples(index=False), 1):
        if row_number == 1 or row_number % 50000 == 0:
            print(f"  thesis rows={row_number}/{total}", flush=True)
        row_s = pd.Series(row._asdict())
        side = str(row_s["side"])
        zone_side = "support" if side == "long" else "resistance"
        decision_ns = int(row_s["decision_ns"])
        reference_price = float(row_s["reference_price"])
        atr = max(float(row_s["atr"]), 1e-12)
        zone = zone_features(zone_tables.get((str(row_s["symbol"]), zone_side)), decision_ns, reference_price, atr)
        trendline = trendline_features(trendline_tables.get(str(row_s["symbol"])), str(row_s["symbol"]), side, decision_ns)
        evaluation = evaluate_row(row_s, zone, trendline)
        rows.append(
            {
                "symbol": str(row_s["symbol"]),
                "decision_timestamp": utc_timestamp(row_s["decision_timestamp"]),
                "side": side,
                "reference_price": reference_price,
                "thesis_valid": evaluation["thesis_valid"],
                "thesis_mode": evaluation["thesis_mode"],
                "candidate_thesis_mode": evaluation["candidate_thesis_mode"],
                "thesis_score": evaluation["thesis_score"],
                "thesis_confidence_bucket": evaluation["thesis_confidence_bucket"],
                "thesis_side_permission": evaluation["thesis_side_permission"],
                "reject_reasons": evaluation["reject_reasons"],
                "htf_zone_kind": zone["htf_zone_kind"],
                "htf_zone_timeframe": zone["htf_zone_timeframe"],
                "htf_location_score": zone["htf_location_score"],
                "sr_zone_score": zone["sr_zone_score"],
                "fvg_zone_score": zone["fvg_zone_score"],
                "liquidity_score": zone["liquidity_score"],
                "trendline_pa_zone_score": trendline["trendline_pa_zone_score"],
                "trendline_interaction_type": trendline["trendline_interaction_type"],
                "trendline_zone_confluence_count": trendline["trendline_zone_confluence_count"],
                "btc_long_context_effect": evaluation["btc_long_context_effect"],
                "btc_short_context_effect": evaluation["btc_short_context_effect"],
                "btc_context_effect_for_side": evaluation["btc_context_effect_for_side"],
                "btc_context_reason": str(row_s.get("btc_context_reason", "")),
                "btc_leader_context_score_for_side": evaluation["btc_leader_context_score_for_side"],
                "target_pool_present": bool(row_s["structural_target_pool_present"]),
                "tp1_candidate_present": bool(str(row_s.get("tp1_candidate_target_id", ""))),
                "core_candidate_present": bool(row_s["core_structural_source_present"]),
                "runner_candidate_present": bool(row_s["runner_structural_source_present"]),
                "structural_path_score": evaluation["structural_path_score"],
                "nearest_target_too_close": bool(row_s["nearest_target_too_close"]),
                "target_pool_conflict_reason": str(row_s["target_pool_conflict_reason"]),
                "craig_dna_pass_proxy": evaluation["craig_dna_pass_proxy"],
                "lookahead_pass": evaluation["lookahead_pass"],
                "btc_htf_zone_kind": str(row_s.get("btc_htf_zone_kind", "none")),
                "btc_pa_reaction_state": str(row_s.get("btc_pa_reaction_state", "none")),
                "btc_trendline_interaction_type": str(row_s.get("btc_trendline_interaction_type", "none")),
                "btc_context_effect_raw": str(row_s.get("btc_context_effect", "neutral")),
                "htf_zone_object_id": zone["htf_zone_object_id"],
                "htf_zone_available_at": zone["htf_zone_available_at"],
                "htf_zone_latest_source_candle_close_used": zone["htf_zone_latest_source_candle_close_used"],
                "htf_zone_distance_atr": zone["htf_zone_distance_atr"],
                "trendline_event_id": trendline["trendline_event_id"],
                "trendline_supportive_role": trendline["trendline_supportive_role"],
                "trendline_clean_break_against_side": trendline["trendline_clean_break_against_side"],
                "trendline_event_available_at": trendline["trendline_event_available_at"],
                "trendline_event_latest_source_candle_close_used": trendline["trendline_event_latest_source_candle_close_used"],
                "target_lookahead_pass": bool(row_s["target_lookahead_pass"]),
                "btc_lookahead_pass": bool(row_s["btc_lookahead_pass"]),
                "latest_btc_source_close_used": row_s.get("latest_source_candle_close_used", pd.NaT),
                "latest_thesis_source_close_used": evaluation["latest_thesis_source_close_used"],
                "lookahead_violation_reason": "" if evaluation["lookahead_pass"] else "source_available_after_decision_timestamp",
            }
        )
    return pd.DataFrame(rows)


def build_audit(snapshots: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "symbol",
        "decision_timestamp",
        "side",
        "thesis_valid",
        "thesis_mode",
        "thesis_side_permission",
        "htf_zone_available_at",
        "htf_zone_latest_source_candle_close_used",
        "trendline_event_available_at",
        "trendline_event_latest_source_candle_close_used",
        "latest_btc_source_close_used",
        "latest_thesis_source_close_used",
        "target_lookahead_pass",
        "btc_lookahead_pass",
        "lookahead_pass",
        "lookahead_violation_reason",
    ]
    audit = snapshots[columns].copy()
    time_cols = [
        "decision_timestamp",
        "htf_zone_available_at",
        "htf_zone_latest_source_candle_close_used",
        "trendline_event_available_at",
        "trendline_event_latest_source_candle_close_used",
        "latest_btc_source_close_used",
        "latest_thesis_source_close_used",
    ]
    for column in time_cols:
        audit[column] = pd.to_datetime(audit[column], utc=True, errors="coerce")
    checks = []
    for column in time_cols[1:]:
        checks.append(audit[column].isna() | (audit[column] <= audit["decision_timestamp"]))
    lookahead = checks[0]
    for check in checks[1:]:
        lookahead = lookahead & check
    lookahead = lookahead & audit["target_lookahead_pass"].astype(bool) & audit["btc_lookahead_pass"].astype(bool)
    audit["lookahead_pass"] = lookahead.astype(bool)
    audit.loc[audit["lookahead_pass"], "lookahead_violation_reason"] = ""
    audit.loc[~audit["lookahead_pass"], "lookahead_violation_reason"] = "source_available_after_decision_timestamp"
    return audit


def exploded_reason_counts(snapshots: pd.DataFrame) -> pd.DataFrame:
    reasons = snapshots["reject_reasons"].fillna("none").astype(str).str.split("|").explode()
    reasons = reasons[reasons.ne("")]
    return reasons.value_counts().reset_index().rename(columns={"index": "reject_reason", "reject_reasons": "rows"})


def write_report(snapshots: pd.DataFrame, audit: pd.DataFrame, symbols: list[str]) -> None:
    valid_counts = snapshots["thesis_valid"].value_counts().reset_index()
    valid_counts.columns = ["thesis_valid", "rows"]
    mode_counts = snapshots["thesis_mode"].value_counts().reset_index()
    mode_counts.columns = ["thesis_mode", "rows"]
    rejected_candidate_mode_counts = snapshots.loc[
        ~snapshots["thesis_valid"], "candidate_thesis_mode"
    ].value_counts().reset_index()
    rejected_candidate_mode_counts.columns = ["candidate_thesis_mode_when_rejected", "rows"]
    reason_counts = exploded_reason_counts(snapshots)
    btc_counts = snapshots["btc_context_effect_for_side"].value_counts().reset_index()
    btc_counts.columns = ["btc_context_effect_for_side", "rows"]
    dna_counts = snapshots["craig_dna_pass_proxy"].value_counts().reset_index()
    dna_counts.columns = ["craig_dna_pass_proxy", "rows"]
    permission_counts = snapshots["thesis_side_permission"].value_counts().reset_index()
    permission_counts.columns = ["thesis_side_permission", "rows"]
    side_counts = snapshots.groupby(["symbol", "side", "thesis_valid"]).size().reset_index(name="rows")
    violations = int((~audit["lookahead_pass"]).sum())
    hard_veto = int(snapshots["thesis_side_permission"].eq("hard_veto").sum())
    soft_veto = int(snapshots["thesis_side_permission"].eq("soft_veto").sum())

    spot_rows = []
    for symbol in symbols:
        for side in ["long", "short"]:
            sample = snapshots[
                snapshots["symbol"].eq(symbol)
                & snapshots["side"].eq(side)
                & snapshots["thesis_valid"]
            ].copy()
            if not sample.empty:
                sample["_spot_distance"] = (sample["thesis_score"] - 0.72).abs()
                sample = sample.sort_values(["_spot_distance", "decision_timestamp"]).head(1)
            if sample.empty:
                sample = snapshots[snapshots["symbol"].eq(symbol) & snapshots["side"].eq(side)].head(1)
            if sample.empty:
                continue
            row = sample.iloc[0]
            spot_rows.append(
                {
                    "symbol": symbol,
                    "decision_timestamp": row["decision_timestamp"],
                    "side": side,
                    "mode": row["thesis_mode"],
                    "score": round(float(row["thesis_score"]), 3),
                    "btc_for_side": row["btc_context_effect_for_side"],
                    "reason": row["reject_reasons"],
                    "local": f"{row['htf_zone_kind']} sr={row['sr_zone_score']:.2f} fvg={row['fvg_zone_score']:.2f} liq={row['liquidity_score']:.2f} tl={row['trendline_pa_zone_score']:.2f}",
                }
            )

    lines = [
        "# Craig v1.2 Thesis Snapshot Build Report",
        "",
        "Generated by `scripts/build_craig_v1_2_thesis_snapshots.py`.",
        "",
        "## Verdict",
        "",
        "- Thesis snapshots were built for SOLUSDT/ETHUSDT closed 15m decision timestamps and both long/short sides.",
        "- This stage classifies Craig DNA thesis validity only; it does not create entries, stops, take-profits, fills, PnL, or optimized parameters.",
        "- BTC context is converted into side-aware long/short effects and used as context, not as a blind direction copy.",
        f"- Lookahead violations: {violations}.",
        "",
        "## Dataset And Grain",
        "",
        f"- Symbols: {', '.join(symbols)}",
        f"- Thesis snapshot rows: {len(snapshots)}",
        "- Snapshot grain: closed 15m candle per symbol and side.",
        "- Target pool fields are used only as structural path evidence; planned RR remains undefined until entry/SL construction.",
        "",
        "## Thesis Valid Distribution",
        "",
        *markdown_table(valid_counts.to_dict("records"), ["thesis_valid", "rows"]),
        "",
        "## Thesis Mode Distribution",
        "",
        *markdown_table(mode_counts.to_dict("records"), ["thesis_mode", "rows"]),
        "",
        "## Rejected Candidate Mode Distribution",
        "",
        *markdown_table(rejected_candidate_mode_counts.to_dict("records"), ["candidate_thesis_mode_when_rejected", "rows"]),
        "",
        "## Reject Reason Distribution",
        "",
        *markdown_table(reason_counts.head(20).to_dict("records"), ["reject_reason", "rows"]),
        "",
        "## BTC Side-Aware Context",
        "",
        *markdown_table(btc_counts.to_dict("records"), ["btc_context_effect_for_side", "rows"]),
        "",
        "## BTC Veto Strength",
        "",
        f"- hard_veto rows: {hard_veto}",
        f"- soft_veto rows: {soft_veto}",
        "- `soft_veto` means BTC opposes the side, but local reversal evidence is strong enough to keep the row as conditional context rather than a hard reject.",
        "",
        "## Craig DNA Pass Proxy Distribution",
        "",
        *markdown_table(dna_counts.to_dict("records"), ["craig_dna_pass_proxy", "rows"]),
        "",
        "## Side Permission Distribution",
        "",
        *markdown_table(permission_counts.to_dict("records"), ["thesis_side_permission", "rows"]),
        "",
        "## Symbol/Side Validity",
        "",
        *markdown_table(side_counts.to_dict("records"), ["symbol", "side", "thesis_valid", "rows"]),
        "",
        "## Spot Checks",
        "",
        *markdown_table(spot_rows, ["symbol", "decision_timestamp", "side", "mode", "score", "btc_for_side", "reason", "local"]),
        "",
        "## No-Lookahead Controls",
        "",
        "- HTF PA-zone `available_at` and `latest_source_candle_close_used` must be less than or equal to `decision_timestamp`.",
        "- Trendline interaction event `available_at` and source close must be less than or equal to `decision_timestamp`.",
        "- BTC context uses its own closed-candle source audit and is joined only at the same or earlier decision timestamp.",
        "- Target pool summary is consumed through its prior `lookahead_pass` field; no future target, gold label, Craig action, result R, entry, stop, TP, or PnL is read.",
        "",
        "## Output Paths",
        "",
        f"- Thesis snapshots: `{rel(OUT_SNAPSHOTS)}`",
        f"- Thesis audit: `{rel(OUT_AUDIT)}`",
        "",
        "## Next Step Recommendation",
        "",
        "Build the 1m precision entry plus thesis-invalidation stop constructor next. It should consume only `thesis_valid=true` rows, wait for a 1m trigger inside or adjacent to the approved HTF/15m zone, place stops beyond thesis invalidation rather than arbitrary tight risk, and only then compute planned core/runner RR from the already-built structural target pool.",
    ]
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=HEADLINE_SYMBOLS)
    args = parser.parse_args()
    symbols = [symbol.upper() for symbol in args.symbols]

    base, zone_tables, trendline_tables = load_inputs(symbols)
    print("build thesis snapshots", flush=True)
    snapshots = build_snapshots(base, zone_tables, trendline_tables)
    audit = build_audit(snapshots)
    if not audit["lookahead_pass"].all():
        failures = int((~audit["lookahead_pass"]).sum())
        raise RuntimeError(f"Thesis lookahead audit failed for {failures} rows")

    OUT_SNAPSHOTS.parent.mkdir(parents=True, exist_ok=True)
    snapshots.to_parquet(OUT_SNAPSHOTS, index=False)
    audit.to_csv(OUT_AUDIT, index=False, encoding="utf-8-sig")
    write_report(snapshots, audit, symbols)
    print(f"thesis_snapshots={OUT_SNAPSHOTS} rows={len(snapshots)}")
    print(f"audit={OUT_AUDIT} rows={len(audit)} lookahead_pass={int(audit['lookahead_pass'].sum())}/{len(audit)}")
    print(f"report={OUT_REPORT}")


if __name__ == "__main__":
    main()
