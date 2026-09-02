#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from build_craig_v1_2_trade_candidates import (
    HEADLINE_SYMBOLS,
    HTF_ZONES_PARQUET,
    PROCESSED_ROOT,
    ROOT,
    TARGET_SUMMARY_PARQUET,
    THESIS_PARQUET,
    compute_atr,
    markdown_table,
    stable_id,
    utc_timestamp,
)


BTC_CONTEXT_PARQUET = ROOT / "outputs/craig_v1_2_btc_context_snapshots.parquet"
SNIPER_CANDIDATES_PARQUET = ROOT / "outputs/craig_v1_2_sniper_trade_candidates.parquet"

OUT_SCENARIOS = ROOT / "outputs/craig_v1_2_scenario_thesis.parquet"
OUT_AUDIT = ROOT / "outputs/craig_v1_2_scenario_thesis_audit.csv"
OUT_REPORT = ROOT / "outputs/craig_v1_2_scenario_thesis_report.md"

MAX_SCENARIOS_PER_SYMBOL_DAY = 4
MIN_SCENARIO_PRIORITY = 1.23
MIN_SCENARIO_ACTIVATION_QUALITY = 0.99
MAX_ACTIVATION_DISTANCE_ATR = 1.0
ACTIVE_DISTANCE_ATR = 0.25
APPROACHING_DISTANCE_ATR = 1.0
STRONG_TRENDLINE_SCORE_THRESHOLD = 0.75
TRENDLINE_ACTIVE_DISTANCE_ATR = 0.15
MIN_TRENDLINE_CONTEXT_CONDITIONS = 2

PRE_REFINEMENT_SCENARIO_ROWS = 5796
PRE_REFINEMENT_SNIPER_HEADLINE_ROWS = 2086
PRE_REFINEMENT_HTF_TRENDLINE_CONTEXT_PCT = 99.948
PRE_REFINEMENT_PRIMARY_SOURCE_COUNTS = {
    "day_high_low": 1741,
    "15m_fvg": 1684,
    "1h_fvg": 1123,
    "4h_fvg": 539,
    "previous_day_high_low": 275,
    "liquidity_pool": 170,
    "15m_swing": 147,
    "4h_swing": 61,
    "1h_swing": 55,
    "1h_sr_zone": 1,
}

SCENARIO_TYPES = {
    "htf_trendline_support_hold",
    "htf_trendline_resistance_reject",
    "htf_trendline_breakdown",
    "htf_trendline_breakout",
    "htf_trendline_fakeout_reclaim",
    "bearish_retrace_to_15m_fvg_mid",
    "bullish_retrace_to_15m_fvg_mid",
    "sr_flip_retest",
    "liquidity_sweep_reversal",
    "continuation_pullback",
}


def find_symbol_parquet(symbol: str) -> Path:
    candidates = sorted((PROCESSED_ROOT / symbol / "1m").glob(f"{symbol}_1m_*.parquet"))
    if not candidates:
        raise FileNotFoundError(f"No normalized continuous parquet found for {symbol}")
    return candidates[-1]


def load_15m_atr(symbols: list[str]) -> pd.DataFrame:
    frames = []
    for symbol in symbols:
        df = pd.read_parquet(find_symbol_parquet(symbol), columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        grouped = df.set_index("timestamp").sort_index().resample("15T", label="left", closed="left")
        bars = grouped.agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            source_1m_count=("close", "count"),
        )
        bars = bars[bars["source_1m_count"] == 15].dropna(subset=["open", "high", "low", "close"]).copy()
        bars["decision_timestamp"] = bars.index + pd.Timedelta(minutes=15)
        bars["atr_15m"] = compute_atr(bars)
        bars["symbol"] = symbol
        frames.append(bars.reset_index(drop=True)[["symbol", "decision_timestamp", "atr_15m"]])
    out = pd.concat(frames, ignore_index=True)
    out["decision_timestamp"] = pd.to_datetime(out["decision_timestamp"], utc=True)
    return out


def load_zone_lookup(symbols: list[str]) -> dict[str, dict[str, object]]:
    cols = [
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
        "trendline_interaction_type",
        "trendline_pa_zone_score",
        "trendline_zone_confluence_count",
        "lookahead_pass",
    ]
    zones = pd.read_parquet(HTF_ZONES_PARQUET, columns=cols)
    zones = zones[zones["symbol"].isin(symbols)].copy()
    zones["available_at"] = pd.to_datetime(zones["available_at"], utc=True)
    zones["latest_source_candle_close_used"] = pd.to_datetime(zones["latest_source_candle_close_used"], utc=True)
    return {
        str(row.object_id): {
            "object_id": str(row.object_id),
            "symbol": str(row.symbol),
            "timeframe": str(row.timeframe),
            "object_type": str(row.object_type),
            "zone_side": str(row.side),
            "zone_low": float(row.zone_low),
            "zone_high": float(row.zone_high),
            "zone_mid": float(row.zone_mid),
            "available_at": pd.Timestamp(row.available_at),
            "latest_source_candle_close_used": pd.Timestamp(row.latest_source_candle_close_used),
            "trendline_interaction_type": str(row.trendline_interaction_type),
            "trendline_pa_zone_score": float(row.trendline_pa_zone_score),
            "trendline_zone_confluence_count": int(row.trendline_zone_confluence_count),
            "lookahead_pass": bool(row.lookahead_pass),
        }
        for row in zones.itertuples(index=False)
    }


def scenario_side_from_row(row: pd.Series) -> str:
    side = str(row["side"])
    if str(row["btc_context_effect_for_side"]) == "veto" and float(row["thesis_score"]) < 0.78:
        return "observe"
    return side if side in {"long", "short"} else "observe"


def primary_source_has_structural_overlap(row: pd.Series) -> bool:
    kind = str(row["htf_zone_kind"])
    if "fvg" in kind:
        return float(row["fvg_zone_score"]) >= 0.45
    if any(token in kind for token in ["sr", "swing"]):
        return float(row["sr_zone_score"]) >= 0.35
    if any(token in kind for token in ["liquidity", "day_high_low", "previous_day_high_low"]):
        return float(row["liquidity_score"]) >= 0.35 or float(row["sr_zone_score"]) >= 0.35
    return False


def scenario_activation_quality(row: pd.Series) -> float:
    distance = max(0.0, float(row["activation_distance_atr"]))
    proximity = max(0.0, 1.0 - min(distance / max(APPROACHING_DISTANCE_ATR, 1e-9), 1.0))
    target_bonus = 0.10 * bool(row["core_candidate_present"]) + 0.05 * bool(row["runner_candidate_present"])
    btc_effect = str(row["btc_context_effect_for_side"])
    btc_bonus = {"confirm": 0.05, "neutral": 0.02, "warn": -0.02, "veto": -0.08}.get(btc_effect, 0.0)
    timeframe_bonus = {"4h": 0.04, "1h": 0.03, "15m": 0.01}.get(str(row["htf_zone_timeframe"]), 0.0)
    return float(max(0.0, min(1.0, proximity * 0.78 + target_bonus + btc_bonus + timeframe_bonus)))


def htf_trendline_context(row: pd.Series, scenario_type: str | None = None) -> tuple[bool, int, str]:
    interaction = str(row["trendline_interaction_type"])
    kind = str(row["htf_zone_kind"])
    side = str(row["side"])
    conditions = [
        float(row["trendline_pa_zone_score"]) >= STRONG_TRENDLINE_SCORE_THRESHOLD,
        int(row["trendline_zone_confluence_count"]) >= 2,
        interaction in {"sweep", "rejection", "break_retest"},
        primary_source_has_structural_overlap(row),
        float(row["activation_distance_atr"]) <= TRENDLINE_ACTIVE_DISTANCE_ATR,
    ]
    condition_count = int(sum(bool(value) for value in conditions))
    trendline_specific_count = int(sum(bool(value) for value in conditions[:3]))
    used = condition_count >= MIN_TRENDLINE_CONTEXT_CONDITIONS and trendline_specific_count >= 2
    if interaction == "rejection":
        used = bool(
            used
            and float(row["trendline_pa_zone_score"]) >= 0.85
            and int(row["trendline_zone_confluence_count"]) >= 3
        )
    if interaction == "clean_break" and scenario_type is not None:
        direction_matches = (
            (side == "long" and scenario_type == "htf_trendline_breakout")
            or (side == "short" and scenario_type == "htf_trendline_breakdown")
        )
        used = bool(used and direction_matches)
    if used:
        reason = f"strong_context_{condition_count}_conditions_{trendline_specific_count}_trendline_specific"
    else:
        reason = f"weak_context_{condition_count}_conditions_{trendline_specific_count}_trendline_specific"
    return bool(used), condition_count, reason


def scenario_type_from_row(row: pd.Series, zone: dict[str, object] | None, trendline_context_used: bool) -> str:
    side = str(row["side"])
    mode = str(row["thesis_mode"])
    kind = str(row["htf_zone_kind"])
    interaction = str(row["trendline_interaction_type"])
    zone_side = str(zone.get("zone_side", "")) if zone else ""

    if mode.startswith("C"):
        return "continuation_pullback"
    if trendline_context_used and interaction in {"sweep", "rejection", "break_retest", "clean_break", "near_touch"}:
        if interaction == "sweep":
            return "htf_trendline_fakeout_reclaim"
        if interaction == "break_retest":
            return "htf_trendline_breakout" if side == "long" else "htf_trendline_breakdown"
        if interaction == "clean_break":
            return "htf_trendline_breakout" if side == "long" else "htf_trendline_breakdown"
    if "fvg" in kind:
        return "bullish_retrace_to_15m_fvg_mid" if side == "long" else "bearish_retrace_to_15m_fvg_mid"
    if any(token in kind for token in ["liquidity", "day_high_low", "previous_day_high_low"]):
        return "liquidity_sweep_reversal"
    if any(token in kind for token in ["sr", "swing"]):
        return "sr_flip_retest"
    if trendline_context_used:
        if side == "long" and zone_side == "support":
            return "htf_trendline_support_hold"
        if side == "short" and zone_side == "resistance":
            return "htf_trendline_resistance_reject"
    return "continuation_pullback" if mode.startswith("C") else "liquidity_sweep_reversal"


def scenario_priority(row: pd.Series) -> float:
    timeframe_bonus = {"4h": 0.18, "1h": 0.12, "15m": 0.06}.get(str(row["htf_zone_timeframe"]), 0.0)
    kind = str(row["htf_zone_kind"])
    if "fvg" in kind:
        kind_bonus = 0.12
    elif any(token in kind for token in ["liquidity", "day_high_low", "previous"]):
        kind_bonus = 0.10
    elif any(token in kind for token in ["sr", "swing"]):
        kind_bonus = 0.06
    else:
        kind_bonus = 0.0
    interaction_bonus = {
        "sweep": 0.08,
        "break_retest": 0.08,
        "rejection": 0.06,
        "near_touch": 0.03,
        "clean_break": -0.10,
        "none": 0.0,
    }.get(str(row["trendline_interaction_type"]), 0.0)
    btc_bonus = {"confirm": 0.06, "neutral": 0.00, "warn": -0.04, "veto": -0.12}.get(
        str(row["btc_context_effect_for_side"]), 0.0
    )
    target_bonus = 0.08 * bool(row["core_candidate_present"]) + 0.04 * bool(row["runner_candidate_present"])
    distance_penalty = min(0.18, max(0.0, float(row["htf_zone_distance_atr"])) * 0.06)
    return float(
        float(row["thesis_score"]) * 0.34
        + float(row["structural_path_score"]) * 0.16
        + float(row["htf_location_score"]) * 0.12
        + float(row["trendline_pa_zone_score"]) * 0.14
        + timeframe_bonus
        + kind_bonus
        + interaction_bonus
        + btc_bonus
        + target_bonus
        - distance_penalty
    )


def activation_state(distance_atr: float, reference_price: float, zone: dict[str, object] | None) -> str:
    if zone is not None and float(zone["zone_low"]) <= reference_price <= float(zone["zone_high"]):
        return "active"
    if distance_atr <= ACTIVE_DISTANCE_ATR:
        return "active"
    if distance_atr <= APPROACHING_DISTANCE_ATR:
        return "approaching"
    return "inactive"


def expected_reaction(side: str, scenario_type: str) -> str:
    if side == "long":
        return "sweep_or_rejection_then_bullish_displacement_into_1m_fvg"
    if side == "short":
        return "sweep_or_rejection_then_bearish_displacement_into_1m_fvg"
    return f"observe_{scenario_type}_until_directional_reaction"


def load_inputs(symbols: list[str]) -> tuple[pd.DataFrame, dict[str, dict[str, object]], pd.DataFrame, pd.DataFrame]:
    thesis_cols = [
        "symbol",
        "decision_timestamp",
        "side",
        "reference_price",
        "thesis_valid",
        "thesis_mode",
        "thesis_score",
        "htf_zone_kind",
        "htf_zone_timeframe",
        "htf_location_score",
        "sr_zone_score",
        "fvg_zone_score",
        "liquidity_score",
        "trendline_pa_zone_score",
        "trendline_interaction_type",
        "trendline_zone_confluence_count",
        "btc_context_effect_for_side",
        "btc_context_reason",
        "btc_leader_context_score_for_side",
        "target_pool_present",
        "core_candidate_present",
        "runner_candidate_present",
        "structural_path_score",
        "target_pool_conflict_reason",
        "htf_zone_object_id",
        "htf_zone_available_at",
        "htf_zone_latest_source_candle_close_used",
        "htf_zone_distance_atr",
        "latest_btc_source_close_used",
        "lookahead_pass",
    ]
    thesis = pd.read_parquet(THESIS_PARQUET, columns=thesis_cols)
    thesis = thesis[thesis["symbol"].isin(symbols)].copy()
    thesis["decision_timestamp"] = pd.to_datetime(thesis["decision_timestamp"], utc=True)
    thesis["htf_zone_available_at"] = pd.to_datetime(thesis["htf_zone_available_at"], utc=True)
    thesis["htf_zone_latest_source_candle_close_used"] = pd.to_datetime(
        thesis["htf_zone_latest_source_candle_close_used"], utc=True
    )
    thesis["latest_btc_source_close_used"] = pd.to_datetime(thesis["latest_btc_source_close_used"], utc=True)
    thesis = thesis[thesis["thesis_valid"].astype(bool) & thesis["lookahead_pass"].astype(bool)].copy()

    target_summary = pd.read_parquet(TARGET_SUMMARY_PARQUET)
    target_summary = target_summary[target_summary["symbol"].isin(symbols)].copy()
    target_summary["decision_timestamp"] = pd.to_datetime(target_summary["decision_timestamp"], utc=True)
    target_summary["target_pool_summary_id"] = [
        stable_id("target_summary", row.symbol, row.decision_timestamp, row.side)
        for row in target_summary.itertuples(index=False)
    ]

    btc = pd.read_parquet(
        BTC_CONTEXT_PARQUET,
        columns=[
            "decision_timestamp",
            "btc_context_effect",
            "btc_long_context_effect",
            "btc_short_context_effect",
            "btc_pa_reaction_state",
            "btc_context_reason",
            "latest_source_candle_close_used",
            "lookahead_pass",
        ],
    )
    btc["decision_timestamp"] = pd.to_datetime(btc["decision_timestamp"], utc=True)
    btc["latest_source_candle_close_used"] = pd.to_datetime(btc["latest_source_candle_close_used"], utc=True)
    return thesis, load_zone_lookup(symbols), target_summary, btc


def build_scenarios(symbols: list[str]) -> pd.DataFrame:
    thesis, zone_lookup, target_summary, _btc = load_inputs(symbols)
    atr = load_15m_atr(symbols)
    thesis = thesis.merge(atr, on=["symbol", "decision_timestamp"], how="left", validate="many_to_one")
    target_index = target_summary.set_index(["symbol", "decision_timestamp", "side"])

    thesis["activation_distance_atr"] = thesis["htf_zone_distance_atr"].fillna(np.inf).astype(float)
    thesis = thesis[thesis["activation_distance_atr"] <= MAX_ACTIVATION_DISTANCE_ATR].copy()
    thesis["scenario_priority"] = [scenario_priority(row) for _, row in thesis.iterrows()]
    thesis["scenario_activation_quality"] = [scenario_activation_quality(row) for _, row in thesis.iterrows()]
    thesis["htf_trendline_context_before"] = thesis["trendline_pa_zone_score"].astype(float) >= 0.45
    trendline_context = [htf_trendline_context(row) for _, row in thesis.iterrows()]
    thesis["htf_trendline_used_for_pa_zone"] = [value[0] for value in trendline_context]
    thesis["htf_trendline_context_condition_count"] = [value[1] for value in trendline_context]
    thesis["htf_trendline_context_reason"] = [value[2] for value in trendline_context]
    thesis["weak_trendline_context_filtered"] = (
        thesis["htf_trendline_context_before"].astype(bool)
        & ~thesis["htf_trendline_used_for_pa_zone"].astype(bool)
    )
    thesis = thesis[
        (thesis["scenario_priority"] >= MIN_SCENARIO_PRIORITY)
        & (thesis["scenario_activation_quality"] >= MIN_SCENARIO_ACTIVATION_QUALITY)
    ].copy()
    thesis = thesis.sort_values(["symbol", "decision_timestamp", "scenario_priority"], ascending=[True, True, False])
    timestamp_top = thesis.groupby(["symbol", "decision_timestamp"], sort=True).head(1).copy()
    timestamp_top["scenario_date_utc"] = (
        timestamp_top["decision_timestamp"] - pd.Timedelta(minutes=1)
    ).dt.date.astype(str)
    timestamp_top = timestamp_top.drop_duplicates(["symbol", "scenario_date_utc", "htf_zone_object_id"], keep="first")
    selected = (
        timestamp_top.sort_values(
            ["symbol", "scenario_date_utc", "decision_timestamp", "scenario_priority"],
            ascending=[True, True, True, False],
        )
        .groupby(["symbol", "scenario_date_utc"], sort=True)
        .head(MAX_SCENARIOS_PER_SYMBOL_DAY)
        .copy()
    )

    rows: list[dict[str, object]] = []
    for row in selected.itertuples(index=False):
        row_s = pd.Series(row._asdict())
        zone = zone_lookup.get(str(row_s["htf_zone_object_id"]))
        side = str(row_s["side"])
        scenario_side = scenario_side_from_row(row_s)
        scenario_type = scenario_type_from_row(row_s, zone, bool(row_s["htf_trendline_used_for_pa_zone"]))
        if bool(row_s["htf_trendline_used_for_pa_zone"]):
            used, count, reason = htf_trendline_context(row_s, scenario_type)
            row_s["htf_trendline_used_for_pa_zone"] = used
            row_s["htf_trendline_context_condition_count"] = count
            row_s["htf_trendline_context_reason"] = reason
            row_s["weak_trendline_context_filtered"] = bool(row_s["htf_trendline_context_before"]) and not used
        if scenario_type not in SCENARIO_TYPES:
            scenario_type = "continuation_pullback"
        scenario_built_at = utc_timestamp(row_s["decision_timestamp"])
        reference_price = float(row_s["reference_price"])
        atr_15m = float(row_s.get("atr_15m", np.nan))
        if pd.isna(atr_15m) or atr_15m <= 0:
            atr_15m = max(reference_price * 0.002, 1e-9)
        zone_low = float(zone["zone_low"]) if zone else np.nan
        zone_high = float(zone["zone_high"]) if zone else np.nan
        zone_mid = float(zone["zone_mid"]) if zone else np.nan
        buffer = max(reference_price * 0.0004, atr_15m * 0.12)
        if side == "long":
            invalidation = zone_low - buffer if pd.notna(zone_low) else reference_price - atr_15m
        elif side == "short":
            invalidation = zone_high + buffer if pd.notna(zone_high) else reference_price + atr_15m
        else:
            invalidation = np.nan
        try:
            summary_row = target_index.loc[(str(row_s["symbol"]), scenario_built_at, side)]
            target_path_available = bool(
                summary_row.get("core_structural_source_present", False)
                or summary_row.get("runner_structural_source_present", False)
            )
            target_pool_summary_id = str(summary_row.get("target_pool_summary_id", ""))
            target_lookahead = bool(summary_row.get("lookahead_pass", False))
        except KeyError:
            target_path_available = False
            target_pool_summary_id = ""
            target_lookahead = False

        zone_available = zone["available_at"] if zone else pd.NaT
        zone_latest = zone["latest_source_candle_close_used"] if zone else pd.NaT
        source_checks = [
            zone is not None,
            pd.notna(zone_available) and zone_available <= scenario_built_at,
            pd.notna(zone_latest) and zone_latest <= scenario_built_at,
            pd.isna(row_s["latest_btc_source_close_used"]) or row_s["latest_btc_source_close_used"] <= scenario_built_at,
            bool(row_s["lookahead_pass"]),
            target_lookahead,
        ]
        lookahead_pass = all(bool(value) for value in source_checks)
        rows.append(
            {
                "symbol": str(row_s["symbol"]),
                "scenario_id": stable_id(
                    "scenario_v1_2_1",
                    row_s["symbol"],
                    row_s["scenario_date_utc"],
                    row_s["htf_zone_object_id"],
                    side,
                    scenario_built_at,
                ),
                "scenario_date_utc": str(row_s["scenario_date_utc"]),
                "scenario_built_at": scenario_built_at,
                "scenario_side": scenario_side,
                "scenario_type": scenario_type,
                "primary_pa_zone_id": str(row_s["htf_zone_object_id"]),
                "primary_pa_zone_source": str(row_s["htf_zone_kind"]),
                "primary_pa_zone_timeframe": str(row_s["htf_zone_timeframe"]),
                "primary_zone_low": zone_low,
                "primary_zone_high": zone_high,
                "primary_zone_mid": zone_mid,
                "activation_distance_atr": float(row_s["activation_distance_atr"]),
                "scenario_activation_state": activation_state(
                    float(row_s["activation_distance_atr"]), reference_price, zone
                ),
                "scenario_priority": float(row_s["scenario_priority"]),
                "scenario_activation_quality": float(row_s["scenario_activation_quality"]),
                "btc_context_effect_for_scenario": str(row_s["btc_context_effect_for_side"]),
                "btc_context_reason": str(row_s["btc_context_reason"]),
                "expected_reaction": expected_reaction(side, scenario_type),
                "invalidation_price": float(invalidation),
                "target_path_available": bool(target_path_available),
                "target_pool_summary_id": target_pool_summary_id,
                "reference_price": reference_price,
                "source_thesis_mode": str(row_s["thesis_mode"]),
                "source_thesis_score": float(row_s["thesis_score"]),
                "htf_trendline_context_before": bool(row_s["htf_trendline_context_before"]),
                "htf_trendline_used_for_pa_zone": bool(row_s["htf_trendline_used_for_pa_zone"]),
                "htf_trendline_context_condition_count": int(row_s["htf_trendline_context_condition_count"]),
                "htf_trendline_context_reason": str(row_s["htf_trendline_context_reason"]),
                "weak_trendline_context_filtered": bool(row_s["weak_trendline_context_filtered"]),
                "htf_trendline_interaction_type": str(row_s["trendline_interaction_type"]),
                "zone_available_at": zone_available,
                "latest_source_candle_close_used": zone_latest,
                "latest_btc_source_close_used": row_s["latest_btc_source_close_used"],
                "lookahead_pass": bool(lookahead_pass),
                "lookahead_violation_reason": "" if lookahead_pass else "source_time_after_scenario_built_at",
            }
        )
    return pd.DataFrame(rows).sort_values(["symbol", "scenario_built_at", "scenario_priority"]).reset_index(drop=True)


def build_audit(scenarios: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "scenario_id",
        "symbol",
        "scenario_built_at",
        "primary_pa_zone_id",
        "zone_available_at",
        "latest_source_candle_close_used",
        "latest_btc_source_close_used",
        "target_pool_summary_id",
        "lookahead_pass",
        "lookahead_violation_reason",
    ]
    audit = scenarios[cols].copy()
    for column in ["scenario_built_at", "zone_available_at", "latest_source_candle_close_used", "latest_btc_source_close_used"]:
        audit[column] = pd.to_datetime(audit[column], utc=True, errors="coerce")
    lookahead = (
        audit["zone_available_at"].notna()
        & (audit["zone_available_at"] <= audit["scenario_built_at"])
        & audit["latest_source_candle_close_used"].notna()
        & (audit["latest_source_candle_close_used"] <= audit["scenario_built_at"])
        & (audit["latest_btc_source_close_used"].isna() | (audit["latest_btc_source_close_used"] <= audit["scenario_built_at"]))
    )
    audit["lookahead_pass"] = lookahead.astype(bool)
    audit.loc[audit["lookahead_pass"], "lookahead_violation_reason"] = ""
    audit.loc[~audit["lookahead_pass"], "lookahead_violation_reason"] = "source_time_after_scenario_built_at"
    return audit


def write_report(scenarios: pd.DataFrame, audit: pd.DataFrame, symbols: list[str]) -> None:
    counts = scenarios["scenario_type"].value_counts().reset_index()
    counts.columns = ["scenario_type", "rows"]
    side_counts = scenarios["scenario_side"].value_counts().reset_index()
    side_counts.columns = ["scenario_side", "rows"]
    state_counts = scenarios["scenario_activation_state"].value_counts().reset_index()
    state_counts.columns = ["scenario_activation_state", "rows"]
    source_counts = scenarios["primary_pa_zone_source"].value_counts().head(20).reset_index()
    source_counts.columns = ["primary_pa_zone_source", "rows"]
    symbol_side = scenarios.groupby(["symbol", "scenario_side"]).size().reset_index(name="rows")
    htf_trendline_before_pct = float(scenarios["htf_trendline_context_before"].mean() * 100) if len(scenarios) else 0.0
    htf_trendline_pct = float(scenarios["htf_trendline_used_for_pa_zone"].mean() * 100) if len(scenarios) else 0.0
    weak_trendline_count = int(scenarios["weak_trendline_context_filtered"].sum()) if len(scenarios) else 0
    source_dates = pd.read_parquet(THESIS_PARQUET, columns=["symbol", "decision_timestamp"])
    source_dates = source_dates[source_dates["symbol"].isin(symbols)].copy()
    source_dates["decision_timestamp"] = pd.to_datetime(source_dates["decision_timestamp"], utc=True)
    source_dates["scenario_date_utc"] = (source_dates["decision_timestamp"] - pd.Timedelta(minutes=1)).dt.date.astype(str)
    full_symbol_days = source_dates[["symbol", "scenario_date_utc"]].drop_duplicates().sort_values(["symbol", "scenario_date_utc"])
    full_index = pd.MultiIndex.from_frame(full_symbol_days)
    per_day = scenarios.groupby(["symbol", "scenario_date_utc"]).size().reindex(full_index, fill_value=0)
    per_day_distribution = (
        per_day.value_counts()
        .reindex(range(0, MAX_SCENARIOS_PER_SYMBOL_DAY + 1), fill_value=0)
        .reset_index()
    )
    per_day_distribution.columns = ["scenarios_per_symbol_day", "symbol_days"]
    date_min = full_symbol_days["scenario_date_utc"].min() if len(full_symbol_days) else ""
    date_max = full_symbol_days["scenario_date_utc"].max() if len(full_symbol_days) else ""
    source_change = []
    current_source_counts = scenarios["primary_pa_zone_source"].value_counts().to_dict()
    all_sources = sorted(set(PRE_REFINEMENT_PRIMARY_SOURCE_COUNTS) | set(current_source_counts))
    for source in all_sources:
        before = int(PRE_REFINEMENT_PRIMARY_SOURCE_COUNTS.get(source, 0))
        after = int(current_source_counts.get(source, 0))
        source_change.append({"primary_pa_zone_source": source, "before_rows": before, "after_rows": after, "delta": after - before})
    latest_sniper_headline = ""
    latest_sniper_delta = ""
    if SNIPER_CANDIDATES_PARQUET.exists():
        sniper = pd.read_parquet(SNIPER_CANDIDATES_PARQUET, columns=["sniper_candidate_status", "entry_pattern_tier"])
        latest_count = int(
            (
                sniper["sniper_candidate_status"].eq("accepted_headline")
                & sniper["entry_pattern_tier"].isin(["S_tier_sniper", "A_tier_sniper"])
            ).sum()
        )
        latest_sniper_headline = str(latest_count)
        latest_sniper_delta = str(latest_count - PRE_REFINEMENT_SNIPER_HEADLINE_ROWS)
    violations = int((~audit["lookahead_pass"]).sum())
    lines = [
        "# Craig v1.2.1 Scenario Thesis Report",
        "",
        "Generated by `scripts/build_craig_v1_2_scenario_thesis.py`.",
        "",
        "## Verdict",
        "",
        "- Existing v1.2 outputs were preserved; this is a separate v1.2.1 scenario layer.",
        "- Broad long/short 15m thesis rows are narrowed into scenario rows built only around active or approaching HTF/15m PA zones.",
        f"- At most {MAX_SCENARIOS_PER_SYMBOL_DAY} scenarios per symbol/UTC day are retained, but rows must pass priority >= {MIN_SCENARIO_PRIORITY:.2f} and activation quality >= {MIN_SCENARIO_ACTIVATION_QUALITY:.2f}.",
        "- HTF/15m trendlines are used only as PA-zone/scenario context, not as the 1m entry trigger.",
        f"- HTF trendline context now requires at least {MIN_TRENDLINE_CONTEXT_CONDITIONS} strong context conditions instead of only `trendline_pa_zone_score >= 0.45`.",
        f"- Lookahead violations: {violations}.",
        "",
        "## Dataset",
        "",
        f"- Symbols: {', '.join(symbols)}",
        f"- Scenario source-date range UTC: {date_min} to {date_max}",
        f"- Scenario rows: {len(scenarios)}",
        f"- Previous v1.2.1 scenario rows: {PRE_REFINEMENT_SCENARIO_ROWS}",
        f"- Scenario row delta: {len(scenarios) - PRE_REFINEMENT_SCENARIO_ROWS}",
        f"- Latest S/A headline rows from sniper parquet: {latest_sniper_headline}",
        f"- Latest S/A headline delta vs previous v1.2.1: {latest_sniper_delta}",
        f"- Mean scenarios per symbol/day: {per_day.mean():.3f}",
        f"- Median scenarios per symbol/day: {per_day.median():.3f}",
        f"- Max scenarios per symbol/day: {int(per_day.max()) if not per_day.empty else 0}",
        f"- 0-scenario symbol-days: {int((per_day == 0).sum())}",
        "",
        "## Scenario Per Symbol-Day Distribution",
        "",
        *markdown_table(per_day_distribution.to_dict("records"), ["scenarios_per_symbol_day", "symbol_days"]),
        "",
        "## Scenario Type Distribution",
        "",
        *markdown_table(counts.to_dict("records"), ["scenario_type", "rows"]),
        "",
        "## Scenario Side Distribution",
        "",
        *markdown_table(side_counts.to_dict("records"), ["scenario_side", "rows"]),
        "",
        "## Symbol And Side Distribution",
        "",
        *markdown_table(symbol_side.to_dict("records"), ["symbol", "scenario_side", "rows"]),
        "",
        "## Activation State Distribution",
        "",
        *markdown_table(state_counts.to_dict("records"), ["scenario_activation_state", "rows"]),
        "",
        "## Primary PA Zone Sources",
        "",
        *markdown_table(source_counts.to_dict("records"), ["primary_pa_zone_source", "rows"]),
        "",
        "## Primary PA Zone Source Change",
        "",
        *markdown_table(source_change, ["primary_pa_zone_source", "before_rows", "after_rows", "delta"]),
        "",
        "## HTF Trendline Context",
        "",
        f"- Previous v1.2.1 HTF/15m trendline context ratio: {PRE_REFINEMENT_HTF_TRENDLINE_CONTEXT_PCT:.3f}%",
        f"- Before strict gate ratio on current scenarios: {htf_trendline_before_pct:.3f}%",
        f"- After strict gate ratio on current scenarios: {htf_trendline_pct:.3f}%",
        f"- Weak trendline contexts filtered/de-emphasized: {weak_trendline_count}",
        "- This flag does not authorize entry by itself. Entry permission is left to the v1.2.1 sniper layer.",
        "",
        "## No-Lookahead Controls",
        "",
        "- `scenario_built_at` is a closed 15m decision timestamp.",
        "- Primary PA-zone `available_at` and `latest_source_candle_close_used` must be at or before `scenario_built_at`.",
        "- BTC context source close must be at or before `scenario_built_at`.",
        "- No realized outcome, gold label, Craig action, result R, fill, stop hit, target hit, or PnL is read.",
        "",
        "## Output Paths",
        "",
        f"- Scenario parquet: `{OUT_SCENARIOS.relative_to(ROOT)}`",
        f"- Audit CSV: `{OUT_AUDIT.relative_to(ROOT)}`",
    ]
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=HEADLINE_SYMBOLS)
    args = parser.parse_args()
    symbols = [symbol.upper() for symbol in args.symbols]
    scenarios = build_scenarios(symbols)
    audit = build_audit(scenarios)
    if not audit["lookahead_pass"].all():
        raise RuntimeError(f"Scenario lookahead audit failed for {int((~audit['lookahead_pass']).sum())} rows")
    OUT_SCENARIOS.parent.mkdir(parents=True, exist_ok=True)
    scenarios.to_parquet(OUT_SCENARIOS, index=False)
    audit.to_csv(OUT_AUDIT, index=False, encoding="utf-8-sig")
    write_report(scenarios, audit, symbols)
    print(f"scenario_thesis={OUT_SCENARIOS} rows={len(scenarios)}")
    print(f"audit={OUT_AUDIT} rows={len(audit)} lookahead_pass={int(audit['lookahead_pass'].sum())}/{len(audit)}")
    print(f"report={OUT_REPORT}")


if __name__ == "__main__":
    main()
