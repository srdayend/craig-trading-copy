#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs"
DECISION_UNITS = OUT_DIR / "gold_v03_decision_units_v1.csv"
COVERAGE_MANIFEST = OUT_DIR / "gold_v03_v1_ohlcv_coverage_manifest.csv"
FEATURE_MATRIX = OUT_DIR / "craig_v1_feature_matrix.csv"

NY = ZoneInfo("America/New_York")
UTC = timezone.utc
CORE_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
SUPPORTED_SYMBOLS = CORE_SYMBOLS + ["ATOMUSDT"]


@dataclass(frozen=True)
class DecisionTime:
    market_date: str
    local_dt: datetime | None
    cutoff_utc: pd.Timestamp | None
    parse_mode: str
    parse_confidence: str
    session_phase: str


def clean(value: object) -> str:
    return "" if value is None else str(value).strip()


def lower(value: object) -> str:
    return clean(value).lower()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def first_market_date(value: str) -> str:
    dates = re.findall(r"\d{4}-\d{2}-\d{2}", clean(value))
    return dates[0] if dates else ""


def phrase_time(window: str) -> tuple[time | None, str]:
    text = lower(window)
    phrase_map: list[tuple[list[str], time, str]] = [
        (["pre-09:30", "pre 09:30", "pre open", "before open"], time(9, 15), "phrase_pre_open"),
        (["09:30 open", "ny open", "market open", "open onward", "open row"], time(9, 30), "phrase_open"),
        (["early session", "early rows"], time(9, 45), "phrase_early_session"),
        (["late morning"], time(11, 0), "phrase_late_morning"),
        (["midday"], time(12, 30), "phrase_midday"),
        (["afternoon"], time(14, 30), "phrase_afternoon"),
        (["power hour"], time(15, 0), "phrase_power_hour"),
        (["dinner", "gym"], time(17, 0), "phrase_dinner_gym"),
        (["evening", "late session", "late night", "night"], time(20, 0), "phrase_evening"),
        (["overnight", "asia"], time(22, 0), "phrase_overnight_asia"),
    ]
    for needles, parsed, mode in phrase_map:
        if any(needle in text for needle in needles):
            return parsed, mode
    return None, ""


def session_phase(local_dt: datetime | None) -> str:
    if local_dt is None:
        return "unknown_time"
    minute = local_dt.hour * 60 + local_dt.minute
    if minute < 8 * 60:
        return "pre_0800"
    if minute < 9 * 60 + 30:
        return "ny_0800_0930"
    if minute < 10 * 60 + 30:
        return "ny_open_0930_1030"
    if minute < 12 * 60:
        return "ny_late_morning"
    if minute < 14 * 60:
        return "ny_midday"
    if minute < 16 * 60:
        return "ny_afternoon"
    if minute < 20 * 60:
        return "ny_evening"
    return "post_2000"


def parse_decision_time(row: dict[str, str]) -> DecisionTime:
    date_text = first_market_date(row.get("market_date_utc_minus4", ""))
    window = clean(row.get("market_time_window_utc_minus4", ""))
    if not date_text:
        return DecisionTime("", None, None, "missing_date", "none", "unknown_time")

    parsed_time: time | None = None
    mode = "missing_time"
    confidence = "none"
    matches = re.findall(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)", window)
    if matches:
        hour, minute = matches[0]
        parsed_time = time(int(hour), int(minute))
        mode = "explicit_time_in_window"
        confidence = "high" if lower(row.get("time_confidence", "")).startswith("high") else "medium"
    else:
        parsed_time, mode = phrase_time(window)
        if parsed_time is not None:
            confidence = "low_phrase_anchor" if lower(row.get("time_confidence", "")).startswith("low") else "medium_phrase_anchor"
        else:
            parsed_time = time(12, 0)
            mode = "date_only_no_intraday_time_default_1200"
            confidence = "low_default_time"

    local_dt = datetime.combine(datetime.fromisoformat(date_text).date(), parsed_time, tzinfo=NY)
    cutoff_utc = pd.Timestamp(local_dt.astimezone(UTC))
    return DecisionTime(date_text, local_dt, cutoff_utc, mode, confidence, session_phase(local_dt))


def coverage_lookup(manifest_rows: list[dict[str, str]]) -> dict[tuple[str, str], Path]:
    out: dict[tuple[str, str], Path] = {}
    for row in manifest_rows:
        if row.get("coverage_status") != "dated_file":
            continue
        path = Path(row.get("path", ""))
        out[(row.get("market_date_utc_minus4", ""), row.get("symbol", ""))] = path
    return out


@lru_cache(maxsize=256)
def load_ohlcv(path_text: str) -> pd.DataFrame:
    path = Path(path_text)
    if not path.exists():
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.read_csv(path)
    if df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.sort_values("timestamp").drop_duplicates("timestamp").set_index("timestamp")
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def asof_history(df: pd.DataFrame, cutoff_utc: pd.Timestamp | None) -> pd.DataFrame:
    if df.empty or cutoff_utc is None:
        return df.iloc[0:0].copy()
    return df[df.index < cutoff_utc].copy()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    return pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def safe_float(value: object) -> float | None:
    text = clean(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def ret_close(hist: pd.DataFrame, minutes: int) -> float | None:
    if len(hist) <= minutes:
        return None
    now = float(hist["close"].iloc[-1])
    then = float(hist["close"].iloc[-1 - minutes])
    if then == 0:
        return None
    return now / then - 1.0


def latest_atr(hist: pd.DataFrame, period: int = 20) -> float | None:
    if len(hist) < 5:
        return None
    tr = true_range(hist)
    atr = tr.rolling(period, min_periods=5).mean().iloc[-1]
    if pd.isna(atr):
        return None
    return float(atr)


def displacement_features(hist: pd.DataFrame, side: str) -> dict[str, object]:
    if len(hist) < 22 or side not in {"long", "short"}:
        return {
            "feature_displacement_score": "",
            "feature_choch_type": "unknown",
            "feature_bos_type": "unknown",
        }
    row = hist.iloc[-1]
    atr = latest_atr(hist) or 0.0
    bodies = (hist["close"] - hist["open"]).abs().iloc[-21:-1]
    body_med = float(bodies.median()) if len(bodies) else 0.0
    if atr <= 0 or body_med <= 0 or float(row.high) == float(row.low):
        disp = 0.0
    else:
        body_score = abs(float(row.close) - float(row.open)) / body_med
        range_score = (float(row.high) - float(row.low)) / atr
        close_score = (
            (float(row.close) - float(row.low)) / (float(row.high) - float(row.low))
            if side == "long"
            else (float(row.high) - float(row.close)) / (float(row.high) - float(row.low))
        )
        disp = min(5.0, 0.45 * body_score + 0.35 * range_score + 0.20 * (2 * close_score))

    def breaks(lookback: int) -> bool:
        prior = hist.iloc[-lookback - 2 : -2]
        if prior.empty:
            return False
        close = float(row.close)
        if side == "long":
            return close > float(prior["high"].max())
        return close < float(prior["low"].min())

    if breaks(12):
        choch = "strict_12"
    elif breaks(5):
        choch = "micro_5"
    elif disp >= 2.4 and breaks(3):
        choch = "impulse_micro_3"
    else:
        choch = "none"
    return {
        "feature_displacement_score": round(disp, 4),
        "feature_choch_type": choch,
        "feature_bos_type": "bos_proxy" if choch != "none" else "none",
    }


def fvg_zones(hist: pd.DataFrame) -> list[dict[str, object]]:
    zones: list[dict[str, object]] = []
    if len(hist) < 3:
        return zones
    rows = hist.reset_index()
    for i in range(2, len(rows)):
        c1 = rows.iloc[i - 2]
        c3 = rows.iloc[i]
        definitions: list[tuple[str, float, float]] = []
        if float(c1.high) < float(c3.low):
            definitions.append(("bullish", float(c1.high), float(c3.low)))
        if float(c1.low) > float(c3.high):
            definitions.append(("bearish", float(c3.high), float(c1.low)))
        for direction, low_price, high_price in definitions:
            mid = (low_price + high_price) / 2.0
            future = rows.iloc[i + 1 :]
            freshness = "new_or_active"
            if not future.empty:
                if direction == "bullish":
                    if (future["close"] < low_price).any():
                        freshness = "invalidated"
                    elif (future["low"] <= low_price).any():
                        freshness = "fully_mitigated"
                    elif (future["low"] <= mid).any():
                        freshness = "midpoint_touched"
                else:
                    if (future["close"] > high_price).any():
                        freshness = "invalidated"
                    elif (future["high"] >= high_price).any():
                        freshness = "fully_mitigated"
                    elif (future["high"] >= mid).any():
                        freshness = "midpoint_touched"
            zones.append(
                {
                    "direction": direction,
                    "low": low_price,
                    "high": high_price,
                    "mid": mid,
                    "timestamp": c3.timestamp,
                    "freshness": freshness,
                }
            )
    return zones


def fvg_features(hist: pd.DataFrame, side: str) -> dict[str, object]:
    zones = fvg_zones(hist.iloc[-180:]) if len(hist) else []
    side_dir = "bullish" if side == "long" else "bearish" if side == "short" else ""
    same = [z for z in zones if z["direction"] == side_dir]
    active_same = [z for z in same if z["freshness"] in {"new_or_active", "midpoint_touched"}]
    latest = same[-1] if same else None
    active = active_same[-1] if active_same else None
    return {
        "feature_fvg_count_recent": len(zones),
        "feature_fvg_side_count_recent": len(same),
        "feature_fvg_active_for_side": "true" if active else "false",
        "feature_fvg_latest_freshness_for_side": clean(latest["freshness"]) if latest else "none",
        "feature_fvg_active_mid_for_side": "" if active is None else round(float(active["mid"]), 6),
    }


def swing_points(hist: pd.DataFrame, lookback: int = 3) -> list[dict[str, object]]:
    points: list[dict[str, object]] = []
    if len(hist) < lookback * 2 + 1:
        return points
    rows = hist.reset_index()
    for i in range(lookback, len(rows) - lookback):
        window = rows.iloc[i - lookback : i + lookback + 1]
        row = rows.iloc[i]
        if float(row.high) >= float(window["high"].max()):
            points.append({"kind": "high", "price": float(row.high), "index": i, "timestamp": row.timestamp})
        if float(row.low) <= float(window["low"].min()):
            points.append({"kind": "low", "price": float(row.low), "index": i, "timestamp": row.timestamp})
    return points


def sr_features(hist: pd.DataFrame) -> dict[str, object]:
    if len(hist) < 30:
        return {
            "feature_sr_cluster_count": 0,
            "feature_nearest_sr_kind": "unknown",
            "feature_nearest_sr_distance_atr": "",
        }
    recent = hist.iloc[-240:]
    atr = latest_atr(recent) or 0.0
    close = float(recent["close"].iloc[-1])
    if atr <= 0:
        return {
            "feature_sr_cluster_count": 0,
            "feature_nearest_sr_kind": "unknown",
            "feature_nearest_sr_distance_atr": "",
        }
    tolerance = max(0.35 * atr, close * 0.001)
    pivots = swing_points(recent)
    clusters: list[dict[str, object]] = []
    for pivot in pivots:
        match = None
        for cluster in clusters:
            if abs(float(cluster["level"]) - float(pivot["price"])) <= tolerance:
                match = cluster
                break
        if match is None:
            match = {"level": float(pivot["price"]), "prices": [], "highs": 0, "lows": 0}
            clusters.append(match)
        match["prices"].append(float(pivot["price"]))
        match["level"] = sum(match["prices"]) / len(match["prices"])
        match["highs"] += 1 if pivot["kind"] == "high" else 0
        match["lows"] += 1 if pivot["kind"] == "low" else 0
    clusters = [c for c in clusters if int(c["highs"]) + int(c["lows"]) >= 2]
    if not clusters:
        return {
            "feature_sr_cluster_count": 0,
            "feature_nearest_sr_kind": "none",
            "feature_nearest_sr_distance_atr": "",
        }
    nearest = min(clusters, key=lambda c: abs(float(c["level"]) - close))
    if int(nearest["lows"]) >= int(nearest["highs"]) and close >= float(nearest["level"]):
        kind = "support_or_sr_flip_support"
    elif int(nearest["highs"]) > int(nearest["lows"]) and close <= float(nearest["level"]):
        kind = "resistance_or_sr_flip_resistance"
    else:
        kind = "mixed_repeated_sr"
    return {
        "feature_sr_cluster_count": len(clusters),
        "feature_nearest_sr_kind": kind,
        "feature_nearest_sr_distance_atr": round(abs(float(nearest["level"]) - close) / atr, 4),
    }


def trendline_features(hist: pd.DataFrame) -> dict[str, object]:
    if len(hist) < 40:
        return {
            "feature_trendline_proxy": "unknown",
            "feature_trendline_proxy_confidence": "low_missing_swings",
        }
    recent = hist.iloc[-220:]
    atr = latest_atr(recent) or 0.0
    if atr <= 0:
        return {
            "feature_trendline_proxy": "unknown",
            "feature_trendline_proxy_confidence": "low_no_atr",
        }
    close = float(recent["close"].iloc[-1])
    pivots = swing_points(recent)
    best: tuple[float, str] | None = None
    for kind, label in [("low", "support_trendline_proxy"), ("high", "resistance_trendline_proxy")]:
        typed = [p for p in pivots if p["kind"] == kind][-6:]
        if len(typed) < 2:
            continue
        p1, p2 = typed[-2], typed[-1]
        if int(p2["index"]) == int(p1["index"]):
            continue
        slope = (float(p2["price"]) - float(p1["price"])) / (int(p2["index"]) - int(p1["index"]))
        projection = float(p1["price"]) + slope * (len(recent) - 1 - int(p1["index"]))
        dist_atr = abs(close - projection) / atr
        if best is None or dist_atr < best[0]:
            best = (dist_atr, label)
    if best is None:
        return {
            "feature_trendline_proxy": "none",
            "feature_trendline_proxy_confidence": "low_no_projection",
        }
    return {
        "feature_trendline_proxy": best[1] if best[0] <= 2.5 else "far_from_recent_trendline_proxy",
        "feature_trendline_proxy_confidence": "low_heuristic",
    }


def sweep_features(hist: pd.DataFrame) -> dict[str, object]:
    if len(hist) < 22:
        return {"feature_sweep_liquidity_proxy": "unknown"}
    prior = hist.iloc[-21:-1]
    row = hist.iloc[-1]
    prior_high = float(prior["high"].max())
    prior_low = float(prior["low"].min())
    if float(row.high) > prior_high and float(row.close) < prior_high:
        return {"feature_sweep_liquidity_proxy": "bearish_high_sweep"}
    if float(row.low) < prior_low and float(row.close) > prior_low:
        return {"feature_sweep_liquidity_proxy": "bullish_low_sweep"}
    return {"feature_sweep_liquidity_proxy": "none"}


def volatility_features(hist: pd.DataFrame) -> dict[str, object]:
    if len(hist) < 25:
        return {
            "feature_atr20": "",
            "feature_atr_pct": "",
            "feature_volatility_regime": "unknown",
            "feature_range_60_pct": "",
        }
    atr = latest_atr(hist) or 0.0
    close = float(hist["close"].iloc[-1])
    atr_pct = atr / close if close else 0.0
    recent60 = hist.iloc[-60:] if len(hist) >= 60 else hist
    range_60_pct = (float(recent60["high"].max()) - float(recent60["low"].min())) / close if close else 0.0
    if atr_pct >= 0.008:
        regime = "extreme"
    elif atr_pct >= 0.004:
        regime = "expanded"
    elif atr_pct >= 0.0015:
        regime = "normal"
    else:
        regime = "compressed"
    return {
        "feature_atr20": round(atr, 8),
        "feature_atr_pct": round(atr_pct, 8),
        "feature_volatility_regime": regime,
        "feature_range_60_pct": round(range_60_pct, 8),
    }


def htf_features(hist: pd.DataFrame, side: str) -> dict[str, object]:
    if len(hist) < 60:
        return {
            "feature_htf_bias": "unknown",
            "feature_htf_bias_confidence": 0,
            "feature_range_location_1d": "",
        }
    close = float(hist["close"].iloc[-1])
    day_high = float(hist["high"].max())
    day_low = float(hist["low"].min())
    range_loc = (close - day_low) / (day_high - day_low) if day_high > day_low else None
    scores = {"long": 0, "short": 0}
    for rule, weight in [("15min", 4), ("1h", 6), ("4h", 8)]:
        tf = hist.resample(rule, label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        ).dropna()
        if len(tf) < 4:
            continue
        move = float(tf["close"].iloc[-1] - tf["close"].iloc[max(0, len(tf) - 4)])
        atr_tf = latest_atr(tf, period=10) or 0.0
        threshold = max(atr_tf * 0.35, close * 0.0008)
        if move > threshold:
            scores["long"] += weight
        elif move < -threshold:
            scores["short"] += weight
    if range_loc is not None:
        if range_loc <= 0.25:
            scores["long"] += 2
        elif range_loc >= 0.75:
            scores["short"] += 2
    diff = scores["long"] - scores["short"]
    if abs(diff) < 4:
        bias = "no_clear_intraday_bias"
    else:
        bias = "long" if diff > 0 else "short"
    aligned = "unknown"
    if side in {"long", "short"} and bias in {"long", "short"}:
        aligned = "true" if side == bias else "false"
    return {
        "feature_htf_bias": bias,
        "feature_htf_bias_confidence": min(100, abs(diff) * 8),
        "feature_htf_bias_aligned_with_candidate": aligned,
        "feature_range_location_1d": "" if range_loc is None else round(range_loc, 4),
    }


def fib_features(hist: pd.DataFrame, row: dict[str, str]) -> dict[str, object]:
    source_stated = row.get("elliott_wave_status") == "stated"
    if len(hist) < 60:
        auto = "unknown"
    else:
        recent = hist.iloc[-120:] if len(hist) >= 120 else hist
        high = float(recent["high"].max())
        low = float(recent["low"].min())
        close = float(recent["close"].iloc[-1])
        span = high - low
        if span <= 0:
            auto = "none"
        else:
            ratios = {
                "near_0_618_retrace": low + 0.618 * span,
                "near_1_618_extension": low + 1.618 * span,
                "near_2_618_extension": low + 2.618 * span,
            }
            nearest = min(ratios.items(), key=lambda item: abs(close - item[1]))
            auto = nearest[0] if abs(close - nearest[1]) / span <= 0.03 else "none"
    return {
        "source_label_elliott_wave_stated": "true" if source_stated else "false",
        "feature_elliott_fib_auto_low_conf": auto,
        "feature_elliott_fib_confidence": "source_supported" if source_stated else "low_auto_or_not_stated",
    }


def geometry_component_confidence(row: dict[str, str], component: str) -> str:
    entry = safe_float(row.get("entry_price_numeric"))
    stop = safe_float(row.get("stop_price_numeric"))
    target = safe_float(row.get("target_price_numeric"))
    geometry_mode = clean(row.get("geometry_mode"))
    has_number = {
        "entry": entry is not None,
        "invalidation": stop is not None,
        "cancel": entry is not None and stop is not None and target is not None,
    }[component]
    if geometry_mode == "numeric_exact" and has_number:
        return "numeric_exact"
    if geometry_mode == "numeric_partial" and has_number:
        return "numeric_partial"
    if geometry_mode == "frame_relative":
        return "frame_relative_policy_only"
    if geometry_mode == "prose_only":
        return "prose_only_hold_exact"
    return "unknown"


def entry_geometry_features(row: dict[str, str], hist: pd.DataFrame) -> dict[str, object]:
    entry = safe_float(row.get("entry_price_numeric"))
    stop = safe_float(row.get("stop_price_numeric"))
    target = safe_float(row.get("target_price_numeric"))
    geometry_mode = clean(row.get("geometry_mode"))
    close = float(hist["close"].iloc[-1]) if len(hist) else None
    atr = latest_atr(hist) if len(hist) else None

    out: dict[str, object] = {
        "feature_entry_numeric_available": "true" if entry is not None else "false",
        "feature_stop_numeric_available": "true" if stop is not None else "false",
        "feature_target_numeric_available": "true" if target is not None else "false",
        "feature_pretrade_rr": "",
        "feature_entry_distance_atr": "",
        "feature_no_chase_risk": "unknown_geometry_not_numeric",
        "feature_entry_zone_geometry_confidence": geometry_component_confidence(row, "entry"),
        "feature_invalidation_geometry_confidence": geometry_component_confidence(row, "invalidation"),
        "feature_cancel_condition_geometry_confidence": geometry_component_confidence(row, "cancel"),
        "feature_exact_fill_backtest_allowed": "true" if row.get("eligible_for_fill_backtest") == "true" else "false",
    }
    side = row.get("trade_side")
    if entry is not None and close is not None and atr and atr > 0:
        out["feature_entry_distance_atr"] = round(abs(close - entry) / atr, 4)
    if entry is not None and stop is not None and target is not None and side in {"long", "short"}:
        risk = abs(entry - stop)
        if risk > 0:
            rr = abs(target - entry) / risk
            out["feature_pretrade_rr"] = round(rr, 4)
            if close is not None and atr and atr > 0 and abs(close - entry) / atr > 2.5:
                out["feature_no_chase_risk"] = "high_far_from_entry"
            elif rr < 2.0:
                out["feature_no_chase_risk"] = "high_rr_compressed"
            else:
                out["feature_no_chase_risk"] = "not_flagged"
    elif row.get("geometry_mode") == "frame_relative":
        out["feature_no_chase_risk"] = "unknown_frame_relative"
    return out


def relative_strength_features(
    coverage: dict[tuple[str, str], Path],
    date_text: str,
    cutoff_utc: pd.Timestamp | None,
    primary_symbol: str,
) -> dict[str, object]:
    returns: dict[str, float | None] = {}
    for symbol in SUPPORTED_SYMBOLS:
        path = coverage.get((date_text, symbol))
        if not path:
            returns[symbol] = None
            continue
        hist = asof_history(load_ohlcv(str(path)), cutoff_utc)
        returns[symbol] = ret_close(hist, 20)
    ranked = sorted([(s, r) for s, r in returns.items() if r is not None], key=lambda item: item[1], reverse=True)
    rank_map = {symbol: i + 1 for i, (symbol, _) in enumerate(ranked)}
    primary_ret = returns.get(primary_symbol)
    btc_ret = returns.get("BTCUSDT")
    alignment = "unknown"
    if primary_ret is not None and btc_ret is not None and primary_symbol != "BTCUSDT":
        alignment = "aligned" if primary_ret * btc_ret > 0 else "against" if primary_ret * btc_ret < 0 else "neutral"
    state = "unknown"
    if primary_symbol in rank_map:
        if rank_map[primary_symbol] == 1:
            state = "relative_leader"
        elif rank_map[primary_symbol] == len(rank_map):
            state = "relative_laggard"
        else:
            state = "middle_of_pack"
    out: dict[str, object] = {
        "feature_primary_symbol_ret20": "" if primary_ret is None else round(primary_ret, 8),
        "feature_primary_symbol_relative_rank_ret20": rank_map.get(primary_symbol, ""),
        "feature_primary_symbol_relative_state": state,
        "feature_btc_leader_alignment": alignment,
    }
    for symbol in SUPPORTED_SYMBOLS:
        out[f"feature_ret20_{symbol}"] = "" if returns.get(symbol) is None else round(float(returns[symbol]), 8)
    return out


def setup_quality(row: dict[str, str], features: dict[str, object]) -> tuple[float, str]:
    score = 0.0
    trace: list[str] = []
    if features.get("feature_fvg_active_for_side") == "true":
        score += 2.5
        trace.append("active_fvg")
    if clean(features.get("feature_choch_type")) not in {"", "none", "unknown"}:
        score += 2.0
        trace.append(f"choch={features.get('feature_choch_type')}")
    disp = safe_float(features.get("feature_displacement_score"))
    if disp is not None:
        if disp >= 2.4:
            score += 2.0
            trace.append("strong_displacement")
        elif disp >= 1.4:
            score += 1.0
            trace.append("some_displacement")
    if features.get("feature_htf_bias_aligned_with_candidate") == "true":
        score += 1.5
        trace.append("htf_aligned")
    elif features.get("feature_htf_bias_aligned_with_candidate") == "false":
        score -= 1.0
        trace.append("htf_against")
    sr_distance = safe_float(features.get("feature_nearest_sr_distance_atr"))
    if sr_distance is not None and sr_distance <= 1.0:
        score += 1.0
        trace.append("near_sr_cluster")
    if clean(features.get("feature_sweep_liquidity_proxy")) not in {"", "none", "unknown"}:
        score += 1.0
        trace.append(f"sweep={features.get('feature_sweep_liquidity_proxy')}")
    if features.get("feature_primary_symbol_relative_state") == "relative_leader":
        score += 0.5
        trace.append("relative_leader")
    if row.get("source_label_elliott_wave_stated") == "true" or features.get("source_label_elliott_wave_stated") == "true":
        score += 0.5
        trace.append("source_elliott_stated")
    return round(max(0.0, score), 3), "|".join(trace) or "no_runtime_confluence"


def build_features(decision_units: Path, manifest: Path, output: Path) -> list[dict[str, object]]:
    rows = read_csv(decision_units)
    coverage = coverage_lookup(read_csv(manifest))
    out_rows: list[dict[str, object]] = []
    for row in rows:
        dt = parse_decision_time(row)
        primary_symbol = row.get("primary_symbol", "")
        ohlcv_path = coverage.get((dt.market_date, primary_symbol))
        hist = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        runtime_status = "ready"
        if not ohlcv_path:
            runtime_status = "missing_primary_symbol_ohlcv"
        else:
            hist = asof_history(load_ohlcv(str(ohlcv_path)), dt.cutoff_utc)
            if hist.empty:
                runtime_status = "no_completed_candles_before_cutoff"
        if dt.parse_confidence in {"none", "low_default_time"}:
            runtime_status = "time_anchor_low_confidence"

        side = row.get("trade_side", "")
        features: dict[str, object] = {}
        if not hist.empty:
            features.update(volatility_features(hist))
            features.update(htf_features(hist, side))
            features.update(fvg_features(hist, side))
            features.update(displacement_features(hist, side))
            features.update(sr_features(hist))
            features.update(trendline_features(hist))
            features.update(sweep_features(hist))
            features.update(fib_features(hist, row))
            features.update(entry_geometry_features(row, hist))
        else:
            features.update(
                {
                    "feature_atr20": "",
                    "feature_atr_pct": "",
                    "feature_volatility_regime": "unknown",
                    "feature_range_60_pct": "",
                    "feature_htf_bias": "unknown",
                    "feature_htf_bias_confidence": 0,
                    "feature_htf_bias_aligned_with_candidate": "unknown",
                    "feature_range_location_1d": "",
                    "feature_fvg_count_recent": 0,
                    "feature_fvg_side_count_recent": 0,
                    "feature_fvg_active_for_side": "false",
                    "feature_fvg_latest_freshness_for_side": "unknown",
                    "feature_fvg_active_mid_for_side": "",
                    "feature_displacement_score": "",
                    "feature_choch_type": "unknown",
                    "feature_bos_type": "unknown",
                    "feature_sr_cluster_count": 0,
                    "feature_nearest_sr_kind": "unknown",
                    "feature_nearest_sr_distance_atr": "",
                    "feature_trendline_proxy": "unknown",
                    "feature_trendline_proxy_confidence": "low_missing_data",
                    "feature_sweep_liquidity_proxy": "unknown",
                    "source_label_elliott_wave_stated": "true" if row.get("elliott_wave_status") == "stated" else "false",
                    "feature_elliott_fib_auto_low_conf": "unknown",
                    "feature_elliott_fib_confidence": "source_supported" if row.get("elliott_wave_status") == "stated" else "low_auto_or_not_stated",
                    "feature_entry_numeric_available": "true" if clean(row.get("entry_price_numeric")) else "false",
                    "feature_stop_numeric_available": "true" if clean(row.get("stop_price_numeric")) else "false",
                    "feature_target_numeric_available": "true" if clean(row.get("target_price_numeric")) else "false",
                    "feature_pretrade_rr": "",
                    "feature_entry_distance_atr": "",
                    "feature_no_chase_risk": "unknown_no_runtime_candles",
                    "feature_entry_zone_geometry_confidence": geometry_component_confidence(row, "entry"),
                    "feature_invalidation_geometry_confidence": geometry_component_confidence(row, "invalidation"),
                    "feature_cancel_condition_geometry_confidence": geometry_component_confidence(row, "cancel"),
                    "feature_exact_fill_backtest_allowed": "true" if row.get("eligible_for_fill_backtest") == "true" else "false",
                }
            )
        features.update(relative_strength_features(coverage, dt.market_date, dt.cutoff_utc, primary_symbol))
        quality, trace = setup_quality(row, features)

        result: dict[str, object] = {
            "context_id": row.get("context_id", ""),
            "session_context_id": row.get("session_context_id", ""),
            "video_id": row.get("video_id", ""),
            "source_stage_v03": row.get("source_stage_v03", ""),
            "label_decision_class": row.get("decision_class", ""),
            "label_decision_subtype": row.get("decision_subtype", ""),
            "label_fill_state": row.get("fill_state", ""),
            "label_trade_side": row.get("trade_side", ""),
            "label_outcome_class": row.get("outcome_class", ""),
            "label_result_r": row.get("result_r", ""),
            "label_result_usd": row.get("result_usd", ""),
            "label_eligible_for_policy_learning": row.get("eligible_for_policy_learning", ""),
            "label_eligible_for_fill_backtest": row.get("eligible_for_fill_backtest", ""),
            "label_eligible_for_management_replay": row.get("eligible_for_management_replay", ""),
            "label_hold_or_exclusion_reason": row.get("hold_or_exclusion_reason", ""),
            "runtime_primary_symbol": primary_symbol,
            "runtime_comparison_symbols": row.get("comparison_symbols", ""),
            "runtime_candidate_side_from_gold_row": side,
            "runtime_market_date": dt.market_date,
            "runtime_decision_time_ny": "" if dt.local_dt is None else dt.local_dt.isoformat(),
            "runtime_cutoff_utc": "" if dt.cutoff_utc is None else dt.cutoff_utc.isoformat(),
            "runtime_time_parse_mode": dt.parse_mode,
            "runtime_time_parse_confidence": dt.parse_confidence,
            "runtime_session_phase": dt.session_phase,
            "runtime_feature_status": runtime_status,
            "runtime_completed_candles": len(hist),
            "runtime_ohlcv_path": "" if not ohlcv_path else str(ohlcv_path),
            "runtime_news_calendar_join_status": "not_joined",
            "feature_high_impact_news_proximity": "unknown_external_not_joined",
            "feature_minutes_to_high_impact_news": "",
            "feature_news_directional_regime": "unknown_external_not_joined",
            "feature_setup_quality_score": quality,
            "feature_setup_quality_trace": trace,
            "source_setup_family_tags_for_audit": row.get("setup_family_tags", ""),
            "source_entry_model_for_audit": row.get("entry_model", ""),
            "source_invalidation_family_for_audit": row.get("invalidation_family", ""),
            "source_management_family_tags_for_audit": row.get("management_family_tags", ""),
            "source_special_condition_tags_for_audit": row.get("special_condition_tags", ""),
            "source_geometry_mode": row.get("geometry_mode", ""),
            "source_geometry_confidence": row.get("geometry_confidence", ""),
            "source_raw_decision_type": row.get("decision_type_raw", ""),
            "source_raw_direction": row.get("direction_raw", ""),
            "source_raw_symbol": row.get("symbol_raw", ""),
        }
        result.update(features)
        out_rows.append(result)
    write_csv(output, out_rows)
    return out_rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Craig v1 runtime feature matrix.")
    parser.add_argument("--decision-units", default=str(DECISION_UNITS))
    parser.add_argument("--ohlcv-manifest", default=str(COVERAGE_MANIFEST))
    parser.add_argument("--output", default=str(FEATURE_MATRIX))
    args = parser.parse_args()
    rows = build_features(Path(args.decision_units), Path(args.ohlcv_manifest), Path(args.output))
    print(f"wrote {args.output} rows={len(rows)}")


if __name__ == "__main__":
    main()
