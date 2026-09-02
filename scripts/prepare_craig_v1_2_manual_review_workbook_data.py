#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_JSON = ROOT / "outputs" / "craig_v1_2_manual_review_workbook_data.json"

TRADE_LOG = ROOT / "outputs" / "craig_v1_2_event_execution_trade_log.csv"
SNIPER = ROOT / "outputs" / "craig_v1_2_sniper_trade_candidates.parquet"
SCENARIO = ROOT / "outputs" / "craig_v1_2_scenario_thesis.parquet"
REPORT = ROOT / "outputs" / "craig_v1_2_event_execution_report.md"


def pct(value: float, total: float) -> float:
    return float(value / total) if total else 0.0


def clean_value(value):
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def iso_utc(series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(series, utc=True, errors="coerce")
    return dt.dt.strftime("%Y-%m-%d %H:%M:%S UTC").where(dt.notna(), "")


def kst_time(series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(series, utc=True, errors="coerce")
    return dt.dt.tz_convert("Asia/Seoul").dt.strftime("%Y-%m-%d %H:%M:%S KST").where(dt.notna(), "")


def ny_time(series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(series, utc=True, errors="coerce")
    return dt.dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d %H:%M:%S NY").where(dt.notna(), "")


def review_hint(row: pd.Series) -> str:
    state = str(row.get("final_state", ""))
    cost_r = float(row.get("cost_r", 0) or 0)
    risk_bps = float(row.get("risk_bps", 0) or 0)
    tier = str(row.get("entry_pattern_tier", ""))
    hints: list[str] = []
    if tier == "S_tier_sniper":
        hints.append("S-tier: Craig-like strict sniper candidate")
    if state == "stopped":
        hints.append("Stopped: check whether PA zone/context was actually meaningful")
    elif state == "breakeven_exit":
        hints.append("BE: check if BE move was too early or normal Craig scratch")
    elif state == "runner_hit":
        hints.append("Winner: inspect what made this one work")
    elif state == "canceled_no_chase":
        hints.append("No-chase: check if Craig would market-enter or let it go")
    elif state == "canceled_no_fill":
        hints.append("No-fill: FVG midpoint order never filled")
    if cost_r >= 0.75:
        hints.append("High cost in R: stop may be too tight for fees/slippage")
    if risk_bps <= 15 and state in {"stopped", "breakeven_exit"}:
        hints.append("Very tight risk: fee/BE bleed candidate")
    if bool(row.get("one_min_trendline_break_confirmed")) is False and bool(row.get("one_min_choch_bos_confirmed")):
        hints.append("CHoCH-only entry permission")
    if bool(row.get("one_min_trendline_break_confirmed")) and bool(row.get("one_min_choch_bos_confirmed")):
        hints.append("1m TL break + CHoCH both present")
    return " | ".join(hints)


def priority_bucket(row: pd.Series) -> str:
    state = str(row.get("final_state", ""))
    tier = str(row.get("entry_pattern_tier", ""))
    cost_r = float(row.get("cost_r", 0) or 0)
    net_r = float(row.get("net_r", 0) or 0)
    if tier == "S_tier_sniper":
        return "P0_S_tier"
    if state == "stopped" and cost_r >= 0.75:
        return "P0_stop_cost"
    if state == "breakeven_exit" and cost_r >= 0.5:
        return "P1_be_fee_bleed"
    if state == "runner_hit" or net_r >= 5:
        return "P1_winner_template"
    if state == "canceled_no_chase":
        return "P2_no_chase"
    return "P3_general"


def chart_symbol(symbol: str) -> str:
    # TradingView's Binance perpetual symbols commonly use the .P suffix.
    return f"BINANCE:{symbol}.P"


def load_and_join() -> pd.DataFrame:
    trades = pd.read_csv(TRADE_LOG)
    sniper = pd.read_parquet(SNIPER)
    scenarios = pd.read_parquet(SCENARIO)

    # Only final simulator inputs are in the event trade log, but keep the filter explicit.
    sniper = sniper[
        sniper["sniper_candidate_status"].eq("accepted_headline")
        & sniper["entry_pattern_tier"].isin(["S_tier_sniper", "A_tier_sniper"])
    ].copy()

    scenario_cols = [
        "scenario_id",
        "scenario_side",
        "primary_pa_zone_source",
        "primary_pa_zone_timeframe",
        "primary_zone_low",
        "primary_zone_high",
        "primary_zone_mid",
        "activation_distance_atr",
        "scenario_priority",
        "scenario_activation_quality",
        "btc_context_effect_for_scenario",
        "btc_context_reason",
        "expected_reaction",
        "invalidation_price",
        "source_thesis_mode",
        "source_thesis_score",
        "htf_trendline_context_before",
        "htf_trendline_used_for_pa_zone",
        "htf_trendline_context_condition_count",
        "htf_trendline_context_reason",
        "weak_trendline_context_filtered",
    ]
    scenarios = scenarios[[c for c in scenario_cols if c in scenarios.columns]].copy()

    sniper_cols = [
        "candidate_id",
        "scenario_id",
        "decision_timestamp",
        "sniper_pattern_name",
        "approved_htf_pa_zone_id",
        "approved_htf_pa_zone_source",
        "htf_trendline_used_for_pa_zone",
        "htf_trendline_interaction_type",
        "one_min_trendline_id",
        "one_min_trendline_break_confirmed",
        "one_min_choch_bos_confirmed",
        "one_min_displacement_confirmed",
        "one_min_fvg_id",
        "one_min_fvg_low",
        "one_min_fvg_high",
        "one_min_fvg_mid",
        "one_min_fvg_created_at",
        "fvg_created_by_displacement",
        "entry_model",
        "fvg_mid_retest_confirmed",
        "one_min_trendline_retest_overlap",
        "sweep_reclaim_present",
        "stop_anchor_type",
        "planned_rr_core_net",
        "planned_rr_runner_net",
        "duplicate_group_id",
        "frequency_control_reason",
        "target_pool_built_at",
        "target_latest_source_close_used",
    ]
    sniper = sniper[[c for c in sniper_cols if c in sniper.columns]].copy()

    df = trades.merge(sniper, on="candidate_id", how="left", suffixes=("", "_candidate"))
    df = df.merge(scenarios, on="scenario_id", how="left", suffixes=("", "_scenario"))

    for col in ["entry_price", "stop_price", "fee_r", "slippage_r", "gross_r", "net_r"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["risk_abs"] = (df["entry_price"] - df["stop_price"]).abs()
    df["risk_bps"] = df["risk_abs"] / df["entry_price"] * 10000
    df["cost_r"] = df["fee_r"].fillna(0) + df["slippage_r"].fillna(0)
    df["chart_symbol"] = df["symbol"].map(chart_symbol)
    df["chart_url"] = "https://www.tradingview.com/chart/?symbol=" + df["chart_symbol"].str.replace(":", "%3A", regex=False)
    df["trigger_utc"] = iso_utc(df["trigger_available_at"])
    df["trigger_kst"] = kst_time(df["trigger_available_at"])
    df["trigger_ny"] = ny_time(df["trigger_available_at"])
    df["decision_utc"] = iso_utc(df["decision_timestamp"])
    df["order_placed_utc"] = iso_utc(df["order_placed_at"])
    df["fill_utc"] = iso_utc(df["fill_timestamp"])
    df["exit_utc"] = iso_utc(df["exit_timestamp"])
    df["one_min_fvg_created_utc"] = iso_utc(df["one_min_fvg_created_at"])
    df["review_hint"] = df.apply(review_hint, axis=1)
    df["review_priority_bucket"] = df.apply(priority_bucket, axis=1)
    df["review_sort_key"] = df["review_priority_bucket"].map(
        {"P0_S_tier": 0, "P0_stop_cost": 1, "P1_be_fee_bleed": 2, "P1_winner_template": 3, "P2_no_chase": 4}
    ).fillna(9)

    return df.sort_values(["trigger_available_at", "symbol", "side", "candidate_id"]).reset_index(drop=True)


def build_review_rows(df: pd.DataFrame) -> list[dict[str, object]]:
    columns = [
        "review_status",
        "craig_verdict",
        "issue_tag",
        "context_grade",
        "entry_grade",
        "management_grade",
        "user_notes",
        "action_recommendation",
        "review_priority_bucket",
        "review_hint",
        "chart_symbol",
        "chart_url",
        "symbol",
        "side",
        "entry_pattern_tier",
        "scenario_type",
        "final_state",
        "session_bucket",
        "decision_utc",
        "trigger_utc",
        "trigger_kst",
        "trigger_ny",
        "order_placed_utc",
        "fill_utc",
        "exit_utc",
        "entry_price",
        "stop_price",
        "risk_bps",
        "tp1_price",
        "core_target_price",
        "runner_target_price",
        "gross_r",
        "net_r",
        "fee_r",
        "slippage_r",
        "cost_r",
        "max_favorable_excursion_r",
        "max_adverse_excursion_r",
        "hit_tp1",
        "hit_core",
        "hit_runner",
        "stopped",
        "canceled_reason",
        "ambiguity_flag",
        "scenario_id",
        "candidate_id",
        "sniper_pattern_name",
        "scenario_side",
        "primary_pa_zone_source",
        "primary_pa_zone_timeframe",
        "primary_zone_low",
        "primary_zone_high",
        "primary_zone_mid",
        "activation_distance_atr",
        "scenario_priority",
        "scenario_activation_quality",
        "btc_context_effect_for_scenario",
        "btc_context_reason",
        "expected_reaction",
        "source_thesis_mode",
        "source_thesis_score",
        "htf_trendline_used_for_pa_zone",
        "htf_trendline_interaction_type",
        "htf_trendline_context_condition_count",
        "htf_trendline_context_reason",
        "weak_trendline_context_filtered",
        "one_min_trendline_break_confirmed",
        "one_min_choch_bos_confirmed",
        "one_min_displacement_confirmed",
        "one_min_fvg_low",
        "one_min_fvg_high",
        "one_min_fvg_mid",
        "one_min_fvg_created_utc",
        "fvg_created_by_displacement",
        "one_min_trendline_retest_overlap",
        "sweep_reclaim_present",
        "entry_model",
        "stop_anchor_type",
        "planned_rr_core_net",
        "planned_rr_runner_net",
        "frequency_control_reason",
        "lookahead_pass",
    ]
    out = df.copy()
    out["review_status"] = "unchecked"
    for c in [
        "craig_verdict",
        "issue_tag",
        "context_grade",
        "entry_grade",
        "management_grade",
        "user_notes",
        "action_recommendation",
    ]:
        out[c] = ""
    rows = []
    for _, row in out[columns].iterrows():
        rows.append({col: clean_value(row[col]) for col in columns})
    return rows


def summary_table(df: pd.DataFrame, group_cols: list[str]) -> list[dict[str, object]]:
    grouped = df.groupby(group_cols, dropna=False)
    rows = []
    for key, part in grouped:
        if not isinstance(key, tuple):
            key = (key,)
        row = {col: clean_value(val) for col, val in zip(group_cols, key)}
        filled = part[part["final_state"].isin(["stopped", "breakeven_exit", "runner_hit", "session_close_exit", "ambiguous_conservative_stop_first"])]
        wins = part[part["net_r"] > 0]
        losses = part[part["net_r"] < 0]
        row.update(
            {
                "rows": int(len(part)),
                "filled": int(len(filled)),
                "net_r": float(part["net_r"].sum()),
                "gross_r": float(part["gross_r"].sum()),
                "expectancy": float(part["net_r"].mean()) if len(part) else 0.0,
                "win_rate": pct(len(wins), len(part)),
                "profit_factor": float(wins["net_r"].sum() / abs(losses["net_r"].sum())) if len(losses) and abs(losses["net_r"].sum()) > 0 else None,
                "fee_r": float(part["fee_r"].sum()),
                "slippage_r": float(part["slippage_r"].sum()),
            }
        )
        rows.append(row)
    return sorted(rows, key=lambda r: (str(r.get(group_cols[0], "")), str(r.get(group_cols[-1], ""))))


def main() -> None:
    df = load_and_join()
    review_rows = build_review_rows(df)
    priority = df.sort_values(["review_sort_key", "net_r", "trigger_available_at"], ascending=[True, True, True]).head(350)
    priority_rows = build_review_rows(priority)

    metadata = {
        "generated_from": {
            "trade_log": str(TRADE_LOG.relative_to(ROOT)),
            "sniper_candidates": str(SNIPER.relative_to(ROOT)),
            "scenario_thesis": str(SCENARIO.relative_to(ROOT)),
            "event_report": str(REPORT.relative_to(ROOT)),
        },
        "row_counts": {
            "review_all": len(review_rows),
            "priority_review": len(priority_rows),
            "s_tier": int((df["entry_pattern_tier"] == "S_tier_sniper").sum()),
            "a_tier": int((df["entry_pattern_tier"] == "A_tier_sniper").sum()),
        },
        "headline": {
            "net_total_r": float(df["net_r"].sum()),
            "gross_total_r": float(df["gross_r"].sum()),
            "fee_drag_r": float(df["fee_r"].sum()),
            "slippage_drag_r": float(df["slippage_r"].sum()),
            "expectancy": float(df["net_r"].mean()),
            "win_rate": pct((df["net_r"] > 0).sum(), len(df)),
        },
        "validation_lists": {
            "review_status": ["unchecked", "reviewed", "needs_screenshot", "revisit"],
            "craig_verdict": ["would_trade", "would_pass", "maybe", "unclear"],
            "issue_tag": [
                "wrong_context",
                "weak_pa_zone",
                "too_many_trendlines",
                "not_main_scenario",
                "no_true_sweep",
                "late_entry",
                "bad_1m_fvg",
                "no_real_choch",
                "stop_too_tight",
                "target_unrealistic",
                "be_management",
                "fee_sensitive",
                "good_setup",
                "other",
            ],
            "grade": ["A", "B", "C", "D", "F", "unclear"],
        },
    }

    payload = {
        "metadata": metadata,
        "review_rows": review_rows,
        "priority_rows": priority_rows,
        "summary_by_state": summary_table(df, ["final_state"]),
        "summary_by_tier": summary_table(df, ["entry_pattern_tier"]),
        "summary_by_scenario": summary_table(df, ["scenario_type"]),
        "summary_by_symbol_side": summary_table(df, ["symbol", "side"]),
        "summary_by_session": summary_table(df, ["session_bucket"]),
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    print(f"Wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
