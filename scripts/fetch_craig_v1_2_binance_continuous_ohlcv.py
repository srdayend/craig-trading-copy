#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "data/raw/binance_futures_continuous"
PROCESSED_ROOT = ROOT / "data/processed/binance_futures_continuous"
OUT_DIR = ROOT / "outputs"
INVENTORY_CSV = OUT_DIR / "craig_v1_2_continuous_ohlcv_inventory.csv"
READINESS_MD = OUT_DIR / "craig_v1_2_continuous_data_readiness_report.md"

BINANCE_VISION_BASE = "https://data.binance.vision/data/futures/um"
BINANCE_FAPI_KLINES = "https://fapi.binance.com/fapi/v1/klines"
USER_AGENT = "CraigResearchDataCache/0.2"
CORE_SYMBOLS = ["SOLUSDT", "ETHUSDT", "BTCUSDT"]
INTERVAL = "1m"
INTERVAL_MS = 60_000
NY_TZ = "America/New_York"

KLINE_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "ignore",
]
NUMERIC_COLUMNS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
]


@dataclass(frozen=True)
class Chunk:
    symbol: str
    kind: str
    start_date: date
    end_date: date

    @property
    def label(self) -> str:
        if self.kind == "monthly":
            return self.start_date.strftime("%Y-%m")
        return self.start_date.isoformat()

    @property
    def file_name(self) -> str:
        return f"{self.symbol}-{INTERVAL}-{self.label}.zip"

    @property
    def url(self) -> str:
        return (
            f"{BINANCE_VISION_BASE}/{self.kind}/klines/"
            f"{self.symbol}/{INTERVAL}/{self.file_name}"
        )

    @property
    def raw_zip_path(self) -> Path:
        return RAW_ROOT / self.symbol / INTERVAL / "raw_zip" / self.kind / self.file_name

    @property
    def api_csv_path(self) -> Path:
        suffix = self.label if self.kind == "daily" else self.label.replace("-", "_")
        return RAW_ROOT / self.symbol / INTERVAL / "raw_api_csv" / f"{self.symbol}_{INTERVAL}_{suffix}.csv"

    @property
    def start_ms(self) -> int:
        return int(datetime.combine(self.start_date, datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000)

    @property
    def end_ms_exclusive(self) -> int:
        return int(
            datetime.combine(self.end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp()
            * 1000
        )


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def month_start(value: date) -> date:
    return value.replace(day=1)


def next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def month_end(value: date) -> date:
    return next_month(value.replace(day=1)) - timedelta(days=1)


def latest_complete_utc_date() -> date:
    return datetime.now(timezone.utc).date() - timedelta(days=1)


def iter_chunks(symbols: list[str], start_date: date, end_date: date) -> list[Chunk]:
    chunks: list[Chunk] = []
    for symbol in symbols:
        cursor = start_date
        while cursor <= end_date:
            current_month_end = month_end(cursor)
            if cursor.day == 1 and current_month_end <= end_date:
                chunks.append(Chunk(symbol=symbol, kind="monthly", start_date=cursor, end_date=current_month_end))
                cursor = next_month(cursor)
            else:
                chunks.append(Chunk(symbol=symbol, kind="daily", start_date=cursor, end_date=cursor))
                cursor += timedelta(days=1)
    return chunks


def request_url(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def download_vision_chunk(chunk: Chunk, force: bool) -> dict[str, object]:
    path = chunk.raw_zip_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0 and not force:
        return {
            "record_type": "raw_chunk",
            "symbol": chunk.symbol,
            "timeframe": INTERVAL,
            "chunk_kind": chunk.kind,
            "chunk_label": chunk.label,
            "chunk_start_date": chunk.start_date.isoformat(),
            "chunk_end_date": chunk.end_date.isoformat(),
            "source": "binance_vision",
            "status": "cached",
            "path": rel(path),
            "url": chunk.url,
            "bytes": path.stat().st_size,
            "error": "",
        }
    try:
        payload = request_url(chunk.url)
        tmp_path = path.with_suffix(path.suffix + ".part")
        tmp_path.write_bytes(payload)
        tmp_path.replace(path)
        status = "downloaded"
        error = ""
    except urllib.error.HTTPError as exc:
        status = f"http_{exc.code}"
        error = str(exc)
    except Exception as exc:
        status = "error"
        error = str(exc)
    return {
        "record_type": "raw_chunk",
        "symbol": chunk.symbol,
        "timeframe": INTERVAL,
        "chunk_kind": chunk.kind,
        "chunk_label": chunk.label,
        "chunk_start_date": chunk.start_date.isoformat(),
        "chunk_end_date": chunk.end_date.isoformat(),
        "source": "binance_vision",
        "status": status,
        "path": rel(path) if path.exists() else "",
        "url": chunk.url,
        "bytes": path.stat().st_size if path.exists() else 0,
        "error": error,
    }


def api_fetch_chunk(chunk: Chunk, pause: float) -> dict[str, object]:
    path = chunk.api_csv_path
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[list[object]] = []
    cursor = chunk.start_ms
    error = ""
    status = "api_downloaded"
    try:
        while cursor < chunk.end_ms_exclusive:
            end_ms = min(chunk.end_ms_exclusive - 1, cursor + INTERVAL_MS * 1500 - 1)
            params = urllib.parse.urlencode(
                {
                    "symbol": chunk.symbol,
                    "interval": INTERVAL,
                    "startTime": cursor,
                    "endTime": end_ms,
                    "limit": 1500,
                }
            )
            payload = json.loads(request_url(f"{BINANCE_FAPI_KLINES}?{params}", timeout=30).decode("utf-8"))
            if isinstance(payload, dict) and payload.get("code"):
                raise RuntimeError(payload)
            if not payload:
                break
            rows.extend(payload)
            last_open = int(payload[-1][0])
            next_cursor = last_open + INTERVAL_MS
            if next_cursor <= cursor:
                break
            cursor = next_cursor
            time.sleep(pause)
    except Exception as exc:
        status = "api_error"
        error = str(exc)

    if rows:
        with path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(KLINE_COLUMNS)
            writer.writerows(rows)
    return {
        "record_type": "raw_chunk",
        "symbol": chunk.symbol,
        "timeframe": INTERVAL,
        "chunk_kind": chunk.kind,
        "chunk_label": chunk.label,
        "chunk_start_date": chunk.start_date.isoformat(),
        "chunk_end_date": chunk.end_date.isoformat(),
        "source": "fapi_rest_fallback",
        "status": status,
        "path": rel(path) if path.exists() else "",
        "url": BINANCE_FAPI_KLINES,
        "bytes": path.stat().st_size if path.exists() else 0,
        "error": error,
    }


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def read_zip_csv(path: Path) -> pd.DataFrame:
    with zipfile.ZipFile(path) as zf:
        csv_names = [name for name in zf.namelist() if name.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise ValueError(f"expected one CSV in {path}, found {csv_names}")
        with zf.open(csv_names[0]) as f:
            return read_kline_csv(f)


def read_kline_csv(source: object) -> pd.DataFrame:
    payload = source.read()
    first_line = payload.splitlines()[0].decode("utf-8", errors="ignore") if payload else ""
    has_header = first_line.split(",", 1)[0] == "open_time"
    if has_header:
        df = pd.read_csv(io.BytesIO(payload))
    else:
        df = pd.read_csv(io.BytesIO(payload), header=None, names=KLINE_COLUMNS)
    missing = [col for col in KLINE_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"missing kline columns: {missing}")
    df = df[KLINE_COLUMNS].copy()
    for column in ["open_time", "close_time", "count"]:
        df[column] = pd.to_numeric(df[column], errors="coerce").astype("Int64")
    for column in [col for col in NUMERIC_COLUMNS if col != "count"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def read_source_chunk(record: dict[str, object]) -> pd.DataFrame:
    path_value = str(record.get("path", ""))
    if not path_value:
        return pd.DataFrame(columns=KLINE_COLUMNS)
    path = ROOT / path_value
    if path.suffix.lower() == ".zip":
        df = read_zip_csv(path)
    else:
        with path.open("rb") as f:
            df = read_kline_csv(f)
    df["source_file"] = path_value
    return df


def normalize_symbol(
    symbol: str,
    chunk_records: list[dict[str, object]],
    start_date: date,
    end_date: date,
) -> tuple[dict[str, object], pd.DataFrame]:
    symbol_records = [
        row
        for row in chunk_records
        if row.get("symbol") == symbol and str(row.get("status", "")) in {"cached", "downloaded", "api_downloaded"}
    ]
    frames = []
    for record in symbol_records:
        try:
            frames.append(read_source_chunk(record))
        except Exception as exc:
            record["status"] = "read_error"
            record["error"] = str(exc)
    if frames:
        df = pd.concat(frames, ignore_index=True)
    else:
        df = pd.DataFrame(columns=[*KLINE_COLUMNS, "source_file"])

    start_ms = int(datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(
        datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000
    )
    if not df.empty:
        df = df[(df["open_time"] >= start_ms) & (df["open_time"] < end_ms)].copy()
        df = df.sort_values(["open_time", "source_file"]).drop_duplicates("open_time", keep="last")
        df = df.sort_values("open_time").reset_index(drop=True)

    expected_index = pd.date_range(
        start=pd.Timestamp(start_ms, unit="ms", tz="UTC"),
        end=pd.Timestamp(end_ms - INTERVAL_MS, unit="ms", tz="UTC"),
        freq="1T",
    )
    present = pd.to_datetime(df["open_time"], unit="ms", utc=True, errors="coerce") if not df.empty else pd.Series([], dtype="datetime64[ns, UTC]")
    present_index = pd.DatetimeIndex(present.dropna())
    missing_index = expected_index.difference(present_index)
    extra_index = present_index.difference(expected_index)
    diffs = present_index.to_series().diff().dropna() if len(present_index) else pd.Series([], dtype="timedelta64[ns]")
    gaps = diffs[diffs > pd.Timedelta(minutes=1)]

    for column in NUMERIC_COLUMNS:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    if not df.empty:
        df["symbol"] = symbol
        df["timeframe"] = INTERVAL
        df["open_time_utc"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df["close_time_utc"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
        df["timestamp"] = df["open_time_utc"]
        ny_open = df["open_time_utc"].dt.tz_convert(NY_TZ)
        df["ny_date"] = ny_open.dt.date.astype(str)
        df["ny_time"] = ny_open.dt.strftime("%H:%M:%S")
        df["open_time_interval_ok"] = df["open_time"].diff().fillna(INTERVAL_MS).eq(INTERVAL_MS)
        ordered_cols = [
            "symbol",
            "timeframe",
            "timestamp",
            "open_time_utc",
            "close_time_utc",
            "ny_date",
            "ny_time",
            "open_time",
            "close_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_volume",
            "count",
            "taker_buy_volume",
            "taker_buy_quote_volume",
            "ignore",
            "source_file",
            "open_time_interval_ok",
        ]
        df = df[ordered_cols]

    null_numeric_rows = int(df[NUMERIC_COLUMNS].isna().any(axis=1).sum()) if not df.empty else 0
    invalid_ohlc_rows = (
        int(
            (
                (df["high"] < df["low"])
                | (df["high"] < df[["open", "close"]].max(axis=1))
                | (df["low"] > df[["open", "close"]].min(axis=1))
            ).sum()
        )
        if not df.empty
        else 0
    )
    negative_volume_rows = int((df["volume"] < 0).sum()) if not df.empty else 0
    duplicate_open_times = int(df["open_time"].duplicated().sum()) if not df.empty else 0

    normalized_path = (
        PROCESSED_ROOT
        / symbol
        / INTERVAL
        / f"{symbol}_{INTERVAL}_{start_date.isoformat()}_{end_date.isoformat()}.parquet"
    )
    normalized_path.parent.mkdir(parents=True, exist_ok=True)
    if not df.empty:
        df.to_parquet(normalized_path, index=False)

    summary = {
        "record_type": "normalized_symbol",
        "symbol": symbol,
        "timeframe": INTERVAL,
        "chunk_kind": "normalized",
        "chunk_label": f"{start_date.isoformat()}_{end_date.isoformat()}",
        "chunk_start_date": start_date.isoformat(),
        "chunk_end_date": end_date.isoformat(),
        "source": "normalized_from_raw_chunks",
        "status": "complete" if len(missing_index) == 0 and duplicate_open_times == 0 else "incomplete",
        "path": rel(normalized_path) if normalized_path.exists() else "",
        "url": "",
        "bytes": normalized_path.stat().st_size if normalized_path.exists() else 0,
        "error": "",
        "row_count": int(len(df)),
        "expected_rows": int(len(expected_index)),
        "missing_open_times": int(len(missing_index)),
        "extra_open_times": int(len(extra_index)),
        "duplicate_open_times": duplicate_open_times,
        "gap_count": int(len(gaps)),
        "max_gap_minutes": float(gaps.max().total_seconds() / 60) if len(gaps) else 0.0,
        "first_open_time_utc": df["open_time_utc"].min().isoformat() if not df.empty else "",
        "last_open_time_utc": df["open_time_utc"].max().isoformat() if not df.empty else "",
        "null_numeric_rows": null_numeric_rows,
        "invalid_ohlc_rows": invalid_ohlc_rows,
        "negative_volume_rows": negative_volume_rows,
        "interval_error_rows": int((~df["open_time_interval_ok"]).sum()) if not df.empty else 0,
    }
    return summary, df


def markdown_table(rows: list[dict[str, object]], columns: list[str]) -> list[str]:
    if not rows:
        return ["_No rows._"]
    lines = ["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return lines


def build_report(
    symbols: list[str],
    start_date: date,
    end_date: date,
    chunk_records: list[dict[str, object]],
    summaries: list[dict[str, object]],
) -> str:
    total_chunks = sum(1 for row in chunk_records if row.get("source") == "binance_vision")
    downloaded = sum(1 for row in chunk_records if row.get("status") == "downloaded")
    cached = sum(1 for row in chunk_records if row.get("status") == "cached")
    failed = [row for row in chunk_records if str(row.get("status", "")).startswith("http_") or row.get("status") == "error"]
    complete_symbols = [row for row in summaries if row.get("status") == "complete"]
    expected_days = (end_date - start_date).days + 1
    walk_forward_ready = len(complete_symbols) == len(symbols) and expected_days >= 300
    readiness = "ready" if walk_forward_ready else "not ready"

    lines = [
        "# Craig v1.2 Continuous OHLCV Data Readiness Report",
        "",
        "Generated by `scripts/fetch_craig_v1_2_binance_continuous_ohlcv.py`.",
        "",
        "## Verdict",
        "",
        f"- Target coverage: {start_date.isoformat()} to {end_date.isoformat()} UTC inclusive ({expected_days} days).",
        f"- Continuous walk-forward data foundation: **{readiness}**.",
        f"- Symbols: {', '.join(symbols)}.",
        "- Source priority: Binance Vision public USD-M futures klines first; REST API fallback only for missing chunks when explicitly enabled.",
        "",
        "## Normalized Symbol Summary",
        "",
        *markdown_table(
            summaries,
            [
                "symbol",
                "status",
                "row_count",
                "expected_rows",
                "missing_open_times",
                "duplicate_open_times",
                "gap_count",
                "invalid_ohlc_rows",
                "null_numeric_rows",
                "first_open_time_utc",
                "last_open_time_utc",
            ],
        ),
        "",
        "## Raw Chunk Download Summary",
        "",
        f"- Binance Vision chunk attempts: {total_chunks}",
        f"- Downloaded this run: {downloaded}",
        f"- Reused from cache: {cached}",
        f"- Failed Binance Vision chunks before optional fallback: {len(failed)}",
        "",
        "## Checks Performed",
        "",
        "- Primary key uniqueness: one row per `symbol,timeframe,open_time`.",
        "- Completeness: every UTC minute from start date 00:00 through end date 23:59 must exist.",
        "- Time-step validity: `open_time` interval must be exactly 60,000 ms after sorting.",
        "- Numeric validity: OHLCV and trade-count columns must parse as numeric.",
        "- OHLC validity: high must be >= open/close/low and low must be <= open/close/high.",
        "- Volume validity: base volume must not be negative.",
        "- Timezone handling: UTC timestamps are preserved; NY date/time fields are derived, not substituted for primary time.",
        "",
        "## Findings",
        "",
    ]
    if walk_forward_ready:
        lines.extend(
            [
                "1. The continuous OHLCV foundation is sufficient for v1.2 walk-forward scaffolding. Severity: low; confidence: high.",
                "",
                f"Evidence: all {len(symbols)} core symbols have complete minute coverage across {expected_days} UTC days, with no missing open times or duplicate open times in the normalized inventory.",
                "",
                "2. Remaining risk is methodological, not raw coverage. HTF detectors must still maintain closed-candle availability and row-level `available_at` / `latest_source_candle_close_used` fields. Severity: medium; confidence: high.",
            ]
        )
    else:
        lines.extend(
            [
                "1. Continuous data is still incomplete for walk-forward use. Severity: critical; confidence: high.",
                "",
                "Evidence: at least one core symbol is missing normalized rows or has missing/duplicate/gapped open times. Review the inventory CSV for failed chunks and rerun the fetcher.",
            ]
        )
    if failed:
        lines.extend(["", "Failed chunks:"])
        for row in failed[:20]:
            lines.append(
                f"- {row.get('symbol')} {row.get('chunk_kind')} {row.get('chunk_label')}: {row.get('status')} {row.get('error')}"
            )
        if len(failed) > 20:
            lines.append(f"- ... {len(failed) - 20} more")

    lines.extend(
        [
            "",
            "## Output Paths",
            "",
            f"- Inventory CSV: `{rel(INVENTORY_CSV)}`",
            f"- Raw zip root: `{rel(RAW_ROOT)}`",
            f"- Normalized parquet root: `{rel(PROCESSED_ROOT)}`",
            "",
            "## Next Use",
            "",
            "Use the normalized parquet files as the source for HTF resampling and zone/trendline registry generation. Do not mix these continuous files with the older event-date cache unless a script explicitly joins them by timestamp for an audit.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_inventory(records: list[dict[str, object]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "record_type",
        "symbol",
        "timeframe",
        "chunk_kind",
        "chunk_label",
        "chunk_start_date",
        "chunk_end_date",
        "source",
        "status",
        "path",
        "url",
        "bytes",
        "row_count",
        "expected_rows",
        "missing_open_times",
        "extra_open_times",
        "duplicate_open_times",
        "gap_count",
        "max_gap_minutes",
        "first_open_time_utc",
        "last_open_time_utc",
        "null_numeric_rows",
        "invalid_ohlc_rows",
        "negative_volume_rows",
        "interval_error_rows",
        "error",
    ]
    with INVENTORY_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=CORE_SYMBOLS)
    parser.add_argument("--start-date", default="2024-01-01")
    parser.add_argument("--end-date", default=latest_complete_utc_date().isoformat())
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--api-fallback", action="store_true")
    parser.add_argument("--pause", type=float, default=0.05)
    parser.add_argument("--download-only", action="store_true")
    args = parser.parse_args()

    symbols = [symbol.upper() for symbol in args.symbols]
    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date)
    if end_date < start_date:
        raise ValueError("end-date must be >= start-date")

    chunks = iter_chunks(symbols, start_date, end_date)
    chunk_records: list[dict[str, object]] = []
    for chunk in chunks:
        record = download_vision_chunk(chunk, args.force)
        chunk_records.append(record)
        if record["status"] not in {"cached", "downloaded"} and args.api_fallback:
            chunk_records.append(api_fetch_chunk(chunk, args.pause))
        time.sleep(args.pause)

    summaries: list[dict[str, object]] = []
    if not args.download_only:
        for symbol in symbols:
            summary, _ = normalize_symbol(symbol, chunk_records, start_date, end_date)
            summaries.append(summary)

    all_records = [*chunk_records, *summaries]
    write_inventory(all_records)
    report = build_report(symbols, start_date, end_date, chunk_records, summaries)
    READINESS_MD.write_text(report, encoding="utf-8")
    print(f"chunks={len(chunks)} inventory={INVENTORY_CSV}")
    print(f"readiness_report={READINESS_MD}")
    for summary in summaries:
        print(
            f"{summary['symbol']} rows={summary['row_count']} expected={summary['expected_rows']} "
            f"missing={summary['missing_open_times']} status={summary['status']}"
        )


if __name__ == "__main__":
    main()
