#!/usr/bin/env python3
from __future__ import annotations

import csv
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LABELS = ROOT / "outputs/craig_transcript_observed_labels.csv"
INVENTORY = ROOT / "outputs/craig_live_trading_video_inventory.csv"
OUT_CSV = ROOT / "outputs/craig_all_live_take_candidate_queue.csv"
OUT_MD = ROOT / "outputs/craig_all_live_take_candidate_queue.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def parse_float(value: str) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def clean_text(value: str, max_len: int = 260) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def symbol_hint(row: dict[str, str]) -> str:
    text = f"{row.get('title','')} {row.get('evidence_text','')}".lower()
    if "solana" in text or " sol " in f" {text} " or "solusdt" in text:
        return "SOLUSDT"
    if "bitcoin" in text or " btc " in f" {text} " or "btcusdt" in text:
        return "BTCUSDT"
    if "ethereum" in text or " eth " in f" {text} " or "ethusdt" in text:
        return "ETHUSDT"
    return "unknown"


def main() -> None:
    labels = read_csv(LABELS)
    inventory = read_csv(INVENTORY)
    live = {row["video_id"]: row for row in inventory}

    by_video = {}
    for row in labels:
        if row.get("video_id") not in live:
            continue
        by_video.setdefault(row["video_id"], []).append(row)
    for rows in by_video.values():
        rows.sort(key=lambda r: parse_float(r.get("timestamp_start_sec", "")))

    out_rows = []
    for vid, rows in by_video.items():
        inv = live[vid]
        for row in rows:
            if row.get("observed_action") != "Take":
                continue
            ts = parse_float(row.get("timestamp_start_sec", ""))
            nearby_after = [
                r
                for r in rows
                if ts < parse_float(r.get("timestamp_start_sec", "")) <= ts + 420
                and r.get("observed_action") in {"Manage_BE_or_RiskReduce", "Exit_TP_or_Close", "Exit_Stop_or_Loss"}
            ]
            nearby_before = [
                r
                for r in rows
                if ts - 180 <= parse_float(r.get("timestamp_start_sec", "")) < ts
                and r.get("observed_action") in {"Missed", "Pass_or_Cooldown", "Context_Only", "Wait_Setup_Forming"}
            ]
            next_exit = next(
                (
                    r
                    for r in nearby_after
                    if r.get("observed_action") in {"Exit_TP_or_Close", "Exit_Stop_or_Loss"}
                ),
                {},
            )
            out_rows.append(
                {
                    "trade_candidate_id": f"{vid}_{int(round(ts))}",
                    "video_id": vid,
                    "title": inv.get("title", ""),
                    "url": inv.get("url", ""),
                    "market_date": inv.get("market_date_for_fetch", ""),
                    "market_date_status": inv.get("market_date_status", ""),
                    "timestamp_start_sec": row.get("timestamp_start_sec", ""),
                    "timestamp_url": row.get("timestamp_url", ""),
                    "observed_direction": row.get("observed_direction", ""),
                    "symbol_hint": symbol_hint(row),
                    "take_label_confidence": row.get("label_confidence_1_5", ""),
                    "take_features": row.get("observed_features", ""),
                    "nearby_context_before_count": len(nearby_before),
                    "nearby_management_after_count": len(
                        [r for r in nearby_after if r.get("observed_action") == "Manage_BE_or_RiskReduce"]
                    ),
                    "nearby_exit_after_count": len(
                        [
                            r
                            for r in nearby_after
                            if r.get("observed_action") in {"Exit_TP_or_Close", "Exit_Stop_or_Loss"}
                        ]
                    ),
                    "next_exit_action": next_exit.get("observed_action", ""),
                    "next_exit_time_sec": next_exit.get("timestamp_start_sec", ""),
                    "review_grade": "B" if "verified" in inv.get("market_date_status", "") else "C",
                    "needs_review": "symbol|event_split|entry_stop_target_frame",
                    "evidence_excerpt": clean_text(row.get("evidence_text", "")),
                }
            )

    out_rows.sort(key=lambda r: (r["market_date"], r["video_id"], parse_float(r["timestamp_start_sec"])))
    fieldnames = [
        "trade_candidate_id",
        "video_id",
        "title",
        "url",
        "market_date",
        "market_date_status",
        "timestamp_start_sec",
        "timestamp_url",
        "observed_direction",
        "symbol_hint",
        "take_label_confidence",
        "take_features",
        "nearby_context_before_count",
        "nearby_management_after_count",
        "nearby_exit_after_count",
        "next_exit_action",
        "next_exit_time_sec",
        "review_grade",
        "needs_review",
        "evidence_excerpt",
    ]
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    verified = sum(1 for r in out_rows if "verified" in r["market_date_status"])
    sol_hint = sum(1 for r in out_rows if r["symbol_hint"] == "SOLUSDT")
    lines = [
        "# Craig 전체 LIVE Take Candidate Queue",
        "",
        "이 파일은 LIVE 영상 전체의 Take 라벨을 trade 비교군 후보로 뽑은 1차 queue다. 가격/심볼/이벤트 분리가 끝난 최종 trade list는 아니다.",
        "",
        "## 요약",
        "",
        f"- LIVE Take 후보: {len(out_rows)}",
        f"- 시장 날짜 검증 완료 후보: {verified}/{len(out_rows)}",
        f"- SOLUSDT 힌트 후보: {sol_hint}/{len(out_rows)}",
        "",
        "## 사용법",
        "",
        "1. `review_grade=B`부터 프레임으로 심볼, entry, stop, target을 확인한다.",
        "2. 같은 구간에 recap와 fresh entry가 섞이면 event split한다.",
        "3. A/B/C 등급을 부여한 뒤 모델 후보와 비교한다.",
        "",
        "CSV: `outputs/craig_all_live_take_candidate_queue.csv`",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"take_candidates={len(out_rows)} output={OUT_CSV}")


if __name__ == "__main__":
    main()
