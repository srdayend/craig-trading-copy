#!/usr/bin/env python3
from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_CSV = ROOT / "outputs" / "craig_intent_entry_answer_key_verified_recent_v0_1.csv"
OBSIDIAN_MD = ROOT / "outputs" / "craig_intent_entry_user_check_queue_verified_recent_v0_1.md"
OUT_CSV = ROOT / "outputs" / "craig_intent_entry_answer_key_verified_recent_user_corrected_v0_1.csv"
OUT_OVERRIDES = ROOT / "outputs" / "craig_obsidian_direction_overrides_v0_1.csv"
OUT_MD = ROOT / "outputs" / "craig_obsidian_direction_overrides_v0_1.md"


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


def clean_direction(value: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", value or "", flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip().lower()
    if text in {"long", "short", "unknown"}:
        return text
    return text


def parse_obsidian_table(path: Path) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        if not line.startswith("|") or "`" not in line or "YouTube" not in line:
            continue
        cols = [col.strip() for col in line.strip().strip("|").split("|")]
        if len(cols) < 7:
            continue
        queue_no = re.sub(r"\D", "", cols[0])
        candidate_match = re.search(r"`([^`]+)`", cols[3])
        if not candidate_match:
            continue
        candidate_key = candidate_match.group(1)
        out[candidate_key] = {
            "queue_no": queue_no,
            "candidate_key": candidate_key,
            "obsidian_direction": clean_direction(cols[5]),
            "obsidian_row": line,
        }
    return out


def main() -> None:
    rows = read_csv(SOURCE_CSV)
    obsidian = parse_obsidian_table(OBSIDIAN_MD)
    corrected: list[dict[str, str]] = []
    overrides: list[dict[str, str]] = []

    for row in rows:
        candidate_key = f"{row['video_id']} #{row['trade_no_for_user']}"
        obs = obsidian.get(candidate_key, {})
        obsidian_direction = obs.get("obsidian_direction", "")
        original_direction = row.get("direction_guess", "")
        final_direction = obsidian_direction or original_direction
        changed = (
            "yes"
            if obsidian_direction and obsidian_direction.lower() != original_direction.lower()
            else "no"
        )
        new_row = dict(row)
        new_row["direction_guess_original"] = original_direction
        new_row["direction_user_obsidian"] = obsidian_direction
        new_row["direction_final"] = final_direction
        new_row["direction_final_source"] = "obsidian_manual" if obsidian_direction else "csv_original"
        new_row["obsidian_queue_no"] = obs.get("queue_no", "")
        corrected.append(new_row)
        if changed == "yes":
            overrides.append(
                {
                    "obsidian_queue_no": obs.get("queue_no", ""),
                    "candidate_key": candidate_key,
                    "answer_id": row.get("answer_id", ""),
                    "market_date": row.get("market_date", ""),
                    "title": row.get("title", ""),
                    "anchor_time_mmss": row.get("anchor_time_mmss", ""),
                    "csv_direction": original_direction,
                    "obsidian_direction": obsidian_direction,
                    "youtube_trade_link": row.get("youtube_trade_link", ""),
                }
            )

    write_csv(OUT_CSV, corrected)
    write_csv(OUT_OVERRIDES, overrides)

    lines = [
        "# Obsidian Direction Overrides v0.1",
        "",
        "사용자가 Obsidian에서 직접 고친 long/short 방향값을 CSV와 비교한 결과다.",
        "",
        f"- 전체 verified 후보: {len(corrected)}",
        f"- 방향 override: {len(overrides)}",
        "",
        "| queue | candidate | CSV | Obsidian | 시점 | 링크 |",
        "|---:|---|---|---|---:|---|",
    ]
    for row in overrides:
        lines.append(
            f"| {row['obsidian_queue_no']} | `{row['candidate_key']}` | "
            f"{row['csv_direction']} | **{row['obsidian_direction']}** | "
            f"{row['anchor_time_mmss']} | [YouTube]({row['youtube_trade_link']}) |"
        )
    lines.extend(
        [
            "",
            "## 다음 처리",
            "",
            "- 이후 gold episode 생성에는 `direction_final`을 사용한다.",
            "- 원본 CSV의 `direction_guess`는 유지하고, 사용자의 수정값은 별도 컬럼으로 보존한다.",
            "",
            "## 파일",
            "",
            f"- corrected CSV: `{OUT_CSV.relative_to(ROOT)}`",
            f"- override CSV: `{OUT_OVERRIDES.relative_to(ROOT)}`",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"corrected_rows={len(corrected)}")
    print(f"overrides={len(overrides)}")
    print(f"output={OUT_CSV}")
    print(f"report={OUT_MD}")


if __name__ == "__main__":
    main()
