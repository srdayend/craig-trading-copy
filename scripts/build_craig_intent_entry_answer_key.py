#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "outputs" / "craig_live_trading_video_inventory.csv"
ATOMIC = ROOT / "outputs" / "craig_transcript_atomic_labels.csv"
TRANSCRIPTS = ROOT / "data" / "source" / "craig_youtube" / "transcripts"
OUT_CSV = ROOT / "outputs" / "craig_intent_entry_answer_key_v0_1.csv"
OUT_VERIFIED_CSV = ROOT / "outputs" / "craig_intent_entry_answer_key_verified_recent_v0_1.csv"
OUT_MD = ROOT / "outputs" / "craig_intent_entry_answer_key_v0_1.md"
OUT_CHECK = ROOT / "outputs" / "craig_intent_entry_user_check_queue_v0_1.md"
OUT_VERIFIED_CHECK = ROOT / "outputs" / "craig_intent_entry_user_check_queue_verified_recent_v0_1.md"


NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
}


PATTERNS: list[tuple[str, int, re.Pattern[str]]] = [
    (
        "executed_entry",
        5,
        re.compile(
            r"\bi[' ]?m in on my entry\b|"
            r"\b(?:we[' ]?re|we are|i[' ]?m|i am)\s+in\s+on\s+(?:this|the|my)\s+(?:trade|position|entry)\b|"
            r"\b(?:we[' ]?re|we are|i[' ]?m|i am)\s+in\s+(?:this|the)\s+(?:trade|position)\b|"
            r"\b(?:we|i)\s+(?:just\s+)?got\s+(?:us|me)?\s*filled\b|"
            r"\b(?:just\s+)?got\s+(?:us|me)?\s*filled\b|"
            r"\b(?:filled|tagged)\s+(?:us|me)?\s*(?:in|on|into)\s*(?:the\s+)?entry\b|"
            r"\b(?:we[' ]?re|we are)\s+into\s+trade\s+number\b|"
            r"\b(?:we[' ]?re|we are)\s+in\s+our\s+position\b",
            re.IGNORECASE,
        ),
    ),
    (
        "direct_position",
        5,
        re.compile(
            r"\bi[' ]?m\s+(?:now\s+)?taking\s+(?:a\s+)?(?:long|short)\s+position\b|"
            r"\bi[' ]?m\s+(?:now\s+)?taking\s+(?:this|the|a)\s+trade\b|"
            r"\b(?:we[' ]?re|we are)\s+(?:now\s+)?taking\s+(?:this|the|a)\s+trade\b|"
            r"\bjust\s+took\s+(?:another\s+)?(?:a\s+)?trade\b|"
            r"\bi\s+just\s+took\s+(?:another\s+)?(?:a\s+)?trade\b|"
            r"\bi\s+took\s+another\s+trade\b",
            re.IGNORECASE,
        ),
    ),
    (
        "planned_position",
        4,
        re.compile(
            r"\b(?:i[' ]?m|i am|we[' ]?re|we are)\s+(?:now\s+)?looking\s+to\s+(?:get\s+in|enter|take)\b|"
            r"\b(?:i[' ]?m|i am|we[' ]?re|we are)\s+(?:now\s+)?waiting\s+to\s+(?:get\s+in|enter|take)\b|"
            r"\b(?:i\s+)?want\s+to\s+(?:get\s+in|get\s+filled|enter|take\s+(?:this|the|a)\s+trade)\b|"
            r"\b(?:if|when)\s+price\b.{0,140}\bget\s+(?:me|us)\s+in\b|"
            r"\b(?:get|getting)\s+(?:me|us)?\s*filled\b|"
            r"\bget\s+(?:me|us)\s+filled\s+on\s+(?:our\s+)?trade\s+number\b|"
            r"\btrade\s+setup\b.{0,100}\blooking\s+to\s+get\s+in\b",
            re.IGNORECASE,
        ),
    ),
    (
        "order_setup",
        3,
        re.compile(
            r"\b(?:i[' ]?m|i am)\s+(?:going\s+to\s+)?(?:set(?:ting)?\s+up|placing|place)\s+my\s+(?:order|position|trade)\b|"
            r"\b(?:i[' ]?m|i am)\s+(?:going\s+to\s+)?(?:place|placing)\s+(?:a\s+)?(?:buy|sell|limit)\s+order\b|"
            r"\b(?:buy|sell)\s+order\b.{0,80}\b(?:entry|position|trade)\b",
            re.IGNORECASE,
        ),
    ),
]

FALSE_CONTEXT_RE = re.compile(
    r"\b(?:take profit|take you|take a look|take control|taking profit|"
    r"don[' ]?t want to take this trade|do not want to take this trade|not going to take this trade|"
    r"for example|say for example|example here|example of|hypothetical)\b",
    re.IGNORECASE,
)

EXPLICIT_TRADE_NO_RE = re.compile(
    r"\btrade\s+number\s+(?P<num>\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b|"
    r"\b(?P<ord>first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+trade\b",
    re.IGNORECASE,
)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def clean(text: str, limit: int = 260) -> str:
    value = re.sub(r"\s+", " ", text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def short_quote(text: str, limit_words: int = 18) -> str:
    value = clean(text, 500)
    words = value.split()
    return " ".join(words[:limit_words])


def parse_float(value: str) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def format_mmss(seconds: float) -> str:
    sec = int(round(seconds))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def load_transcript(video_id: str) -> list[dict[str, str | float]]:
    path = TRANSCRIPTS / f"{video_id}.json"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data


def context_text(segments: list[dict[str, str | float]], idx: int, left: int = 5, right: int = 7) -> str:
    start = max(0, idx - left)
    end = min(len(segments), idx + right + 1)
    return clean(" ".join(str(seg.get("text", "")) for seg in segments[start:end]), 900)


def match_anchor(text: str) -> tuple[str, int, str] | None:
    # Generic live-session planning near the intro produces too many false positives.
    # Keep actual entry/fill phrases even if the surrounding text contains "take profit";
    # apply the false-context filter to planned/order phrases only.
    for kind, confidence, pattern in PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        if kind in {"planned_position", "order_setup"} and FALSE_CONTEXT_RE.search(text):
            return None
        return kind, confidence, clean(match.group(0), 90)
    return None


def direction_from_text(text: str) -> tuple[str, str]:
    low = text.lower()
    short_hits = [
        "short position",
        "short trade",
        "looking for shorts",
        "looking to short",
        "sell order",
        "bearish",
        "downside",
        "move lower",
        "pull down",
        "drop",
        "reject",
    ]
    long_hits = [
        "long position",
        "long trade",
        "looking for longs",
        "looking to long",
        "buy order",
        "bullish",
        "upside",
        "dip entry",
        "ride out",
        "move higher",
        "push up",
        "bounce",
    ]
    short_score = sum(1 for item in short_hits if item in low)
    long_score = sum(1 for item in long_hits if item in low)
    if "short position" in low:
        return "short", "direct_phrase"
    if "long position" in low:
        return "long", "direct_phrase"
    if short_score > long_score:
        return "short", "context_keywords"
    if long_score > short_score:
        return "long", "context_keywords"
    return "unknown", "not_enough_text"


def trade_no_from_text(text: str) -> tuple[str, str]:
    match = EXPLICIT_TRADE_NO_RE.search(text)
    if not match:
        return "", ""
    raw = match.group("num") or match.group("ord") or ""
    raw_low = raw.lower()
    if raw_low.isdigit():
        return raw_low, "explicit_in_speech"
    if raw_low in NUMBER_WORDS:
        return str(NUMBER_WORDS[raw_low]), "explicit_in_speech"
    return "", ""


def tag_if(text: str, patterns: Iterable[str]) -> bool:
    low = text.lower()
    return any(pattern in low for pattern in patterns)


def htf_summary(text: str, atomic_rows: list[dict[str, str]]) -> str:
    tags = []
    all_text = text.lower()
    features = "|".join(row.get("observed_features", "") for row in atomic_rows).lower()
    if tag_if(all_text, ["4 hour", "4-hour", "four hour", "4h"]):
        tags.append("4H")
    if tag_if(all_text, ["15 minute", "15-minute", "15m"]):
        tags.append("15M")
    if tag_if(all_text, ["higher time frame", "macro level", "macro"]):
        tags.append("HTF/macro")
    if tag_if(all_text, ["trend line", "trendline"]) or "trendline" in features:
        tags.append("trendline")
    if tag_if(all_text, ["support", "resistance", "key level", "flip", "retest"]) or "sr" in features:
        tags.append("SR/flip")
    if tag_if(all_text, ["fair value gap", "fvg", "gap"]) or "fvg" in features:
        tags.append("HTF/FVG")
    if tag_if(all_text, ["previous day", "pd high", "pd low", "daily bias", "day high", "day low"]):
        tags.append("daily/liquidity")
    if tag_if(all_text, ["liquidity", "sweep", "taken out"]) or "liquidity" in features:
        tags.append("liquidity/sweep")
    if not tags:
        return "자막상 HTF 근거는 약함/영상 확인 필요"
    return ", ".join(dict.fromkeys(tags))


def entry_summary(text: str, atomic_rows: list[dict[str, str]]) -> str:
    tags = []
    all_text = text.lower()
    features = "|".join(row.get("observed_features", "") for row in atomic_rows).lower()
    if tag_if(all_text, ["change of character", "choch"]) or "choch" in features:
        tags.append("CHoCH")
    if tag_if(all_text, ["break of structure", "bos", "break underneath", "break above"]) or "bos" in features:
        tags.append("BOS/structure break")
    if tag_if(all_text, ["fair value gap", "fvg", "gap"]) or "fvg" in features:
        tags.append("1M/entry FVG")
    if tag_if(all_text, ["midpoint", "50%", "equilibrium"]) or "midpoint" in features:
        tags.append("midpoint/equilibrium")
    if tag_if(all_text, ["retest", "tap", "tag", "pull back", "pullback"]):
        tags.append("retest/tap")
    if tag_if(all_text, ["trend line", "trendline"]):
        tags.append("trendline reaction")
    if not tags:
        return "entry trigger는 영상/차트 확인 필요"
    return ", ".join(dict.fromkeys(tags))


def risk_summary(text: str, atomic_rows: list[dict[str, str]]) -> str:
    event_counts = Counter(row.get("source_event_type", "") for row in atomic_rows)
    parts = []
    low = text.lower()
    if "stop loss" in low or event_counts.get("STOP_RISK"):
        parts.append("SL 언급/근처 구조 밖")
    if "take profit" in low or "target" in low or event_counts.get("TARGET_TP"):
        parts.append("TP/target 언급")
    if "break even" in low or event_counts.get("BREAKEVEN"):
        parts.append("BE 관리 언급")
    if not parts:
        return "SL/TP는 position box 또는 후속 문장 확인 필요"
    return ", ".join(dict.fromkeys(parts))


def atomic_support(
    atomic_by_video: dict[str, list[dict[str, str]]], video_id: str, start: float, end: float
) -> list[dict[str, str]]:
    return [
        row
        for row in atomic_by_video.get(video_id, [])
        if start <= parse_float(row.get("timestamp_sec", "")) <= end
    ]


def cluster_anchors(anchors: list[dict[str, str | float | int]]) -> list[list[dict[str, str | float | int]]]:
    anchors.sort(key=lambda row: float(row["timestamp_sec"]))
    clusters: list[list[dict[str, str | float | int]]] = []
    for anchor in anchors:
        ts = float(anchor["timestamp_sec"])
        explicit_no = str(anchor.get("explicit_trade_no", ""))
        if not clusters:
            clusters.append([anchor])
            continue
        last = clusters[-1]
        cluster_start = min(float(row["timestamp_sec"]) for row in last)
        last_ts = max(float(row["timestamp_sec"]) for row in last)
        last_numbers = {str(row.get("explicit_trade_no", "")) for row in last if row.get("explicit_trade_no")}
        last_known_dirs = {str(row.get("direction", "")) for row in last if row.get("direction") in {"long", "short"}}
        current_dir = str(anchor.get("direction", ""))
        current_context = str(anchor.get("context", "")).lower()
        if (
            ts - cluster_start > 45
            and re.search(r"\b(another|next)\s+trade\b|\btrade\s+number\b", current_context)
        ):
            clusters.append([anchor])
            continue
        if explicit_no and last_numbers and explicit_no not in last_numbers:
            clusters.append([anchor])
            continue
        if explicit_no and not last_numbers and ts - cluster_start > 45:
            clusters.append([anchor])
            continue
        if current_dir in {"long", "short"} and last_known_dirs and current_dir not in last_known_dirs and ts - last_ts > 25:
            clusters.append([anchor])
            continue
        if ts - cluster_start > 150 and ts - last_ts > 35:
            clusters.append([anchor])
            continue
        window = 125 if anchor["anchor_kind"] in {"planned_position", "order_setup"} else 105
        if ts - last_ts <= window:
            clusters[-1].append(anchor)
        else:
            clusters.append([anchor])
    return clusters


def cluster_best_anchor(cluster: list[dict[str, str | float | int]]) -> dict[str, str | float | int]:
    order = {"direct_position": 4, "executed_entry": 3, "planned_position": 2, "order_setup": 1}
    best = max(cluster, key=lambda row: (order.get(str(row["anchor_kind"]), 0), int(row["phrase_confidence"])))
    return best


def likely_status(kind: str, support: list[dict[str, str]], text: str) -> str:
    event_types = {row.get("source_event_type", "") for row in support}
    low = text.lower()
    if kind in {"executed_entry", "direct_position"}:
        return "likely_actual_entry"
    if "ENTRY" in event_types or "i'm in" in low or "we're in" in low or "got filled" in low:
        return "likely_actual_entry_from_support"
    if kind == "planned_position":
        return "entry_intent_needs_fill_check"
    return "order_setup_needs_fill_check"


def answer_grade(status: str, direction: str, risk: str, htf: str, entry: str) -> str:
    score = 0
    if status.startswith("likely_actual_entry"):
        score += 2
    if direction != "unknown":
        score += 1
    if "확인 필요" not in risk:
        score += 1
    if "약함" not in htf:
        score += 1
    if "확인 필요" not in entry:
        score += 1
    if score >= 5:
        return "A_answer_key_seed"
    if score >= 3:
        return "B_user_check_priority"
    return "C_candidate_check_later"


def build() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    inventory = {row["video_id"]: row for row in read_csv(INVENTORY)}
    atomic_rows = read_csv(ATOMIC)
    atomic_by_video: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in atomic_rows:
        if row.get("video_id") in inventory:
            atomic_by_video[row["video_id"]].append(row)
    for rows in atomic_by_video.values():
        rows.sort(key=lambda row: parse_float(row.get("timestamp_sec", "")))

    answer_rows: list[dict[str, str]] = []
    gap_rows: list[dict[str, str]] = []
    for video_id, inv in inventory.items():
        segments = load_transcript(video_id)
        anchors: list[dict[str, str | float | int]] = []
        for idx, segment in enumerate(segments):
            match_ctx = context_text(segments, idx, left=0, right=2)
            matched = match_anchor(match_ctx)
            if not matched:
                continue
            kind, phrase_conf, matched_phrase = matched
            # Most intro explanations are not per-trade answer keys.
            ts = float(segment.get("start", 0.0))
            if ts < 210 and kind in {"planned_position", "order_setup"}:
                continue
            summary_ctx = context_text(segments, idx, left=7, right=12)
            trade_no, trade_no_source = trade_no_from_text(match_ctx + " " + summary_ctx)
            direction, direction_source = direction_from_text(match_ctx + " " + summary_ctx)
            anchors.append(
                {
                    "timestamp_sec": ts,
                    "segment_index": idx,
                    "anchor_kind": kind,
                    "phrase_confidence": phrase_conf,
                    "matched_phrase": matched_phrase,
                    "explicit_trade_no": trade_no,
                    "trade_no_source": trade_no_source,
                    "direction": direction,
                    "direction_source": direction_source,
                    "context": summary_ctx,
                    "quote": short_quote(match_ctx),
                }
            )
        clusters = cluster_anchors(anchors)
        prior_no = 0
        video_answer_rows: list[dict[str, str]] = []
        for seq, cluster in enumerate(clusters, 1):
            cluster_start = min(float(row["timestamp_sec"]) for row in cluster)
            cluster_end = max(float(row["timestamp_sec"]) for row in cluster)
            best_anchor = cluster_best_anchor(cluster)
            anchor_ts = float(best_anchor["timestamp_sec"])
            all_context = clean(" ".join(str(row["context"]) for row in cluster), 1500)
            explicit_numbers = [
                int(str(row["explicit_trade_no"]))
                for row in cluster
                if str(row.get("explicit_trade_no", "")).isdigit()
            ]
            if explicit_numbers:
                trade_no = max(set(explicit_numbers), key=explicit_numbers.count)
                trade_no_source = "explicit_in_speech"
                prior_no = max(prior_no, trade_no)
            else:
                prior_no += 1
                trade_no = prior_no
                trade_no_source = "sequential_candidate_order"
            direction_counts = Counter(str(row["direction"]) for row in cluster if row.get("direction") != "unknown")
            if direction_counts:
                direction = direction_counts.most_common(1)[0][0]
                direction_source = "cluster_context_keywords"
            else:
                direction = "unknown"
                direction_source = "not_enough_text"
            support = atomic_support(atomic_by_video, video_id, max(0, cluster_start - 220), cluster_end + 360)
            kind = str(best_anchor["anchor_kind"])
            phrase_conf = int(best_anchor["phrase_confidence"])
            htf = htf_summary(all_context, support)
            entry = entry_summary(all_context, support)
            risk = risk_summary(all_context, support)
            status = likely_status(kind, support, all_context)
            grade = answer_grade(status, direction, risk, htf, entry)
            best_quote = str(best_anchor["quote"])
            row = {
                "answer_id": f"{video_id}_trade{trade_no:02d}_{int(round(anchor_ts))}",
                "video_id": video_id,
                "market_date": inv.get("market_date_for_fetch", ""),
                "market_date_status": inv.get("market_date_status", ""),
                "title": inv.get("title", ""),
                "trade_no_for_user": str(trade_no),
                "trade_no_source": trade_no_source,
                "youtube_trade_link": f"https://www.youtube.com/watch?v={video_id}&t={int(anchor_ts)}s",
                "video_url": inv.get("url", ""),
                "anchor_sec": f"{anchor_ts:.2f}",
                "anchor_time_mmss": format_mmss(anchor_ts),
                "context_start_sec": f"{cluster_start:.2f}",
                "context_end_sec": f"{cluster_end:.2f}",
                "anchor_kind": kind,
                "entry_status_guess": status,
                "answer_key_grade": grade,
                "phrase_confidence_1_5": str(phrase_conf),
                "matched_phrase": str(best_anchor.get("matched_phrase", "")),
                "direction_guess": direction,
                "direction_source": direction_source,
                "htf_context_summary_ko": htf,
                "entry_trigger_summary_ko": entry,
                "risk_target_summary_ko": risk,
                "position_box_status": "user_will_supply_or_manual_chart_check",
                "user_check_needed_ko": "해당 유튜브 시점에서 TradingView position box/주문 박스 기준 direction, entry, SL, TP 확인",
                "support_event_types": "|".join(sorted(Counter(row.get("source_event_type", "") for row in support))),
                "supporting_atomic_events": str(len(support)),
                "evidence_short_quote": best_quote,
            }
            video_answer_rows.append(row)
        video_answer_rows.sort(key=lambda row: parse_float(row["anchor_sec"]))
        answer_rows.extend(video_answer_rows)
        gap_rows.append(
            {
                "video_id": video_id,
                "title": inv.get("title", ""),
                "market_date": inv.get("market_date_for_fetch", ""),
                "intent_entry_candidates": str(len(video_answer_rows)),
                "take_labels": inv.get("observed_take_labels", ""),
                "manage_labels": inv.get("observed_manage_labels", ""),
                "tp_close_labels": inv.get("observed_tp_close_labels", ""),
                "loss_labels": inv.get("observed_loss_labels", ""),
                "url": inv.get("url", ""),
            }
        )
    answer_rows.sort(key=lambda row: (row["market_date"], row["video_id"], parse_float(row["anchor_sec"])))
    return answer_rows, gap_rows


def write_markdown(rows: list[dict[str, str]], gaps: list[dict[str, str]]) -> None:
    grade_counts = Counter(row["answer_key_grade"] for row in rows)
    status_counts = Counter(row["entry_status_guess"] for row in rows)
    by_video = defaultdict(list)
    for row in rows:
        by_video[row["video_id"]].append(row)

    lines = [
        "# Craig Intent Entry Answer Key v0.1",
        "",
        "이 정답지는 기존 `Take` 라벨만 보던 방식에서 벗어나, 자막 문맥상 Craig가 포지션에 들어가려 하거나 실제 들어갔다고 말한 구간을 우선 추출한 것이다.",
        "",
        "주의: position box 가격은 아직 확정하지 않았다. 사용자가 확인할 수 있도록 유튜브 링크와 영상 안 후보 거래 번호를 붙였다.",
        "",
        "## 요약",
        "",
        f"- intent/entry 후보: {len(rows)}",
        f"- 영상 수: {len(by_video)}",
        "",
        "## 등급",
        "",
        "| 등급 | 개수 | 의미 |",
        "|---|---:|---|",
    ]
    meanings = {
        "A_answer_key_seed": "실제 진입 가능성이 높고 방향/근거/SL·TP 단서가 비교적 잘 붙은 우선 정답지",
        "B_user_check_priority": "진입 의도 또는 실제 진입이 보이나 position box 확인이 필요한 우선 후보",
        "C_candidate_check_later": "진입 의도는 있으나 체결 여부/방향/SL·TP 확인이 더 필요한 후보",
    }
    for key, count in grade_counts.most_common():
        lines.append(f"| `{key}` | {count} | {meanings.get(key, '')} |")
    lines.extend(["", "## 상태", "", "| 상태 | 개수 |", "|---|---:|"])
    for key, count in status_counts.most_common():
        lines.append(f"| `{key}` | {count} |")
    lines.extend(["", "## 영상별 후보 수", "", "| date | video | 후보 | Take 라벨 | 링크 |", "|---|---|---:|---:|---|"])
    for gap in sorted(gaps, key=lambda row: (row["market_date"], row["video_id"])):
        if int(gap["intent_entry_candidates"]) == 0:
            continue
        lines.append(
            f"| {gap['market_date']} | `{gap['video_id']}` | {gap['intent_entry_candidates']} | "
            f"{gap['take_labels']} | [video]({gap['url']}) |"
        )
    lines.extend(["", "## 사용자 확인 우선순위", "", "| 우선 | date | video/trade | 시점 | 방향 | 상태 | 핵심 근거 | 링크 |", "|---:|---|---|---:|---|---|---|---|"])
    priority_rows = sorted(
        rows,
        key=lambda row: (
            {"A_answer_key_seed": 0, "B_user_check_priority": 1, "C_candidate_check_later": 2}.get(
                row["answer_key_grade"], 9
            ),
            row["market_date"],
            row["video_id"],
            parse_float(row["anchor_sec"]),
        ),
    )
    for idx, row in enumerate(priority_rows[:40], 1):
        basis = clean(
            f"{row['htf_context_summary_ko']} / {row['entry_trigger_summary_ko']} / {row['risk_target_summary_ko']}",
            120,
        )
        lines.append(
            f"| {idx} | {row['market_date']} | `{row['video_id']} #{row['trade_no_for_user']}` | "
            f"{row['anchor_time_mmss']} | {row['direction_guess']} | `{row['entry_status_guess']}` | {basis} | "
            f"[trade link]({row['youtube_trade_link']}) |"
        )
    lines.extend(
        [
            "",
            "## 파일",
            "",
            f"- CSV: `{OUT_CSV.relative_to(ROOT)}`",
            f"- 날짜 검증 CSV: `{OUT_VERIFIED_CSV.relative_to(ROOT)}`",
            f"- 전체 검수 queue: `{OUT_CHECK.relative_to(ROOT)}`",
            f"- 날짜 검증 영상 우선 queue: `{OUT_VERIFIED_CHECK.relative_to(ROOT)}`",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def check_table(table_rows: list[dict[str, str]], title: str, note: str) -> str:
        check_lines = [
            title,
            "",
            note,
            "",
            "| 우선 | date | 영상 제목 | 후보 거래 | 시점 | 방향 | 확인할 것 | 링크 |",
            "|---:|---|---|---|---:|---|---|---|",
        ]
        for idx, row in enumerate(table_rows, 1):
            title_text = clean(row["title"], 52)
            check = clean(row["user_check_needed_ko"], 70)
            check_lines.append(
                f"| {idx} | {row['market_date']} | {title_text} | `{row['video_id']} #{row['trade_no_for_user']}` | "
                f"{row['anchor_time_mmss']} | {row['direction_guess']} | {check} | [YouTube]({row['youtube_trade_link']}) |"
            )
        return "\n".join(check_lines) + "\n"

    all_check = [
        "# Craig Intent Entry User Check Queue v0.1",
    ]
    OUT_CHECK.write_text(
        check_table(
            priority_rows,
            "# Craig Intent Entry User Check Queue v0.1",
            "사용자가 확인할 때 필요한 최소 정보만 모은 queue다. 각 줄의 `#N`은 같은 영상 안에서 시간순으로 붙인 후보 거래 번호다.",
        ),
        encoding="utf-8",
    )

    verified_rows = [row for row in priority_rows if "verified" in row["market_date_status"]]
    OUT_VERIFIED_CHECK.write_text(
        check_table(
            verified_rows,
            "# Craig Intent Entry Verified Recent Check Queue v0.1",
            "사용자가 날짜를 확인했거나 고해상도 프레임으로 날짜가 검증된 영상만 모은 우선 검수 queue다.",
        ),
        encoding="utf-8",
    )


def main() -> None:
    rows, gaps = build()
    write_csv(OUT_CSV, rows)
    write_csv(OUT_VERIFIED_CSV, [row for row in rows if "verified" in row["market_date_status"]])
    write_markdown(rows, gaps)
    print(f"intent_entry_answer_rows={len(rows)}")
    print(f"videos_with_candidates={len({row['video_id'] for row in rows})}")
    print(f"output={OUT_CSV}")
    print(f"verified_output={OUT_VERIFIED_CSV}")
    print(f"report={OUT_MD}")
    print(f"check_queue={OUT_CHECK}")
    print(f"verified_check_queue={OUT_VERIFIED_CHECK}")


if __name__ == "__main__":
    main()
