#!/usr/bin/env python3
"""
Reference implementation scaffold for the Craig Percoco public-video emulator v0.2.

This is not a backtester and not a finished trading bot. It operationalizes the
spec enough to accept chart JSON, build an HTF map, detect simple FVG/CHoCH-like
1m candidates, score them, and emit the documented output schema.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo


NY = ZoneInfo("America/New_York")
DEFAULT_CANDIDATE_LIMIT = 200


def parse_time(value: str) -> datetime:
    value = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=NY)
    return dt


def as_candles(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    candles = []
    for row in rows or []:
        candles.append(
            {
                "timestamp": row["timestamp"],
                "dt": parse_time(row["timestamp"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": None if row.get("volume") is None else float(row["volume"]),
            }
        )
    candles.sort(key=lambda c: c["dt"])
    return candles


def true_ranges(candles: List[Dict[str, Any]]) -> List[float]:
    out = []
    prev_close = None
    for c in candles:
        if prev_close is None:
            tr = c["high"] - c["low"]
        else:
            tr = max(c["high"] - c["low"], abs(c["high"] - prev_close), abs(c["low"] - prev_close))
        out.append(max(tr, 0.0))
        prev_close = c["close"]
    return out


def atr(candles: List[Dict[str, Any]], period: int = 20) -> float:
    if not candles:
        return 0.0
    trs = true_ranges(candles)[-period:]
    return sum(trs) / max(1, len(trs))


def median_body(candles: List[Dict[str, Any]], end: int, lookback: int = 20) -> float:
    start = max(0, end - lookback)
    bodies = [abs(c["close"] - c["open"]) for c in candles[start:end]]
    if not bodies:
        return 0.0
    return statistics.median(bodies)


def session_phase(dt: datetime) -> str:
    local = dt.astimezone(NY)
    minutes = local.hour * 60 + local.minute
    if minutes < 8 * 60:
        return "pre_0800"
    if minutes < 9 * 60 + 30:
        return "ny_0800_0930"
    if minutes < 10 * 60 + 30:
        return "ny_open_0930_1030"
    if minutes < 12 * 60:
        return "ny_late_morning"
    if minutes < 16 * 60:
        return "ny_afternoon"
    return "post_session"


def is_active_session(dt: datetime) -> bool:
    phase = session_phase(dt)
    # Time is context, not a hard permission. Craig may still trade outside the
    # open when volatility returns, for example into Asia or a power-hour move.
    return phase != "post_session"


def news_risk_at(input_data: Dict[str, Any], dt: datetime) -> str:
    events = input_data.get("economic_calendar")
    if events is None:
        return "unknown"
    risk = "clear"
    for event in events:
        if event.get("impact") != "high":
            continue
        try:
            event_dt = parse_time(event["timestamp"])
        except Exception:
            continue
        delta = event_dt - dt
        if timedelta(minutes=-15) <= delta <= timedelta(minutes=5):
            return "blackout"
        if timedelta(minutes=-30) <= delta <= timedelta(minutes=30):
            risk = "warning"
    return risk


def fvg_freshness(direction: str, low: float, high: float, future: List[Dict[str, Any]]) -> str:
    mid = (low + high) / 2.0
    midpoint_touched = False
    for c in future:
        if direction == "bullish":
            if c["close"] < low:
                return "invalidated"
            if c["low"] <= low:
                return "fully_mitigated"
            if c["low"] <= mid:
                midpoint_touched = True
        else:
            if c["close"] > high:
                return "invalidated"
            if c["high"] >= high:
                return "fully_mitigated"
            if c["high"] >= mid:
                midpoint_touched = True
    return "midpoint_touched" if midpoint_touched else "untouched"


def find_fvgs(candles: List[Dict[str, Any]], timeframe: str, limit: int = 40) -> List[Dict[str, Any]]:
    zones = []
    for i in range(2, len(candles)):
        c1, c3 = candles[i - 2], candles[i]
        if c1["high"] < c3["low"]:
            low, high = c1["high"], c3["low"]
            freshness = fvg_freshness("bullish", low, high, candles[i + 1 :])
            if freshness != "invalidated":
                zones.append(make_zone(timeframe, "bullish_fvg", low, high, candles[i]["timestamp"], freshness))
        if c1["low"] > c3["high"]:
            low, high = c3["high"], c1["low"]
            freshness = fvg_freshness("bearish", low, high, candles[i + 1 :])
            if freshness != "invalidated":
                zones.append(make_zone(timeframe, "bearish_fvg", low, high, candles[i]["timestamp"], freshness))
    return zones[-limit:]


def make_zone(timeframe: str, zone_type: str, low: float, high: float, timestamp: str, freshness: str) -> Dict[str, Any]:
    mid = (low + high) / 2.0
    quality = 5 if freshness == "untouched" else 4 if freshness == "midpoint_touched" else 2
    return {
        "zone_id": f"{timeframe}_{zone_type}_{timestamp}",
        "timeframe": timeframe,
        "type": zone_type,
        "low": low,
        "high": high,
        "mid": mid,
        "freshness": freshness,
        "quality": quality,
    }


def previous_day_levels(daily: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if len(daily) < 2:
        return []
    prev = daily[-2]
    return [
        make_zone("1d", "pdh", prev["high"], prev["high"], prev["timestamp"], "active"),
        make_zone("1d", "pdl", prev["low"], prev["low"], prev["timestamp"], "active"),
    ]


def swing_points(candles: List[Dict[str, Any]], lookback: int = 3) -> List[Dict[str, Any]]:
    points: List[Dict[str, Any]] = []
    if len(candles) < lookback * 2 + 1:
        return points
    for i in range(lookback, len(candles) - lookback):
        window = candles[i - lookback : i + lookback + 1]
        high = candles[i]["high"]
        low = candles[i]["low"]
        if high == max(c["high"] for c in window):
            points.append({"index": i, "type": "high", "price": high, "timestamp": candles[i]["timestamp"]})
        if low == min(c["low"] for c in window):
            points.append({"index": i, "type": "low", "price": low, "timestamp": candles[i]["timestamp"]})
    return points


def sr_flip_zones(candles: List[Dict[str, Any]], timeframe: str, limit: int = 12) -> List[Dict[str, Any]]:
    """Approximate Craig's manually boxed SR/flip areas from repeated HTF pivots."""
    if len(candles) < 20:
        return []
    recent = candles[-180:]
    atr_base = atr(recent, 20)
    if atr_base <= 0:
        return []
    tolerance = max(atr_base * 0.35, recent[-1]["close"] * 0.001)
    pivots = swing_points(recent, lookback=3)
    clusters: List[Dict[str, Any]] = []
    for pivot in pivots:
        price = float(pivot["price"])
        match = None
        for cluster in clusters:
            if abs(cluster["level"] - price) <= tolerance:
                match = cluster
                break
        if match is None:
            match = {"level": price, "prices": [], "highs": 0, "lows": 0, "last_timestamp": pivot["timestamp"]}
            clusters.append(match)
        match["prices"].append(price)
        match["level"] = sum(match["prices"]) / len(match["prices"])
        match["highs"] += 1 if pivot["type"] == "high" else 0
        match["lows"] += 1 if pivot["type"] == "low" else 0
        match["last_timestamp"] = pivot["timestamp"]

    close = recent[-1]["close"]
    zones: List[Dict[str, Any]] = []
    for cluster in clusters:
        touches = int(cluster["highs"]) + int(cluster["lows"])
        if touches < 2:
            continue
        level = float(cluster["level"])
        low = level - tolerance
        high = level + tolerance
        if cluster["highs"] >= 2 and close > level + tolerance:
            zone_type = "sr_flip_support"
        elif cluster["lows"] >= 2 and close < level - tolerance:
            zone_type = "sr_flip_resistance"
        elif cluster["lows"] >= cluster["highs"] and close >= level:
            zone_type = "support"
        elif cluster["highs"] > cluster["lows"] and close <= level:
            zone_type = "resistance"
        else:
            zone_type = "repeated_sr"
        zones.append(
            make_zone(
                timeframe,
                zone_type,
                low,
                high,
                str(cluster["last_timestamp"]),
                "active",
            )
            | {"quality": min(5, 2 + touches)}
        )
    zones.sort(key=lambda z: (z["quality"], -abs(z["mid"] - close)), reverse=True)
    return zones[:limit]


def trendline_zones(candles: List[Dict[str, Any]], timeframe: str, limit: int = 8) -> List[Dict[str, Any]]:
    """Generate near-current HTF trendline reaction zones from repeated swing points."""
    if len(candles) < 30:
        return []
    recent = candles[-220:]
    atr_base = atr(recent, 20)
    if atr_base <= 0:
        return []
    tolerance = max(atr_base * 0.45, recent[-1]["close"] * 0.0015)
    pivots = swing_points(recent, lookback=3)
    close = recent[-1]["close"]
    zones: List[Dict[str, Any]] = []
    for pivot_type, zone_type, slope_ok in [
        ("low", "support_trendline", lambda slope: slope > 0),
        ("high", "resistance_trendline", lambda slope: slope < 0),
    ]:
        typed = [p for p in pivots if p["type"] == pivot_type][-10:]
        for a in range(len(typed)):
            for b in range(a + 1, len(typed)):
                p1, p2 = typed[a], typed[b]
                if p2["index"] == p1["index"]:
                    continue
                slope = (float(p2["price"]) - float(p1["price"])) / (int(p2["index"]) - int(p1["index"]))
                if not slope_ok(slope):
                    continue
                projection = float(p1["price"]) + slope * (len(recent) - 1 - int(p1["index"]))
                if abs(close - projection) > max(3.0 * atr_base, close * 0.018):
                    continue
                touches = 0
                for point in typed:
                    expected = float(p1["price"]) + slope * (int(point["index"]) - int(p1["index"]))
                    if abs(float(point["price"]) - expected) <= tolerance:
                        touches += 1
                if touches < 2:
                    continue
                zones.append(
                    make_zone(
                        timeframe,
                        zone_type,
                        projection - tolerance,
                        projection + tolerance,
                        str(p2["timestamp"]),
                        "active",
                    )
                    | {"quality": min(5, 2 + touches)}
                )
    zones.sort(key=lambda z: (z["quality"], -abs(z["mid"] - close)), reverse=True)
    return zones[:limit]


def trend_score(candles: List[Dict[str, Any]]) -> int:
    if len(candles) < 10:
        return 0
    close_now = candles[-1]["close"]
    close_then = candles[-10]["close"]
    move = close_now - close_then
    threshold = atr(candles[-30:], 20) * 0.5
    if move > threshold:
        return 1
    if move < -threshold:
        return -1
    return 0


def range_location(candles: List[Dict[str, Any]], lookback: int = 96) -> Optional[float]:
    recent = candles[-lookback:]
    if not recent:
        return None
    high = max(c["high"] for c in recent)
    low = min(c["low"] for c in recent)
    if high == low:
        return None
    return (recent[-1]["close"] - low) / (high - low)


def leader_alignment(input_data: Dict[str, Any], instrument_move: float) -> str:
    leaders = input_data.get("leader_assets") or []
    if not leaders:
        return "unknown"
    first = leaders[0]
    series = as_candles((first.get("timeframes") or {}).get("15m") or [])
    if len(series) < 5:
        return "unknown"
    leader_move = series[-1]["close"] - series[max(0, len(series) - 20)]["close"]
    if abs(leader_move) == 0 or abs(instrument_move) == 0:
        return "neutral"
    return "aligned" if leader_move * instrument_move > 0 else "against"


def build_htf_map(input_data: Dict[str, Any], tf: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    zones: List[Dict[str, Any]] = []
    zones.extend(previous_day_levels(tf.get("1d", [])))
    zones.extend(find_fvgs(tf.get("4h", []), "4h", limit=8))
    zones.extend(find_fvgs(tf.get("1h", []), "1h", limit=15))
    zones.extend(find_fvgs(tf.get("15m", []), "15m", limit=25))
    for timeframe in ["4h", "1h", "15m"]:
        zones.extend(sr_flip_zones(tf.get(timeframe, []), timeframe))
        zones.extend(trendline_zones(tf.get(timeframe, []), timeframe))

    fifteen = tf.get("15m", [])
    loc = range_location(fifteen)
    instrument_move = 0.0
    if len(fifteen) >= 20:
        instrument_move = fifteen[-1]["close"] - fifteen[-20]["close"]
    alignment = leader_alignment(input_data, instrument_move)

    long_score = 0
    short_score = 0
    for key, weight in [("1d", 8), ("4h", 6), ("1h", 5), ("15m", 4)]:
        s = trend_score(tf.get(key, []))
        if s > 0:
            long_score += weight
        elif s < 0:
            short_score += weight
    if loc is not None:
        if loc <= 0.25:
            long_score += 4
            short_score -= 3
        elif loc >= 0.75:
            short_score += 4
            long_score -= 3
    if alignment == "aligned":
        if instrument_move >= 0:
            long_score += 3
        else:
            short_score += 3

    diff = long_score - short_score
    if abs(diff) >= 8:
        bias = "long" if diff > 0 else "short"
    else:
        bias = "no_bias"
    confidence = min(100, abs(diff) * 8)

    last_close = fifteen[-1]["close"] if fifteen else None
    draws = liquidity_draws(zones, last_close)
    return {
        "bias": bias,
        "bias_confidence": confidence,
        "long_score": long_score,
        "short_score": short_score,
        "range_location": loc,
        "key_zones": zones,
        "liquidity_draws": draws,
        "invalidation_notes": [],
        "_leader_alignment": alignment,
    }


def liquidity_draws(zones: List[Dict[str, Any]], price: Optional[float]) -> List[Dict[str, Any]]:
    if price is None:
        return []
    out = []
    for z in zones:
        level = z.get("mid") if z.get("mid") is not None else z["high"]
        direction = "up" if level > price else "down"
        out.append({"type": z["type"], "price": level, "direction": direction, "quality": z.get("quality", 3)})
    out.sort(key=lambda d: abs(d["price"] - price))
    return out[:8]


def displacement_score(candles: List[Dict[str, Any]], i: int, direction: str) -> float:
    c = candles[i]
    body_base = median_body(candles, i, 20)
    atr_base = atr(candles[max(0, i - 20) : i + 1], 20)
    if body_base == 0 or atr_base == 0 or c["high"] == c["low"]:
        return 0.0
    body_score = abs(c["close"] - c["open"]) / body_base
    range_score = (c["high"] - c["low"]) / atr_base
    if direction == "long":
        close_score = (c["close"] - c["low"]) / (c["high"] - c["low"])
    else:
        close_score = (c["high"] - c["close"]) / (c["high"] - c["low"])
    raw = 0.45 * body_score + 0.35 * range_score + 0.20 * (2 * close_score)
    return min(raw, 5.0)


def near_zones(price: float, zones: List[Dict[str, Any]], threshold: float) -> List[Dict[str, Any]]:
    nearby = []
    for z in zones:
        low, high = min(z["low"], z["high"]), max(z["low"], z["high"])
        distance = 0.0 if low <= price <= high else min(abs(price - low), abs(price - high))
        if distance <= threshold:
            nearby.append(z)
    return nearby


def nearby_zone_alignment(nearby: List[Dict[str, Any]], direction: str) -> Tuple[int, int]:
    long_zones = {
        "bullish_fvg",
        "pdl",
        "support",
        "range_low",
        "sr_flip_support",
        "support_trendline",
    }
    short_zones = {
        "bearish_fvg",
        "pdh",
        "resistance",
        "range_high",
        "sr_flip_resistance",
        "resistance_trendline",
    }
    aligned = 0
    against = 0
    for zone in nearby:
        zone_type = zone.get("type")
        if zone_type in long_zones:
            if direction == "long":
                aligned += 1
            else:
                against += 1
        elif zone_type in short_zones:
            if direction == "short":
                aligned += 1
            else:
                against += 1
    return aligned, against


def simple_choch(candles: List[Dict[str, Any]], i: int, direction: str, lookback: int = 12) -> bool:
    if i < lookback + 2:
        return False
    previous = candles[i - lookback : i - 2]
    c = candles[i]
    if direction == "long":
        return c["close"] > max(x["high"] for x in previous)
    return c["close"] < min(x["low"] for x in previous)


def effective_choch(candles: List[Dict[str, Any]], i: int, direction: str, disp: float) -> Tuple[bool, str]:
    if simple_choch(candles, i, direction, lookback=12):
        return True, "strict_12"
    if simple_choch(candles, i, direction, lookback=5):
        return True, "micro_5"
    if disp >= 2.4 and simple_choch(candles, i, direction, lookback=3):
        return True, "impulse_micro_3"
    return False, "none"


def fvg_displacement_score(candles: List[Dict[str, Any]], i: int, direction: str) -> float:
    if i <= 0:
        return displacement_score(candles, i, direction)
    return max(displacement_score(candles, i - 1, direction), displacement_score(candles, i, direction))


def timeframe_minutes(timeframe: str) -> Optional[int]:
    mapping = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
    return mapping.get(timeframe)


def completed_candles(candles: List[Dict[str, Any]], timeframe: str, cutoff: Optional[datetime]) -> List[Dict[str, Any]]:
    if cutoff is None:
        return candles
    minutes = timeframe_minutes(timeframe)
    if minutes is None:
        return [c for c in candles if c["dt"] <= cutoff]
    return [c for c in candles if c["dt"] + timedelta(minutes=minutes) <= cutoff]


def htf_body_shelf_objectives(
    direction: str,
    entry: float,
    stop: float,
    tf: Optional[Dict[str, List[Dict[str, Any]]]],
    cutoff: Optional[datetime],
) -> List[Dict[str, Any]]:
    risk = abs(entry - stop)
    if not tf or risk == 0:
        return []
    objectives: List[Dict[str, Any]] = []
    priority = {"15m": 0, "1h": 1, "5m": 2}
    max_bars = {"15m": 12, "1h": 8, "5m": 24}
    for timeframe in ["15m", "1h", "5m"]:
        candles = completed_candles(tf.get(timeframe, []), timeframe, cutoff)
        if len(candles) < 4:
            continue
        recent = candles[-max_bars[timeframe] :]
        body_floor = max(median_body(candles, len(candles), 30) * 1.2, atr(candles[-30:], 20) * 0.25)
        for c in reversed(recent):
            body = abs(c["close"] - c["open"])
            if body < body_floor:
                continue
            if direction == "long" and c["open"] > c["close"]:
                level = c["open"]
            elif direction == "short" and c["open"] < c["close"]:
                level = c["open"]
            else:
                continue
            if direction == "long" and level <= entry:
                continue
            if direction == "short" and level >= entry:
                continue
            rr = abs(level - entry) / risk
            if rr < 3.5:
                continue
            objectives.append(
                {
                    "type": f"{timeframe}_adverse_displacement_open_retest",
                    "price": level,
                    "rr": rr,
                    "_sort": (priority[timeframe], -c["dt"].timestamp(), abs(level - entry)),
                }
            )
    objectives.sort(key=lambda item: item["_sort"])
    return objectives


def candidate_target(
    direction: str,
    entry: float,
    stop: float,
    draws: List[Dict[str, Any]],
    tf: Optional[Dict[str, List[Dict[str, Any]]]] = None,
    cutoff: Optional[datetime] = None,
    allow_body_shelf: bool = False,
) -> Tuple[float, str, float]:
    risk = abs(entry - stop)
    if risk == 0:
        return entry, "invalid", 0.0
    directional = [
        d
        for d in draws
        if (direction == "long" and float(d["price"]) > entry)
        or (direction == "short" and float(d["price"]) < entry)
    ]
    if directional:
        nearest = directional[0]
        target = nearest["price"]
        rr = abs(target - entry) / risk
        if rr >= 3.5:
            return target, nearest["type"], rr
    if allow_body_shelf:
        body_shelves = htf_body_shelf_objectives(direction, entry, stop, tf, cutoff)
        if body_shelves:
            target = body_shelves[0]["price"]
            return target, body_shelves[0]["type"], body_shelves[0]["rr"]
    for draw in directional[1:]:
        target = draw["price"]
        rr = abs(target - entry) / risk
        if rr >= 3.5:
            return target, draw["type"], rr
    synthetic = entry + 4 * risk if direction == "long" else entry - 4 * risk
    return synthetic, "4R_synthetic_until_real_htf_target_labeled", 4.0


def structure_stop(
    candles: List[Dict[str, Any]],
    i: int,
    direction: str,
    buffer: float,
    external_level: Optional[float] = None,
) -> Tuple[float, str]:
    setup = candles[max(0, i - 2) : i + 1]
    if not setup:
        return candles[i]["close"], "fallback_current_close"
    recent_atr = atr(candles[max(0, i - 20) : i + 1], 20)
    if direction == "long":
        base = min(x["low"] for x in setup)
        if external_level is not None and external_level < base and base - external_level <= 2.0 * recent_atr:
            base = external_level
            return base - buffer, "external_sweep_or_failed_low"
        return base - buffer, "local_fvg_origin_low"
    base = max(x["high"] for x in setup)
    if external_level is not None and external_level > base and external_level - base <= 2.0 * recent_atr:
        base = external_level
        return base + buffer, "external_sweep_or_failed_high"
    return base + buffer, "local_fvg_origin_high"


def response_area_retest_entry(direction: str, fvg_mid: float, stop: float, buffer: float) -> float:
    origin = stop + buffer if direction == "long" else stop - buffer
    if direction == "long":
        return origin + 0.25 * (fvg_mid - origin)
    return origin - 0.25 * (origin - fvg_mid)


def breakdown_market_fill_entry(candle: Dict[str, Any], direction: str) -> float:
    if direction == "short":
        return candle["low"] + 0.25 * max(0.0, candle["close"] - candle["low"])
    return candle["high"] - 0.25 * max(0.0, candle["high"] - candle["close"])


def volatility_market_stop(entry: float, direction: str, recent_atr: float, multiplier: float = 0.75) -> float:
    distance = max(recent_atr * multiplier, 1e-9)
    if direction == "short":
        return entry + distance
    return entry - distance


def is_fast_breakaway_from_midpoint(direction: str, mid: float, candle: Dict[str, Any], recent_atr: float) -> bool:
    if recent_atr <= 0:
        return False
    if direction == "short":
        return mid - candle["close"] >= 0.75 * recent_atr
    return candle["close"] - mid >= 0.75 * recent_atr


def score_candidate(
    direction: str,
    phase: str,
    news_risk: str,
    htf: Dict[str, Any],
    nearby: List[Dict[str, Any]],
    sweep: bool,
    choch: bool,
    disp: float,
    fvg_quality: int,
    rr: float,
    hard_pass: List[str],
) -> Tuple[float, float, str]:
    if hard_pass:
        return 0.0, 0.0, "pass"
    score = 0.0
    score += 5 if phase == "ny_open_0930_1030" else 3 if phase in {"ny_0800_0930", "ny_late_morning"} else 1
    score += 4 if news_risk == "clear" else 2 if news_risk == "unknown" else 1
    score += 3
    score += 3 if htf.get("_leader_alignment") == "aligned" else 1 if htf.get("_leader_alignment") == "unknown" else -4
    htf_bias = htf.get("bias")
    bias_points = min(8, htf.get("bias_confidence", 0) / 12)
    if htf_bias == direction:
        score += bias_points
    elif htf_bias in {"long", "short"}:
        score -= bias_points
    aligned_zones, against_zones = nearby_zone_alignment(nearby, direction)
    if aligned_zones:
        score += min(5, 2 + aligned_zones * 1.5)
    elif against_zones:
        score -= min(6, 2 + against_zones * 2)
    score += min(7, max((z.get("quality", 0) for z in nearby), default=0) + 2)
    loc = htf.get("range_location")
    if loc is not None:
        if direction == "long" and loc <= 0.35:
            score += 4
        elif direction == "short" and loc >= 0.65:
            score += 4
        else:
            score += 2
    score += 5 if htf.get("liquidity_draws") else 0
    score += 3 if any(z.get("freshness") in {"untouched", "midpoint_touched", "active"} for z in nearby) else 1
    score += 5 if sweep else 2
    score += 8 if choch else 0
    score += min(8, disp * 3.0)
    score += fvg_quality
    score += 5  # midpoint is inherent in the detected FVG candidate.
    score += 7
    score += min(7, rr)
    score += 4
    score += 2
    score += 5
    likelihood = 100.0 / (1.0 + math.exp(-((score - 68.0) / 8.0)))
    if phase == "ny_open_0930_1030":
        likelihood += 8
    if htf.get("bias") == "no_bias":
        likelihood -= 10
    if news_risk == "warning":
        likelihood -= 8
    likelihood = max(0.0, min(100.0, likelihood))
    action = "take" if score >= 70 and likelihood >= 65 else "wait" if score >= 55 else "pass"
    return round(score, 2), round(likelihood, 2), action


def sweep_signal(candles: List[Dict[str, Any]], i: int, direction: str, lookback: int = 12) -> Tuple[bool, Optional[float]]:
    if i < lookback + 1:
        return False, None
    prior = candles[i - lookback : i]
    c = candles[i]
    if direction == "long":
        level = min(x["low"] for x in prior)
        return c["low"] < level and c["close"] > level, level
    level = max(x["high"] for x in prior)
    return c["high"] > level and c["close"] < level, level


def failed_continuation_signal(
    candles: List[Dict[str, Any]], i: int, direction: str, lookback: int = 12
) -> Tuple[bool, Optional[float]]:
    if i < lookback + 1:
        return False, None
    prior = candles[i - lookback : i]
    c = candles[i]
    if direction == "long":
        recent_low = min(x["low"] for x in prior)
        failed = c["low"] <= recent_low + 0.15 * atr(prior, min(20, len(prior))) and c["close"] > c["open"]
        return failed, recent_low
    recent_high = max(x["high"] for x in prior)
    failed = c["high"] >= recent_high - 0.15 * atr(prior, min(20, len(prior))) and c["close"] < c["open"]
    return failed, recent_high


def recent_news_risk(input_data: Dict[str, Any], candles: List[Dict[str, Any]]) -> str:
    if not candles:
        return "unknown" if input_data.get("economic_calendar") is None else "clear"
    return news_risk_at(input_data, candles[-1]["dt"])


def scan_candidates(input_data: Dict[str, Any], tf: Dict[str, List[Dict[str, Any]]], htf: Dict[str, Any]) -> List[Dict[str, Any]]:
    one = tf.get("1m", [])
    fifteen_atr = atr(tf.get("15m", []), 20)
    threshold = max(fifteen_atr, atr(one, 20) * 4, 1e-9)
    session_tz = ZoneInfo(input_data.get("session_timezone") or "America/New_York")
    out = []
    for i in range(22, len(one)):
        c1, c3 = one[i - 2], one[i]
        phase = session_phase(c3["dt"])
        direction = None
        fvg_low = fvg_high = None
        if c1["high"] < c3["low"]:
            direction = "long"
            fvg_low, fvg_high = c1["high"], c3["low"]
        elif c1["low"] > c3["high"]:
            direction = "short"
            fvg_low, fvg_high = c3["high"], c1["low"]
        if direction is None:
            continue
        mid = (fvg_low + fvg_high) / 2.0
        nearby = near_zones(mid, htf["key_zones"], threshold)
        if not nearby:
            continue
        aligned_zones, against_zones = nearby_zone_alignment(nearby, direction)
        sweep, sweep_level = sweep_signal(one, max(0, i - 1), direction)
        failed_continuation, failed_level = failed_continuation_signal(one, max(0, i - 1), direction)
        sweep_or_fail = sweep or failed_continuation
        recent_atr = atr(one[max(0, i - 20) : i + 1], 20)
        disp = fvg_displacement_score(one, i, direction)
        choch, choch_type = effective_choch(one, i, direction, disp)
        buffer = max(0.05 * recent_atr, 1e-9)
        stop, stop_model = structure_stop(
            one,
            i,
            direction,
            buffer,
            sweep_level if sweep else failed_level if failed_continuation else None,
        )
        target, target_type, rr = candidate_target(
            direction,
            mid,
            stop,
            htf.get("liquidity_draws", []),
            tf=tf,
            cutoff=c3["dt"],
        )
        news_risk = news_risk_at(input_data, c3["dt"])
        hard = []
        if news_risk == "blackout":
            hard.append("news_blackout")
        if not is_active_session(c3["dt"]) and disp < 2.0:
            hard.append("quiet_off_session")
        if disp < 1.4:
            hard.append("weak_displacement")
        if not choch:
            hard.append("choch_not_confirmed")
        if rr < 3.5:
            hard.append("rr_below_minimum")
        if htf.get("bias") == "no_bias" and disp < 1.8:
            hard.append("bias_forcing")
        fvg_quality = 5 if disp >= 1.8 else 3 if disp >= 1.4 else 1
        setup_score, likelihood, action = score_candidate(
            direction, phase, news_risk, htf, nearby, sweep_or_fail, choch, disp, fvg_quality, rr, hard
        )
        entry_model = "fvg_midpoint"
        out.append(
            {
                "candidate_id": f"c_{len(out)+1}_{c3['timestamp']}",
                "timestamp": c3["timestamp"],
                "timestamp_local": c3["dt"].astimezone(session_tz).isoformat(),
                "session_phase": phase,
                "direction": direction,
                "trigger_summary": (
                    f"{phase} {direction} FVG midpoint near HTF zone; "
                    f"sweep_or_fail={sweep_or_fail}; choch={choch}; choch_type={choch_type}; "
                    f"displacement={disp:.2f}; news={news_risk}"
                ),
                "near_zone_ids": [z["zone_id"] for z in nearby[:4]],
                "near_zone_types": [z["type"] for z in nearby[:4]],
                "near_zone_alignment": {
                    "aligned_count": aligned_zones,
                    "against_count": against_zones,
                },
                "sweep_valid": sweep_or_fail,
                "sweep_level": sweep_level if sweep else failed_level if failed_continuation else None,
                "choch_valid": choch,
                "choch_type": choch_type,
                "displacement_score": round(disp, 2),
                "fvg": {
                    "direction": "bullish" if direction == "long" else "bearish",
                    "low": fvg_low,
                    "high": fvg_high,
                    "mid": mid,
                    "quality": fvg_quality,
                    "freshness": "new",
                },
                "entry": mid,
                "entry_model": entry_model,
                "stop": stop,
                "stop_model": stop_model,
                "targets": [{"price": target, "type": target_type, "rr": round(rr, 2)}],
                "rr_to_first_target": round(rr, 2),
                "hard_pass_flags": hard,
                "setup_score": setup_score,
                "craig_likelihood": likelihood,
                "action": action,
                "pass_reason": hard[0] if hard else None,
                "needs_human_review": bool(hard) or htf.get("bias") == "no_bias",
            }
        )
        if (
            choch
            and disp >= 1.8
            and abs(fvg_high - fvg_low) <= 0.35 * recent_atr
            and is_fast_breakaway_from_midpoint(direction, mid, c3, recent_atr)
            and news_risk != "blackout"
        ):
            market_entry = breakdown_market_fill_entry(c3, direction)
            market_stop = volatility_market_stop(market_entry, direction, recent_atr)
            market_target, market_target_type, market_rr = candidate_target(
                direction,
                market_entry,
                market_stop,
                htf.get("liquidity_draws", []),
                tf=tf,
                cutoff=c3["dt"],
            )
            market_hard = []
            if market_rr < 3.5:
                market_hard.append("rr_below_minimum")
            if htf.get("bias") == "no_bias" and disp < 2.0:
                market_hard.append("bias_forcing")
            market_score, market_likelihood, market_action = score_candidate(
                direction,
                phase,
                news_risk,
                htf,
                nearby,
                sweep_or_fail,
                choch,
                disp,
                fvg_quality,
                market_rr,
                market_hard,
            )
            if not market_hard:
                market_score = min(100.0, market_score + 2.0)
                market_likelihood = min(100.0, market_likelihood + 2.0)
                market_action = "take" if market_score >= 70 and market_likelihood >= 65 else market_action
            out.append(
                {
                    "candidate_id": f"c_{len(out)+1}_{c3['timestamp']}",
                    "timestamp": c3["timestamp"],
                    "timestamp_local": c3["dt"].astimezone(session_tz).isoformat(),
                    "session_phase": phase,
                    "direction": direction,
                    "trigger_summary": (
                        f"{phase} {direction} fast breakdown/market-fill after CHoCH; "
                        f"midpoint_chase=True; choch={choch}; choch_type={choch_type}; "
                        f"displacement={disp:.2f}; news={news_risk}"
                    ),
                    "near_zone_ids": [z["zone_id"] for z in nearby[:4]],
                    "near_zone_types": [z["type"] for z in nearby[:4]],
                    "near_zone_alignment": {
                        "aligned_count": aligned_zones,
                        "against_count": against_zones,
                    },
                    "sweep_valid": sweep_or_fail,
                    "sweep_level": sweep_level if sweep else failed_level if failed_continuation else None,
                    "choch_valid": choch,
                    "choch_type": choch_type,
                    "displacement_score": round(disp, 2),
                    "fvg": {
                        "direction": "bullish" if direction == "long" else "bearish",
                        "low": fvg_low,
                        "high": fvg_high,
                        "mid": mid,
                        "quality": fvg_quality,
                        "freshness": "fast_breakaway_market_fill",
                    },
                    "entry": market_entry,
                    "entry_model": "breakdown_market_fill_quarter_extreme",
                    "stop": market_stop,
                    "stop_model": "volatility_market_stop_0_75atr",
                    "targets": [
                        {"price": market_target, "type": market_target_type, "rr": round(market_rr, 2)}
                    ],
                    "rr_to_first_target": round(market_rr, 2),
                    "hard_pass_flags": market_hard,
                    "setup_score": round(market_score, 2),
                    "craig_likelihood": round(market_likelihood, 2),
                    "action": market_action,
                    "pass_reason": market_hard[0] if market_hard else None,
                    "needs_human_review": bool(market_hard) or htf.get("bias") == "no_bias",
                }
            )
        if not hard and choch and sweep_or_fail and disp >= 1.8:
            retest_entry = response_area_retest_entry(direction, mid, stop, buffer)
            for retest in one[i + 1 : min(len(one), i + 9)]:
                filled = retest["low"] <= retest_entry <= retest["high"]
                held = retest["close"] > stop + buffer if direction == "long" else retest["close"] < stop - buffer
                if not (filled and held):
                    continue
                retest_target, retest_target_type, retest_rr = candidate_target(
                    direction,
                    retest_entry,
                    stop,
                    htf.get("liquidity_draws", []),
                    tf=tf,
                    cutoff=retest["dt"],
                    allow_body_shelf=True,
                )
                if retest_rr < 3.5:
                    break
                retest_score, retest_likelihood, retest_action = score_candidate(
                    direction,
                    session_phase(retest["dt"]),
                    news_risk_at(input_data, retest["dt"]),
                    htf,
                    nearby,
                    True,
                    choch,
                    disp,
                    fvg_quality,
                    retest_rr,
                    [],
                )
                retest_score = min(100.0, retest_score + 4.0)
                retest_likelihood = min(100.0, retest_likelihood + 4.0)
                retest_action = "take" if retest_score >= 70 and retest_likelihood >= 65 else retest_action
                out.append(
                    {
                        "candidate_id": f"c_{len(out)+1}_{retest['timestamp']}",
                        "timestamp": retest["timestamp"],
                        "timestamp_local": retest["dt"].astimezone(session_tz).isoformat(),
                        "session_phase": session_phase(retest["dt"]),
                        "direction": direction,
                        "trigger_summary": (
                            f"{session_phase(retest['dt'])} {direction} response-area retest after FVG/CHoCH; "
                            f"origin_retest=True; choch={choch}; choch_type={choch_type}; "
                            f"displacement={disp:.2f}; news={news_risk_at(input_data, retest['dt'])}"
                        ),
                        "near_zone_ids": [z["zone_id"] for z in nearby[:4]],
                        "near_zone_types": [z["type"] for z in nearby[:4]],
                        "near_zone_alignment": {
                            "aligned_count": aligned_zones,
                            "against_count": against_zones,
                        },
                        "sweep_valid": True,
                        "sweep_level": stop + buffer if direction == "long" else stop - buffer,
                        "choch_valid": choch,
                        "choch_type": choch_type,
                        "displacement_score": round(disp, 2),
                        "fvg": {
                            "direction": "bullish" if direction == "long" else "bearish",
                            "low": fvg_low,
                            "high": fvg_high,
                            "mid": mid,
                            "quality": fvg_quality,
                            "freshness": "response_area_retest",
                        },
                        "entry": retest_entry,
                        "entry_model": "response_area_retest_quarter_origin",
                        "stop": stop,
                        "stop_model": stop_model,
                        "targets": [
                            {"price": retest_target, "type": retest_target_type, "rr": round(retest_rr, 2)}
                        ],
                        "rr_to_first_target": round(retest_rr, 2),
                        "hard_pass_flags": [],
                        "setup_score": round(retest_score, 2),
                        "craig_likelihood": round(retest_likelihood, 2),
                        "action": retest_action,
                        "pass_reason": None,
                        "needs_human_review": htf.get("bias") == "no_bias",
                    }
                )
                break
    out.sort(key=lambda x: (x["craig_likelihood"], x["setup_score"]), reverse=True)
    limit = int(input_data.get("candidate_limit") or DEFAULT_CANDIDATE_LIMIT)
    return out[:limit]


def market_context(input_data: Dict[str, Any], tf: Dict[str, List[Dict[str, Any]]], htf: Dict[str, Any]) -> Dict[str, Any]:
    one = tf.get("1m", [])
    dt = one[-1]["dt"] if one else datetime.now(tz=NY)
    return {
        "session_phase": session_phase(dt),
        "news_risk": news_risk_at(input_data, dt),
        "leader_asset_read": f"leader_alignment={htf.get('_leader_alignment', 'unknown')}",
        "leader_alignment": htf.get("_leader_alignment", "unknown"),
        "volatility_state": "healthy" if atr(one, 20) > 0 else "unknown",
    }


def watch_plan(htf: Dict[str, Any]) -> List[Dict[str, str]]:
    zones = htf.get("key_zones", [])[:5]
    plan = []
    for z in zones:
        if z["type"] in {"bullish_fvg", "pdl", "support", "range_low", "sr_flip_support", "support_trendline"}:
            action = "Watch for 1m bullish CHoCH plus high-impact FVG midpoint long."
        elif z["type"] in {
            "bearish_fvg",
            "pdh",
            "resistance",
            "range_high",
            "sr_flip_resistance",
            "resistance_trendline",
        }:
            action = "Watch for 1m bearish CHoCH plus high-impact FVG midpoint short."
        else:
            action = "Watch reaction; require LTF structure confirmation."
        plan.append(
            {
                "condition": f"Price trades into {z['timeframe']} {z['type']} around {z['low']}-{z['high']}.",
                "expected_action": action,
                "craig_style_reason": "HTF zone first, 1m execution second.",
            }
        )
    if not plan:
        plan.append(
            {
                "condition": "No clear HTF zone is available.",
                "expected_action": "Wait or pass.",
                "craig_style_reason": "Craig-style setups need a larger-picture reason.",
            }
        )
    return plan


def final_decision(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not candidates:
        return {
            "action": "wait",
            "candidate_id": None,
            "reason": "No candidate reached an HTF zone with valid 1m FVG/CHoCH confirmation.",
            "craig_likelihood": 0,
            "needs_human_review": False,
        }
    best = candidates[0]
    return {
        "action": best["action"],
        "candidate_id": best["candidate_id"],
        "reason": best["trigger_summary"] if best["action"] != "pass" else best.get("pass_reason") or "low_score",
        "craig_likelihood": best["craig_likelihood"],
        "needs_human_review": best["needs_human_review"],
    }


def run(input_data: Dict[str, Any]) -> Dict[str, Any]:
    raw_tf = input_data.get("timeframes") or {}
    tf = {key: as_candles(value) for key, value in raw_tf.items()}
    htf = build_htf_map(input_data, tf)
    candidates = scan_candidates(input_data, tf, htf)
    htf_public = {k: v for k, v in htf.items() if not k.startswith("_")}
    return {
        "instrument": input_data.get("instrument", "unknown"),
        "market_context": market_context(input_data, tf, htf),
        "htf_map": htf_public,
        "watch_plan": watch_plan(htf),
        "candidates": candidates,
        "final_decision": final_decision(candidates),
        "management_plan": {
            "be_trigger": "Move stop to BE only after favorable BOS candle close.",
            "partial_trigger": "Consider partial around 1:4R or first HTF liquidity target; if BE is secured and a larger HTF draw remains, first support/resistance can be a runner-hold decision.",
            "exit_trigger": "Exit on planned HTF target, opposing CHoCH, stop, or BE.",
            "notes": "Reference scaffold; human review is still required for trendline, true CHoCH quality, and private-tool confluence.",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json", help="Path to chart input JSON matching craig_chart_input_schema.json")
    parser.add_argument("--output", help="Optional path to write decision output JSON")
    args = parser.parse_args()

    with open(args.input_json, "r", encoding="utf-8") as f:
        input_data = json.load(f)
    output = run(input_data)
    payload = json.dumps(output, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(payload)
    else:
        print(payload)


if __name__ == "__main__":
    main()
