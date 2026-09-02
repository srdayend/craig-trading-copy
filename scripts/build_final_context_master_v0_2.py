from __future__ import annotations

import csv
import re
from pathlib import Path

from build_remaining_context_queue_v0_2 import (
    OHLCV_DIR,
    TRANSCRIPT_DIR,
    fmt_mmss,
    load_transcript,
    nearest_time_anchor,
    ohlcv_status,
)


ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "data/processed/gold_context_trades/manual_seed_contexts.csv"
BDG = ROOT / "data/processed/gold_context_trades/context_review_queue.csv"
PILOT3 = ROOT / "data/processed/gold_context_trades/pilot_3_context_review.csv"
REMAINING = ROOT / "data/processed/gold_context_trades/remaining_context_queue_v0_2.csv"
USER_DATES = ROOT / "data/source/craig_youtube/user_verified_market_dates.csv"
OUT = ROOT / "data/processed/gold_context_trades/final_context_master_v0_2.csv"
OUT_GOLD_READY = ROOT / "data/processed/gold_context_trades/final_gold_ready_candidates_v0_2.csv"
OUT_SUMMARY = ROOT / "outputs/final_context_master_v0_2_summary.md"

FIELDNAMES = [
    "master_id",
    "source_stage",
    "scope_order",
    "video_id",
    "video_title",
    "upload_date",
    "youtube_window",
    "youtube_anchor_sec",
    "market_date",
    "market_time_utc_minus4",
    "market_datetime_utc_minus4",
    "market_time_hint_utc_minus4",
    "market_datetime_hint_utc_minus4",
    "market_time_hint_source",
    "market_time_hint_confidence",
    "market_time_source",
    "market_time_confidence",
    "market_time_evidence_ko",
    "ohlcv_alignment_status",
    "symbol",
    "direction",
    "decision_type",
    "evidence_status",
    "frame_policy",
    "context_ko",
    "setup_ko",
    "chart_understanding_ko",
    "execution_result_ko",
    "rule_features_ko",
    "chart_frame_paths",
    "source_anchors_ko",
    "remaining_checks_ko",
    "raw_context_excerpt",
]

MONTHS = {
    "jan": "01",
    "feb": "02",
    "mar": "03",
    "apr": "04",
    "may": "05",
    "jun": "06",
    "jul": "07",
    "aug": "08",
    "sep": "09",
    "sept": "09",
    "oct": "10",
    "nov": "11",
    "dec": "12",
}
MANUAL_TIME_RE = re.compile(
    r"\b(?:mon|tue|wed|thu|fri|sat|sun)?\s*(?P<day>\d{1,2})\s+"
    r"(?P<mon>[a-z]{3,4})\s+(?P<year>\d{2,4})\s+"
    r"(?P<hour>\d{1,2}):(?P<minute>\d{2})",
    re.I,
)
BAD_SPOKEN_TIME_HINT_RE = re.compile(
    r"(\$|%|"
    r"\b(?:news|minutes?|seconds?|risk|risking|profit|loss|lost|made|bucks|dollars?|"
    r"funding|fees?|factors?|weekly goal|daily goal|turnaround|"
    r"down about|up about|we'?re up|we are up|reward|rr|pnl)\b|"
    r"\b\d+(?:\.\d+)?\s*(?:r|x)\b)",
    re.I,
)
STRONG_SPOKEN_TIME_HINT_RE = re.compile(
    r"\b(?:it'?s|it is|currently|right now|this morning|in the morning|"
    r"today|tonight|after dinner|overnight|a\.?m\.?|p\.?m\.?|am|pm)\b",
    re.I,
)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def parse_mmss_window(window: str) -> float:
    value = (window or "").split("-")[0].strip()
    parts = value.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(float(parts[1]))
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(float(parts[2]))
    try:
        return float(value)
    except ValueError:
        return 0.0


def parse_manual_market_note(note: str) -> tuple[str, str, str, str]:
    match = MANUAL_TIME_RE.search(note or "")
    if not match:
        return "", "", "not_available", "수동 메모에서 기계적으로 날짜/시각을 파싱하지 못함."
    year = match.group("year")
    if len(year) == 2:
        year = "20" + year
    month = MONTHS.get(match.group("mon").lower(), "")
    if not month:
        return "", "", "not_available", f"수동 메모 월 파싱 실패: {note}"
    date = f"{year}-{month}-{int(match.group('day')):02d}"
    time = f"{int(match.group('hour')):02d}:{int(match.group('minute')):02d}"
    return date, time, "high", f"사용자 수동 엑셀의 UTC-4 실제 거래 시각 메모 `{note}`에서 파싱."


def user_date_map() -> dict[str, dict[str, str]]:
    return {row["video_id"]: row for row in read_csv(USER_DATES)}


def date_for_video(video_id: str, upload_date: str = "") -> tuple[str, str, str]:
    row = user_date_map().get(video_id, {})
    if row:
        return (
            row.get("verified_market_date", ""),
            row.get("verification_source", "user_verified"),
            row.get("confidence", "high"),
        )
    if len(upload_date) == 8 and upload_date.isdigit():
        return f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}", "upload_proxy", "low"
    return upload_date, "upload_proxy", "low"


def transcript_time_for(video_id: str, anchor_sec: float) -> tuple[str, str, str, str]:
    rows = load_transcript(video_id)
    if not rows:
        return "", "", "not_available", ""
    time_anchor_sec, raw_time, conf, norm = nearest_time_anchor(rows, anchor_sec)
    source = "spoken_time_anchor" if norm else "not_extracted"
    evidence = (
        f"후보 구간 주변 자막 {time_anchor_sec}에서 `{raw_time}` 시각 표현을 감지. "
        "하단축 직접 OCR은 아님."
        if raw_time
        else "후보 구간 주변 자막에서 명시적 market time 표현을 찾지 못함."
    )
    return norm, source, conf, evidence


def make_datetime(date: str, time: str) -> str:
    return f"{date} {time}" if date and time else ""


def spoken_time_hint(
    market_date: str,
    norm_time: str,
    confidence: str,
    evidence: str,
) -> dict[str, str]:
    if not norm_time:
        return {
            "market_time_hint_utc_minus4": "",
            "market_datetime_hint_utc_minus4": "",
            "market_time_hint_source": "",
            "market_time_hint_confidence": "",
        }
    evidence_text = evidence or ""
    if BAD_SPOKEN_TIME_HINT_RE.search(evidence_text) or not STRONG_SPOKEN_TIME_HINT_RE.search(evidence_text):
        return {
            "market_time_hint_utc_minus4": "",
            "market_datetime_hint_utc_minus4": "",
            "market_time_hint_source": "",
            "market_time_hint_confidence": "",
        }
    hint_conf = confidence if confidence in {"medium", "low"} else "low"
    return {
        "market_time_hint_utc_minus4": norm_time,
        "market_datetime_hint_utc_minus4": make_datetime(market_date, norm_time),
        "market_time_hint_source": "spoken_time_anchor_unverified",
        "market_time_hint_confidence": hint_conf,
    }


def unresolved_time_evidence(market_date: str, date_source: str, date_conf: str, hint_evidence: str = "") -> str:
    parts = [f"시장일={market_date} ({date_source}, {date_conf})."]
    parts.append("실제 UTC-4 거래 시각은 하단축/position box/OHLCV 정렬로 아직 확보하지 못해 확정 칼럼은 비워둠.")
    if hint_evidence:
        parts.append(f"참고용 자막 시간 힌트 검토: {hint_evidence}")
    return " ".join(parts)


def base_row(master_id: str, source_stage: str) -> dict[str, str]:
    return {field: "" for field in FIELDNAMES} | {"master_id": master_id, "source_stage": source_stage}


def add_manual(rows_out: list[dict[str, str]]) -> None:
    for row in read_csv(MANUAL):
        market_date, market_time, conf, evidence = parse_manual_market_note(row.get("market_time_note", ""))
        out = base_row(row.get("trade_id", ""), "manual_seed")
        out.update(
            {
                "scope_order": row.get("playlist_index_oldest_first", ""),
                "video_id": row.get("video_id", ""),
                "youtube_window": row.get("youtube_anchor", ""),
                "youtube_anchor_sec": str(int(parse_mmss_window(row.get("youtube_anchor", "")))),
                "market_date": market_date,
                "market_time_utc_minus4": market_time,
                "market_datetime_utc_minus4": make_datetime(market_date, market_time),
                "market_time_hint_utc_minus4": "",
                "market_datetime_hint_utc_minus4": "",
                "market_time_hint_source": "",
                "market_time_hint_confidence": "",
                "market_time_source": "user_manual_excel",
                "market_time_confidence": conf,
                "market_time_evidence_ko": evidence,
                "ohlcv_alignment_status": ohlcv_status(market_date, row.get("symbol", "").upper()),
                "symbol": row.get("symbol", "").upper(),
                "direction": row.get("direction", ""),
                "decision_type": "manual_seed_context",
                "evidence_status": row.get("status", ""),
                "frame_policy": "selected_frames_needed",
                "context_ko": row.get("pre_entry_thesis_ko", ""),
                "setup_ko": row.get("setup_structure_ko", ""),
                "execution_result_ko": row.get("result_ko", ""),
                "rule_features_ko": row.get("rule_features_ko", ""),
                "source_anchors_ko": row.get("source_anchors_ko", ""),
                "remaining_checks_ko": row.get("missing_or_uncertain_ko", ""),
                "raw_context_excerpt": row.get("original_notes_ko", ""),
            }
        )
        rows_out.append(out)


def add_bdg(rows_out: list[dict[str, str]]) -> None:
    for row in read_csv(BDG):
        anchor = parse_mmss_window(row.get("youtube_window", ""))
        market_date, date_source, date_conf = date_for_video(row.get("video_id", ""))
        market_time_hint, _time_source, time_conf, time_evidence = transcript_time_for(row.get("video_id", ""), anchor)
        hint = spoken_time_hint(market_date, market_time_hint, time_conf, time_evidence)
        out = base_row(row.get("candidate_id", ""), "bDg_visual_review")
        out.update(
            {
                "scope_order": "11",
                "video_id": row.get("video_id", ""),
                "youtube_window": row.get("youtube_window", ""),
                "youtube_anchor_sec": str(int(anchor)),
                "market_date": market_date,
                "market_time_utc_minus4": "",
                "market_datetime_utc_minus4": "",
                **hint,
                "market_time_source": "not_extracted",
                "market_time_confidence": "not_available",
                "market_time_evidence_ko": unresolved_time_evidence(market_date, date_source, date_conf, time_evidence),
                "ohlcv_alignment_status": ohlcv_status(market_date, row.get("symbol", "").upper()),
                "symbol": row.get("symbol", ""),
                "direction": row.get("direction", ""),
                "decision_type": row.get("decision_type", ""),
                "evidence_status": row.get("promoted_rule_evidence_type", "") or row.get("status", ""),
                "frame_policy": "reviewed_selected_chart_frames",
                "context_ko": row.get("context_summary_ko", ""),
                "setup_ko": row.get("setup_summary_ko", ""),
                "chart_understanding_ko": row.get("chart_understanding_ko", ""),
                "execution_result_ko": row.get("execution_result_ko", ""),
                "chart_frame_paths": row.get("chart_frame_paths", ""),
                "source_anchors_ko": row.get("source_anchors_ko", ""),
                "remaining_checks_ko": row.get("remaining_checks_ko", "") or row.get("why_not_gold_yet", ""),
            }
        )
        rows_out.append(out)


def add_pilot3(rows_out: list[dict[str, str]]) -> None:
    for row in read_csv(PILOT3):
        anchor = parse_mmss_window(row.get("youtube_window", ""))
        market_date, date_source, date_conf = date_for_video(row.get("video_id", ""), row.get("upload_date", ""))
        market_time_hint, _time_source, time_conf, time_evidence = transcript_time_for(row.get("video_id", ""), anchor)
        hint = spoken_time_hint(market_date, market_time_hint, time_conf, time_evidence)
        out = base_row(row.get("candidate_id", ""), "pilot3_visual_review")
        out.update(
            {
                "scope_order": row.get("scope_order", ""),
                "video_id": row.get("video_id", ""),
                "video_title": row.get("video_title", ""),
                "upload_date": row.get("upload_date", ""),
                "youtube_window": row.get("youtube_window", ""),
                "youtube_anchor_sec": str(int(anchor)),
                "market_date": market_date,
                "market_time_utc_minus4": "",
                "market_datetime_utc_minus4": "",
                **hint,
                "market_time_source": "not_extracted",
                "market_time_confidence": "not_available",
                "market_time_evidence_ko": unresolved_time_evidence(market_date, date_source, date_conf, time_evidence),
                "ohlcv_alignment_status": ohlcv_status(market_date, row.get("symbol", "").upper()),
                "symbol": row.get("symbol", ""),
                "direction": row.get("direction", ""),
                "decision_type": row.get("decision_type", ""),
                "evidence_status": row.get("evidence_status", ""),
                "frame_policy": "reviewed_selected_chart_frames",
                "context_ko": row.get("transcript_context_ko", ""),
                "setup_ko": row.get("timeframe_evidence_ko", ""),
                "chart_understanding_ko": row.get("chart_understanding_ko", ""),
                "execution_result_ko": row.get("execution_result_ko", ""),
                "rule_features_ko": row.get("rule_features_ko", ""),
                "chart_frame_paths": row.get("chart_frame_paths", ""),
                "source_anchors_ko": row.get("source_anchors_ko", ""),
                "remaining_checks_ko": row.get("remaining_checks_ko", ""),
            }
        )
        rows_out.append(out)


def add_remaining(rows_out: list[dict[str, str]]) -> None:
    for row in read_csv(REMAINING):
        market_date = row.get("market_date", "")
        market_time_hint = row.get("market_time_hint_utc_minus4", "") or row.get("market_time_utc_minus4", "")
        hint_conf = row.get("market_time_hint_confidence", "") or row.get("market_time_confidence", "")
        hint = spoken_time_hint(market_date, market_time_hint, hint_conf, row.get("market_time_evidence_ko", ""))
        date_source = "user_verified_or_upload_proxy"
        date_conf = "mixed"
        out = base_row(row.get("candidate_id", ""), "remaining_auto_queue")
        out.update(
            {
                "scope_order": row.get("scope_order", ""),
                "video_id": row.get("video_id", ""),
                "video_title": row.get("video_title", ""),
                "upload_date": row.get("upload_date", ""),
                "youtube_window": row.get("youtube_window", ""),
                "youtube_anchor_sec": row.get("youtube_anchor_sec", ""),
                "market_date": market_date,
                "market_time_utc_minus4": "",
                "market_datetime_utc_minus4": "",
                **hint,
                "market_time_source": "not_extracted",
                "market_time_confidence": "not_available",
                "market_time_evidence_ko": unresolved_time_evidence(market_date, date_source, date_conf, row.get("market_time_evidence_ko", "")),
                "ohlcv_alignment_status": row.get("ohlcv_alignment_status", ""),
                "symbol": row.get("symbol", ""),
                "direction": row.get("direction", ""),
                "decision_type": "auto_transcript_candidate",
                "evidence_status": row.get("evidence_status", ""),
                "frame_policy": row.get("frame_policy", ""),
                "context_ko": "자동 추출 후보. 이 행은 아직 gold 메모가 아니라 자막 후보와 최소 프레임 계획이다.",
                "setup_ko": row.get("auto_rule_feature_hints", ""),
                "rule_features_ko": row.get("auto_rule_feature_hints", ""),
                "remaining_checks_ko": row.get("remaining_checks_ko", ""),
                "raw_context_excerpt": row.get("candidate_transcript_excerpt_auto", ""),
            }
        )
        rows_out.append(out)


def write_outputs(rows: list[dict[str, str]]) -> None:
    rows.sort(key=lambda r: (int(r["scope_order"]) if str(r["scope_order"]).isdigit() else 10_000, r["video_id"], float(r["youtube_anchor_sec"] or 0)))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    gold_ready = [
        row
        for row in rows
        if row["source_stage"] in {"bDg_visual_review", "pilot3_visual_review", "manual_seed"}
        and (
            row["evidence_status"].startswith("gold_")
            or row["evidence_status"] in {"needs_frame_review"}
        )
    ]
    with OUT_GOLD_READY.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(gold_ready)

    by_stage: dict[str, int] = {}
    by_status: dict[str, int] = {}
    time_counts = {"high": 0, "medium": 0, "low": 0, "not_available": 0, "": 0}
    hint_counts = {"medium": 0, "low": 0, "": 0}
    for row in rows:
        by_stage[row["source_stage"]] = by_stage.get(row["source_stage"], 0) + 1
        by_status[row["evidence_status"]] = by_status.get(row["evidence_status"], 0) + 1
        time_counts[row["market_time_confidence"]] = time_counts.get(row["market_time_confidence"], 0) + 1
        hint_counts[row["market_time_hint_confidence"]] = hint_counts.get(row["market_time_hint_confidence"], 0) + 1
    verified_dates = sum(1 for row in rows if row["market_date"])
    exact_times = sum(1 for row in rows if row["market_time_utc_minus4"])
    spoken_hints = sum(1 for row in rows if row["market_time_hint_utc_minus4"])
    lines = [
        "# Final Context Master v0.2",
        "",
        "이 파일은 현재 방식의 통합 산출물이다. 이미 시각 검토한 bDg/파일럿3와, 남은 영상 전체의 자동 review queue를 같은 스키마로 합쳤다.",
        "",
        "중요: `remaining_auto_queue` 행은 최종 gold가 아니라 누락 방지용 후보이며, `final_gold_ready_candidates_v0_2.csv`만 바로 룰 증거 후보로 보는 것이 안전하다.",
        "",
        "시간 원칙: `market_time_utc_minus4`는 수동 엑셀/하단축/OHLCV 정렬처럼 실제로 확보된 시각만 넣는다. 자막에서 들린 시각은 `market_time_hint_utc_minus4`에만 보관한다.",
        "",
        f"- master rows: {len(rows)}",
        f"- visual/manual ready rows: {len(gold_ready)}",
        f"- rows with market date present: {sum(1 for row in rows if row['market_date'])}",
        f"- rows with secured UTC-4 market time: {exact_times}",
        f"- rows with spoken/session time hint only: {spoken_hints}",
        "",
        "## Source Stage Counts",
        "",
    ]
    for key in sorted(by_stage):
        lines.append(f"- {key}: {by_stage[key]}")
    lines += ["", "## Evidence Status Counts", ""]
    for key in sorted(by_status):
        lines.append(f"- {key}: {by_status[key]}")
    lines += ["", "## Market Time Confidence", ""]
    for key in ["high", "medium", "low", "not_available", ""]:
        if time_counts.get(key, 0):
            label = key or "blank"
            lines.append(f"- {label}: {time_counts[key]}")
    lines += ["", "## Spoken Time Hint Confidence", ""]
    for key in ["medium", "low", ""]:
        if hint_counts.get(key, 0):
            label = key or "blank"
            lines.append(f"- {label}: {hint_counts[key]}")
    lines += [
        "",
        "## Files",
        "",
        f"- master: `{OUT.relative_to(ROOT).as_posix()}`",
        f"- gold-ready subset: `{OUT_GOLD_READY.relative_to(ROOT).as_posix()}`",
        f"- remaining frame plan: `data/processed/gold_context_trades/remaining_frame_capture_plan_v0_2.csv`",
    ]
    OUT_SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    rows: list[dict[str, str]] = []
    add_manual(rows)
    add_bdg(rows)
    add_pilot3(rows)
    add_remaining(rows)
    write_outputs(rows)
    print(f"master={OUT}")
    print(f"gold_ready={OUT_GOLD_READY}")
    print(f"summary={OUT_SUMMARY}")


if __name__ == "__main__":
    main()
