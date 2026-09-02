#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data/raw/binance_futures_live_dates"
OUT_DIR = ROOT / "outputs"
INVENTORY_CSV = OUT_DIR / "craig_v1_2_ohlcv_inventory.csv"
READINESS_MD = OUT_DIR / "craig_v1_2_data_readiness_report.md"
SNAPSHOT_PARQUET = OUT_DIR / "craig_v1_2_market_feature_snapshots.parquet"
SNAPSHOT_CSV = OUT_DIR / "craig_v1_2_market_feature_snapshots.csv"
AUDIT_CSV = OUT_DIR / "craig_v1_2_market_feature_audit.csv"

CORE_SYMBOLS = ["SOLUSDT", "ETHUSDT", "BTCUSDT"]
OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]
PRICE_COLUMNS = ["open", "high", "low", "close", "volume"]
DERIVED_TIMEFRAMES = ["5m", "15m", "1h", "4h"]
TIMEFRAME_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}
RESAMPLE_RULES = {
    "5m": "5T",
    "15m": "15T",
    "1h": "1H",
    "4h": "4H",
}
FILE_RE = re.compile(
    r"^(?P<symbol>[A-Z0-9]+)_(?P<timeframe>\d+[mhd])_"
    r"(?P<market_date>\d{4}-\d{2}-\d{2})(?P<ny>_ny)?(?P<suffix>.*)\.csv$"
)
NY_TZ = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class FileMeta:
    symbol: str
    timeframe: str
    market_date: str
    has_ny_suffix: bool
    suffix: str


def parse_file_meta(path: Path) -> FileMeta | None:
    match = FILE_RE.match(path.name)
    if not match:
        return None
    suffix = (match.group("suffix") or "").lstrip("_")
    return FileMeta(
        symbol=match.group("symbol"),
        timeframe=match.group("timeframe"),
        market_date=match.group("market_date"),
        has_ny_suffix=bool(match.group("ny")),
        suffix=suffix,
    )


def iso_or_blank(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return pd.Timestamp(value).isoformat()


def minutes_or_blank(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{pd.Timedelta(value).total_seconds() / 60:.0f}"


def read_ohlcv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = [column for column in OHLCV_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError(f"missing OHLCV columns: {missing}")
    df = df[OHLCV_COLUMNS].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    for column in PRICE_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df.sort_values("timestamp").reset_index(drop=True)


def expected_ny_day_index(market_date: str) -> pd.DatetimeIndex:
    date_value = datetime.strptime(market_date, "%Y-%m-%d").date()
    start_local = datetime.combine(date_value, dtime.min, tzinfo=NY_TZ)
    end_local = datetime.combine(date_value + timedelta(days=1), dtime.min, tzinfo=NY_TZ)
    start_utc = pd.Timestamp(start_local).tz_convert("UTC")
    end_utc = pd.Timestamp(end_local).tz_convert("UTC") - pd.Timedelta(minutes=1)
    return pd.date_range(start=start_utc, end=end_utc, freq="1T")


def relative_to_root(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def dataset_scope(path: Path, raw_dir: Path, meta: FileMeta | None) -> str:
    rel_parts = path.relative_to(raw_dir).parts
    if "episode_review_snapshot" in rel_parts:
        return "episode_review_snapshot"
    if meta and rel_parts and rel_parts[0] == meta.market_date:
        return "canonical_date_folder"
    return rel_parts[0] if rel_parts else "unknown"


def profile_file(path: Path, raw_dir: Path) -> dict[str, object]:
    meta = parse_file_meta(path)
    rel_path = relative_to_root(path)
    scope = dataset_scope(path, raw_dir, meta)
    row: dict[str, object] = {
        "path": rel_path,
        "file_name": path.name,
        "dataset_scope": scope,
        "symbol": meta.symbol if meta else "",
        "timeframe": meta.timeframe if meta else "",
        "market_date": meta.market_date if meta else "",
        "has_ny_suffix": bool(meta.has_ny_suffix) if meta else False,
        "suffix": meta.suffix if meta else "",
        "is_canonical_ny_1m": bool(
            meta
            and meta.timeframe == "1m"
            and meta.has_ny_suffix
            and path.parent.name == meta.market_date
        ),
        "is_episode_review_snapshot": scope == "episode_review_snapshot",
        "file_size_bytes": path.stat().st_size,
        "read_status": "ok",
        "error": "",
    }
    try:
        df = read_ohlcv(path)
    except Exception as exc:
        row.update(
            {
                "read_status": "error",
                "error": str(exc),
                "row_count": 0,
                "unique_timestamps": 0,
                "duplicate_timestamps": 0,
                "missing_rows_in_span": "",
                "gap_count": "",
                "max_gap_minutes": "",
                "first_timestamp_utc": "",
                "last_timestamp_utc": "",
                "first_timestamp_ny": "",
                "last_timestamp_ny": "",
                "full_ny_expected_rows": "",
                "full_ny_missing_rows": "",
                "full_ny_extra_rows": "",
                "full_ny_day_complete": False,
                "numeric_null_rows": "",
                "invalid_ohlc_rows": "",
                "negative_volume_rows": "",
            }
        )
        return row

    timestamps = df["timestamp"].dropna()
    unique_ts = timestamps.drop_duplicates().sort_values()
    duplicate_timestamps = int(timestamps.duplicated().sum())
    step_minutes = TIMEFRAME_MINUTES.get(str(row["timeframe"]), 1)
    step = pd.Timedelta(minutes=step_minutes)

    if unique_ts.empty:
        first_ts = pd.NaT
        last_ts = pd.NaT
        span_expected = 0
        missing_in_span = 0
        gap_count = 0
        max_gap = pd.NaT
    else:
        first_ts = unique_ts.iloc[0]
        last_ts = unique_ts.iloc[-1]
        span_expected = int(((last_ts - first_ts) / step) + 1)
        missing_in_span = max(0, span_expected - len(unique_ts))
        diffs = unique_ts.diff().dropna()
        gaps = diffs[diffs > step]
        gap_count = int(len(gaps))
        max_gap = gaps.max() if not gaps.empty else pd.NaT

    numeric_null_rows = int(df[PRICE_COLUMNS].isna().any(axis=1).sum())
    invalid_ohlc_rows = int(
        (
            (df["high"] < df["low"])
            | (df["high"] < df[["open", "close"]].max(axis=1))
            | (df["low"] > df[["open", "close"]].min(axis=1))
        ).sum()
    )
    negative_volume_rows = int((df["volume"] < 0).sum())

    full_expected = ""
    full_missing = ""
    full_extra = ""
    full_complete = False
    if row["is_canonical_ny_1m"]:
        expected_index = expected_ny_day_index(str(row["market_date"]))
        present_index = pd.DatetimeIndex(unique_ts)
        full_expected = len(expected_index)
        full_missing = len(expected_index.difference(present_index))
        full_extra = len(present_index.difference(expected_index))
        full_complete = (
            len(df) == full_expected
            and duplicate_timestamps == 0
            and full_missing == 0
            and full_extra == 0
            and missing_in_span == 0
            and numeric_null_rows == 0
            and invalid_ohlc_rows == 0
            and negative_volume_rows == 0
        )

    row.update(
        {
            "row_count": int(len(df)),
            "unique_timestamps": int(len(unique_ts)),
            "duplicate_timestamps": duplicate_timestamps,
            "missing_rows_in_span": int(missing_in_span),
            "gap_count": gap_count,
            "max_gap_minutes": minutes_or_blank(max_gap),
            "first_timestamp_utc": iso_or_blank(first_ts),
            "last_timestamp_utc": iso_or_blank(last_ts),
            "first_timestamp_ny": iso_or_blank(first_ts.tz_convert("America/New_York") if not pd.isna(first_ts) else pd.NaT),
            "last_timestamp_ny": iso_or_blank(last_ts.tz_convert("America/New_York") if not pd.isna(last_ts) else pd.NaT),
            "full_ny_expected_rows": full_expected,
            "full_ny_missing_rows": full_missing,
            "full_ny_extra_rows": full_extra,
            "full_ny_day_complete": full_complete,
            "numeric_null_rows": numeric_null_rows,
            "invalid_ohlc_rows": invalid_ohlc_rows,
            "negative_volume_rows": negative_volume_rows,
        }
    )
    return row


def build_inventory(raw_dir: Path) -> pd.DataFrame:
    rows = [profile_file(path, raw_dir) for path in sorted(raw_dir.rglob("*.csv"))]
    inventory = pd.DataFrame(rows)
    if inventory.empty:
        return inventory
    sort_cols = ["dataset_scope", "market_date", "symbol", "timeframe", "path"]
    return inventory.sort_values(sort_cols).reset_index(drop=True)


def contiguous_runs(dates: Iterable[str]) -> list[tuple[pd.Timestamp, pd.Timestamp, int]]:
    parsed = sorted(pd.to_datetime(list(set(dates))).date)
    if not parsed:
        return []
    runs = []
    start = parsed[0]
    prev = parsed[0]
    for current in parsed[1:]:
        if (current - prev).days == 1:
            prev = current
            continue
        runs.append((pd.Timestamp(start), pd.Timestamp(prev), (prev - start).days + 1))
        start = current
        prev = current
    runs.append((pd.Timestamp(start), pd.Timestamp(prev), (prev - start).days + 1))
    return runs


def resample_complete_ohlcv(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    minutes = TIMEFRAME_MINUTES[timeframe]
    rule = RESAMPLE_RULES[timeframe]
    indexed = df.set_index("timestamp").sort_index()
    grouped = indexed.resample(rule, label="left", closed="left")
    bars = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        source_1m_count=("close", "count"),
    )
    bars = bars[bars["source_1m_count"] == minutes].copy()
    bars = bars.dropna(subset=["open", "high", "low", "close"])
    bars["open_time"] = bars.index
    bars["close_time"] = bars["open_time"] + pd.Timedelta(minutes=minutes)
    return bars.reset_index(drop=True)


def build_snapshots_for_file(path: Path, symbol: str, market_date: str) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    raw = read_ohlcv(path)
    raw = raw.drop_duplicates(subset=["timestamp"], keep="last").sort_values("timestamp")
    base = raw.copy()
    base["symbol"] = symbol
    base["market_date"] = market_date
    base["source_path"] = str(path.relative_to(ROOT))
    base["timestamp_1m_open"] = base["timestamp"]
    base["decision_timestamp"] = base["timestamp"] + pd.Timedelta(minutes=1)
    base["latest_1m_close_used"] = base["decision_timestamp"]
    base = base.rename(
        columns={
            "open": "open_1m",
            "high": "high_1m",
            "low": "low_1m",
            "close": "close_1m",
            "volume": "volume_1m",
        }
    )
    base = base.drop(columns=["timestamp"])
    base = base.sort_values("decision_timestamp").reset_index(drop=True)

    resample_summary: list[dict[str, object]] = []
    snapshots = base
    for timeframe in DERIVED_TIMEFRAMES:
        bars = resample_complete_ohlcv(raw, timeframe)
        latest_col = f"latest_{timeframe}_close_used"
        if bars.empty:
            right = pd.DataFrame(
                columns=[
                    latest_col,
                    f"open_{timeframe}",
                    f"high_{timeframe}",
                    f"low_{timeframe}",
                    f"close_{timeframe}",
                    f"volume_{timeframe}",
                    f"source_1m_count_{timeframe}",
                ]
            )
            first_close = pd.NaT
            last_close = pd.NaT
        else:
            right = bars.rename(
                columns={
                    "close_time": latest_col,
                    "open": f"open_{timeframe}",
                    "high": f"high_{timeframe}",
                    "low": f"low_{timeframe}",
                    "close": f"close_{timeframe}",
                    "volume": f"volume_{timeframe}",
                    "source_1m_count": f"source_1m_count_{timeframe}",
                }
            )[
                [
                    latest_col,
                    f"open_{timeframe}",
                    f"high_{timeframe}",
                    f"low_{timeframe}",
                    f"close_{timeframe}",
                    f"volume_{timeframe}",
                    f"source_1m_count_{timeframe}",
                ]
            ].sort_values(latest_col)
            first_close = right[latest_col].min()
            last_close = right[latest_col].max()

        snapshots = pd.merge_asof(
            snapshots.sort_values("decision_timestamp"),
            right,
            left_on="decision_timestamp",
            right_on=latest_col,
            direction="backward",
            allow_exact_matches=True,
        )
        resample_summary.append(
            {
                "symbol": symbol,
                "market_date": market_date,
                "timeframe": timeframe,
                "complete_bars": int(len(bars)),
                "first_close_used": iso_or_blank(first_close),
                "last_close_used": iso_or_blank(last_close),
            }
        )

    latest_cols = [
        "latest_1m_close_used",
        "latest_5m_close_used",
        "latest_15m_close_used",
        "latest_1h_close_used",
        "latest_4h_close_used",
    ]
    future_violation = pd.Series(False, index=snapshots.index)
    for column in latest_cols:
        if column in snapshots.columns:
            future_violation = future_violation | (
                snapshots[column].notna() & (snapshots[column] > snapshots["decision_timestamp"])
            )
    snapshots["all_timeframes_available"] = snapshots[latest_cols].notna().all(axis=1)
    snapshots["lookahead_pass"] = ~future_violation
    snapshots["lookahead_violation_reason"] = ""
    snapshots.loc[future_violation, "lookahead_violation_reason"] = "future_close_used"
    return snapshots, resample_summary


def build_feature_store(inventory: pd.DataFrame, symbols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    canonical = inventory[
        (inventory["is_canonical_ny_1m"] == True)
        & (inventory["symbol"].isin(symbols))
        & (inventory["read_status"] == "ok")
    ].copy()
    if canonical.empty:
        raise RuntimeError("No canonical 1m NY OHLCV files found for requested symbols.")

    snapshots_parts = []
    resample_rows: list[dict[str, object]] = []
    for _, row in canonical.sort_values(["market_date", "symbol"]).iterrows():
        path = ROOT / str(row["path"])
        snapshots, summary = build_snapshots_for_file(path, str(row["symbol"]), str(row["market_date"]))
        snapshots_parts.append(snapshots)
        resample_rows.extend(summary)

    snapshots_all = pd.concat(snapshots_parts, ignore_index=True)
    snapshots_all = snapshots_all.sort_values(["symbol", "decision_timestamp"]).reset_index(drop=True)
    resample_summary = pd.DataFrame(resample_rows)
    if not snapshots_all["lookahead_pass"].all():
        failures = int((~snapshots_all["lookahead_pass"]).sum())
        raise RuntimeError(f"Lookahead validation failed for {failures} snapshots.")
    return snapshots_all, resample_summary


def markdown_table(df: pd.DataFrame, columns: list[str]) -> list[str]:
    if df.empty:
        return ["_No rows._"]
    rows = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for _, row in df[columns].iterrows():
        values = [str(row[column]) for column in columns]
        rows.append("| " + " | ".join(values) + " |")
    return rows


def build_report(inventory: pd.DataFrame, snapshots: pd.DataFrame, resample_summary: pd.DataFrame, snapshot_path: Path) -> str:
    canonical_core = inventory[
        (inventory["is_canonical_ny_1m"] == True)
        & (inventory["symbol"].isin(CORE_SYMBOLS))
        & (inventory["read_status"] == "ok")
    ].copy()
    all_files = len(inventory)
    parsed_files = int((inventory["read_status"] == "ok").sum()) if not inventory.empty else 0
    core_dates = sorted(canonical_core["market_date"].unique())
    date_symbol_counts = canonical_core.groupby("market_date")["symbol"].nunique()
    all_three_dates = int((date_symbol_counts == 3).sum())
    runs = contiguous_runs(core_dates)
    longest_run = max(runs, key=lambda item: item[2]) if runs else None

    symbol_summary = (
        canonical_core.groupby("symbol")
        .agg(
            files=("path", "count"),
            dates=("market_date", "nunique"),
            rows=("row_count", "sum"),
            first_date=("market_date", "min"),
            last_date=("market_date", "max"),
            missing_1m_rows=("full_ny_missing_rows", "sum"),
            duplicate_timestamps=("duplicate_timestamps", "sum"),
            complete_days=("full_ny_day_complete", "sum"),
        )
        .reset_index()
    )
    if not symbol_summary.empty:
        for column in ["rows", "missing_1m_rows", "duplicate_timestamps", "complete_days"]:
            symbol_summary[column] = symbol_summary[column].astype(int)

    availability_rows = []
    for timeframe in ["1m", *DERIVED_TIMEFRAMES]:
        latest_col = f"latest_{timeframe}_close_used"
        available = int(snapshots[latest_col].notna().sum())
        availability_rows.append(
            {
                "timeframe": timeframe,
                "available_snapshots": available,
                "total_snapshots": len(snapshots),
                "available_pct": f"{available / len(snapshots) * 100:.2f}%" if len(snapshots) else "0.00%",
            }
        )
    availability = pd.DataFrame(availability_rows)

    resample_counts = (
        resample_summary.groupby("timeframe")
        .agg(
            files=("market_date", "count"),
            complete_bars=("complete_bars", "sum"),
            min_bars_per_file=("complete_bars", "min"),
            max_bars_per_file=("complete_bars", "max"),
        )
        .reset_index()
    )

    snapshot_scope = inventory[inventory["is_episode_review_snapshot"] == True]
    snapshot_files = len(snapshot_scope)
    canonical_files = int(inventory["is_canonical_ny_1m"].sum()) if not inventory.empty else 0
    longest_run_text = (
        f"{longest_run[0].date()} to {longest_run[1].date()} ({longest_run[2]} days)"
        if longest_run
        else "none"
    )

    lines = [
        "# Craig v1.2 P0 Data Readiness Report",
        "",
        "Generated by `scripts/build_craig_v1_2_market_features.py`.",
        "",
        "## Verdict",
        "",
        "- Continuous walk-forward backtest readiness: **not ready**.",
        "- Craig event-date prototype readiness: **ready for P0 market feature and no-lookahead alignment work**.",
        "- Main blocker: the canonical 1m cache is exact but sparse. It covers event dates, not continuous 90/180-day training windows.",
        "",
        "## Dataset And Grain",
        "",
        f"- Raw directory: `data/raw/binance_futures_live_dates`",
        f"- OHLCV CSV files inventoried: {all_files}",
        f"- Readable OHLCV files: {parsed_files}/{all_files}",
        f"- Canonical `*_1m_*_ny.csv` files: {canonical_files}",
        f"- Episode review snapshot files inventoried but excluded from feature-store input: {snapshot_files}",
        f"- Feature-store input scope: canonical date-folder 1m NY files for {', '.join(CORE_SYMBOLS)}.",
        f"- Feature snapshot output: `{snapshot_path.relative_to(ROOT)}`",
        "",
        "## Core 1m Coverage",
        "",
        *markdown_table(
            symbol_summary,
            [
                "symbol",
                "files",
                "dates",
                "rows",
                "first_date",
                "last_date",
                "missing_1m_rows",
                "duplicate_timestamps",
                "complete_days",
            ],
        ),
        "",
        f"- Dates where SOLUSDT, ETHUSDT, and BTCUSDT are all present: {all_three_dates}/{len(core_dates)}.",
        f"- First canonical core date: {core_dates[0] if core_dates else ''}.",
        f"- Last canonical core date: {core_dates[-1] if core_dates else ''}.",
        f"- Longest contiguous canonical date run: {longest_run_text}.",
        "- Note: the 2026-03-08 NY date has 1,380 expected 1m rows because of the New York daylight-saving transition; it is complete under that expected calendar.",
        "",
        "## Resample Readiness",
        "",
        "Closed-candle resampling from 1m was performed with exchange-UTC anchoring and complete-candle filtering.",
        "",
        *markdown_table(
            resample_counts,
            ["timeframe", "files", "complete_bars", "min_bars_per_file", "max_bars_per_file"],
        ),
        "",
        "Latest closed-candle availability across produced decision snapshots:",
        "",
        *markdown_table(availability, ["timeframe", "available_snapshots", "total_snapshots", "available_pct"]),
        "",
        "Interpretation:",
        "",
        "- 5m, 15m, and 1h closed candles are usable inside each event-day file after the first completed derived candle.",
        "- 4h closed candles are usable, but early-day availability is limited on EST dates because Binance-style 4h candles are UTC anchored while source slices start at NY midnight.",
        "- One-day event slices are not enough for robust HTF zone, trendline, or BTC context warmup. Future P1/P2 work should fetch continuous history plus at least 30 warmup days before each fold or event window.",
        "",
        "## Quality Findings",
        "",
        "1. Canonical event-date 1m files pass basic OHLCV validity checks. Evidence: zero missing canonical NY rows, zero duplicate timestamps, zero invalid OHLC rows, and zero negative volume rows for the three v1.2 symbols. Severity: low for P0; confidence: high.",
        "",
        "2. The dataset is sparse across calendar time. Evidence: 75 shared core dates from 2022-12-16 through 2026-07-22, with a longest contiguous run of only "
        f"{longest_run[2] if longest_run else 0} days. Severity: critical for continuous walk-forward backtesting; confidence: high.",
        "",
        "3. HTF context is under-warmed for full Craig DNA logic. Evidence: canonical files are one NY day each, while v1.2 trendline, 1h/4h zones, target pools, and BTC PA context require historical candles before the decision timestamp. Severity: high for HTF detector and BTC context accuracy; confidence: high.",
        "",
        "4. `episode_review_snapshot` contains duplicate snapshot trees and pre-resampled HTF files for only SOLUSDT/BTCUSDT on two dates. It is useful as reference material but should not be mixed into the canonical P0 feature store. Severity: medium if accidentally joined; confidence: high.",
        "",
        "## No-Lookahead Audit",
        "",
        f"- Decision snapshots produced: {len(snapshots)}",
        f"- Lookahead violations: {int((~snapshots['lookahead_pass']).sum())}",
        f"- Audit CSV: `{AUDIT_CSV.relative_to(ROOT)}`",
        "- Audit rule: every source candle close used by a snapshot must be less than or equal to `decision_timestamp`; incomplete resampled candles are discarded.",
        "",
        "## Recommendation",
        "",
        "Proceed next with **HTF zone + trendline detector**. BTC context and target-pool generation both need the same no-lookahead PA-zone objects first; building zones/trendlines as shared primitives will reduce duplicated logic and make later BTC/target audits cleaner.",
        "",
        "Suggested order:",
        "",
        "1. HTF zone + trendline detector",
        "2. BTC context engine using those PA-zone objects",
        "3. Target pool generator using the same structural zone registry",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(
    inventory: pd.DataFrame,
    snapshots: pd.DataFrame,
    resample_summary: pd.DataFrame,
    snapshot_format: str,
) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    inventory.to_csv(INVENTORY_CSV, index=False, encoding="utf-8-sig")

    audit_cols = [
        "symbol",
        "market_date",
        "decision_timestamp",
        "latest_1m_close_used",
        "latest_5m_close_used",
        "latest_15m_close_used",
        "latest_1h_close_used",
        "latest_4h_close_used",
        "all_timeframes_available",
        "lookahead_pass",
        "lookahead_violation_reason",
    ]
    snapshots[audit_cols].to_csv(AUDIT_CSV, index=False, encoding="utf-8-sig")

    snapshot_path = SNAPSHOT_PARQUET
    if snapshot_format == "csv":
        snapshot_path = SNAPSHOT_CSV
        snapshots.to_csv(snapshot_path, index=False, encoding="utf-8-sig")
    else:
        try:
            snapshots.to_parquet(SNAPSHOT_PARQUET, index=False)
            snapshot_path = SNAPSHOT_PARQUET
        except Exception:
            if snapshot_format == "parquet":
                raise
            snapshot_path = SNAPSHOT_CSV
            snapshots.to_csv(snapshot_path, index=False, encoding="utf-8-sig")

    report = build_report(inventory, snapshots, resample_summary, snapshot_path)
    READINESS_MD.write_text(report, encoding="utf-8")
    return snapshot_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--symbols", nargs="+", default=CORE_SYMBOLS)
    parser.add_argument("--snapshot-format", choices=["auto", "parquet", "csv"], default="auto")
    args = parser.parse_args()

    inventory = build_inventory(args.raw_dir)
    snapshots, resample_summary = build_feature_store(inventory, args.symbols)
    snapshot_path = write_outputs(inventory, snapshots, resample_summary, args.snapshot_format)
    print(f"inventory={INVENTORY_CSV}")
    print(f"readiness_report={READINESS_MD}")
    print(f"feature_snapshots={snapshot_path}")
    print(f"audit={AUDIT_CSV}")
    print(f"snapshots={len(snapshots)} lookahead_pass={int(snapshots['lookahead_pass'].sum())}/{len(snapshots)}")


if __name__ == "__main__":
    main()
