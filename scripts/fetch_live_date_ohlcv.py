#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_CSV = ROOT / "outputs/craig_live_trading_video_inventory.csv"
OUT_DIR = ROOT / "data/raw/binance_futures_live_dates"
OUT_MANIFEST_CSV = ROOT / "outputs/craig_live_trading_binance_data_manifest.csv"
OUT_MANIFEST_MD = ROOT / "outputs/craig_live_trading_binance_data_manifest.md"
BINANCE_FAPI_BASE = "https://fapi.binance.com/fapi/v1/klines"
NY = ZoneInfo("America/New_York")


def read_inventory(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def parse_iso_date(value: str) -> date:
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def date_window_ms(market_date: date, lookback_days: int) -> tuple[int, int]:
    start = datetime.combine(market_date - timedelta(days=lookback_days), dtime.min, tzinfo=NY)
    end = datetime.combine(market_date + timedelta(days=1), dtime.min, tzinfo=NY)
    return int(start.timestamp() * 1000), int(end.timestamp() * 1000)


def http_json(params: dict[str, str | int]) -> list:
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        f"{BINANCE_FAPI_BASE}?{query}",
        headers={"User-Agent": "CraigResearchDataCache/0.1"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if isinstance(payload, dict) and payload.get("code"):
        raise RuntimeError(payload)
    return payload


def fetch_1m(symbol: str, start_ms: int, end_ms: int, pause: float) -> list[dict[str, str | float]]:
    rows_by_ts: dict[int, dict[str, str | float]] = {}
    cursor = start_ms
    interval_ms = 60_000
    while cursor < end_ms:
        payload = http_json(
            {
                "symbol": symbol,
                "interval": "1m",
                "startTime": cursor,
                "endTime": min(end_ms, cursor + interval_ms * 1500),
                "limit": 1500,
            }
        )
        if not payload:
            break
        for item in payload:
            ts = int(item[0])
            if start_ms <= ts < end_ms:
                rows_by_ts[ts] = {
                    "timestamp": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(),
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "volume": float(item[5]),
                }
        last_ts = int(payload[-1][0])
        next_cursor = last_ts + interval_ms
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        time.sleep(pause)
    return [rows_by_ts[k] for k in sorted(rows_by_ts)]


def write_rows(path: Path, rows: list[dict[str, str | float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=["SOLUSDT", "BTCUSDT", "ETHUSDT"])
    parser.add_argument("--dates", nargs="*", help="Optional explicit NY market dates YYYY-MM-DD.")
    parser.add_argument("--lookback-days", type=int, default=0)
    parser.add_argument("--pause", type=float, default=0.03)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    wanted_dates: dict[str, set[str]] = {}
    if args.dates:
        for token in args.dates:
            wanted_dates.setdefault(token[:10], set()).add("manual_date_request")
    else:
        inventory = read_inventory(INVENTORY_CSV)
        for row in inventory:
            date_tokens = [token for token in row.get("market_date_for_fetch", "").split("|") if token]
            for token in date_tokens:
                wanted_dates.setdefault(token[:10], set()).add(row.get("video_id", ""))

    manifest_rows = []
    for date_text in sorted(wanted_dates):
        market_date = parse_iso_date(date_text)
        start_ms, end_ms = date_window_ms(market_date, args.lookback_days)
        for symbol in args.symbols:
            filename = f"{symbol}_1m_{date_text}_ny"
            if args.lookback_days:
                filename += f"_lookback{args.lookback_days}"
            path = OUT_DIR / date_text / f"{filename}.csv"
            status = "cached_existing"
            error = ""
            rows_count = 0
            if not path.exists() or args.force:
                try:
                    rows = fetch_1m(symbol, start_ms, end_ms, args.pause)
                    write_rows(path, rows)
                    rows_count = len(rows)
                    status = "fetched"
                except Exception as exc:  # pragma: no cover - network dependent
                    status = "error"
                    error = str(exc)
            if path.exists() and rows_count == 0:
                with path.open(encoding="utf-8") as f:
                    rows_count = max(0, sum(1 for _ in f) - 1)
            manifest_rows.append(
                {
                    "market_date_for_fetch": date_text,
                    "symbol": symbol,
                    "path": str(path),
                    "rows": rows_count,
                    "videos": "|".join(sorted(wanted_dates[date_text])),
                    "lookback_days": args.lookback_days,
                    "status": status,
                    "error": error,
                }
            )

    with OUT_MANIFEST_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "market_date_for_fetch",
                "symbol",
                "path",
                "rows",
                "videos",
                "lookback_days",
                "status",
                "error",
            ],
        )
        writer.writeheader()
        writer.writerows(manifest_rows)

    total_dates = len({r["market_date_for_fetch"] for r in manifest_rows})
    ok = sum(1 for r in manifest_rows if r["status"] in {"fetched", "cached_existing"} and int(r["rows"] or 0) > 0)
    total = len(manifest_rows)
    lines = [
        "# Craig LIVE 날짜 Binance 1분봉 캐시",
        "",
        f"- 날짜 수: {total_dates}",
        f"- 심볼: {', '.join(args.symbols)}",
        f"- 성공 파일: {ok}/{total}",
        f"- NY 세션 기준 lookback days: {args.lookback_days}",
        "",
        "주의: 실제 시장 날짜가 검증되지 않은 영상은 업로드일 proxy로 받은 데이터다. 이 데이터는 비교 준비용 캐시이지, 최종 Craig 일치성 판정용이 아니다.",
        "",
        "CSV manifest: `outputs/craig_live_trading_binance_data_manifest.csv`",
    ]
    OUT_MANIFEST_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"dates={total_dates} files={total} ok={ok} manifest={OUT_MANIFEST_CSV}")


if __name__ == "__main__":
    main()
