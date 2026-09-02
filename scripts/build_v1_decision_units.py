#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "processed" / "gold_context_trades"
OUT_DIR = ROOT / "outputs"

TRADE_PATH = DATA_DIR / "gold_v03_trade_context_queue.csv"
RULE_PATH = DATA_DIR / "gold_v03_rule_seed_queue.csv"
HOLD_PATH = DATA_DIR / "gold_v03_hold_context_queue.csv"

OUT_DECISION_UNITS = OUT_DIR / "gold_v03_decision_units_v1.csv"
OUT_MAPPING = OUT_DIR / "gold_v03_canonical_mapping_v1.csv"
OUT_AUDIT = OUT_DIR / "gold_v03_v1_normalization_audit.md"
OUT_SUMMARY = OUT_DIR / "gold_v03_v1_model_eligibility_summary.json"
OUT_OHLCV_MANIFEST = OUT_DIR / "gold_v03_v1_ohlcv_coverage_manifest.csv"

CORE_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def low(value: object) -> str:
    return clean(value).lower()


def whole_number(value: str) -> float | None:
    text = clean(value)
    if not text:
        return None
    normalized = text.replace("$", "").replace(",", "").strip()
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", normalized):
        return float(normalized)
    return None


def is_exact_number(value: str) -> bool:
    return whole_number(value) is not None


def parse_signed_money(text: str) -> float | None:
    raw = clean(text)
    if not raw:
        return None
    direct = re.search(r"([+-])\s*(?:about\s*)?\$?\s*(\d[\d,]*(?:\.\d+)?)", raw, flags=re.IGNORECASE)
    if direct:
        sign = -1.0 if direct.group(1) == "-" else 1.0
        return sign * float(direct.group(2).replace(",", ""))
    dollar = re.search(r"\$\s*(\d[\d,]*(?:\.\d+)?)", raw)
    if not dollar:
        return None
    amount = float(dollar.group(1).replace(",", ""))
    before = raw[: dollar.start()].lower()
    after = raw[dollar.end() :].lower()
    context = (before[-30:] + " " + after[:30]).lower()
    if any(token in context for token in ["loss", "down", "drawdown", "stop", "fee loss"]):
        return -amount
    if any(token in context for token in ["profit", "winner", "win", "net p&l", "gross", "locked", "up"]):
        return amount
    return None


def parse_r_multiple(text: str) -> float | None:
    raw = clean(text)
    if not raw:
        return None
    match = re.search(r"([+-]?\d+(?:\.\d+)?)\s*r\b", raw, flags=re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def split_symbols(symbol_raw: str) -> tuple[str, str, list[str]]:
    text = clean(symbol_raw).upper().replace("/", "|")
    parts = [p.strip() for p in text.split("|") if p.strip()]
    canonical: list[str] = []
    for part in parts:
        if part == "ATOM":
            canonical.append("ATOMUSDT")
        else:
            canonical.append(part)
    if not canonical:
        return "", "", []
    primary = canonical[0]
    comparisons = [p for p in canonical[1:] if p != primary]
    return primary, "|".join(comparisons), canonical


def canonical_direction(raw: str, decision_type: str) -> tuple[str, str]:
    text = low(raw)
    dtype = low(decision_type)
    has_long = "long" in text
    has_short = "short" in text
    if "session_management" in text or dtype.startswith("session_"):
        return "none", "context_only"
    if "unknown" in text:
        return "unknown", "unknown"
    if has_long and has_short:
        if "to" in text or "flip" in text or "reassessment" in text:
            return "both_or_flip", "flip_or_reassessment"
        return "mixed_conditional", "mixed_conditional"
    if "mixed" in text:
        return "mixed_conditional", "mixed_conditional"
    if "conditional" in text and not (has_long or has_short):
        return "conditional", "conditional_unspecified"
    if has_long:
        if "conditional" in text or "or_" in text:
            return "long", "conditional_long"
        return "long", "long"
    if has_short:
        if "conditional" in text or "or_" in text:
            return "short", "conditional_short"
        return "short", "short"
    if "bullish_bias" in text:
        return "conditional", "bullish_bias_flexible"
    return "unknown", "unknown"


def decision_class(dtype: str, gold_status: str) -> str:
    text = low(dtype)
    status = low(gold_status)
    if text.startswith("session_") or text.startswith("daily_macro") or text.startswith("macro_"):
        return "session_context"
    if text.startswith("process_rule") or text.startswith("fvg_close_confirmation_filter"):
        return "process_rule_context"
    if "no_chase" in text or "pass" in text:
        return "pass_cancel"
    if "cancel" in text:
        return "pass_cancel"
    if "no_fill" in text or "missed_fill" in text or "missed_order" in text:
        return "planned_no_fill"
    if "risk_management" in text or "management" in text or "runner_lock" in text or "early_exit" in text:
        if "executed" in text:
            return "management_context"
        return "process_rule_context"
    if "conditional" in text and "executed" not in text:
        return "conditional_setup"
    if "actionable_setup" in text:
        return "actionable_setup"
    if "executed_or_actionable" in text:
        if "actionable" in status and "trade" not in status:
            return "actionable_setup"
        return "executed_trade"
    if "executed" in text or text.startswith("actual_trade") or "trade" in text:
        if "context_ready" in status and "actionable" in status and "trade" not in status:
            return "actionable_setup"
        return "executed_trade"
    return "session_context"


def fill_state(dtype: str, cls: str) -> str:
    text = low(dtype)
    if cls == "executed_trade":
        return "filled"
    if cls == "management_context":
        return "managed_existing"
    if cls == "planned_no_fill":
        return "not_filled"
    if cls == "pass_cancel":
        if "cancel" in text:
            return "cancelled"
        return "passed"
    if cls in {"session_context", "process_rule_context"}:
        return "context_only"
    if cls in {"actionable_setup", "conditional_setup"}:
        if "no_trade" in text or "no_fill" in text:
            return "not_filled"
        return "planned_unknown_fill"
    return "unknown"


def decision_subtype(dtype: str, text_blob: str) -> str:
    text = (low(dtype) + " " + low(text_blob)).replace("-", "_")
    tags: list[str] = []
    checks = [
        ("winner", ["winner", "win", "profit", "+$"]),
        ("loss", ["loss", "drawdown", "-$"]),
        ("breakeven", ["breakeven", "break even", " be ", "near breakeven"]),
        ("reentry", ["reentry", "re-entry"]),
        ("manual_close", ["manual close", "manual tp", "manual flat"]),
        ("runner", ["runner"]),
        ("risk_reduction", ["risk reduction", "risk-free", "risk free", "move stop", "stop to be"]),
        ("execution_anomaly", ["fatfinger", "wrong size", "slippage", "bad fill", "order error"]),
        ("no_chase", ["no chase", "missed setup"]),
        ("no_fill", ["no fill", "missed fill", "missed_order"]),
        ("cancel", ["cancel"]),
        ("lower_quality", ["lower quality", "make shift"]),
    ]
    for tag, needles in checks:
        if any(n in text for n in needles):
            tags.append(tag)
    return "|".join(dict.fromkeys(tags)) or "generic"


def outcome_class(dtype: str, fill: str, realized: str, exit_result: str, rule_outcome: str) -> str:
    text = " ".join([low(dtype), low(realized), low(exit_result), low(rule_outcome)])
    text = text.replace("-", " ").replace("_", " ")
    if fill == "not_filled":
        return "no_fill"
    if fill == "cancelled":
        return "cancelled"
    if fill == "passed":
        return "pass"
    if fill == "context_only":
        return "context_only"
    if "be loss" in text or "winner then be" in text or "mixed" in text:
        return "mixed"
    if any(token in text for token in ["breakeven", "break even", "basically be", "near breakeven", "risk free"]) or re.search(r"\bbe\b", text):
        if any(token in text for token in ["+$", "profit", "winner"]) and any(token in text for token in ["-$", "loss"]):
            return "mixed"
        return "breakeven"
    if any(token in text for token in ["full loss", "-$", " loss", "drawdown", "stopped"]):
        return "loss"
    if any(token in text for token in ["+$", "+about $", "winner", " win", "profit", "tp", "locked", "large winner"]):
        return "win"
    if "complete setup" in text or "context held" in text:
        return "unknown"
    return "unknown"


def contains_any(text: str, needles: Iterable[str]) -> bool:
    return any(needle in text for needle in needles)


def setup_tags(row: dict[str, str], rule: dict[str, str]) -> str:
    text = " ".join(
        low(row.get(col, ""))
        for col in [
            "session_macro_context_ko",
            "scenario_tree_ko",
            "elliott_wave_context_ko",
            "structure_reference_ko",
            "setup_context_ko",
            "entry_plan_ko",
            "rule_feature_vector_seed_ko",
        ]
    )
    text += " " + " ".join(low(rule.get(col, "")) for col in ["scenario_feature", "wave_fib_feature", "setup_trigger_feature", "entry_feature"])
    tags: list[str] = []
    checks = [
        ("fvg", ["fvg", "fair value gap"]),
        ("choch", ["choch", "change of character"]),
        ("bos", [" bos ", "break of structure"]),
        ("sr_flip", ["support", "resistance", "sr", "underside", "overside", "retest level", "key level"]),
        ("trendline_channel", ["trendline", "trend line", "channel"]),
        ("liquidity_sweep", ["sweep", "liquidity", "equal high", "equal low"]),
        ("elliott_wave", ["elliott", "wave 3", "wave 4", "wave 5", "abc"]),
        ("fib_extension", ["fib", "2.618", "3.618", "4.618", "1.618"]),
        ("order_block", ["order block", " ob "]),
        ("pattern_hs", ["head and shoulders", "h&s", "neckline"]),
        ("htf_context", ["15m", "1h", "4h", "daily", "higher time frame", "htf"]),
        ("macro_news", ["news", "fomc", "tariff", "earnings", "nvidia", "fundamental"]),
        ("relative_strength", ["relative", "stronger", "weaker", "leader", "lag"]),
    ]
    for tag, needles in checks:
        if contains_any(text, needles):
            tags.append(tag)
    return "|".join(tags) or "prose_context"


def entry_model(row: dict[str, str], rule: dict[str, str], fill: str) -> str:
    text = " ".join([low(row.get("entry_plan_ko", "")), low(rule.get("entry_feature", "")), low(row.get("setup_context_ko", ""))])
    if fill in {"passed", "cancelled"} and "no chase" in text:
        return "no_chase_pass"
    if "midpoint" in text or "50%" in text:
        return "fvg_midpoint_limit"
    if "fvg" in text or "fair value gap" in text:
        return "fvg_zone_limit"
    if contains_any(text, ["underside", "overside", "retest", "support", "resistance", "key level"]):
        return "sr_retest_limit"
    if contains_any(text, ["close above", "close below", "breakout", "breakdown"]):
        return "breakout_confirmation"
    if contains_any(text, ["ladder", "scale", "deep buy", "deep sell"]):
        return "laddered_limit"
    if contains_any(text, ["market", "fast entry"]):
        return "fast_or_market_entry"
    if "frame_relative_or_about" in low(row.get("entry_price", "")):
        return "frame_relative_zone"
    return "prose_only"


def invalidation_family(row: dict[str, str], rule: dict[str, str]) -> str:
    text = " ".join([low(row.get("invalidation_condition_ko", "")), low(rule.get("invalidation_feature", "")), low(row.get("management_plan_ko", ""))])
    tags: list[str] = []
    checks = [
        ("fvg_invalidation", ["fvg", "fair value gap", "close through"]),
        ("key_level_reclaim", ["reclaim", "level", "support", "resistance", "underside", "overside"]),
        ("swing_stop", ["swing", "high", "low", "stop"]),
        ("no_follow_through", ["no follow", "fails", "failure", "doesn't hold", "does not hold"]),
        ("be_or_risk_stop", ["break even", "breakeven", " be ", "risk reduction"]),
        ("news_blackout", ["news", "fomc", "earnings", "tariff"]),
        ("rr_compression", ["rr", "risk reward", "too far", "chase"]),
    ]
    for tag, needles in checks:
        if contains_any(text, needles):
            tags.append(tag)
    return "|".join(tags) or "unknown"


def management_tags(row: dict[str, str], rule: dict[str, str]) -> str:
    text = " ".join([low(row.get("management_plan_ko", "")), low(row.get("live_thesis_changes_ko", "")), low(row.get("exit_result_ko", "")), low(rule.get("management_feature", ""))])
    tags: list[str] = []
    checks = [
        ("move_to_be", ["move stop", "breakeven", "break even", " to be", "stop to be"]),
        ("risk_reduce", ["risk reduction", "risk-free", "risk free", "reduce risk"]),
        ("partial_take", ["partial", "take some", "scale out"]),
        ("runner_hold", ["runner", "let it run"]),
        ("manual_exit", ["manual close", "manual tp", "close early", "flat"]),
        ("trail_structure", ["trail", "trailing", "trendline", "higher low", "lower high"]),
        ("daily_goal_preserve", ["daily goal", "goal", "done for the day"]),
        ("no_chase_or_cancel", ["no chase", "cancel"]),
        ("execution_anomaly", ["slippage", "wrong size", "fatfinger", "bad fill", "order error"]),
    ]
    for tag, needles in checks:
        if contains_any(text, needles):
            tags.append(tag)
    return "|".join(tags) or "none_stated"


def special_tags(row: dict[str, str], rule: dict[str, str]) -> str:
    text = " ".join(low(v) for v in list(row.values()) + list(rule.values()))
    tags: list[str] = []
    checks = [
        ("news_macro", ["news", "fomc", "tariff", "earnings", "nvidia", "fundamental"]),
        ("execution_anomaly", ["fatfinger", "wrong size", "slippage", "bad fill", "order error"]),
        ("after_loss_or_drawdown", ["after loss", "losing streak", "drawdown"]),
        ("daily_goal_or_pnl_pressure", ["daily goal", "title day", "day net", "p&l"]),
        ("lower_quality", ["lower quality", "make shift", "marginal"]),
        ("no_chase_discipline", ["no chase", "already touched", "ran too far"]),
        ("time_constraint", ["gym", "dinner", "overnight", "asia"]),
        ("video_recovery_issue", ["corrupt", "frame recovery", "legacy only"]),
    ]
    for tag, needles in checks:
        if contains_any(text, needles):
            tags.append(tag)
    return "|".join(tags) or "none"


def geometry(row: dict[str, str]) -> tuple[str, str]:
    values = [row.get("entry_price", ""), row.get("stop_price", ""), row.get("target_price", "")]
    exact_count = sum(1 for v in values if is_exact_number(v))
    text = " ".join(low(v) for v in values)
    if exact_count == 3:
        return "numeric_exact", "high_numeric"
    if exact_count >= 2:
        return "numeric_partial", "medium_numeric_partial"
    if "frame_relative" in text or "about" in text:
        return "frame_relative", "medium_frame_relative"
    if any(clean(v) for v in values):
        return "prose_only", "low_prose"
    return "unknown", "unknown"


def time_confidence(raw: str, market_window: str) -> str:
    text = low(raw)
    if not clean(market_window):
        return "low_missing_market_time"
    if text.startswith("high"):
        return "high"
    if text.startswith("medium_high"):
        return "medium_high"
    if text.startswith("medium"):
        return "medium"
    return "unknown"


def ohlcv_file_exists(date_text: str, symbol: str) -> bool:
    if not date_text or not symbol:
        return False
    dated = ROOT / "data" / "raw" / "binance_futures_live_dates" / date_text / f"{symbol}_1m_{date_text}_ny.csv"
    if dated.exists() and dated.stat().st_size > 100:
        return True
    if symbol in CORE_SYMBOLS:
        consolidated = ROOT / "data" / "raw" / "binance_futures_1m" / f"{symbol}_1m_20260223_20260822.csv"
        if consolidated.exists() and "2026-02-23" <= date_text <= "2026-08-22":
            return True
    return False


def ohlcv_path_status(date_text: str, symbol: str) -> tuple[str, str]:
    if not date_text or not symbol:
        return "missing_input", ""
    dated = ROOT / "data" / "raw" / "binance_futures_live_dates" / date_text / f"{symbol}_1m_{date_text}_ny.csv"
    if dated.exists() and dated.stat().st_size > 100:
        return "dated_file", str(dated)
    if symbol in CORE_SYMBOLS:
        consolidated = ROOT / "data" / "raw" / "binance_futures_1m" / f"{symbol}_1m_20260223_20260822.csv"
        if consolidated.exists() and "2026-02-23" <= date_text <= "2026-08-22":
            return "consolidated_file", str(consolidated)
    return "missing", ""


def parse_market_dates(date_text: str) -> list[str]:
    return re.findall(r"\d{4}-\d{2}-\d{2}", clean(date_text))


def ohlcv_status(date_text: str, symbols: list[str]) -> tuple[str, str]:
    dates = parse_market_dates(date_text)
    if not dates:
        return "missing_market_date", ""
    relevant = [s for s in symbols if s]
    if not relevant:
        return "missing_symbol", ""
    missing = [f"{s}@{d}" for d in dates for s in relevant if not ohlcv_file_exists(d, s)]
    if not missing:
        return "covered_all_relevant_symbols", ""
    core_missing = [f"{s}@{d}" for d in dates for s in CORE_SYMBOLS if not ohlcv_file_exists(d, s)]
    if not core_missing:
        return "covered_btc_eth_sol_but_missing_noncore", "|".join(missing)
    if len(missing) < len(relevant) * len(dates):
        return "partial_relevant_symbol_coverage", "|".join(missing)
    return "missing_relevant_symbol_coverage", "|".join(missing)


def frame_status(frame_paths: str) -> tuple[str, int]:
    raw = clean(frame_paths)
    if not raw:
        return "missing_frame_paths", 0
    parts = [p.strip() for p in re.split(r"[;|]", raw) if p.strip()]
    found = 0
    for part in parts:
        path = Path(part)
        if not path.is_absolute():
            path = ROOT / part
        if path.exists():
            found += 1
    if found == len(parts):
        return "all_paths_exist", found
    if found:
        return "partial_paths_exist", found
    return "paths_not_found_or_legacy_reference", 0


def bool_text(value: bool) -> str:
    return "true" if value else "false"


def eligibility(
    cls: str,
    fill: str,
    geom_mode: str,
    time_conf: str,
    ohlcv: str,
    outcome: str,
    mgmt_tags: str,
) -> tuple[str, str, str, str]:
    reasons: list[str] = []
    policy = cls in {
        "executed_trade",
        "actionable_setup",
        "planned_no_fill",
        "pass_cancel",
        "conditional_setup",
        "management_context",
    }
    if not policy:
        reasons.append("context_or_process_unit_not_direct_policy_label")
    if "missing" in ohlcv:
        reasons.append("ohlcv_missing")
    if time_conf.startswith("low"):
        reasons.append("low_time_confidence")
    fill_backtest = (
        cls in {"executed_trade", "planned_no_fill", "actionable_setup", "conditional_setup"}
        and fill in {"filled", "not_filled", "planned_unknown_fill"}
        and geom_mode in {"numeric_exact", "numeric_partial"}
        and not time_conf.startswith("low")
        and "missing" not in ohlcv
    )
    if not fill_backtest:
        if geom_mode not in {"numeric_exact", "numeric_partial"}:
            reasons.append("geometry_not_numeric")
        if fill not in {"filled", "not_filled", "planned_unknown_fill"}:
            reasons.append("fill_state_not_simulatable")
    management = (
        fill in {"filled", "managed_existing"}
        and mgmt_tags != "none_stated"
        and outcome not in {"unknown", "context_only", "no_fill", "pass", "cancelled"}
        and "missing" not in ohlcv
    )
    if not management and fill in {"filled", "managed_existing"}:
        if mgmt_tags == "none_stated":
            reasons.append("management_rule_not_stated")
        if outcome == "unknown":
            reasons.append("outcome_unknown")
    return bool_text(policy), bool_text(fill_backtest), bool_text(management), "|".join(dict.fromkeys(reasons)) or "none"


def mapping_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    specs = [
        ("decision_type", "decision_type_raw", ["decision_class", "decision_subtype", "fill_state"]),
        ("direction", "direction_raw", ["trade_side", "scenario_side"]),
        ("symbol", "symbol_raw", ["primary_symbol", "comparison_symbols"]),
        ("outcome", "realized_result_raw", ["outcome_class"]),
    ]
    for mapping_type, raw_col, canonical_cols in specs:
        grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
        for row in rows:
            grouped[clean(row.get(raw_col, ""))].append(row)
        for raw_value, group in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0])):
            canonical_summary = []
            for col in canonical_cols:
                counts = Counter(clean(r.get(col, "")) for r in group)
                canonical_summary.append(f"{col}=" + "|".join(f"{k}:{v}" for k, v in counts.most_common()))
            out.append(
                {
                    "mapping_type": mapping_type,
                    "raw_value": raw_value,
                    "raw_count": len(group),
                    "canonical_summary": "; ".join(canonical_summary),
                    "needs_manual_review": bool_text(len(set(tuple(clean(r.get(c, "")) for c in canonical_cols) for r in group)) > 1),
                }
            )
    return out


def build() -> None:
    trade_rows = read_csv(TRADE_PATH)
    rule_rows = {row["context_id"]: row for row in read_csv(RULE_PATH)}
    if set(rule_rows) != {row["context_id"] for row in trade_rows}:
        raise RuntimeError("Trade/rule context_id sets do not match.")

    out_rows: list[dict[str, object]] = []
    for row in trade_rows:
        rule = rule_rows[row["context_id"]]
        primary_symbol, comparison_symbols, symbol_list = split_symbols(row.get("symbol", ""))
        cls = decision_class(row.get("decision_type", ""), row.get("gold_status", ""))
        fill = fill_state(row.get("decision_type", ""), cls)
        trade_side, scenario_side = canonical_direction(row.get("direction", ""), row.get("decision_type", ""))
        text_blob = " ".join(clean(row.get(k, "")) for k in row)
        subtype = decision_subtype(row.get("decision_type", ""), text_blob)
        outcome = outcome_class(
            row.get("decision_type", ""),
            fill,
            row.get("realized_result", ""),
            row.get("exit_result_ko", ""),
            rule.get("outcome_feature", ""),
        )
        result_usd = parse_signed_money(row.get("realized_result", "")) or parse_signed_money(row.get("exit_result_ko", ""))
        result_r = parse_r_multiple(row.get("realized_result", "")) or parse_r_multiple(rule.get("outcome_feature", ""))
        geom_mode, geom_conf = geometry(row)
        tc = time_confidence(row.get("market_time_confidence", ""), row.get("market_time_window_utc_minus4", ""))
        ohlcv, missing_symbols = ohlcv_status(row.get("market_date_utc_minus4", ""), symbol_list)
        f_status, f_count = frame_status(row.get("frame_evidence_paths", ""))
        setup = setup_tags(row, rule)
        entry = entry_model(row, rule, fill)
        inv = invalidation_family(row, rule)
        mgmt = management_tags(row, rule)
        special = special_tags(row, rule)
        policy, fill_bt, mgmt_replay, hold_reason = eligibility(cls, fill, geom_mode, tc, ohlcv, outcome, mgmt)
        if not clean(row.get("realized_result", "")) and outcome != "unknown":
            realized_status = "derived_outcome_from_context"
        elif not clean(row.get("realized_result", "")):
            realized_status = "missing_result_unknown"
        else:
            realized_status = "raw_result_present"

        out = {
            "context_id": row["context_id"],
            "session_context_id": row.get("session_context_id", ""),
            "rule_seed_id": rule.get("rule_seed_id", ""),
            "video_id": row.get("video_id", ""),
            "video_title": row.get("video_title", ""),
            "local_index_oldest_first": row.get("local_index_oldest_first", ""),
            "source_stage_v03": row.get("source_stage_v03", ""),
            "gold_status": row.get("gold_status", ""),
            "decision_type_raw": row.get("decision_type", ""),
            "direction_raw": row.get("direction", ""),
            "symbol_raw": row.get("symbol", ""),
            "decision_class": cls,
            "decision_subtype": subtype,
            "fill_state": fill,
            "trade_side": trade_side,
            "scenario_side": scenario_side,
            "outcome_class": outcome,
            "result_usd": "" if result_usd is None else f"{result_usd:.2f}",
            "result_r": "" if result_r is None else f"{result_r:.4g}",
            "realized_result_raw": row.get("realized_result", ""),
            "realized_result_status": realized_status,
            "primary_symbol": primary_symbol,
            "comparison_symbols": comparison_symbols,
            "all_relevant_symbols": "|".join(symbol_list),
            "market_date_utc_minus4": row.get("market_date_utc_minus4", ""),
            "market_time_window_utc_minus4": row.get("market_time_window_utc_minus4", ""),
            "market_time_confidence_raw": row.get("market_time_confidence", ""),
            "time_confidence": tc,
            "youtube_window": row.get("youtube_window", ""),
            "anchor_seconds": row.get("anchor_seconds", ""),
            "chart_timeframe": row.get("chart_timeframe", ""),
            "setup_family_tags": setup,
            "entry_model": entry,
            "invalidation_family": inv,
            "management_family_tags": mgmt,
            "special_condition_tags": special,
            "geometry_mode": geom_mode,
            "geometry_confidence": geom_conf,
            "entry_price_raw": row.get("entry_price", ""),
            "stop_price_raw": row.get("stop_price", ""),
            "target_price_raw": row.get("target_price", ""),
            "entry_price_numeric": "" if whole_number(row.get("entry_price", "")) is None else whole_number(row.get("entry_price", "")),
            "stop_price_numeric": "" if whole_number(row.get("stop_price", "")) is None else whole_number(row.get("stop_price", "")),
            "target_price_numeric": "" if whole_number(row.get("target_price", "")) is None else whole_number(row.get("target_price", "")),
            "ohlcv_coverage_status": ohlcv,
            "ohlcv_missing_symbols": missing_symbols,
            "frame_evidence_status": f_status,
            "frame_evidence_count_found": f_count,
            "macro_context_status": "present" if clean(row.get("session_macro_context_ko", "")) else "missing",
            "elliott_wave_status": "stated" if clean(row.get("elliott_wave_context_ko", "")) else "not_stated",
            "eligible_for_policy_learning": policy,
            "eligible_for_fill_backtest": fill_bt,
            "eligible_for_management_replay": mgmt_replay,
            "hold_or_exclusion_reason": hold_reason,
            "session_macro_context_ko": row.get("session_macro_context_ko", ""),
            "scenario_tree_ko": row.get("scenario_tree_ko", ""),
            "symbol_selection_context_ko": row.get("symbol_selection_context_ko", ""),
            "elliott_wave_context_ko": row.get("elliott_wave_context_ko", ""),
            "trade_thesis_link_ko": row.get("trade_thesis_link_ko", ""),
            "structure_reference_ko": row.get("structure_reference_ko", ""),
            "setup_context_ko": row.get("setup_context_ko", ""),
            "entry_plan_ko": row.get("entry_plan_ko", ""),
            "management_plan_ko": row.get("management_plan_ko", ""),
            "live_thesis_changes_ko": row.get("live_thesis_changes_ko", ""),
            "exit_result_ko": row.get("exit_result_ko", ""),
            "frame_evidence_paths": row.get("frame_evidence_paths", ""),
            "ohlcv_alignment_ko": row.get("ohlcv_alignment_ko", ""),
            "rule_feature_vector_seed_ko": row.get("rule_feature_vector_seed_ko", ""),
            "invalidation_condition_ko": row.get("invalidation_condition_ko", ""),
            "remaining_uncertainty_ko": row.get("remaining_uncertainty_ko", ""),
            "rule_macro_bias_feature": rule.get("macro_bias_feature", ""),
            "rule_scenario_feature": rule.get("scenario_feature", ""),
            "rule_wave_fib_feature": rule.get("wave_fib_feature", ""),
            "rule_setup_trigger_feature": rule.get("setup_trigger_feature", ""),
            "rule_entry_feature": rule.get("entry_feature", ""),
            "rule_invalidation_feature": rule.get("invalidation_feature", ""),
            "rule_management_feature": rule.get("management_feature", ""),
            "rule_outcome_feature": rule.get("outcome_feature", ""),
            "rule_negative_or_pass_rule": rule.get("negative_or_pass_rule", ""),
            "rule_quantification_notes_ko": rule.get("quantification_notes_ko", ""),
        }
        out_rows.append(out)

    fieldnames = list(out_rows[0].keys())
    write_csv(OUT_DECISION_UNITS, out_rows, fieldnames)

    coverage_rows: list[dict[str, object]] = []
    seen_coverage: set[tuple[str, str]] = set()
    for out in out_rows:
        symbols = [s for s in clean(out.get("all_relevant_symbols", "")).split("|") if s]
        for date_text in parse_market_dates(clean(out.get("market_date_utc_minus4", ""))):
            for symbol in symbols:
                key = (date_text, symbol)
                if key in seen_coverage:
                    continue
                seen_coverage.add(key)
                status, path = ohlcv_path_status(date_text, symbol)
                coverage_rows.append(
                    {
                        "market_date_utc_minus4": date_text,
                        "symbol": symbol,
                        "coverage_status": status,
                        "path": path,
                    }
                )
    coverage_rows.sort(key=lambda r: (clean(r["market_date_utc_minus4"]), clean(r["symbol"])))
    write_csv(
        OUT_OHLCV_MANIFEST,
        coverage_rows,
        ["market_date_utc_minus4", "symbol", "coverage_status", "path"],
    )

    mapping = mapping_rows(out_rows)
    write_csv(
        OUT_MAPPING,
        mapping,
        ["mapping_type", "raw_value", "raw_count", "canonical_summary", "needs_manual_review"],
    )

    hold_rows = read_csv(HOLD_PATH) if HOLD_PATH.exists() else []
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_files": {
            "trade_context_queue": str(TRADE_PATH.relative_to(ROOT)),
            "rule_seed_queue": str(RULE_PATH.relative_to(ROOT)),
            "hold_context_queue": str(HOLD_PATH.relative_to(ROOT)),
        },
        "output_files": {
            "decision_units": str(OUT_DECISION_UNITS.relative_to(ROOT)),
            "canonical_mapping": str(OUT_MAPPING.relative_to(ROOT)),
            "normalization_audit": str(OUT_AUDIT.relative_to(ROOT)),
            "eligibility_summary": str(OUT_SUMMARY.relative_to(ROOT)),
            "ohlcv_coverage_manifest": str(OUT_OHLCV_MANIFEST.relative_to(ROOT)),
        },
        "row_counts": {
            "decision_units": len(out_rows),
            "hold_context_rows_external": len(hold_rows),
            "unique_ohlcv_date_symbol_pairs": len(coverage_rows),
        },
        "canonical_distributions": {
            "decision_class": Counter(r["decision_class"] for r in out_rows),
            "fill_state": Counter(r["fill_state"] for r in out_rows),
            "trade_side": Counter(r["trade_side"] for r in out_rows),
            "outcome_class": Counter(r["outcome_class"] for r in out_rows),
            "geometry_mode": Counter(r["geometry_mode"] for r in out_rows),
            "time_confidence": Counter(r["time_confidence"] for r in out_rows),
            "ohlcv_coverage_status": Counter(r["ohlcv_coverage_status"] for r in out_rows),
            "eligible_for_policy_learning": Counter(r["eligible_for_policy_learning"] for r in out_rows),
            "eligible_for_fill_backtest": Counter(r["eligible_for_fill_backtest"] for r in out_rows),
            "eligible_for_management_replay": Counter(r["eligible_for_management_replay"] for r in out_rows),
            "elliott_wave_status": Counter(r["elliott_wave_status"] for r in out_rows),
            "frame_evidence_status": Counter(r["frame_evidence_status"] for r in out_rows),
        },
        "numeric_geometry_counts": {
            "entry_price_numeric": sum(1 for r in out_rows if clean(r.get("entry_price_numeric", ""))),
            "stop_price_numeric": sum(1 for r in out_rows if clean(r.get("stop_price_numeric", ""))),
            "target_price_numeric": sum(1 for r in out_rows if clean(r.get("target_price_numeric", ""))),
        },
        "raw_distinct_counts": {
            "decision_type_raw": len(Counter(r["decision_type_raw"] for r in out_rows)),
            "direction_raw": len(Counter(r["direction_raw"] for r in out_rows)),
            "symbol_raw": len(Counter(r["symbol_raw"] for r in out_rows)),
        },
        "derived_result_rows": sum(1 for r in out_rows if r["realized_result_status"] == "derived_outcome_from_context"),
        "unknown_outcome_rows": sum(1 for r in out_rows if r["outcome_class"] == "unknown"),
        "mapping_rows_needing_manual_review": sum(1 for r in mapping if r["needs_manual_review"] == "true"),
        "ohlcv_coverage_manifest_missing_pairs": sum(1 for r in coverage_rows if r["coverage_status"] == "missing"),
    }
    serializable_summary = json.loads(json.dumps(summary, default=dict))
    OUT_SUMMARY.write_text(json.dumps(serializable_summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def md_counter(counter: Counter[str]) -> str:
        return "\n".join(f"- `{k}`: {v}" for k, v in counter.most_common()) or "- none"

    audit_lines = [
        "# Craig gold v0.3 to v1 decision-unit normalization audit",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "## What changed",
        "",
        "- Kept the original v0.3 gold rows unchanged.",
        "- Added a derived v1 decision-unit layer with canonical decision, direction, outcome, geometry, time, OHLCV, and eligibility fields.",
        "- Preserved raw labels in `decision_type_raw`, `direction_raw`, `symbol_raw`, `realized_result_raw`, and raw price fields.",
        "- Rechecked local OHLCV file coverage after the missing-date fetch step.",
        "- Did not infer numeric entry/SL/TP where source geometry is only frame-relative or prose.",
        "",
        "## Row counts",
        "",
        f"- Decision units: {len(out_rows)}",
        f"- External hold rows kept outside gold: {len(hold_rows)}",
        f"- Raw decision_type distinct: {summary['raw_distinct_counts']['decision_type_raw']}",
        f"- Raw direction distinct: {summary['raw_distinct_counts']['direction_raw']}",
        f"- Raw symbol distinct: {summary['raw_distinct_counts']['symbol_raw']}",
        "",
        "## Canonical decision_class",
        "",
        md_counter(Counter(r["decision_class"] for r in out_rows)),
        "",
        "## Canonical outcome_class",
        "",
        md_counter(Counter(r["outcome_class"] for r in out_rows)),
        "",
        "## Geometry readiness",
        "",
        md_counter(Counter(r["geometry_mode"] for r in out_rows)),
        "",
        f"- Numeric entry rows: {summary['numeric_geometry_counts']['entry_price_numeric']}",
        f"- Numeric stop rows: {summary['numeric_geometry_counts']['stop_price_numeric']}",
        f"- Numeric target rows: {summary['numeric_geometry_counts']['target_price_numeric']}",
        "",
        "## OHLCV coverage",
        "",
        md_counter(Counter(r["ohlcv_coverage_status"] for r in out_rows)),
        "",
        "## Model eligibility",
        "",
        md_counter(Counter(r["eligible_for_policy_learning"] for r in out_rows)),
        "",
        "Fill backtest:",
        "",
        md_counter(Counter(r["eligible_for_fill_backtest"] for r in out_rows)),
        "",
        "Management replay:",
        "",
        md_counter(Counter(r["eligible_for_management_replay"] for r in out_rows)),
        "",
        "## Remaining data limits",
        "",
        "- Most rows are still relative-structure/prose geometry; exact fill/SL/TP simulation must stay limited to `geometry_mode in {numeric_exact,numeric_partial}`.",
        "- A canonical enum can now be consumed by v1, but rows marked `needs_manual_review=true` in the mapping file should be reviewed before freezing a permanent ontology.",
        "- News/macro calendar data is still not a normalized external table. Rows can expose macro/news tags, but the next model stage should join an external same-day calendar before claiming true Craig-like inputs.",
        "- ATOM appears as a non-core symbol; BTC/ETH/SOL coverage is fixed, but ATOM-specific OHLCV remains out of scope unless separately fetched.",
        "",
        "## Output files",
        "",
        f"- `{OUT_DECISION_UNITS.relative_to(ROOT)}`",
        f"- `{OUT_MAPPING.relative_to(ROOT)}`",
        f"- `{OUT_SUMMARY.relative_to(ROOT)}`",
        f"- `{OUT_AUDIT.relative_to(ROOT)}`",
        f"- `{OUT_OHLCV_MANIFEST.relative_to(ROOT)}`",
    ]
    OUT_AUDIT.write_text("\n".join(audit_lines) + "\n", encoding="utf-8")

    print(f"decision_units={len(out_rows)} mapping_rows={len(mapping)}")
    print(f"wrote={OUT_DECISION_UNITS}")
    print(f"wrote={OUT_MAPPING}")
    print(f"wrote={OUT_SUMMARY}")
    print(f"wrote={OUT_AUDIT}")
    print(f"wrote={OUT_OHLCV_MANIFEST}")


if __name__ == "__main__":
    build()
