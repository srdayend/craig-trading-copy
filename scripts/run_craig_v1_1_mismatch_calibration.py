#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
from typing import Any

from build_craig_v1_features import (
    FEATURE_MATRIX,
    ROOT,
    clean,
    coverage_lookup,
    read_csv,
    safe_float,
    write_csv,
)
from run_craig_v1_decision_replay import (
    COVERAGE_MANIFEST,
    DECISION_UNITS,
    exact_fill_replay,
    index_decision_units,
    management_replay,
    pct,
    predict_policy_action as predict_policy_action_v1,
    target_policy_action,
)


OUT_DIR = ROOT / "outputs"
V1_REPLAY_RESULTS = OUT_DIR / "craig_v1_replay_results.csv"
V1_1_MISMATCH_AUDIT = OUT_DIR / "craig_v1_1_mismatch_audit.csv"
V1_1_RULEBOOK = OUT_DIR / "craig_v1_1_rulebook.yaml"
V1_1_REPLAY_RESULTS = OUT_DIR / "craig_v1_1_replay_results.csv"
V1_1_VALIDATION_REPORT = OUT_DIR / "craig_v1_1_validation_report.md"

TAKE_THRESHOLD_V1_1 = 4.5
HTF_RELATIVE_VETO_MAX_SCORE_V1_1 = 3.0
HARD_FVG_CANCEL_MAX_SCORE_V1_1 = 3.5

MISMATCH_TAGS = {
    "feature_gap": "Missing or weak runtime proxy for the Craig context recorded in gold.",
    "threshold_issue": "The v1 score threshold or veto boundary is too coarse for this row.",
    "fvg_freshness_misread": "The auto FVG freshness state appears too terminal or contradictory.",
    "htf_bias_overweight": "HTF bias or relative-laggard evidence was weighted too heavily.",
    "time_confidence_issue": "Decision time was approximate enough to distort replay features.",
    "frame_relative_geometry_issue": "Frame/prose-relative geometry limits exact numeric interpretation.",
}


def boolish(value: object) -> bool:
    return clean(value).lower() == "true"


def split_pipe(value: object) -> set[str]:
    return {clean(part) for part in clean(value).split("|") if clean(part)}


def policy_status_and_match(target: str, predicted: str) -> tuple[str, str]:
    if target == "exclude_context_prior":
        return "excluded_context_prior", ""
    if predicted == "hold_unknown":
        if target in {"wait", "management"}:
            return "hold_unknown_not_failure", "not_scored_hold_unknown"
        return "evaluated_hold_unknown", "false"
    return "evaluated", str(predicted == target).lower()


def predict_policy_action_v1_1(row: dict[str, str]) -> tuple[str, str, float]:
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
    fvg_active = row.get("feature_fvg_active_for_side") == "true"
    htf_aligned = row.get("feature_htf_bias_aligned_with_candidate", "")
    geometry_mode = row.get("source_geometry_mode", "")
    time_confidence = row.get("runtime_time_parse_confidence", "")

    if no_chase in {"high_far_from_entry", "high_rr_compressed"}:
        trace.append(f"plan_entry:no_chase={no_chase}")
        return "pass", "|".join(trace), quality

    if fvg_freshness == "fully_mitigated" and quality < 5:
        hard_numeric_cancel = (
            not fvg_active
            and geometry_mode in {"numeric_exact", "numeric_partial"}
            and time_confidence in {"high", "medium"}
            and quality < HARD_FVG_CANCEL_MAX_SCORE_V1_1
        )
        if hard_numeric_cancel:
            trace.append("plan_entry:fvg_terminal_numeric_low_confluence")
            return "cancel", "|".join(trace), quality
        trace.append("calibration:fvg_freshness_softened")

    trace.append("rank_select_symbol")
    if (
        row.get("feature_primary_symbol_relative_state") == "relative_laggard"
        and htf_aligned == "false"
        and quality < HTF_RELATIVE_VETO_MAX_SCORE_V1_1
    ):
        trace.append("calibration:htf_relative_veto_only_when_very_weak")
        return "wait", "|".join(trace), quality

    trace.append("wait_for_setup")
    if quality >= TAKE_THRESHOLD_V1_1:
        trace.append(f"calibration:balanced_confluence_take_threshold={TAKE_THRESHOLD_V1_1}")
        return "take", "|".join(trace), quality
    if quality >= 3.5:
        trace.append("setup_partial_wait")
        return "wait", "|".join(trace), quality
    trace.append("insufficient_runtime_confluence")
    return "wait", "|".join(trace), quality


def source_context_tags(row: dict[str, str]) -> set[str]:
    tags: set[str] = set()
    for column in (
        "source_setup_family_tags_for_audit",
        "source_entry_model_for_audit",
        "source_special_condition_tags_for_audit",
        "source_invalidation_family_for_audit",
    ):
        tags.update(split_pipe(row.get(column, "")))
    return tags


def add_tag(tags: list[str], tag: str) -> None:
    if tag not in tags:
        tags.append(tag)


def tag_mismatch(feature_row: dict[str, str], v1_row: dict[str, str]) -> tuple[list[str], str, str]:
    tags: list[str] = []
    reasons: list[str] = []
    target = v1_row.get("target_policy_action", "")
    predicted = v1_row.get("predicted_policy_action", "")
    score = safe_float(v1_row.get("policy_score")) or 0.0
    policy_trace = v1_row.get("policy_trace", "")
    setup_trace = feature_row.get("feature_setup_quality_trace", "")
    source_tags = source_context_tags(feature_row)
    time_confidence = feature_row.get("runtime_time_parse_confidence", "")
    fvg_freshness = feature_row.get("feature_fvg_latest_freshness_for_side", "")
    geometry_mode = feature_row.get("source_geometry_mode", "")

    if (
        feature_row.get("runtime_feature_status") != "ready"
        or predicted == "hold_unknown"
        or score < 3.5
        or source_tags.intersection({"macro_news", "news_macro", "pattern_hs", "order_block"})
    ):
        add_tag(tags, "feature_gap")
        reasons.append("runtime features do not fully encode the annotated setup context")

    if time_confidence in {"low_default_time", "low_phrase_anchor", "medium_phrase_anchor"}:
        add_tag(tags, "time_confidence_issue")
        reasons.append(f"time confidence is {time_confidence}")

    if geometry_mode in {"frame_relative", "prose_only"}:
        add_tag(tags, "frame_relative_geometry_issue")
        reasons.append(f"geometry mode is {geometry_mode}")

    if fvg_freshness in {"fully_mitigated", "invalidated", "midpoint_touched"} and (
        predicted == "cancel" or "fvg" in source_tags or target == "take"
    ):
        add_tag(tags, "fvg_freshness_misread")
        reasons.append(f"latest FVG freshness is {fvg_freshness}")

    if (
        feature_row.get("feature_htf_bias_aligned_with_candidate") == "false"
        or "htf_against" in setup_trace
        or "symbol_not_clean_enough" in policy_trace
    ):
        add_tag(tags, "htf_bias_overweight")
        reasons.append("HTF/relative-strength evidence overrode LTF setup evidence")

    if (
        target == "take"
        and predicted in {"wait", "cancel", "pass"}
        and score >= 3.5
    ) or (target != "take" and predicted == "take") or predicted in {"cancel", "pass"}:
        add_tag(tags, "threshold_issue")
        reasons.append("v1 decision boundary is too coarse for this setup score")

    if not tags:
        add_tag(tags, "feature_gap")
        reasons.append("mismatch is not explained by a single calibrated threshold")

    primary_order = [
        "fvg_freshness_misread" if predicted == "cancel" else "",
        "threshold_issue" if target == "take" and predicted == "wait" and score >= 3.5 else "",
        "htf_bias_overweight" if "symbol_not_clean_enough" in policy_trace else "",
        "time_confidence_issue",
        "frame_relative_geometry_issue",
        "htf_bias_overweight",
        "threshold_issue",
        "feature_gap",
    ]
    primary = next((tag for tag in primary_order if tag and tag in tags), tags[0])
    return tags, primary, "; ".join(dict.fromkeys(reasons))


def audit_priority(target: str, predicted: str, status: str) -> str:
    if target == "take" and predicted in {"wait", "cancel"}:
        return "p0_take_wait_cancel"
    if predicted == "hold_unknown" or status == "evaluated_hold_unknown":
        return "p2_hold_unknown"
    return "p1_other_policy_mismatch"


def summarize_policy(rows: list[dict[str, object]]) -> dict[str, Any]:
    policy_eval = [r for r in rows if clean(r.get("policy_layer_status")) == "evaluated"]
    policy_matches = [r for r in policy_eval if clean(r.get("policy_match")) == "true"]
    false_eval = [r for r in policy_eval if clean(r.get("policy_match")) == "false"]
    target_take_eval = [r for r in policy_eval if clean(r.get("target_policy_action")) == "take"]
    target_take_matches = [r for r in target_take_eval if clean(r.get("policy_match")) == "true"]
    return {
        "row_count": len(rows),
        "policy_evaluated": len(policy_eval),
        "policy_matches": len(policy_matches),
        "policy_accuracy": pct(len(policy_matches), len(policy_eval)),
        "policy_accuracy_float": len(policy_matches) / len(policy_eval) if policy_eval else 0.0,
        "target_action_counts": Counter(clean(r.get("target_policy_action")) for r in rows),
        "predicted_action_counts": Counter(clean(r.get("predicted_policy_action")) for r in rows),
        "status_counts": Counter(clean(r.get("policy_layer_status")) for r in rows),
        "evaluated_mismatch_combo_counts": Counter(
            f"{clean(r.get('target_policy_action'))}->{clean(r.get('predicted_policy_action'))}"
            for r in false_eval
        ),
        "take_eval": len(target_take_eval),
        "take_matches": len(target_take_matches),
        "take_recall": pct(len(target_take_matches), len(target_take_eval)),
        "take_wait_mismatches": sum(
            1
            for r in false_eval
            if clean(r.get("target_policy_action")) == "take"
            and clean(r.get("predicted_policy_action")) == "wait"
        ),
        "take_cancel_mismatches": sum(
            1
            for r in false_eval
            if clean(r.get("target_policy_action")) == "take"
            and clean(r.get("predicted_policy_action")) == "cancel"
        ),
    }


def summarize_exact_and_management(rows: list[dict[str, object]]) -> dict[str, Any]:
    exact_eval = [r for r in rows if clean(r.get("exact_fill_layer_status")).startswith("evaluated")]
    exact_scored = [r for r in exact_eval if clean(r.get("exact_fill_match")) in {"true", "false"}]
    exact_matches = [r for r in exact_scored if clean(r.get("exact_fill_match")) == "true"]
    management_eval = [r for r in rows if clean(r.get("management_layer_status")) == "evaluated_family_proxy"]
    management_scored = [r for r in management_eval if clean(r.get("management_match")) in {"true", "false"}]
    management_matches = [r for r in management_scored if clean(r.get("management_match")) == "true"]
    return {
        "exact_evaluated": len(exact_eval),
        "exact_scored": len(exact_scored),
        "exact_matches": len(exact_matches),
        "exact_accuracy": pct(len(exact_matches), len(exact_scored)),
        "management_evaluated": len(management_eval),
        "management_scored": len(management_scored),
        "management_matches": len(management_matches),
        "management_accuracy": pct(len(management_matches), len(management_scored)),
    }


def md_counter(counter: Counter[str], limit: int | None = None) -> list[str]:
    if not counter:
        return ["- none"]
    items = counter.most_common(limit)
    return [f"- `{key}`: {value}" for key, value in items]


def pp_delta(v1: dict[str, Any], v11: dict[str, Any]) -> str:
    delta = (v11["policy_accuracy_float"] - v1["policy_accuracy_float"]) * 100
    return f"{delta:+.1f} pp"


def build_replay_and_audit(
    feature_matrix: Path,
    decision_units: Path,
    manifest: Path,
    v1_replay_path: Path,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, Any]]:
    feature_rows = read_csv(feature_matrix)
    unit_by_id = index_decision_units(decision_units)
    coverage = coverage_lookup(read_csv(manifest))
    v1_rows = read_csv(v1_replay_path)
    v1_by_id = {row["context_id"]: row for row in v1_rows}

    replay_rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    regressions: list[dict[str, object]] = []
    improvements: list[dict[str, object]] = []

    for row in feature_rows:
        unit = unit_by_id[row["context_id"]]
        target = target_policy_action(row)
        predicted, trace, score = predict_policy_action_v1_1(row)
        policy_status, policy_match = policy_status_and_match(target, predicted)
        exact = exact_fill_replay(row, unit, coverage)
        management = management_replay(row, unit)
        out: dict[str, object] = {
            "context_id": row["context_id"],
            "video_id": row.get("video_id", ""),
            "runtime_market_date": row.get("runtime_market_date", ""),
            "runtime_decision_time_ny": row.get("runtime_decision_time_ny", ""),
            "runtime_primary_symbol": row.get("runtime_primary_symbol", ""),
            "runtime_candidate_side": row.get("runtime_candidate_side_from_gold_row", ""),
            "target_policy_action": target,
            "predicted_policy_action": predicted,
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
        out.update(management)
        replay_rows.append(out)

        v1_row = v1_by_id[row["context_id"]]
        v1_match = clean(v1_row.get("policy_match"))
        v1_status = clean(v1_row.get("policy_layer_status"))
        v1_predicted = clean(v1_row.get("predicted_policy_action"))
        if v1_match == "false":
            tags, primary, rationale = tag_mismatch(row, v1_row)
            v11_resolution = "resolved" if policy_match == "true" else "still_mismatch"
            audit_rows.append(
                {
                    "priority": audit_priority(target, v1_predicted, v1_status),
                    "context_id": row["context_id"],
                    "video_id": row.get("video_id", ""),
                    "runtime_market_date": row.get("runtime_market_date", ""),
                    "runtime_decision_time_ny": row.get("runtime_decision_time_ny", ""),
                    "runtime_primary_symbol": row.get("runtime_primary_symbol", ""),
                    "runtime_candidate_side": row.get("runtime_candidate_side_from_gold_row", ""),
                    "target_policy_action": target,
                    "predicted_policy_action_v1": v1_predicted,
                    "predicted_policy_action_v1_1": predicted,
                    "target_predicted_combo_v1": f"{target}->{v1_predicted}",
                    "policy_layer_status_v1": v1_status,
                    "policy_match_v1": v1_match,
                    "policy_match_v1_1": policy_match,
                    "v1_1_resolution": v11_resolution,
                    "primary_mismatch_tag": primary,
                    "mismatch_tags": "|".join(tags),
                    "tag_rationale": rationale,
                    "v1_policy_score": v1_row.get("policy_score", ""),
                    "v1_policy_trace": v1_row.get("policy_trace", ""),
                    "v1_1_policy_score": score,
                    "v1_1_policy_trace": trace,
                    "runtime_feature_status": row.get("runtime_feature_status", ""),
                    "runtime_time_parse_confidence": row.get("runtime_time_parse_confidence", ""),
                    "runtime_time_parse_mode": row.get("runtime_time_parse_mode", ""),
                    "runtime_session_phase": row.get("runtime_session_phase", ""),
                    "feature_setup_quality_score": row.get("feature_setup_quality_score", ""),
                    "feature_setup_quality_trace": row.get("feature_setup_quality_trace", ""),
                    "feature_fvg_active_for_side": row.get("feature_fvg_active_for_side", ""),
                    "feature_fvg_latest_freshness_for_side": row.get("feature_fvg_latest_freshness_for_side", ""),
                    "feature_htf_bias": row.get("feature_htf_bias", ""),
                    "feature_htf_bias_confidence": row.get("feature_htf_bias_confidence", ""),
                    "feature_htf_bias_aligned_with_candidate": row.get("feature_htf_bias_aligned_with_candidate", ""),
                    "feature_primary_symbol_relative_state": row.get("feature_primary_symbol_relative_state", ""),
                    "feature_no_chase_risk": row.get("feature_no_chase_risk", ""),
                    "source_geometry_mode": row.get("source_geometry_mode", ""),
                    "source_setup_family_tags_for_audit": row.get("source_setup_family_tags_for_audit", ""),
                    "source_entry_model_for_audit": row.get("source_entry_model_for_audit", ""),
                    "source_special_condition_tags_for_audit": row.get("source_special_condition_tags_for_audit", ""),
                }
            )

        v11_match = clean(policy_match)
        if v1_status == "evaluated" and v1_match == "false" and policy_status == "evaluated" and v11_match == "true":
            improvements.append(
                {
                    "context_id": row["context_id"],
                    "target": target,
                    "v1": v1_predicted,
                    "v1_1": predicted,
                }
            )
        if v1_status == "evaluated" and v1_match == "true" and not (
            policy_status == "evaluated" and v11_match == "true"
        ):
            regressions.append(
                {
                    "context_id": row["context_id"],
                    "target": target,
                    "v1": v1_predicted,
                    "v1_1": predicted,
                }
            )

    audit_rows.sort(key=lambda r: (r["priority"], r["target_predicted_combo_v1"], r["context_id"]))
    write_csv(V1_1_REPLAY_RESULTS, replay_rows)
    write_csv(V1_1_MISMATCH_AUDIT, audit_rows)

    comparison = {
        "v1": summarize_policy([dict(r) for r in v1_rows]),
        "v1_1": summarize_policy(replay_rows),
        "exact_management": summarize_exact_and_management(replay_rows),
        "audit_tag_counts": Counter(
            tag for row in audit_rows for tag in clean(row.get("mismatch_tags")).split("|") if tag
        ),
        "audit_primary_tag_counts": Counter(clean(row.get("primary_mismatch_tag")) for row in audit_rows),
        "audit_priority_counts": Counter(clean(row.get("priority")) for row in audit_rows),
        "audit_rows": len(audit_rows),
        "resolved_audit_rows": sum(1 for row in audit_rows if row.get("v1_1_resolution") == "resolved"),
        "improvements": improvements,
        "regressions": regressions,
    }
    return replay_rows, audit_rows, comparison


def write_rulebook(comparison: dict[str, Any], output: Path) -> None:
    v1 = comparison["v1"]
    v11 = comparison["v1_1"]
    lines = [
        "version: craig_v1_1",
        "inherits_from: craig_v1_0",
        "generated_for: gold_v03_decision_units_v1",
        "generated_by: scripts/run_craig_v1_1_mismatch_calibration.py",
        "objective: >",
        "  Mismatch-driven calibration of the v1 policy layer. This update",
        "  does not add new features, does not mutate gold labels, and does",
        "  not use future candles or realized outcomes for policy decisions.",
        "",
        "source_artifacts:",
        "  feature_matrix: outputs/craig_v1_feature_matrix.csv",
        "  v1_replay_results: outputs/craig_v1_replay_results.csv",
        "  v1_validation_report: outputs/craig_v1_validation_report.md",
        "  v1_rulebook: outputs/craig_v1_rulebook.yaml",
        "  decision_units: outputs/gold_v03_decision_units_v1.csv",
        "",
        "calibration_scope:",
        "  mode: mismatch_driven_policy_layer_only",
        "  no_new_feature_expansion: true",
        "  exact_fill_layer_changed: false",
        "  management_layer_changed: false",
        "  preserve_v1_inputs_and_gold_labels: true",
        "",
        "v1_baseline:",
        f"  policy_evaluated_rows: {v1['policy_evaluated']}",
        f"  policy_matches: {v1['policy_matches']}",
        f"  policy_accuracy: \"{v1['policy_accuracy']}\"",
        f"  target_take_recall: \"{v1['take_matches']}/{v1['take_eval']} ({v1['take_recall']})\"",
        f"  take_wait_mismatches: {v1['take_wait_mismatches']}",
        f"  take_cancel_mismatches: {v1['take_cancel_mismatches']}",
        "",
        "v1_1_result:",
        f"  policy_evaluated_rows: {v11['policy_evaluated']}",
        f"  policy_matches: {v11['policy_matches']}",
        f"  policy_accuracy: \"{v11['policy_accuracy']}\"",
        f"  policy_accuracy_delta_vs_v1: \"{pp_delta(v1, v11)}\"",
        f"  target_take_recall: \"{v11['take_matches']}/{v11['take_eval']} ({v11['take_recall']})\"",
        f"  take_wait_mismatches: {v11['take_wait_mismatches']}",
        f"  take_cancel_mismatches: {v11['take_cancel_mismatches']}",
        "",
        "policy_replay_calibrations:",
        "  fvg_freshness_softening:",
        "    v1_behavior: fully_mitigated_fvg_and_quality_below_5_implies_cancel",
        "    v1_1_behavior: >",
        "      Fully mitigated FVG is not terminal by itself when another active",
        "      same-side FVG exists, geometry is frame/prose-relative, or the",
        "      decision time is approximate. Continue to confluence scoring unless",
        "      numeric geometry, reliable time, no active FVG, and very low score",
        "      all point to a stale setup.",
        f"    hard_cancel_max_score: {HARD_FVG_CANCEL_MAX_SCORE_V1_1}",
        "  htf_bias_softening:",
        "    v1_behavior: relative_laggard_plus_htf_against_blocks_when_quality_below_5",
        "    v1_1_behavior: >",
        "      HTF-against and relative-laggard evidence demotes only very weak",
        "      LTF setups. Craig often still takes a framed FVG/SR entry when the",
        "      local setup is actionable.",
        f"    veto_only_when_quality_below: {HTF_RELATIVE_VETO_MAX_SCORE_V1_1}",
        "  balanced_confluence_take_threshold:",
        "    v1_threshold: 6.0",
        f"    v1_1_threshold: {TAKE_THRESHOLD_V1_1}",
        "    applies_when:",
        "      - runtime evidence is present",
        "      - candidate side is tradeable",
        "      - no hard no-chase flag is present",
        "      - no hard numeric stale-FVG cancel is present",
        "    principle: >",
        "      A Craig take often appears at medium confluence when the plan is",
        "      frame-defined and supported by FVG/SR/HTF context. v1 required",
        "      near-perfect proxy confluence and over-produced wait.",
        "",
        "unchanged_guardrails:",
        "  - hold_unknown_when_runtime_evidence_missing",
        "  - hold_unknown_when_candidate_side_is_not_tradeable",
        "  - no_chase_pass_for_high_far_from_entry_or_compressed_rr",
        "  - no_future_candles_for_policy_decision",
        "  - no_realized_outcome_or_rule_outcome_feature_for_policy_decision",
        "  - frame_relative_rows_remain_excluded_from_exact_fill_backtest",
        "",
        "known_limits:",
        "  - news_macro_features_remain_placeholder_not_joined",
        "  - frame_relative_geometry_still_limits exact entry and cancellation logic",
        "  - v1_1 improves take recall but still cannot identify no_fill/pass/cancel without richer runtime geometry",
        "  - two v1-correct wait rows regress to take under the medium-confluence threshold",
    ]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_validation_report(comparison: dict[str, Any], output: Path) -> None:
    v1 = comparison["v1"]
    v11 = comparison["v1_1"]
    exact_management = comparison["exact_management"]
    improvements = comparison["improvements"]
    regressions = comparison["regressions"]
    improvement_counter = Counter(f"{r['target']}:{r['v1']}->{r['v1_1']}" for r in improvements)
    regression_counter = Counter(f"{r['target']}:{r['v1']}->{r['v1_1']}" for r in regressions)
    lines = [
        "# Craig v1.1 Mismatch-Driven Calibration Report",
        "",
        "Generated by `scripts/run_craig_v1_1_mismatch_calibration.py`.",
        "",
        "## Overall Assessment: Share with caveats",
        "",
        "v1.1 improves the evaluated policy layer by correcting the dominant take-underprediction pattern without adding new features. The improvement is real but still limited by frame-relative geometry, approximate decision-time anchors, and the missing news/macro join.",
        "",
        "## v1 vs v1.1 Policy Replay",
        "",
        "| Metric | v1 | v1.1 | Delta |",
        "| --- | ---: | ---: | ---: |",
        f"| Evaluated policy rows | {v1['policy_evaluated']} | {v11['policy_evaluated']} | 0 |",
        f"| Policy matches | {v1['policy_matches']} | {v11['policy_matches']} | {v11['policy_matches'] - v1['policy_matches']:+d} |",
        f"| Policy accuracy | {v1['policy_accuracy']} | {v11['policy_accuracy']} | {pp_delta(v1, v11)} |",
        f"| Target=take recall | {v1['take_matches']}/{v1['take_eval']} ({v1['take_recall']}) | {v11['take_matches']}/{v11['take_eval']} ({v11['take_recall']}) | {v11['take_matches'] - v1['take_matches']:+d} matches |",
        f"| take->wait mismatches | {v1['take_wait_mismatches']} | {v11['take_wait_mismatches']} | {v11['take_wait_mismatches'] - v1['take_wait_mismatches']:+d} |",
        f"| take->cancel mismatches | {v1['take_cancel_mismatches']} | {v11['take_cancel_mismatches']} | {v11['take_cancel_mismatches'] - v1['take_cancel_mismatches']:+d} |",
        "",
        "## v1 Mismatch Classification",
        "",
        f"- Audited v1 policy mismatch rows: {comparison['audit_rows']}",
        f"- Resolved by v1.1: {comparison['resolved_audit_rows']}",
        "",
        "Mismatch priority counts:",
        "",
        *md_counter(comparison["audit_priority_counts"]),
        "",
        "v1 evaluated mismatch combos:",
        "",
        *md_counter(v1["evaluated_mismatch_combo_counts"], limit=20),
        "",
        "Mismatch tag counts:",
        "",
        *md_counter(comparison["audit_tag_counts"]),
        "",
        "Primary tag counts:",
        "",
        *md_counter(comparison["audit_primary_tag_counts"]),
        "",
        "## Priority Finding: target=take, predicted=wait/cancel",
        "",
        "The v1 policy layer is too reluctant to take. In evaluated rows, `take->wait` was the largest mismatch combo and `take->cancel` came from an over-terminal FVG freshness rule. v1.1 changes only repeated principles:",
        "",
        "1. A `fully_mitigated` latest FVG is not automatically stale when another active same-side FVG exists or the entry is frame-relative.",
        "2. HTF-against plus relative-laggard should demote very weak setups, not veto every medium LTF FVG/SR setup.",
        "3. Medium confluence (`setup_quality_score >= 4.5`) is actionable when no hard no-chase or numeric stale-FVG cancel condition is present.",
        "",
        "## Changes Applied",
        "",
        f"- Lowered the take threshold from `6.0` to `{TAKE_THRESHOLD_V1_1}` under guardrails.",
        f"- Softened the HTF/relative-laggard veto from quality `<5.0` to `<{HTF_RELATIVE_VETO_MAX_SCORE_V1_1}`.",
        "- Replaced the broad fully-mitigated-FVG cancel with a hard cancel only for numeric geometry, reliable time, no active FVG, and very low confluence.",
        "- Left exact fill replay and management replay unchanged.",
        "",
        "## Improvements And Regressions",
        "",
        "Evaluated-row improvements by transition:",
        "",
        *md_counter(improvement_counter),
        "",
        "Evaluated-row regressions by transition:",
        "",
        *md_counter(regression_counter),
        "",
        "Regression rows:",
        "",
    ]
    if regressions:
        for row in regressions:
            lines.append(f"- `{row['context_id']}` target=`{row['target']}` v1=`{row['v1']}` v1.1=`{row['v1_1']}`")
    else:
        lines.append("- none")

    lines.extend(
        [
            "",
            "## Exact Fill And Management Layers",
            "",
            f"- Exact fill evaluated rows: {exact_management['exact_evaluated']} ({exact_management['exact_scored']} scored); matches: {exact_management['exact_matches']} ({exact_management['exact_accuracy']})",
            f"- Management evaluated rows: {exact_management['management_evaluated']} ({exact_management['management_scored']} scored); matches: {exact_management['management_matches']} ({exact_management['management_accuracy']})",
            "- These layers are intentionally unchanged in v1.1, because this stage calibrates policy mismatch only.",
            "",
            "## Validation Notes",
            "",
            "- The v1.1 predictor uses the same feature matrix columns already produced for v1.",
            "- The rule changes do not read realized outcome, `rule_outcome_feature`, or future candles for policy prediction.",
            "- The mismatch audit includes hold-unknown false rows for diagnosis, but policy accuracy is still computed on `policy_layer_status=evaluated`, matching v1 reporting.",
            "- Remaining no-fill/pass/cancel errors are not safely fixable without better runtime geometry and event-time features.",
            "",
            "## Output Files",
            "",
            f"- `{V1_1_MISMATCH_AUDIT.relative_to(ROOT)}`",
            f"- `{V1_1_RULEBOOK.relative_to(ROOT)}`",
            f"- `{V1_1_REPLAY_RESULTS.relative_to(ROOT)}`",
            f"- `{V1_1_VALIDATION_REPORT.relative_to(ROOT)}`",
        ]
    )
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Craig v1.1 mismatch-driven calibration.")
    parser.add_argument("--feature-matrix", default=str(FEATURE_MATRIX))
    parser.add_argument("--decision-units", default=str(DECISION_UNITS))
    parser.add_argument("--ohlcv-manifest", default=str(COVERAGE_MANIFEST))
    parser.add_argument("--v1-replay-results", default=str(V1_REPLAY_RESULTS))
    args = parser.parse_args()

    replay_rows, audit_rows, comparison = build_replay_and_audit(
        Path(args.feature_matrix),
        Path(args.decision_units),
        Path(args.ohlcv_manifest),
        Path(args.v1_replay_results),
    )
    write_rulebook(comparison, V1_1_RULEBOOK)
    write_validation_report(comparison, V1_1_VALIDATION_REPORT)

    v1 = comparison["v1"]
    v11 = comparison["v1_1"]
    print(f"wrote {V1_1_MISMATCH_AUDIT} rows={len(audit_rows)}")
    print(f"wrote {V1_1_RULEBOOK}")
    print(f"wrote {V1_1_REPLAY_RESULTS} rows={len(replay_rows)}")
    print(f"wrote {V1_1_VALIDATION_REPORT}")
    print(f"policy_accuracy_v1={v1['policy_accuracy']}")
    print(f"policy_accuracy_v1_1={v11['policy_accuracy']}")
    print(f"policy_accuracy_delta={pp_delta(v1, v11)}")


if __name__ == "__main__":
    main()
