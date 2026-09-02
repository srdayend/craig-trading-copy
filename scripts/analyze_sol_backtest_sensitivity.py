from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
TRADES = ROOT / "outputs" / "sol_craig_rule_backtest_trades.csv"
TRACE = ROOT / "outputs" / "sol_craig_rule_backtest_trace_opportunities.csv"
OUT = ROOT / "outputs" / "sol_craig_rule_backtest_filter_sensitivity.csv"


def summarize(name: str, df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "filter": name,
            "trades": 0,
            "win_rate": "",
            "loss_rate": "",
            "total_r": 0,
            "avg_r": "",
            "profit_factor": "",
        }
    r = df["result_r"].astype(float)
    wins = r[r > 0]
    losses = r[r < 0]
    pf = wins.sum() / abs(losses.sum()) if abs(losses.sum()) > 0 else float("inf")
    return {
        "filter": name,
        "trades": len(df),
        "win_rate": round((r > 0).mean(), 3),
        "loss_rate": round((r < 0).mean(), 3),
        "total_r": round(r.sum(), 3),
        "avg_r": round(r.mean(), 3),
        "profit_factor": "inf" if pf == float("inf") else round(pf, 3),
    }


def main() -> None:
    trades = pd.read_csv(TRADES)
    traces = pd.read_csv(TRACE) if TRACE.exists() and TRACE.stat().st_size else pd.DataFrame()
    trades["result_r"] = trades["result_r"].astype(float)
    trades["displacement_score"] = trades["displacement_score"].astype(float)
    rows = []
    masks = {
        "baseline": pd.Series(True, index=trades.index),
        "drop_no_bias": trades["htf_bias"] != "no_bias",
        "ny_open_or_power_hour_only": trades["session_phase"].isin(["ny_open", "power_hour"]),
        "disp_2_4_plus_only": trades["displacement_score"] >= 2.4,
        "drop_market_fill": trades["entry_model"] != "market_fill",
        "leader_aligned_only": trades["leader_bias"] == trades["direction"],
        "one_hour_zone_only": trades["primary_zone"].str.startswith("1h:", na=False),
        "drop_late_and_no_bias": (trades["session_phase"] != "late_morning") & (trades["htf_bias"] != "no_bias"),
        "critical_strict_v1": (
            (trades["session_phase"].isin(["ny_open", "power_hour"]))
            & (trades["htf_bias"] != "no_bias")
            & (trades["displacement_score"] >= 2.4)
            & (trades["leader_bias"] == trades["direction"])
        ),
        "critical_strict_v2_no_market": (
            (trades["session_phase"].isin(["ny_open", "power_hour"]))
            & (trades["htf_bias"] != "no_bias")
            & (trades["displacement_score"] >= 2.4)
            & (trades["leader_bias"] == trades["direction"])
            & (trades["entry_model"] != "market_fill")
        ),
    }
    for name, mask in masks.items():
        rows.append(summarize(name, trades[mask]))
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(OUT)

    if not traces.empty:
        traces["result_r"] = traces["result_r"].astype(float)
        print("top trace flags")
        print(traces["hard_flags"].fillna("score_below_strict").str.split("|").explode().value_counts().head(8))


if __name__ == "__main__":
    main()
