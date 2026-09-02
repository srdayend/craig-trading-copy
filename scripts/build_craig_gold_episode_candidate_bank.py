#!/usr/bin/env python3
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTEXT = ROOT / "outputs" / "craig_trade_context_review.csv"
TAKES = ROOT / "outputs" / "craig_all_live_take_candidate_queue.csv"
FRAMES_ROOT = ROOT / "data" / "source" / "craig_frames" / "seed_frame_review" / "craig_seed_frame_review"
OUT_CSV = ROOT / "outputs" / "craig_gold_episode_candidate_bank_v0_1.csv"
OUT_MD = ROOT / "outputs" / "craig_gold_episode_candidate_bank_v0_1.md"
OUT_BOX_REQUEST = ROOT / "outputs" / "craig_position_box_request_list_v0_1.csv"


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


def parse_float(value: str) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def clean(value: str, limit: int = 180) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def frame_dirs() -> list[Path]:
    if not FRAMES_ROOT.exists():
        return []
    return [p for p in FRAMES_ROOT.iterdir() if p.is_dir()]


def map_frames() -> dict[str, list[Path]]:
    mapping: dict[str, list[Path]] = defaultdict(list)
    for folder in frame_dirs():
        name = folder.name
        parts = name.split("_")
        if len(parts) < 4:
            continue
        video_id = parts[1]
        try:
            sec = int(parts[2])
        except ValueError:
            continue
        action = parts[3]
        if action != "Take":
            continue
        mapping[video_id].append(folder)
    return mapping


def nearest_frame(video_frames: dict[str, list[Path]], video_id: str, ts: float) -> tuple[str, str, str]:
    best: tuple[float, Path] | None = None
    for folder in video_frames.get(video_id, []):
        parts = folder.name.split("_")
        sec = float(parts[2])
        delta = abs(sec - ts)
        if best is None or delta < best[0]:
            best = (delta, folder)
    if best is None or best[0] > 35:
        return "none", "", ""
    folder = best[1]
    event = next(folder.glob("event_*.jpg"), None)
    sheet = next(folder.glob("*_sheet.jpg"), None)
    return "available", str(event or ""), str(sheet or "")


def numeric(row: dict[str, str], field: str) -> int:
    try:
        return int(float(row.get(field, "") or 0))
    except Exception:
        return 0


def evidence_score(row: dict[str, str], take: dict[str, str], frame_status: str) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if row["htf_evidence_level"] == "strong":
        score += 18
        reasons.append("HTF근거강함")
    elif row["htf_evidence_level"] == "moderate":
        score += 12
        reasons.append("HTF근거보통")
    if row["ltf_entry_quality"] == "high":
        score += 18
        reasons.append("1분진입근거강함")
    elif row["ltf_entry_quality"] == "medium":
        score += 10
        reasons.append("1분진입근거보통")
    if row["trendline_evidence_level"] != "none":
        score += 10
        reasons.append("추세선맥락")
    if row["sr_flip_evidence_level"] != "none":
        score += 10
        reasons.append("SR반응")
    if numeric(row, "liquidity_target_hits") > 0:
        score += 8
        reasons.append("유동성/타겟")
    if numeric(row, "risk_management_hits") > 0:
        score += 8
        reasons.append("손절/관리발화")
    if numeric(row, "pair_market_hits") > 0:
        score += 5
        reasons.append("페어/시장맥락")
    if frame_status == "available":
        score += 12
        reasons.append("프레임있음")
    if row.get("observed_direction") in {"long", "short"}:
        score += 8
        reasons.append("방향라벨있음")
    if take.get("next_exit_action"):
        score += 4
        reasons.append("exit연결있음")
    return score, reasons


def grade(score: int, row: dict[str, str], frame_status: str) -> str:
    if score >= 74 and frame_status == "available" and row["ltf_entry_quality"] == "high":
        return "A_candidate_position_box_needed"
    if score >= 62:
        return "B_candidate_good_context"
    if score >= 48:
        return "C_candidate_context_only"
    return "D_reference_only"


def model_lesson(row: dict[str, str]) -> str:
    archetype = row["primary_trade_archetype"]
    tags = set((row.get("model_gap_tags") or "").split("|"))
    lessons = []
    if archetype == "HTF_trendline_reaction":
        lessons.append("HTF 추세선/대각선 반응을 primary reaction zone으로 먼저 만든다")
    if archetype == "HTF_SR_flip_reaction":
        lessons.append("SR flip 또는 반복 SR 박스를 primary reaction zone으로 먼저 만든다")
    if "FVG_role_entry_vs_target" in tags:
        lessons.append("FVG를 entry zone인지 target draw인지 분리한다")
    if "real_HTF_target_not_synthetic_4R" in tags:
        lessons.append("TP는 synthetic 4R보다 실제 HTF draw를 우선한다")
    if "time_as_volatility_context" in tags:
        lessons.append("시간은 hard gate가 아니라 변동성 context로만 쓴다")
    if "state_after_loss_or_goal" in tags:
        lessons.append("손실 후/목표 달성 후 state를 따로 둔다")
    return " / ".join(lessons[:4])


def missing_for_user(row: dict[str, str], frame_status: str) -> str:
    missing = ["position_box_방향_entry_SL_TP"]
    if row.get("observed_direction") not in {"long", "short"}:
        missing.append("방향확인")
    if frame_status != "available":
        missing.append("맥락프레임")
    if row["trendline_evidence_level"] == "none" and row["primary_trade_archetype"] == "HTF_trendline_reaction":
        missing.append("HTF추세선프레임")
    return "|".join(missing)


def main() -> None:
    context_rows = read_csv(CONTEXT)
    take_rows = {row["trade_candidate_id"]: row for row in read_csv(TAKES)}
    video_frames = map_frames()
    out_rows: list[dict[str, str]] = []
    request_rows: list[dict[str, str]] = []

    for row in context_rows:
        take = take_rows.get(row["trade_candidate_id"], {})
        ts = parse_float(row["timestamp_start_sec"])
        frame_status, event_frame, sheet_frame = nearest_frame(video_frames, row["video_id"], ts)
        score, reasons = evidence_score(row, take, frame_status)
        candidate_grade = grade(score, row, frame_status)
        out = {
            "gold_candidate_id": f"gold_{len(out_rows)+1:02d}",
            "candidate_grade": candidate_grade,
            "priority_score": str(score),
            "priority_reasons": "|".join(reasons),
            "trade_candidate_id": row["trade_candidate_id"],
            "video_id": row["video_id"],
            "market_date": row["market_date"],
            "timestamp_start_sec": row["timestamp_start_sec"],
            "timestamp_url": row["timestamp_url"],
            "title": row["title"],
            "observed_direction": row["observed_direction"],
            "symbol_hint": row["symbol_hint"],
            "primary_trade_archetype": row["primary_trade_archetype"],
            "htf_evidence_level": row["htf_evidence_level"],
            "trendline_evidence_level": row["trendline_evidence_level"],
            "sr_flip_evidence_level": row["sr_flip_evidence_level"],
            "ltf_entry_quality": row["ltf_entry_quality"],
            "management_specificity": row["management_specificity"],
            "setup_components_ko": row["setup_components_ko"],
            "model_lesson": model_lesson(row),
            "frame_status": frame_status,
            "event_frame": event_frame,
            "sheet_frame": sheet_frame,
            "next_exit_action": take.get("next_exit_action", ""),
            "next_exit_time_sec": take.get("next_exit_time_sec", ""),
            "position_box_status": "excluded_user_will_supply",
            "needs_user_image_or_check": missing_for_user(row, frame_status),
            "evidence_keywords": row.get("compact_evidence_terms", ""),
            "short_note": clean(take.get("evidence_excerpt", ""), 160),
        }
        out_rows.append(out)
        if candidate_grade in {"A_candidate_position_box_needed", "B_candidate_good_context"}:
            request_rows.append(
                {
                    "gold_candidate_id": out["gold_candidate_id"],
                    "trade_candidate_id": out["trade_candidate_id"],
                    "market_date": out["market_date"],
                    "timestamp_url": out["timestamp_url"],
                    "observed_direction": out["observed_direction"],
                    "primary_trade_archetype": out["primary_trade_archetype"],
                    "frame_status": out["frame_status"],
                    "event_frame": out["event_frame"],
                    "what_to_attach_or_confirm": out["needs_user_image_or_check"],
                    "why_this_matters": "이 후보는 Craig 모사 룰의 기준 샘플로 쓸 수 있지만 position box 가격/방향 확정이 필요하다.",
                }
            )

    out_rows.sort(key=lambda r: (-int(r["priority_score"]), r["market_date"], r["timestamp_start_sec"]))
    for idx, row in enumerate(out_rows, 1):
        row["gold_candidate_id"] = f"gold_{idx:02d}"
    id_map = {row["trade_candidate_id"]: row["gold_candidate_id"] for row in out_rows}
    for request in request_rows:
        request["gold_candidate_id"] = id_map.get(request["trade_candidate_id"], request["gold_candidate_id"])
    request_rows.sort(key=lambda r: id_map.get(r["trade_candidate_id"], r["gold_candidate_id"]))

    write_csv(OUT_CSV, out_rows)
    write_csv(OUT_BOX_REQUEST, request_rows)

    grade_counts = Counter(row["candidate_grade"] for row in out_rows)
    archetype_counts = Counter(row["primary_trade_archetype"] for row in out_rows)
    lines = [
        "# Craig Golden Episode Candidate Bank v0.1",
        "",
        "position box 확정은 이번 단계에서 제외하고, Craig 모사를 위한 HTF/셋업/맥락 후보를 최대한 넓게 만든 결과다.",
        "",
        "## 요약",
        "",
        f"- 전체 후보: {len(out_rows)}",
        f"- A 후보(position box만 붙이면 gold seed 가능): {grade_counts.get('A_candidate_position_box_needed', 0)}",
        f"- B 후보(맥락 좋음, 추가 프레임/방향 확인 필요): {grade_counts.get('B_candidate_good_context', 0)}",
        f"- C 후보(context only): {grade_counts.get('C_candidate_context_only', 0)}",
        f"- 사용자 position box 확인 요청 후보: {len(request_rows)}",
        "",
        "## 분류",
        "",
        "| 등급 | 개수 | 의미 |",
        "|---|---:|---|",
    ]
    for key, value in grade_counts.most_common():
        meaning = {
            "A_candidate_position_box_needed": "HTF/LTF/프레임 근거가 좋아 position box만 붙이면 gold seed 가능",
            "B_candidate_good_context": "맥락은 좋지만 방향/프레임/entry detail 보완 필요",
            "C_candidate_context_only": "학습 참고는 가능하지만 정답지로는 부족",
            "D_reference_only": "현재는 참고용",
        }.get(key, "")
        lines.append(f"| `{key}` | {value} | {meaning} |")
    lines.extend(["", "## Archetype 분포", "", "| archetype | 개수 |", "|---|---:|"])
    for key, value in archetype_counts.most_common():
        lines.append(f"| `{key}` | {value} |")
    lines.extend(
        [
            "",
            "## 상위 후보",
            "",
            "| id | date | time | direction | archetype | score | frame | 확인 필요 |",
            "|---|---|---:|---|---|---:|---|---|",
        ]
    )
    for row in out_rows[:18]:
        lines.append(
            f"| `{row['gold_candidate_id']}` | {row['market_date']} | {row['timestamp_start_sec']} | "
            f"`{row['observed_direction']}` | `{row['primary_trade_archetype']}` | {row['priority_score']} | "
            f"`{row['frame_status']}` | `{row['needs_user_image_or_check']}` |"
        )
    lines.extend(
        [
            "",
            "## 이 후보 bank를 쓰는 법",
            "",
            "1. A 후보부터 사용자가 position box 방향/entry/SL/TP를 붙인다.",
            "2. 붙은 후보는 `gold episode`로 승격한다.",
            "3. 모델 v0.3은 gold episode와 같은 HTF zone, 같은 방향, 같은 LTF trigger를 냈는지 먼저 비교한다.",
            "4. 백테스트는 gold episode 일치도가 오른 뒤 다시 실행한다.",
            "",
            "## 파일",
            "",
            f"- 후보 bank CSV: `{OUT_CSV.relative_to(ROOT)}`",
            f"- position box 확인 요청 CSV: `{OUT_BOX_REQUEST.relative_to(ROOT)}`",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"candidates={len(out_rows)} requests={len(request_rows)} output={OUT_CSV}")
    print(f"report={OUT_MD}")


if __name__ == "__main__":
    main()
