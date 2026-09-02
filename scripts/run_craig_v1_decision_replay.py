#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from build_craig_v1_features import (
    CORE_SYMBOLS,
    FEATURE_MATRIX,
    ROOT,
    clean,
    coverage_lookup,
    load_ohlcv,
    parse_decision_time,
    read_csv,
    safe_float,
    write_csv,
)


OUT_DIR = ROOT / "outputs"
DECISION_UNITS = OUT_DIR / "gold_v03_decision_units_v1.csv"
COVERAGE_MANIFEST = OUT_DIR / "gold_v03_v1_ohlcv_coverage_manifest.csv"
CANONICAL_MAPPING = OUT_DIR / "gold_v03_canonical_mapping_v1.csv"
REPLAY_RESULTS = OUT_DIR / "craig_v1_replay_results.csv"
VALIDATION_REPORT = OUT_DIR / "craig_v1_validation_report.md"
MAPPING_PROPOSAL = OUT_DIR / "gold_v03_canonical_mapping_v1_1_proposal.csv"
NY_TZ = "America/New_York"


def boolish(value: object) -> bool:
    return clean(value).lower() == "true"


def target_policy_action(row: dict[str, str]) -> str:
    if not boolish(row.get("label_eligible_for_policy_learning")):
        return "exclude_context_prior"
    fill = row.get("label_fill_state", "")
    cls = row.get("label_decision_class", "")
    if fill == "filled":
        return "take"
    if fill == "not_filled":
        return "no_fill"
    if fill == "passed":
        return "pass"
    if fill == "cancelled":
        return "cancel"
    if fill == "managed_existing" or cls == "management_context":
        return "management"
    if fill == "planned_unknown_fill":
        return "wait"
    return "exclude_context_prior"


def predict_policy_action(row: dict[str, str]) -> tuple[str, str, float]:
    trace: list[str] = ["observe_session_state"]
    if row.get("runtime_feature_status") in {"missing_primary_symbol_ohlcv", "no_completed_candles_before_cutoff"}:
        trace.append(row.get("runtime_feature_status", "missing_runtime_feature"))
        return "hold_unknown", "|".join(trace), 0.0
    if row.get("runtime_time_parse_confidence") in {"none"}:
        trace.append("missing_decision_time")
        return "hold_unknown", "|".join(trace), 0.0
    side = row.get("runtime_candidate_side_from_gold_row", "")
    if side not in {"long", "short"}:
        trace.append(f"side_not_tradeable={side or 'blank'}")
        return "hold_unknown", "|".join(trace), 0.0

    trace.append("form_thesis")
    quality = safe_float(row.get("feature_setup_quality_score")) or 0.0
    no_chase = row.get("feature_no_chase_risk", "")
    fvg_freshness = row.get("feature_fvg_latest_freshness_for_side", "")
    htf_aligned = row.get("feature_htf_bias_aligned_with_candidate", "")

    if no_chase in {"high_far_from_entry", "high_rr_compressed"}:
        trace.append(f"plan_entry:no_chase={no_chase}")
        return "pass", "|".join(trace), quality
    if fvg_freshness == "fully_mitigated" and quality < 5:
        trace.append("plan_entry:fvg_already_fully_mitigated")
        return "cancel", "|".join(trace), quality

    trace.append("rank_select_symbol")
    if row.get("feature_primary_symbol_relative_state") == "relative_laggard" and htf_aligned == "false" and quality < 5:
        trace.append("symbol_not_clean_enough")
        return "wait", "|".join(trace), quality

    trace.append("wait_for_setup")
    if quality >= 6.0:
        trace.append("setup_confluence_take")
        return "take", "|".join(trace), quality
    if quality >= 3.5:
        trace.append("setup_partial_wait")
        return "wait", "|".join(trace), quality
    trace.append("insufficient_runtime_confluence")
    return "wait", "|".join(trace), quality


def load_feature_rows(path: Path) -> list[dict[str, str]]:
    rows = read_csv(path)
    if not rows:
        raise RuntimeError(f"Feature matrix is empty: {path}")
    return rows


def index_decision_units(path: Path) -> dict[str, dict[str, str]]:
    return {row["context_id"]: row for row in read_csv(path)}


def exact_fill_replay(row: dict[str, str], unit: dict[str, str], coverage: dict[tuple[str, str], Path]) -> dict[str, object]:
    if not boolish(row.get("label_eligible_for_fill_backtest")):
        return {
            "exact_fill_layer_status": "excluded_not_fill_backtest_eligible",
            "exact_fill_result": "",
            "exact_fill_match": "",
            "exact_fill_trace": "",
        }

    entry = safe_float(unit.get("entry_price_numeric"))
    stop = safe_float(unit.get("stop_price_numeric"))
    target = safe_float(unit.get("target_price_numeric"))
    side = unit.get("trade_side", "")
    dt = parse_decision_time(unit)
    path = coverage.get((dt.market_date, unit.get("primary_symbol", "")))
    if path is None or dt.cutoff_utc is None or entry is None:
        return {
            "exact_fill_layer_status": "blocked_missing_runtime_or_entry",
            "exact_fill_result": "",
            "exact_fill_match": "",
            "exact_fill_trace": "missing_path_or_time_or_entry",
        }
    df = load_ohlcv(str(path))
    if df.empty:
        return {
            "exact_fill_layer_status": "blocked_empty_ohlcv",
            "exact_fill_result": "",
            "exact_fill_match": "",
            "exact_fill_trace": "empty_ohlcv",
        }
    local_start = dt.cutoff_utc.tz_convert(NY_TZ)
    local_end = pd.Timestamp(local_start.date()).tz_localize(NY_TZ) + pd.Timedelta(days=1)
    future = df[(df.index >= dt.cutoff_utc) & (df.index < local_end.tz_convert("UTC"))].copy()
    if future.empty:
        return {
            "exact_fill_layer_status": "blocked_no_future_window",
            "exact_fill_result": "",
            "exact_fill_match": "",
            "exact_fill_trace": "no_future_candles",
        }

    fill_time = ""
    exit_result = "open_or_not_resolved"
    trace: list[str] = []
    filled = False
    for ts, candle in future.iterrows():
        high = float(candle.high)
        low = float(candle.low)
        if not filled:
            if low <= entry <= high:
                filled = True
                fill_time = ts.isoformat()
                trace.append(f"filled@{fill_time}")
            else:
                continue
        if filled:
            stop_hit = False
            target_hit = False
            if stop is not None:
                stop_hit = low <= stop if side == "long" else high >= stop
            if target is not None:
                target_hit = high >= target if side == "long" else low <= target
            if stop_hit and target_hit:
                exit_result = "ambiguous_stop_and_target_same_candle"
                trace.append(f"ambiguous@{ts.isoformat()}")
                break
            if stop_hit:
                exit_result = "stop_hit"
                trace.append(f"stop@{ts.isoformat()}")
                break
            if target_hit:
                exit_result = "target_hit"
                trace.append(f"target@{ts.isoformat()}")
                break
    if not filled:
        exit_result = "not_filled"
        trace.append("entry_not_touched_before_day_end")
    elif exit_result == "open_or_not_resolved" and (stop is None or target is None):
        exit_result = "filled_partial_geometry_unresolved"

    outcome = row.get("label_outcome_class", "")
    coarse_match = ""
    if outcome == "loss":
        coarse_match = str(exit_result == "stop_hit").lower()
    elif outcome == "win":
        coarse_match = str(exit_result == "target_hit").lower()
    elif outcome == "no_fill":
        coarse_match = str(exit_result == "not_filled").lower()
    elif outcome in {"breakeven", "mixed"}:
        coarse_match = "not_scored_requires_management"
    else:
        coarse_match = "not_scored_unknown_outcome"

    return {
        "exact_fill_layer_status": "evaluated_partial_geometry" if stop is None or target is None else "evaluated_exact_geometry",
        "exact_fill_result": exit_result,
        "exact_fill_match": coarse_match,
        "exact_fill_trace": "|".join(trace),
    }


def management_replay(row: dict[str, str], unit: dict[str, str]) -> dict[str, object]:
    if not boolish(row.get("label_eligible_for_management_replay")):
        return {
            "management_layer_status": "excluded_not_management_replay_eligible",
            "management_expected_family": "",
            "management_predicted_family": "",
            "management_match": "",
            "management_trace": "",
        }
    expected = row.get("source_management_family_tags_for_audit", "")
    outcome = row.get("label_outcome_class", "")
    families = set(filter(None, expected.split("|")))
    predicted: set[str] = set()
    trace: list[str] = ["manage_risk"]
    vol = row.get("feature_volatility_regime")
    if vol in {"expanded", "extreme"}:
        predicted.add("risk_reduce")
        trace.append(f"volatility={vol}:risk_reduce")
    if row.get("feature_choch_type") not in {"none", "unknown", ""}:
        predicted.add("move_to_be")
        trace.append(f"choch={row.get('feature_choch_type')}:move_to_be")
    if row.get("feature_htf_bias_aligned_with_candidate") == "true" and outcome == "win":
        predicted.add("runner_hold")
        trace.append("htf_aligned_win_context:runner_hold")
    if row.get("feature_sweep_liquidity_proxy") not in {"none", "unknown", ""} and outcome in {"breakeven", "mixed", "loss"}:
        predicted.add("manual_exit")
        trace.append("sweep_or_reversal_context:manual_exit")
    if not predicted:
        predicted.add("family_only_unresolved")
        trace.append("no_numeric_management_trigger")

    if "execution_anomaly" in families:
        match = "excluded_execution_anomaly"
    else:
        match = str(bool(families.intersection(predicted))).lower()
        if "family_only_unresolved" in predicted and families:
            match = "family_only_unresolved"
    return {
        "management_layer_status": "evaluated_family_proxy",
        "management_expected_family": expected,
        "management_predicted_family": "|".join(sorted(predicted)),
        "management_match": match,
        "management_trace": "|".join(trace),
    }


def mapping_v1_1_proposal(mapping_path: Path, output: Path) -> list[dict[str, object]]:
    rows = [r for r in read_csv(mapping_path) if boolish(r.get("needs_manual_review"))]
    proposal_rows: list[dict[str, object]] = []
    for row in rows:
        mapping_type = row.get("mapping_type", "")
        raw = row.get("raw_value", "")
        if mapping_type == "decision_type":
            if raw == "missed_fill":
                proposed_class = "planned_no_fill"
                proposed_fill = "not_filled"
                subtype = "missed_by_fraction_or_no_fill_from_row_context"
            elif "executed_or_actionable" in raw:
                proposed_class = "split_by_gold_status_and_fill_evidence"
                proposed_fill = "filled_only_if_execution_visible_else_planned_unknown_fill"
                subtype = "derive_from_row_context"
            elif raw.startswith("executed"):
                proposed_class = "executed_trade"
                proposed_fill = "filled"
                subtype = "derive_from_row_outcome_and_management_fields_not_raw_label"
            else:
                proposed_class = "keep_current"
                proposed_fill = "keep_current"
                subtype = "derive_from_row_context"
        elif mapping_type == "outcome" and raw == "":
            proposed_class = "unchanged"
            proposed_fill = "unchanged"
            subtype = "blank_realized_result_keeps_outcome_unknown_unless_exit_or_rule_outcome_supports_specific_class"
        else:
            proposed_class = "keep_current"
            proposed_fill = "keep_current"
            subtype = "manual_review"
        proposal_rows.append(
            {
                "mapping_type": mapping_type,
                "raw_value": raw,
                "raw_count": row.get("raw_count", ""),
                "current_canonical_summary": row.get("canonical_summary", ""),
                "proposed_decision_class_rule": proposed_class,
                "proposed_fill_state_rule": proposed_fill,
                "proposed_subtype_or_outcome_rule": subtype,
                "review_reason": "Current raw value maps to multiple row-level canonical states; preserve raw meaning and derive specifics from row fields.",
            }
        )
    write_csv(output, proposal_rows)
    return proposal_rows


def run_replay(feature_matrix: Path, decision_units: Path, manifest: Path, mapping: Path) -> tuple[list[dict[str, object]], dict[str, Any]]:
    feature_rows = load_feature_rows(feature_matrix)
    unit_by_id = index_decision_units(decision_units)
    coverage = coverage_lookup(read_csv(manifest))
    results: list[dict[str, object]] = []
    for row in feature_rows:
        unit = unit_by_id[row["context_id"]]
        target = target_policy_action(row)
        pred, trace, score = predict_policy_action(row)
        if target == "exclude_context_prior":
            policy_status = "excluded_context_prior"
            policy_match = ""
        elif pred == "hold_unknown":
            policy_status = "hold_unknown_not_failure" if target in {"wait", "management"} else "evaluated_hold_unknown"
            policy_match = "not_scored_hold_unknown" if "hold_unknown_not_failure" in policy_status else "false"
        else:
            policy_status = "evaluated"
            policy_match = str(pred == target).lower()
        exact = exact_fill_replay(row, unit, coverage)
        mgmt = management_replay(row, unit)
        out: dict[str, object] = {
            "context_id": row["context_id"],
            "video_id": row.get("video_id", ""),
            "runtime_market_date": row.get("runtime_market_date", ""),
            "runtime_decision_time_ny": row.get("runtime_decision_time_ny", ""),
            "runtime_primary_symbol": row.get("runtime_primary_symbol", ""),
            "runtime_candidate_side": row.get("runtime_candidate_side_from_gold_row", ""),
            "target_policy_action": target,
            "predicted_policy_action": pred,
            "policy_layer_status": policy_status,
            "policy_match": policy_match,
            "policy_score": score,
            "policy_trace": trace,
            "setup_quality_score": row.get("feature_setup_quality_score", ""),
            "setup_quality_trace": row.get("feature_setup_quality_trace", ""),
            "feature_status": row.get("runtime_feature_status", ""),
            "feature_session_phase": row.get("runtime_session_phase", ""),
            "feature_htf_bias": row.get("feature_htf_bias", ""),
            "feature_fvg_active_for_side": row.get("feature_fvg_active_for_side", ""),
            "feature_choch_type": row.get("feature_choch_type", ""),
            "feature_volatility_regime": row.get("feature_volatility_regime", ""),
            "source_geometry_mode": row.get("source_geometry_mode", ""),
            "label_decision_class": row.get("label_decision_class", ""),
            "label_fill_state": row.get("label_fill_state", ""),
            "label_outcome_class": row.get("label_outcome_class", ""),
        }
        out.update(exact)
        out.update(mgmt)
        results.append(out)
    write_csv(REPLAY_RESULTS, results)
    mapping_rows = mapping_v1_1_proposal(mapping, MAPPING_PROPOSAL)
    summary = summarize(results, mapping_rows)
    write_report(summary, VALIDATION_REPORT)
    return results, summary


def pct(numer: int, denom: int) -> str:
    if denom == 0:
        return "n/a"
    return f"{numer / denom:.1%}"


def summarize(results: list[dict[str, object]], mapping_rows: list[dict[str, object]]) -> dict[str, Any]:
    policy_eval = [r for r in results if r["policy_layer_status"] == "evaluated"]
    policy_matches = [r for r in policy_eval if r["policy_match"] == "true"]
    hold_unknown = [r for r in results if "hold_unknown" in clean(r.get("policy_layer_status"))]
    exact_eval = [r for r in results if str(r.get("exact_fill_layer_status", "")).startswith("evaluated")]
    exact_scored = [r for r in exact_eval if r.get("exact_fill_match") in {"true", "false"}]
    exact_matches = [r for r in exact_scored if r.get("exact_fill_match") == "true"]
    mgmt_eval = [r for r in results if r.get("management_layer_status") == "evaluated_family_proxy"]
    mgmt_matches = [r for r in mgmt_eval if r.get("management_match") == "true"]
    mgmt_unresolved = [r for r in mgmt_eval if r.get("management_match") == "family_only_unresolved"]
    return {
        "row_count": len(results),
        "policy_status_counts": Counter(clean(r.get("policy_layer_status")) for r in results),
        "target_action_counts": Counter(clean(r.get("target_policy_action")) for r in results),
        "predicted_action_counts": Counter(clean(r.get("predicted_policy_action")) for r in results),
        "policy_evaluated": len(policy_eval),
        "policy_matches": len(policy_matches),
        "policy_accuracy": pct(len(policy_matches), len(policy_eval)),
        "hold_unknown_count": len(hold_unknown),
        "exact_status_counts": Counter(clean(r.get("exact_fill_layer_status")) for r in results),
        "exact_evaluated": len(exact_eval),
        "exact_scored": len(exact_scored),
        "exact_matches": len(exact_matches),
        "exact_accuracy": pct(len(exact_matches), len(exact_scored)),
        "management_status_counts": Counter(clean(r.get("management_layer_status")) for r in results),
        "management_evaluated": len(mgmt_eval),
        "management_matches": len(mgmt_matches),
        "management_unresolved": len(mgmt_unresolved),
        "management_accuracy": pct(len(mgmt_matches), len([r for r in mgmt_eval if r.get("management_match") in {"true", "false"}])),
        "mapping_proposal_rows": len(mapping_rows),
        "top_policy_mismatches": [
            r
            for r in results
            if r.get("policy_layer_status") == "evaluated" and r.get("policy_match") == "false"
        ][:20],
        "exact_evaluated_rows": exact_eval,
    }


def md_counter(counter: Counter[str]) -> list[str]:
    if not counter:
        return ["- none"]
    return [f"- `{key}`: {value}" for key, value in counter.most_common()]


def write_report(summary: dict[str, Any], output: Path) -> None:
    lines: list[str] = [
        "# Craig v1 Decision Replay Validation Report",
        "",
        "Generated by `scripts/run_craig_v1_decision_replay.py`.",
        "",
        "## Summary",
        "",
        f"- Feature/replay rows: {summary['row_count']}",
        f"- Policy replay evaluated rows: {summary['policy_evaluated']}",
        f"- Policy replay matches: {summary['policy_matches']} ({summary['policy_accuracy']})",
        f"- Hold/unknown policy outputs: {summary['hold_unknown_count']} (not treated as failures when evidence is insufficient)",
        f"- Exact fill replay evaluated rows: {summary['exact_evaluated']} ({summary['exact_scored']} scored against win/loss/no-fill outcomes)",
        f"- Exact fill replay matches: {summary['exact_matches']} ({summary['exact_accuracy']})",
        f"- Management replay evaluated rows: {summary['management_evaluated']}",
        f"- Management family matches: {summary['management_matches']} ({summary['management_accuracy']}); unresolved family-only cases: {summary['management_unresolved']}",
        f"- Mapping v1.1 proposal rows: {summary['mapping_proposal_rows']}",
        "",
        "## Policy Layer",
        "",
        "Target action counts:",
        "",
        *md_counter(summary["target_action_counts"]),
        "",
        "Predicted action counts:",
        "",
        *md_counter(summary["predicted_action_counts"]),
        "",
        "Policy status counts:",
        "",
        *md_counter(summary["policy_status_counts"]),
        "",
        "## Exact Fill Layer",
        "",
        "Exact fill status counts:",
        "",
        *md_counter(summary["exact_status_counts"]),
        "",
        "The exact fill layer is intentionally limited to numeric exact/partial geometry rows. Frame-relative rows are excluded rather than assigned invented prices.",
        "",
        "## Management Layer",
        "",
        "Management status counts:",
        "",
        *md_counter(summary["management_status_counts"]),
        "",
        "Most management rows remain family-proxy validation because frame-relative geometry does not provide exact BE, partial, runner, or manual exit trigger prices.",
        "",
        "## Mapping v1.1 Proposal",
        "",
        f"Saved to `{MAPPING_PROPOSAL.relative_to(ROOT)}`.",
        "",
        "The 10 manual-review mapping rows are not changed in the source files. The proposal separates broad raw decision labels from row-level outcome and management evidence.",
        "",
        "## Mismatch Audit",
        "",
    ]
    mismatches = summary["top_policy_mismatches"]
    if not mismatches:
        lines.append("- No evaluated policy mismatches.")
    else:
        for row in mismatches[:15]:
            lines.append(
                "- "
                f"`{row['context_id']}` target=`{row['target_policy_action']}` "
                f"predicted=`{row['predicted_policy_action']}` "
                f"score={row['policy_score']} trace=`{row['policy_trace']}`"
            )
    lines.extend(
        [
            "",
            "## Leakage Guardrails Checked",
            "",
            "- Policy prediction uses runtime feature columns and does not use realized result, `rule_outcome_feature`, or future candles.",
            "- Exact fill simulation runs only in the exact fill layer and only for rows marked `eligible_for_fill_backtest=true`.",
            "- Management validation is separated from policy replay and reports family-only unresolved cases.",
            "- News/macro features are placeholders until an external normalized calendar is joined.",
            "- Unknown/context-only rows are excluded or marked hold/unknown rather than counted as Craig-decision failures.",
            "",
            "## Output Files",
            "",
            f"- `{FEATURE_MATRIX.relative_to(ROOT)}`",
            f"- `{REPLAY_RESULTS.relative_to(ROOT)}`",
            f"- `{VALIDATION_REPORT.relative_to(ROOT)}`",
            f"- `{MAPPING_PROPOSAL.relative_to(ROOT)}`",
            f"- `{Path('outputs/craig_v1_rulebook.yaml')}`",
        ]
    )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Craig v1 decision replay.")
    parser.add_argument("--feature-matrix", default=str(FEATURE_MATRIX))
    parser.add_argument("--decision-units", default=str(DECISION_UNITS))
    parser.add_argument("--ohlcv-manifest", default=str(COVERAGE_MANIFEST))
    parser.add_argument("--canonical-mapping", default=str(CANONICAL_MAPPING))
    args = parser.parse_args()
    results, summary = run_replay(
        Path(args.feature_matrix),
        Path(args.decision_units),
        Path(args.ohlcv_manifest),
        Path(args.canonical_mapping),
    )
    print(f"wrote {REPLAY_RESULTS} rows={len(results)}")
    print(f"wrote {VALIDATION_REPORT}")
    print(f"policy_accuracy={summary['policy_accuracy']}")
    print(f"exact_accuracy={summary['exact_accuracy']}")
    print(f"management_accuracy={summary['management_accuracy']}")


if __name__ == "__main__":
    main()
