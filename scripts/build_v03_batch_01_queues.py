from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "gold_context_trades"
FRAME_MANIFEST = ROOT / "data" / "source" / "craig_frames" / "local_v03_batch_01" / "local_v03_batch_01_frame_manifest.json"
QUALITY_INPUTS = ROOT / "outputs" / "craig_quality_tracker_v0_3" / "quality_tracker_inputs.json"
OUT_SUMMARY = ROOT / "outputs" / "v03_batch_01_7_video_summary.md"

BATCH_IDS = [
    "NvK0bj-2MiA",
    "yEyoTXmvDWY",
    "2Sn-yI9eL9M",
    "spSY9ExzUuY",
    "o1S_w9o34Ao",
    "tUEQDc56pKE",
    "1zmixRfB8co",
]

CTX_FIELDS = [
    "context_id",
    "session_context_id",
    "video_id",
    "video_title",
    "local_index_oldest_first",
    "source_stage_v03",
    "decision_type",
    "gold_status",
    "symbol",
    "direction",
    "chart_timeframe",
    "market_date_utc_minus4",
    "market_time_window_utc_minus4",
    "visible_chart_time_note",
    "market_time_confidence",
    "youtube_window",
    "anchor_seconds",
    "entry_price",
    "stop_price",
    "target_price",
    "realized_result",
    "session_macro_context_ko",
    "scenario_tree_ko",
    "symbol_selection_context_ko",
    "elliott_wave_context_ko",
    "trade_thesis_link_ko",
    "structure_reference_ko",
    "setup_context_ko",
    "entry_plan_ko",
    "management_plan_ko",
    "live_thesis_changes_ko",
    "exit_result_ko",
    "frame_evidence_paths",
    "ohlcv_alignment_ko",
    "rule_feature_vector_seed_ko",
    "invalidation_condition_ko",
    "remaining_uncertainty_ko",
]

SESSION_FIELDS = [
    "session_context_id",
    "video_id",
    "video_title",
    "local_index_oldest_first",
    "source_stage_v03",
    "market_dates_utc_minus4",
    "primary_symbols",
    "confirmed_timeframes",
    "local_video_path",
    "local_srt_path",
    "session_macro_context_ko",
    "scenario_tree_ko",
    "symbol_selection_context_ko",
    "elliott_wave_context_ko",
    "session_risk_context_ko",
    "frame_contact_sheet",
    "v03_upgrade_notes_ko",
]

RULE_FIELDS = [
    "rule_seed_id",
    "context_id",
    "video_id",
    "decision_type",
    "symbol",
    "direction",
    "macro_bias_feature",
    "scenario_feature",
    "wave_fib_feature",
    "setup_trigger_feature",
    "entry_feature",
    "invalidation_feature",
    "management_feature",
    "outcome_feature",
    "negative_or_pass_rule",
    "quantification_notes_ko",
]

AUDIT_FIELDS = [
    "video_id",
    "video_title",
    "context_rows",
    "status_mix",
    "has_session_row",
    "has_local_frames",
    "v03_quality_note_ko",
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


def load_progress() -> dict[str, dict[str, str]]:
    raw = json.loads(QUALITY_INPUTS.read_text(encoding="utf-8"))
    return {row["video_id"]: row for row in raw["videos"]}


def load_manifest() -> dict[str, list[dict[str, str]]]:
    return json.loads(FRAME_MANIFEST.read_text(encoding="utf-8"))


PROGRESS = load_progress()
MANIFEST = load_manifest()


DATES = {
    "NvK0bj-2MiA": ("2025-05-07", "high_user_verified_bottom_axis"),
    "yEyoTXmvDWY": ("2025-06-11", "high_frame_bottom_axis_and_notion_log"),
    "2Sn-yI9eL9M": ("2025-06-16", "high_user_verified_bottom_axis"),
    "spSY9ExzUuY": ("2025-07-21", "high_user_verified_bottom_axis"),
    "o1S_w9o34Ao": ("2025-07-27", "high_frame_bottom_axis_and_notion_log"),
    "tUEQDc56pKE": ("2025-07-23", "high_frame_bottom_axis_and_notion_log"),
    "1zmixRfB8co": ("2025-08-19", "high_frame_bottom_axis_and_notion_log"),
}


def contacts(video_id: str) -> list[str]:
    return [frame["path"] for frame in MANIFEST.get(video_id, []) if frame.get("stamp") == "contact"]


def evidence(video_id: str, *labels: str) -> str:
    needles = [label.lower() for label in labels if label]
    found = []
    for frame in MANIFEST.get(video_id, []):
        text = f"{frame.get('labels', '')} {frame.get('stamp', '')}".lower()
        if frame.get("stamp") == "contact" or any(n in text for n in needles):
            found.append(frame["path"])
    return "|".join(dict.fromkeys(found))


def ohlcv_note(video_id: str, symbols: str) -> str:
    date_text = DATES[video_id][0]
    checks = []
    for symbol in symbols.split("|"):
        path = ROOT / "data" / "raw" / "binance_futures_live_dates" / date_text / f"{symbol}_1m_{date_text}_ny.csv"
        checks.append(f"{symbol}: {'있음' if path.exists() else '없음'}({path.as_posix()})")
    return f"{date_text} NY/UTC-4 기준 1분봉 캐시 확인. " + "; ".join(checks)


def progress_value(video_id: str, key: str) -> str:
    return PROGRESS.get(video_id, {}).get(key, "")


def session(
    video_id: str,
    title: str,
    symbols: str,
    macro: str,
    scenario: str,
    selection: str,
    wave: str,
    risk: str,
    notes: str,
) -> dict[str, str]:
    date_text, _confidence = DATES[video_id]
    p = PROGRESS[video_id]
    return {
        "session_context_id": f"{video_id}_session_v03_batch01",
        "video_id": video_id,
        "video_title": title,
        "local_index_oldest_first": p["local_index_oldest_first"],
        "source_stage_v03": "v0_3_batch_01_local_srt_frame_ohlcv",
        "market_dates_utc_minus4": date_text,
        "primary_symbols": symbols,
        "confirmed_timeframes": "1m visible; higher time frame/daily/4h when spoken or shown",
        "local_video_path": p["video_file"],
        "local_srt_path": p["srt_file"],
        "session_macro_context_ko": macro,
        "scenario_tree_ko": scenario,
        "symbol_selection_context_ko": selection,
        "elliott_wave_context_ko": wave,
        "session_risk_context_ko": risk,
        "frame_contact_sheet": "|".join(contacts(video_id)),
        "v03_upgrade_notes_ko": notes,
    }


def ctx(
    video_id: str,
    n: int,
    decision_type: str,
    symbol: str,
    direction: str,
    youtube_window: str,
    anchor_seconds: str,
    market_time: str,
    visible_note: str,
    result: str,
    session_macro: str,
    scenario_tree: str,
    selection: str,
    wave: str,
    thesis: str,
    structure: str,
    setup: str,
    entry: str,
    management: str,
    live_changes: str,
    exit_result: str = "",
    rule_seed: str = "",
    invalidation: str = "",
    uncertainty: str | tuple[str, ...] = "",
    labels: tuple[str, ...] | None = None,
    entry_price: str = "frame_relative_or_about",
    stop_price: str = "frame_relative_or_about",
    target_price: str = "frame_relative_or_about",
    chart_timeframe: str = "1m",
    gold_status: str = "v03_gold_trade_context_ready",
) -> dict[str, str]:
    if labels is None and isinstance(uncertainty, tuple):
        labels = uncertainty
        uncertainty = invalidation
        invalidation = rule_seed
        rule_seed = exit_result
        exit_result = live_changes
        live_changes = management
        management = entry
        entry = setup
    title = progress_value(video_id, "video_title")
    date_text, confidence = DATES[video_id]
    return {
        "context_id": f"{video_id}_v03_batch01_{n:02d}",
        "session_context_id": f"{video_id}_session_v03_batch01",
        "video_id": video_id,
        "video_title": title,
        "local_index_oldest_first": progress_value(video_id, "local_index_oldest_first"),
        "source_stage_v03": "v0_3_batch_01_local_srt_frame_ohlcv",
        "decision_type": decision_type,
        "gold_status": gold_status,
        "symbol": symbol,
        "direction": direction,
        "chart_timeframe": chart_timeframe,
        "market_date_utc_minus4": date_text,
        "market_time_window_utc_minus4": market_time,
        "visible_chart_time_note": visible_note,
        "market_time_confidence": confidence,
        "youtube_window": youtube_window,
        "anchor_seconds": anchor_seconds,
        "entry_price": entry_price,
        "stop_price": stop_price,
        "target_price": target_price,
        "realized_result": result,
        "session_macro_context_ko": session_macro,
        "scenario_tree_ko": scenario_tree,
        "symbol_selection_context_ko": selection,
        "elliott_wave_context_ko": wave,
        "trade_thesis_link_ko": thesis,
        "structure_reference_ko": structure,
        "setup_context_ko": setup,
        "entry_plan_ko": entry,
        "management_plan_ko": management,
        "live_thesis_changes_ko": live_changes,
        "exit_result_ko": exit_result,
        "frame_evidence_paths": evidence(video_id, *(labels or ())),
        "ohlcv_alignment_ko": ohlcv_note(video_id, "BTCUSDT|ETHUSDT|SOLUSDT"),
        "rule_feature_vector_seed_ko": rule_seed,
        "invalidation_condition_ko": invalidation,
        "remaining_uncertainty_ko": uncertainty,
    }


def rule_from_context(row: dict[str, str]) -> dict[str, str]:
    negative = "no_fill/pass/cancel 샘플" if "no_fill" in row["decision_type"] or "pass" in row["decision_type"] else ""
    if "loss" in row["realized_result"].lower() or "손실" in row["realized_result"]:
        negative = "손실/무효화 샘플"
    return {
        "rule_seed_id": row["context_id"].replace("_v03_", "_rule_"),
        "context_id": row["context_id"],
        "video_id": row["video_id"],
        "decision_type": row["decision_type"],
        "symbol": row["symbol"],
        "direction": row["direction"],
        "macro_bias_feature": row["session_macro_context_ko"],
        "scenario_feature": row["scenario_tree_ko"],
        "wave_fib_feature": row["elliott_wave_context_ko"],
        "setup_trigger_feature": row["setup_context_ko"],
        "entry_feature": row["entry_plan_ko"],
        "invalidation_feature": row["invalidation_condition_ko"],
        "management_feature": row["management_plan_ko"],
        "outcome_feature": row["exit_result_ko"],
        "negative_or_pass_rule": negative,
        "quantification_notes_ko": row["rule_feature_vector_seed_ko"],
    }


def build_sessions() -> list[dict[str, str]]:
    return [
        session(
            "NvK0bj-2MiA",
            "Live Day Trading (THIS TRADE WAS INSANE)",
            "BTCUSDT|SOLUSDT|ETHUSDT",
            "뉴스 캘린더에서 14:00 고영향 이벤트를 확인하고, BTC daily는 전일 bullish close와 previous day high 회수 가능성을 기준으로 bullish day bias를 둔다. 다만 실제 1분봉이 오전에 choppy하게 움직이면 bias와 반대인 short도 허용한다.",
            "초기에는 bullish continuation 가능성을 보지만, 두 번의 손실 뒤 큰 저점 이탈과 bearish displacement가 나오면 underside retest/FVG short로 전환한다. 이후 14:00 뉴스 전에는 예측보다 setup 품질과 리스크 제한을 우선한다.",
            "SOL이 1분봉에서 FVG, trend retest, position box가 가장 또렷해 실제 실행 중심으로 쓰인다. BTC는 daily bias와 뉴스 배경을 주는 기준 축이다.",
            "명시적 Elliott count보다 daily bias, trendline, FVG, CHoCH, previous high/low가 중심이다.",
            "초기 리스크는 trade당 약 $500. 두 번의 손실 이후에도 동일 전략을 따르며, 세 번째 trade에서 빠른 BE 전환과 trend trailing으로 손실을 복구한다.",
            "초기 손실 2개와 세 번째 10R turnaround가 모두 자막/프레임/1m 데이터로 연결됨. 이후 뉴스 전 SOL 후보는 보류로 분리.",
        ),
        session(
            "yEyoTXmvDWY",
            "Day In The Life Of A 28 Year Old Millionaire Day Trader In NYC",
            "SOLUSDT|ETHUSDT|BTCUSDT",
            "목표는 $4,000. 오전 분석은 전체적으로 long bias였지만 09:30 이후 강한 하락이 나오자 resistance/FVG short로 전술을 전환한다. HFT 테이블은 EMA/세션 bias를 함께 보여준다.",
            "아침에는 상단 레벨 돌파/상승 지속을 기대하지만, NY open 급락 뒤에는 FVG로 되돌림이 오면 short. 여러 BE 뒤에도 같은 구조가 반복되면 작은 이익 또는 새 critical break만 실행. 저녁에는 SOL long 실패 후 ETH에서 더 깨끗한 ABC/FVG long으로 전환한다.",
            "SOL은 오전 short/오후 long 실패에 쓰이고, ETH는 후반에 SOL보다 구조가 깨끗한 long 후보로 채택된다.",
            "후반 ETH long은 ABC/Elliott 성격의 되돌림 해석과 equal highs 목표가 언급된다. 오전 short들은 Elliott보다 FVG/저항 flip 중심이다.",
            "기본 risk는 $500. BE 전환을 빠르게 하고, 목표 $4,000을 향해 여러 번의 제한 손실/BE를 쌓는다.",
            "프레임에서 June 11, 2025, SOLUSDT 1m, UTC-4, Notion trade log가 확인되어 기존 미검증 날짜를 고신뢰로 승격.",
        ),
        session(
            "2Sn-yI9eL9M",
            "LIVE DAY TRADING - (PULLED OUT A WIN)",
            "SOLUSDT|BTCUSDT|ETHUSDT",
            "영상 시작 시 이미 포지션 보유. 왼쪽 모니터에서 경제 캘린더와 TradingView를 같이 띄우고, 09:30 NY stock market open 구간을 회색 영역으로 표시한다.",
            "시작 long이 유리하면 trend-follow로 하루 전체 runner를 노리고, BE 이후 시장이 되돌리면 다음 trade를 기다린다. 이후 전체 trend가 아래로 움직일 때 FVG/레벨 confluence가 나오면 short continuation으로 전환한다.",
            "SOL 실행이 중심. BTC는 시작 화면/거시 캘린더와 함께 배경 모니터링 역할.",
            "Elliott보다는 09:30 open, trend break, FVG box, discretionary indicator가 중심이다.",
            "초기 포지션은 BE로 위험 제거. 주문 수량 실수로 작은 사이즈였다는 메타까지 기록되어 실제 리스크 구현 때 중요하다.",
            "사용자 검증 날짜 2025-06-16과 로컬 1분봉 데이터가 있음. 시작 포지션은 entry 이전 설명이 일부 부족해 관리/결과 중심으로 기록.",
        ),
        session(
            "spSY9ExzUuY",
            "LIVE TRADING CRYPTO - Making $11,725 Profit Risking $1k",
            "SOLUSDT|ETHUSDT|BTCUSDT",
            "trade당 risk를 키워 목표 $8K 이상을 설정. 뉴스 캘린더상 당장 고영향 뉴스는 없고, 고확률 confluence와 risk containment를 반복하는 세션이다.",
            "초기 SOL short가 흔들리면 FVG stop sweep 가능성을 받아들이고 손실 제한. 시장이 ripping하면 long miss/오더 실수도 인정한다. 이후 G2 continuation, Elliott 5파/2.618 반응, trend underside retest, 후반 ETH weakness short로 이어진다.",
            "SOL이 주 실행 축이고, 후반에는 ETH가 상대적으로 약해 short 후보로 선택된다.",
            "1-2-3-4-5 wave, 2.618/1.618 반응, 5파 top 가능성을 reversal/continuation 필터로 사용한다.",
            "risk per trade 약 $1,000. 오더/SL 실수로 손실이 커지는 장면도 포함되며, 이후 BE/partial/trailing으로 회복한다.",
            "사용자 검증 날짜 2025-07-21. Elliott/Fib와 G2 continuation이 뚜렷해 규칙화 소스로 가치가 높음.",
        ),
        session(
            "o1S_w9o34Ao",
            "LIVE TRADING CRYPTO - Making $7,806 [I Went Crazy]",
            "BTCUSDT|SOLUSDT|ETHUSDT",
            "Bitcoin 4H Elliott wave를 먼저 보고, uptrend 이탈 뒤 1-2-3-4에서 5파 하락으로 저점 이탈 가능성을 본다. 해당 저점/critical area에 도달하면 long 전환도 계획한다.",
            "처음에는 bearish continuation/short runner를 노리고, 크게 밀리면 stop을 BE로 옮겨 open-ended runner. 이후 previous day low/61.8 근방까지 더 열어두며, 과열 하락 뒤에는 SOL/ETH의 CHoCH/BOS long 후보도 준비한다.",
            "BTC는 HFT/Elliott bias, SOL은 주요 실행 종목, ETH는 후반 log에 포함된 대체 실행 종목이다.",
            "Elliott 4H 1-2-3-4-5, Fib 61.8, 2.618 extension, parabolic move/reversal area를 적극 사용한다.",
            "risk $1,000. 큰 runner에서는 BE 이후 high/low 위아래로 stop walking, gym 중 alert/stop 운용까지 포함된다.",
            "프레임에서 July 27, 2025, SOL/ETH 1m trade log, UTC-4가 확인됨. 2025-07-27 1분봉 데이터 있음.",
        ),
        session(
            "tUEQDc56pKE",
            "Day In The Life Of A Millionaire 28 Year Old Day Trader In NYC",
            "BTCUSDT|SOLUSDT|ETHUSDT",
            "daily bias를 먼저 설명한다. Bitcoin weakness와 session low break가 나오면 전체 세션에서 큰 short opportunity가 열린다는 가정을 둔다.",
            "fair value gap과 trend break를 기본 entry 모델로 설명한 뒤, risk-free long/short를 관리한다. bearish direction이 확정되면 SOL에서 low break/capitulation short runner를 추적하고, 후반에는 ETH short가 더 좋은 선택이었다고 실시간으로 평가를 수정한다.",
            "SOL 실행이 중심이나, 후반에는 ETH short가 상대적으로 더 좋은 move였음을 인정하고 다음 trade 후보를 ETH/SOL로 비교한다.",
            "명시적 Elliott보다 trend/FVG/daily bias 중심. 프레임에는 Elliott 도구가 보이지만 이 영상의 핵심 설명은 FVG/trend/risk management다.",
            "risk $1,000. 세션 중 50% win rate라도 큰 winner가 손실보다 커야 한다는 risk-reward 철학을 직접 설명한다.",
            "프레임에서 July 23, 2025, SOLUSDT/ETHUSDT 1m, UTC-4, Notion trade log가 확인되어 actual market date로 승격.",
        ),
        session(
            "1zmixRfB8co",
            "LIVE TRADING CRYPTO - Losing $2,428 In A Day Risking $1k",
            "ETHUSDT|SOLUSDT|BTCUSDT",
            "세션 전체가 losing-day process 예시다. ETH/SOL의 1분봉 short/long 후보를 보되, 연속 손실과 감정 통제를 핵심 맥락으로 둔다.",
            "좋은 setup이 fill되면 실행하지만, 3연속 손실 규칙에 가까워지면 원래는 session 종료가 맞다고 인정한다. 영상 완성 목적상 조심해서 계속하되, chase 금지와 full direction change 대기를 명시한다.",
            "초기 ETH short와 후반 SOL/ETH 1분봉 후보가 중심. 손실일수록 종목 선택보다 setup 품질과 self-control이 우선이다.",
            "명시적 Elliott보다 RSI divergence, FVG, downtrend retest, CHoCH/BOS flip이 중심이다.",
            "risk $1,000. 세 번 연속 손실 시 종료 규칙, BE로 나온 home-run miss, chase 금지 규칙이 명확하다.",
            "프레임에서 August 19, 2025, SOLUSDT 1m, UTC-4, trade log가 확인됨. losing-day rule seed로 중요.",
        ),
    ]


def build_contexts() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    add = rows.append

    add(ctx(
        "NvK0bj-2MiA", 1, "executed_loss_context", "SOLUSDT", "short", "06:04-07:45", "364|452", "morning after initial long loss",
        "2025-05-07 1m, 초기 choppy 구간. 자막상 trade 2는 SOL open at entry/FVG/CHoCH short였고 stop hit.",
        "-$1,223 day drawdown after second loss", "daily bullish bias였지만 1분봉은 choppy하고 하방 trend/FVG가 보여 short를 허용",
        "bias와 반대라도 FVG/CHoCH가 있으면 소액 리스크로 시도. stop hit 시 즉시 journal 후 다음 quality setup 대기",
        "SOL이 실제 FVG/CHoCH short 후보", "Elliott 없음", "daily bullish와 1m bearish setup의 충돌을 테스트한 손실 샘플",
        "CHoCH, down trend, FVG, no support, stop-loss box", "SOL이 open에서 entry 부근으로 와서 short; stop은 FVG/고점 위",
        "진입 후 강한 하방 follow-through가 없으면 stop loss 수용", "price가 stop-loss를 관통하며 choppy market이라고 판단",
        "contained loss로 journal; down $1,223", "counter_daily_bias_allowed_if_1m_fvg_choch_but_stop_if_no_followthrough", "FVG 상단/최근 high 돌파",
        "entry/SL exact price는 프레임 기반 재산출 필요", ("auto_01", "auto_02")))

    add(ctx(
        "NvK0bj-2MiA", 2, "executed_winner_context", "SOLUSDT", "short", "08:17-15:30", "497|697|753|811|862|967|1084", "late morning continuation",
        "저점 이탈 후 underside retest와 resistance/FVG. 프레임에서 short position box와 후속 runner 확인.",
        "about +$5,000; about 10R; nearly 6K turnaround", "초기 daily bullish였지만 큰 sell-off candle과 low break가 나오며 intraday thesis를 bearish continuation으로 전환",
        "market realignment 뒤 underside retest/FVG short. 움직이면 BE, 저점 깨지면 trailing, resistance pocket에서 exit",
        "SOL이 가장 또렷한 short continuation 구조", "Elliott 없음", "큰 displacement 이후 되돌림이 resistance/FVG에 들어오면 daily bias보다 실시간 구조를 우선",
        "broken lows, severe candle, underside retest, resistance level, FVG, trend continuation", "entry criteria 충족 후 limit/order fill 대기. fill되면 low break로 risk reduce",
        "첫 push 후 high 위로 stop 축소, BE 전환, trendline을 따라 stop을 낮추고 2R 이상 잠금", "처음에는 더 내려갈지 모른다고 보수적. +3K unrealized에서 trend trailing, resistance pockets 접근 시 finger on trigger",
        "resistance pocket에서 약 +$5K로 close; 10R winner", "displacement_low_break_plus_underside_fvg_short_then_be_trail_to_resistance", "reclaim above retest high or break of bearish trend",
        "정확한 가격은 OHLCV와 프레임 position box 좌표로 후속 산출", ("auto_02", "auto_03", "auto_04", "auto_05", "auto_06", "auto_07", "auto_08")))

    add(ctx(
        "NvK0bj-2MiA", 3, "conditional_pre_news_setup_context", "SOLUSDT", "mixed_or_conditional", "16:26-21:56", "1166", "pre 14:00 news/FOMC window",
        "14:00 고영향 rate/news 전에 setup이 나오면 trade 가능하지만 예측은 하지 않겠다고 발화.",
        "context held; only include as conditional decision, not executed-result sample", "rate decision이 bullish/bearish 양방향 driver가 될 수 있음을 인정",
        "뉴스 방향을 예측하지 않고, 뉴스 전 좋은 setup만 허용. 뉴스 자체에는 chase하지 않음",
        "SOL 후보", "Elliott 없음", "macro event risk가 있을 때 setup quality와 timing filter를 별도 룰로 둔다",
        "pre-news uncertainty, key level, possible SOL setup", "뉴스 전에 좋은 setup이 있으면 리스크 제한으로만 진입",
        "뉴스 직전/직후 volatility에서는 불리한 fill이나 방향 예측을 피함", "rates drop 여부에 따라 양방향 가능성을 열어둠",
        "결과가 완결되지 않아 gold trade가 아니라 conditional setup sample", "pre_news_trade_only_if_setup_complete_before_event_no_prediction", "event-driven candle before setup completion",
        "실행/종료가 완결되지 않아 hold 성격이 강함", ("auto_09",), gold_status="v03_gold_actionable_context_ready"))

    add(ctx(
        "yEyoTXmvDWY", 1, "executed_break_even_context", "SOLUSDT", "short", "02:59-07:08", "332|387|594", "09:30-10:58 approximate",
        "프레임에서 June 11 2025, SOLUSDT 1m, position Short, UTC-4가 보임. 09:30 sell-off 뒤 resistance/FVG retest short.",
        "break-even trade", "초기 분석은 long bias였지만 09:30 meltdown 뒤 intraday short로 전환",
        "큰 push down 이후 FVG/저항 되돌림에서 short. low가 깨지면 stop 축소, entry retest로 돌아오면 BE",
        "SOL의 급락 후 되돌림 short가 가장 명확", "Elliott 없음", "daily/초기 long bias가 있어도 NY open displacement가 나오면 resistance short로 전술 전환",
        "9:30 open drop, upper resistance, FVG, CHoCH/BOS markers", "FVG midpoint/저항으로 되돌아오면 short, stop은 retest high 위",
        "low break가 나오면 risk reduce; entry retest 시 BE 처리", "좋은 반응이 있었지만 low break가 충분하지 않아 BE를 수용",
        "came back and retested entry; journal as first trade BE", "ny_open_displacement_then_fvg_short_reduce_on_low_break_be_if_entry_retest", "reclaim above FVG/resistance high",
        "entry/SL/TP exact는 프레임상 167.40/167.76/163.55 계열로 보이나 후속 OCR/좌표 검증 필요", ("auto_02", "auto_03", "auto_04")))

    add(ctx(
        "yEyoTXmvDWY", 2, "executed_small_profit_context", "SOLUSDT", "short", "07:17-12:24", "594", "late morning",
        "recap에서 같은 하방 idea 반복 뒤 trend underside retest short가 small profit로 끝났다고 설명.",
        "small profit about +$478", "첫 BE 이후에도 09:30 하락 구조가 유지되어 short bias 유지",
        "동일 resistance/FVG short가 반복되지만 support가 생기면 무리한 home-run 대신 small profit",
        "SOL", "Elliott 없음", "반복 setup에서 follow-through 품질이 약하면 작은 이익으로 방어",
        "underside retest of trend, support response", "trend underside/FVG touch에서 short",
        "support가 생기면 risk/reward가 약해지므로 일부 또는 전부 close", "생각은 맞았지만 support가 막아주는 것을 보고 기대치를 낮춤",
        "took small profit instead of forcing continuation", "repeat_fvg_short_but_take_small_profit_when_support_forms", "support holds and price reclaims entry",
        "세부 가격은 recap 중심이라 exact box는 재확인 가능", ("auto_04",)))

    add(ctx(
        "yEyoTXmvDWY", 3, "executed_winner_context", "SOLUSDT", "short", "recap 20:06 plus earlier trade 4", "1206", "midday",
        "critical level break 뒤 underside retest short가 dump로 이어진 trade 4 recap.",
        "winning short; part of day toward $4,500", "long bias를 버리고 구조적 breakdown을 우선",
        "critical level이 깨지면 그 레벨의 underside retest를 short trigger로 사용",
        "SOL", "Elliott 없음", "level break -> underside retest -> continuation dump의 textbook rule seed",
        "critical broken level, underside retest, FVG/resistance", "break 후 retest에 short; stop은 reclaimed level 위",
        "초기 push 후 BE, continuation 시 runner", "이전 BE/작은 profit 뒤 더 깨끗한 break를 기다린 결과",
        "dumped after retest; winner in recap", "critical_level_break_underside_retest_short", "close back above broken level",
        "프레임 직접성은 recap+contact 중심", ("auto_05",)))

    add(ctx(
        "yEyoTXmvDWY", 4, "executed_loss_context", "SOLUSDT", "long", "15:52-16:28", "1102", "afternoon/gym window",
        "trade number five. SOL long은 divergence/trend break/FVG response가 있었지만 high break 실패 후 손실.",
        "-$564 loss", "하락 후 reversal long을 시도하지만 목표 $4,000을 향한 후반 trade라 리스크 제한",
        "support/FVG response로 long, high를 못 깨면 빠르게 손실 인정",
        "SOL", "possible reversal/ABC context but not primary Elliott", "short trend 뒤 reversal long이 fail할 때 negative sample",
        "trend break, FVG, support, failed high break", "dip into support/FVG long",
        "고점 돌파가 나오면 risk reduce; 실패하면 full loss 전 수용", "초기 반응은 있었지만 high break 실패로 thesis 약화",
        "loss $564; moved to next cleaner ETH idea", "reversal_long_needs_high_break_after_fvg_response", "failure to break prior high and return through support",
        "정확한 가격은 recap 중심", ("auto_05",)))

    add(ctx(
        "yEyoTXmvDWY", 5, "executed_winner_context", "ETHUSDT", "long", "20:06-23:25", "1206|1405", "evening",
        "recap상 SOL이 죽은 뒤 ETH long으로 전환. ABC/Elliott 성격, FVG entry, tight stop, green level에서 risk reduce, equal highs target.",
        "about +$2,137 full profit; day about +$4,500", "하루 목표 미달 상태에서 더 깨끗한 ETH reversal long을 선택",
        "SOL long 실패 뒤 같은 방향을 고집하지 않고 ETH의 더 좋은 wave/FVG long으로 전환",
        "ETH selected over weaker SOL", "ABC/Elliott-style correction and equal highs target", "종목 교체가 성과를 만든 샘플",
        "ABC correction, fair value gap, tight stop, equal highs liquidity", "FVG entry with tight stop below invalidation",
        "green level 도달 시 risk reduce, equal highs에서 TP/full close", "SOL 실패 후 ETH가 더 깨끗하다고 판단을 바꿈",
        "full profit around $2,137 and day around $4,500", "switch_symbol_after_failed_sol_to_cleaner_eth_abc_fvg_long", "break below ABC/FVG invalidation low",
        "프레임 일부는 recap 중심; 정확한 ETH price는 후속 좌표/OHLCV 재산출", ("auto_05",)))

    add(ctx(
        "2Sn-yI9eL9M", 1, "executed_management_context", "SOLUSDT", "long", "00:46-05:50", "226|290|344|459|526", "09:30 open onward",
        "영상 시작 전에 이미 long. 09:30 open gray area, boxes/FVG, proprietary indicators. +$1,200에서 BE로 risk 제거 후 trend-follow.",
        "risk-free runner attempt; later partial/small profit or BE management", "경제 캘린더와 09:30 open을 보고 변동성 시작점으로 사용",
        "이미 좋은 entry면 추가 설명보다 risk-free로 만들고 하루 runner 가능성을 열어둔다",
        "SOL 실행, BTC/캘린더 모니터링", "Elliott 없음", "entry 이후 management도 복제 대상: 좋은 초기 포지션은 성급히 닫지 않는다",
        "9:30 open level, trend break, FVG boxes, strong push", "pre-video long already filled; new entries wait for trend break/boxes",
        "stop to BE, trend-follow if market runs for rest of session, resist urge to close early", "volatile해서 standoffish. 큰 winner 욕심과 조기청산 충동을 말로 인식",
        "let-run management sample; exact final not isolated from next context", "good_entry_at_open_move_to_be_and_trend_follow_until_structure_break", "return to original position level or break bearish against long",
        "pre-video entry라 진입 직전 근거 일부는 부족하지만 관리 문맥은 완결", ("auto_01", "auto_02", "auto_03", "auto_04", "auto_05")))

    add(ctx(
        "2Sn-yI9eL9M", 2, "executed_winner_context", "SOLUSDT", "short", "07:23-11:16", "623", "mid session",
        "overall trend가 아래로 움직이며 finally level/level/FVG opportunity가 나와 short. 주문 입력 실수로 400 units만 들어갔지만 +$1,700까지 이동.",
        "winner/risk-free; smaller size due order input mistake", "초기 long runner 이후 차트가 되돌리고 하방 trend가 우세해짐",
        "상단에는 좋은 opportunity가 없다가 여러 레벨과 FVG가 겹치는 곳에서 short continuation",
        "SOL", "Elliott 없음", "여러 레벨 confluence가 생기기 전까지 기다리는 patience 샘플",
        "overall downtrend, multiple levels, FVG, stop moved to BE", "confluence level/FVG에서 short; size input mistake recorded",
        "초기 profit 뒤 stop BE. level stab back up이면 BE out", "수량 실수로 PnL은 작지만 setup 자체는 quality라고 판단",
        "up about $1,700 then BE-protected", "wait_for_level_stack_fvg_in_downtrend_then_short", "stab back into level above entry",
        "exact price는 프레임/OHLCV 후속 산출", ("auto_06",)))

    add(ctx(
        "2Sn-yI9eL9M", 3, "executed_loss_context", "SOLUSDT", "mixed_or_unknown", "11:42-12:08", "882", "later session",
        "position number four. level test에서 momentum 기대했지만 pattern이 bearish/not looking good이라고 보고 contained loss.",
        "contained loss", "세션 후반, 여러 포지션 후에도 contained risk 원칙 유지",
        "level reaction을 기대해 들어갔지만 entry로 돌아오고 패턴이 반대로 보이면 손실 수용",
        "SOL", "Elliott 없음", "setup이 기대 방향으로 바로 momentum을 못 주면 small contained loss",
        "level test, momentum failure, bearish pattern", "level response를 기대한 진입",
        "momentum 없고 entry retest/반대 패턴이면 빠르게 close", "진입 직후 현실적으로 좋지 않다고 말하며 thesis를 낮춤",
        "out for contained loss", "failed_level_momentum_exit_loss", "pattern shifts bearish against position",
        "direction은 자막 자동분류가 mixed라 후속 프레임 재확인 가능", ("auto_07",)))

    add(ctx(
        "spSY9ExzUuY", 1, "executed_loss_context", "SOLUSDT", "short", "02:20-07:50", "273|587|632", "NY open/morning",
        "risk를 키운 세션의 trade 1. SOL short가 FVG를 맞고 stop-loss를 관통하거나 break fully down 둘 중 하나라고 보고, 실제로 whiplash/stop으로 손실.",
        "loss; day roughly near breakeven/down after early gain", "고영향 뉴스 없음. 큰 risk라도 quality setup 반복",
        "FVG에서 bearish close가 나오면 계속 보유, 반대로 stop sweep이면 손실 인정",
        "SOL", "Elliott not primary", "risk-up 세션에서 첫 trade가 틀릴 때도 process 유지",
        "fair value gap, bearish candle close, stop-loss, whiplash", "short already in/entry at high-probability area",
        "FVG 반응과 candle close 확인. stop hit 시 손실 제한", "FVG를 관통해 stop을 칠 가능성도 미리 말함",
        "stop/whiplash; loss accepted", "short_fvg_requires_bearish_close_or_full_breakdown", "push through FVG and stop-loss",
        "trade 1 exact price는 프레임 재산출", ("auto_02", "auto_03", "auto_04")))

    add(ctx(
        "spSY9ExzUuY", 2, "missed_or_order_error_context", "SOLUSDT", "long", "07:50-08:55", "632", "after whiplash",
        "시장 ripping 중 long이 유지됐으면 좋았겠지만 order/SL handling 실수로 기대보다 손실이 커짐. 실행 실수 샘플.",
        "missed long / order error cost", "market ripping and long continuation opportunity", "setup은 맞아도 order/SL handling이 틀리면 PnL이 왜곡됨",
        "SOL", "Elliott not primary", "크레이그 복제에서 strategy와 execution error를 분리해야 하는 샘플",
        "whiplash, high break, long that did not stay filled", "long should have remained filled only if structure held",
        "오더와 stop 상태 확인 필요", "스스로 stop-loss order를 messed up 했다고 인정",
        "lost more than expected / missed continuation", "separate_execution_error_from_strategy_signal", "manual order/SL inconsistency",
        "규칙 성능평가에서는 strategy sample이 아니라 execution-error tag로 제외 가능", ("auto_04",), gold_status="v03_gold_actionable_context_ready"))

    add(ctx(
        "spSY9ExzUuY", 3, "executed_winner_context", "SOLUSDT", "long", "08:55-10:08", "535|584|608", "late morning",
        "G2 trade로 continuation을 플레이. FVG와 confluence에서 bullish response 확인 후 BE, 2.618 response를 보며 exit.",
        "winner; locked about $1,495", "market trending/ripping, continuation bias", "G2 continuation은 trend 방향 response가 확인될 때만 실행",
        "SOL", "2.618 response used as reaction/exit filter", "G2 continuation rule seed",
        "G2 process, FVG, confluence, bullish response, 2.618", "FVG/confluence에서 long, response 확인",
        "response 후 stop BE, extension level 반응에서 take off", "exit를 조금 놓쳤다고 말하지만 profit lock",
        "took off after 2.618 response, about +$1,495 locked", "g2_continuation_long_fvg_response_be_exit_at_extension_response", "failure to respond off FVG or reclaim below entry",
        "exact entry/SL/TP는 프레임/OHLCV 후속 산출", ("auto_05",)))

    add(ctx(
        "spSY9ExzUuY", 4, "executed_wave_setup_context", "SOLUSDT", "short", "10:08-11:29", "608|647", "midday",
        "1-2-3-4 wave 5, 3파 top 1.618/2.618 반응을 보고 5파 top 가능성 및 short opportunity를 구성.",
        "setup/winner candidate; order barely missed part noted", "trend가 extension까지 진행되어 reversal short 후보가 생김",
        "2.618에서 반응하면 5파 top 후보. break confirmation 뒤 SOL short 준비",
        "SOL", "1-2-3-4-5, 1.618, 2.618, wave 5 top", "Elliott/Fib가 entry 전 필터로 쓰인 대표 샘플",
        "Elliott impulse, 2.618 reaction, previous extension level break", "confirmation after break off previous 2.618 level",
        "fill되면 low break와 continuation 확인, 안 오면 chase 금지", "order가 아주 살짝 miss됐고 이미 다른 trade라 진입 우선순위를 조정",
        "partly missed/partly active; use as complete setup relation more than PnL sample", "wave5_extension_reaction_short_only_after_break_confirmation", "continuation through extension without bearish response",
        "실제 fill/result는 일부 분절되어 setup-relation gold로 둠", ("auto_06", "auto_07"), gold_status="v03_gold_actionable_context_ready"))

    add(ctx(
        "spSY9ExzUuY", 5, "executed_winner_context", "SOLUSDT", "short", "11:29-12:17", "689", "midday",
        "trend underside retest, 여러 contact point, 61.8/FVG confluence. ideal missed 후 다음 capitulation에서 진입해 critical area까지 continuation을 노림.",
        "winner/continuation; exact PnL included in session total", "상승 뒤 reversal/continuation short thesis", "ideal touch를 놓치면 다음 capitulation 확인 후 들어가고 chase를 줄임",
        "SOL", "Fib 61.8 used with FVG", "trendline underside retest + 61.8/FVG short",
        "trendline contact points, underside retest, 61.8, FVG, capitulation", "missed ideal entry; enter after next capitulation confirms",
        "low break가 나오면 critical area까지 runner; stop은 retest high 위", "놓친 뒤에도 더 나쁜 chase 대신 confirmation을 기다림",
        "continuation toward critical area", "underside_trend_retest_618_fvg_short_after_capitulation", "reclaim above underside trend/FVG",
        "exact result는 trade log total에 묶임", ("auto_07",)))

    add(ctx(
        "spSY9ExzUuY", 6, "executed_short_context", "ETHUSDT", "short", "20:36-21:56", "1236|1290", "evening",
        "멘토링 후 ETH weakness를 보고 lows가 가까이 test되고 CHoCH가 나왔기 때문에 retest level short order를 연다.",
        "executed/managed short; included in $11,725 day", "후반에도 SOL만 고집하지 않고 더 약한 ETH를 선택",
        "lows test, CHoCH, retest level이 완성되면 short. 너무 이른 fill이면 caution",
        "ETH weaker than SOL at that moment", "Elliott not primary", "relative weakness + CHoCH short",
        "ETH weakness, lows closer, CHoCH, retest level", "retest level에 limit/order open",
        "bad/early fill이면 momentum catch를 피하고 trend retest 여부 확인", "ETH 움직임이 weird하다고 하며 fill quality를 계속 평가",
        "short context complete; exact final tied to daily result", "relative_weakness_choch_retest_short", "failed retest and reclaim above CHoCH level",
        "price/result exact는 후속 프레임/OHLCV 계산 가능", ("auto_08", "auto_09")))

    add(ctx(
        "o1S_w9o34Ao", 1, "executed_winner_context", "BTCUSDT|SOLUSDT", "short", "01:18-09:29", "258|306|419|645", "early session",
        "BTC 4H Elliott 1-2-3-4에서 5파 하락을 예상. red/green FVG midpoint와 confluence를 이용해 momentum/reversal short를 실행하고 빠르게 BE.",
        "large winner; up about $3,400 then more; part of +$7,806 day", "상위 BTC wave가 bearish라 low break/continuation을 우선",
        "critical low가 깨지면 short runner. target은 lower area, 위험은 BE로 이동",
        "BTC bias를 보고 SOL 실행도 함께 비교", "4H Elliott 1-2-3-4 to 5, low break", "HFT Elliott와 1m FVG execution 연결",
        "Elliott wave breakdown, FVG midpoint, critical level break, lower target area", "FVG/confluence short; break under key low confirms",
        "initial push 후 risk reduce, stop BE, open-ended runner", "너무 crowd하지 않고 큰 하락 가능성을 열어둠",
        "beautiful trade; resistance/momentum area에서 일부/전부 close", "hft_elliott_wave5_bias_plus_1m_fvg_short_be_runner", "break above structure high or failed low break",
        "symbol별 exact fill은 프레임/OHLCV에서 후속 산출", ("auto_03", "auto_04", "auto_05", "auto_06")))

    add(ctx(
        "o1S_w9o34Ao", 2, "executed_runner_management_context", "SOLUSDT", "short", "10:29-13:05", "809|871|918", "16:30-17:00 approximate",
        "previous day low/61.8 근방까지 continuation 가능성을 열어두고, worst case는 이미 locked profit, best case는 session-long dump라고 설명.",
        "locked near $2,000; day around $7,000 active; later taken off", "bearish momentum이 강해 이전 저점/61.8까지 열어둠",
        "parabolic move에서 premature exit를 피하되 high 위로 stop walking",
        "SOL", "Fib 61.8 and possible final reversal area", "runner 관리와 alert/gym 운영 샘플",
        "previous day low, 61.8 area, parabolic move, final reversal area", "이미 진입된 short를 유지; 새 entry보다 management",
        "stop을 lower high 위로 계속 내리고 alert 설정, gym 중에도 trade play out", "best/worst case를 명확히 말하고 risk-free 상태라 기다림",
        "took trade off when enough/profit protected", "let_runner_continue_to_pdl_618_when_profit_locked", "stop above latest lower high",
        "runner final exact PnL은 trade log 총합으로 확인", ("auto_07", "auto_08", "auto_09")))

    add(ctx(
        "o1S_w9o34Ao", 3, "executed_small_profit_context", "SOLUSDT", "short", "14:13-15:18", "1033|1098", "later session",
        "새 SOL short가 entry에서 좋은 response를 줬지만 volatility가 커서 position 안쪽으로 risk를 줄이고 $321 정도만 lock.",
        "about +$321 / basically break-even", "큰 수익 후 추가 trade는 보수적으로 risk 축소",
        "response는 좋지만 volatility가 크면 full loss를 피하고 작은 profit으로 방어",
        "SOL", "Elliott/Fib secondary", "큰 winning day 후 overtrading 방지용 risk compression",
        "entry response, volatility, continuation hope", "short entry after response off setup",
        "position 안으로 stop을 넣어 full loss 차단, 1:3/1:4 가능하면 close", "좋은 move지만 day profit을 지키려 함",
        "locked $321, effectively BE; day still around +$7,800", "after_big_win_reduce_risk_fast_on_extra_trade", "flip back above entry/setup",
        "exact entry는 프레임상 read 가능하나 좌표 검증 전 frame_relative", ("auto_10", "auto_11")))

    add(ctx(
        "o1S_w9o34Ao", 4, "conditional_reversal_long_context", "SOLUSDT", "long", "15:29-20:48", "1098", "late session",
        "마지막 trade 후보. SOL이 계속 downtrend였지만 lows에서 support, BOS/CHoCH up이 나오고 massive support로 dip하면 long을 보겠다고 함.",
        "complete setup; final result not emphasized", "상위 bearish가 목표 area에 도달하면 reversal long도 조건부 허용",
        "downtrend 중에도 support + BOS/CHoCH + FVG/support retest가 나오면 long 전환",
        "SOL", "wave target 도달 후 reversal idea", "bearish day에서 long 전환 조건을 분리",
        "support lows, break of structure, CHoCH, massive support retest", "dip back into support after BOS/CHoCH long",
        "support가 hold하고 high를 다시 밀면 관리; support 이탈은 invalid", "마지막 trade라고 선을 긋고 무리하지 않음",
        "setup relation complete; result less explicit than earlier winners", "reversal_long_after_downtrend_requires_support_plus_bos_choch", "support retest failure/new low",
        "결과가 recap에서 덜 직접적이므로 rule relation sample로 사용", ("auto_11",), gold_status="v03_gold_actionable_context_ready"))

    add(ctx(
        "tUEQDc56pKE", 1, "executed_winner_context", "BTCUSDT|SOLUSDT", "short", "00:00-02:13", "13", "session opening clip",
        "Bitcoin weakness와 level break를 보면 session-wide opportunity가 열릴 수 있다고 말하고, 두 번째 파트에서 +$3,766 lock.",
        "+$3,766 on second part", "daily bias 설명 직전 opening proof trade. BTC weakness가 전체 bearish day 가능성을 제공",
        "low/level break가 나오면 runner를 열어두고 partial/second part로 수익 확정",
        "BTC weakness as bias, SOL likely execution from frame/log", "Elliott not primary", "opening clip에서도 macro-to-execution 관계가 확인됨",
        "Bitcoin weakness, break underneath level, session opportunity", "break under level triggers short continuation or management of already-filled short",
        "second part close로 profit lock; 나머지는 trend-follow", "weakness가 더 진행되면 큰 기회라고 봄",
        "fully out, second part +$3,766", "btc_weakness_level_break_short_runner_partial_exit", "reclaim above broken level",
        "opening clip이라 entry 전 상세는 제한되지만 result/management는 완결", ("auto_01",)))

    add(ctx(
        "tUEQDc56pKE", 2, "strategy_explainer_to_trade_context", "BTCUSDT|SOLUSDT", "mixed_or_conditional", "02:53-07:03", "263|544", "morning",
        "daily bias 뒤 trend break와 fair value gap을 기본 모델로 설명. risk contained, winners open-ended, 5R 예시.",
        "framework sample; live trade risk-free context", "daily bias로 하루 방향을 먼저 잡고 lower timeframe FVG로 실행",
        "trend break -> FVG target -> contained risk -> move in direction이면 open-ended",
        "BTC for bias, SOL/ETH for execution", "Elliott not primary", "전략 설명이 실제 trade 관리와 연결됨",
        "trend break, fair value gaps, risk contained, winners run", "trend가 한 방향으로 깨지고 FVG로 되돌리면 entry",
        "risk-free 전환 후 TP는 위쪽 liquidity/equal highs 또는 runner", "처음부터 full TP 고정이 아니라 day direction이면 runner",
        "risk-free trade context; no standalone PnL", "daily_bias_then_trend_break_fvg_entry_open_ended_winner", "trend reclaim opposite side",
        "구체 trade와 explainer가 섞여 있어 rule framework row로 둠", ("auto_02", "auto_03"), gold_status="v03_gold_actionable_context_ready"))

    add(ctx(
        "tUEQDc56pKE", 3, "executed_winner_context", "SOLUSDT", "short", "10:12-16:38", "792|848|896", "13:12-16:38 approximate",
        "low break/capitulation 이후 bearish direction으로 SOL short runner. loss가 있는 상태라 risk reduction을 공격적으로 하고 1:2에서 partial.",
        "locked $1,400; floating total up to about $4,300 during move", "daily/bearish direction이 실제 1분봉 low break로 확인됨",
        "capitulation low break가 나오면 stop을 lower high 위로 낮추고 partial/runner",
        "SOL", "Elliott not primary", "bearish daily bias가 1m capitulation으로 실행되는 핵심 샘플",
        "low break, capitulation, lower high, bearish direction, FVG/trend", "short after break underneath low/level",
        "loss on table 때문에 빠르게 risk reduce, 1:2에서 partial, 이후 lower highs 따라 stop walking", "trade가 잘 가면 lunch를 먹으며 runner 유지",
        "locked $1,400 and later floating $4,300 while still dropping", "bearish_bias_low_break_capitulation_short_trail_lower_highs", "push back above latest lower high / reclaim broken low",
        "entry exact는 프레임/OHLCV 후속 산출", ("auto_04", "auto_05", "auto_06")))

    add(ctx(
        "tUEQDc56pKE", 4, "executed_or_reassessed_context", "SOLUSDT|ETHUSDT", "long_to_short_reassessment", "16:30-20:47", "1140|1377", "late afternoon",
        "새 trade에서 candles가 line 위로 close하면 uptrend confirm으로 risk reduce하려 했지만, 원하는 turn이 안 나오고 ETH short가 진짜 move였다고 평가 수정.",
        "mixed; session still about +$4,600 before trade 7", "큰 winner 이후에도 다음 setup은 confirmation close가 필요",
        "long 전환은 candle close over line이 필요. 실패하면 ETH relative weakness short로 생각을 바꿈",
        "ETH short becomes preferred over SOL idea", "Elliott not primary", "실시간 의견 변경/종목 전환 샘플",
        "line close confirmation, failed turn, ETH short relative move", "uptrend confirm close over line before risk reduce",
        "confirm되면 stop을 scoop up; 안 되면 trade idea abandoned/reassessed", "ETH short from above was the move라고 즉시 반성",
        "not the desired turn; reassessment before trade seven", "require_close_confirmation_for_reversal_else_switch_to_relative_weakness", "failure to close over confirmation line",
        "이 row는 result보다 실시간 thesis change가 핵심", ("auto_07",), gold_status="v03_gold_actionable_context_ready"))

    add(ctx(
        "tUEQDc56pKE", 5, "executed_final_trade_context", "ETHUSDT|SOLUSDT", "short", "20:27-27:04", "1377", "evening/pre-dinner",
        "shower 후 trade number seven 탐색. 50% win rate라도 큰 winner 덕분에 +$4,600임을 설명하고, 후반 trade log에서 총 +$3,307로 마감.",
        "final session around +$3,307", "하루 후반에는 수익 보전과 trade quality가 우선",
        "screeners를 켜두고 dinner 전 quality setup만 추가. 이미 winning day라 profit protection",
        "ETH/SOL compared; ETH weakness noted earlier", "Elliott not primary", "winning day 후반 추가 진입/중단 기준",
        "trade seven, screener, relative weakness, profit lock", "quality setup only before dinner",
        "profit lock, avoid giving back too much after +$4,600", "수익 중이어도 계속 trade하되 quality threshold를 높임",
        "recap/log frame shows +$3,307 area", "late_day_after_big_win_only_quality_setup_profit_protection", "low-quality/no confirmation after prior winners",
        "trade 7의 세부 entry는 후속 프레임 확대 가능", ("auto_08",)))

    add(ctx(
        "1zmixRfB8co", 1, "executed_winner_then_be_context", "ETHUSDT", "short", "00:00-04:06", "66|226", "opening",
        "ETH short가 fill되고 momentum이 좋아 +$4,500까지 갔지만, 세션 설명상 이후 여러 손실/BE가 발생. 좋은 setup도 home-run 욕심이면 되돌림을 맞을 수 있음.",
        "up about $4,500 unrealized; later not banked as day loses", "losing day에도 첫 setup 자체는 quality로 시작",
        "momentum short는 runner를 노리지만 profit protection이 늦으면 BE/손실 day가 될 수 있음",
        "ETH", "Elliott not primary", "좋은 setup과 나쁜 day outcome을 분리하는 샘플",
        "ETH momentum, good setup, filled short, runner attempt", "momentum into area, fill short",
        "let run but should manage against reversal; no fixed early TP", "홈런을 노리다 되돌림 리스크가 커짐",
        "unrealized +$4,500; day later negative", "quality_short_can_fail_as_outcome_if_profit_not_protected", "strong reversal through entry/structure",
        "초기 clip이라 정확한 exit와 연결은 후속 context에 포함", ("auto_01",)))

    add(ctx(
        "1zmixRfB8co", 2, "executed_loss_sequence_context", "ETHUSDT", "long", "03:22-07:11", "382|515|586", "morning",
        "trade 2/3 부근. initial response는 있었지만 가격을 flip시키려면 더 많은 momentum이 필요했고, RSI divergence/FVG long도 실패해 세 번째 loss를 journal.",
        "third loss; would normally terminate session", "세션이 손실로 기울면서 risk containment와 session stop rule이 중요",
        "RSI divergence + FVG는 reversal hint지만 candle close와 momentum이 부족하면 실패",
        "ETH", "Elliott not primary; RSI divergence used", "negative reversal-long sample",
        "RSI divergence, fair value gap, candle close, failed momentum", "candle close after divergence could trigger FVG long",
        "3 losses in a row threshold. 실패 시 session termination이 원칙", "영상을 위해 계속하지만 원래라면 quit이라고 말함",
        "third contained loss journaled", "rsi_divergence_fvg_long_requires_momentum_and_three_loss_stop", "no flip/momentum after fill; third consecutive loss",
        "trade 2와 trade 3이 일부 겹쳐 sequence context로 통합", ("auto_02", "auto_03", "auto_04")))

    add(ctx(
        "1zmixRfB8co", 3, "executed_break_even_management_context", "ETHUSDT", "long", "08:16-08:47", "676", "afternoon",
        "이전 trade가 +$7,000까지 갔지만 home run을 노리다 level response 후 break-even으로 종료.",
        "break-even after +$7,000 unrealized", "손실일수록 큰 winner로 만회하려는 심리가 생김",
        "home run attempt는 가능하지만 중요 level response가 나오면 profit protection을 강화해야 함",
        "ETH", "Elliott not primary", "profit-taking/BE management negative sample",
        "major unrealized profit, response off level, break-even exit", "already in trade; no new entry",
        "level response가 나오면 stop/profit lock을 더 빠르게 조정", "좋은 ideas는 있었지만 chart가 잘 맞지 않는다고 평가",
        "took off for break-even", "after_large_unrealized_profit_do_not_allow_full_be_without_structure_reason", "response off opposing level and reclaim against position",
        "진입 근거는 앞 row와 이어짐", ("auto_05",)))

    add(ctx(
        "1zmixRfB8co", 4, "no_fill_no_chase_context", "ETHUSDT", "mixed_or_conditional", "09:14-14:44", "734", "afternoon",
        "order가 거의 fill될 뻔했지만 price가 떠나고, 아이디어는 맞아도 chase하지 않고 frustration을 통제한다고 말함.",
        "no fill / no chase", "losing day에서 감정 추격을 막는 risk rule",
        "confluence와 맞아도 entry가 안 오면 추격하지 않는다. quality setup만 대기",
        "ETH", "Elliott not primary", "완전 setup이지만 미체결인 gold rule sample",
        "order in, confluences agree, near fill, price runs without fill", "limit/order at planned level only",
        "fill missed이면 chase 금지, 다음 setup 대기", "frustration을 인식하고 pocket에 머문다고 말함",
        "missed trade; no executed result", "if_limit_missed_do_not_chase_even_if_idea_works", "price leaves entry zone without fill",
        "결과 PnL은 없지만 setup-intention 관계가 완결", ("auto_06",), gold_status="v03_gold_actionable_context_ready"))

    add(ctx(
        "1zmixRfB8co", 5, "conditional_flip_context", "ETHUSDT", "short_to_long_conditional", "10:31-16:01", "811", "late session",
        "ETH retest area에서 short response를 기대하지만, upside breakout이 나오면 하루 종일 보던 ETH downtrend의 big push/long flip도 평가하겠다고 함.",
        "final trade context; title day still -$2,428 despite late attempts", "손실일의 마지막 구간은 빠른 방향 고집보다 full direction change 확인",
        "retest short가 기본. 단, breakout/CHoCH가 나오면 downtrend long flip으로 전환",
        "ETH", "Elliott not primary", "양방향 conditional decision tree",
        "retest area, coiling price, downtrend, breakout flip, potential long", "short response at retest; alternate long only after upside breakout",
        "short 실패/상방 돌파 시 thesis switch. 손실 누적이 있어 risk 엄격", "quick flip으로 day를 recover하려는 욕구와 규칙 사이를 조절",
        "not enough clean profit to avoid losing-day title", "primary_retest_short_alternate_long_only_after_breakout_flip", "no response at retest or breakout against short",
        "마지막 PnL 세부는 더 확대 필요", ("auto_07",), gold_status="v03_gold_actionable_context_ready"))

    return rows


def build_hold_rows() -> list[dict[str, str]]:
    return []


def audit_rows(contexts: list[dict[str, str]], sessions: list[dict[str, str]]) -> list[dict[str, str]]:
    out = []
    by_video: dict[str, list[dict[str, str]]] = {video_id: [] for video_id in BATCH_IDS}
    for row in contexts:
        by_video.setdefault(row["video_id"], []).append(row)
    session_ids = {row["video_id"] for row in sessions}
    for video_id in BATCH_IDS:
        rows = by_video.get(video_id, [])
        mix = Counter(row["gold_status"] for row in rows)
        out.append(
            {
                "video_id": video_id,
                "video_title": progress_value(video_id, "video_title"),
                "context_rows": str(len(rows)),
                "status_mix": "; ".join(f"{k}:{v}" for k, v in sorted(mix.items())),
                "has_session_row": "yes" if video_id in session_ids else "no",
                "has_local_frames": "yes" if contacts(video_id) else "no",
                "v03_quality_note_ko": "로컬 SRT 정독 후보, 원본 프레임, 실제 시장 날짜, 1m OHLCV 캐시를 연결해 v0.3 필드로 정리. price exact는 일부 frame_relative로 남김.",
            }
        )
    return out


def append_without_batch(main_file: str, batch_rows: list[dict[str, str]], fields: list[str]) -> None:
    path = PROCESSED / main_file
    old = [row for row in read_csv(path) if row.get("video_id") not in set(BATCH_IDS)]
    write_csv(path, old + batch_rows, fields)


def main() -> None:
    sessions = build_sessions()
    ready_contexts = build_contexts()
    hold_contexts = build_hold_rows()
    all_contexts = ready_contexts + hold_contexts
    rules = [rule_from_context(row) for row in ready_contexts]
    audit = audit_rows(ready_contexts, sessions)

    write_csv(PROCESSED / "gold_v03_batch_01_video_session_maps.csv", sessions, SESSION_FIELDS)
    write_csv(PROCESSED / "gold_v03_batch_01_trade_context_queue.csv", ready_contexts, CTX_FIELDS)
    write_csv(PROCESSED / "gold_v03_batch_01_hold_context_queue.csv", hold_contexts, CTX_FIELDS)
    write_csv(PROCESSED / "gold_v03_batch_01_all_context_queue.csv", all_contexts, CTX_FIELDS)
    write_csv(PROCESSED / "gold_v03_batch_01_rule_seed_queue.csv", rules, RULE_FIELDS)
    write_csv(PROCESSED / "gold_v03_batch_01_quality_audit.csv", audit, AUDIT_FIELDS)

    append_without_batch("gold_v03_video_session_maps.csv", sessions, SESSION_FIELDS)
    append_without_batch("gold_v03_trade_context_queue.csv", ready_contexts, CTX_FIELDS)
    append_without_batch("gold_v03_hold_context_queue.csv", hold_contexts, CTX_FIELDS)
    combined_ready = read_csv(PROCESSED / "gold_v03_trade_context_queue.csv")
    combined_hold = read_csv(PROCESSED / "gold_v03_hold_context_queue.csv")
    write_csv(PROCESSED / "gold_v03_all_context_queue.csv", combined_ready + combined_hold, CTX_FIELDS)
    append_without_batch("gold_v03_rule_seed_queue.csv", rules, RULE_FIELDS)

    old_audit = [row for row in read_csv(PROCESSED / "gold_v03_quality_audit.csv") if row.get("video_id") not in set(BATCH_IDS)]
    write_csv(PROCESSED / "gold_v03_quality_audit.csv", old_audit + audit, AUDIT_FIELDS)

    summary_lines = [
        "# v0.3 Batch 01 - 7 Oldest Remaining Videos",
        "",
        f"- sessions added: {len(sessions)}",
        f"- gold/actionable contexts added: {len(ready_contexts)}",
        f"- hold contexts added: {len(hold_contexts)}",
        f"- rule seed rows added: {len(rules)}",
        "",
        "| upload order | video_id | title | market date | contexts | note |",
        "|---:|---|---|---|---:|---|",
    ]
    by_video_count = Counter(row["video_id"] for row in ready_contexts)
    for video_id in BATCH_IDS:
        summary_lines.append(
            f"| {progress_value(video_id, 'local_index_oldest_first')} | {video_id} | {progress_value(video_id, 'video_title')} | {DATES[video_id][0]} | {by_video_count[video_id]} | frame+SRT+OHLCV v0.3 integrated |"
        )
    OUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    OUT_SUMMARY.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(
        f"batch01 sessions={len(sessions)} contexts={len(ready_contexts)} hold={len(hold_contexts)} rules={len(rules)} summary={OUT_SUMMARY}"
    )


if __name__ == "__main__":
    main()
