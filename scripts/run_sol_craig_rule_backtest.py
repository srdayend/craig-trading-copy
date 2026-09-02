from __future__ import annotations

import csv
import json
import math
import time
import urllib.parse
import urllib.request
import urllib.error
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "binance_futures_1m"
OUT_DIR = ROOT / "outputs"
TRADES_CSV = OUT_DIR / "sol_craig_rule_backtest_trades.csv"
TRACE_CSV = OUT_DIR / "sol_craig_rule_backtest_trace_opportunities.csv"
SEGMENTS_CSV = OUT_DIR / "sol_craig_rule_backtest_segments.csv"
SUMMARY_MD = OUT_DIR / "sol_craig_rule_backtest_summary.md"
DATA_MANIFEST = OUT_DIR / "sol_craig_rule_backtest_data_manifest.md"

BINANCE_FAPI_BASE = "https://fapi.binance.com/fapi/v1/klines"
BINANCE_TIME = "https://fapi.binance.com/fapi/v1/time"
NY = ZoneInfo("America/New_York")
NY_TZ = "America/New_York"
INTERVAL_MS = 60_000
RISK_PCT_PER_TRADE = 1.0
FETCH_LOOKBACK_DAYS = 180
BACKTEST_LOOKBACK_DAYS = 120


@dataclass
class Zone:
    timeframe: str
    zone_type: str
    low: float
    high: float
    mid: float
    available_at: pd.Timestamp
    invalidated_at: pd.Timestamp | None
    quality: int


def http_json(url: str, params: dict | None = None, timeout: int = 30):
    query = "" if not params else "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url + query, headers={"User-Agent": "SOLRuleBacktest/0.1"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code not in {418, 429} or attempt == 5:
                raise
            wait = 8 * (attempt + 1)
            print(f"rate limited by Binance ({exc.code}); sleeping {wait}s")
            time.sleep(wait)
        except urllib.error.URLError:
            if attempt == 5:
                raise
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("unreachable http_json retry state")


def server_now_utc() -> datetime:
    payload = http_json(BINANCE_TIME)
    return datetime.fromtimestamp(payload["serverTime"] / 1000, tz=timezone.utc)


def fetch_1m(symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    cache = RAW_DIR / f"{symbol}_1m_{start:%Y%m%d}_{end:%Y%m%d}.csv"
    if cache.exists():
        return load_ohlcv(cache)

    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    rows = []
    cursor = start_ms
    while cursor < end_ms:
        payload = http_json(
            BINANCE_FAPI_BASE,
            {
                "symbol": symbol,
                "interval": "1m",
                "startTime": cursor,
                "endTime": end_ms,
                "limit": 1500,
            },
        )
        if isinstance(payload, dict) and payload.get("code"):
            raise RuntimeError(f"Binance error for {symbol}: {payload}")
        if not payload:
            break
        for item in payload:
            ts = int(item[0])
            if start_ms <= ts < end_ms:
                rows.append(
                    {
                        "timestamp": datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat(),
                        "open": float(item[1]),
                        "high": float(item[2]),
                        "low": float(item[3]),
                        "close": float(item[4]),
                        "volume": float(item[5]),
                    }
                )
        last_ts = int(payload[-1][0])
        next_cursor = last_ts + INTERVAL_MS
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        time.sleep(0.12)

    with cache.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(rows)
    return load_ohlcv(cache)


def load_ohlcv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").drop_duplicates("timestamp").set_index("timestamp")
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = df.resample(rule, label="left", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    )
    return out.dropna()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - prev_close).abs(),
            (out["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr20"] = tr.rolling(20, min_periods=5).mean()
    out["body_med20"] = (out["close"] - out["open"]).abs().rolling(20, min_periods=5).median().shift(1)
    out["trend_move_10"] = out["close"] - out["close"].shift(10)
    out["trend_score"] = 0
    threshold = out["atr20"] * 0.5
    out.loc[out["trend_move_10"] > threshold, "trend_score"] = 1
    out.loc[out["trend_move_10"] < -threshold, "trend_score"] = -1
    roll_high = out["high"].rolling(96, min_periods=20).max()
    roll_low = out["low"].rolling(96, min_periods=20).min()
    out["range_location"] = (out["close"] - roll_low) / (roll_high - roll_low)
    out["ret20"] = out["close"] / out["close"].shift(20) - 1
    return out


def completed_index(tf: pd.DataFrame, minutes: int) -> pd.DatetimeIndex:
    return tf.index + pd.to_timedelta(minutes, unit="m")


def asof_pos(done_index: pd.DatetimeIndex, ts: pd.Timestamp) -> int:
    return int(done_index.searchsorted(ts, side="right") - 1)


def build_fvg_zones(tf: pd.DataFrame, timeframe: str, minutes: int) -> list[Zone]:
    zones: list[Zone] = []
    done = completed_index(tf, minutes)
    highs = tf["high"].to_numpy()
    lows = tf["low"].to_numpy()
    closes = tf["close"].to_numpy()
    for i in range(2, len(tf)):
        c1_high = float(highs[i - 2])
        c1_low = float(lows[i - 2])
        c3_high = float(highs[i])
        c3_low = float(lows[i])
        definitions = []
        if c1_high < c3_low:
            definitions.append(("bullish_fvg", c1_high, c3_low))
        if c1_low > c3_high:
            definitions.append(("bearish_fvg", c3_high, c1_low))
        for zone_type, low, high in definitions:
            invalidated_at = None
            for j in range(i + 1, len(tf)):
                if zone_type == "bullish_fvg" and float(closes[j]) < low:
                    invalidated_at = done[j]
                    break
                if zone_type == "bearish_fvg" and float(closes[j]) > high:
                    invalidated_at = done[j]
                    break
            zones.append(
                Zone(
                    timeframe=timeframe,
                    zone_type=zone_type,
                    low=float(low),
                    high=float(high),
                    mid=(float(low) + float(high)) / 2.0,
                    available_at=done[i],
                    invalidated_at=invalidated_at,
                    quality=5,
                )
            )
    return zones


def swing_points(tf: pd.DataFrame, minutes: int, lookback: int = 3) -> list[dict]:
    points = []
    done = completed_index(tf, minutes)
    for i in range(lookback, len(tf) - lookback):
        window = tf.iloc[i - lookback : i + lookback + 1]
        row = tf.iloc[i]
        if float(row.high) >= float(window["high"].max()):
            points.append(
                {
                    "i": i,
                    "kind": "high",
                    "price": float(row.high),
                    "available_at": done[min(i + lookback, len(done) - 1)],
                }
            )
        if float(row.low) <= float(window["low"].min()):
            points.append(
                {
                    "i": i,
                    "kind": "low",
                    "price": float(row.low),
                    "available_at": done[min(i + lookback, len(done) - 1)],
                }
            )
    points.sort(key=lambda p: p["available_at"])
    return points


def build_repeated_sr_zones(tf: pd.DataFrame, timeframe: str, minutes: int, min_touches: int = 3) -> list[Zone]:
    """Build non-perfect but time-aware HTF SR boxes from repeated swing pivots."""
    zones: list[Zone] = []
    if len(tf) < 30:
        return zones
    atr_series = add_indicators(tf)["atr20"].ffill()
    points = swing_points(tf, minutes, lookback=3)
    for idx, point in enumerate(points):
        atr_value = float(atr_series.iloc[min(point["i"], len(atr_series) - 1)])
        if math.isnan(atr_value) or atr_value <= 0:
            continue
        tolerance = max(0.35 * atr_value, point["price"] * 0.001)
        prior = [
            p
            for p in points[max(0, idx - 40) : idx]
            if p["kind"] == point["kind"] and abs(p["price"] - point["price"]) <= tolerance
        ]
        if len(prior) + 1 < min_touches:
            continue
        prices = [p["price"] for p in prior] + [point["price"]]
        level = sum(prices) / len(prices)
        if point["kind"] == "low":
            zone_type = "support"
        else:
            zone_type = "resistance"
        zones.append(
            Zone(
                timeframe=timeframe,
                zone_type=zone_type,
                low=level - tolerance,
                high=level + tolerance,
                mid=level,
                available_at=point["available_at"],
                invalidated_at=None,
                quality=min(5, 2 + len(prices)),
            )
        )
    return zones


def prev_ny_day_levels(sol_1m: pd.DataFrame) -> dict:
    local_dates = sol_1m.index.tz_convert(NY_TZ).date
    grouped = sol_1m.assign(local_date=local_dates).groupby("local_date")
    days = sorted(grouped.groups)
    out = {}
    for idx in range(1, len(days)):
        prev_day = days[idx - 1]
        cur_day = days[idx]
        prev = grouped.get_group(prev_day)
        high = float(prev["high"].max())
        low = float(prev["low"].min())
        out[cur_day] = [
            Zone("1d", "pdh", high, high, high, pd.Timestamp.min.tz_localize("UTC"), None, 4),
            Zone("1d", "pdl", low, low, low, pd.Timestamp.min.tz_localize("UTC"), None, 4),
        ]
    return out


def active_zones(zones: list[Zone], avails: list[pd.Timestamp], ts: pd.Timestamp, limit: int = 80) -> list[Zone]:
    pos = bisect_right(avails, ts)
    valid = []
    for zone in reversed(zones[max(0, pos - 400) : pos]):
        if zone.invalidated_at is None or zone.invalidated_at > ts:
            valid.append(zone)
        if len(valid) >= limit:
            break
    return list(reversed(valid))


def session_phase(ts: pd.Timestamp) -> str:
    local = ts.tz_convert(NY_TZ)
    minutes = local.hour * 60 + local.minute
    if 9 * 60 + 30 <= minutes < 10 * 60 + 30:
        return "ny_open"
    if 10 * 60 + 30 <= minutes < 12 * 60:
        return "late_morning"
    if 14 * 60 <= minutes < 15 * 60 + 30:
        return "power_hour"
    return "other_session_context"


def direction_sign(direction: str) -> int:
    return 1 if direction == "long" else -1


def displacement(row, atr20: float, body_med: float, direction: str) -> float:
    high, low, close, open_ = float(row.high), float(row.low), float(row.close), float(row.open)
    if atr20 <= 0 or body_med <= 0 or high == low:
        return 0.0
    body_score = abs(close - open_) / body_med
    range_score = (high - low) / atr20
    close_score = (close - low) / (high - low) if direction == "long" else (high - close) / (high - low)
    return min(5.0, 0.45 * body_score + 0.35 * range_score + 0.20 * (2 * close_score))


def choch_type(sol: pd.DataFrame, i: int, direction: str, disp: float) -> str:
    def breaks(lookback: int) -> bool:
        if i < lookback + 2:
            return False
        prev = sol.iloc[i - lookback : i - 2]
        close = float(sol.iloc[i].close)
        if direction == "long":
            return close > float(prev["high"].max())
        return close < float(prev["low"].min())

    if breaks(12):
        return "strict_12"
    if breaks(5):
        return "micro_5"
    if disp >= 2.4 and breaks(3):
        return "impulse_micro_3"
    return "none"


def sweep_or_fail(sol: pd.DataFrame, i: int, direction: str) -> bool:
    if i < 12:
        return False
    prior = sol.iloc[i - 12 : i]
    row = sol.iloc[i]
    atr_local = float(prior["atr20"].dropna().tail(1).iloc[0]) if prior["atr20"].notna().any() else 0.0
    if direction == "long":
        recent_low = float(prior["low"].min())
        return float(row.low) <= recent_low + 0.15 * atr_local and float(row.close) > float(row.open)
    recent_high = float(prior["high"].max())
    return float(row.high) >= recent_high - 0.15 * atr_local and float(row.close) < float(row.open)


def zone_alignment(zones: list[Zone], direction: str) -> tuple[int, int, list[str]]:
    long_types = {"bullish_fvg", "pdl", "support", "range_low", "sr_flip_support", "support_trendline"}
    short_types = {"bearish_fvg", "pdh", "resistance", "range_high", "sr_flip_resistance", "resistance_trendline"}
    aligned = against = 0
    types = []
    for zone in zones:
        types.append(f"{zone.timeframe}:{zone.zone_type}")
        if zone.zone_type in long_types:
            aligned += direction == "long"
            against += direction == "short"
        elif zone.zone_type in short_types:
            aligned += direction == "short"
            against += direction == "long"
    return int(aligned), int(against), types[:6]


def candidate_target(direction: str, entry: float, stop: float, zones: list[Zone]) -> tuple[float, str, float]:
    risk = abs(entry - stop)
    sign = direction_sign(direction)
    candidates = []
    for zone in zones:
        price = zone.mid
        if sign * (price - entry) <= 0:
            continue
        rr = sign * (price - entry) / risk
        if rr >= 3.5:
            candidates.append((abs(price - entry), price, f"{zone.timeframe}:{zone.zone_type}", rr))
    if candidates:
        _, price, target_type, rr = sorted(candidates, key=lambda x: x[0])[0]
        return float(price), target_type, float(rr)
    target = entry + sign * 4.0 * risk
    return float(target), "synthetic_4R", 4.0


def score_candidate(
    phase: str,
    direction: str,
    htf_bias: str,
    bias_conf: float,
    aligned: int,
    against: int,
    range_loc: float | None,
    leader_bias: str,
    sweep: bool,
    choch: str,
    disp: float,
    rr: float,
    risk_pct_price: float,
    trade_count_day: int,
    cooldown_ok: bool,
) -> float:
    score = 0.0
    score += {"ny_open": 5, "late_morning": 3, "power_hour": 3, "other_session_context": 1}.get(phase, 0)
    score += 2  # news unknown, not clear enough for full credit.
    score += 3 if risk_pct_price > 0 else 0
    if leader_bias == direction:
        score += 3

    score += 6 if htf_bias in {direction, "no_bias"} else 2
    score += min(7, aligned * 3.5)
    if against:
        score -= min(6, against * 3)
    if range_loc is not None:
        if direction == "long" and range_loc <= 0.35:
            score += 4
        elif direction == "short" and range_loc >= 0.65:
            score += 4
        elif 0.40 <= range_loc <= 0.60:
            score -= 3
    score += min(5, max(0, bias_conf / 20))
    score += 3

    score += 5 if sweep else 0
    score += 8 if choch != "none" else 0
    score += 8 if disp >= 2.4 else 6 if disp >= 1.8 else 3 if disp >= 1.4 else 0
    score += 7 if disp >= 1.8 else 4 if disp >= 1.4 else 1
    score += 5

    score += 7 if 0.00025 <= risk_pct_price <= 0.012 else 3
    score += min(7, rr)
    score += 4
    score += 2

    score += 2
    score += 2 if cooldown_ok else -4
    score += 1 if trade_count_day < 3 else -5
    return round(max(0.0, min(100.0, score)), 2)


def likelihood(score: float, hard_flags: list[str], phase: str, aligned: int, leader_bias: str, direction: str) -> float:
    if hard_flags:
        return 0.0
    base = 100 / (1 + math.exp(-((score - 68) / 8)))
    if phase == "ny_open":
        base += 8
    if aligned:
        base += 6
    if leader_bias == direction:
        base += 5
    return round(max(0.0, min(100.0, base)), 2)


def simulate(sol: pd.DataFrame, start_i: int, candidate: dict) -> dict:
    entry = candidate["entry"]
    stop = candidate["stop"]
    target = candidate["target"]
    direction = candidate["direction"]
    risk = abs(entry - stop)
    sign = direction_sign(direction)
    partial_target = entry + sign * 4.0 * risk
    current_stop = stop
    fill_i = None
    fill_time = missed_time = be_time = partial_time = exit_time = ""
    exit_reason = "session_close"
    partial_done = False
    ambiguous = []

    start_ts = sol.index[start_i]
    local_date = start_ts.tz_convert(NY_TZ).date()
    day_rows = sol[(sol.index >= start_ts) & (sol.index.tz_convert(NY_TZ).date == local_date)]
    day_rows = day_rows[day_rows.index.tz_convert(NY_TZ).time <= datetime.strptime("16:00", "%H:%M").time()]

    for idx, row in day_rows.iterrows():
        high, low, close = float(row.high), float(row.low), float(row.close)
        if fill_i is None:
            moved_away = high >= entry + 2 * risk if direction == "long" else low <= entry - 2 * risk
            touched = low <= entry <= high
            if candidate["entry_model"] == "market_fill":
                touched = True
            if touched:
                fill_i = sol.index.get_loc(idx)
                fill_time = idx.isoformat()
                continue
            if moved_away:
                missed_time = idx.isoformat()
                return {
                    "fill_time": "",
                    "missed_time": missed_time,
                    "be_time": "",
                    "partial_time": "",
                    "exit_time": "",
                    "exit_reason": "missed_no_chase",
                    "result_r": 0.0,
                    "result_pct": 0.0,
                    "price_move_pct": 0.0,
                    "ambiguous": "",
                }
            continue

        stop_hit = low <= current_stop if direction == "long" else high >= current_stop
        target_hit = high >= target if direction == "long" else low <= target
        partial_hit = high >= partial_target if direction == "long" else low <= partial_target
        if stop_hit and (target_hit or partial_hit):
            ambiguous.append(idx.isoformat())
        if stop_hit:
            exit_time = idx.isoformat()
            if math.isclose(current_stop, entry, abs_tol=1e-9):
                exit_reason = "breakeven_after_partial" if partial_done else "breakeven"
                result_r = 2.0 if partial_done else 0.0
            else:
                exit_reason = "initial_stop"
                result_r = -1.0
            return finish_result(result_r, entry, current_stop, direction, exit_time, exit_reason, fill_time, be_time, partial_time, ambiguous)

        if not be_time:
            pre = sol.iloc[max(0, fill_i - 5) : fill_i]
            if not pre.empty:
                if direction == "long" and close > float(pre.high.max()) and close > entry:
                    current_stop = entry
                    be_time = idx.isoformat()
                elif direction == "short" and close < float(pre.low.min()) and close < entry:
                    current_stop = entry
                    be_time = idx.isoformat()

        if not partial_done and partial_hit:
            partial_done = True
            partial_time = idx.isoformat()
            current_stop = entry
            if not be_time:
                be_time = idx.isoformat()

        if target_hit:
            exit_time = idx.isoformat()
            target_rr = sign * (target - entry) / risk
            result_r = 2.0 + 0.5 * target_rr if partial_done else target_rr
            return finish_result(result_r, entry, target, direction, exit_time, "target", fill_time, be_time, partial_time, ambiguous)

    if fill_i is None:
        return {
            "fill_time": "",
            "missed_time": "",
            "be_time": "",
            "partial_time": "",
            "exit_time": "",
            "exit_reason": "not_filled_by_session_end",
            "result_r": 0.0,
            "result_pct": 0.0,
            "price_move_pct": 0.0,
            "ambiguous": "",
        }
    last = day_rows.iloc[-1]
    exit_price = float(last.close)
    raw_r = sign * (exit_price - entry) / risk
    result_r = 2.0 + 0.5 * raw_r if partial_done else raw_r
    return finish_result(result_r, entry, exit_price, direction, day_rows.index[-1].isoformat(), "session_close", fill_time, be_time, partial_time, ambiguous)


def finish_result(
    result_r: float,
    entry: float,
    exit_price: float,
    direction: str,
    exit_time: str,
    exit_reason: str,
    fill_time: str,
    be_time: str,
    partial_time: str,
    ambiguous: list[str],
) -> dict:
    price_move_pct = direction_sign(direction) * (exit_price - entry) / entry * 100
    return {
        "fill_time": fill_time,
        "missed_time": "",
        "be_time": be_time,
        "partial_time": partial_time,
        "exit_time": exit_time,
        "exit_reason": exit_reason,
        "result_r": round(result_r, 3),
        "result_pct": round(result_r * RISK_PCT_PER_TRADE, 3),
        "price_move_pct": round(price_move_pct, 3),
        "ambiguous": "|".join(ambiguous),
    }


def summarize_segments(trades: list[dict]) -> list[dict]:
    dims = ["direction", "session_phase", "htf_bias", "leader_bias", "entry_model", "range_bucket", "primary_zone", "disp_band"]
    rows = []
    for dim in dims:
        groups = defaultdict(list)
        for trade in trades:
            groups[trade.get(dim, "")].append(trade)
        for value, group in groups.items():
            if len(group) < 4:
                continue
            wins = [g for g in group if float(g["result_r"]) > 0]
            losses = [g for g in group if float(g["result_r"]) < 0]
            rows.append(
                {
                    "dimension": dim,
                    "value": value,
                    "trades": len(group),
                    "win_rate": round(len(wins) / len(group), 3),
                    "loss_rate": round(len(losses) / len(group), 3),
                    "avg_r": round(sum(float(g["result_r"]) for g in group) / len(group), 3),
                    "total_r": round(sum(float(g["result_r"]) for g in group), 3),
                }
            )
    rows.sort(key=lambda r: (r["avg_r"], -r["trades"]))
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    end = server_now_utc().replace(second=0, microsecond=0)
    start = end - timedelta(days=FETCH_LOOKBACK_DAYS)
    backtest_start = end - timedelta(days=BACKTEST_LOOKBACK_DAYS)
    print(
        f"fetching 1m Binance futures data {start:%Y-%m-%d} -> {end:%Y-%m-%d}; "
        f"backtesting from {backtest_start:%Y-%m-%d}"
    )
    raw_paths = {}
    sol = add_indicators(fetch_1m("SOLUSDT", start, end))
    raw_paths["SOLUSDT"] = RAW_DIR / f"SOLUSDT_1m_{start:%Y%m%d}_{end:%Y%m%d}.csv"
    btc = add_indicators(fetch_1m("BTCUSDT", start, end))
    raw_paths["BTCUSDT"] = RAW_DIR / f"BTCUSDT_1m_{start:%Y%m%d}_{end:%Y%m%d}.csv"
    eth = add_indicators(fetch_1m("ETHUSDT", start, end))
    raw_paths["ETHUSDT"] = RAW_DIR / f"ETHUSDT_1m_{start:%Y%m%d}_{end:%Y%m%d}.csv"
    write_data_manifest(start, end, raw_paths, {"SOLUSDT": len(sol), "BTCUSDT": len(btc), "ETHUSDT": len(eth)})

    sol15 = add_indicators(resample_ohlcv(sol, "15min"))
    sol1h = add_indicators(resample_ohlcv(sol, "1h"))
    sol4h = add_indicators(resample_ohlcv(sol, "4h"))
    sol1d = add_indicators(resample_ohlcv(sol, "1D"))
    btc15 = add_indicators(resample_ohlcv(btc, "15min"))
    eth15 = add_indicators(resample_ohlcv(eth, "15min"))

    done15, done1h, done4h, done1d = completed_index(sol15, 15), completed_index(sol1h, 60), completed_index(sol4h, 240), completed_index(sol1d, 1440)
    btcdone15, ethdone15 = completed_index(btc15, 15), completed_index(eth15, 15)
    zones = sorted(
        build_fvg_zones(sol15, "15m", 15)
        + build_fvg_zones(sol1h, "1h", 60)
        + build_fvg_zones(sol4h, "4h", 240)
        + build_repeated_sr_zones(sol15, "15m", 15, min_touches=3)
        + build_repeated_sr_zones(sol1h, "1h", 60, min_touches=2)
        + build_repeated_sr_zones(sol4h, "4h", 240, min_touches=2),
        key=lambda z: z.available_at,
    )
    zone_avails = [z.available_at for z in zones]
    pday = prev_ny_day_levels(sol)

    trades: list[dict] = []
    traces: list[dict] = []
    last_block_until = pd.Timestamp.min.tz_localize("UTC")
    day_trade_count = Counter()
    last_trace_until = {"long": pd.Timestamp.min.tz_localize("UTC"), "short": pd.Timestamp.min.tz_localize("UTC")}

    for i in range(22, len(sol)):
        ts = sol.index[i]
        if ts < backtest_start:
            continue
        phase = session_phase(ts)
        if ts < last_block_until:
            continue
        row = sol.iloc[i]
        c1 = sol.iloc[i - 2]
        direction = None
        fvg_low = fvg_high = None
        if float(c1.high) < float(row.low):
            direction = "long"
            fvg_low, fvg_high = float(c1.high), float(row.low)
        elif float(c1.low) > float(row.high):
            direction = "short"
            fvg_low, fvg_high = float(row.high), float(c1.low)
        if direction is None:
            continue

        atr1 = float(row.atr20) if not math.isnan(float(row.atr20)) else 0.0
        body_med = float(row.body_med20) if not math.isnan(float(row.body_med20)) else 0.0
        if atr1 <= 0 or body_med <= 0:
            continue
        mid = (fvg_low + fvg_high) / 2
        disp = displacement(row, atr1, body_med, direction)
        choch = choch_type(sol, i, direction, disp)
        local_date = ts.tz_convert(NY_TZ).date()
        day_key = str(local_date)

        pos15 = asof_pos(done15, ts)
        pos1h = asof_pos(done1h, ts)
        pos4h = asof_pos(done4h, ts)
        pos1d = asof_pos(done1d, ts)
        if min(pos15, pos1h, pos4h, pos1d) < 20:
            continue
        atr15 = float(sol15.iloc[pos15].atr20)
        near_threshold = max(0.75 * atr15, 4 * atr1)
        candidate_zones = active_zones(zones, zone_avails, ts) + pday.get(local_date, [])
        near = []
        for zone in candidate_zones:
            low, high = min(zone.low, zone.high), max(zone.low, zone.high)
            distance = 0.0 if low <= mid <= high else min(abs(mid - low), abs(mid - high))
            if distance <= near_threshold:
                near.append(zone)
        if not near:
            continue

        aligned, against, zone_types = zone_alignment(near, direction)
        stop_buffer = max(0.05 * atr1, 1e-9)
        if direction == "long":
            stop = min(float(sol.iloc[i - 2 : i + 1]["low"].min()), float(row.low)) - stop_buffer
        else:
            stop = max(float(sol.iloc[i - 2 : i + 1]["high"].max()), float(row.high)) + stop_buffer
        risk = abs(mid - stop)
        if risk <= 0:
            continue
        target, target_type, rr = candidate_target(direction, mid, stop, candidate_zones)
        risk_pct_price = risk / mid

        trends = [
            (int(sol1d.iloc[pos1d].trend_score), 8),
            (int(sol4h.iloc[pos4h].trend_score), 6),
            (int(sol1h.iloc[pos1h].trend_score), 5),
            (int(sol15.iloc[pos15].trend_score), 4),
        ]
        long_score = sum(weight for trend, weight in trends if trend > 0)
        short_score = sum(weight for trend, weight in trends if trend < 0)
        range_loc = float(sol15.iloc[pos15].range_location) if not math.isnan(float(sol15.iloc[pos15].range_location)) else None
        if range_loc is not None:
            if range_loc <= 0.25:
                long_score += 4
                short_score -= 3
            elif range_loc >= 0.75:
                short_score += 4
                long_score -= 3
        btcpos = asof_pos(btcdone15, ts)
        ethpos = asof_pos(ethdone15, ts)
        leader_move = 0.0
        if btcpos >= 20 and ethpos >= 20:
            leader_move = float(btc15.iloc[btcpos].ret20) + 0.5 * float(eth15.iloc[ethpos].ret20)
        leader_bias = "long" if leader_move > 0.001 else "short" if leader_move < -0.001 else "neutral"
        if leader_bias == "long":
            long_score += 3
        elif leader_bias == "short":
            short_score += 3
        diff = long_score - short_score
        htf_bias = "long" if diff >= 8 else "short" if diff <= -8 else "no_bias"
        bias_conf = min(100, abs(diff) * 8)

        sweep = sweep_or_fail(sol, max(0, i - 1), direction)
        cooldown_ok = ts >= last_block_until
        score = score_candidate(
            phase,
            direction,
            htf_bias,
            bias_conf,
            aligned,
            against,
            range_loc,
            leader_bias,
            sweep,
            choch,
            disp,
            rr,
            risk_pct_price,
            day_trade_count[day_key],
            cooldown_ok,
        )
        hard = []
        if disp < 1.4:
            hard.append("weak_displacement")
        if phase == "other_session_context" and disp < 2.2:
            hard.append("quiet_off_session")
        if choch == "none":
            hard.append("choch_not_confirmed")
        if rr < 3.5:
            hard.append("rr_below_minimum")
        if aligned == 0:
            hard.append("no_aligned_htf_zone")
        if htf_bias == "no_bias" and disp < 1.8:
            hard.append("bias_forcing")
        if not (0.00025 <= risk_pct_price <= 0.012):
            hard.append("risk_size_outlier")
        if day_trade_count[day_key] >= 3:
            hard.append("trade_count_cap")
        like = likelihood(score, hard, phase, aligned, leader_bias, direction)

        entry_model = "fvg_midpoint"
        if choch != "none" and disp >= 1.8 and abs(fvg_high - fvg_low) <= 0.35 * atr1:
            moved_from_mid = (float(row.close) - mid) * direction_sign(direction)
            if moved_from_mid >= 0.75 * atr1:
                entry_model = "market_fill"
                mid = float(row.low + 0.25 * (row.close - row.low)) if direction == "short" else float(row.high - 0.25 * (row.high - row.close))
                stop = mid - 0.75 * atr1 if direction == "long" else mid + 0.75 * atr1
                risk = abs(mid - stop)
                target, target_type, rr = candidate_target(direction, mid, stop, candidate_zones)
                risk_pct_price = risk / mid

        range_bucket = "unknown"
        if range_loc is not None:
            range_bucket = "low" if range_loc < 0.35 else "mid" if range_loc <= 0.65 else "high"
        disp_band = "2.4+" if disp >= 2.4 else "1.8-2.4" if disp >= 1.8 else "1.4-1.8" if disp >= 1.4 else "<1.4"
        base = {
            "timestamp": ts.isoformat(),
            "timestamp_ny": ts.tz_convert(NY_TZ).isoformat(),
            "direction": direction,
            "session_phase": phase,
            "entry_model": entry_model,
            "entry": round(mid, 6),
            "stop": round(stop, 6),
            "target": round(target, 6),
            "initial_risk": round(risk, 6),
            "risk_pct_price": round(risk_pct_price * 100, 4),
            "target_rr": round(rr, 3),
            "target_type": target_type,
            "setup_score": score,
            "craig_likelihood": like,
            "hard_flags": "|".join(hard),
            "htf_bias": htf_bias,
            "htf_long_score": long_score,
            "htf_short_score": short_score,
            "leader_bias": leader_bias,
            "range_location": "" if range_loc is None else round(range_loc, 3),
            "range_bucket": range_bucket,
            "choch_type": choch,
            "displacement_score": round(disp, 3),
            "disp_band": disp_band,
            "sweep_or_fail": sweep,
            "aligned_zones": aligned,
            "against_zones": against,
            "primary_zone": zone_types[0] if zone_types else "",
            "near_zone_types": "|".join(zone_types),
        }

        strict = not hard and score >= 75 and like >= 70
        loose = (not strict) and choch != "none" and disp >= 1.2 and rr >= 3.0 and score >= 58
        if strict:
            result = simulate(sol, i, base)
            trade = {**base, **result, "decision": "strict_take"}
            if trade["exit_reason"] not in {"missed_no_chase", "not_filled_by_session_end"}:
                trades.append(trade)
                day_trade_count[day_key] += 1
                exit_ts = pd.Timestamp(trade["exit_time"]) if trade["exit_time"] else ts
                cooldown = timedelta(minutes=20 if float(trade["result_r"]) < 0 else 5)
                last_block_until = exit_ts + cooldown
        elif loose:
            if ts < last_trace_until[direction]:
                continue
            result = simulate(sol, i, base)
            last_trace_until[direction] = ts + timedelta(minutes=15)
            trace = {**base, **result, "decision": "loose_trace"}
            if float(trace["result_r"]) >= 2.0:
                traces.append(trace)

    write_csv(TRADES_CSV, trades)
    traces = sorted(traces, key=lambda r: float(r["result_r"]), reverse=True)
    write_csv(TRACE_CSV, traces[:500])
    segments = summarize_segments(trades)
    write_csv(SEGMENTS_CSV, segments)
    write_summary(start, end, backtest_start, sol, btc, eth, trades, traces, segments)
    print(f"wrote {TRADES_CSV}")
    print(f"wrote {TRACE_CSV}")
    print(f"wrote {SEGMENTS_CSV}")
    print(f"wrote {SUMMARY_MD}")
    print(f"wrote {DATA_MANIFEST}")


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def write_summary(start, end, backtest_start, sol, btc, eth, trades, traces, segments) -> None:
    filled = trades
    wins = [t for t in filled if float(t["result_r"]) > 0]
    losses = [t for t in filled if float(t["result_r"]) < 0]
    bes = [t for t in filled if float(t["result_r"]) == 0]
    total_r = sum(float(t["result_r"]) for t in filled)
    avg_r = total_r / len(filled) if filled else 0
    win_rate = len(wins) / len(filled) if filled else 0
    loss_rate = len(losses) / len(filled) if filled else 0
    pf = sum(float(t["result_r"]) for t in wins) / abs(sum(float(t["result_r"]) for t in losses)) if losses else float("inf")
    avg_win = sum(float(t["result_r"]) for t in wins) / len(wins) if wins else 0
    avg_loss = sum(float(t["result_r"]) for t in losses) / len(losses) if losses else 0
    exit_counts = Counter(t["exit_reason"] for t in filled)
    loss_causes = Counter()
    for t in losses:
        loss_causes.update(
            [
                f"session={t['session_phase']}",
                f"bias={t['htf_bias']}",
                f"leader={t['leader_bias']}",
                f"zone={t['primary_zone']}",
                f"disp={t['disp_band']}",
                f"range={t['range_bucket']}",
            ]
        )
    weakest = [s for s in segments if int(s["trades"]) >= 4][:8]
    missed_by_reason = Counter()
    for trace in traces:
        flags = trace["hard_flags"].split("|") if trace["hard_flags"] else ["score_below_strict"]
        missed_by_reason.update(flags)

    lines = [
        "# SOL Craig-Rule First Backtest",
        "",
        f"Scope: Binance USD-M futures 1m, SOLUSDT traded, BTCUSDT/ETHUSDT used as leader context. Data cached from `{start:%Y-%m-%d}` to `{end:%Y-%m-%d}` UTC; backtest metrics use `{backtest_start:%Y-%m-%d}` to `{end:%Y-%m-%d}` UTC. This is a first critical-failure scan, not a production-grade fill model.",
        "",
        "## Headline Metrics",
        "",
        f"- SOL 1m rows: {len(sol):,}; BTC rows: {len(btc):,}; ETH rows: {len(eth):,}.",
        f"- Strict filled trades: {len(filled)}.",
        f"- Win rate: {pct(win_rate)}; loss rate: {pct(loss_rate)}; BE/flat rate: {pct(len(bes) / len(filled) if filled else 0)}.",
        f"- Total result: {total_r:.2f}R, equivalent to {total_r * RISK_PCT_PER_TRADE:.2f}% at 1% account risk per trade.",
        f"- Average trade: {avg_r:.2f}R; average win: {avg_win:.2f}R; average loss: {avg_loss:.2f}R; profit factor: {'inf' if math.isinf(pf) else f'{pf:.2f}'}.",
        "",
        "## Exit Mix",
        "",
    ]
    for key, value in exit_counts.most_common():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Loss Pattern Scan", ""])
    if losses:
        lines.append(f"- Loss trades: {len(losses)}. Most repeated tags across losing trades:")
        for key, value in loss_causes.most_common(12):
            lines.append(f"- `{key}`: {value}")
        lines.append("")
        lines.append("Weakest measured segments with at least 4 trades:")
        for row in weakest:
            lines.append(
                f"- `{row['dimension']}={row['value']}`: {row['trades']} trades, win {pct(float(row['win_rate']))}, avg {float(row['avg_r']):.2f}R, total {float(row['total_r']):.2f}R"
            )
    else:
        lines.append("- No losing strict trades in this run; this is unlikely to persist in larger samples.")
    lines.extend(["", "## Loose Trace Opportunities", ""])
    lines.append(
        f"- Profitable loose traces saved: {len(traces)} candidates with simulated result >= 2R, top 500 written to CSV."
    )
    if traces:
        lines.append("- Main reasons strict rules skipped profitable traces:")
        for key, value in missed_by_reason.most_common(10):
            lines.append(f"- `{key}`: {value}")
        lines.append("")
        lines.append("Top 10 loose traces by R:")
        for trace in traces[:10]:
            lines.append(
                f"- {trace['timestamp_ny']} {trace['direction']} {trace['result_r']}R, score {trace['setup_score']}, flags `{trace['hard_flags'] or 'score_below_strict'}`, zone `{trace['primary_zone']}`"
            )
    lines.extend(
        [
            "",
            "## First Critical Interpretation",
            "",
            "- Treat this as a pattern-finding backtest. It uses Binance 1m candles, conservative intrabar ordering, a simplified news model, and a simplified HTF zone engine.",
            "- The key things to inspect next are the weakest segments and the loose traces. If loose winners mostly fail because of one overly strict flag, that flag becomes the first improvement candidate.",
            "- If losses concentrate in no-bias, mid-range, leader-against, or weak-displacement segments, those should become stronger filters before expanding the test.",
            "",
            "## Files",
            "",
            f"- Trades: `{TRADES_CSV.relative_to(ROOT)}`",
            f"- Loose trace opportunities: `{TRACE_CSV.relative_to(ROOT)}`",
            f"- Segment table: `{SEGMENTS_CSV.relative_to(ROOT)}`",
        ]
    )
    SUMMARY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_data_manifest(start, end, raw_paths: dict[str, Path], row_counts: dict[str, int]) -> None:
    lines = [
        "# SOL Craig-Rule Backtest Data Manifest",
        "",
        f"Fetched period: `{start.isoformat()}` to `{end.isoformat()}`.",
        "Source: Binance USD-M futures public klines, interval `1m`.",
        "",
        "| symbol | rows | cached CSV |",
        "|---|---:|---|",
    ]
    for symbol, path in raw_paths.items():
        lines.append(f"| `{symbol}` | {row_counts.get(symbol, 0):,} | `{path.relative_to(ROOT)}` |")
    DATA_MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
