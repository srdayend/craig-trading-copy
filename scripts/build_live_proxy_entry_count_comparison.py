#!/usr/bin/env python3
from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "outputs/craig_live_trading_video_inventory.csv"
TRADES = ROOT / "outputs/sol_craig_rule_backtest_trades.csv"
OUT_CSV = ROOT / "outputs/craig_live_recent_proxy_entry_count_comparison.csv"
OUT_MD = ROOT / "outputs/craig_live_recent_proxy_entry_count_comparison.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def is_opposing(row: dict[str, str], field: str) -> bool:
    value = row.get(field)
    return value in {"long", "short"} and value != row.get("direction")


def strict_v1_overlay(row: dict[str, str]) -> bool:
    try:
        displacement = float(row.get("displacement_score") or 0)
        aligned = int(row.get("aligned_zones") or 0)
        against = int(row.get("against_zones") or 0)
    except Exception:
        return False
    return all(
        [
            row.get("session_phase") in {"ny_open", "power_hour"},
            row.get("htf_bias") == row.get("direction"),
            not is_opposing(row, "leader_bias"),
            not is_opposing(row, "htf_bias"),
            displacement >= 2.4,
            row.get("entry_model") != "market_fill",
            "synthetic" not in (row.get("target_type") or ""),
            aligned > 0,
            against == 0,
        ]
    )


def in_craig_active_window(timestamp_ny: str) -> bool:
    # Craig can still trade after 10:30 if the open thesis is actively resolving.
    # This wider window is not an auto-entry permission; it is a review queue.
    hhmm = (timestamp_ny or "")[11:16]
    return "09:30" <= hhmm <= "11:00" or "14:00" <= hhmm <= "15:30"


def craig_context_review_candidate(row: dict[str, str]) -> bool:
    try:
        displacement = float(row.get("displacement_score") or 0)
        aligned = int(row.get("aligned_zones") or 0)
    except Exception:
        return False
    return all(
        [
            in_craig_active_window(row.get("timestamp_ny", "")),
            displacement >= 1.75,
            aligned > 0,
            row.get("choch_type") not in {"", "none"},
        ]
    )


def main() -> None:
    inventory = read_csv(INVENTORY)
    trades = read_csv(TRADES)
    live_by_date = defaultdict(list)
    for row in inventory:
        date_text = (row.get("market_date_for_fetch") or "")[:10]
        if date_text:
            live_by_date[date_text].append(row)

    base_by_date = defaultdict(list)
    strict_by_date = defaultdict(list)
    review_by_date = defaultdict(list)
    for row in trades:
        date_text = (row.get("timestamp_ny") or "")[:10]
        if not date_text:
            continue
        base_by_date[date_text].append(row)
        if strict_v1_overlay(row):
            strict_by_date[date_text].append(row)
        if craig_context_review_candidate(row):
            review_by_date[date_text].append(row)

    rows = []
    for date_text in sorted(live_by_date):
        if date_text not in base_by_date:
            continue
        videos = live_by_date[date_text]
        take_labels = sum(int(v.get("observed_take_labels") or 0) for v in videos)
        verified = any("verified" in v.get("market_date_status", "") for v in videos)
        baseline_rows = base_by_date[date_text]
        strict_rows = strict_by_date[date_text]
        rows.append(
            {
                "date": date_text,
                "video_ids": "|".join(v["video_id"] for v in videos),
                "date_status": "verified" if verified else "upload_proxy",
                "craig_transcript_take_labels": take_labels,
                "baseline_model_trades": len(baseline_rows),
                "strict_v1_overlay_trades": len(strict_rows),
                "craig_context_review_candidates": len(review_by_date[date_text]),
                "baseline_total_r": f"{sum(float(r.get('result_r') or 0) for r in baseline_rows):.2f}",
                "strict_v1_total_r": f"{sum(float(r.get('result_r') or 0) for r in strict_rows):.2f}",
                "craig_context_review_total_r": f"{sum(float(r.get('result_r') or 0) for r in review_by_date[date_text]):.2f}",
                "strict_v1_times_ny": "|".join((r.get("timestamp_ny") or "")[11:16] for r in strict_rows),
                "review_times_ny": "|".join((r.get("timestamp_ny") or "")[11:16] for r in review_by_date[date_text]),
                "titles": " / ".join(v.get("title", "") for v in videos),
            }
        )

    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "date",
                "video_ids",
                "date_status",
                "craig_transcript_take_labels",
                "baseline_model_trades",
                "strict_v1_overlay_trades",
                "craig_context_review_candidates",
                "baseline_total_r",
                "strict_v1_total_r",
                "craig_context_review_total_r",
                "strict_v1_times_ny",
                "review_times_ny",
                "titles",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    total_take = sum(int(r["craig_transcript_take_labels"]) for r in rows)
    total_base = sum(int(r["baseline_model_trades"]) for r in rows)
    total_strict = sum(int(r["strict_v1_overlay_trades"]) for r in rows)
    total_review = sum(int(r["craig_context_review_candidates"]) for r in rows)
    strict_r = sum(float(r["strict_v1_total_r"]) for r in rows)
    review_r = sum(float(r["craig_context_review_total_r"]) for r in rows)
    base_r = sum(float(r["baseline_total_r"]) for r in rows)

    lines = [
        "# LIVE 최근 날짜 Entry Count Proxy 비교",
        "",
        "범위: 기존 SOL 6개월 백테스트 데이터에 포함되는 LIVE 영상 날짜만 비교했다.",
        "",
        "이 비교는 정밀 Craig 일치성 평가가 아니다. 시장 날짜가 검증됐더라도 Craig의 자막 Take 라벨은 실제 체결 수와 1:1로 확정되지 않았다.",
        "",
        "## 요약",
        "",
        f"- 비교 가능 날짜: {len(rows)}",
        f"- Craig transcript Take 라벨 합계: {total_take}",
        f"- baseline 모델 진입 수: {total_base}",
        f"- strict v1 hard overlay 진입 수: {total_strict}",
        f"- Craig-context review 후보 수: {total_review}",
        f"- baseline 합계 R: {base_r:.2f}",
        f"- strict v1 hard overlay 합계 R: {strict_r:.2f}",
        f"- Craig-context review 후보 합계 R: {review_r:.2f}",
        "",
        "## 날짜별 비교",
        "",
        "| date | status | Craig takes | baseline | hard strict | context review | review times NY |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row['date']} | {row['date_status']} | {row['craig_transcript_take_labels']} | "
            f"{row['baseline_model_trades']} | {row['strict_v1_overlay_trades']} | "
            f"{row['craig_context_review_candidates']} | {row['review_times_ny']} |"
        )
    lines.extend(
        [
            "",
            "## 해석",
            "",
            "hard strict overlay는 너무 보수적으로 0개까지 줄어든다. 이것은 최종 모델이 아니라, 어떤 조건이 Craig 실제 거래까지 막는지 보기 위한 하한선이다.",
            "",
            "Craig-context review 후보는 `09:30-11:00 또는 14:00-15:30`, displacement >= 1.75, aligned zone 존재, CHoCH 존재만 요구한다. 이 후보들은 자동 진입이 아니라 프레임/자막으로 primary objective가 진짜였는지 확인할 queue다.",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"rows={len(rows)} output={OUT_CSV}")


if __name__ == "__main__":
    main()
