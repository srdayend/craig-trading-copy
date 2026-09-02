#!/usr/bin/env python3
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/craig_similarity_critical_mismatch_audit.md"
DOC = ROOT / "docs/05_Craig_critical_mismatch_재감사.md"


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def fmt_float(value: str) -> str:
    try:
        return f"{float(value):.2f}"
    except Exception:
        return value or ""


def build() -> str:
    live = read_csv(ROOT / "outputs/craig_live_trading_video_inventory.csv")
    audit = read_csv(ROOT / "outputs/craig_binance_entry_mismatch_audit.csv")
    splits = read_csv(ROOT / "outputs/craig_episode_event_splits_v0_2b.csv")
    outcome = read_csv(ROOT / "outputs/craig_outcome_agreement_v0_1.csv")
    trades = read_csv(ROOT / "outputs/sol_craig_rule_backtest_trades.csv")
    proxy_counts = read_csv(ROOT / "outputs/craig_live_recent_proxy_entry_count_comparison.csv")

    live_total = len(live)
    live_verified = sum(1 for r in live if "verified" in r.get("market_date_status", ""))
    live_takes = sum(int(r.get("observed_take_labels") or 0) for r in live)
    live_scorable = sum(1 for r in live if int(r.get("verified_episode_rows") or 0) > 0)

    audit_counts = Counter(r.get("audit_category", "") for r in audit)
    take_rows = [r for r in audit if (r.get("observed_action_class") or "").lower() == "take"]
    same_dir = [
        r
        for r in take_rows
        if r.get("model_action") == "take" and r.get("observed_direction") == r.get("model_direction")
    ]
    strict_price = [r for r in audit if r.get("price_status") == "strict_entry_stop_match"]
    target_near = [r for r in audit if r.get("target_match") == "target_near"]
    filled_results = [r for r in audit if r.get("result_r") not in ("", None)]
    total_r = sum(float(r["result_r"]) for r in filled_results if r["result_r"])

    outcome_exit_matches = sum(1 for r in outcome if r.get("exit_reason_match") == "pass")
    outcome_exit_rows = sum(1 for r in outcome if r.get("exit_reason_match") in {"pass", "fail"})
    outcome_be_matches = sum(1 for r in outcome if r.get("be_match") == "pass")
    outcome_be_rows = sum(1 for r in outcome if r.get("be_match") in {"pass", "fail"})
    outcome_partial_matches = sum(1 for r in outcome if r.get("partial_match") == "pass")
    outcome_partial_rows = sum(1 for r in outcome if r.get("partial_match") in {"pass", "fail"})
    proxy_dates = len(proxy_counts)
    proxy_craig_takes = sum(int(r.get("craig_transcript_take_labels") or 0) for r in proxy_counts)
    proxy_baseline = sum(int(r.get("baseline_model_trades") or 0) for r in proxy_counts)
    proxy_hard_strict = sum(int(r.get("strict_v1_overlay_trades") or 0) for r in proxy_counts)
    proxy_review = sum(int(r.get("craig_context_review_candidates") or 0) for r in proxy_counts)

    def trade_r(row: dict[str, str]) -> float:
        try:
            return float(row.get("result_r") or 0.0)
        except Exception:
            return 0.0

    def segment_stats(predicate) -> tuple[int, float, float]:
        rows = [r for r in trades if predicate(r)]
        total = sum(trade_r(r) for r in rows)
        avg = total / len(rows) if rows else 0.0
        return len(rows), total, avg

    bad_segments = [
        ("no-bias 자동 진입", lambda r: r.get("htf_bias") == "no_bias"),
        ("리더 반대 방향", lambda r: r.get("leader_bias") in {"long", "short"} and r.get("leader_bias") != r.get("direction")),
        ("late morning", lambda r: r.get("session_phase") == "late_morning"),
        ("displacement < 2.4", lambda r: (r.get("disp_band") or "") in {"1.4-1.8", "1.8-2.4", "<1.4"}),
        ("market-fill 과다", lambda r: r.get("entry_model") == "market_fill"),
        ("synthetic 4R target", lambda r: "synthetic" in (r.get("target_type") or "")),
        ("HTF bias 반대", lambda r: r.get("htf_bias") in {"long", "short"} and r.get("htf_bias") != r.get("direction")),
    ]

    lines = [
        "# Craig 닮기 Critical Mismatch 재감사",
        "",
        "작성일: 2026-08-22",
        "",
        "## 현재 답",
        "",
        "아까의 1차 개선은 방향은 맞았지만, 사용자가 원하는 수준의 `Craig 복제`라고 말하기에는 아직 부족했다. 특히 `수익 개선 필터`와 `Craig 행동 일치성`이 섞여 있었고, LIVE TRADING 전체 영상으로 확장된 비교도 아직 완료 전이었다.",
        "",
        "이번 재감사의 기준은 수익률이 아니라 다음 질문이다.",
        "",
        "> Craig가 그 자리에서 실제로 보고 있었을 맥락, 기다린 trigger, 진입/패스 판단을 모델도 같은 방식으로 표현하는가?",
        "",
        "## 데이터 상태",
        "",
        f"- LIVE/TRADING 영상 인벤토리: {live_total}개",
        f"- 자막 기반 Take 라벨: {live_takes}개",
        f"- 실제 시장 날짜가 검증된 영상: {live_verified}/{live_total}",
        f"- episode 단위 비교 가능 영상: {live_scorable}/{live_total}",
        "- 현재 정밀 비교 완료 범위: a7x0yKL6jkI, C3-ZcTx1mpE 두 영상의 8개 episode/split row",
        "",
        "중요: a7/C3 두 영상 모두 업로드일과 실제 거래일이 달랐다. 사용자가 추가로 18개 영상의 TradingView 하단 날짜축을 확인해 주었고, 아직 19개 영상은 upload date proxy 상태다.",
        "",
        "## 기존 8개 이벤트 비교 요약",
        "",
        f"- observed Take row 중 같은 방향 candidate: {len(same_dir)}/{len(take_rows)}",
        f"- entry/stop strict price-box match: {len(strict_price)}/6",
        f"- target near: {len(target_near)}/6",
        f"- 단순 Binance replay 합계: {fmt_float(str(total_r))}R",
        f"- exit reason agreement: {outcome_exit_matches}/{outcome_exit_rows}",
        f"- BE state agreement: {outcome_be_matches}/{outcome_be_rows}",
        f"- partial decision agreement: {outcome_partial_matches}/{outcome_partial_rows}",
        "",
        "event split 이후 가장 큰 변화는 `a7_20260722_long_trade_2`다. 넓은 12:45-13:30 창에서는 모델이 뒤쪽 숏을 골랐지만, 프레임/자막을 분리하면 Craig의 실제 subevent는 12:31-12:57 롱 주문계획이다. 즉 이 오류는 필터 문제가 아니라 거래 단위를 잘못 자른 문제다.",
        "",
        "## 최근 LIVE 날짜 Entry Count Proxy",
        "",
        f"- 비교 가능 날짜: {proxy_dates}",
        f"- Craig transcript Take 라벨 합계: {proxy_craig_takes}",
        f"- baseline 모델 진입 수: {proxy_baseline}",
        f"- hard strict overlay 진입 수: {proxy_hard_strict}",
        f"- Craig-context review 후보 수: {proxy_review}",
        "",
        f"해석: hard strict는 0개까지 줄어 Craig 실제 거래도 놓칠 위험이 크다. 반대로 Craig-context review 후보는 {proxy_review}개로 자막 Take {proxy_craig_takes}개와 더 가깝다. 따라서 다음 모델은 `자동 진입 strict`와 `Craig가 볼 법한 review 후보`를 분리해야 한다.",
        "",
        "## 백테스트 손실이 가리킨 위험 구간",
        "",
        "| 문제 구간 | 거래 수 | 총 R | 평균 R | 해석 |",
        "|---|---:|---:|---:|---|",
    ]
    for label, predicate in bad_segments:
        count, total, avg = segment_stats(predicate)
        lines.append(
            f"| {label} | {count} | {total:.2f} | {avg:.2f} | Craig라면 strict가 아니라 pass/trace로 뒀을 가능성이 큰 구간 |"
        )

    lines.extend(
        [
            "",
            "## Critical Mismatch",
            "",
            "| 우선순위 | 차이 | Craig 쪽 해석 | 현재 모델의 오작동 | 룰 수정 |",
            "|---:|---|---|---|---|",
            "| 1 | HTF zone 위계 | 15m/1h FVG는 아무 반응 구역이 아니라 오늘 thesis의 primary reaction/objective다. 1m은 entry trigger다. | `근처 active 15m/1h FVG`를 거의 동등하게 인정해서 좋은 자리 판정이 너무 쉽게 난다. | primary reaction zone을 하나로 고르고, 방향 정렬 + freshness + 오늘 range/draw 맥락을 요구한다. |",
            "| 2 | 영상 이벤트 분할 | Craig의 한 narration에는 이전 거래 청산, 새 진입, runner 관리가 섞일 수 있다. | 넓은 시간창에서 가장 높은 후보를 고르며 뒤쪽 반대 방향 후보를 선택할 수 있다. | fresh entry cue가 있는 subevent만 scoring하고 recap/runner context는 제외한다. |",
            "| 3 | no-bias | 방향성이 없으면 기다리거나 강한 objective 반응만 본다. | no-bias에서도 displacement만 강하면 strict take가 된다. | no-bias strict 자동 진입 금지. 예외는 별도 human-review 후보로만 둔다. |",
            "| 4 | market-fill | 빠른 진입도 이미 보고 있던 level/gap에서만 예외적으로 가능하다. | tiny FVG + midpoint 이탈만으로 market-fill이 과발동한다. | market-fill 기본 OFF. pre-planned zone, aligned bias, concrete target, no opposite zone이 모두 있을 때만 예외. |",
            "| 5 | target | Craig는 PDH/PDL, resting liquidity, HTF FVG midpoint, body shelf 같은 구체적 draw를 말한다. | target이 없으면 synthetic 4R이 strict final TP가 된다. | synthetic 4R은 final target 금지. 4R은 partial/BE 관리 기준으로만 사용. |",
            "| 6 | post-loss/session state | 손실 후 revenge를 피하고 다음 objective trade까지 쉰다. 목표 달성 후에는 강제로 새 진입하지 않는다. | cooldown은 있지만 같은 thesis 재사용과 daily-goal 방어가 약하다. | 손실 후 같은 방향+같은 zone+같은 thesis 재진입 금지. daily goal 이후 후보는 conditional. |",
            "| 7 | leader context | BTC/ETH momentum은 단순 수치가 아니라 그날 risk-on/off narrative다. | 15m 수익률 합으로 leader를 너무 단순화한다. | opposing leader는 strict 금지에 가깝게 두고, neutral/aligned만 허용한다. |",
            "| 8 | no-chase/attention | 좋은 움직임을 놓치면 따라가지 않고 다음 setup을 기다린다. | 모델은 차트에 보이는 setup이면 진입 후보로 만든다. | missed/open move는 trade가 아니라 no-chase trace로 저장한다. |",
            "",
            "## 오해 소지가 큰 룰 표현",
            "",
            "- `15m FVG`: entry zone일 수도, target일 수도, 단순 배경일 수도 있다. 모델 필드는 `primary_reaction_zone`, `target_draw`, `background_context`로 분리해야 한다.",
            "- `CHoCH`: 아무 1분 고점/저점 돌파가 아니라, Craig가 언급한 level 위/아래 종가 확인이어야 한다.",
            "- `entry`: 영상에서는 limit order plan, 실제 fill, 설명용 박스가 섞인다. Open Orders(1)/Positions(0) 같은 프레임 상태를 구분해야 한다.",
            "- `target`: 최종 TP, 첫 partial, liquidity objective, 나중 recap가 섞인다. 4R은 특히 final target으로 고정하면 안 된다.",
            "- `업로드일`: 실제 거래일이 아니다. a7은 2026-08-09 업로드지만 2026-07-22 거래, C3는 2026-07-19 업로드지만 2026-07-02 거래였다.",
            "",
            "## Craig-like Strict v1",
            "",
            "이건 무작위 필터 튜닝이 아니라 위 mismatch를 막기 위한 최소 룰이다.",
            "",
            "| 항목 | strict v1 값 | 사람이 읽는 의미 |",
            "|---|---|---|",
            "| 시간 | NY 09:30-10:30, 14:00-15:30 | 오픈 후 첫 기회와 power hour 중심. 그 외는 trace. |",
            "| HTF bias | 방향 일치 필수 | 큰 그림이 long이면 long만, short이면 short만. no-bias 자동 금지. |",
            "| primary zone | 방향 정렬 필수 | long은 bullish FVG/support/range low, short은 bearish FVG/resistance/range high. |",
            "| objective confluence | 최소 2개 | FVG 하나만으로는 부족. liquidity, PDH/PDL, range extreme, leader 등이 겹쳐야 함. |",
            "| displacement | 2.4 이상 | 단순 꼬리/잡음이 아니라 뚜렷한 추진 캔들. 1.8-2.4는 trace. |",
            "| leader | 반대 방향 strict 금지 | SOL만 보지 않고 BTC/ETH 흐름이 정면으로 반대면 pass. |",
            "| entry | midpoint/retest 기본 | 추격 진입보다 계획한 되돌림/중심값 체결. |",
            "| market-fill | 기본 OFF | 이미 보던 zone에서 급격히 떠나는 예외만 허용. |",
            "| target | concrete HTF draw 필수 | synthetic 4R final TP 금지. |",
            "| post-loss | 같은 thesis 재진입 금지 | 같은 구역에서 계속 두드리는 손실 루프 차단. |",
            "",
            "## 다음 정밀 비교 절차",
            "",
            "1. 39개 LIVE 영상 전체는 이미 인벤토리화한다.",
            "2. 각 영상의 `market_date_status`가 proxy인 행은 프레임으로 실제 거래일/심볼부터 확정한다.",
            "3. Take 라벨이 많은 영상부터 event split을 한다.",
            "4. entry/stop/target이 보이는 프레임만 price-level agreement에 넣는다.",
            "5. 그 다음 strict v1 후보와 Craig 실제 행동을 `take/pass/missed`, 방향, 가격, 관리, 결과 순서로 비교한다.",
            "",
            "## 현재 결론",
            "",
            "Craig를 더 닮기 위해 가장 먼저 고칠 것은 수익 필터가 아니라 `context ownership`이다. 모델이 먼저 오늘의 HTF objective를 정하고, 그 안에서 1분 trigger를 기다려야 한다. 지금처럼 1분 FVG가 먼저 나오고 나서 근처 HTF zone을 붙이면 Craig보다 훨씬 많은 나쁜 진입이 생긴다.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    text = build()
    OUT.write_text(text, encoding="utf-8")
    DOC.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"wrote {DOC}")


if __name__ == "__main__":
    main()
