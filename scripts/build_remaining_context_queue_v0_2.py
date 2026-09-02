from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCOPE_CSV = ROOT / "data/processed/gold_context_trades/review_scope_bdg_forward.csv"
USER_DATES_CSV = ROOT / "data/source/craig_youtube/user_verified_market_dates.csv"
TRANSCRIPT_DIR = ROOT / "data/source/craig_youtube/transcripts"
OHLCV_DIR = ROOT / "data/raw/binance_futures_live_dates"
OUT_QUEUE = ROOT / "data/processed/gold_context_trades/remaining_context_queue_v0_2.csv"
OUT_FRAME_PLAN = ROOT / "data/processed/gold_context_trades/remaining_frame_capture_plan_v0_2.csv"
OUT_SUMMARY = ROOT / "outputs/remaining_context_queue_v0_2_summary.md"


SYMBOL_RE = re.compile(r"\b(sol(?:ana)?|eth(?:ereum)?|btc|bitcoin|atom|ada|xrp|doge|link|bnb)\b", re.I)
DIRECTION_RE = re.compile(r"\b(long|short|buy|sell)\b", re.I)
CLOCK_PHRASE_RE = re.compile(
    r"\b(?:(?:it'?s|it is|currently|right now it'?s|it's currently)\s+(?:about\s+)?)"
    r"(?P<clock>\d{1,2}:\d{2}|\d{3,4}|\d{1,2})\s*"
    r"(?P<ampm>a\.?m\.?|p\.?m\.?|am|pm)?"
    r"(?:\s*(?P<context>this morning|in the morning|right now|today|tonight|after dinner|overnight))?\b",
    re.I,
)
CLOCK_ABOUT_RE = re.compile(
    r"\b(?:right around|around|about)\s+"
    r"(?P<clock>\d{1,2}:\d{2}|\d{3,4})\s*"
    r"(?P<ampm>a\.?m\.?|p\.?m\.?|am|pm)?\s*"
    r"(?P<context>this morning|in the morning|right now|tonight|after dinner|overnight)\b",
    re.I,
)
CLOCK_TRAILING_CONTEXT_RE = re.compile(
    r"\b(?P<clock>\d{1,2}:\d{2}|\d{3,4})\s*"
    r"(?P<ampm>a\.?m\.?|p\.?m\.?|am|pm)?\s*"
    r"(?P<context>this morning|in the morning|right now|tonight|after dinner|overnight)\b",
    re.I,
)
BAD_TIME_ANCHOR_CONTEXT_RE = re.compile(
    r"(\$|%|"
    r"\b(?:news|minutes?|seconds?|risk|risking|profit|loss|lost|made|bucks|dollars?|"
    r"funding|fees?|factors?|weekly goal|daily goal|turnaround|"
    r"down about|up about|we'?re up|we are up|reward|rr|pnl)\b|"
    r"\b\d+(?:\.\d+)?\s*(?:r|x)\b)",
    re.I,
)
STRONG_TIME_ANCHOR_CONTEXT_RE = re.compile(
    r"\b(?:it'?s|it is|currently|right now|this morning|in the morning|"
    r"today|tonight|after dinner|overnight|a\.?m\.?|p\.?m\.?|am|pm)\b",
    re.I,
)

ENTRY_PAT = re.compile(
    r"\b("
    r"trade setup|setup|set up|position|order|entry|entered|fill|filled|we are in|"
    r"i took|took a|snagged|risking|stop loss|take profit|target"
    r")\b",
    re.I,
)
HIGH_SIGNAL_ENTRY_PAT = re.compile(
    r"\b("
    r"trade number|first trade|second trade|third trade|fourth trade|fifth trade|"
    r"last trade|next trade|trade setup|setup here|position here|short position|"
    r"long position|set up (?:an? )?(?:order|position|trade)|order set|"
    r"we are in|i'?m in|got filled|filled my|entry here|took (?:a|this) trade|"
    r"took (?:a|this|nice)?\s*(?:short|long|position)"
    r")\b",
    re.I,
)
HIGH_SIGNAL_RESULT_PAT = re.compile(
    r"\b("
    r"stopped (?:us |me )?out|stop(?:ped)? out|break even|breakeven|"
    r"took profit|take profit|closed out|lock(?:ed)? in|made \$|lost \$|"
    r"profit of|trade loss|trade profit|missed (?:it|my|the)|never (?:got )?filled|"
    r"for a total|overall for the day|recap"
    r")\b",
    re.I,
)
RESULT_PAT = re.compile(
    r"\b("
    r"stopped out|stop(?:ped)? us out|break even|breakeven|take profit|took profit|"
    r"lock(?:ed)? in|profit|loss|lost|made|gain|recap|overall for the day"
    r")\b",
    re.I,
)
STRUCTURE_PAT = re.compile(
    r"\b("
    r"fair value gap|fvg|change of character|choch|change in state|displacement|"
    r"support|resistance|trend|retest|underside|overside|head and shoulders|"
    r"five wave|5 wave|fibonacci|61\.8|order block|liquidity"
    r")\b",
    re.I,
)


@dataclass
class Segment:
    start: float
    end: float
    anchor: float
    lines: list[dict]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fmt_mmss(sec: float) -> str:
    sec_i = max(0, int(round(sec)))
    return f"{sec_i // 60:02d}:{sec_i % 60:02d}"


def parse_scope_rank(value: str) -> int:
    value = (value or "").strip()
    return int(value) if value.isdigit() else 10_000


def effective_scope_ranks(scope_rows: list[dict[str, str]]) -> dict[str, int]:
    ordered = sorted(
        scope_rows,
        key=lambda row: (
            row.get("upload_date", "") or "99999999",
            parse_scope_rank(row.get("scope_rank", "")),
            row.get("video_id", ""),
        ),
    )
    return {row["video_id"]: idx + 10 for idx, row in enumerate(ordered, 1)}


def normalize_symbol(text: str) -> str:
    hits = [m.group(1).lower() for m in SYMBOL_RE.finditer(text)]
    if not hits:
        return "unknown"
    mapped = []
    for hit in hits:
        if hit.startswith("sol"):
            mapped.append("SOL")
        elif hit.startswith("eth"):
            mapped.append("ETH")
        elif hit in {"btc", "bitcoin"}:
            mapped.append("BTC")
        else:
            mapped.append(hit.upper())
    for priority in ["SOL", "ETH", "ATOM", "BTC"]:
        if priority in mapped:
            return priority
    return mapped[0]


def normalize_direction(text: str) -> str:
    hits = [m.group(1).lower() for m in DIRECTION_RE.finditer(text)]
    if not hits:
        return "unknown"
    short_score = hits.count("short") + hits.count("sell")
    long_score = hits.count("long") + hits.count("buy")
    if short_score > long_score:
        return "short"
    if long_score > short_score:
        return "long"
    return "mixed_or_unknown"


def normalize_time(raw: str, video_sec: float) -> tuple[str, str]:
    if not raw:
        return "", "not_available"
    m = CLOCK_PHRASE_RE.search(raw) or CLOCK_ABOUT_RE.search(raw) or CLOCK_TRAILING_CONTEXT_RE.search(raw)
    if not m:
        return "", "low"
    clock = m.group("clock")
    if ":" in clock:
        hour_s, minute_s = clock.split(":", 1)
        hour = int(hour_s)
        minute = int(minute_s)
    elif len(clock) in {3, 4}:
        hour = int(clock[:-2])
        minute = int(clock[-2:])
    else:
        hour = int(clock)
        minute = 0
    ampm = (m.group("ampm") or "").lower().replace(".", "")
    context = (m.group("context") or "").lower()
    if hour > 24 or minute > 59:
        return "", "not_available"
    confidence = "low"
    if ampm:
        if ampm.startswith("p") and hour < 12:
            hour += 12
        if ampm.startswith("a") and hour == 12:
            hour = 0
        confidence = "medium"
    elif "morning" in context:
        if hour == 12:
            hour = 0
        confidence = "medium"
    elif "after dinner" in context or "tonight" in context:
        if hour < 12:
            hour += 12
        confidence = "medium"
    elif "right now" in context and video_sec >= 20 * 60 and hour <= 11:
        hour += 12
        confidence = "low"
    elif raw.strip() in {"930", "9:30"} or "9:30" in raw:
        confidence = "low"
    if 0 <= hour <= 23:
        return f"{hour:02d}:{minute:02d}", confidence
    return "", "not_available"


def valid_spoken_time_anchor(text: str, match: re.Match[str]) -> bool:
    clock_start = match.start("clock")
    window = text[max(0, clock_start - 55):match.end("clock") + 55]
    if BAD_TIME_ANCHOR_CONTEXT_RE.search(window):
        return False
    if "$" in window or "," in window or "%" in window:
        return False
    if not STRONG_TIME_ANCHOR_CONTEXT_RE.search(window):
        return False
    clock = match.group("clock") or ""
    ampm = (match.group("ampm") or "").strip()
    context = (match.group("context") or "").strip()
    if not (":" in clock or len(clock) in {3, 4} or ampm or context):
        return False
    return True


def nearest_time_anchor(rows: list[dict], anchor: float) -> tuple[str, str, str, str]:
    best: tuple[float, str] | None = None
    for row in rows:
        st = float(row["start"])
        if st > anchor:
            break
        if anchor - st > 900:
            continue
        text = row["text"].replace("\n", " ")
        if re.search(r"\b(news|minutes?|risk|profit|loss|lost|made|bucks|dollars?|funding|fees?|factors?|weekly goal|daily goal|turnaround|down about|up about)\b", text, re.I):
            continue
        match = CLOCK_PHRASE_RE.search(text) or CLOCK_ABOUT_RE.search(text) or CLOCK_TRAILING_CONTEXT_RE.search(text)
        if match:
            if not valid_spoken_time_anchor(text, match):
                continue
            best = (st, text)
    if not best:
        return "", "", "not_available", ""
    raw = best[1]
    norm, conf = normalize_time(raw, best[0])
    return fmt_mmss(best[0]), raw, conf, norm


def load_transcript(video_id: str) -> list[dict]:
    path = TRANSCRIPT_DIR / f"{video_id}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def line_text(row: dict) -> str:
    return row["text"].replace("\n", " ")


def build_segments(rows: list[dict]) -> list[Segment]:
    anchors: list[tuple[float, str]] = []
    for row in rows:
        text = line_text(row)
        if HIGH_SIGNAL_ENTRY_PAT.search(text):
            anchors.append((float(row["start"]), "entry"))
        if HIGH_SIGNAL_RESULT_PAT.search(text):
            anchors.append((float(row["start"]), "result"))

    # Fallback for videos with weaker ASR phrasing.
    if not anchors:
        for row in rows:
            text = line_text(row)
            if ENTRY_PAT.search(text) and (RESULT_PAT.search(text) or STRUCTURE_PAT.search(text)):
                anchors.append((float(row["start"]), "fallback"))

    anchors = sorted((int(sec), kind) for sec, kind in anchors)
    clusters: list[list[tuple[int, str]]] = []
    for anchor in anchors:
        if not clusters or anchor[0] - clusters[-1][-1][0] > 90:
            clusters.append([])
        clusters[-1].append(anchor)

    segments: list[Segment] = []
    for cluster in clusters:
        anchor = cluster[0][0]
        last = cluster[-1][0]
        has_result = any(kind == "result" for _, kind in cluster)
        pad_before = 150 if has_result else 90
        pad_after = 120 if has_result else 180
        start = max(0, anchor - pad_before)
        end = last + pad_after
        if end - start > 480:
            # Long clusters usually mean the video is continuously narrating. Keep the
            # strongest result anchors separate so rows stay close to decision units.
            result_anchors = [sec for sec, kind in cluster if kind == "result"] or [anchor]
            for sec in result_anchors[:8]:
                s2 = max(0, sec - 180)
                e2 = sec + 150
                selected2 = [row for row in rows if s2 <= float(row["start"]) <= e2]
                text2 = " ".join(line_text(row) for row in selected2)
                if len(text2.split()) >= 45 and (ENTRY_PAT.search(text2) or STRUCTURE_PAT.search(text2)):
                    segments.append(Segment(s2, e2, sec, selected2))
            continue
        selected = [row for row in rows if start <= float(row["start"]) <= end]
        joined = " ".join(line_text(row) for row in selected)
        if len(joined.split()) < 45:
            continue
        if not (ENTRY_PAT.search(joined) and (RESULT_PAT.search(joined) or STRUCTURE_PAT.search(joined))):
            continue
        if segments and start <= segments[-1].end + 30 and (max(end, segments[-1].end) - min(start, segments[-1].start) <= 420):
            segments[-1].end = max(segments[-1].end, end)
            segments[-1].lines.extend([row for row in selected if row not in segments[-1].lines])
        else:
            segments.append(Segment(start, end, anchor, selected))

    # Keep candidate counts controlled: early broad setup, live events, recap windows.
    pruned: list[Segment] = []
    for seg in segments:
        text = " ".join(line_text(row) for row in seg.lines)
        has_trade = re.search(r"\b(trade|position|order|entry|filled|stopped|profit|loss|break even|take profit)\b", text, re.I)
        if has_trade:
            pruned.append(seg)
    deduped: list[Segment] = []
    for seg in pruned:
        # Drop near-duplicate windows that share essentially the same anchor.
        if deduped and abs(seg.anchor - deduped[-1].anchor) < 45:
            if (seg.end - seg.start) > (deduped[-1].end - deduped[-1].start):
                deduped[-1] = seg
            continue
        deduped.append(seg)
    return deduped[:12]


def excerpt(rows: list[dict], max_chars: int = 1700) -> str:
    text = " / ".join(f"{fmt_mmss(float(row['start']))} {line_text(row)}" for row in rows)
    return text[:max_chars].rstrip()


def classify_status(text: str) -> str:
    lower = text.lower()
    has_entry = any(k in lower for k in ["entry", "position", "order", "filled", "we are in", "i took"])
    has_setup = any(k in lower for k in ["fair value gap", "fvg", "change of character", "choch", "trend", "support", "resistance", "retest"])
    has_result = any(k in lower for k in ["stopped", "break even", "take profit", "profit", "loss", "lost", "made"])
    missed = any(k in lower for k in ["missed", "never filled", "didn't fill", "did not fill"])
    if has_entry and has_setup and has_result:
        return "auto_executed_trade_review_candidate"
    if missed and has_setup:
        return "auto_actionable_setup_review_candidate"
    if has_setup and has_entry:
        return "auto_needs_result_or_recap"
    return "auto_context_candidate_needs_review"


def frame_policy(text: str, status: str, market_time_norm: str) -> tuple[str, str, str]:
    lower = text.lower()
    captures: list[str] = []
    if any(k in lower for k in ["setup", "entry", "position", "order", "fair value gap", "fvg"]):
        captures.append("setup_or_entry")
    if any(k in lower for k in ["break even", "reduce risk", "stop loss", "trail"]):
        captures.append("management")
    if any(k in lower for k in ["stopped", "take profit", "profit", "loss", "recap", "overall for the day"]):
        captures.append("result_or_recap")
    if not market_time_norm:
        captures.append("bottom_axis_time")
    captures = list(dict.fromkeys(captures))
    if status == "auto_executed_trade_review_candidate" and market_time_norm and len(captures) <= 2:
        policy = "optional_frame_review"
    elif len(captures) <= 1:
        policy = "one_frame_needed"
    else:
        policy = "selected_frames_needed"
    return policy, "|".join(captures), "프레임은 후보당 필요한 확인 지점만 캡처한다."


def ohlcv_status(market_date: str, symbol: str) -> str:
    if not market_date or symbol == "unknown":
        return "not_checkable"
    pair = {"SOL": "SOLUSDT", "ETH": "ETHUSDT", "BTC": "BTCUSDT", "ATOM": "ATOMUSDT"}.get(symbol, f"{symbol}USDT")
    path = OHLCV_DIR / market_date / f"{pair}_1m_{market_date}_ny.csv"
    if path.exists():
        return "cached_1m_available_not_aligned"
    return "missing_symbol_or_date_cache"


def main() -> None:
    scope_rows = read_csv(SCOPE_CSV)
    rank_by_video = effective_scope_ranks(scope_rows)
    user_dates = {row["video_id"]: row for row in read_csv(USER_DATES_CSV)}
    out_rows: list[dict[str, str]] = []
    frame_rows: list[dict[str, str]] = []

    for scope in scope_rows:
        rank = rank_by_video.get(scope["video_id"], parse_scope_rank(scope.get("scope_rank", "")))
        if rank <= 14:
            continue
        video_id = scope["video_id"]
        rows = load_transcript(video_id)
        if not rows:
            continue
        date_info = user_dates.get(video_id, {})
        market_date = date_info.get("verified_market_date") or ""
        market_date_source = date_info.get("verification_source") or ""
        if not market_date:
            raw_upload = scope.get("upload_date", "")
            market_date = f"{raw_upload[:4]}-{raw_upload[4:6]}-{raw_upload[6:8]}" if len(raw_upload) == 8 else raw_upload
            market_date_source = "upload_proxy_needs_bottom_axis_review"

        macro = [row for row in rows if 0 <= float(row["start"]) <= min(420, float(rows[-1]["start"]))]
        macro_excerpt = excerpt(macro, 1200)
        segments = build_segments(rows)
        for idx, seg in enumerate(segments, 1):
            text = " ".join(line_text(row) for row in seg.lines)
            symbol = normalize_symbol(text)
            direction = normalize_direction(text)
            time_anchor_sec, raw_time, time_conf, norm_time = nearest_time_anchor(rows, seg.anchor)
            status = classify_status(text)
            policy, capture_types, frame_note = frame_policy(text, status, "")
            candidate_id = f"{video_id}_auto_{idx:02d}"
            hint_dt = f"{market_date} {norm_time}" if market_date and norm_time else ""
            hint_source = "spoken_time_anchor_unverified" if norm_time else ""
            hint_conf = time_conf if norm_time and time_conf in {"medium", "low"} else ""
            evidence = (
                f"시장일={market_date} ({market_date_source}). "
                f"실제 하단축 시각은 미확보. 참고용 자막 시간 앵커={time_anchor_sec} `{raw_time}`."
                if raw_time
                else f"시장일={market_date} ({market_date_source}). 실제 하단축 시각 미확보, 구간 주변에서 명시적 자막 시각 힌트도 미검출."
            )
            row = {
                "candidate_id": candidate_id,
                "scope_order": str(rank),
                "video_id": video_id,
                "video_title": scope.get("title", ""),
                "upload_date": scope.get("upload_date", ""),
                "youtube_window": f"{fmt_mmss(seg.start)}-{fmt_mmss(seg.end)}",
                "youtube_anchor_sec": str(int(seg.anchor)),
                "market_date": market_date,
                "market_time_utc_minus4": "",
                "market_datetime_utc_minus4": "",
                "market_time_hint_utc_minus4": norm_time,
                "market_datetime_hint_utc_minus4": hint_dt,
                "market_time_hint_source": hint_source,
                "market_time_hint_confidence": hint_conf,
                "market_time_source": "not_extracted",
                "market_time_confidence": "not_available",
                "market_time_evidence_ko": evidence,
                "ohlcv_alignment_status": ohlcv_status(market_date, symbol),
                "symbol": symbol,
                "direction": direction,
                "evidence_status": status,
                "frame_policy": policy,
                "recommended_frame_checks": capture_types,
                "macro_context_excerpt_auto": macro_excerpt,
                "candidate_transcript_excerpt_auto": excerpt(seg.lines),
                "auto_rule_feature_hints": "; ".join(
                    sorted(set(m.group(1).lower() for m in STRUCTURE_PAT.finditer(text)))[:12]
                ),
                "remaining_checks_ko": "자막 자동 후보. gold 승격 전 차트/recap/market time 검수 필요.",
            }
            out_rows.append(row)
            suggested = [int(seg.anchor)]
            if "management" in capture_types:
                suggested.append(int(min(seg.end, seg.anchor + 90)))
            if "result_or_recap" in capture_types:
                suggested.append(int(min(seg.end, seg.anchor + 160)))
            frame_rows.append(
                {
                    "candidate_id": candidate_id,
                    "video_id": video_id,
                    "youtube_window": row["youtube_window"],
                    "suggested_capture_secs": "|".join(str(x) for x in sorted(set(suggested))),
                    "recommended_frame_checks": capture_types,
                    "frame_policy": policy,
                    "reason_ko": frame_note,
                }
            )

    OUT_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    if out_rows:
        with OUT_QUEUE.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
            writer.writeheader()
            writer.writerows(out_rows)
    if frame_rows:
        with OUT_FRAME_PLAN.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(frame_rows[0].keys()))
            writer.writeheader()
            writer.writerows(frame_rows)

    by_video: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for row in out_rows:
        by_video[row["video_id"]] = by_video.get(row["video_id"], 0) + 1
        by_status[row["evidence_status"]] = by_status.get(row["evidence_status"], 0) + 1
    lines = [
        "# Remaining Context Queue v0.2",
        "",
        "이 파일은 파일럿3 이후 남은 영상을 순서대로 자동 스캔한 review queue다. 완성 gold 데이터가 아니라, 누락 방지와 최소 프레임 계획을 위한 상위 후보 목록이다.",
        "",
        f"- videos scanned: {len(by_video)}",
        f"- candidate rows: {len(out_rows)}",
        f"- frame plan rows: {len(frame_rows)}",
        "",
        "## Status Counts",
        "",
    ]
    for key in sorted(by_status):
        lines.append(f"- {key}: {by_status[key]}")
    lines += ["", "## Rows Per Video", ""]
    for video_id, count in sorted(by_video.items(), key=lambda item: min(parse_scope_rank(r.get("scope_order", "")) for r in out_rows if r["video_id"] == item[0])):
        lines.append(f"- `{video_id}`: {count}")
    lines += [
        "",
        f"Queue CSV: `{OUT_QUEUE.relative_to(ROOT).as_posix()}`",
        f"Frame plan CSV: `{OUT_FRAME_PLAN.relative_to(ROOT).as_posix()}`",
    ]
    OUT_SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows={len(out_rows)} videos={len(by_video)} queue={OUT_QUEUE}")
    print(f"frame_plan={OUT_FRAME_PLAN}")


if __name__ == "__main__":
    main()
