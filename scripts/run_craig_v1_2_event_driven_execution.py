#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from build_craig_v1_2_trade_candidates import (
    HEADLINE_SYMBOLS,
    ROOT,
    TARGET_POOLS_PARQUET,
    TARGET_SUMMARY_PARQUET,
    latest_tf_close,
    load_market_data,
    markdown_table,
    stable_id,
    utc_timestamp,
)


SNIPER_CANDIDATES_PARQUET = ROOT / "outputs/craig_v1_2_sniper_trade_candidates.parquet"
CONFIG_YAML = ROOT / "outputs/craig_v1_2_backtest_config.yaml"

OUT_TRADE_LOG = ROOT / "outputs/craig_v1_2_event_execution_trade_log.csv"
OUT_EQUITY_CURVE = ROOT / "outputs/craig_v1_2_event_execution_equity_curve.csv"
OUT_AUDIT = ROOT / "outputs/craig_v1_2_event_execution_audit.csv"
OUT_REPORT = ROOT / "outputs/craig_v1_2_event_execution_report.md"

DEFAULT_ORDER_EXPIRY_MINUTES = 60
DEFAULT_MAX_HOLD_MINUTES = 24 * 60
NO_CHASE_ATR_MULTIPLE = 1.25
TP1_WEIGHT = 0.25
CORE_WEIGHT = 0.50
RUNNER_WEIGHT = 0.25

FINAL_STATES = {
    "pending",
    "canceled_no_fill",
    "canceled_no_chase",
    "filled",
    "stopped",
    "tp1_hit",
    "core_hit",
    "runner_hit",
    "breakeven_exit",
    "expired",
    "session_close_exit",
    "ambiguous_conservative_stop_first",
}


def side_sign(side: str) -> int:
    return 1 if side == "long" else -1


def directional_move(side: str, price: float, reference: float) -> float:
    return (price - reference) * side_sign(side)


def target_touched(side: str, high: float, low: float, target: float) -> bool:
    if pd.isna(target):
        return False
    return high >= target if side == "long" else low <= target


def stop_touched(side: str, high: float, low: float, stop: float) -> bool:
    if pd.isna(stop):
        return False
    return low <= stop if side == "long" else high >= stop


def entry_touched(high: float, low: float, entry: float) -> bool:
    return low <= entry <= high


def load_config() -> dict[str, object]:
    if yaml is None or not CONFIG_YAML.exists():
        return {}
    with CONFIG_YAML.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def cost_assumptions(config: dict[str, object]) -> dict[str, float]:
    execution = config.get("execution_cost_assumptions", {}) if isinstance(config, dict) else {}
    fees = execution.get("fee_bps", {}) if isinstance(execution, dict) else {}
    slippage = execution.get("slippage_bps", {}) if isinstance(execution, dict) else {}
    return {
        "maker_entry_fee_bps": float(fees.get("maker_entry", 2.0)),
        "maker_exit_fee_bps": float(fees.get("maker_exit", 2.0)),
        "stop_exit_fee_bps": float(fees.get("stop_exit", 5.0)),
        "limit_entry_slippage_bps": float(slippage.get("limit_entry_base", 0.5)),
        "limit_exit_slippage_bps": float(slippage.get("limit_exit_base", 0.5)),
        "stop_exit_slippage_bps": float(slippage.get("stop_exit_base", 3.0)),
    }


def latest_atr_15m(market, timestamp_ns: int) -> float:
    bars = market.tf_bars["15m"]
    values = bars["close_time_ns"].to_numpy(dtype="int64")
    pos = int(np.searchsorted(values, timestamp_ns, side="right")) - 1
    if pos < 0:
        return np.nan
    return float(bars.iloc[pos]["atr"])


def load_target_tables(symbols: list[str]) -> tuple[pd.DataFrame, dict[str, dict[str, object]]]:
    summary = pd.read_parquet(TARGET_SUMMARY_PARQUET)
    summary = summary[summary["symbol"].isin(symbols)].copy()
    summary["decision_timestamp"] = pd.to_datetime(summary["decision_timestamp"], utc=True)
    target_cols = [
        "target_id",
        "symbol",
        "decision_timestamp",
        "side",
        "target_source",
        "target_timeframe",
        "target_price",
        "available_at",
        "latest_source_candle_close_used",
        "lookahead_pass",
    ]
    targets = pd.read_parquet(TARGET_POOLS_PARQUET, columns=target_cols)
    targets = targets[targets["symbol"].isin(symbols)].copy()
    targets["available_at"] = pd.to_datetime(targets["available_at"], utc=True)
    targets["latest_source_candle_close_used"] = pd.to_datetime(targets["latest_source_candle_close_used"], utc=True)
    lookup = {
        str(row.target_id): {
            "target_id": str(row.target_id),
            "target_source": str(row.target_source),
            "target_timeframe": str(row.target_timeframe),
            "target_price": float(row.target_price),
            "available_at": pd.Timestamp(row.available_at),
            "latest_source_candle_close_used": pd.Timestamp(row.latest_source_candle_close_used),
            "lookahead_pass": bool(row.lookahead_pass),
        }
        for row in targets.itertuples(index=False)
    }
    return summary, lookup


def target_from_lookup(lookup: dict[str, dict[str, object]], target_id: object) -> dict[str, object] | None:
    if pd.isna(target_id) or str(target_id) == "":
        return None
    return lookup.get(str(target_id))


def candidate_targets(
    candidate: pd.Series,
    summary_index: pd.DataFrame,
    target_lookup: dict[str, dict[str, object]],
) -> dict[str, object]:
    key = (str(candidate["symbol"]), utc_timestamp(candidate["decision_timestamp"]), str(candidate["side"]))
    try:
        summary = summary_index.loc[key]
    except KeyError:
        summary = None
    if summary is None:
        return {
            "tp1_price": np.nan,
            "core_target_price": np.nan,
            "runner_target_price": np.nan,
            "target_latest_source_close_used": pd.NaT,
            "target_pool_built_at": utc_timestamp(candidate["decision_timestamp"]),
            "target_lookup_pass": False,
        }
    tp1 = target_from_lookup(target_lookup, summary.get("tp1_candidate_target_id", ""))
    core = target_from_lookup(target_lookup, summary.get("core_candidate_target_id", ""))
    runner = target_from_lookup(target_lookup, summary.get("runner_candidate_target_id", ""))
    latest = [
        target["latest_source_candle_close_used"]
        for target in [tp1, core, runner]
        if target is not None and pd.notna(target.get("latest_source_candle_close_used", pd.NaT))
    ]
    return {
        "tp1_price": tp1["target_price"] if tp1 else np.nan,
        "core_target_price": core["target_price"] if core else np.nan,
        "runner_target_price": runner["target_price"] if runner else np.nan,
        "tp1_source": tp1["target_source"] if tp1 else "none",
        "core_target_source": core["target_source"] if core else "none",
        "runner_target_source": runner["target_source"] if runner else "none",
        "target_latest_source_close_used": max(latest) if latest else pd.NaT,
        "target_pool_built_at": utc_timestamp(candidate["decision_timestamp"]),
        "target_lookup_pass": core is not None and bool(core.get("lookahead_pass", False)),
    }


def r_for_price(side: str, price: float, entry: float, risk_abs: float) -> float:
    if risk_abs <= 0 or pd.isna(price):
        return np.nan
    return float(directional_move(side, price, entry) / risk_abs)


def weighted_realized_r(
    side: str,
    entry: float,
    risk_abs: float,
    exit_price: float,
    tp1_price: float,
    core_price: float,
    runner_price: float,
    hit_tp1: bool,
    hit_core: bool,
    hit_runner: bool,
    stopped_before_tp1: bool,
) -> float:
    if stopped_before_tp1:
        return -1.0
    realized = 0.0
    remaining = 1.0
    if hit_tp1:
        realized += TP1_WEIGHT * r_for_price(side, tp1_price, entry, risk_abs)
        remaining -= TP1_WEIGHT
    if hit_core:
        realized += CORE_WEIGHT * r_for_price(side, core_price, entry, risk_abs)
        remaining -= CORE_WEIGHT
    if hit_runner:
        realized += RUNNER_WEIGHT * r_for_price(side, runner_price, entry, risk_abs)
        remaining -= RUNNER_WEIGHT
    else:
        realized += max(0.0, remaining) * r_for_price(side, exit_price, entry, risk_abs)
    return float(realized)


def cost_drag_r(
    entry: float,
    risk_abs: float,
    final_state: str,
    hit_tp1: bool,
    hit_core: bool,
    hit_runner: bool,
    costs: dict[str, float],
) -> tuple[float, float]:
    if risk_abs <= 0 or final_state in {"canceled_no_fill", "canceled_no_chase", "expired"}:
        return 0.0, 0.0
    fee_bps = costs["maker_entry_fee_bps"]
    slippage_bps = costs["limit_entry_slippage_bps"]
    remaining = 1.0
    if hit_tp1:
        fee_bps += TP1_WEIGHT * costs["maker_exit_fee_bps"]
        slippage_bps += TP1_WEIGHT * costs["limit_exit_slippage_bps"]
        remaining -= TP1_WEIGHT
    if hit_core:
        fee_bps += CORE_WEIGHT * costs["maker_exit_fee_bps"]
        slippage_bps += CORE_WEIGHT * costs["limit_exit_slippage_bps"]
        remaining -= CORE_WEIGHT
    if hit_runner:
        fee_bps += RUNNER_WEIGHT * costs["maker_exit_fee_bps"]
        slippage_bps += RUNNER_WEIGHT * costs["limit_exit_slippage_bps"]
        remaining -= RUNNER_WEIGHT
    else:
        exit_is_stop = final_state in {"stopped", "ambiguous_conservative_stop_first", "breakeven_exit"}
        fee_bps += max(0.0, remaining) * (costs["stop_exit_fee_bps"] if exit_is_stop else costs["maker_exit_fee_bps"])
        slippage_bps += max(0.0, remaining) * (costs["stop_exit_slippage_bps"] if exit_is_stop else costs["limit_exit_slippage_bps"])
    fee_r = (fee_bps / 10000.0 * entry) / risk_abs
    slippage_r = (slippage_bps / 10000.0 * entry) / risk_abs
    return float(fee_r), float(slippage_r)


def session_bucket(ts: pd.Timestamp) -> str:
    hour = utc_timestamp(ts).hour
    if 0 <= hour < 8:
        return "asia_utc"
    if 8 <= hour < 13:
        return "london_utc"
    if 13 <= hour < 21:
        return "ny_utc"
    return "late_utc"


def simulate_candidate(
    candidate: pd.Series,
    market,
    target_info: dict[str, object],
    costs: dict[str, float],
    order_expiry_minutes: int,
    max_hold_minutes: int,
) -> dict[str, object]:
    symbol = str(candidate["symbol"])
    side = str(candidate["side"])
    trigger_at = utc_timestamp(candidate["trigger_available_at"])
    order_placed_at = trigger_at
    order_expiry_at = order_placed_at + pd.Timedelta(minutes=order_expiry_minutes)
    entry = float(candidate["entry_price"])
    stop = float(candidate["stop_price"])
    risk_abs = entry - stop if side == "long" else stop - entry
    tp1 = float(target_info["tp1_price"]) if pd.notna(target_info["tp1_price"]) else np.nan
    core = float(target_info["core_target_price"]) if pd.notna(target_info["core_target_price"]) else np.nan
    runner = float(target_info["runner_target_price"]) if pd.notna(target_info["runner_target_price"]) else np.nan
    trigger_ns = trigger_at.value
    expiry_ns = order_expiry_at.value
    start = int(np.searchsorted(market.close_ns_1m, trigger_ns, side="right"))
    expiry_end = int(np.searchsorted(market.close_ns_1m, expiry_ns, side="right"))
    atr_15 = latest_atr_15m(market, trigger_ns)
    atr_15 = atr_15 if pd.notna(atr_15) and atr_15 > 0 else max(entry * 0.002, 1e-9)

    base = {
        "candidate_id": str(candidate["candidate_id"]),
        "symbol": symbol,
        "side": side,
        "entry_pattern_tier": str(candidate["entry_pattern_tier"]),
        "scenario_type": str(candidate.get("scenario_type", "")),
        "trigger_available_at": trigger_at,
        "order_placed_at": order_placed_at,
        "order_expiry_at": order_expiry_at,
        "entry_price": entry,
        "stop_price": stop,
        "tp1_price": tp1,
        "core_target_price": core,
        "runner_target_price": runner,
        "fill_timestamp": pd.NaT,
        "exit_timestamp": pd.NaT,
        "final_state": "pending",
        "gross_r": 0.0,
        "net_r": 0.0,
        "fee_r": 0.0,
        "slippage_r": 0.0,
        "max_favorable_excurson_r": 0.0,
        "max_favorable_excursion_r": 0.0,
        "max_adverse_excursion_r": 0.0,
        "hit_tp1": False,
        "hit_core": False,
        "hit_runner": False,
        "stopped": False,
        "canceled_reason": "",
        "ambiguity_flag": False,
        "session_bucket": session_bucket(trigger_at),
        "lookahead_pass": bool(candidate["lookahead_pass"]),
        "lookahead_violation_reason": "",
    }
    if risk_abs <= 0 or pd.isna(entry) or pd.isna(stop) or pd.isna(core):
        base.update({"final_state": "expired", "canceled_reason": "invalid_entry_stop_or_core_target"})
        return base

    fill_idx = -1
    for i in range(start, min(expiry_end, len(market.close_ns_1m))):
        high_i = float(market.high[i])
        low_i = float(market.low[i])
        close_i = float(market.close[i])
        if entry_touched(high_i, low_i, entry):
            fill_idx = i
            break
        no_chase_price = high_i if side == "long" else low_i
        if directional_move(side, no_chase_price, entry) > NO_CHASE_ATR_MULTIPLE * atr_15:
            base.update(
                {
                    "exit_timestamp": pd.Timestamp(int(market.close_ns_1m[i]), unit="ns", tz="UTC"),
                    "final_state": "canceled_no_chase",
                    "canceled_reason": "price_moved_away_before_limit_fill",
                }
            )
            return base
    if fill_idx < 0:
        base.update({"exit_timestamp": order_expiry_at, "final_state": "canceled_no_fill", "canceled_reason": "order_expired_no_fill"})
        return base

    fill_ts = pd.Timestamp(int(market.close_ns_1m[fill_idx]), unit="ns", tz="UTC")
    max_hold_end = fill_ts + pd.Timedelta(minutes=max_hold_minutes)
    end_ns = max_hold_end.value
    end_idx = min(int(np.searchsorted(market.close_ns_1m, end_ns, side="right")), len(market.close_ns_1m))
    hit_tp1 = False
    hit_core = False
    hit_runner = False
    stopped = False
    ambiguity = False
    final_state = "filled"
    exit_ts = pd.NaT
    exit_price = entry
    max_favorable = 0.0
    max_adverse = 0.0
    active_stop = stop

    for i in range(fill_idx, end_idx):
        high_i = float(market.high[i])
        low_i = float(market.low[i])
        close_i = float(market.close[i])
        close_ts = pd.Timestamp(int(market.close_ns_1m[i]), unit="ns", tz="UTC")
        favorable_price = high_i if side == "long" else low_i
        adverse_price = low_i if side == "long" else high_i
        max_favorable = max(max_favorable, max(0.0, directional_move(side, favorable_price, entry) / risk_abs))
        max_adverse = max(max_adverse, max(0.0, -directional_move(side, adverse_price, entry) / risk_abs))

        stop_hit = stop_touched(side, high_i, low_i, active_stop)
        tp1_hit_now = (not hit_tp1) and target_touched(side, high_i, low_i, tp1)
        core_hit_now = (not hit_core) and target_touched(side, high_i, low_i, core)
        runner_hit_now = (not hit_runner) and target_touched(side, high_i, low_i, runner)

        if stop_hit and (tp1_hit_now or core_hit_now or runner_hit_now):
            ambiguity = True
            stopped = True
            final_state = "ambiguous_conservative_stop_first"
            exit_ts = close_ts
            exit_price = active_stop
            break
        if stop_hit:
            stopped = True
            final_state = "stopped" if active_stop != entry else "breakeven_exit"
            exit_ts = close_ts
            exit_price = active_stop
            break
        if tp1_hit_now:
            hit_tp1 = True
            active_stop = entry
            final_state = "tp1_hit"
        if core_hit_now:
            hit_tp1 = True if pd.notna(tp1) else hit_tp1
            hit_core = True
            active_stop = entry
            final_state = "core_hit"
        if runner_hit_now:
            hit_tp1 = True if pd.notna(tp1) else hit_tp1
            hit_core = True if pd.notna(core) else hit_core
            hit_runner = True
            final_state = "runner_hit"
            exit_ts = close_ts
            exit_price = runner
            break

    if pd.isna(exit_ts):
        if end_idx > fill_idx:
            last_i = end_idx - 1
            exit_ts = pd.Timestamp(int(market.close_ns_1m[last_i]), unit="ns", tz="UTC")
            exit_price = float(market.close[last_i])
            final_state = "session_close_exit"
        else:
            exit_ts = fill_ts
            exit_price = entry
            final_state = "expired"

    gross_r = weighted_realized_r(
        side,
        entry,
        risk_abs,
        exit_price,
        tp1,
        core,
        runner,
        hit_tp1,
        hit_core,
        hit_runner,
        stopped_before_tp1=bool(stopped and not hit_tp1 and final_state != "breakeven_exit"),
    )
    fee_r, slippage_r = cost_drag_r(entry, risk_abs, final_state, hit_tp1, hit_core, hit_runner, costs)
    net_r = gross_r - fee_r - slippage_r
    base.update(
        {
            "fill_timestamp": fill_ts,
            "exit_timestamp": exit_ts,
            "final_state": final_state,
            "gross_r": float(gross_r),
            "net_r": float(net_r),
            "fee_r": float(fee_r),
            "slippage_r": float(slippage_r),
            "max_favorable_excurson_r": float(max_favorable),
            "max_favorable_excursion_r": float(max_favorable),
            "max_adverse_excursion_r": float(max_adverse),
            "hit_tp1": bool(hit_tp1),
            "hit_core": bool(hit_core),
            "hit_runner": bool(hit_runner),
            "stopped": bool(stopped),
            "canceled_reason": "",
            "ambiguity_flag": bool(ambiguity),
        }
    )
    return base


def load_candidates(symbols: list[str]) -> pd.DataFrame:
    candidates = pd.read_parquet(SNIPER_CANDIDATES_PARQUET)
    candidates = candidates[candidates["symbol"].isin(symbols)].copy()
    candidates["decision_timestamp"] = pd.to_datetime(candidates["decision_timestamp"], utc=True)
    candidates["trigger_available_at"] = pd.to_datetime(candidates["trigger_available_at"], utc=True)
    mask = (
        candidates["sniper_candidate_status"].eq("accepted_headline")
        & candidates["entry_pattern_tier"].isin(["S_tier_sniper", "A_tier_sniper"])
        & candidates["lookahead_pass"].astype(bool)
    )
    return candidates[mask].sort_values(["trigger_available_at", "symbol", "candidate_id"]).reset_index(drop=True)


def run_simulation(symbols: list[str], order_expiry_minutes: int, max_hold_minutes: int) -> pd.DataFrame:
    config = load_config()
    costs = cost_assumptions(config)
    candidates = load_candidates(symbols)
    markets = {symbol: load_market_data(symbol) for symbol in symbols}
    target_summary, target_lookup = load_target_tables(symbols)
    target_summary_index = target_summary.set_index(["symbol", "decision_timestamp", "side"])
    rows = []
    total = len(candidates)
    for idx, candidate in enumerate(candidates.itertuples(index=False), 1):
        if idx == 1 or idx % 500 == 0:
            print(f"  execution candidates={idx}/{total}", flush=True)
        candidate_s = pd.Series(candidate._asdict())
        target_info = candidate_targets(candidate_s, target_summary_index, target_lookup)
        rows.append(
            simulate_candidate(
                candidate_s,
                markets[str(candidate_s["symbol"])],
                target_info,
                costs,
                order_expiry_minutes,
                max_hold_minutes,
            )
        )
    return pd.DataFrame(rows)


def build_audit(trades: pd.DataFrame) -> pd.DataFrame:
    audit = trades[
        [
            "candidate_id",
            "symbol",
            "side",
            "trigger_available_at",
            "order_placed_at",
            "order_expiry_at",
            "fill_timestamp",
            "exit_timestamp",
            "final_state",
            "lookahead_pass",
            "lookahead_violation_reason",
        ]
    ].copy()
    for column in ["trigger_available_at", "order_placed_at", "order_expiry_at", "fill_timestamp", "exit_timestamp"]:
        audit[column] = pd.to_datetime(audit[column], utc=True, errors="coerce")
    filled = audit["fill_timestamp"].notna()
    exited = audit["exit_timestamp"].notna()
    time_ok = (
        (audit["order_placed_at"] >= audit["trigger_available_at"])
        & (audit["order_expiry_at"] > audit["order_placed_at"])
        & (~filled | (audit["fill_timestamp"] > audit["trigger_available_at"]))
        & (~exited | (audit["exit_timestamp"] >= audit["trigger_available_at"]))
        & (~(filled & exited) | (audit["exit_timestamp"] >= audit["fill_timestamp"]))
    )
    audit["lookahead_pass"] = time_ok.astype(bool) & audit["lookahead_pass"].astype(bool)
    audit.loc[audit["lookahead_pass"], "lookahead_violation_reason"] = ""
    audit.loc[~audit["lookahead_pass"], "lookahead_violation_reason"] = "execution_timestamp_ordering_violation"
    return audit


def build_equity_curve(trades: pd.DataFrame) -> pd.DataFrame:
    curve = trades.sort_values(["exit_timestamp", "trigger_available_at", "candidate_id"]).copy()
    curve["trade_number"] = np.arange(1, len(curve) + 1)
    curve["cumulative_net_r"] = curve["net_r"].fillna(0.0).cumsum()
    curve["equity_peak_r"] = curve["cumulative_net_r"].cummax()
    curve["drawdown_r"] = curve["cumulative_net_r"] - curve["equity_peak_r"]
    return curve[["trade_number", "candidate_id", "exit_timestamp", "net_r", "cumulative_net_r", "equity_peak_r", "drawdown_r"]]


def summarize_group(df: pd.DataFrame, group_cols: list[str]) -> list[dict[str, object]]:
    if df.empty:
        return []
    rows = []
    for key, group in df.groupby(group_cols):
        key_values = key if isinstance(key, tuple) else (key,)
        wins = group[group["net_r"] > 0]
        losses = group[group["net_r"] < 0]
        gross_profit = wins["net_r"].sum()
        gross_loss = -losses["net_r"].sum()
        row = {column: value for column, value in zip(group_cols, key_values)}
        row.update(
            {
                "trades": len(group),
                "filled": int(group["fill_timestamp"].notna().sum()),
                "net_r": round(float(group["net_r"].sum()), 3),
                "expectancy": round(float(group["net_r"].mean()), 3),
                "win_rate_pct": round(float((group["net_r"] > 0).mean() * 100), 2),
                "profit_factor": round(float(gross_profit / gross_loss), 3) if gross_loss > 0 else "inf",
            }
        )
        rows.append(row)
    return rows


def write_report(trades: pd.DataFrame, curve: pd.DataFrame, audit: pd.DataFrame, order_expiry_minutes: int, max_hold_minutes: int) -> None:
    total = len(trades)
    filled = trades[trades["fill_timestamp"].notna()].copy()
    wins = trades[trades["net_r"] > 0]
    losses = trades[trades["net_r"] < 0]
    gross_profit = float(wins["net_r"].sum())
    gross_loss = float(-losses["net_r"].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else np.inf
    max_dd = float(curve["drawdown_r"].min()) if not curve.empty else 0.0
    runner_contribution = float(
        (trades.loc[trades["hit_runner"], "net_r"] - trades.loc[trades["hit_runner"], "planned_runner_baseline_r"]).sum()
    ) if "planned_runner_baseline_r" in trades.columns and trades["hit_runner"].any() else float(trades.loc[trades["hit_runner"], "net_r"].sum())
    top5_net_r = float(trades["net_r"].nlargest(5).sum()) if total else 0.0
    total_net = float(trades["net_r"].sum()) if total else 0.0
    top5_gross_profit_share = top5_net_r / gross_profit * 100 if gross_profit > 0 else np.nan
    top5_total_net_share = top5_net_r / total_net * 100 if total_net > 0 else np.nan
    state_counts = trades["final_state"].value_counts().reset_index()
    state_counts.columns = ["final_state", "rows"]
    tier_summary = summarize_group(trades, ["entry_pattern_tier"])
    symbol_side = summarize_group(trades, ["symbol", "side"])
    session_summary = summarize_group(trades, ["session_bucket"])
    scenario_summary = summarize_group(trades, ["scenario_type"])
    violations = int((~audit["lookahead_pass"]).sum())
    lines = [
        "# Craig v1.2 Event-Driven Execution Report",
        "",
        "Generated by `scripts/run_craig_v1_2_event_driven_execution.py`.",
        "",
        "## Verdict",
        "",
        "- This is the first PnL prototype over v1.2.1 S/A-tier sniper candidates only.",
        "- Broad v1.2 trade candidates are not used as headline simulator input.",
        "- Orders are FVG-mid limit orders placed after `trigger_available_at`; fills are event-driven from later 1m candle ranges.",
        "- Same-candle fill/stop/target ambiguity is handled conservatively with stop-first ordering.",
        "- No gold label, Craig action, result R, realized source outcome, or parameter optimization is used.",
        f"- Lookahead violations: {violations}.",
        "",
        "## Inputs",
        "",
        f"- Candidates consumed: {total}",
        "- Input filter: `sniper_candidate_status=accepted_headline`, `entry_pattern_tier in [S_tier_sniper, A_tier_sniper]`, `lookahead_pass=true`.",
        f"- Order expiry: {order_expiry_minutes} minutes",
        f"- Max hold/session-close horizon: {max_hold_minutes} minutes",
        "",
        "## State Counts",
        "",
        *markdown_table(state_counts.to_dict("records"), ["final_state", "rows"]),
        "",
        "## Headline Performance",
        "",
        f"- Filled trades: {int(filled.shape[0])}",
        f"- No-fill cancels: {int(trades['final_state'].eq('canceled_no_fill').sum())}",
        f"- No-chase cancels: {int(trades['final_state'].eq('canceled_no_chase').sum())}",
        f"- Expired/session-close exits: {int(trades['final_state'].isin(['expired', 'session_close_exit']).sum())}",
        f"- Gross total R: {float(trades['gross_r'].sum()):.3f}",
        f"- Net total R: {float(total_net):.3f}",
        f"- Net expectancy per consumed candidate: {float(trades['net_r'].mean()):.3f}",
        f"- Win rate: {float((trades['net_r'] > 0).mean() * 100):.2f}%",
        f"- Profit factor: {profit_factor:.3f}" if np.isfinite(profit_factor) else "- Profit factor: inf",
        f"- Max drawdown R: {max_dd:.3f}",
        f"- Average win R: {float(wins['net_r'].mean()):.3f}" if not wins.empty else "- Average win R: n/a",
        f"- Average loss R: {float(losses['net_r'].mean()):.3f}" if not losses.empty else "- Average loss R: n/a",
        f"- Median R: {float(trades['net_r'].median()):.3f}",
        f"- Runner-hit contribution net R: {runner_contribution:.3f}",
        f"- Top 5 net R: {top5_net_r:.3f}",
        f"- Top 5 share of gross profit: {top5_gross_profit_share:.2f}%" if pd.notna(top5_gross_profit_share) else "- Top 5 share of gross profit: n/a",
        f"- Top 5 share of total net R: {top5_total_net_share:.2f}%" if pd.notna(top5_total_net_share) else "- Top 5 share of total net R: n/a because total net R <= 0",
        f"- Fee drag R: {float(trades['fee_r'].sum()):.3f}",
        f"- Slippage drag R: {float(trades['slippage_r'].sum()):.3f}",
        f"- Ambiguous candle count: {int(trades['ambiguity_flag'].sum())}",
        "",
        "## S-Tier vs A-Tier",
        "",
        *markdown_table(tier_summary, ["entry_pattern_tier", "trades", "filled", "net_r", "expectancy", "win_rate_pct", "profit_factor"]),
        "",
        "## Symbol And Side",
        "",
        *markdown_table(symbol_side, ["symbol", "side", "trades", "filled", "net_r", "expectancy", "win_rate_pct", "profit_factor"]),
        "",
        "## Session Buckets",
        "",
        *markdown_table(session_summary, ["session_bucket", "trades", "filled", "net_r", "expectancy", "win_rate_pct", "profit_factor"]),
        "",
        "## Scenario Type",
        "",
        *markdown_table(scenario_summary, ["scenario_type", "trades", "filled", "net_r", "expectancy", "win_rate_pct", "profit_factor"]),
        "",
        "## Output Paths",
        "",
        f"- Trade log: `{OUT_TRADE_LOG.relative_to(ROOT)}`",
        f"- Equity curve: `{OUT_EQUITY_CURVE.relative_to(ROOT)}`",
        f"- Audit CSV: `{OUT_AUDIT.relative_to(ROOT)}`",
    ]
    OUT_REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=HEADLINE_SYMBOLS[:2])
    parser.add_argument("--order-expiry-minutes", type=int, default=DEFAULT_ORDER_EXPIRY_MINUTES)
    parser.add_argument("--max-hold-minutes", type=int, default=DEFAULT_MAX_HOLD_MINUTES)
    args = parser.parse_args()
    symbols = [symbol.upper() for symbol in args.symbols]
    trades = run_simulation(symbols, args.order_expiry_minutes, args.max_hold_minutes)
    if "planned_runner_baseline_r" not in trades.columns:
        trades["planned_runner_baseline_r"] = 0.0
    audit = build_audit(trades)
    if not audit["lookahead_pass"].all():
        raise RuntimeError(f"Execution lookahead audit failed for {int((~audit['lookahead_pass']).sum())} rows")
    curve = build_equity_curve(trades)
    OUT_TRADE_LOG.parent.mkdir(parents=True, exist_ok=True)
    trades.to_csv(OUT_TRADE_LOG, index=False, encoding="utf-8-sig")
    curve.to_csv(OUT_EQUITY_CURVE, index=False, encoding="utf-8-sig")
    audit.to_csv(OUT_AUDIT, index=False, encoding="utf-8-sig")
    write_report(trades, curve, audit, args.order_expiry_minutes, args.max_hold_minutes)
    print(f"trade_log={OUT_TRADE_LOG} rows={len(trades)}")
    print(f"equity_curve={OUT_EQUITY_CURVE} rows={len(curve)}")
    print(f"audit={OUT_AUDIT} rows={len(audit)} lookahead_pass={int(audit['lookahead_pass'].sum())}/{len(audit)}")
    print(f"report={OUT_REPORT}")


if __name__ == "__main__":
    main()
