#!/usr/bin/env python3
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ATOMIC = ROOT / "outputs" / "craig_transcript_atomic_labels.csv"
INVENTORY = ROOT / "outputs" / "craig_live_trading_video_inventory.csv"
FRAMES_ROOT = ROOT / "data" / "source" / "craig_frames" / "seed_frame_review" / "craig_seed_frame_review"
OUT_CSV = ROOT / "outputs" / "craig_expanded_trade_episode_bank_v0_1.csv"
OUT_MD = ROOT / "outputs" / "craig_expanded_trade_episode_bank_v0_1.md"
OUT_GAPS = ROOT / "outputs" / "craig_expanded_trade_episode_video_gaps_v0_1.csv"


ENTRY_RE = re.compile(
    r"\b(i[' ]?m|we[' ]?re|we are)\s+in\b|"
    r"\b(entry|entered|entering|taking an? .*position|take .*position|"
    r"filled here|got filled|get (?:us )?filled|trade number|next trade|"
    r"short position|long position)\b",
    re.IGNORECASE,
)
RECAP_RE = re.compile(
    r"\b(first|second|third|fourth|fifth|sixth|last|next)\s+trade\b|"
    r"\btrade number\b|"
    r"\bfull loss\b|\bbreak even trade\b|\bcontained loss\b|"
    r"\blocked in\b|\btake profit\b|\ball out\b|\bout for\b",
    re.IGNORECASE,
)
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
}


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


def clean(value: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def live_inventory() -> dict[str, dict[str, str]]:
    rows = read_csv(INVENTORY)
    return {row["video_id"]: row for row in rows}


def title_expected_count(title: str) -> str:
    text = title.lower()
    match = re.search(r"\b(?:in|with)\s+(\d+)\s+trades\b", text)
    if match:
        return match.group(1)
    match = re.search(r"\b(\d+)\s+trades\b", text)
    if match:
        return match.group(1)
    return ""


def frame_events() -> dict[str, list[dict[str, str | float]]]:
    out: dict[str, list[dict[str, str | float]]] = defaultdict(list)
    if not FRAMES_ROOT.exists():
        return out
    for folder in FRAMES_ROOT.iterdir():
        if not folder.is_dir():
            continue
        parts = folder.name.split("_")
        if len(parts) < 4:
            continue
        try:
            video_id = parts[1]
            ts = float(parts[2])
            action = "_".join(parts[3:])
        except Exception:
            continue
        event = next(folder.glob("event_*.jpg"), None)
        sheet = next(folder.glob("*_sheet.jpg"), None)
        out[video_id].append(
            {
                "timestamp_sec": ts,
                "action": action,
                "folder": str(folder),
                "event_frame": str(event or ""),
                "sheet_frame": str(sheet or ""),
            }
        )
    for items in out.values():
        items.sort(key=lambda x: float(x["timestamp_sec"]))
    return out


def nearest_frame(frames: dict[str, list[dict[str, str | float]]], video_id: str, ts: float) -> dict[str, str | float]:
    best = None
    for frame in frames.get(video_id, []):
        delta = abs(float(frame["timestamp_sec"]) - ts)
        if best is None or delta < best[0]:
            best = (delta, frame)
    if best is None or best[0] > 45:
        return {"frame_status": "none", "event_frame": "", "sheet_frame": "", "frame_action": "", "frame_delta_sec": ""}
    frame = best[1]
    return {
        "frame_status": "available",
        "event_frame": str(frame["event_frame"]),
        "sheet_frame": str(frame["sheet_frame"]),
        "frame_action": str(frame["action"]),
        "frame_delta_sec": f"{best[0]:.1f}",
    }


def anchor_kind(row: dict[str, str]) -> str:
    event_type = row.get("source_event_type", "")
    text = row.get("evidence_text", "")
    action = row.get("observed_action", "")
    if event_type == "ENTRY" or action == "Take":
        return "explicit_entry"
    if event_type == "SETUP_TRIGGER" and ENTRY_RE.search(text):
        return "setup_implied_entry"
    if event_type in {"TARGET_TP", "STOP_RISK", "BREAKEVEN"} and RECAP_RE.search(text):
        return "recap_or_management_implied_trade"
    return ""


def merge_direction(values: list[str]) -> str:
    counts = Counter(v for v in values if v in {"long", "short"})
    if not counts:
        return "unknown"
    if len(counts) == 1:
        return counts.most_common(1)[0][0]
    top = counts.most_common()
    return top[0][0] if top[0][1] > top[1][1] else "mixed"


def episode_grade(row: dict[str, str]) -> str:
    explicit = int(row["explicit_entry_events"])
    setup = int(row["setup_implied_entry_events"])
    frame = row["frame_status"] == "available"
    htf = int(row["htf_context_events"])
    trigger = int(row["setup_trigger_events"])
    risk = int(row["stop_risk_events"])
    target = int(row["target_tp_events"])
    if explicit and frame and (htf or trigger) and (risk or target):
        return "A_expanded_strong"
    if explicit or setup:
        return "B_expanded_entry_likely"
    if int(row["recap_implied_events"]):
        return "C_recap_inferred"
    return "D_context_only"


def cluster_video_rows(rows: list[dict[str, str]]) -> list[list[dict[str, str]]]:
    anchors = []
    for row in rows:
        kind = anchor_kind(row)
        if not kind:
            continue
        anchor = dict(row)
        anchor["_anchor_kind"] = kind
        anchor["_time"] = parse_float(row.get("timestamp_sec", ""))
        anchors.append(anchor)
    anchors.sort(key=lambda r: float(r["_time"]))

    clusters: list[list[dict[str, str]]] = []
    for anchor in anchors:
        ts = float(anchor["_time"])
        if not clusters:
            clusters.append([anchor])
            continue
        last_ts = max(float(x["_time"]) for x in clusters[-1])
        # Entry/setup duplicates inside the same narrated decision often repeat
        # within 90-120 seconds. Recap events get a wider merge window.
        window = 140 if anchor["_anchor_kind"] != "explicit_entry" else 95
        if ts - last_ts <= window:
            clusters[-1].append(anchor)
        else:
            clusters.append([anchor])
    return clusters


def support_events(all_rows: list[dict[str, str]], start: float, end: float) -> list[dict[str, str]]:
    return [row for row in all_rows if start <= parse_float(row.get("timestamp_sec", "")) <= end]


def build_episode(
    video_id: str,
    inventory_row: dict[str, str],
    cluster: list[dict[str, str]],
    all_rows: list[dict[str, str]],
    idx: int,
    frames: dict[str, list[dict[str, str | float]]],
) -> dict[str, str]:
    start = min(float(row["_time"]) for row in cluster)
    end = max(float(row["_time"]) for row in cluster)
    support = support_events(all_rows, max(0, start - 120), end + 240)
    event_counts = Counter(row.get("source_event_type", "") for row in support)
    anchor_counts = Counter(row["_anchor_kind"] for row in cluster)
    direction = merge_direction([row.get("observed_direction", "") for row in support])
    features = sorted(
        {
            item
            for row in support
            for item in (row.get("observed_features", "") or "").split("|")
            if item
        }
    )
    frame = nearest_frame(frames, video_id, start)
    first_text = next((row.get("evidence_text", "") for row in cluster if row.get("evidence_text")), "")
    row = {
        "expanded_episode_id": f"{video_id}_ep{idx:02d}_{int(round(start))}",
        "video_id": video_id,
        "market_date": inventory_row.get("market_date_for_fetch", ""),
        "market_date_status": inventory_row.get("market_date_status", ""),
        "title": inventory_row.get("title", ""),
        "url": inventory_row.get("url", ""),
        "episode_start_sec": f"{start:.2f}",
        "episode_end_sec": f"{end:.2f}",
        "timestamp_url": f"https://www.youtube.com/watch?v={video_id}&t={int(start)}s",
        "episode_anchor_kind": "|".join(sorted(anchor_counts)),
        "explicit_entry_events": str(anchor_counts.get("explicit_entry", 0)),
        "setup_implied_entry_events": str(anchor_counts.get("setup_implied_entry", 0)),
        "recap_implied_events": str(anchor_counts.get("recap_or_management_implied_trade", 0)),
        "observed_direction": direction,
        "features": "|".join(features),
        "htf_context_events": str(event_counts.get("HTF_CONTEXT", 0)),
        "setup_trigger_events": str(event_counts.get("SETUP_TRIGGER", 0)),
        "stop_risk_events": str(event_counts.get("STOP_RISK", 0)),
        "target_tp_events": str(event_counts.get("TARGET_TP", 0)),
        "breakeven_events": str(event_counts.get("BREAKEVEN", 0)),
        "pass_missed_events": str(event_counts.get("PASS_MISSED_DISCIPLINE", 0)),
        "supporting_event_count": str(len(support)),
        "position_box_status": "excluded_user_will_supply",
        "needs_user_check": "direction_entry_SL_TP_box",
        "evidence_excerpt": clean(first_text),
        **{k: str(v) for k, v in frame.items()},
    }
    row["expanded_grade"] = episode_grade(row)
    return row


def recap_expected_counts(rows: list[dict[str, str]], title: str) -> str:
    counts = []
    title_count = title_expected_count(title)
    if title_count:
        counts.append(int(title_count))
    joined = " ".join(row.get("evidence_text", "") for row in rows).lower()
    for match in re.finditer(r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+total trades\b", joined):
        raw = match.group(1)
        counts.append(int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw, 0))
    for match in re.finditer(r"\btwo losses and two wins\b", joined):
        counts.append(4)
    for match in re.finditer(r"\btwo full losses, two full break evens, and then two decent trades\b", joined):
        counts.append(6)
    return str(max(counts)) if counts else ""


def main() -> None:
    inventory = live_inventory()
    live_ids = set(inventory)
    atomic = [row for row in read_csv(ATOMIC) if row.get("video_id") in live_ids]
    by_video: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in atomic:
        by_video[row["video_id"]].append(row)
    for rows in by_video.values():
        rows.sort(key=lambda r: parse_float(r.get("timestamp_sec", "")))
    frames = frame_events()

    episodes: list[dict[str, str]] = []
    gap_rows: list[dict[str, str]] = []
    for video_id, inv in inventory.items():
        rows = by_video.get(video_id, [])
        clusters = cluster_video_rows(rows)
        video_eps = []
        for idx, cluster in enumerate(clusters, 1):
            ep = build_episode(video_id, inv, cluster, rows, idx, frames)
            video_eps.append(ep)
        episodes.extend(video_eps)
        expected = recap_expected_counts(rows, inv.get("title", ""))
        gap_rows.append(
            {
                "video_id": video_id,
                "market_date": inv.get("market_date_for_fetch", ""),
                "title": inv.get("title", ""),
                "title_or_recap_expected_trades": expected,
                "take_labels": inv.get("observed_take_labels", ""),
                "expanded_episode_candidates": str(len(video_eps)),
                "explicit_or_setup_candidates": str(
                    sum(
                        1
                        for ep in video_eps
                        if int(ep["explicit_entry_events"]) + int(ep["setup_implied_entry_events"]) > 0
                    )
                ),
                "recap_only_candidates": str(sum(1 for ep in video_eps if ep["episode_anchor_kind"] == "recap_or_management_implied_trade")),
                "gap_note": (
                    "expanded_below_expected_check_video"
                    if expected and len(video_eps) < int(expected)
                    else "expanded_at_or_above_known_count"
                    if expected
                    else "no_title_or_recap_expected_count"
                ),
                "url": inv.get("url", ""),
            }
        )

    episodes.sort(key=lambda r: (r["market_date"], r["video_id"], parse_float(r["episode_start_sec"])))
    write_csv(OUT_CSV, episodes)
    write_csv(OUT_GAPS, gap_rows)

    grade_counts = Counter(row["expanded_grade"] for row in episodes)
    anchor_counts = Counter(row["episode_anchor_kind"] for row in episodes)
    with_frame = sum(1 for row in episodes if row["frame_status"] == "available")
    explicit_setup = sum(
        1 for row in episodes if int(row["explicit_entry_events"]) + int(row["setup_implied_entry_events"]) > 0
    )
    lines = [
        "# Craig Expanded Trade Episode Bank v0.1",
        "",
        "이 파일은 기존 `Take` 36개보다 넓은 분모다. 실제 전체 trade 확정 리스트가 아니라, 자막/프레임에서 trade 가능성이 보이는 episode 후보 bank다.",
        "",
        "## 왜 36개보다 많은가",
        "",
        "- 기존 36개는 `observed_action=Take`만 모은 좁은 후보였다.",
        "- 실제 영상에는 진입 장면이 `Take`라고 라벨링되지 않고, 관리/청산/리캡 문장 안에 숨어 있는 경우가 많다.",
        "- 그래서 이번 bank는 `ENTRY`, entry 암시 setup, 관리/청산으로 역추론되는 trade를 함께 묶었다.",
        "",
        "## 요약",
        "",
        f"- expanded episode 후보: {len(episodes)}",
        f"- explicit/setup entry 후보: {explicit_setup}",
        f"- 프레임 근처 확인 가능 후보: {with_frame}",
        "",
        "## 등급 분포",
        "",
        "| 등급 | 개수 | 의미 |",
        "|---|---:|---|",
    ]
    meanings = {
        "A_expanded_strong": "명시 진입 + 프레임 + HTF/setup + risk/target 근거가 같이 있음",
        "B_expanded_entry_likely": "명시 진입 또는 entry 암시가 있음",
        "C_recap_inferred": "관리/청산/리캡으로 trade가 있었음을 역추론",
        "D_context_only": "참고용",
    }
    for key, value in grade_counts.most_common():
        lines.append(f"| `{key}` | {value} | {meanings.get(key, '')} |")
    lines.extend(["", "## Anchor 종류", "", "| anchor | 개수 |", "|---|---:|"])
    for key, value in anchor_counts.most_common():
        lines.append(f"| `{key}` | {value} |")
    lines.extend(
        [
            "",
            "## 영상별 gap 체크",
            "",
            "| date | video | expected | Take | expanded | gap note |",
            "|---|---|---:|---:|---:|---|",
        ]
    )
    for gap in sorted(gap_rows, key=lambda r: (r["market_date"], r["video_id"])):
        if not gap["title_or_recap_expected_trades"] and int(gap["expanded_episode_candidates"]) == 0:
            continue
        lines.append(
            f"| {gap['market_date']} | `{gap['video_id']}` | {gap['title_or_recap_expected_trades'] or ''} | "
            f"{gap['take_labels']} | {gap['expanded_episode_candidates']} | `{gap['gap_note']}` |"
        )
    lines.extend(
        [
            "",
            "## 상위 확인 방식",
            "",
            "1. `A_expanded_strong`부터 position box를 붙여 gold episode로 승격한다.",
            "2. `B_expanded_entry_likely`는 방향/entry frame을 확인한다.",
            "3. `C_recap_inferred`는 실제 진입 장면이 영상에 없을 수 있으므로, 결과/관리 샘플로만 쓴다.",
            "",
            "## 파일",
            "",
            f"- expanded CSV: `{OUT_CSV.relative_to(ROOT)}`",
            f"- 영상별 gap CSV: `{OUT_GAPS.relative_to(ROOT)}`",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"episodes={len(episodes)} explicit_setup={explicit_setup} frames={with_frame}")
    print(f"output={OUT_CSV}")
    print(f"report={OUT_MD}")


if __name__ == "__main__":
    main()
