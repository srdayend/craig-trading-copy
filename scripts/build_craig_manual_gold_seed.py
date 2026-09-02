#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
IN_CSV = ROOT / "outputs" / "craig_intent_entry_answer_key_verified_recent_user_corrected_v0_1.csv"
OUT_CSV = ROOT / "outputs" / "craig_manual_gold_seed_batch1_v0_1.csv"
OUT_MD = ROOT / "outputs" / "craig_manual_gold_seed_batch1_v0_1.md"
OUT_IMAGE_NOTES_CSV = ROOT / "outputs" / "craig_user_image_manual_notes_batch1_v0_1.csv"
TRANSCRIPT_DIR = ROOT / "data" / "source" / "craig_youtube" / "transcripts"


KEYWORD_BUCKETS = {
    "HTF/큰그림": [
        "daily bias",
        "multi-time frame",
        "higher time frame",
        "4hour",
        "4 hour",
        "1 hour",
        "15 minute",
        "overall market",
    ],
    "트렌드라인": ["trend line", "trendline", "trend level", "break out of this trend"],
    "SR/플립": ["support", "resistance", "retest", "level", "underneath", "above", "below"],
    "FVG/OB": ["fvg", "fair value", "order block", "imbalance"],
    "딥바이/분할": ["dip by", "dip buy", "limit one", "limit two", "l1 bomb", "fib", "fibonacci"],
    "진입/체결": ["entry", "filled", "get filled", "position", "take a trade", "taking"],
    "리더자산": ["bitcoin", "ethereum", "btc", "eth"],
    "관리/청산": ["stop loss", "take profit", "target", "break even", "risk", "profit"],
}


# 사용자가 첨부 이미지 번호로 남긴 수동 메모다. 이미지 순서는 대체로 검수 queue와
# 비슷하지만 완전히 같지는 않으므로, row-level 반영은 아래 ROW_OVERRIDES에서 분리한다.
IMAGE_NOTES = [
    {
        "image_no": "14",
        "note_ko": "분할매수 전략. dip buy 1/2가 있는 박스로 봐야 하며 단일 FVG 진입으로 해석하면 안 됨.",
        "candidate_guess": "pBkAG3h2QRA 계열",
    },
    {
        "image_no": "15",
        "note_ko": "분할매수 전략. dip buy 1/2가 있는 박스로 봐야 함.",
        "candidate_guess": "pBkAG3h2QRA 계열",
    },
    {
        "image_no": "16",
        "note_ko": "분할매수 전략. dip buy 1/2가 있는 박스로 봐야 함.",
        "candidate_guess": "pBkAG3h2QRA 계열",
    },
    {
        "image_no": "18",
        "note_ko": "크레이그가 직접 표시한 SR flip 구간 박스. position box나 단순 FVG로 혼동하면 안 됨.",
        "candidate_guess": "Dec 2025 전후 SR flip 후보",
    },
    {
        "image_no": "19",
        "note_ko": "크레이그가 직접 표시한 SR flip 구간 박스일 가능성이 있으므로 수동 박스 의미를 우선 확인.",
        "candidate_guess": "Feb 2026 전후 SR/flip 후보",
    },
    {
        "image_no": "21",
        "note_ko": "좌측 파란 박스는 의미 없는 퍼센트 확인 박스. 포지션/존/근거로 쓰지 않음.",
        "candidate_guess": "KB4vL1x9ZcM 계열",
    },
    {
        "image_no": "25",
        "note_ko": "포지션 시작은 영상 7분57초 부근으로 확인 필요.",
        "candidate_guess": "a7x0yKL6jkI #2 가능성이 높음",
    },
    {
        "image_no": "31",
        "note_ko": "롱 포지션이 없었고 설명만 있었음. gold episode에서 제외해야 함.",
        "candidate_guess": "7j5JrAfmM-s #1 가능성이 높음",
    },
]


# row-level 반영. obsidian_queue_no 기준이다. 이미지 번호와 queue 번호가 완전히
# 같지는 않아서, 확실도가 낮은 것은 note_basis에 그대로 남긴다.
ROW_OVERRIDES = {
    "14": {
        "trade_status_final": "actual_trade_complex_split_entry",
        "setup_archetype_manual": "TCL_fib_dip_buy_split_entry",
        "visual_box_interpretation_ko": "dip buy 1/2를 포함한 분할 진입 계획 박스. 단일 FVG 진입으로 축약 금지.",
        "include_in_gold_episode": "yes_complex",
        "note_basis": "사용자 이미지 14-16 메모와 queue 14-16이 pBkAG3h2QRA 계열로 정렬됨",
    },
    "15": {
        "trade_status_final": "actual_trade_complex_split_entry",
        "setup_archetype_manual": "TCL_fib_dip_buy_split_entry",
        "visual_box_interpretation_ko": "dip buy 1/2를 포함한 분할 진입 계획 박스. 단일 FVG 진입으로 축약 금지.",
        "include_in_gold_episode": "yes_complex",
        "note_basis": "사용자 이미지 14-16 메모와 queue 14-16이 pBkAG3h2QRA 계열로 정렬됨",
    },
    "16": {
        "trade_status_final": "actual_trade_complex_split_entry",
        "setup_archetype_manual": "TCL_fib_dip_buy_split_entry",
        "visual_box_interpretation_ko": "dip buy 1/2를 포함한 분할 진입 계획 박스. 단일 FVG 진입으로 축약 금지.",
        "include_in_gold_episode": "yes_complex",
        "note_basis": "사용자 이미지 14-16 메모와 queue 14-16이 pBkAG3h2QRA 계열로 정렬됨",
    },
    "18": {
        "trade_status_final": "actual_trade_manual_sr_flip_context",
        "setup_archetype_manual": "manual_SR_flip_reaction_box",
        "visual_box_interpretation_ko": "수동 SR flip/reaction zone을 primary reaction zone으로 우선 해석.",
        "include_in_gold_episode": "yes_needs_box_role_check",
        "note_basis": "사용자 18/19번 SR flip 메모. 이미지 번호와 queue 번호가 일부 어긋날 수 있어 추가 확인 플래그 유지.",
    },
    "19": {
        "trade_status_final": "actual_trade_manual_sr_flip_context",
        "setup_archetype_manual": "manual_SR_flip_reaction_box",
        "visual_box_interpretation_ko": "수동 SR flip/reaction zone을 primary reaction zone으로 우선 해석.",
        "include_in_gold_episode": "yes_needs_box_role_check",
        "note_basis": "사용자 18/19번 SR flip 메모. 이미지 번호와 queue 번호가 일부 어긋날 수 있어 추가 확인 플래그 유지.",
    },
    "21": {
        "visual_exclusion_ko": "좌측 파란 박스는 퍼센트 측정용이라 포지션/존/근거로 사용하지 않음.",
        "include_in_gold_episode": "yes_ignore_left_blue_measure_box",
        "note_basis": "사용자 21번 이미지 메모",
    },
    "27": {
        "anchor_sec_final": "477",
        "anchor_time_final_mmss": "07:57",
        "trade_status_final": "actual_trade_start_time_user_corrected",
        "include_in_gold_episode": "yes_start_corrected",
        "note_basis": "사용자 25번 이미지 메모: 영상 7분57초 부근 포지션 시작. a7x0yKL6jkI #2로 매핑.",
    },
    "33": {
        "trade_status_final": "not_trade_explanation_only",
        "include_in_gold_episode": "no_explanation_only",
        "include_in_backtest_truth": "no",
        "setup_archetype_manual": "explanation_only_no_actual_position",
        "visual_box_interpretation_ko": "롱 포지션으로 보지 않음. 설명/가정용 박스 가능성이 높아 정답 거래에서 제외.",
        "note_basis": "사용자 31번 이미지 메모: 롱포지션 없고 설명만 있음. 2026-05-06 첫 후보로 매핑.",
    },
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]], fieldnames: list[str] | None = None) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    names = fieldnames or list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=names)
        writer.writeheader()
        writer.writerows(rows)


def mmss(seconds: float) -> str:
    sec = int(round(seconds))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def load_transcript(video_id: str) -> list[dict[str, object]]:
    path = TRANSCRIPT_DIR / f"{video_id}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def keyword_hits(video_id: str, center_sec: float, window: float = 90.0) -> str:
    rows = load_transcript(video_id)
    if not rows:
        return ""
    texts = []
    start = center_sec - window
    end = center_sec + window
    for item in rows:
        t = float(item.get("start", 0.0))
        if start <= t <= end:
            texts.append(str(item.get("text", "")))
    haystack = " ".join(texts).lower()
    hits = []
    for bucket, keywords in KEYWORD_BUCKETS.items():
        if any(word in haystack for word in keywords):
            hits.append(bucket)
    return ", ".join(hits)


def transcript_context_ko(hits: str) -> str:
    if not hits:
        return "주변 자막 키워드 없음 또는 자막 미확보"
    parts = hits.split(", ")
    return "주변 자막에서 " + ", ".join(parts) + " 관련 근거가 감지됨"


def sort_key(row: dict[str, str]) -> tuple[int, str]:
    q = row.get("obsidian_queue_no", "")
    return (int(q) if q.isdigit() else 999, row.get("answer_id", ""))


def main() -> None:
    rows = read_csv(IN_CSV)
    out_rows: list[dict[str, str]] = []

    extra_fields = [
        "anchor_sec_final",
        "anchor_time_final_mmss",
        "youtube_trade_link_final",
        "trade_status_final",
        "include_in_gold_episode",
        "include_in_backtest_truth",
        "setup_archetype_manual",
        "visual_box_interpretation_ko",
        "visual_exclusion_ko",
        "manual_note_basis_ko",
        "transcript_keyword_hits_ko",
        "transcript_context_summary_ko",
    ]

    for row in rows:
        new_row = dict(row)
        queue_no = new_row.get("obsidian_queue_no", "")
        anchor_sec = float(new_row.get("anchor_sec") or 0.0)
        final_sec = anchor_sec
        final_time = new_row.get("anchor_time_mmss", "")
        final_link = new_row.get("youtube_trade_link", "")

        new_row.update(
            {
                "anchor_sec_final": f"{anchor_sec:.0f}" if anchor_sec else "",
                "anchor_time_final_mmss": final_time,
                "youtube_trade_link_final": final_link,
                "trade_status_final": "actual_trade_candidate_needs_position_box",
                "include_in_gold_episode": "yes_pending_box_price",
                "include_in_backtest_truth": "yes_pending_price",
                "setup_archetype_manual": "",
                "visual_box_interpretation_ko": "",
                "visual_exclusion_ko": "",
                "manual_note_basis_ko": "",
            }
        )

        override = ROW_OVERRIDES.get(queue_no, {})
        if override:
            for key, value in override.items():
                if key == "note_basis":
                    new_row["manual_note_basis_ko"] = value
                else:
                    new_row[key] = value
            if "anchor_sec_final" in override:
                final_sec = float(override["anchor_sec_final"])
                final_time = override.get("anchor_time_final_mmss", mmss(final_sec))
                new_row["anchor_sec_final"] = f"{final_sec:.0f}"
                new_row["anchor_time_final_mmss"] = final_time
                new_row["youtube_trade_link_final"] = (
                    f"https://www.youtube.com/watch?v={new_row['video_id']}&t={int(final_sec)}s"
                )

        hits = keyword_hits(new_row.get("video_id", ""), final_sec)
        new_row["transcript_keyword_hits_ko"] = hits
        new_row["transcript_context_summary_ko"] = transcript_context_ko(hits)
        out_rows.append(new_row)

    out_rows.sort(key=sort_key)

    fieldnames = list(out_rows[0].keys())
    for field in extra_fields:
        if field not in fieldnames:
            fieldnames.append(field)
    write_csv(OUT_CSV, out_rows, fieldnames)
    write_csv(
        OUT_IMAGE_NOTES_CSV,
        IMAGE_NOTES,
        ["image_no", "candidate_guess", "note_ko"],
    )

    direction_overrides = [
        row
        for row in out_rows
        if row.get("direction_user_obsidian")
        and row.get("direction_user_obsidian") != row.get("direction_guess_original")
    ]
    excluded = [row for row in out_rows if row.get("include_in_gold_episode", "").startswith("no")]
    complex_rows = [row for row in out_rows if "complex" in row.get("include_in_gold_episode", "")]

    lines = [
        "# Craig Manual Gold Seed Batch1 v0.1",
        "",
        "Obsidian 방향 수정값과 사용자가 첨부 이미지에 남긴 수동 메모를 합친 gold episode 초안이다.",
        "",
        "## 요약",
        "",
        f"- 전체 검수 후보: {len(out_rows)}",
        f"- Obsidian 방향 override: {len(direction_overrides)}",
        f"- gold episode 제외: {len(excluded)}",
        f"- 분할/dip-buy 복합 진입으로 표시: {len(complex_rows)}",
        "",
        "## 이번에 반영한 핵심",
        "",
        "- long/short 방향은 `direction_final`을 우선 사용한다.",
        "- 첨부 이미지 14~16번은 단일 FVG가 아니라 dip buy 1/2가 있는 분할 진입 전략으로 표시했다.",
        "- 첨부 이미지 18~19번의 수동 박스는 SR flip/reaction zone일 수 있으므로 position box/FVG로 자동 오인하지 않도록 표시했다.",
        "- 첨부 이미지 21번의 좌측 파란 박스는 퍼센트 측정용으로 제외했다.",
        "- 첨부 이미지 25번은 a7x0yKL6jkI #2 후보에 매핑하고 영상 시작 시점을 07:57로 보정했다.",
        "- 첨부 이미지 31번은 7j5JrAfmM-s #1 후보에 매핑하고 설명-only로 제외했다.",
        "",
        "## 방향 수정 목록",
        "",
        "| queue | candidate | CSV | Obsidian | final |",
        "|---:|---|---|---|---|",
    ]
    for row in direction_overrides:
        lines.append(
            f"| {row.get('obsidian_queue_no')} | `{row.get('video_id')} #{row.get('trade_no_for_user')}` | "
            f"{row.get('direction_guess_original')} | {row.get('direction_user_obsidian')} | "
            f"**{row.get('direction_final')}** |"
        )

    lines.extend(
        [
            "",
            "## 수동 예외 메모",
            "",
            "| queue | candidate | 처리 | 근거 메모 |",
            "|---:|---|---|---|",
        ]
    )
    for row in out_rows:
        if row.get("manual_note_basis_ko"):
            lines.append(
                f"| {row.get('obsidian_queue_no')} | `{row.get('video_id')} #{row.get('trade_no_for_user')}` | "
                f"{row.get('include_in_gold_episode')} | {row.get('manual_note_basis_ko')} |"
            )

    lines.extend(
        [
            "",
            "## 이미지 번호 메모 원문 정리",
            "",
            "| image | 후보 매핑 추정 | 메모 |",
            "|---:|---|---|",
        ]
    )
    for note in IMAGE_NOTES:
        lines.append(f"| {note['image_no']} | {note['candidate_guess']} | {note['note_ko']} |")

    lines.extend(
        [
            "",
            "## 파일",
            "",
            f"- gold seed CSV: `{OUT_CSV.relative_to(ROOT)}`",
            f"- image notes CSV: `{OUT_IMAGE_NOTES_CSV.relative_to(ROOT)}`",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"rows={len(out_rows)}")
    print(f"direction_overrides={len(direction_overrides)}")
    print(f"excluded={len(excluded)}")
    print(f"out_csv={OUT_CSV}")
    print(f"out_md={OUT_MD}")


if __name__ == "__main__":
    main()
