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
THESIS_PARQUET = ROOT / "outputs/craig_v1_2_thesis_snapshots.parquet"
TARGET_POOLS_PARQUET = ROOT / "outputs/craig_v1_2_target_pools.parquet"
TARGET_SUMMARY_PARQUET = ROOT / "outputs/craig_v1_2_target_pool_summary.parquet"
HTF_ZONES_PARQUET = ROOT / "outputs/craig_v1_2_htf_zones.parquet"
TRENDLINE_ZONES_PARQUET = ROOT / "outputs/craig_v1_2_trendline_zones.parquet"
BTC_CONTEXT_PARQUET = ROOT / "outputs/craig_v1_2_btc_context_snapshots.parquet"

OUT_CANDIDATES = ROOT / "outputs/craig_v1_2_trade_candidates.parquet"
OUT_AUDIT = ROOT / "outputs/craig_v1_2_trade_candidate_audit.csv"
OUT_REPORT = ROOT / "outputs/craig_v1_2_trade_candidate_build_report.md"

HEADLINE_SYMBOLS = ["SOLUSDT", "ETHUSDT"]
TRIGGER_EXPIRY_MINUTES = 45
SIDE_SCORE_GAP_MIN = 0.07
CONTINUATION_OVER_REVERSAL_GAP = 0.20
MIN_CORE_RR_NET = 3.0
MIN_RUNNER_RR_NET = 7.0
MAX_CHASE_ATR = 1.15
MAX_STOP_ATR = 1.60
MIN_STOP_ATR = 0.20
MIN_TRIGGER_CONFLUENCE = 3
MIN_ACCEPTED_ENTRY_QUALITY = 0.78
MAX_CORE_TARGET_DISTANCE_ATR = 10.0
MAX_STALE_CORE_TARGET_DISTANCE_ATR = 5.0
MAX_RUNNER_TARGET_DISTANCE_ATR = 30.0
ATR_PERIOD = 14

TIMEFRAME_MINUTES = {"5m": 5, "15m": 15, "1h": 60, "4h": 240}
RESAMPLE_RULES = {"5m": "5T", "15m": "15T", "1h": "1H", "4h": "4H"}
REVERSAL_MODES = {
    "R1_reversal_extreme_sr_fvg",
    "R2_sweep_reversal",
    "R3_trendline_reversal",
    "R4_break_retest_reversal",
}
CONTINUATION_MODES = {
    "C1_htf_aligned_fvg_pullback",
    "C2_breakout_retest_continuation",
    "C3_channel_or_trendline_continuation",
}
STATUS_VALUES = {
    "accepted",
    "rejected_side_conflict",
    "rejected_no_1m_trigger",
    "rejected_no_chase",
    "rejected_invalid_stop",
    "rejected_rr_below_dna",
    "rejected_no_structural_target",
    "rejected_lookahead",
    "rejected_other",
}


@dataclass(frozen=True)
class MarketData:
    bars_1m: pd.DataFrame
    tf_bars: dict[str, pd.DataFrame]
    close_ns_1m: np.ndarray
    open_: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    atr_1m: np.ndarray
    prev5_high: np.ndarray
    prev5_low: np.ndarray
    prev10_high: np.ndarray
    prev10_low: np.ndarray


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


def find_symbol_parquet(symbol: str) -> Path:
    candidates = sorted((PROCESSED_ROOT / symbol / "1m").glob(f"{symbol}_1m_*.parquet"))
    if not candidates:
        raise FileNotFoundError(f"No normalized continuous parquet found for {symbol}")
    return candidates[-1]


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
    bars["close_time_ns"] = pd.to_datetime(bars["close_time"], utc=True).astype("int64")
    return bars


def load_market_data(symbol: str) -> MarketData:
    path = find_symbol_parquet(symbol)
    df = pd.read_parquet(path, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")
    df = df.drop_duplicates("timestamp", keep="last").reset_index(drop=True)
    df["close_time"] = df["timestamp"] + pd.Timedelta(minutes=1)
    df["close_time_ns"] = pd.to_datetime(df["close_time"], utc=True).astype("int64")
    df["atr_1m"] = compute_atr(df)
    df["prev5_high"] = df["high"].shift(1).rolling(5, min_periods=1).max()
    df["prev5_low"] = df["low"].shift(1).rolling(5, min_periods=1).min()
    df["prev10_high"] = df["high"].shift(1).rolling(10, min_periods=1).max()
    df["prev10_low"] = df["low"].shift(1).rolling(10, min_periods=1).min()
    tf_bars = {timeframe: resample_ohlcv(df, timeframe) for timeframe in ["5m", "15m", "1h", "4h"]}
    return MarketData(
        bars_1m=df,
        tf_bars=tf_bars,
        close_ns_1m=df["close_time_ns"].to_numpy(dtype="int64"),
        open_=df["open"].astype(float).to_numpy(),
        high=df["high"].astype(float).to_numpy(),
        low=df["low"].astype(float).to_numpy(),
        close=df["close"].astype(float).to_numpy(),
        atr_1m=df["atr_1m"].astype(float).to_numpy(),
        prev5_high=df["prev5_high"].astype(float).to_numpy(),
        prev5_low=df["prev5_low"].astype(float).to_numpy(),
        prev10_high=df["prev10_high"].astype(float).to_numpy(),
        prev10_low=df["prev10_low"].astype(float).to_numpy(),
    )


def latest_tf_close(tf_bars: pd.DataFrame, timestamp_ns: int) -> pd.Timestamp:
    values = tf_bars["close_time_ns"].to_numpy(dtype="int64")
    pos = int(np.searchsorted(values, timestamp_ns, side="right")) - 1
    if pos < 0:
        return pd.NaT
    return ns_to_utc(values[pos])


def latest_tf_close_ns(tf_bars: pd.DataFrame, timestamp_ns: int) -> int | None:
    values = tf_bars["close_time_ns"].to_numpy(dtype="int64")
    pos = int(np.searchsorted(values, timestamp_ns, side="right")) - 1
    if pos < 0:
        return None
    return int(values[pos])


def side_sign(side: str) -> int:
    return 1 if side == "long" else -1


def mode_priority(mode: str) -> float:
    return {
        "R2_sweep_reversal": 0.12,
        "R3_trendline_reversal": 0.11,
        "R4_break_retest_reversal": 0.10,
        "R1_reversal_extreme_sr_fvg": 0.09,
        "C2_breakout_retest_continuation": 0.03,
        "C3_channel_or_trendline_continuation": 0.02,
        "C1_htf_aligned_fvg_pullback": 0.02,
    }.get(str(mode), 0.0)


def context_bonus(effect: str) -> float:
    return {"confirm": 0.08, "neutral": 0.02, "warn": -0.03, "veto": -0.09}.get(str(effect), 0.0)


def permission_bonus(permission: str) -> float:
    return {"allow": 0.06, "conditional": 0.00, "soft_veto": -0.08, "hard_veto": -0.30}.get(str(permission), 0.0)


def conflict_penalty(reason: str) -> float:
    return {
        "none": 0.00,
        "nearest_target_too_close": 0.06,
        "no_runner_distance_proxy_requires_entry_sl": 0.05,
        "no_core_distance_proxy_requires_entry_sl": 0.10,
        "no_structural_target": 0.30,
    }.get(str(reason), 0.04)


def displacement_score(market: MarketData, decision_ns: int, side: str, reference_price: float, atr_15m: float) -> float:
    pos = int(np.searchsorted(market.close_ns_1m, decision_ns, side="right")) - 1
    if pos <= 15 or atr_15m <= 0:
        return 0.0
    close_now = market.close[pos]
    close_5 = market.close[max(0, pos - 5)]
    close_15 = market.close[max(0, pos - 15)]
    raw = ((close_now - close_5) * 0.55 + (close_now - close_15) * 0.45) / atr_15m
    signed = raw * side_sign(side)
    return clamp(np.tanh(signed), -1.0, 1.0)


def arbitration_score(row: pd.Series, market: MarketData) -> float:
    decision_ns = utc_timestamp(row["decision_timestamp"]).value
    reference_price = float(row["reference_price"])
    latest_15m = latest_tf_close_ns(market.tf_bars["15m"], decision_ns)
    atr_15m = float(row.get("atr_15m", np.nan))
    if pd.isna(atr_15m) or atr_15m <= 0:
        if latest_15m is not None:
            values = market.tf_bars["15m"]["close_time_ns"].to_numpy(dtype="int64")
            pos = int(np.searchsorted(values, latest_15m, side="right")) - 1
            atr_15m = float(market.tf_bars["15m"].iloc[max(pos, 0)]["atr"])
        else:
            atr_15m = max(reference_price * 0.002, 1e-9)
    local_confluence = max(float(row["sr_zone_score"]), float(row["fvg_zone_score"]), float(row["liquidity_score"]))
    displacement = displacement_score(market, decision_ns, str(row["side"]), reference_price, atr_15m)
    score = (
        float(row["thesis_score"]) * 0.34
        + float(row["structural_path_score"]) * 0.18
        + float(row["trendline_pa_zone_score"]) * 0.12
        + local_confluence * 0.14
        + mode_priority(str(row["thesis_mode"]))
        + context_bonus(str(row["btc_context_effect_for_side"]))
        + permission_bonus(str(row["thesis_side_permission"]))
        + displacement * 0.08
        - conflict_penalty(str(row["target_pool_conflict_reason"]))
    )
    return float(score)


def is_reversal(mode: str) -> bool:
    return str(mode) in REVERSAL_MODES


def is_continuation(mode: str) -> bool:
    return str(mode) in CONTINUATION_MODES


def arbitrate_side(group: pd.DataFrame, market: MarketData) -> dict[str, object]:
    valid = group[group["thesis_valid"].astype(bool)].copy()
    if valid.empty:
        return {
            "selected_row": None,
            "side_arbitration_state": "rejected_both",
            "side_arbitration_reason": "no_valid_thesis_side",
            "selected_side_score": np.nan,
            "opposing_side_score": np.nan,
            "side_score_gap": np.nan,
        }
    valid["side_score"] = [arbitration_score(row, market) for _, row in valid.iterrows()]
    if len(valid) == 1:
        row = valid.iloc[0]
        return {
            "selected_row": row,
            "side_arbitration_state": "single_side",
            "side_arbitration_reason": "only_one_valid_thesis_side",
            "selected_side_score": float(row["side_score"]),
            "opposing_side_score": np.nan,
            "side_score_gap": np.nan,
        }
    long_row = valid[valid["side"].eq("long")].iloc[0] if valid["side"].eq("long").any() else None
    short_row = valid[valid["side"].eq("short")].iloc[0] if valid["side"].eq("short").any() else None
    if long_row is None or short_row is None:
        best = valid.sort_values("side_score", ascending=False).iloc[0]
        return {
            "selected_row": best,
            "side_arbitration_state": "single_side",
            "side_arbitration_reason": "duplicate_or_missing_side_after_valid_filter",
            "selected_side_score": float(best["side_score"]),
            "opposing_side_score": np.nan,
            "side_score_gap": np.nan,
        }
    long_score = float(long_row["side_score"])
    short_score = float(short_row["side_score"])
    gap = abs(long_score - short_score)
    if gap < SIDE_SCORE_GAP_MIN:
        return {
            "selected_row": None,
            "side_arbitration_state": "unresolved_conflict",
            "side_arbitration_reason": f"side_score_gap_below_{SIDE_SCORE_GAP_MIN:.2f}",
            "selected_side_score": max(long_score, short_score),
            "opposing_side_score": min(long_score, short_score),
            "side_score_gap": gap,
        }

    provisional = long_row if long_score > short_score else short_row
    opposing = short_row if long_score > short_score else long_row
    provisional_score = max(long_score, short_score)
    opposing_score = min(long_score, short_score)

    if is_continuation(str(provisional["thesis_mode"])) and is_reversal(str(opposing["thesis_mode"])):
        if provisional_score - opposing_score < CONTINUATION_OVER_REVERSAL_GAP:
            return {
                "selected_row": opposing,
                "side_arbitration_state": f"{opposing['side']}_wins",
                "side_arbitration_reason": "reversal_mode_preserved_over_marginal_continuation_advantage",
                "selected_side_score": float(opposing_score),
                "opposing_side_score": float(provisional_score),
                "side_score_gap": float(provisional_score - opposing_score),
            }

    state = "long_wins" if str(provisional["side"]) == "long" else "short_wins"
    return {
        "selected_row": provisional,
        "side_arbitration_state": state,
        "side_arbitration_reason": "higher_side_score_after_btc_structure_mode_displacement_arbitration",
        "selected_side_score": float(provisional_score),
        "opposing_side_score": float(opposing_score),
        "side_score_gap": float(gap),
    }


def load_zone_map(symbols: list[str]) -> dict[str, dict[str, object]]:
    zones = pd.read_parquet(
        HTF_ZONES_PARQUET,
        columns=[
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
        ],
    )
    zones = zones[zones["symbol"].isin(symbols)].copy()
    zones["available_at"] = pd.to_datetime(zones["available_at"], utc=True)
    zones["latest_source_candle_close_used"] = pd.to_datetime(zones["latest_source_candle_close_used"], utc=True)
    return {
        str(row.object_id): {
            "object_id": str(row.object_id),
            "symbol": str(row.symbol),
            "timeframe": str(row.timeframe),
            "object_type": str(row.object_type),
            "side": str(row.side),
            "zone_low": float(row.zone_low),
            "zone_high": float(row.zone_high),
            "zone_mid": float(row.zone_mid),
            "available_at": pd.Timestamp(row.available_at),
            "latest_source_candle_close_used": pd.Timestamp(row.latest_source_candle_close_used),
        }
        for row in zones.itertuples(index=False)
    }


def load_target_lookup() -> dict[str, dict[str, object]]:
    cols = [
        "target_id",
        "target_source",
        "target_timeframe",
        "target_price",
        "target_mid",
        "target_side",
        "available_at",
        "latest_source_candle_close_used",
        "freshness_state",
        "distance_atr",
        "target_quality_score",
        "structural_target_rank",
        "target_conflict_reason",
        "used_as_tp1_candidate",
        "used_as_core_candidate",
        "used_as_runner_candidate",
        "lookahead_pass",
    ]
    targets = pd.read_parquet(TARGET_POOLS_PARQUET, columns=cols)
    role_mask = (
        targets["used_as_tp1_candidate"].astype(bool)
        | targets["used_as_core_candidate"].astype(bool)
        | targets["used_as_runner_candidate"].astype(bool)
    )
    targets = targets[role_mask].copy()
    targets["available_at"] = pd.to_datetime(targets["available_at"], utc=True)
    targets["latest_source_candle_close_used"] = pd.to_datetime(targets["latest_source_candle_close_used"], utc=True)
    return {
        str(row.target_id): {
            "target_id": str(row.target_id),
            "target_source": str(row.target_source),
            "target_timeframe": str(row.target_timeframe),
            "target_price": float(row.target_price),
            "target_mid": float(row.target_mid),
            "target_side": str(row.target_side),
            "available_at": pd.Timestamp(row.available_at),
            "latest_source_candle_close_used": pd.Timestamp(row.latest_source_candle_close_used),
            "freshness_state": str(row.freshness_state),
            "distance_atr": float(row.distance_atr),
            "target_quality_score": float(row.target_quality_score),
            "structural_target_rank": int(row.structural_target_rank),
            "target_conflict_reason": str(row.target_conflict_reason),
            "lookahead_pass": bool(row.lookahead_pass),
        }
        for row in targets.itertuples(index=False)
    }


def load_target_summary(symbols: list[str]) -> pd.DataFrame:
    summary = pd.read_parquet(TARGET_SUMMARY_PARQUET)
    summary = summary[summary["symbol"].isin(symbols)].copy()
    summary["decision_timestamp"] = pd.to_datetime(summary["decision_timestamp"], utc=True)
    return summary


def directional_move(side: str, current_price: float, reference_price: float) -> float:
    return (current_price - reference_price) * side_sign(side)


def candle_body_score(open_: float, high: float, low: float, close: float, side: str) -> float:
    rng = max(high - low, 1e-12)
    body = abs(close - open_)
    close_location = (close - low) / rng if side == "long" else (high - close) / rng
    direction_ok = close >= open_ if side == "long" else close <= open_
    return (body / rng) * 0.55 + close_location * 0.45 if direction_ok else 0.0


def overlaps_zone(low: float, high: float, zone_low: float, zone_high: float, tolerance: float) -> bool:
    return high >= zone_low - tolerance and low <= zone_high + tolerance


def trigger_quality(trigger_type: str, side: str, row: pd.Series, confluence_count: int, body_score: float) -> float:
    base = {
        "1m_sweep_reclaim": 0.74,
        "1m_choch_bos_proxy": 0.68,
        "1m_displacement_candle": 0.60,
        "1m_fvg_creation_retrace": 0.72,
        "approved_htf_zone_retest": 0.64,
        "trendline_retest_rejection": 0.70,
        "sr_flip_retest": 0.66,
        "none": 0.0,
    }.get(trigger_type, 0.0)
    _ = side
    score = base + min(0.14, confluence_count * 0.04) + body_score * 0.12
    if str(row["btc_context_effect_for_side"]) == "confirm":
        score += 0.04
    elif str(row["btc_context_effect_for_side"]) == "warn":
        score -= 0.02
    elif str(row["btc_context_effect_for_side"]) == "veto":
        score -= 0.06
    if str(row["thesis_side_permission"]) == "soft_veto":
        score -= 0.05
    return clamp(score)


def no_trigger_dict(reason: str, no_chase: bool = False) -> dict[str, object]:
    return {
        "entry_trigger_type": "none",
        "trigger_timestamp": pd.NaT,
        "trigger_available_at": pd.NaT,
        "trigger_reference_candle_close": pd.NaT,
        "entry_model": "no_entry",
        "entry_price": np.nan,
        "entry_zone_low": np.nan,
        "entry_zone_high": np.nan,
        "entry_quality_score": 0.0,
        "entry_inside_approved_zone": False,
        "trigger_confluence_count": 0,
        "trigger_reject_reason": reason,
        "trigger_index": -1,
        "trigger_low": np.nan,
        "trigger_high": np.nan,
        "fvg_low": np.nan,
        "fvg_high": np.nan,
        "no_chase_triggered": no_chase,
        "missed_no_chase_reason": reason if no_chase else "",
        "latest_1m_close_used": pd.NaT,
        "latest_5m_close_used": pd.NaT,
    }


def find_1m_trigger(
    row: pd.Series,
    zone: dict[str, object] | None,
    market: MarketData,
    order_expiry_minutes: int,
) -> dict[str, object]:
    if zone is None:
        return no_trigger_dict("no_approved_htf_zone_for_1m_trigger")
    side = str(row["side"])
    reference_price = float(row["reference_price"])
    decision_ts = utc_timestamp(row["decision_timestamp"])
    decision_ns = decision_ts.value
    expiry_ns = (decision_ts + pd.Timedelta(minutes=order_expiry_minutes)).value
    start = int(np.searchsorted(market.close_ns_1m, decision_ns, side="right"))
    end = int(np.searchsorted(market.close_ns_1m, expiry_ns, side="right"))
    if start >= end:
        return no_trigger_dict("no_1m_bars_inside_expiry_window")

    latest_15_pos = int(np.searchsorted(market.tf_bars["15m"]["close_time_ns"].to_numpy(dtype="int64"), decision_ns, side="right")) - 1
    atr_15m = float(market.tf_bars["15m"].iloc[max(latest_15_pos, 0)]["atr"]) if latest_15_pos >= 0 else max(reference_price * 0.002, 1e-9)
    zone_low = float(zone["zone_low"])
    zone_high = float(zone["zone_high"])
    zone_mid = float(zone["zone_mid"])
    tolerance = max(0.05 * atr_15m, 0.0005 * reference_price)
    max_excursion = 0.0
    pending_fvg: dict[str, float] | None = None

    for i in range(start, end):
        open_i = float(market.open_[i])
        high_i = float(market.high[i])
        low_i = float(market.low[i])
        close_i = float(market.close[i])
        close_ns = int(market.close_ns_1m[i])
        max_excursion = max(max_excursion, directional_move(side, high_i if side == "long" else low_i, reference_price))
        if directional_move(side, close_i, reference_price) > MAX_CHASE_ATR * atr_15m and not overlaps_zone(low_i, high_i, zone_low, zone_high, tolerance):
            return no_trigger_dict("price_left_thesis_zone_before_valid_retest", no_chase=True)

        inside_zone = overlaps_zone(low_i, high_i, zone_low, zone_high, tolerance)
        if not inside_zone:
            if i >= 2:
                if side == "long" and market.low[i] > market.high[i - 2]:
                    pending_fvg = {"low": float(market.high[i - 2]), "high": float(market.low[i]), "mid": float((market.high[i - 2] + market.low[i]) / 2.0)}
                elif side == "short" and market.high[i] < market.low[i - 2]:
                    pending_fvg = {"low": float(market.high[i]), "high": float(market.low[i - 2]), "mid": float((market.high[i] + market.low[i - 2]) / 2.0)}
            continue

        body_score = candle_body_score(open_i, high_i, low_i, close_i, side)
        confluence_count = int(row["trendline_zone_confluence_count"])
        if float(row["sr_zone_score"]) >= 0.35:
            confluence_count += 1
        if float(row["fvg_zone_score"]) >= 0.35:
            confluence_count += 1
        if float(row["liquidity_score"]) >= 0.35:
            confluence_count += 1
        strong_confluence = confluence_count >= MIN_TRIGGER_CONFLUENCE

        if pending_fvg is not None and low_i <= pending_fvg["mid"] <= high_i and strong_confluence and body_score >= 0.25:
            entry_price = float(pending_fvg["mid"])
            return {
                "entry_trigger_type": "1m_fvg_creation_retrace",
                "trigger_timestamp": ns_to_utc(close_ns),
                "trigger_available_at": ns_to_utc(close_ns),
                "trigger_reference_candle_close": ns_to_utc(close_ns),
                "entry_model": "limit_fvg_mid",
                "entry_price": entry_price,
                "entry_zone_low": float(pending_fvg["low"]),
                "entry_zone_high": float(pending_fvg["high"]),
                "entry_quality_score": trigger_quality("1m_fvg_creation_retrace", side, row, confluence_count, body_score),
                "entry_inside_approved_zone": True,
                "trigger_confluence_count": confluence_count,
                "trigger_reject_reason": "none",
                "trigger_index": i,
                "trigger_low": low_i,
                "trigger_high": high_i,
                "fvg_low": float(pending_fvg["low"]),
                "fvg_high": float(pending_fvg["high"]),
                "no_chase_triggered": False,
                "missed_no_chase_reason": "",
                "latest_1m_close_used": ns_to_utc(close_ns),
                "latest_5m_close_used": latest_tf_close(market.tf_bars["5m"], close_ns),
            }

        sweep = False
        if side == "long":
            sweep = low_i < float(market.prev5_low[i]) and close_i > float(market.prev5_low[i]) and close_i >= open_i
        else:
            sweep = high_i > float(market.prev5_high[i]) and close_i < float(market.prev5_high[i]) and close_i <= open_i
        if sweep and strong_confluence and body_score >= 0.35:
            entry_price = close_i
            return {
                "entry_trigger_type": "1m_sweep_reclaim",
                "trigger_timestamp": ns_to_utc(close_ns),
                "trigger_available_at": ns_to_utc(close_ns),
                "trigger_reference_candle_close": ns_to_utc(close_ns),
                "entry_model": "confirmation_market",
                "entry_price": entry_price,
                "entry_zone_low": zone_low,
                "entry_zone_high": zone_high,
                "entry_quality_score": trigger_quality("1m_sweep_reclaim", side, row, confluence_count, body_score),
                "entry_inside_approved_zone": True,
                "trigger_confluence_count": confluence_count,
                "trigger_reject_reason": "none",
                "trigger_index": i,
                "trigger_low": low_i,
                "trigger_high": high_i,
                "fvg_low": np.nan,
                "fvg_high": np.nan,
                "no_chase_triggered": False,
                "missed_no_chase_reason": "",
                "latest_1m_close_used": ns_to_utc(close_ns),
                "latest_5m_close_used": latest_tf_close(market.tf_bars["5m"], close_ns),
            }

        trendline_interaction = str(row["trendline_interaction_type"])
        trendline_score = float(row["trendline_pa_zone_score"])
        trendline_trigger = (
            (
                trendline_interaction in {"sweep", "rejection", "break_retest"}
                and body_score >= 0.52
                and trendline_score >= 0.45
                and strong_confluence
            )
            or (
                trendline_interaction == "near_touch"
                and body_score >= 0.65
                and trendline_score >= 0.65
                and confluence_count >= 3
            )
        )
        if trendline_trigger:
            entry_price = zone_high if side == "long" else zone_low
            return {
                "entry_trigger_type": "trendline_retest_rejection",
                "trigger_timestamp": ns_to_utc(close_ns),
                "trigger_available_at": ns_to_utc(close_ns),
                "trigger_reference_candle_close": ns_to_utc(close_ns),
                "entry_model": "limit_retest_edge",
                "entry_price": float(entry_price),
                "entry_zone_low": zone_low,
                "entry_zone_high": zone_high,
                "entry_quality_score": trigger_quality("trendline_retest_rejection", side, row, confluence_count, body_score),
                "entry_inside_approved_zone": True,
                "trigger_confluence_count": confluence_count,
                "trigger_reject_reason": "none",
                "trigger_index": i,
                "trigger_low": low_i,
                "trigger_high": high_i,
                "fvg_low": np.nan,
                "fvg_high": np.nan,
                "no_chase_triggered": False,
                "missed_no_chase_reason": "",
                "latest_1m_close_used": ns_to_utc(close_ns),
                "latest_5m_close_used": latest_tf_close(market.tf_bars["5m"], close_ns),
            }

        choch = False
        if side == "long":
            choch = close_i > float(market.prev10_high[i]) and body_score >= 0.55
        else:
            choch = close_i < float(market.prev10_low[i]) and body_score >= 0.55
        if choch and strong_confluence:
            return {
                "entry_trigger_type": "1m_choch_bos_proxy",
                "trigger_timestamp": ns_to_utc(close_ns),
                "trigger_available_at": ns_to_utc(close_ns),
                "trigger_reference_candle_close": ns_to_utc(close_ns),
                "entry_model": "confirmation_market",
                "entry_price": close_i,
                "entry_zone_low": zone_low,
                "entry_zone_high": zone_high,
                "entry_quality_score": trigger_quality("1m_choch_bos_proxy", side, row, confluence_count, body_score),
                "entry_inside_approved_zone": True,
                "trigger_confluence_count": confluence_count,
                "trigger_reject_reason": "none",
                "trigger_index": i,
                "trigger_low": low_i,
                "trigger_high": high_i,
                "fvg_low": np.nan,
                "fvg_high": np.nan,
                "no_chase_triggered": False,
                "missed_no_chase_reason": "",
                "latest_1m_close_used": ns_to_utc(close_ns),
                "latest_5m_close_used": latest_tf_close(market.tf_bars["5m"], close_ns),
            }

        displacement = (
            strong_confluence
            and body_score >= 0.68
            and abs(close_i - open_i) >= max(0.35 * float(market.atr_1m[i]), 0.08 * atr_15m)
        )
        if displacement:
            return {
                "entry_trigger_type": "1m_displacement_candle",
                "trigger_timestamp": ns_to_utc(close_ns),
                "trigger_available_at": ns_to_utc(close_ns),
                "trigger_reference_candle_close": ns_to_utc(close_ns),
                "entry_model": "confirmation_market",
                "entry_price": close_i,
                "entry_zone_low": zone_low,
                "entry_zone_high": zone_high,
                "entry_quality_score": trigger_quality("1m_displacement_candle", side, row, confluence_count, body_score),
                "entry_inside_approved_zone": True,
                "trigger_confluence_count": confluence_count,
                "trigger_reject_reason": "none",
                "trigger_index": i,
                "trigger_low": low_i,
                "trigger_high": high_i,
                "fvg_low": np.nan,
                "fvg_high": np.nan,
                "no_chase_triggered": False,
                "missed_no_chase_reason": "",
                "latest_1m_close_used": ns_to_utc(close_ns),
                "latest_5m_close_used": latest_tf_close(market.tf_bars["5m"], close_ns),
            }

        retest_close_ok = close_i >= zone_mid if side == "long" else close_i <= zone_mid
        if retest_close_ok and body_score >= 0.45 and strong_confluence:
            trigger_type = "sr_flip_retest" if float(row["sr_zone_score"]) >= 0.45 else "approved_htf_zone_retest"
            entry_price = zone_high if side == "long" else zone_low
            return {
                "entry_trigger_type": trigger_type,
                "trigger_timestamp": ns_to_utc(close_ns),
                "trigger_available_at": ns_to_utc(close_ns),
                "trigger_reference_candle_close": ns_to_utc(close_ns),
                "entry_model": "limit_retest_edge",
                "entry_price": float(entry_price),
                "entry_zone_low": zone_low,
                "entry_zone_high": zone_high,
                "entry_quality_score": trigger_quality(trigger_type, side, row, confluence_count, body_score),
                "entry_inside_approved_zone": True,
                "trigger_confluence_count": confluence_count,
                "trigger_reject_reason": "none",
                "trigger_index": i,
                "trigger_low": low_i,
                "trigger_high": high_i,
                "fvg_low": np.nan,
                "fvg_high": np.nan,
                "no_chase_triggered": False,
                "missed_no_chase_reason": "",
                "latest_1m_close_used": ns_to_utc(close_ns),
                "latest_5m_close_used": latest_tf_close(market.tf_bars["5m"], close_ns),
            }

        if i >= 2:
            if side == "long" and market.low[i] > market.high[i - 2]:
                pending_fvg = {"low": float(market.high[i - 2]), "high": float(market.low[i]), "mid": float((market.high[i - 2] + market.low[i]) / 2.0)}
            elif side == "short" and market.high[i] < market.low[i - 2]:
                pending_fvg = {"low": float(market.high[i]), "high": float(market.low[i - 2]), "mid": float((market.high[i] + market.low[i - 2]) / 2.0)}

    if max_excursion > MAX_CHASE_ATR * atr_15m:
        return no_trigger_dict("price_moved_without_retest_inside_expiry", no_chase=True)
    return no_trigger_dict("no_approved_1m_trigger_inside_expiry_window")


def construct_stop(
    row: pd.Series,
    zone: dict[str, object] | None,
    market: MarketData,
    trigger: dict[str, object],
) -> dict[str, object]:
    if trigger["entry_model"] == "no_entry" or pd.isna(trigger["entry_price"]):
        return {
            "stop_price": np.nan,
            "stop_anchor_type": "none",
            "stop_anchor_price": np.nan,
            "stop_buffer": np.nan,
            "stop_distance_abs": np.nan,
            "stop_distance_pct": np.nan,
            "stop_distance_atr": np.nan,
            "thesis_invalidation_stop": False,
            "stop_valid": False,
            "stop_reject_reason": "no_entry_trigger",
        }
    if zone is None:
        return {
            "stop_price": np.nan,
            "stop_anchor_type": "none",
            "stop_anchor_price": np.nan,
            "stop_buffer": np.nan,
            "stop_distance_abs": np.nan,
            "stop_distance_pct": np.nan,
            "stop_distance_atr": np.nan,
            "thesis_invalidation_stop": False,
            "stop_valid": False,
            "stop_reject_reason": "no_approved_zone_anchor",
        }
    side = str(row["side"])
    entry = float(trigger["entry_price"])
    i = int(trigger["trigger_index"])
    decision_ns = utc_timestamp(row["decision_timestamp"]).value
    latest_15_pos = int(np.searchsorted(market.tf_bars["15m"]["close_time_ns"].to_numpy(dtype="int64"), decision_ns, side="right")) - 1
    atr_15m = float(market.tf_bars["15m"].iloc[max(latest_15_pos, 0)]["atr"]) if latest_15_pos >= 0 else max(entry * 0.002, 1e-9)
    start = max(0, i - 10)
    local_low = float(np.nanmin(market.low[start : i + 1]))
    local_high = float(np.nanmax(market.high[start : i + 1]))

    if side == "long":
        if trigger["entry_trigger_type"] == "1m_sweep_reclaim":
            anchor_type = "sweep_low"
            anchor = min(float(trigger["trigger_low"]), local_low)
        elif trigger["entry_model"] == "limit_fvg_mid" and pd.notna(trigger["fvg_low"]):
            anchor_type = "fvg_low"
            anchor = float(trigger["fvg_low"])
        elif str(row["trendline_interaction_type"]) in {"near_touch", "sweep", "rejection", "break_retest"}:
            anchor_type = "trendline_retest_invalidation_low"
            anchor = min(float(zone["zone_low"]), local_low)
        else:
            anchor_type = "approved_zone_low"
            anchor = float(zone["zone_low"])
        anchor = min(anchor, local_low if anchor > entry else anchor)
        buffer = max(entry * 0.0002, atr_15m * 0.06)
        stop = anchor - buffer
        distance = entry - stop
        ordering_ok = stop < entry
    else:
        if trigger["entry_trigger_type"] == "1m_sweep_reclaim":
            anchor_type = "sweep_high"
            anchor = max(float(trigger["trigger_high"]), local_high)
        elif trigger["entry_model"] == "limit_fvg_mid" and pd.notna(trigger["fvg_high"]):
            anchor_type = "fvg_high"
            anchor = float(trigger["fvg_high"])
        elif str(row["trendline_interaction_type"]) in {"near_touch", "sweep", "rejection", "break_retest"}:
            anchor_type = "trendline_retest_invalidation_high"
            anchor = max(float(zone["zone_high"]), local_high)
        else:
            anchor_type = "approved_zone_high"
            anchor = float(zone["zone_high"])
        anchor = max(anchor, local_high if anchor < entry else anchor)
        buffer = max(entry * 0.0002, atr_15m * 0.06)
        stop = anchor + buffer
        distance = stop - entry
        ordering_ok = stop > entry

    min_distance = max(entry * 0.0003, MIN_STOP_ATR * atr_15m)
    max_distance = MAX_STOP_ATR * atr_15m
    if not ordering_ok:
        valid = False
        reason = "stop_entry_ordering_invalid"
    elif distance <= min_distance:
        valid = False
        reason = "stop_inside_noise_or_spread"
    elif distance >= max_distance:
        valid = False
        reason = "stop_too_wide_rr_likely_broken"
    else:
        valid = True
        reason = "none"
    return {
        "stop_price": float(stop),
        "stop_anchor_type": anchor_type,
        "stop_anchor_price": float(anchor),
        "stop_buffer": float(buffer),
        "stop_distance_abs": float(distance),
        "stop_distance_pct": float(distance / entry) if entry else np.nan,
        "stop_distance_atr": float(distance / atr_15m) if atr_15m > 0 else np.nan,
        "thesis_invalidation_stop": bool(valid),
        "stop_valid": bool(valid),
        "stop_reject_reason": reason,
    }


def target_row(target_lookup: dict[str, dict[str, object]], target_id: object) -> dict[str, object] | None:
    if pd.isna(target_id) or not str(target_id):
        return None
    return target_lookup.get(str(target_id))


def rr_for_target(side: str, entry: float, risk_abs: float, target: dict[str, object] | None, entry_model: str) -> tuple[float, float]:
    if target is None or risk_abs <= 0 or pd.isna(target.get("target_price", np.nan)):
        return np.nan, np.nan
    target_price = float(target["target_price"])
    move = directional_move(side, target_price, entry)
    gross = move / risk_abs if risk_abs > 0 else np.nan
    entry_cost_bps = 7.0 if entry_model == "confirmation_market" else 2.5
    exit_cost_bps = 2.5
    cost_abs = (entry_cost_bps + exit_cost_bps) / 10000.0 * entry
    net = (move - cost_abs) / risk_abs if risk_abs > 0 else np.nan
    return float(gross), float(net)


def combine_targets_and_rr(
    row: pd.Series,
    target_summary: pd.Series | None,
    target_lookup: dict[str, dict[str, object]],
    trigger: dict[str, object],
    stop: dict[str, object],
) -> dict[str, object]:
    empty = {
        "tp1_target_id": "",
        "core_target_id": "",
        "runner_target_id": "",
        "tp1_price": np.nan,
        "core_target_price": np.nan,
        "runner_target_price": np.nan,
        "tp1_source": "none",
        "core_target_source": "none",
        "runner_target_source": "none",
        "planned_rr_tp1_gross": np.nan,
        "planned_rr_core_gross": np.nan,
        "planned_rr_runner_gross": np.nan,
        "planned_rr_tp1_net": np.nan,
        "planned_rr_core_net": np.nan,
        "planned_rr_runner_net": np.nan,
        "core_rr_ge_3r": False,
        "runner_rr_ge_7r": False,
        "fixed_r_primary_target": False,
        "structural_target_used": False,
        "target_pool_built_at": row["decision_timestamp"],
        "target_latest_source_close_used": pd.NaT,
        "target_rr_reject_reason": "no_entry_or_stop",
    }
    if target_summary is None or trigger["entry_model"] == "no_entry" or not bool(stop["stop_valid"]):
        return empty
    tp1 = target_row(target_lookup, target_summary.get("tp1_candidate_target_id", ""))
    core = target_row(target_lookup, target_summary.get("core_candidate_target_id", ""))
    runner = target_row(target_lookup, target_summary.get("runner_candidate_target_id", ""))
    entry = float(trigger["entry_price"])
    risk_abs = float(stop["stop_distance_abs"])
    tp1_gross, tp1_net = rr_for_target(str(row["side"]), entry, risk_abs, tp1, str(trigger["entry_model"]))
    core_gross, core_net = rr_for_target(str(row["side"]), entry, risk_abs, core, str(trigger["entry_model"]))
    runner_gross, runner_net = rr_for_target(str(row["side"]), entry, risk_abs, runner, str(trigger["entry_model"]))
    fixed_primary = core is not None and str(core["target_source"]) == "fixed_R_placeholder"
    structural_core = core is not None and str(core["target_source"]) not in {"fixed_R_placeholder", "none"}
    structural_runner = runner is not None and str(runner["target_source"]) not in {"fixed_R_placeholder", "none"}
    core_distance_atr = float(core.get("distance_atr", np.nan)) if core is not None else np.nan
    runner_distance_atr = float(runner.get("distance_atr", np.nan)) if runner is not None else np.nan
    core_is_stale_far = (
        structural_core
        and str(core.get("freshness_state", "")) == "stale"
        and pd.notna(core_distance_atr)
        and core_distance_atr > MAX_STALE_CORE_TARGET_DISTANCE_ATR
    )
    core_is_too_far = structural_core and pd.notna(core_distance_atr) and core_distance_atr > MAX_CORE_TARGET_DISTANCE_ATR
    structural_core_usable = structural_core and not fixed_primary and not core_is_stale_far and not core_is_too_far
    structural_runner_usable = (
        structural_runner
        and pd.notna(runner_distance_atr)
        and runner_distance_atr <= MAX_RUNNER_TARGET_DISTANCE_ATR
    )
    latest_targets = [
        target["latest_source_candle_close_used"]
        for target in [tp1, core, runner]
        if target is not None and pd.notna(target.get("latest_source_candle_close_used", pd.NaT))
    ]
    latest_source = max(latest_targets) if latest_targets else pd.NaT
    if not structural_core:
        reason = "no_structural_core_target"
    elif fixed_primary:
        reason = "fixed_r_primary_target"
    elif core_is_stale_far:
        reason = "stale_core_target_too_far_for_candidate_stage"
    elif core_is_too_far:
        reason = "core_target_too_far_for_candidate_stage"
    elif pd.isna(core_net) or core_net < MIN_CORE_RR_NET:
        reason = "planned_core_rr_net_below_3r"
    else:
        reason = "none"
    return {
        "tp1_target_id": tp1["target_id"] if tp1 else "",
        "core_target_id": core["target_id"] if core else "",
        "runner_target_id": runner["target_id"] if runner else "",
        "tp1_price": tp1["target_price"] if tp1 else np.nan,
        "core_target_price": core["target_price"] if core else np.nan,
        "runner_target_price": runner["target_price"] if runner else np.nan,
        "tp1_source": tp1["target_source"] if tp1 else "none",
        "core_target_source": core["target_source"] if core else "none",
        "runner_target_source": runner["target_source"] if runner else "none",
        "planned_rr_tp1_gross": tp1_gross,
        "planned_rr_core_gross": core_gross,
        "planned_rr_runner_gross": runner_gross,
        "planned_rr_tp1_net": tp1_net,
        "planned_rr_core_net": core_net,
        "planned_rr_runner_net": runner_net,
        "core_rr_ge_3r": bool(pd.notna(core_net) and core_net >= MIN_CORE_RR_NET),
        "runner_rr_ge_7r": bool(pd.notna(runner_net) and runner_net >= MIN_RUNNER_RR_NET and structural_runner_usable),
        "fixed_r_primary_target": bool(fixed_primary),
        "structural_target_used": bool(structural_core_usable),
        "target_pool_built_at": row["decision_timestamp"],
        "target_latest_source_close_used": latest_source,
        "target_rr_reject_reason": reason,
    }


def row_with_defaults(
    symbol: str,
    decision_timestamp: pd.Timestamp,
    side: str,
    arbitration: dict[str, object],
    candidate_status: str,
    status_reason: str,
) -> dict[str, object]:
    return {
        "candidate_id": stable_id(symbol, decision_timestamp, side, candidate_status, status_reason),
        "symbol": symbol,
        "decision_timestamp": decision_timestamp,
        "side": side,
        "reference_price": np.nan,
        "thesis_mode": "reject",
        "thesis_score": np.nan,
        "thesis_confidence_bucket": "reject",
        "thesis_side_permission": "none",
        "side_arbitration_state": arbitration["side_arbitration_state"],
        "side_arbitration_reason": arbitration["side_arbitration_reason"],
        "opposing_side_score": arbitration["opposing_side_score"],
        "selected_side_score": arbitration["selected_side_score"],
        "side_score_gap": arbitration["side_score_gap"],
        "entry_trigger_type": "none",
        "trigger_timestamp": pd.NaT,
        "trigger_available_at": pd.NaT,
        "trigger_reference_candle_close": pd.NaT,
        "entry_model": "no_entry",
        "entry_price": np.nan,
        "entry_zone_low": np.nan,
        "entry_zone_high": np.nan,
        "entry_quality_score": 0.0,
        "entry_inside_approved_zone": False,
        "trigger_confluence_count": 0,
        "trigger_reject_reason": status_reason,
        "stop_price": np.nan,
        "stop_anchor_type": "none",
        "stop_anchor_price": np.nan,
        "stop_buffer": np.nan,
        "stop_distance_abs": np.nan,
        "stop_distance_pct": np.nan,
        "stop_distance_atr": np.nan,
        "thesis_invalidation_stop": False,
        "stop_valid": False,
        "stop_reject_reason": status_reason,
        "tp1_target_id": "",
        "core_target_id": "",
        "runner_target_id": "",
        "tp1_price": np.nan,
        "core_target_price": np.nan,
        "runner_target_price": np.nan,
        "tp1_source": "none",
        "core_target_source": "none",
        "runner_target_source": "none",
        "planned_rr_tp1_gross": np.nan,
        "planned_rr_core_gross": np.nan,
        "planned_rr_runner_gross": np.nan,
        "planned_rr_tp1_net": np.nan,
        "planned_rr_core_net": np.nan,
        "planned_rr_runner_net": np.nan,
        "core_rr_ge_3r": False,
        "runner_rr_ge_7r": False,
        "fixed_r_primary_target": False,
        "structural_target_used": False,
        "order_expiry_minutes": TRIGGER_EXPIRY_MINUTES,
        "no_chase_triggered": False,
        "rr_compression_cancel": False,
        "missed_no_chase_reason": "",
        "candidate_status": candidate_status,
        "candidate_reject_reason": status_reason,
        "latest_1m_close_used": pd.NaT,
        "latest_5m_close_used": pd.NaT,
        "latest_15m_close_used": pd.NaT,
        "latest_1h_close_used": pd.NaT,
        "latest_4h_close_used": pd.NaT,
        "trigger_window_end": decision_timestamp + pd.Timedelta(minutes=TRIGGER_EXPIRY_MINUTES),
        "target_pool_built_at": decision_timestamp,
        "target_latest_source_close_used": pd.NaT,
        "lookahead_pass": True,
        "lookahead_violation_reason": "",
    }


def build_candidate_row(
    row: pd.Series,
    arbitration: dict[str, object],
    zone: dict[str, object] | None,
    market: MarketData,
    target_summary: pd.Series | None,
    target_lookup: dict[str, dict[str, object]],
    order_expiry_minutes: int,
) -> dict[str, object]:
    symbol = str(row["symbol"])
    decision_timestamp = utc_timestamp(row["decision_timestamp"])
    side = str(row["side"])
    trigger = find_1m_trigger(row, zone, market, order_expiry_minutes)
    stop = construct_stop(row, zone, market, trigger)
    targets = combine_targets_and_rr(row, target_summary, target_lookup, trigger, stop)

    if trigger["entry_model"] == "no_entry":
        status = "rejected_no_chase" if trigger["no_chase_triggered"] else "rejected_no_1m_trigger"
        reason = str(trigger["trigger_reject_reason"])
    elif float(trigger["entry_quality_score"]) < MIN_ACCEPTED_ENTRY_QUALITY:
        status = "rejected_no_1m_trigger"
        reason = f"entry_quality_below_{MIN_ACCEPTED_ENTRY_QUALITY:.2f}"
    elif not bool(stop["stop_valid"]):
        status = "rejected_invalid_stop"
        reason = str(stop["stop_reject_reason"])
    elif not bool(targets["structural_target_used"]):
        status = "rejected_no_structural_target"
        reason = str(targets["target_rr_reject_reason"])
    elif bool(targets["fixed_r_primary_target"]):
        status = "rejected_no_structural_target"
        reason = "fixed_r_primary_target"
    elif not bool(targets["core_rr_ge_3r"]):
        status = "rejected_rr_below_dna"
        reason = str(targets["target_rr_reject_reason"])
    else:
        status = "accepted"
        reason = "none"

    rr_compression_cancel = status == "rejected_rr_below_dna"
    trigger_end = decision_timestamp + pd.Timedelta(minutes=order_expiry_minutes)
    trigger_available = trigger["trigger_available_at"]
    latest_1m = trigger["latest_1m_close_used"]
    latest_5m = trigger["latest_5m_close_used"]
    decision_ns = decision_timestamp.value
    latest_15m = latest_tf_close(market.tf_bars["15m"], decision_ns)
    latest_1h = latest_tf_close(market.tf_bars["1h"], decision_ns)
    latest_4h = latest_tf_close(market.tf_bars["4h"], decision_ns)
    target_built_at = targets["target_pool_built_at"]
    target_latest = targets["target_latest_source_close_used"]
    time_checks = [
        pd.isna(latest_1m) or latest_1m <= trigger_available or pd.isna(trigger_available),
        pd.isna(latest_5m) or latest_5m <= trigger_available or pd.isna(trigger_available),
        pd.isna(latest_15m) or latest_15m <= decision_timestamp,
        pd.isna(latest_1h) or latest_1h <= decision_timestamp,
        pd.isna(latest_4h) or latest_4h <= decision_timestamp,
        pd.isna(trigger_available) or (decision_timestamp < trigger_available <= trigger_end),
        pd.isna(target_built_at) or target_built_at <= decision_timestamp,
        pd.isna(target_latest) or target_latest <= decision_timestamp,
        bool(row["lookahead_pass"]),
    ]
    lookahead_pass = all(bool(value) for value in time_checks)
    if not lookahead_pass:
        status = "rejected_lookahead"
        reason = "source_time_after_decision_or_trigger_window"
    if status not in STATUS_VALUES:
        status = "rejected_other"

    return {
        "candidate_id": stable_id(symbol, decision_timestamp, side, trigger["entry_trigger_type"], trigger_available),
        "symbol": symbol,
        "decision_timestamp": decision_timestamp,
        "side": side,
        "reference_price": float(row["reference_price"]),
        "thesis_mode": str(row["thesis_mode"]),
        "thesis_score": float(row["thesis_score"]),
        "thesis_confidence_bucket": str(row["thesis_confidence_bucket"]),
        "thesis_side_permission": str(row["thesis_side_permission"]),
        "side_arbitration_state": arbitration["side_arbitration_state"],
        "side_arbitration_reason": arbitration["side_arbitration_reason"],
        "opposing_side_score": arbitration["opposing_side_score"],
        "selected_side_score": arbitration["selected_side_score"],
        "side_score_gap": arbitration["side_score_gap"],
        **{key: trigger[key] for key in [
            "entry_trigger_type",
            "trigger_timestamp",
            "trigger_available_at",
            "trigger_reference_candle_close",
            "entry_model",
            "entry_price",
            "entry_zone_low",
            "entry_zone_high",
            "entry_quality_score",
            "entry_inside_approved_zone",
            "trigger_confluence_count",
            "trigger_reject_reason",
        ]},
        **stop,
        **{key: targets[key] for key in [
            "tp1_target_id",
            "core_target_id",
            "runner_target_id",
            "tp1_price",
            "core_target_price",
            "runner_target_price",
            "tp1_source",
            "core_target_source",
            "runner_target_source",
            "planned_rr_tp1_gross",
            "planned_rr_core_gross",
            "planned_rr_runner_gross",
            "planned_rr_tp1_net",
            "planned_rr_core_net",
            "planned_rr_runner_net",
            "core_rr_ge_3r",
            "runner_rr_ge_7r",
            "fixed_r_primary_target",
            "structural_target_used",
        ]},
        "order_expiry_minutes": int(order_expiry_minutes),
        "no_chase_triggered": bool(trigger["no_chase_triggered"]),
        "rr_compression_cancel": bool(rr_compression_cancel),
        "missed_no_chase_reason": str(trigger["missed_no_chase_reason"]),
        "candidate_status": status,
        "candidate_reject_reason": reason,
        "latest_1m_close_used": latest_1m,
        "latest_5m_close_used": latest_5m,
        "latest_15m_close_used": latest_15m,
        "latest_1h_close_used": latest_1h,
        "latest_4h_close_used": latest_4h,
        "trigger_window_end": trigger_end,
        "target_pool_built_at": target_built_at,
        "target_latest_source_close_used": target_latest,
        "lookahead_pass": bool(lookahead_pass),
        "lookahead_violation_reason": "" if lookahead_pass else "source_time_after_decision_or_trigger_window",
    }


def load_thesis(symbols: list[str], market_by_symbol: dict[str, MarketData]) -> pd.DataFrame:
    thesis = pd.read_parquet(THESIS_PARQUET)
    thesis = thesis[thesis["symbol"].isin(symbols)].copy()
    thesis["decision_timestamp"] = pd.to_datetime(thesis["decision_timestamp"], utc=True)
    thesis = thesis[thesis["thesis_valid"].astype(bool)].copy()
    atr_records = []
    for symbol, market in market_by_symbol.items():
        bars = market.tf_bars["15m"][["close_time", "atr"]].rename(columns={"close_time": "decision_timestamp", "atr": "atr_15m"})
        bars["symbol"] = symbol
        atr_records.append(bars)
    atr_df = pd.concat(atr_records, ignore_index=True)
    atr_df["decision_timestamp"] = pd.to_datetime(atr_df["decision_timestamp"], utc=True)
    thesis = thesis.merge(atr_df, on=["symbol", "decision_timestamp"], how="left", validate="many_to_one")
    return thesis.sort_values(["symbol", "decision_timestamp", "side"]).reset_index(drop=True)


def build_candidates(
    thesis: pd.DataFrame,
    target_summary: pd.DataFrame,
    zone_map: dict[str, dict[str, object]],
    target_lookup: dict[str, dict[str, object]],
    market_by_symbol: dict[str, MarketData],
    order_expiry_minutes: int,
) -> pd.DataFrame:
    target_summary_index = target_summary.set_index(["symbol", "decision_timestamp", "side"])
    rows: list[dict[str, object]] = []
    groups = thesis.groupby(["symbol", "decision_timestamp"], sort=True)
    total = len(groups)
    for group_number, ((symbol, decision_timestamp), group) in enumerate(groups, 1):
        if group_number == 1 or group_number % 25000 == 0:
            print(f"  trade_candidate groups={group_number}/{total}", flush=True)
        market = market_by_symbol[str(symbol)]
        arbitration = arbitrate_side(group, market)
        selected = arbitration["selected_row"]
        if selected is None:
            rows.append(
                row_with_defaults(
                    str(symbol),
                    utc_timestamp(decision_timestamp),
                    "none",
                    arbitration,
                    "rejected_side_conflict",
                    str(arbitration["side_arbitration_reason"]),
                )
            )
            continue
        selected = pd.Series(selected)
        zone = zone_map.get(str(selected.get("htf_zone_object_id", "")))
        try:
            summary_row = target_summary_index.loc[(str(symbol), utc_timestamp(decision_timestamp), str(selected["side"]))]
        except KeyError:
            summary_row = None
        rows.append(
            build_candidate_row(
                selected,
                arbitration,
                zone,
                market,
                summary_row,
                target_lookup,
                order_expiry_minutes,
            )
        )
    return pd.DataFrame(rows)


def build_audit(candidates: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "candidate_id",
        "symbol",
        "decision_timestamp",
        "side",
        "candidate_status",
        "latest_1m_close_used",
        "latest_5m_close_used",
        "latest_15m_close_used",
        "latest_1h_close_used",
        "latest_4h_close_used",
        "trigger_available_at",
        "trigger_window_end",
        "target_pool_built_at",
        "target_latest_source_close_used",
        "lookahead_pass",
        "lookahead_violation_reason",
    ]
    audit = candidates[columns].copy()
    for column in [
        "decision_timestamp",
        "latest_1m_close_used",
        "latest_5m_close_used",
        "latest_15m_close_used",
        "latest_1h_close_used",
        "latest_4h_close_used",
        "trigger_available_at",
        "trigger_window_end",
        "target_pool_built_at",
        "target_latest_source_close_used",
    ]:
        audit[column] = pd.to_datetime(audit[column], utc=True, errors="coerce")
    trigger_exists = audit["trigger_available_at"].notna()
    lookahead = (
        (audit["latest_15m_close_used"].isna() | (audit["latest_15m_close_used"] <= audit["decision_timestamp"]))
        & (audit["latest_1h_close_used"].isna() | (audit["latest_1h_close_used"] <= audit["decision_timestamp"]))
        & (audit["latest_4h_close_used"].isna() | (audit["latest_4h_close_used"] <= audit["decision_timestamp"]))
        & (audit["target_pool_built_at"].isna() | (audit["target_pool_built_at"] <= audit["decision_timestamp"]))
        & (audit["target_latest_source_close_used"].isna() | (audit["target_latest_source_close_used"] <= audit["decision_timestamp"]))
        & (
            ~trigger_exists
            | (
                (audit["trigger_available_at"] > audit["decision_timestamp"])
                & (audit["trigger_available_at"] <= audit["trigger_window_end"])
                & (audit["latest_1m_close_used"].isna() | (audit["latest_1m_close_used"] <= audit["trigger_available_at"]))
                & (audit["latest_5m_close_used"].isna() | (audit["latest_5m_close_used"] <= audit["trigger_available_at"]))
            )
        )
    )
    audit["lookahead_pass"] = lookahead.astype(bool)
    audit.loc[audit["lookahead_pass"], "lookahead_violation_reason"] = ""
    audit.loc[~audit["lookahead_pass"], "lookahead_violation_reason"] = "source_time_after_decision_or_trigger_window"
    return audit


def write_report(candidates: pd.DataFrame, audit: pd.DataFrame, symbols: list[str], order_expiry_minutes: int) -> None:
    status_counts = candidates["candidate_status"].value_counts().reset_index()
    status_counts.columns = ["candidate_status", "rows"]
    accepted = int(candidates["candidate_status"].eq("accepted").sum())
    accepted_pct = accepted / len(candidates) * 100 if len(candidates) else 0.0
    arb_counts = candidates["side_arbitration_state"].value_counts().reset_index()
    arb_counts.columns = ["side_arbitration_state", "rows"]
    trigger_counts = candidates["entry_trigger_type"].value_counts().reset_index()
    trigger_counts.columns = ["entry_trigger_type", "rows"]
    model_counts = candidates["entry_model"].value_counts().reset_index()
    model_counts.columns = ["entry_model", "rows"]
    stop_counts = candidates["stop_anchor_type"].value_counts().reset_index()
    stop_counts.columns = ["stop_anchor_type", "rows"]
    reject_reason_counts = candidates.loc[
        candidates["candidate_status"].ne("accepted"), "candidate_reject_reason"
    ].value_counts().head(20).reset_index()
    reject_reason_counts.columns = ["candidate_reject_reason", "rows"]
    accepted_rows = candidates[candidates["candidate_status"].eq("accepted")].copy()
    accepted_mode_counts = accepted_rows["thesis_mode"].value_counts().reset_index()
    accepted_mode_counts.columns = ["thesis_mode", "accepted_rows"]
    if not accepted_rows.empty:
        accepted_by_symbol_side = accepted_rows.groupby(["symbol", "side"]).size().reset_index(name="accepted_rows")
    else:
        accepted_by_symbol_side = pd.DataFrame(columns=["symbol", "side", "accepted_rows"])
    accepted_variant_rows = []
    if not accepted_rows.empty:
        accepted_variant_rows = [
            {"variant_family": "reversal", "accepted_rows": int(accepted_rows["thesis_mode"].isin(REVERSAL_MODES).sum())},
            {"variant_family": "continuation", "accepted_rows": int(accepted_rows["thesis_mode"].isin(CONTINUATION_MODES).sum())},
        ]
    fixed_pct = float(candidates["fixed_r_primary_target"].mean() * 100) if len(candidates) else 0.0
    core_ge_pct = float(candidates["core_rr_ge_3r"].mean() * 100) if len(candidates) else 0.0
    runner_ge_pct = float(candidates["runner_rr_ge_7r"].mean() * 100) if len(candidates) else 0.0
    violations = int((~audit["lookahead_pass"]).sum())
    rr = candidates["planned_rr_core_net"].dropna()
    rr_stats = []
    if not rr.empty:
        rr_stats = [
            {
                "metric": "planned_rr_core_net",
                "p25": round(float(rr.quantile(0.25)), 3),
                "median": round(float(rr.quantile(0.50)), 3),
                "p75": round(float(rr.quantile(0.75)), 3),
                "p90": round(float(rr.quantile(0.90)), 3),
                "p99": round(float(rr.quantile(0.99)), 3),
            }
        ]
    accepted_rr = accepted_rows["planned_rr_core_net"].dropna()
    accepted_rr_stats = []
    if not accepted_rr.empty:
        accepted_rr_stats = [
            {
                "metric": "accepted_planned_rr_core_net",
                "p25": round(float(accepted_rr.quantile(0.25)), 3),
                "median": round(float(accepted_rr.quantile(0.50)), 3),
                "p75": round(float(accepted_rr.quantile(0.75)), 3),
                "p90": round(float(accepted_rr.quantile(0.90)), 3),
                "p99": round(float(accepted_rr.quantile(0.99)), 3),
            }
        ]
    spot = []
    for symbol in symbols:
        for side in ["long", "short"]:
            sample = accepted_rows[accepted_rows["symbol"].eq(symbol) & accepted_rows["side"].eq(side)].copy()
            if sample.empty:
                sample = candidates[candidates["symbol"].eq(symbol) & candidates["side"].eq(side)].head(1).copy()
            else:
                median_rr = float(sample["planned_rr_core_net"].median())
                sample["rr_median_distance"] = (sample["planned_rr_core_net"] - median_rr).abs()
                sample = sample.sort_values(["rr_median_distance", "decision_timestamp"]).head(1)
            for row in sample.itertuples(index=False):
                spot.append(
                    {
                        "symbol": row.symbol,
                        "decision_timestamp": row.decision_timestamp,
                        "side": row.side,
                        "status": row.candidate_status,
                        "trigger": row.entry_trigger_type,
                        "entry": round(float(row.entry_price), 6) if pd.notna(row.entry_price) else "",
                        "stop": round(float(row.stop_price), 6) if pd.notna(row.stop_price) else "",
                        "core_rr_net": round(float(row.planned_rr_core_net), 3) if pd.notna(row.planned_rr_core_net) else "",
                        "core_target": row.core_target_source,
                        "structure_note": (
                            f"{row.entry_trigger_type} in approved zone; "
                            f"stop anchored by {row.stop_anchor_type}; "
                            f"core target from {row.core_target_source}; no execution outcome used"
                        ),
                    }
                )
    if not spot:
        for row in candidates.head(4).itertuples(index=False):
            spot.append(
                {
                    "symbol": row.symbol,
                    "decision_timestamp": row.decision_timestamp,
                    "side": row.side,
                    "status": row.candidate_status,
                    "trigger": row.entry_trigger_type,
                    "entry": round(float(row.entry_price), 6) if pd.notna(row.entry_price) else "",
                    "stop": round(float(row.stop_price), 6) if pd.notna(row.stop_price) else "",
                    "core_rr_net": round(float(row.planned_rr_core_net), 3) if pd.notna(row.planned_rr_core_net) else "",
                    "core_target": row.core_target_source,
                    "structure_note": (
                        f"{row.entry_trigger_type} in approved zone; "
                        f"stop anchored by {row.stop_anchor_type}; "
                        f"core target from {row.core_target_source}; no execution outcome used"
                    ),
                }
            )

    lines = [
        "# Craig v1.2 Trade Candidate Build Report",
        "",
        "Generated by `scripts/build_craig_v1_2_trade_candidates.py`.",
        "",
        "## Verdict",
        "",
        "- Trade candidates were built from `thesis_valid=true` rows only.",
        "- Long/short conflicts are arbitrated before any 1m trigger search.",
        "- A candidate is accepted only after a strict 1m trigger, thesis-invalidation stop, structural target, and planned core RR net >= 3R.",
        f"- Entry gate constants: trigger confluence >= {MIN_TRIGGER_CONFLUENCE}, entry quality >= {MIN_ACCEPTED_ENTRY_QUALITY:.2f}, stop distance between {MIN_STOP_ATR:.2f} and {MAX_STOP_ATR:.2f} ATR.",
        f"- Core targets are capped at {MAX_CORE_TARGET_DISTANCE_ATR:.1f} ATR, or {MAX_STALE_CORE_TARGET_DISTANCE_ATR:.1f} ATR when stale, to avoid remote-target RR outliers at this construction stage.",
        "- This stage does not simulate fills, stop hits, target hits, partial exits, runner outcome, PnL, or parameter optimization.",
        f"- Lookahead violations: {violations}.",
        "",
        "## Dataset And Grain",
        "",
        f"- Symbols: {', '.join(symbols)}",
        f"- Trade candidate rows: {len(candidates)}",
        f"- Accepted candidates: {accepted} ({accepted_pct:.3f}%)",
        f"- Trigger expiry window: {order_expiry_minutes} minutes.",
        "",
        "## Candidate Status Distribution",
        "",
        *markdown_table(status_counts.to_dict("records"), ["candidate_status", "rows"]),
        "",
        "## Side Arbitration Distribution",
        "",
        *markdown_table(arb_counts.to_dict("records"), ["side_arbitration_state", "rows"]),
        "",
        "## Entry Trigger Distribution",
        "",
        *markdown_table(trigger_counts.to_dict("records"), ["entry_trigger_type", "rows"]),
        "",
        "## Entry Model Distribution",
        "",
        *markdown_table(model_counts.to_dict("records"), ["entry_model", "rows"]),
        "",
        "## Accepted Thesis Mode Distribution",
        "",
        *markdown_table(accepted_mode_counts.to_dict("records"), ["thesis_mode", "accepted_rows"]),
        "",
        "## Accepted R/C Family Split",
        "",
        *markdown_table(accepted_variant_rows, ["variant_family", "accepted_rows"]),
        "",
        "## Accepted Symbol And Side Distribution",
        "",
        *markdown_table(accepted_by_symbol_side.to_dict("records"), ["symbol", "side", "accepted_rows"]),
        "",
        "## Stop Anchor Distribution",
        "",
        *markdown_table(stop_counts.to_dict("records"), ["stop_anchor_type", "rows"]),
        "",
        "## Reject Reason Distribution",
        "",
        *markdown_table(reject_reason_counts.to_dict("records"), ["candidate_reject_reason", "rows"]),
        "",
        "## Planned Core RR Net Distribution",
        "",
        *markdown_table(rr_stats, ["metric", "p25", "median", "p75", "p90", "p99"]),
        "",
        "## Accepted Planned Core RR Net Distribution",
        "",
        *markdown_table(accepted_rr_stats, ["metric", "p25", "median", "p75", "p90", "p99"]),
        "",
        "## DNA Target Checks",
        "",
        f"- core_rr_ge_3r row share: {core_ge_pct:.3f}%",
        f"- runner_rr_ge_7r row share: {runner_ge_pct:.3f}%",
        f"- fixed_r_primary_target row share: {fixed_pct:.6f}%",
        "- `fixed_r_primary_target=true` rows are never accepted.",
        "",
        "## Spot Checks",
        "",
        *markdown_table(
            spot,
            [
                "symbol",
                "decision_timestamp",
                "side",
                "status",
                "trigger",
                "entry",
                "stop",
                "core_rr_net",
                "core_target",
                "structure_note",
            ],
        ),
        "",
        "## No-Lookahead Controls",
        "",
        "- 1m trigger search is restricted to the predefined expiry window after `decision_timestamp`.",
        "- The first deterministic qualifying trigger is used; the script does not search for the best future fill.",
        "- Thesis, HTF zone, BTC context, and target pool source closes remain at or before `decision_timestamp`.",
        "- Trigger-level 1m/5m closes must be at or before `trigger_available_at`.",
        "- The script does not read realized outcome, gold label, Craig action, result R, fill state, stop hit, target hit, or PnL.",
        "",
        "## Output Paths",
        "",
        f"- Trade candidates: `{rel(OUT_CANDIDATES)}`",
        f"- Audit CSV: `{rel(OUT_AUDIT)}`",
        "",
        "## Next Step Recommendation",
        "",
        "Build the event-driven execution simulator next. It should consume only accepted candidates, replay 1m candles from `trigger_available_at` forward, apply deterministic order-fill rules, conservative same-candle ordering, stop/TP/core/runner state transitions, fee/slippage costs, and write a separate execution audit without changing thesis or entry construction logic.",
    ]
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=HEADLINE_SYMBOLS)
    parser.add_argument("--expiry-minutes", type=int, default=TRIGGER_EXPIRY_MINUTES)
    args = parser.parse_args()
    symbols = [symbol.upper() for symbol in args.symbols]

    print("load market data", flush=True)
    market_by_symbol = {symbol: load_market_data(symbol) for symbol in symbols}
    print("load thesis snapshots", flush=True)
    thesis = load_thesis(symbols, market_by_symbol)
    print(f"valid thesis rows={len(thesis)}", flush=True)
    print("load target summary", flush=True)
    target_summary = load_target_summary(symbols)
    print("load target lookup", flush=True)
    target_lookup = load_target_lookup()
    print("load HTF zone map", flush=True)
    zone_map = load_zone_map(symbols)
    print("schema reference: trendlines and BTC context", flush=True)
    _ = pd.read_parquet(TRENDLINE_ZONES_PARQUET, columns=["object_id", "available_at"]).head(1)
    _ = pd.read_parquet(BTC_CONTEXT_PARQUET, columns=["decision_timestamp", "lookahead_pass"]).head(1)

    print("build trade candidates", flush=True)
    candidates = build_candidates(thesis, target_summary, zone_map, target_lookup, market_by_symbol, args.expiry_minutes)
    audit = build_audit(candidates)
    if not audit["lookahead_pass"].all():
        failures = int((~audit["lookahead_pass"]).sum())
        raise RuntimeError(f"Trade candidate lookahead audit failed for {failures} rows")

    OUT_CANDIDATES.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_parquet(OUT_CANDIDATES, index=False)
    audit.to_csv(OUT_AUDIT, index=False, encoding="utf-8-sig")
    write_report(candidates, audit, symbols, args.expiry_minutes)
    print(f"trade_candidates={OUT_CANDIDATES} rows={len(candidates)}")
    print(f"audit={OUT_AUDIT} rows={len(audit)} lookahead_pass={int(audit['lookahead_pass'].sum())}/{len(audit)}")
    print(f"report={OUT_REPORT}")


if __name__ == "__main__":
    main()
