#!/usr/bin/env python3
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from external_chart_tools import (  # noqa: E402
    detect_sr_flip_state,
    detect_zigzag_sr_levels,
    load_live_date_1m,
    resample_ohlcv,
)


TAKES = ROOT / "outputs" / "craig_trade_context_review.csv"
OUT_CSV = ROOT / "outputs" / "external_chart_tools_live_date_sr_probe.csv"
OUT_MD = ROOT / "outputs" / "external_chart_tools_setup_and_probe.md"


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


def scan_date(market_date: str) -> list[dict[str, str]]:
    one = load_live_date_1m("SOLUSDT", market_date)
    frames: dict[str, pd.DataFrame] = {
        "15m": resample_ohlcv(one, "15min"),
        "1h": resample_ohlcv(one, "1h"),
    }
    rows: list[dict[str, str]] = []
    for timeframe, df in frames.items():
        if len(df) < 20:
            continue
        levels = detect_zigzag_sr_levels(
            df,
            timeframe=timeframe,
            min_retrace_pct=0.18 if timeframe == "15m" else 0.30,
            max_pct_diff=0.12 if timeframe == "15m" else 0.18,
            max_bars_between=96,
            min_touches=2 if timeframe == "1h" else 3,
        )
        last_price = float(df["close"].iloc[-1])
        for level in levels[:8]:
            distance_pct = abs(level.level - last_price) / last_price * 100.0
            rows.append(
                {
                    "market_date": market_date,
                    "symbol": "SOLUSDT",
                    "timeframe": timeframe,
                    "level": f"{level.level:.6f}",
                    "low": f"{level.low:.6f}",
                    "high": f"{level.high:.6f}",
                    "direction_hint": level.direction_hint,
                    "touches": str(level.touches),
                    "flip_state": detect_sr_flip_state(df, level),
                    "distance_to_session_last_pct": f"{distance_pct:.3f}",
                    "first_touch": level.first_index,
                    "last_touch": level.last_index,
                    "source": level.source,
                }
            )
    return rows


def write_report(rows: list[dict[str, str]], dates: list[str], missing: list[str]) -> None:
    flip_counts = Counter(row["flip_state"] for row in rows)
    tf_counts = Counter(row["timeframe"] for row in rows)
    lines = [
        "# External Chart Tools Setup And Probe",
        "",
        "이 문서는 외부 GitHub 도구를 우리 프로젝트 목적에 맞게 어떻게 쓸지와, 우선 SOLUSDT LIVE 날짜에 S/R 후보를 뽑아본 결과를 기록한다.",
        "",
        "## 바로 쓰는 것",
        "",
        "- `Algorithmic-Support-and-Resistance`의 핵심 아이디어를 기반으로 zig-zag 반전점과 반복 터치 가격대를 묶는 `scripts/external_chart_tools.py`를 만들었다.",
        "- 이 래퍼는 Yahoo/yfinance 의존성을 제거하고, 이미 저장된 Binance SOLUSDT 1분봉 CSV를 직접 사용한다.",
        "- 산출물은 `SRLevel`과 `flip_state`로 나오므로 Craig의 `SR flip box`, `repeated SR box`, `primary reaction zone` 후보로 바로 연결할 수 있다.",
        "",
        "## 참고만 하는 것",
        "",
        "- `PatternPy`: OHLCV 패턴 탐지 아이디어는 참고 가능하지만 라이선스가 `CC BY-NC-SA 4.0`이라 직접 통합하지 않는다.",
        "- `chart-pattern-recognition-spike`: YOLOv8 차트 패턴 탐지 실험으로, 별도 HuggingFace 모델/Git LFS/Python 3.11이 필요하다. 지금은 빨간/파란 position box 추출 문제의 정답 도구가 아니다.",
        "- `stock-agent`: 스크린샷을 vision LLM에 보내는 구조와 JSON schema는 참고할 만하지만, 현재 local vision endpoint가 없고 가격축 OCR 검증이 없다. position box 추출은 별도 검증 레이어가 필요하다.",
        "- `youtube-stocks-analyser-crewai-local-ollama`: YouTube transcript multi-agent 처리 구조는 참고 가능하지만, 우리는 이미 자막/날짜/후보 큐를 갖고 있어 직접 실행 이득은 낮다.",
        "",
        "## 빨간/파란 Position Box에 대한 판단",
        "",
        "- 현재 자동으로 entry/SL/TP를 안정적으로 뽑고 있다고 보면 안 된다.",
        "- 올바른 방식은 `색상 박스 후보 탐지 -> 가격축 OCR -> Craig 발화와 교차검증 -> confidence 점수` 순서다.",
        "- 따라서 현재 모델 비교에서 position box 값은 `frame_review_required`로 남기고, 자동 백테스트의 가격값으로 확정하지 않는다.",
        "",
        "## Probe 요약",
        "",
        f"- 스캔한 Craig LIVE 날짜: {len(dates)}개",
        f"- 데이터 누락 날짜: {len(missing)}개",
        f"- 생성된 S/R 후보: {len(rows)}개",
        "",
        "| timeframe | 후보 수 |",
        "|---|---:|",
    ]
    for key, value in tf_counts.most_common():
        lines.append(f"| `{key}` | {value} |")
    lines.extend(["", "| flip_state | 후보 수 |", "|---|---:|"])
    for key, value in flip_counts.most_common():
        lines.append(f"| `{key}` | {value} |")
    if missing:
        lines.extend(["", "데이터 누락:", ""])
        for date in missing:
            lines.append(f"- `{date}`")
    lines.extend(
        [
            "",
            "## 다음 연결",
            "",
            "1. `craig_emulator_reference.py`의 HTF map에 `sr_flip_support`, `sr_flip_resistance`, `repeated_sr`를 primary reaction zone 후보로 넣는다.",
            "2. 1분 FVG/CHoCH 후보는 이 zone 근처에서만 자동 진입 후보로 승격한다.",
            "3. 영상 프레임에서 수동 박스/라인이 보이는 경우, 자동 S/R 후보와 겹치는지 확인해 confidence를 올린다.",
            "",
            f"상세 CSV: `{OUT_CSV.relative_to(ROOT)}`",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    takes = read_csv(TAKES)
    dates = sorted({row["market_date"] for row in takes if row.get("market_date")})
    rows: list[dict[str, str]] = []
    missing: list[str] = []
    for date in dates:
        try:
            rows.extend(scan_date(date))
        except FileNotFoundError:
            missing.append(date)
    write_csv(OUT_CSV, rows)
    write_report(rows, dates, missing)
    print(f"dates={len(dates)} rows={len(rows)} missing={len(missing)}")
    print(f"output={OUT_CSV}")
    print(f"report={OUT_MD}")


if __name__ == "__main__":
    main()
