#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from build_craig_v1_2_trade_candidates import (
    HEADLINE_SYMBOLS,
    MIN_CORE_RR_NET,
    ROOT,
    THESIS_PARQUET,
    TARGET_SUMMARY_PARQUET,
    combine_targets_and_rr,
    latest_tf_close,
    load_market_data,
    load_target_lookup,
    load_target_summary,
    markdown_table,
    ns_to_utc,
    stable_id,
    utc_timestamp,
)


SCENARIO_PARQUET = ROOT / "outputs/craig_v1_2_scenario_thesis.parquet"
BROAD_TRADE_CANDIDATES_PARQUET = ROOT / "outputs/craig_v1_2_trade_candidates.parquet"

OUT_CANDIDATES = ROOT / "outputs/craig_v1_2_sniper_trade_candidates.parquet"
OUT_AUDIT = ROOT / "outputs/craig_v1_2_sniper_trade_candidate_audit.csv"
OUT_REPORT = ROOT / "outputs/craig_v1_2_sniper_trade_candidate_report.md"

SNIPER_SEARCH_MINUTES = 180
POST_ZONE_TRIGGER_MINUTES = 45
DUPLICATE_SUPPRESSION_MINUTES = 240
MAX_CHASE_ATR = 1.10
MIN_STOP_ATR = 0.20
MAX_STOP_ATR = 1.80
MIN_DISPLACEMENT_BODY_ATR = 0.45
MIN_DISPLACEMENT_BODY_SCORE = 0.58

PRE_REFINEMENT_SCENARIO_ROWS = 5796
PRE_REFINEMENT_SNIPER_HEADLINE_ROWS = 2086
PRE_REFINEMENT_SNIPER_S_TIER_ROWS = 199
PRE_REFINEMENT_SNIPER_A_TIER_ROWS = 1887
PRE_REFINEMENT_HTF_TRENDLINE_HEADLINE_PCT = 100.0


@dataclass(frozen=True)
class OneMinuteStructure:
    swing_high_idx: np.ndarray
    swing_high_price: np.ndarray
    swing_high_confirm_idx: np.ndarray
    swing_low_idx: np.ndarray
    swing_low_price: np.ndarray
    swing_low_confirm_idx: np.ndarray


def side_sign(side: str) -> int:
    return 1 if side == "long" else -1


def directional_move(side: str, price: float, reference: float) -> float:
    return (price - reference) * side_sign(side)


def overlaps_zone(low: float, high: float, zone_low: float, zone_high: float, tolerance: float) -> bool:
    return high >= zone_low - tolerance and low <= zone_high + tolerance


def candle_body_score(open_: float, high: float, low: float, close: float, side: str) -> float:
    rng = max(high - low, 1e-12)
    body = abs(close - open_)
    close_location = (close - low) / rng if side == "long" else (high - close) / rng
    direction_ok = close >= open_ if side == "long" else close <= open_
    return float((body / rng) * 0.55 + close_location * 0.45) if direction_ok else 0.0


def build_1m_structure(market) -> OneMinuteStructure:
    highs = pd.Series(market.high)
    lows = pd.Series(market.low)
    swing_high = (
        highs.eq(highs.rolling(5, center=True, min_periods=5).max())
        & highs.gt(highs.shift(1))
        & highs.gt(highs.shift(-1))
    ).fillna(False)
    swing_low = (
        lows.eq(lows.rolling(5, center=True, min_periods=5).min())
        & lows.lt(lows.shift(1))
        & lows.lt(lows.shift(-1))
    ).fillna(False)
    sh_idx = np.flatnonzero(swing_high.to_numpy())
    sl_idx = np.flatnonzero(swing_low.to_numpy())
    sh_confirm = sh_idx + 2
    sl_confirm = sl_idx + 2
    valid_sh = sh_confirm < len(market.close)
    valid_sl = sl_confirm < len(market.close)
    return OneMinuteStructure(
        swing_high_idx=sh_idx[valid_sh].astype(int),
        swing_high_price=market.high[sh_idx[valid_sh]].astype(float),
        swing_high_confirm_idx=sh_confirm[valid_sh].astype(int),
        swing_low_idx=sl_idx[valid_sl].astype(int),
        swing_low_price=market.low[sl_idx[valid_sl]].astype(float),
        swing_low_confirm_idx=sl_confirm[valid_sl].astype(int),
    )


def last_two_swings(confirm_idx: np.ndarray, swing_idx: np.ndarray, prices: np.ndarray, current_idx: int):
    pos = int(np.searchsorted(confirm_idx, current_idx, side="left"))
    if pos < 2:
        return None
    return (
        int(swing_idx[pos - 2]),
        float(prices[pos - 2]),
        int(swing_idx[pos - 1]),
        float(prices[pos - 1]),
    )


def one_min_trendline_state(market, structure: OneMinuteStructure, i: int, side: str) -> dict[str, object]:
    tolerance = max(float(market.atr_1m[i]) * 0.12, float(market.close[i]) * 0.00015)
    if side == "long":
        anchors = last_two_swings(
            structure.swing_high_confirm_idx,
            structure.swing_high_idx,
            structure.swing_high_price,
            i,
        )
    else:
        anchors = last_two_swings(
            structure.swing_low_confirm_idx,
            structure.swing_low_idx,
            structure.swing_low_price,
            i,
        )
    if anchors is None:
        return {
            "one_min_trendline_id": "",
            "one_min_trendline_break_confirmed": False,
            "projected_price": np.nan,
            "line_tolerance": tolerance,
        }
    idx1, price1, idx2, price2 = anchors
    if idx2 <= idx1:
        return {
            "one_min_trendline_id": "",
            "one_min_trendline_break_confirmed": False,
            "projected_price": np.nan,
            "line_tolerance": tolerance,
        }
    slope = (price2 - price1) / (idx2 - idx1)
    projected = price1 + slope * (i - idx1)
    previous_projected = price1 + slope * ((i - 1) - idx1)
    if side == "long":
        break_confirmed = market.close[i] > projected + tolerance and market.close[i - 1] <= previous_projected + tolerance
    else:
        break_confirmed = market.close[i] < projected - tolerance and market.close[i - 1] >= previous_projected - tolerance
    return {
        "one_min_trendline_id": stable_id("1m_trendline", side, idx1, round(price1, 8), idx2, round(price2, 8)),
        "one_min_trendline_break_confirmed": bool(break_confirmed),
        "projected_price": float(projected),
        "line_tolerance": float(tolerance),
    }


def one_min_choch_bos(market, structure: OneMinuteStructure, i: int, side: str) -> bool:
    if side == "long":
        pos = int(np.searchsorted(structure.swing_high_confirm_idx, i, side="left")) - 1
        if pos < 0:
            return False
        level = float(structure.swing_high_price[pos])
        return bool(market.close[i] > level and market.close[i - 1] <= level)
    pos = int(np.searchsorted(structure.swing_low_confirm_idx, i, side="left")) - 1
    if pos < 0:
        return False
    level = float(structure.swing_low_price[pos])
    return bool(market.close[i] < level and market.close[i - 1] >= level)


def displacement_and_fvg(market, i: int, side: str) -> dict[str, object]:
    if i < 2:
        return {
            "one_min_displacement_confirmed": False,
            "one_min_fvg_id": "",
            "one_min_fvg_low": np.nan,
            "one_min_fvg_high": np.nan,
            "one_min_fvg_mid": np.nan,
            "one_min_fvg_created_at": pd.NaT,
            "fvg_created_by_displacement": False,
        }
    body = abs(float(market.close[i] - market.open_[i]))
    body_score = candle_body_score(
        float(market.open_[i]),
        float(market.high[i]),
        float(market.low[i]),
        float(market.close[i]),
        side,
    )
    displacement = bool(body >= MIN_DISPLACEMENT_BODY_ATR * float(market.atr_1m[i]) and body_score >= MIN_DISPLACEMENT_BODY_SCORE)
    if side == "long":
        fvg_created = bool(market.low[i] > market.high[i - 2])
        fvg_low = float(market.high[i - 2]) if fvg_created else np.nan
        fvg_high = float(market.low[i]) if fvg_created else np.nan
    else:
        fvg_created = bool(market.high[i] < market.low[i - 2])
        fvg_low = float(market.high[i]) if fvg_created else np.nan
        fvg_high = float(market.low[i - 2]) if fvg_created else np.nan
    if not displacement or not fvg_created:
        return {
            "one_min_displacement_confirmed": bool(displacement),
            "one_min_fvg_id": "",
            "one_min_fvg_low": np.nan,
            "one_min_fvg_high": np.nan,
            "one_min_fvg_mid": np.nan,
            "one_min_fvg_created_at": pd.NaT,
            "fvg_created_by_displacement": False,
        }
    fvg_mid = (fvg_low + fvg_high) / 2.0
    created_at = ns_to_utc(int(market.close_ns_1m[i]))
    return {
        "one_min_displacement_confirmed": True,
        "one_min_fvg_id": stable_id("1m_fvg", side, created_at, round(fvg_low, 8), round(fvg_high, 8)),
        "one_min_fvg_low": float(fvg_low),
        "one_min_fvg_high": float(fvg_high),
        "one_min_fvg_mid": float(fvg_mid),
        "one_min_fvg_created_at": created_at,
        "fvg_created_by_displacement": True,
    }


def zone_reaction_state(market, i: int, side: str, zone_low: float, zone_high: float, zone_mid: float) -> tuple[bool, bool]:
    if side == "long":
        sweep = bool(market.low[i] < min(float(market.prev5_low[i]), zone_low) and market.close[i] > min(float(market.prev5_low[i]), zone_low))
        rejection = bool(market.low[i] <= zone_mid and market.close[i] > zone_mid and market.close[i] >= market.open_[i])
    else:
        sweep = bool(market.high[i] > max(float(market.prev5_high[i]), zone_high) and market.close[i] < max(float(market.prev5_high[i]), zone_high))
        rejection = bool(market.high[i] >= zone_mid and market.close[i] < zone_mid and market.close[i] <= market.open_[i])
    return sweep, rejection


def no_sniper_row(scenario: pd.Series, status: str, reason: str) -> dict[str, object]:
    return {
        "candidate_id": stable_id("sniper", scenario["scenario_id"], status, reason),
        "scenario_id": str(scenario["scenario_id"]),
        "symbol": str(scenario["symbol"]),
        "decision_timestamp": utc_timestamp(scenario["scenario_built_at"]),
        "scenario_type": str(scenario["scenario_type"]),
        "side": str(scenario["scenario_side"]) if str(scenario["scenario_side"]) in {"long", "short"} else "none",
        "entry_pattern_tier": "reject",
        "sniper_pattern_name": "none",
        "scenario_active_at_trigger": False,
        "approved_htf_pa_zone_id": str(scenario["primary_pa_zone_id"]),
        "approved_htf_pa_zone_source": str(scenario["primary_pa_zone_source"]),
        "htf_trendline_used_for_pa_zone": bool(scenario["htf_trendline_used_for_pa_zone"]),
        "htf_trendline_interaction_type": str(scenario["htf_trendline_interaction_type"]),
        "one_min_trendline_id": "",
        "one_min_trendline_break_confirmed": False,
        "one_min_choch_bos_confirmed": False,
        "one_min_displacement_confirmed": False,
        "one_min_fvg_id": "",
        "one_min_fvg_low": np.nan,
        "one_min_fvg_high": np.nan,
        "one_min_fvg_mid": np.nan,
        "one_min_fvg_created_at": pd.NaT,
        "fvg_created_by_displacement": False,
        "entry_model": "no_entry",
        "entry_price": np.nan,
        "fvg_mid_retest_confirmed": False,
        "one_min_trendline_retest_overlap": False,
        "sweep_reclaim_present": False,
        "trigger_timestamp": pd.NaT,
        "trigger_available_at": pd.NaT,
        "stop_price": np.nan,
        "stop_anchor_type": "none",
        "planned_rr_core_net": np.nan,
        "planned_rr_runner_net": np.nan,
        "sniper_candidate_status": status,
        "sniper_reject_reason": reason,
        "duplicate_suppressed": False,
        "duplicate_group_id": stable_id("dup", scenario["symbol"], scenario["scenario_side"], scenario["primary_pa_zone_id"]),
        "first_trigger_for_scenario": False,
        "scenario_already_triggered": False,
        "zone_reentry_allowed": False,
        "frequency_control_reason": reason,
        "target_pool_built_at": utc_timestamp(scenario["scenario_built_at"]),
        "target_latest_source_close_used": pd.NaT,
        "latest_1m_close_used": pd.NaT,
        "latest_5m_close_used": pd.NaT,
        "latest_15m_close_used": pd.NaT,
        "latest_1h_close_used": pd.NaT,
        "latest_4h_close_used": pd.NaT,
        "lookahead_pass": bool(scenario["lookahead_pass"]),
        "lookahead_violation_reason": "" if bool(scenario["lookahead_pass"]) else "scenario_lookahead_failed",
    }


def construct_sniper_stop(scenario: pd.Series, market, trigger_idx: int, side: str, entry_price: float, sweep_present: bool) -> dict[str, object]:
    zone_low = float(scenario["primary_zone_low"])
    zone_high = float(scenario["primary_zone_high"])
    atr_15 = latest_atr_15m(market, utc_timestamp(scenario["scenario_built_at"]).value)
    atr_15 = atr_15 if atr_15 > 0 else max(entry_price * 0.002, 1e-9)
    start = max(0, trigger_idx - 12)
    local_low = float(np.nanmin(market.low[start : trigger_idx + 1]))
    local_high = float(np.nanmax(market.high[start : trigger_idx + 1]))
    buffer = max(entry_price * 0.0002, atr_15 * 0.06)
    if side == "long":
        if sweep_present:
            anchor_type = "sweep_low"
            anchor = min(local_low, zone_low)
        else:
            anchor_type = "scenario_zone_low"
            anchor = min(zone_low, local_low)
        stop = anchor - buffer
        distance = entry_price - stop
        ordering_ok = stop < entry_price
    else:
        if sweep_present:
            anchor_type = "sweep_high"
            anchor = max(local_high, zone_high)
        else:
            anchor_type = "scenario_zone_high"
            anchor = max(zone_high, local_high)
        stop = anchor + buffer
        distance = stop - entry_price
        ordering_ok = stop > entry_price
    min_distance = max(entry_price * 0.0003, MIN_STOP_ATR * atr_15)
    max_distance = MAX_STOP_ATR * atr_15
    if not ordering_ok:
        valid = False
        reason = "stop_ordering_invalid"
    elif distance <= min_distance:
        valid = False
        reason = "stop_inside_noise_or_spread"
    elif distance >= max_distance:
        valid = False
        reason = "stop_too_wide_for_sniper_rr"
    else:
        valid = True
        reason = "none"
    return {
        "stop_price": float(stop),
        "stop_anchor_type": anchor_type,
        "stop_anchor_price": float(anchor),
        "stop_buffer": float(buffer),
        "stop_distance_abs": float(distance),
        "stop_distance_atr": float(distance / atr_15) if atr_15 > 0 else np.nan,
        "stop_valid": bool(valid),
        "stop_reject_reason": reason,
    }


def latest_atr_15m(market, timestamp_ns: int) -> float:
    bars = market.tf_bars["15m"]
    values = bars["close_time_ns"].to_numpy(dtype="int64")
    pos = int(np.searchsorted(values, timestamp_ns, side="right")) - 1
    if pos < 0:
        return np.nan
    return float(bars.iloc[pos]["atr"])


def classify_pattern(
    sweep_or_rejection: bool,
    trendline_break: bool,
    choch_bos: bool,
    displacement: bool,
    fvg_created: bool,
    trendline_overlap: bool,
) -> tuple[str, str, str]:
    if fvg_created and displacement and (trendline_break or choch_bos):
        if sweep_or_rejection and (trendline_overlap or (trendline_break and choch_bos)):
            return "S_tier_sniper", "sniper_fvg_mid_after_sweep_or_rejection_with_1m_structure_shift", "accepted_headline"
        return "A_tier_sniper", "sniper_fvg_mid_after_1m_structure_shift", "accepted_headline"
    if sweep_or_rejection and not fvg_created:
        return "B_tier_context", "sweep_reclaim_only", "research_only"
    if trendline_break and not fvg_created:
        return "B_tier_context", "one_min_trendline_break_without_fvg", "research_only"
    return "reject", "none", "rejected"


def scan_scenario_for_sniper(
    scenario: pd.Series,
    market,
    structure: OneMinuteStructure,
    target_summary_row: pd.Series | None,
    target_lookup: dict[str, dict[str, object]],
) -> dict[str, object]:
    side = str(scenario["scenario_side"])
    if side not in {"long", "short"}:
        return no_sniper_row(scenario, "rejected", "no_directional_active_scenario")
    if str(scenario["scenario_activation_state"]) not in {"active", "approaching"}:
        return no_sniper_row(scenario, "rejected", "no_active_scenario")
    if not bool(scenario["target_path_available"]):
        return no_sniper_row(scenario, "rejected", "no_structural_target_path")

    scenario_ts = utc_timestamp(scenario["scenario_built_at"])
    start_ns = scenario_ts.value
    end_ns = (scenario_ts + pd.Timedelta(minutes=SNIPER_SEARCH_MINUTES)).value
    start = int(np.searchsorted(market.close_ns_1m, start_ns, side="right"))
    end = int(np.searchsorted(market.close_ns_1m, end_ns, side="right"))
    if start >= end:
        return no_sniper_row(scenario, "rejected", "no_1m_bars_inside_sniper_window")

    zone_low = float(scenario["primary_zone_low"])
    zone_high = float(scenario["primary_zone_high"])
    zone_mid = float(scenario["primary_zone_mid"])
    reference_price = float(scenario["reference_price"])
    atr_15 = latest_atr_15m(market, start_ns)
    atr_15 = atr_15 if pd.notna(atr_15) and atr_15 > 0 else max(reference_price * 0.002, 1e-9)
    tolerance = max(0.06 * atr_15, 0.0005 * reference_price)
    zone_touch_idx = -1
    zone_touch_ns = None
    best_b_tier: dict[str, object] | None = None

    for i in range(start, end):
        low_i = float(market.low[i])
        high_i = float(market.high[i])
        close_i = float(market.close[i])
        close_ns = int(market.close_ns_1m[i])
        inside_zone = overlaps_zone(low_i, high_i, zone_low, zone_high, tolerance)
        if inside_zone:
            zone_touch_idx = i
            zone_touch_ns = close_ns
        if zone_touch_idx < 0:
            if directional_move(side, close_i, reference_price) > MAX_CHASE_ATR * atr_15:
                return no_sniper_row(scenario, "rejected", "market_chase_before_zone_touch")
            continue
        if close_ns - int(zone_touch_ns) > POST_ZONE_TRIGGER_MINUTES * 60 * 1_000_000_000:
            return no_sniper_row(scenario, "rejected", "no_sniper_trigger_after_zone_touch")
        if directional_move(side, close_i, reference_price) > MAX_CHASE_ATR * atr_15 and not inside_zone:
            return no_sniper_row(scenario, "rejected", "market_chase_after_zone_touch")

        sweep, rejection = zone_reaction_state(market, i, side, zone_low, zone_high, zone_mid)
        sweep_or_rejection = bool(sweep or rejection)
        tl_state = one_min_trendline_state(market, structure, i, side)
        choch_bos = one_min_choch_bos(market, structure, i, side)
        fvg = displacement_and_fvg(market, i, side)
        trendline_overlap = (
            bool(fvg["fvg_created_by_displacement"])
            and pd.notna(tl_state["projected_price"])
            and abs(float(fvg["one_min_fvg_mid"]) - float(tl_state["projected_price"])) <= max(float(tl_state["line_tolerance"]) * 1.5, atr_15 * 0.05)
        )
        tier, pattern_name, pattern_status = classify_pattern(
            sweep_or_rejection,
            bool(tl_state["one_min_trendline_break_confirmed"]),
            bool(choch_bos),
            bool(fvg["one_min_displacement_confirmed"]),
            bool(fvg["fvg_created_by_displacement"]),
            bool(trendline_overlap),
        )
        if tier == "reject":
            continue
        if pattern_status == "research_only" and best_b_tier is None:
            best_b_tier = {
                "tier": tier,
                "pattern_name": pattern_name,
                "i": i,
                "close_ns": close_ns,
                "sweep": sweep,
                "rejection": rejection,
                "tl_state": tl_state,
                "choch_bos": choch_bos,
                "fvg": fvg,
                "trendline_overlap": trendline_overlap,
            }
            continue
        if pattern_status != "accepted_headline":
            continue

        entry_price = float(fvg["one_min_fvg_mid"])
        stop = construct_sniper_stop(scenario, market, i, side, entry_price, bool(sweep))
        trigger = {
            "entry_model": "limit_fvg_mid",
            "entry_price": entry_price,
            "trigger_available_at": ns_to_utc(close_ns),
            "latest_1m_close_used": ns_to_utc(close_ns),
            "latest_5m_close_used": latest_tf_close(market.tf_bars["5m"], close_ns),
        }
        if not stop["stop_valid"]:
            return build_sniper_row(
                scenario,
                market,
                i,
                side,
                tier,
                pattern_name,
                "rejected",
                f"stop_unrelated_or_invalid:{stop['stop_reject_reason']}",
                tl_state,
                choch_bos,
                fvg,
                trendline_overlap,
                bool(sweep),
                trigger,
                stop,
                None,
            )
        targets = combine_targets_and_rr(
            pd.Series({"side": side, "decision_timestamp": scenario_ts}),
            target_summary_row,
            target_lookup,
            trigger,
            {"stop_valid": stop["stop_valid"], "stop_distance_abs": stop["stop_distance_abs"]},
        )
        if bool(targets["fixed_r_primary_target"]):
            status = "rejected"
            reason = "fixed_R_only_target"
        elif not bool(targets["structural_target_used"]):
            status = "rejected"
            reason = "no_structural_target"
        elif pd.isna(targets["planned_rr_core_net"]) or float(targets["planned_rr_core_net"]) < MIN_CORE_RR_NET:
            status = "rejected"
            reason = "planned_core_rr_net_below_3r"
        else:
            status = "accepted_headline"
            reason = "none"
        return build_sniper_row(
            scenario,
            market,
            i,
            side,
            tier,
            pattern_name,
            status,
            reason,
            tl_state,
            choch_bos,
            fvg,
            trendline_overlap,
            bool(sweep),
            trigger,
            stop,
            targets,
        )

    if best_b_tier is not None:
        event = best_b_tier
        trigger = {
            "entry_model": "no_entry",
            "entry_price": np.nan,
            "trigger_available_at": ns_to_utc(event["close_ns"]),
            "latest_1m_close_used": ns_to_utc(event["close_ns"]),
            "latest_5m_close_used": latest_tf_close(market.tf_bars["5m"], event["close_ns"]),
        }
        empty_stop = {
            "stop_price": np.nan,
            "stop_anchor_type": "none",
            "stop_anchor_price": np.nan,
            "stop_buffer": np.nan,
            "stop_distance_abs": np.nan,
            "stop_distance_atr": np.nan,
            "stop_valid": False,
            "stop_reject_reason": "research_bucket_no_fvg_mid_entry",
        }
        return build_sniper_row(
            scenario,
            market,
            event["i"],
            side,
            event["tier"],
            event["pattern_name"],
            "research_only",
            event["pattern_name"],
            event["tl_state"],
            event["choch_bos"],
            event["fvg"],
            event["trendline_overlap"],
            bool(event["sweep"]),
            trigger,
            empty_stop,
            None,
        )
    return no_sniper_row(scenario, "rejected", "no_1m_fvg_after_structure_shift_inside_active_scenario")


def build_sniper_row(
    scenario: pd.Series,
    market,
    trigger_idx: int,
    side: str,
    tier: str,
    pattern_name: str,
    status: str,
    reason: str,
    tl_state: dict[str, object],
    choch_bos: bool,
    fvg: dict[str, object],
    trendline_overlap: bool,
    sweep_present: bool,
    trigger: dict[str, object],
    stop: dict[str, object],
    targets: dict[str, object] | None,
) -> dict[str, object]:
    close_ns = int(market.close_ns_1m[trigger_idx]) if trigger_idx >= 0 else None
    scenario_ts = utc_timestamp(scenario["scenario_built_at"])
    latest_15m = latest_tf_close(market.tf_bars["15m"], scenario_ts.value)
    latest_1h = latest_tf_close(market.tf_bars["1h"], scenario_ts.value)
    latest_4h = latest_tf_close(market.tf_bars["4h"], scenario_ts.value)
    if targets is None:
        targets = {
            "planned_rr_core_net": np.nan,
            "planned_rr_runner_net": np.nan,
            "target_pool_built_at": scenario_ts,
            "target_latest_source_close_used": pd.NaT,
        }
    trigger_available = trigger["trigger_available_at"]
    latest_1m = trigger["latest_1m_close_used"]
    latest_5m = trigger["latest_5m_close_used"]
    search_end = scenario_ts + pd.Timedelta(minutes=SNIPER_SEARCH_MINUTES)
    lookahead_checks = [
        bool(scenario["lookahead_pass"]),
        pd.isna(trigger_available) or (scenario_ts < trigger_available <= search_end),
        pd.isna(latest_1m) or pd.isna(trigger_available) or latest_1m <= trigger_available,
        pd.isna(latest_5m) or pd.isna(trigger_available) or latest_5m <= trigger_available,
        pd.isna(latest_15m) or latest_15m <= scenario_ts,
        pd.isna(latest_1h) or latest_1h <= scenario_ts,
        pd.isna(latest_4h) or latest_4h <= scenario_ts,
        pd.isna(targets["target_pool_built_at"]) or targets["target_pool_built_at"] <= scenario_ts,
        pd.isna(targets["target_latest_source_close_used"]) or targets["target_latest_source_close_used"] <= scenario_ts,
        pd.isna(fvg["one_min_fvg_created_at"]) or fvg["one_min_fvg_created_at"] <= trigger_available,
    ]
    lookahead_pass = all(bool(value) for value in lookahead_checks)
    if not lookahead_pass:
        status = "rejected"
        reason = "lookahead_violation"
    return {
        "candidate_id": stable_id("sniper", scenario["scenario_id"], tier, trigger_available, side),
        "scenario_id": str(scenario["scenario_id"]),
        "symbol": str(scenario["symbol"]),
        "decision_timestamp": scenario_ts,
        "scenario_type": str(scenario["scenario_type"]),
        "side": side,
        "entry_pattern_tier": tier,
        "sniper_pattern_name": pattern_name,
        "scenario_active_at_trigger": bool(str(scenario["scenario_activation_state"]) in {"active", "approaching"}),
        "approved_htf_pa_zone_id": str(scenario["primary_pa_zone_id"]),
        "approved_htf_pa_zone_source": str(scenario["primary_pa_zone_source"]),
        "htf_trendline_used_for_pa_zone": bool(scenario["htf_trendline_used_for_pa_zone"]),
        "htf_trendline_interaction_type": str(scenario["htf_trendline_interaction_type"]),
        "one_min_trendline_id": str(tl_state["one_min_trendline_id"]),
        "one_min_trendline_break_confirmed": bool(tl_state["one_min_trendline_break_confirmed"]),
        "one_min_choch_bos_confirmed": bool(choch_bos),
        "one_min_displacement_confirmed": bool(fvg["one_min_displacement_confirmed"]),
        "one_min_fvg_id": str(fvg["one_min_fvg_id"]),
        "one_min_fvg_low": float(fvg["one_min_fvg_low"]) if pd.notna(fvg["one_min_fvg_low"]) else np.nan,
        "one_min_fvg_high": float(fvg["one_min_fvg_high"]) if pd.notna(fvg["one_min_fvg_high"]) else np.nan,
        "one_min_fvg_mid": float(fvg["one_min_fvg_mid"]) if pd.notna(fvg["one_min_fvg_mid"]) else np.nan,
        "one_min_fvg_created_at": fvg["one_min_fvg_created_at"],
        "fvg_created_by_displacement": bool(fvg["fvg_created_by_displacement"]),
        "entry_model": "limit_fvg_mid" if tier in {"S_tier_sniper", "A_tier_sniper"} and status != "rejected" else "no_entry",
        "entry_price": trigger["entry_price"],
        "fvg_mid_retest_confirmed": False,
        "one_min_trendline_retest_overlap": bool(trendline_overlap),
        "sweep_reclaim_present": bool(sweep_present),
        "trigger_timestamp": ns_to_utc(close_ns) if close_ns is not None else pd.NaT,
        "trigger_available_at": trigger_available,
        "stop_price": stop["stop_price"],
        "stop_anchor_type": stop["stop_anchor_type"],
        "planned_rr_core_net": targets["planned_rr_core_net"],
        "planned_rr_runner_net": targets["planned_rr_runner_net"],
        "sniper_candidate_status": status,
        "sniper_reject_reason": reason,
        "duplicate_suppressed": False,
        "duplicate_group_id": stable_id("dup", scenario["symbol"], side, scenario["primary_pa_zone_id"]),
        "first_trigger_for_scenario": bool(status == "accepted_headline"),
        "scenario_already_triggered": False,
        "zone_reentry_allowed": bool(status == "accepted_headline"),
        "frequency_control_reason": "first_valid_sniper_for_scenario" if status == "accepted_headline" else reason,
        "target_pool_built_at": targets["target_pool_built_at"],
        "target_latest_source_close_used": targets["target_latest_source_close_used"],
        "latest_1m_close_used": latest_1m,
        "latest_5m_close_used": latest_5m,
        "latest_15m_close_used": latest_15m,
        "latest_1h_close_used": latest_1h,
        "latest_4h_close_used": latest_4h,
        "lookahead_pass": bool(lookahead_pass),
        "lookahead_violation_reason": "" if lookahead_pass else "source_time_after_scenario_or_trigger_window",
    }


def apply_frequency_control(candidates: pd.DataFrame) -> pd.DataFrame:
    out = candidates.sort_values(["symbol", "trigger_available_at", "scenario_id"]).copy().reset_index(drop=True)
    last_by_group: dict[str, pd.Timestamp] = {}
    triggered_scenarios: set[str] = set()
    for idx, row in out.iterrows():
        if row["sniper_candidate_status"] != "accepted_headline":
            continue
        scenario_id = str(row["scenario_id"])
        group_id = str(row["duplicate_group_id"])
        trigger_at = utc_timestamp(row["trigger_available_at"])
        if scenario_id in triggered_scenarios:
            out.at[idx, "sniper_candidate_status"] = "duplicate_suppressed"
            out.at[idx, "duplicate_suppressed"] = True
            out.at[idx, "first_trigger_for_scenario"] = False
            out.at[idx, "scenario_already_triggered"] = True
            out.at[idx, "zone_reentry_allowed"] = False
            out.at[idx, "frequency_control_reason"] = "scenario_already_triggered"
            continue
        if group_id in last_by_group:
            minutes = (trigger_at - last_by_group[group_id]).total_seconds() / 60.0
            if minutes < DUPLICATE_SUPPRESSION_MINUTES:
                out.at[idx, "sniper_candidate_status"] = "duplicate_suppressed"
                out.at[idx, "duplicate_suppressed"] = True
                out.at[idx, "first_trigger_for_scenario"] = False
                out.at[idx, "scenario_already_triggered"] = False
                out.at[idx, "zone_reentry_allowed"] = False
                out.at[idx, "frequency_control_reason"] = f"same_zone_reentry_within_{DUPLICATE_SUPPRESSION_MINUTES}m"
                continue
        triggered_scenarios.add(scenario_id)
        last_by_group[group_id] = trigger_at
    return out.sort_values(["symbol", "decision_timestamp", "side"]).reset_index(drop=True)


def build_candidates(symbols: list[str]) -> pd.DataFrame:
    scenarios = pd.read_parquet(SCENARIO_PARQUET)
    scenarios = scenarios[scenarios["symbol"].isin(symbols)].copy()
    scenarios["scenario_built_at"] = pd.to_datetime(scenarios["scenario_built_at"], utc=True)
    markets = {symbol: load_market_data(symbol) for symbol in symbols}
    structures = {symbol: build_1m_structure(markets[symbol]) for symbol in symbols}
    target_summary = load_target_summary(symbols)
    target_summary_index = target_summary.set_index(["symbol", "decision_timestamp", "side"])
    target_lookup = load_target_lookup()

    rows = []
    total = len(scenarios)
    for idx, scenario in enumerate(scenarios.itertuples(index=False), 1):
        if idx == 1 or idx % 1000 == 0:
            print(f"  sniper scenarios={idx}/{total}", flush=True)
        scenario_s = pd.Series(scenario._asdict())
        symbol = str(scenario_s["symbol"])
        side = str(scenario_s["scenario_side"])
        try:
            summary_row = target_summary_index.loc[(symbol, utc_timestamp(scenario_s["scenario_built_at"]), side)]
        except KeyError:
            summary_row = None
        rows.append(scan_scenario_for_sniper(scenario_s, markets[symbol], structures[symbol], summary_row, target_lookup))
    return apply_frequency_control(pd.DataFrame(rows))


def build_audit(candidates: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "candidate_id",
        "scenario_id",
        "symbol",
        "decision_timestamp",
        "side",
        "sniper_candidate_status",
        "trigger_available_at",
        "one_min_fvg_created_at",
        "latest_1m_close_used",
        "latest_5m_close_used",
        "latest_15m_close_used",
        "latest_1h_close_used",
        "latest_4h_close_used",
        "target_pool_built_at",
        "target_latest_source_close_used",
        "lookahead_pass",
        "lookahead_violation_reason",
    ]
    audit = candidates[cols].copy()
    for column in [
        "decision_timestamp",
        "trigger_available_at",
        "one_min_fvg_created_at",
        "latest_1m_close_used",
        "latest_5m_close_used",
        "latest_15m_close_used",
        "latest_1h_close_used",
        "latest_4h_close_used",
        "target_pool_built_at",
        "target_latest_source_close_used",
    ]:
        audit[column] = pd.to_datetime(audit[column], utc=True, errors="coerce")
    trigger_exists = audit["trigger_available_at"].notna()
    search_end = audit["decision_timestamp"] + pd.Timedelta(minutes=SNIPER_SEARCH_MINUTES)
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
                & (audit["trigger_available_at"] <= search_end)
                & (audit["one_min_fvg_created_at"].isna() | (audit["one_min_fvg_created_at"] <= audit["trigger_available_at"]))
                & (audit["latest_1m_close_used"].isna() | (audit["latest_1m_close_used"] <= audit["trigger_available_at"]))
                & (audit["latest_5m_close_used"].isna() | (audit["latest_5m_close_used"] <= audit["trigger_available_at"]))
            )
        )
    )
    audit["lookahead_pass"] = lookahead.astype(bool)
    audit.loc[audit["lookahead_pass"], "lookahead_violation_reason"] = ""
    audit.loc[~audit["lookahead_pass"], "lookahead_violation_reason"] = "source_time_after_scenario_or_trigger_window"
    return audit


def pct(mask: pd.Series, denominator: int) -> float:
    return float(mask.sum() / denominator * 100.0) if denominator else 0.0


def rr_stats(series: pd.Series, metric: str) -> list[dict[str, object]]:
    values = series.dropna()
    if values.empty:
        return []
    return [
        {
            "metric": metric,
            "p25": round(float(values.quantile(0.25)), 3),
            "median": round(float(values.quantile(0.50)), 3),
            "p75": round(float(values.quantile(0.75)), 3),
            "p90": round(float(values.quantile(0.90)), 3),
            "p99": round(float(values.quantile(0.99)), 3),
        }
    ]


def write_report(candidates: pd.DataFrame, audit: pd.DataFrame, symbols: list[str]) -> None:
    broad = pd.read_parquet(
        BROAD_TRADE_CANDIDATES_PARQUET,
        columns=["candidate_status", "entry_trigger_type", "entry_model", "symbol", "side"],
    )
    broad_accepted = broad[broad["candidate_status"].eq("accepted")]
    headline = candidates[candidates["sniper_candidate_status"].eq("accepted_headline")]
    s_tier = headline[headline["entry_pattern_tier"].eq("S_tier_sniper")]
    a_tier = headline[headline["entry_pattern_tier"].eq("A_tier_sniper")]
    research = candidates[candidates["sniper_candidate_status"].eq("research_only")]
    rejected = candidates[candidates["sniper_candidate_status"].eq("rejected")]
    duplicate = candidates[candidates["sniper_candidate_status"].eq("duplicate_suppressed")]
    source_calendar = pd.read_parquet(THESIS_PARQUET, columns=["symbol", "decision_timestamp"])
    source_calendar = source_calendar[source_calendar["symbol"].isin(symbols)].copy()
    source_calendar["decision_timestamp"] = pd.to_datetime(source_calendar["decision_timestamp"], utc=True)
    source_calendar["source_date_utc"] = (source_calendar["decision_timestamp"] - pd.Timedelta(minutes=1)).dt.date
    calendar_days = max(1, source_calendar["source_date_utc"].nunique())
    source_date_min = str(source_calendar["source_date_utc"].min()) if len(source_calendar) else ""
    source_date_max = str(source_calendar["source_date_utc"].max()) if len(source_calendar) else ""
    status_counts = candidates["sniper_candidate_status"].value_counts().reset_index()
    status_counts.columns = ["sniper_candidate_status", "rows"]
    tier_counts = candidates["entry_pattern_tier"].value_counts().reset_index()
    tier_counts.columns = ["entry_pattern_tier", "rows"]
    symbol_side = headline.groupby(["symbol", "side"]).size().reset_index(name="headline_rows")
    entry_model = candidates["entry_model"].value_counts().reset_index()
    entry_model.columns = ["entry_model", "rows"]
    reject_counts = candidates.loc[candidates["sniper_candidate_status"].ne("accepted_headline"), "sniper_reject_reason"].value_counts().head(20).reset_index()
    reject_counts.columns = ["sniper_reject_reason", "rows"]
    trigger_only_downgraded = int((research["sniper_pattern_name"] == "one_min_trendline_break_without_fvg").sum())
    sweep_only_downgraded = int((research["sniper_pattern_name"] == "sweep_reclaim_only").sum())
    broad_trendline_accepted = int((broad_accepted["entry_trigger_type"] == "trendline_retest_rejection").sum())
    broad_sweep_accepted = int((broad_accepted["entry_trigger_type"] == "1m_sweep_reclaim").sum())
    violations = int((~audit["lookahead_pass"]).sum())
    headline_count = len(headline)
    fvg_mid_ratio = pct(headline["entry_model"].eq("limit_fvg_mid"), headline_count)
    one_min_tl_ratio = pct(headline["one_min_trendline_break_confirmed"], headline_count)
    choch_ratio = pct(headline["one_min_choch_bos_confirmed"], headline_count)
    displacement_ratio = pct(headline["one_min_displacement_confirmed"], headline_count)
    htf_tl_ratio = pct(headline["htf_trendline_used_for_pa_zone"], headline_count)
    lines = [
        "# Craig v1.2.1 Sniper Trade Candidate Report",
        "",
        "Generated by `scripts/build_craig_v1_2_sniper_trade_candidates.py`.",
        "",
        "## Verdict",
        "",
        "- Existing v1.2 broad trade candidates were preserved and are used only for comparison.",
        "- v1.2.1 headline candidates consume scenario thesis rows, then require 1m structure shift, displacement, and displacement-created 1m FVG midpoint entry.",
        "- HTF/15m trendline remains PA/scenario context; 1m trendline break/CHoCH is the entry permission layer.",
        "- `confirmation_market`, `trendline_retest_rejection only`, and `sweep_reclaim only` are not headline sniper candidates.",
        "- This stage does not simulate fills, stop hits, target hits, partial exits, runner outcome, PnL, gold labels, Craig action, result R, or optimization.",
        f"- Lookahead violations: {violations}.",
        "",
        "## v1.2 vs v1.2.1 Frequency",
        "",
        f"- Existing v1.2 accepted count: {len(broad_accepted)}",
        f"- Previous v1.2.1 scenario rows before this refinement: {PRE_REFINEMENT_SCENARIO_ROWS}",
        f"- Previous v1.2.1 S/A headline count before this refinement: {PRE_REFINEMENT_SNIPER_HEADLINE_ROWS}",
        f"- Previous v1.2.1 S-tier/A-tier before this refinement: {PRE_REFINEMENT_SNIPER_S_TIER_ROWS} / {PRE_REFINEMENT_SNIPER_A_TIER_ROWS}",
        f"- v1.2.1 S-tier count: {len(s_tier)}",
        f"- v1.2.1 A-tier count: {len(a_tier)}",
        f"- v1.2.1 S/A headline count delta: {headline_count - PRE_REFINEMENT_SNIPER_HEADLINE_ROWS}",
        f"- v1.2.1 B-tier/research count: {len(research)}",
        f"- v1.2.1 duplicate-suppressed count: {len(duplicate)}",
        f"- v1.2.1 rejected count: {len(rejected)}",
        f"- v1.2.1 source-date range UTC: {source_date_min} to {source_date_max}",
        f"- Average S/A-tier headline candidates per UTC day across {', '.join(symbols)}: {headline_count / calendar_days:.3f}",
        "",
        "## Candidate Status Distribution",
        "",
        *markdown_table(status_counts.to_dict("records"), ["sniper_candidate_status", "rows"]),
        "",
        "## Detected Entry Pattern Tier Distribution Before Final Gates",
        "",
        *markdown_table(tier_counts.to_dict("records"), ["entry_pattern_tier", "rows"]),
        "",
        "## Symbol And Side Distribution",
        "",
        *markdown_table(symbol_side.to_dict("records"), ["symbol", "side", "headline_rows"]),
        "",
        "## Entry Model Distribution",
        "",
        *markdown_table(entry_model.to_dict("records"), ["entry_model", "rows"]),
        "",
        "## Sniper DNA Ratios",
        "",
        f"- limit_fvg_mid ratio among headline S/A: {fvg_mid_ratio:.3f}%",
        f"- 1m FVG midpoint entry ratio among headline S/A: {fvg_mid_ratio:.3f}%",
        f"- 1m trendline break included among headline S/A: {one_min_tl_ratio:.3f}%",
        f"- 1m CHoCH/BOS included among headline S/A: {choch_ratio:.3f}%",
        f"- 1m displacement included among headline S/A: {displacement_ratio:.3f}%",
        f"- Previous headline HTF trendline PA scenario ratio: {PRE_REFINEMENT_HTF_TRENDLINE_HEADLINE_PCT:.3f}%",
        f"- HTF trendline PA scenario ratio among headline S/A: {htf_tl_ratio:.3f}%",
        "",
        "## Downgrade Checks",
        "",
        f"- v1.2 accepted `trendline_retest_rejection`: {broad_trendline_accepted}",
        f"- v1.2.1 trendline-break/retest-without-FVG research-only rows: {trigger_only_downgraded}",
        f"- v1.2 accepted `1m_sweep_reclaim`: {broad_sweep_accepted}",
        f"- v1.2.1 sweep/reclaim-without-FVG research-only rows: {sweep_only_downgraded}",
        "",
        "## Reject / Research Reasons",
        "",
        *markdown_table(reject_counts.to_dict("records"), ["sniper_reject_reason", "rows"]),
        "",
        "## Planned Core RR Net",
        "",
        *markdown_table(rr_stats(headline["planned_rr_core_net"], "headline_planned_rr_core_net"), ["metric", "p25", "median", "p75", "p90", "p99"]),
        "",
        "## Planned Runner RR Net",
        "",
        *markdown_table(rr_stats(headline["planned_rr_runner_net"], "headline_planned_rr_runner_net"), ["metric", "p25", "median", "p75", "p90", "p99"]),
        "",
        "## Frequency Control",
        "",
        f"- Duplicate suppression window: {DUPLICATE_SUPPRESSION_MINUTES} minutes.",
        "- Same symbol/scenario keeps only the first valid S/A trigger.",
        "- Same symbol/side/primary PA zone repeated inside the suppression window is marked `duplicate_suppressed`.",
        "",
        "## No-Lookahead Controls",
        "",
        f"- 1m sniper search is restricted to {SNIPER_SEARCH_MINUTES} minutes after `scenario_built_at`.",
        f"- After zone touch, 1m structure/FVG must appear within {POST_ZONE_TRIGGER_MINUTES} minutes.",
        "- 1m trendline anchors use only causally confirmed 1m swing highs/lows.",
        "- The candidate is created at 1m FVG creation close; FVG midpoint is an order price for the later simulator, not a simulated fill.",
        "- Target source closes must remain at or before the scenario timestamp.",
        "",
        "## Output Paths",
        "",
        f"- Sniper candidates: `{OUT_CANDIDATES.relative_to(ROOT)}`",
        f"- Audit CSV: `{OUT_AUDIT.relative_to(ROOT)}`",
        "",
        "## Next Step Recommendation",
        "",
        "Build the event-driven execution simulator against v1.2.1 S/A-tier sniper candidates only. The simulator should consume `sniper_candidate_status=accepted_headline`, place the FVG-mid limit after `trigger_available_at`, model expiry/no-chase cancellation, then walk 1m candles for fill/stop/TP1/core/runner state transitions with a conservative same-candle ambiguity rule.",
    ]
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=HEADLINE_SYMBOLS)
    args = parser.parse_args()
    symbols = [symbol.upper() for symbol in args.symbols]
    candidates = build_candidates(symbols)
    audit = build_audit(candidates)
    if not audit["lookahead_pass"].all():
        raise RuntimeError(f"Sniper candidate lookahead audit failed for {int((~audit['lookahead_pass']).sum())} rows")
    OUT_CANDIDATES.parent.mkdir(parents=True, exist_ok=True)
    candidates.to_parquet(OUT_CANDIDATES, index=False)
    audit.to_csv(OUT_AUDIT, index=False, encoding="utf-8-sig")
    write_report(candidates, audit, symbols)
    print(f"sniper_candidates={OUT_CANDIDATES} rows={len(candidates)}")
    print(f"audit={OUT_AUDIT} rows={len(audit)} lookahead_pass={int(audit['lookahead_pass'].sum())}/{len(audit)}")
    print(f"report={OUT_REPORT}")


if __name__ == "__main__":
    main()
