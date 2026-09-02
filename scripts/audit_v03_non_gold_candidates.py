from __future__ import annotations

import csv
import re
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "gold_context_trades"
OUT_CSV = PROCESSED / "gold_v03_non_gold_recheck_audit.csv"
OUT_MD = ROOT / "outputs" / "v03_non_gold_recheck_summary.md"

FIELDS = [
    "source_file",
    "candidate_id",
    "video_id",
    "video_title",
    "youtube_window",
    "candidate_status",
    "review_class",
    "extraction_or_interpretation_issue",
    "matched_gold_context_ids",
    "matched_hold_context_ids",
    "action_taken_ko",
    "reason_ko",
    "recommended_next_action_ko",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def parse_time(token: str) -> int | None:
    token = token.strip()
    parts = token.split(":")
    if len(parts) == 2 and all(part.isdigit() for part in parts):
        return int(parts[0]) * 60 + int(parts[1])
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return None


def parse_window(value: str) -> tuple[int, int] | None:
    if not value:
        return None
    matches = re.findall(r"\d{1,2}:\d{2}(?::\d{2})?", value)
    if len(matches) >= 2:
        start = parse_time(matches[0])
        end = parse_time(matches[1])
    elif len(matches) == 1:
        start = parse_time(matches[0])
        end = start + 60 if start is not None else None
    else:
        return None
    if start is None or end is None:
        return None
    if end < start:
        return None
    return start, end


def overlap_seconds(a: tuple[int, int] | None, b: tuple[int, int] | None) -> int:
    if not a or not b:
        return 0
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def normalize_bdg_id(candidate_id: str) -> str:
    return candidate_id.replace("after1220", "v03_after1220")


EXECUTION_HINT_RE = re.compile(
    r"\b(we'?re in|we are in|i'?m in|filled|fill us|position|trade number|trade \d|stop(?:ped)? out|profit|loss|p&l|take off|break even|breakeven|target|tp1|risk)\b",
    re.IGNORECASE,
)


def find_matches(row: dict[str, str], contexts: list[dict[str, str]]) -> list[dict[str, str]]:
    vid = row.get("video_id", "")
    win = parse_window(row.get("youtube_window", ""))
    out = []
    for ctx in contexts:
        if ctx.get("video_id") != vid:
            continue
        cwin = parse_window(ctx.get("youtube_window", ""))
        if overlap_seconds(win, cwin) >= 20:
            out.append(ctx)
    return out


def build() -> list[dict[str, str]]:
    ready = read_csv(PROCESSED / "gold_v03_trade_context_queue.csv")
    hold = read_csv(PROCESSED / "gold_v03_hold_context_queue.csv")
    sessions = {row["video_id"] for row in read_csv(PROCESSED / "gold_v03_video_session_maps.csv")}
    quality_inputs_path = ROOT / "outputs" / "craig_quality_tracker_v0_3" / "quality_tracker_inputs.json"
    if quality_inputs_path.exists():
        inventory_video_ids = {
            row["video_id"]
            for row in json.loads(quality_inputs_path.read_text(encoding="utf-8")).get("videos", [])
        }
    else:
        inventory_video_ids = set()
    ready_by_id = {row["context_id"]: row for row in ready}
    hold_by_id = {row["context_id"]: row for row in hold}

    out: list[dict[str, str]] = []

    for row in read_csv(PROCESSED / "context_review_queue.csv"):
        candidate_id = row.get("candidate_id", "")
        mapped_id = normalize_bdg_id(candidate_id)
        matched_ready = [ready_by_id[mapped_id]] if mapped_id in ready_by_id else []
        matched_hold = [hold_by_id[mapped_id]] if mapped_id in hold_by_id else []
        if matched_ready:
            review_class = "legacy_candidate_promoted_to_v03_gold"
            issue = "no"
            action = "기존 후보가 현재 v0.3 gold/actionable context로 승격되어 있음."
            reason = "candidate_id가 현재 context_id와 직접 매칭됨."
            next_action = "없음"
        elif matched_hold:
            review_class = "legacy_candidate_demoted_to_hold_after_recheck"
            issue = "fixed"
            action = "재검토 결과 gold 승격이 과했으므로 hold로 내림."
            reason = "후보 자체가 context_incomplete/not_gold_context_incomplete였고, 독립 thesis/entry/SL/TP가 부족함."
            next_action = "추가 원본 프레임/주문 박스가 복원되지 않으면 discard 유지."
        else:
            review_class = "legacy_candidate_unmatched"
            issue = "yes_needs_manual_check"
            action = "현재 v0.3 context/hold와 직접 매칭되지 않음."
            reason = "오래된 후보 id와 현재 산출물 사이에 연결이 없음."
            next_action = "수동 점검 필요"
        out.append(
            {
                "source_file": "context_review_queue.csv",
                "candidate_id": candidate_id,
                "video_id": row.get("video_id", ""),
                "video_title": "",
                "youtube_window": row.get("youtube_window", ""),
                "candidate_status": row.get("status", ""),
                "review_class": review_class,
                "extraction_or_interpretation_issue": issue,
                "matched_gold_context_ids": "|".join(ctx["context_id"] for ctx in matched_ready),
                "matched_hold_context_ids": "|".join(ctx["context_id"] for ctx in matched_hold),
                "action_taken_ko": action,
                "reason_ko": reason,
                "recommended_next_action_ko": next_action,
            }
        )

    for row in read_csv(PROCESSED / "remaining_context_queue_v0_2.csv"):
        candidate_text = " ".join(
            [
                row.get("candidate_transcript_excerpt_auto", ""),
                row.get("macro_context_excerpt_auto", ""),
                row.get("remaining_checks_ko", ""),
            ]
        )
        matched_ready = find_matches(row, ready)
        matched_hold = find_matches(row, hold)
        if matched_ready:
            review_class = "auto_candidate_covered_by_merged_v03_context"
            issue = "no"
            action = "자동 후보의 시간/내용이 현재 v0.3 context에 흡수됨."
            reason = "자동 후보 행은 하나의 trade 단위가 아니라 후보 구간이므로, 현재 큐에서는 더 큰 decision context로 병합됨."
            next_action = "없음"
        elif matched_hold:
            review_class = "auto_candidate_covered_by_hold"
            issue = "source_or_context_limited"
            action = "현재 hold context와 겹침."
            reason = "프레임 손상 또는 독립 맥락 부족 때문에 rule seed로 승격하지 않음."
            next_action = "대체 프레임/원본 복구 시 재검토."
        elif row.get("video_id", "") in sessions and row.get("youtube_window", "").startswith("00:00-") and int(row.get("youtube_anchor_sec", "0") or 0) < 300:
            review_class = "auto_candidate_not_promoted_intro_or_session_setup"
            issue = "no"
            action = "초반 intro/session setup 후보로, 독립 trade decision이 아니라 세션 맵 또는 이후 context에 흡수됨."
            reason = "영상 초반 설명/목표/도구 소개 구간이며 실제 실행 맥락은 이후 v0.3 rows에 존재."
            next_action = "없음"
        elif row.get("video_id", "") in sessions and EXECUTION_HINT_RE.search(candidate_text):
            review_class = "auto_candidate_unmatched_execution_hint_spot_review_needed"
            issue = "yes_possible_extraction_gap"
            action = "자동 후보가 현재 v0.3 context와 겹치지 않지만 실행 표현이 있어 spot review 필요."
            reason = "후보 텍스트에 체결/포지션/손절/목표 표현이 있음."
            next_action = "해당 window의 SRT/프레임을 다시 확인해 gold/hold/discard 중 하나로 확정."
        elif row.get("video_id", "") in sessions:
            review_class = "auto_candidate_not_promoted_low_signal_or_session_only"
            issue = "no"
            action = "현재 전체 영상은 v0.3 처리 완료. 이 자동 후보는 별도 decision context로 승격하지 않음."
            reason = "실행 단위보다 넓은 설명/intro/recap 또는 이미 세션 맵으로 흡수된 저신호 후보."
            next_action = "없음"
        else:
            if row.get("video_id", "") not in inventory_video_ids:
                review_class = "legacy_auto_candidate_out_of_current_local_scope"
                issue = "no"
                action = "현재 로컬 프로젝트 영상 목록에서 제외된 오래된 자동 후보로 분류."
                reason = "quality tracker inventory 32개에 없는 video_id이며, 사용자가 제외 영상 파일을 삭제한 뒤 남은 과거 큐 잔여물."
                next_action = "없음"
            else:
                review_class = "auto_candidate_video_not_in_v03_scope"
                issue = "yes_scope_check"
                action = "현재 v0.3 세션 목록에 없는 video_id."
                reason = "로컬 프로젝트 범위/제외 영상 여부 확인 필요."
                next_action = "inventory 확인"
        out.append(
            {
                "source_file": "remaining_context_queue_v0_2.csv",
                "candidate_id": row.get("candidate_id", ""),
                "video_id": row.get("video_id", ""),
                "video_title": row.get("video_title", ""),
                "youtube_window": row.get("youtube_window", ""),
                "candidate_status": row.get("evidence_status", ""),
                "review_class": review_class,
                "extraction_or_interpretation_issue": issue,
                "matched_gold_context_ids": "|".join(ctx["context_id"] for ctx in matched_ready),
                "matched_hold_context_ids": "|".join(ctx["context_id"] for ctx in matched_hold),
                "action_taken_ko": action,
                "reason_ko": reason,
                "recommended_next_action_ko": next_action,
            }
        )

    return out


def main() -> None:
    rows = build()
    write_csv(OUT_CSV, rows, FIELDS)
    counts = Counter(row["review_class"] for row in rows)
    issues = Counter(row["extraction_or_interpretation_issue"] for row in rows)
    flagged = [row for row in rows if row["extraction_or_interpretation_issue"].startswith("yes")]
    lines = [
        "# v0.3 Non-Gold Candidate Recheck",
        "",
        f"- audited rows: {len(rows)}",
        f"- possible extraction/interpretation gaps still flagged: {len(flagged)}",
        "",
        "## Review Class Counts",
        "",
    ]
    for key, value in sorted(counts.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Issue Counts", ""])
    for key, value in sorted(issues.items()):
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Flagged Rows", ""])
    if flagged:
        lines.append("| candidate_id | video_id | window | class | next action |")
        lines.append("|---|---|---|---|---|")
        for row in flagged[:100]:
            lines.append(
                f"| {row['candidate_id']} | {row['video_id']} | {row['youtube_window']} | {row['review_class']} | {row['recommended_next_action_ko']} |"
            )
    else:
        lines.append("No remaining possible extraction/interpretation gaps after this audit.")
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"audit_rows={len(rows)} flagged_possible_gaps={len(flagged)} out={OUT_CSV}")


if __name__ == "__main__":
    main()
