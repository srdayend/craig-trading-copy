#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BTC_1M_PARQUET = (
    ROOT
    / "data/processed/binance_futures_continuous/BTCUSDT/1m/BTCUSDT_1m_2024-01-01_2026-08-23.parquet"
)
HTF_ZONES_PARQUET = ROOT / "outputs/craig_v1_2_htf_zones.parquet"
TRENDLINE_ZONES_PARQUET = ROOT / "outputs/craig_v1_2_trendline_zones.parquet"
OUT_SNAPSHOTS = ROOT / "outputs/craig_v1_2_btc_context_snapshots.parquet"
OUT_AUDIT = ROOT / "outputs/craig_v1_2_btc_context_audit.csv"
OUT_REPORT = ROOT / "outputs/craig_v1_2_btc_context_build_report.md"

TIMEFRAME_MINUTES = {"15m": 15, "1h": 60, "4h": 240}
RESAMPLE_RULES = {"15m": "15T", "1h": "1H", "4h": "4H"}
TIMEFRAME_PRIORITY = {"4h": 0, "1h": 1, "15m": 2}
TIMEFRAME_SCORE_BONUS = {"4h": 0.18, "1h": 0.12, "15m": 0.06}
ZONE_LOOKBACK = {"15m": pd.Timedelta(days=14), "1h": pd.Timedelta(days=60), "4h": pd.Timedelta(days=240)}
ZONE_TAIL_SCAN = {"15m": 180, "1h": 140, "4h": 120}
TRENDLINE_EVENT_MAX_AGE = {
    "near_touch": {"15m": pd.Timedelta(minutes=30), "1h": pd.Timedelta(hours=2), "4h": pd.Timedelta(hours=8)},
    "rejection": {"15m": pd.Timedelta(hours=2), "1h": pd.Timedelta(hours=8), "4h": pd.Timedelta(hours=24)},
    "sweep": {"15m": pd.Timedelta(hours=2), "1h": pd.Timedelta(hours=8), "4h": pd.Timedelta(hours=24)},
    "clean_break": {"15m": pd.Timedelta(hours=4), "1h": pd.Timedelta(hours=12), "4h": pd.Timedelta(hours=48)},
    "break_retest": {"15m": pd.Timedelta(hours=4), "1h": pd.Timedelta(hours=12), "4h": pd.Timedelta(hours=48)},
}
ATR_PERIOD = 14

ALLOWED_CONTEXT_EFFECTS = {"confirm", "warn", "veto", "neutral"}
ALLOWED_REACTION_STATES = {
    "bullish_rejection",
    "bearish_rejection",
    "bullish_acceptance",
    "bearish_acceptance",
    "chop_no_decision",
    "liquidity_sweep_reclaim",
    "liquidity_sweep_fail",
    "none",
}
ALLOWED_INTERACTIONS = {"near_touch", "sweep", "break_retest", "rejection", "clean_break", "none"}


@dataclass(frozen=True)
class ZoneCandidate:
    object_id: str
    object_type: str
    source: str
    timeframe: str
    kind: str
    side: str
    zone_low: float
    zone_high: float
    zone_mid: float
    distance_atr: float
    available_at: pd.Timestamp
    latest_source_candle_close_used: pd.Timestamp


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


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
    bars["bar_index"] = np.arange(len(bars))
    bars["atr"] = compute_atr(bars)
    bars["body_atr"] = (bars["close"] - bars["open"]).abs() / bars["atr"].replace(0, np.nan)
    bars["return_4bar"] = bars["close"].pct_change(4)
    return bars


def load_btc_bars(path: Path) -> dict[str, pd.DataFrame]:
    df = pd.read_parquet(path)
    df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    for column in ["open", "high", "low", "close", "volume"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["timestamp", "open", "high", "low", "close"]).sort_values("timestamp")
    df = df.drop_duplicates("timestamp", keep="last").reset_index(drop=True)
    return {timeframe: resample_ohlcv(df, timeframe) for timeframe in ["15m", "1h", "4h"]}


def object_kind(object_type: str, timeframe: str) -> str:
    if object_type.startswith("fvg_"):
        return f"{timeframe}_fvg"
    if object_type.startswith("sr_"):
        return f"{timeframe}_sr_zone"
    if object_type.startswith("liquidity_"):
        return "liquidity_pool"
    if object_type.startswith("current_day_"):
        return "day_high_low"
    if object_type.startswith("previous_day_"):
        return "previous_day_high_low"
    if object_type.startswith("swing_"):
        return f"{timeframe}_swing"
    if object_type == "trendline" or object_type == "trendline_interaction":
        return f"{timeframe}_trendline"
    return "none"


def source_priority(object_type: str) -> int:
    if object_type == "trendline_interaction":
        return 0
    if object_type.startswith("liquidity_"):
        return 1
    if object_type.startswith("sr_"):
        return 2
    if object_type.startswith("fvg_"):
        return 3
    if object_type.startswith("previous_day_") or object_type.startswith("current_day_"):
        return 4
    if object_type.startswith("swing_"):
        return 5
    return 9


def distance_to_zone_atr(price: float, zone_low: float, zone_high: float, atr: float) -> float:
    if not np.isfinite(atr) or atr <= 0:
        return float("inf")
    if zone_low <= price <= zone_high:
        return 0.0
    return min(abs(price - zone_low), abs(price - zone_high)) / atr


def prepare_zone_groups(htf_zones: pd.DataFrame) -> dict[str, tuple[pd.DataFrame, np.ndarray]]:
    btc = htf_zones[htf_zones["symbol"].eq("BTCUSDT")].copy()
    btc["available_at"] = pd.to_datetime(btc["available_at"], utc=True)
    btc["latest_source_candle_close_used"] = pd.to_datetime(btc["latest_source_candle_close_used"], utc=True)
    groups: dict[str, tuple[pd.DataFrame, np.ndarray]] = {}
    for timeframe, group in btc.groupby("timeframe"):
        group = group.sort_values("available_at").reset_index(drop=True)
        groups[timeframe] = (group, group["available_at"].values)
    return groups


def prepare_trendline_events(trendline_zones: pd.DataFrame) -> pd.DataFrame:
    events = trendline_zones[
        trendline_zones["symbol"].eq("BTCUSDT")
        & trendline_zones["object_type"].eq("trendline_interaction")
        & trendline_zones["trendline_interaction_type"].isin(ALLOWED_INTERACTIONS - {"none"})
    ].copy()
    if events.empty:
        return events
    events["available_at"] = pd.to_datetime(events["available_at"], utc=True)
    events["latest_source_candle_close_used"] = pd.to_datetime(events["latest_source_candle_close_used"], utc=True)
    return events.sort_values("available_at").reset_index(drop=True)


def latest_trendline_event(events: pd.DataFrame, decision_timestamp: pd.Timestamp) -> dict[str, object] | None:
    if events.empty:
        return None
    pos = int(np.searchsorted(events["available_at"].values, decision_timestamp.to_datetime64(), side="right"))
    if pos <= 0:
        return None
    for _, event in events.iloc[max(0, pos - 20) : pos].iloc[::-1].iterrows():
        interaction = str(event.get("trendline_interaction_type", "none"))
        timeframe = str(event.get("timeframe", "15m"))
        max_age = TRENDLINE_EVENT_MAX_AGE.get(interaction, {}).get(timeframe, pd.Timedelta(hours=1))
        age = decision_timestamp - pd.Timestamp(event["available_at"])
        if age <= max_age:
            return event.to_dict()
    return None


def nearest_zone(
    zone_groups: dict[str, tuple[pd.DataFrame, np.ndarray]],
    decision_timestamp: pd.Timestamp,
    price: float,
    atr_by_tf: dict[str, float],
    trendline_event: dict[str, object] | None,
) -> ZoneCandidate | None:
    candidates: list[ZoneCandidate] = []
    for timeframe, (zones, available_values) in zone_groups.items():
        pos = int(np.searchsorted(available_values, decision_timestamp.to_datetime64(), side="right"))
        if pos <= 0:
            continue
        recent = zones.iloc[max(0, pos - ZONE_TAIL_SCAN.get(timeframe, 300)) : pos]
        min_available = decision_timestamp - ZONE_LOOKBACK.get(timeframe, pd.Timedelta(days=30))
        recent = recent[recent["available_at"] >= min_available]
        if recent.empty:
            continue
        atr = atr_by_tf.get(timeframe, np.nan)
        zone_low = recent["zone_low"].astype(float).to_numpy()
        zone_high = recent["zone_high"].astype(float).to_numpy()
        if len(zone_low) == 0 or not np.isfinite(atr) or atr <= 0:
            continue
        below = price < zone_low
        above = price > zone_high
        distances_np = np.zeros(len(recent), dtype=float)
        distances_np[below] = (zone_low[below] - price) / atr
        distances_np[above] = (price - zone_high[above]) / atr
        best_pos = int(np.nanargmin(distances_np))
        row = recent.iloc[best_pos]
        best_distance = float(distances_np[best_pos])
        candidates.append(
            ZoneCandidate(
                object_id=str(row["object_id"]),
                object_type=str(row["object_type"]),
                source=str(row["object_type"]),
                timeframe=str(row["timeframe"]),
                kind=object_kind(str(row["object_type"]), str(row["timeframe"])),
                side=str(row["side"]),
                zone_low=float(row["zone_low"]),
                zone_high=float(row["zone_high"]),
                zone_mid=float(row["zone_mid"]),
                distance_atr=best_distance,
                available_at=pd.Timestamp(row["available_at"]),
                latest_source_candle_close_used=pd.Timestamp(row["latest_source_candle_close_used"]),
            )
        )

    if trendline_event is not None:
        timeframe = str(trendline_event.get("timeframe", "15m"))
        atr = atr_by_tf.get(timeframe, np.nan)
        candidates.append(
            ZoneCandidate(
                object_id=str(trendline_event.get("object_id", "")),
                object_type="trendline_interaction",
                source=f"trendline_{trendline_event.get('trendline_interaction_type', 'interaction')}",
                timeframe=timeframe,
                kind=f"{timeframe}_trendline",
                side=str(trendline_event.get("side", "")),
                zone_low=float(trendline_event.get("zone_low", np.nan)),
                zone_high=float(trendline_event.get("zone_high", np.nan)),
                zone_mid=float(trendline_event.get("zone_mid", np.nan)),
                distance_atr=distance_to_zone_atr(
                    price,
                    float(trendline_event.get("zone_low", np.nan)),
                    float(trendline_event.get("zone_high", np.nan)),
                    atr,
                ),
                available_at=pd.Timestamp(trendline_event.get("available_at")),
                latest_source_candle_close_used=pd.Timestamp(trendline_event.get("latest_source_candle_close_used")),
            )
        )

    if not candidates:
        return None
    candidates.sort(
        key=lambda item: (
            item.distance_atr,
            TIMEFRAME_PRIORITY.get(item.timeframe, 9),
            source_priority(item.object_type),
            item.available_at,
        )
    )
    return candidates[0]


def classify_reaction(
    bar_15m: pd.Series,
    zone: ZoneCandidate | None,
    trendline_event: dict[str, object] | None,
) -> tuple[str, str, str, float, str]:
    if zone is None:
        body_atr = float(bar_15m.get("body_atr", 0) or 0)
        if body_atr < 0.10:
            return "chop_no_decision", "neutral", "neutral", 0.0, "range_middle_chop_without_nearby_htf_zone"
        return "none", "neutral", "neutral", 0.0, "no_nearby_visible_btc_pa_zone"

    close = float(bar_15m["btc_15m_close"])
    open_ = float(bar_15m["btc_15m_open"])
    high = float(bar_15m["btc_15m_high"])
    low = float(bar_15m["btc_15m_low"])
    atr = max(float(bar_15m["btc_15m_atr"]), 1e-12)
    body_atr = abs(close - open_) / atr
    side = zone.side
    distance = zone.distance_atr
    interaction = str(trendline_event.get("trendline_interaction_type", "none")) if trendline_event else "none"
    event_side = str(trendline_event.get("side", side)) if trendline_event else side
    near = distance <= 0.55
    very_near = distance <= 0.20

    if interaction == "sweep":
        if event_side == "support":
            return (
                "liquidity_sweep_reclaim" if close >= open_ else "liquidity_sweep_fail",
                "bullish",
                "confirm",
                0.75,
                "btc_swept_support_or_trendline_and_reclaimed_on_closed_candle",
            )
        return (
            "liquidity_sweep_reclaim" if close <= open_ else "liquidity_sweep_fail",
            "bearish",
            "confirm",
            0.75,
            "btc_swept_resistance_or_trendline_and_rejected_on_closed_candle",
        )

    if interaction == "rejection":
        if event_side == "support":
            return "bullish_rejection", "bullish", "confirm", 0.68, "btc_rejected_from_support_trendline_event"
        return "bearish_rejection", "bearish", "confirm", 0.68, "btc_rejected_from_resistance_trendline_event"

    if interaction in {"clean_break", "break_retest"}:
        if event_side == "resistance":
            return "bullish_acceptance", "bullish", "veto", 0.86, "btc_clean_break_or_retest_above_resistance_trendline"
        return "bearish_acceptance", "bearish", "veto", 0.86, "btc_clean_break_or_retest_below_support_trendline"

    if near:
        if side == "support":
            if low <= zone.zone_high and close > zone.zone_mid and close >= open_ and body_atr >= 0.12:
                return "bullish_rejection", "bullish", "confirm", 0.62, "btc_closed_bullishly_from_visible_support_zone"
            if close < zone.zone_low and body_atr >= 0.18:
                return "bearish_acceptance", "bearish", "veto", 0.72, "btc_accepted_below_visible_support_zone"
            return "chop_no_decision", "neutral", "warn", 0.15, "btc_near_support_zone_without_confirmed_reaction"
        if high >= zone.zone_low and close < zone.zone_mid and close <= open_ and body_atr >= 0.12:
            return "bearish_rejection", "bearish", "confirm", 0.62, "btc_closed_bearishly_from_visible_resistance_zone"
        if close > zone.zone_high and body_atr >= 0.18:
            return "bullish_acceptance", "bullish", "veto", 0.72, "btc_accepted_above_visible_resistance_zone"
        return "chop_no_decision", "neutral", "warn", 0.15, "btc_near_resistance_zone_without_confirmed_reaction"

    if distance <= 1.25:
        return "chop_no_decision", "neutral", "warn", 0.10, "btc_approaching_htf_zone_but_no_reaction_yet"

    body_atr = float(bar_15m.get("body_atr", 0) or 0)
    if body_atr < 0.10:
        return "chop_no_decision", "neutral", "neutral", 0.0, "btc_mid_range_chop_no_decision"
    return "none", "neutral", "neutral", 0.0, "btc_not_at_actionable_pa_zone"


def side_effects(reaction_state: str, bias: str, context_effect: str) -> tuple[str, str]:
    if reaction_state in {"chop_no_decision", "none"}:
        return ("warn", "warn") if context_effect == "warn" else ("neutral", "neutral")
    if bias == "bullish":
        if context_effect == "veto":
            return "confirm", "veto"
        return "confirm", "warn"
    if bias == "bearish":
        if context_effect == "veto":
            return "veto", "confirm"
        return "warn", "confirm"
    return "neutral", "neutral"


def leader_score(base_strength: float, bias: str, zone: ZoneCandidate | None) -> float:
    if bias not in {"bullish", "bearish"}:
        return 0.0
    distance_bonus = 0.0
    timeframe_bonus = 0.0
    if zone is not None:
        distance_bonus = max(0.0, min(0.12, (0.60 - min(zone.distance_atr, 0.60)) * 0.20))
        timeframe_bonus = TIMEFRAME_SCORE_BONUS.get(zone.timeframe, 0.0)
    score = min(1.0, base_strength + distance_bonus + timeframe_bonus)
    return score if bias == "bullish" else -score


def build_context_snapshots(
    bars: dict[str, pd.DataFrame],
    zones: pd.DataFrame,
    trendlines: pd.DataFrame,
) -> pd.DataFrame:
    bars_15m = bars["15m"].copy()
    base = bars_15m.rename(
        columns={
            "close_time": "decision_timestamp",
            "close": "btc_15m_close",
            "open": "btc_15m_open",
            "high": "btc_15m_high",
            "low": "btc_15m_low",
            "atr": "btc_15m_atr",
        }
    )[
        [
            "decision_timestamp",
            "btc_15m_open",
            "btc_15m_high",
            "btc_15m_low",
            "btc_15m_close",
            "btc_15m_atr",
            "body_atr",
            "return_4bar",
        ]
    ].sort_values("decision_timestamp")
    base["latest_btc_15m_close_used"] = base["decision_timestamp"]

    for timeframe in ["1h", "4h"]:
        right = bars[timeframe][["close_time", "close", "atr"]].rename(
            columns={
                "close_time": f"latest_btc_{timeframe}_close_used",
                "close": f"btc_{timeframe}_close",
                "atr": f"btc_{timeframe}_atr",
            }
        )
        base = pd.merge_asof(
            base.sort_values("decision_timestamp"),
            right.sort_values(f"latest_btc_{timeframe}_close_used"),
            left_on="decision_timestamp",
            right_on=f"latest_btc_{timeframe}_close_used",
            direction="backward",
            allow_exact_matches=True,
        )

    zone_groups = prepare_zone_groups(zones)
    trendline_events = prepare_trendline_events(trendlines)
    rows: list[dict[str, object]] = []
    total = len(base)
    for row_number, (_, bar) in enumerate(base.iterrows(), 1):
        if row_number == 1 or row_number % 10000 == 0:
            print(f"  btc_context rows={row_number}/{total}", flush=True)
        decision_timestamp = pd.Timestamp(bar["decision_timestamp"])
        trend_event = latest_trendline_event(trendline_events, decision_timestamp)
        atr_by_tf = {
            "15m": float(bar["btc_15m_atr"]),
            "1h": float(bar.get("btc_1h_atr", np.nan)),
            "4h": float(bar.get("btc_4h_atr", np.nan)),
        }
        zone = nearest_zone(zone_groups, decision_timestamp, float(bar["btc_15m_close"]), atr_by_tf, trend_event)
        reaction_state, bias, effect, strength, reason = classify_reaction(bar, zone, trend_event)
        long_effect, short_effect = side_effects(reaction_state, bias, effect)
        score = leader_score(strength, bias, zone)

        used_times = [
            pd.Timestamp(bar["latest_btc_15m_close_used"]),
            pd.Timestamp(bar["latest_btc_1h_close_used"]) if pd.notna(bar.get("latest_btc_1h_close_used")) else pd.NaT,
            pd.Timestamp(bar["latest_btc_4h_close_used"]) if pd.notna(bar.get("latest_btc_4h_close_used")) else pd.NaT,
        ]
        if zone is not None:
            used_times.append(zone.latest_source_candle_close_used)
        if trend_event is not None:
            used_times.append(pd.Timestamp(trend_event["latest_source_candle_close_used"]))
        used_valid = [value for value in used_times if pd.notna(value)]
        latest_source = max(used_valid) if used_valid else decision_timestamp
        lookahead_pass = all(value <= decision_timestamp for value in used_valid)

        interaction = str(trend_event.get("trendline_interaction_type", "none")) if trend_event else "none"
        if interaction not in ALLOWED_INTERACTIONS:
            interaction = "none"
        if effect not in ALLOWED_CONTEXT_EFFECTS:
            effect = "neutral"
        if reaction_state not in ALLOWED_REACTION_STATES:
            reaction_state = "none"

        rows.append(
            {
                "decision_timestamp": decision_timestamp,
                "latest_btc_15m_close_used": pd.Timestamp(bar["latest_btc_15m_close_used"]),
                "latest_btc_1h_close_used": bar.get("latest_btc_1h_close_used", pd.NaT),
                "latest_btc_4h_close_used": bar.get("latest_btc_4h_close_used", pd.NaT),
                "btc_close": float(bar["btc_15m_close"]),
                "btc_15m_atr": float(bar["btc_15m_atr"]),
                "btc_htf_zone_kind": zone.kind if zone is not None else "none",
                "btc_nearest_zone_id": zone.object_id if zone is not None else "",
                "btc_nearest_zone_source": zone.source if zone is not None else "none",
                "btc_nearest_zone_timeframe": zone.timeframe if zone is not None else "none",
                "btc_nearest_zone_side": zone.side if zone is not None else "none",
                "btc_nearest_zone_low": zone.zone_low if zone is not None else np.nan,
                "btc_nearest_zone_high": zone.zone_high if zone is not None else np.nan,
                "btc_distance_to_zone_atr": zone.distance_atr if zone is not None else np.nan,
                "btc_trendline_interaction_type": interaction,
                "btc_trendline_event_id": str(trend_event.get("object_id", "")) if trend_event else "",
                "btc_trendline_event_timeframe": str(trend_event.get("timeframe", "")) if trend_event else "",
                "btc_pa_reaction_state": reaction_state,
                "btc_directional_bias": bias,
                "btc_leader_context_score": float(score),
                "btc_context_effect": effect,
                "btc_long_context_effect": long_effect,
                "btc_short_context_effect": short_effect,
                "btc_context_reason": reason,
                "btc_context_built_at": decision_timestamp,
                "latest_source_candle_close_used": latest_source,
                "lookahead_pass": bool(lookahead_pass),
                "lookahead_violation_reason": "" if lookahead_pass else "btc_source_close_after_decision_timestamp",
            }
        )
    return pd.DataFrame(rows)


def build_audit(snapshots: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "decision_timestamp",
        "latest_btc_15m_close_used",
        "latest_btc_1h_close_used",
        "latest_btc_4h_close_used",
        "latest_source_candle_close_used",
        "btc_context_built_at",
        "btc_htf_zone_kind",
        "btc_nearest_zone_source",
        "btc_trendline_interaction_type",
        "btc_pa_reaction_state",
        "btc_context_effect",
        "lookahead_pass",
        "lookahead_violation_reason",
    ]
    audit = snapshots[columns].copy()
    for column in [
        "decision_timestamp",
        "latest_btc_15m_close_used",
        "latest_btc_1h_close_used",
        "latest_btc_4h_close_used",
        "latest_source_candle_close_used",
        "btc_context_built_at",
    ]:
        audit[column] = pd.to_datetime(audit[column], utc=True, errors="coerce")
    latest_checks = [
        audit["latest_btc_15m_close_used"] <= audit["decision_timestamp"],
        audit["latest_btc_1h_close_used"].isna() | (audit["latest_btc_1h_close_used"] <= audit["decision_timestamp"]),
        audit["latest_btc_4h_close_used"].isna() | (audit["latest_btc_4h_close_used"] <= audit["decision_timestamp"]),
        audit["latest_source_candle_close_used"] <= audit["decision_timestamp"],
        audit["btc_context_built_at"] <= audit["decision_timestamp"],
    ]
    audit["lookahead_pass"] = latest_checks[0]
    for check in latest_checks[1:]:
        audit["lookahead_pass"] = audit["lookahead_pass"] & check
    audit.loc[audit["lookahead_pass"], "lookahead_violation_reason"] = ""
    audit.loc[~audit["lookahead_pass"], "lookahead_violation_reason"] = "btc_source_close_after_decision_timestamp"
    return audit


def markdown_table(rows: Iterable[dict[str, object]], columns: list[str]) -> list[str]:
    rows = list(rows)
    if not rows:
        return ["_No rows._"]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(column, "")) for column in columns) + " |")
    return lines


def write_report(
    snapshots: pd.DataFrame,
    audit: pd.DataFrame,
    bars: dict[str, pd.DataFrame],
    zones: pd.DataFrame,
    trendlines: pd.DataFrame,
) -> None:
    effect_counts = snapshots["btc_context_effect"].value_counts().reset_index()
    effect_counts.columns = ["btc_context_effect", "rows"]
    reaction_counts = snapshots["btc_pa_reaction_state"].value_counts().reset_index()
    reaction_counts.columns = ["btc_pa_reaction_state", "rows"]
    interaction_counts = snapshots["btc_trendline_interaction_type"].value_counts().reset_index()
    interaction_counts.columns = ["btc_trendline_interaction_type", "rows"]
    zone_kind_counts = snapshots["btc_htf_zone_kind"].value_counts().head(12).reset_index()
    zone_kind_counts.columns = ["btc_htf_zone_kind", "rows"]
    violations = int((~audit["lookahead_pass"]).sum())

    spot = []
    for effect in ["confirm", "warn", "veto", "neutral"]:
        sample = snapshots[snapshots["btc_context_effect"].eq(effect)].head(1)
        if sample.empty:
            continue
        row = sample.iloc[0]
        spot.append(
            {
                "decision_timestamp": row["decision_timestamp"],
                "effect": row["btc_context_effect"],
                "reaction": row["btc_pa_reaction_state"],
                "bias": row["btc_directional_bias"],
                "zone": f"{row['btc_nearest_zone_timeframe']}:{row['btc_nearest_zone_source']}",
                "distance_atr": round(float(row["btc_distance_to_zone_atr"]), 3)
                if pd.notna(row["btc_distance_to_zone_atr"])
                else "",
                "reason": row["btc_context_reason"],
            }
        )

    lines = [
        "# Craig v1.2 BTC Context Build Report",
        "",
        "Generated by `scripts/build_craig_v1_2_btc_context.py`.",
        "",
        "## Verdict",
        "",
        "- BTC PA context snapshots were built from BTCUSDT 15m/1h/4h closed candles and the no-lookahead HTF PA-zone registry.",
        "- BTC is interpreted as PA-zone reaction context, not as a simple green/red or momentum filter.",
        f"- Lookahead violations: {violations}.",
        "",
        "## Dataset And Grain",
        "",
        f"- Decision snapshot grain: closed BTC 15m candles ({len(snapshots)} rows).",
        f"- BTC 15m bars: {len(bars['15m'])}",
        f"- BTC 1h bars: {len(bars['1h'])}",
        f"- BTC 4h bars: {len(bars['4h'])}",
        f"- BTC HTF zone rows available: {len(zones[zones['symbol'].eq('BTCUSDT')])}",
        f"- BTC trendline zone/event rows available: {len(trendlines[trendlines['symbol'].eq('BTCUSDT')])}",
        "",
        "## Context Effect Distribution",
        "",
        "`btc_context_effect` is side-agnostic: `confirm` means BTC has a directional PA-zone reaction, while `veto` means a strong acceptance/clean-break state that should veto the opposite thesis. Use `btc_long_context_effect` and `btc_short_context_effect` in the later SOL/ETH thesis generator.",
        "",
        *markdown_table(effect_counts.to_dict("records"), ["btc_context_effect", "rows"]),
        "",
        "## PA Reaction State Distribution",
        "",
        *markdown_table(reaction_counts.to_dict("records"), ["btc_pa_reaction_state", "rows"]),
        "",
        "## Trendline Interaction Distribution",
        "",
        *markdown_table(interaction_counts.to_dict("records"), ["btc_trendline_interaction_type", "rows"]),
        "",
        "## Nearest HTF Zone Kind Distribution",
        "",
        *markdown_table(zone_kind_counts.to_dict("records"), ["btc_htf_zone_kind", "rows"]),
        "",
        "## Spot Checks",
        "",
        *markdown_table(
            spot,
            ["decision_timestamp", "effect", "reaction", "bias", "zone", "distance_atr", "reason"],
        ),
        "",
        "## No-Lookahead Controls",
        "",
        "- `latest_btc_15m_close_used`, `latest_btc_1h_close_used`, and `latest_btc_4h_close_used` must be less than or equal to `decision_timestamp`.",
        "- The nearest PA-zone object must have `available_at <= decision_timestamp` and `latest_source_candle_close_used <= decision_timestamp`.",
        "- Trendline interactions are consumed as event rows with their own `available_at`; future trendline anchors or future reaction labels are not used.",
        "- The script does not read SOL/ETH outcomes, gold labels, Craig target action, result R, entry, stop, TP, or PnL fields.",
        "",
        "## Output Paths",
        "",
        f"- Snapshots: `{rel(OUT_SNAPSHOTS)}`",
        f"- Audit CSV: `{rel(OUT_AUDIT)}`",
        "",
        "## Next Step Recommendation",
        "",
        "Build the target pool generator before the thesis generator. The thesis generator needs to know whether a candidate has a structural path to Craig-style 3R+ core and 7R-8R runner targets; without that, it can only score context, not decide whether the setup preserves Craig DNA.",
    ]
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--btc-1m", type=Path, default=BTC_1M_PARQUET)
    parser.add_argument("--htf-zones", type=Path, default=HTF_ZONES_PARQUET)
    parser.add_argument("--trendline-zones", type=Path, default=TRENDLINE_ZONES_PARQUET)
    args = parser.parse_args()

    print("load BTC bars", flush=True)
    bars = load_btc_bars(args.btc_1m)
    print("load HTF zones", flush=True)
    zones = pd.read_parquet(args.htf_zones)
    print("load trendline zones", flush=True)
    trendlines = pd.read_parquet(args.trendline_zones)
    print("build BTC context snapshots", flush=True)
    snapshots = build_context_snapshots(bars, zones, trendlines)
    print("build audit", flush=True)
    audit = build_audit(snapshots)
    if not audit["lookahead_pass"].all():
        failures = int((~audit["lookahead_pass"]).sum())
        raise RuntimeError(f"BTC context lookahead audit failed for {failures} rows")

    OUT_SNAPSHOTS.parent.mkdir(parents=True, exist_ok=True)
    snapshots.to_parquet(OUT_SNAPSHOTS, index=False)
    audit.to_csv(OUT_AUDIT, index=False, encoding="utf-8-sig")
    write_report(snapshots, audit, bars, zones, trendlines)
    print(f"snapshots={OUT_SNAPSHOTS} rows={len(snapshots)}")
    print(f"audit={OUT_AUDIT} rows={len(audit)} lookahead_pass={int(audit['lookahead_pass'].sum())}/{len(audit)}")
    print(f"report={OUT_REPORT}")


if __name__ == "__main__":
    main()
