from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "gold_context_trades"
FRAME_MANIFEST = ROOT / "data" / "source" / "craig_frames" / "local_v03_batch_03" / "local_v03_batch_03_frame_manifest.json"
QUALITY_INPUTS = ROOT / "outputs" / "craig_quality_tracker_v0_3" / "quality_tracker_inputs.json"
OUT_SUMMARY = ROOT / "outputs" / "v03_batch_03_7_video_summary.md"

BATCH_IDS = [
    "6DUOPBNmR7A",
    "9-zrNcDeGeo",
    "KB4vL1x9ZcM",
    "cIryRKYMiT4",
    "7j5JrAfmM-s",
    "MDRzCMqETZw",
    "a7x0yKL6jkI",
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

VIDEO_DATES = {
    "6DUOPBNmR7A": {
        "session_dates": "2026-02-06",
        "default_date": "2026-02-06",
        "confidence": "high_user_verified_and_frame_bottom_axis_fri_06_feb_26_utc_minus5_tradezella",
    },
    "9-zrNcDeGeo": {
        "session_dates": "2026-02-26",
        "default_date": "2026-02-26",
        "confidence": "high_frame_tradezella_thu_feb_26_2026_and_bottom_axis_utc_minus5",
    },
    "KB4vL1x9ZcM": {
        "session_dates": "2026-03-18",
        "default_date": "2026-03-18",
        "confidence": "high_user_verified_and_frame_bottom_axis_wed_18_mar_26_utc_minus4",
    },
    "cIryRKYMiT4": {
        "session_dates": "2026-04-16",
        "default_date": "2026-04-16",
        "confidence": "high_frame_tradezella_filter_apr_16_2026_and_bottom_axis_utc_minus4",
    },
    "7j5JrAfmM-s": {
        "session_dates": "2026-05-06",
        "default_date": "2026-05-06",
        "confidence": "high_user_verified_and_tradezella_day_view_wed_may_06_2026_utc_minus4",
    },
    "MDRzCMqETZw": {
        "session_dates": "2026-05-28",
        "default_date": "2026-05-28",
        "confidence": "high_user_verified_and_tradezella_entry_05_28_2026_utc_minus4",
    },
    "a7x0yKL6jkI": {
        "session_dates": "2026-07-22",
        "default_date": "2026-07-22",
        "confidence": "high_frame_tradezella_day_view_wed_jul_22_2026_and_bottom_axis_utc_minus4",
    },
}


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


def progress_value(video_id: str, key: str) -> str:
    return PROGRESS.get(video_id, {}).get(key, "")


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


def ohlcv_note(date_text: str, symbols: str) -> str:
    checks = []
    for date in [part.strip() for part in date_text.split("|") if part.strip()]:
        for symbol in [part.strip() for part in symbols.split("|") if part.strip()]:
            path = ROOT / "data" / "raw" / "binance_futures_live_dates" / date / f"{symbol}_1m_{date}_ny.csv"
            checks.append(f"{date} {symbol}: {'있음' if path.exists() else '없음'}({path.as_posix()})")
    return "NY local 기준 1분봉 캐시 확인. " + "; ".join(checks)


def session(
    video_id: str,
    symbols: str,
    macro: str,
    scenario: str,
    selection: str,
    wave: str,
    risk: str,
    notes: str,
) -> dict[str, str]:
    meta = VIDEO_DATES[video_id]
    p = PROGRESS[video_id]
    return {
        "session_context_id": f"{video_id}_session_v03_batch03",
        "video_id": video_id,
        "video_title": p["video_title"],
        "local_index_oldest_first": p["local_index_oldest_first"],
        "source_stage_v03": "v0_3_batch_03_local_srt_frame_ohlcv",
        "market_dates_utc_minus4": meta["session_dates"],
        "primary_symbols": symbols,
        "confirmed_timeframes": "1m execution visible; 15m split/HFT/daily or 30m exchange pane when shown",
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
    *,
    decision_type: str,
    symbol: str,
    direction: str,
    youtube_window: str,
    anchor_seconds: str,
    market_time: str,
    visible_note: str,
    realized_result: str,
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
    exit_result: str,
    rule_seed: str,
    invalidation: str,
    uncertainty: str,
    labels: tuple[str, ...],
    market_date: str | None = None,
    entry_price: str = "frame_relative_or_about",
    stop_price: str = "frame_relative_or_about",
    target_price: str = "frame_relative_or_about",
    chart_timeframe: str = "1m",
    gold_status: str = "v03_gold_trade_context_ready",
) -> dict[str, str]:
    meta = VIDEO_DATES[video_id]
    date_text = market_date or meta["default_date"]
    symbols_for_data = "BTCUSDT|ETHUSDT|SOLUSDT"
    return {
        "context_id": f"{video_id}_v03_batch03_{n:02d}",
        "session_context_id": f"{video_id}_session_v03_batch03",
        "video_id": video_id,
        "video_title": progress_value(video_id, "video_title"),
        "local_index_oldest_first": progress_value(video_id, "local_index_oldest_first"),
        "source_stage_v03": "v0_3_batch_03_local_srt_frame_ohlcv",
        "decision_type": decision_type,
        "gold_status": gold_status,
        "symbol": symbol,
        "direction": direction,
        "chart_timeframe": chart_timeframe,
        "market_date_utc_minus4": date_text,
        "market_time_window_utc_minus4": market_time,
        "visible_chart_time_note": visible_note,
        "market_time_confidence": meta["confidence"],
        "youtube_window": youtube_window,
        "anchor_seconds": anchor_seconds,
        "entry_price": entry_price,
        "stop_price": stop_price,
        "target_price": target_price,
        "realized_result": realized_result,
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
        "frame_evidence_paths": evidence(video_id, *labels),
        "ohlcv_alignment_ko": ohlcv_note(date_text, symbols_for_data),
        "rule_feature_vector_seed_ko": rule_seed,
        "invalidation_condition_ko": invalidation,
        "remaining_uncertainty_ko": uncertainty,
    }


def rule_from_context(row: dict[str, str]) -> dict[str, str]:
    text = f"{row['decision_type']} {row['realized_result']}".lower()
    negative = ""
    if "hold" in row["gold_status"]:
        negative = "검증보류 샘플"
    elif "no_fill" in row["decision_type"] or "pass" in row["decision_type"] or "conditional" in row["decision_type"]:
        negative = "미체결/패스/조건부 setup 샘플"
    elif "loss" in text or "손실" in row["realized_result"] or "-$" in row["realized_result"]:
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
            "6DUOPBNmR7A",
            "BTCUSDT|SOLUSDT|ETHUSDT",
            "초반 BTC daily lower support와 전체 selloff를 먼저 본다. 전일 큰 하락 때문에 macro는 조심스럽지만, open 직전에는 upside reversal도 가능하다고 보고 SOL/ETH의 1m response를 기다린다.",
            "주된 분기는 두 개다. 1) lower support에서 반응하고 15m bearish FVG로 올라가면 long/upside scalp 가능. 2) macro selloff와 fundamental headline이 다시 힘을 얻으면 higher-timeframe area rejection에서 short 또는 risk-off 관리.",
            "SOL이 실제 박스와 TradeZella 결과가 가장 명확하다. ETH는 watchlist/상대 강도 비교이고 BTC는 daily support/macro anchor다.",
            "명시적 Elliott count는 중심이 아니다. HFT 5m/15m vs 1H/4H 혼재, lower support, 15m bearish FVG, liquidity inflection high/low, prior structure가 핵심이다.",
            "첫날 큰 risk를 넣었다고 언급하고, fundamental 변동이 보이면 TP1 miss 후 stop을 BE로 당기는 등 빠른 리스크 제거를 우선한다. gym/외출 때문에 early exit를 선택한 맥락도 포함된다.",
            "2026-02-06 UTC-5 프레임에서 SOL 1m/15m, TradeZella short +$9,374.04, later dashboard/runner context가 확인됨.",
        ),
        session(
            "9-zrNcDeGeo",
            "SOLUSDT|BTCUSDT|ETHUSDT",
            "경제 캘린더에 high-impact news가 없다는 점을 먼저 확인하고, 특정 방향을 단정하지 않는다. 15m midpoint rejection, FVG, red zone break/close 여부를 보며 시장이 먼저 방향을 말하게 둔다.",
            "초반에는 area break를 기다리고, no-fill이면 추격하지 않는다. 중반에는 HTF FVG/resistance까지 뛴 long을 크게 먹고, 후반에는 red zone 아래로 닫히면 lower gap까지 short로 따라가는 분기다.",
            "SOL 실행이 전부 프레임과 TradeZella row로 확인된다. BTC/ETH는 시장 동조성과 exchange ticker 정도로 보조.",
            "Elliott보다는 HTF FVG midpoint, resistance, red zone, gap target, consolidation partial/BE가 주된 구조다.",
            "큰 size에서 감정적 흔들림을 직접 언급한다. 그래서 6R 이상이 뜨면 partial/close를 적극적으로 검토하고, slippage $400 같은 execution cost도 모델 입력으로 분리한다.",
            "2026-02-26 UTC-5 TradeZella Day View에서 +$17,183, 3 trades, rows: long -$176, long +$11,357, short +$6,002가 확인됨.",
        ),
        session(
            "KB4vL1x9ZcM",
            "SOLUSDT|BTCUSDT|ETHUSDT",
            "세션 초반에는 하락장 속에서도 15m FVG/CHoCH와 1m pullback response를 연결한다. 단순히 방향을 맞추는 것보다 position size, fill quality, slippage까지 결과를 좌우한다고 말한다.",
            "초기 thesis가 맞아도 units가 틀리면 작은 이익으로 끝날 수 있다. 이후 missed pullback/no chase, full loss, slippage loss, 그리고 final short winner까지 같은 날의 의사결정 흐름이 이어진다.",
            "SOL 1m/15m split이 실행 중심. TradeZella/Notion rows가 모든 결과를 SOLUSD로 표시한다.",
            "Elliott count는 거의 나오지 않고, 15m FVG, CHoCH, BOS, liquidity line, FVG midpoint, swing low close 여부가 핵심이다.",
            "중간 손실과 slippage를 감수해도, 남은 edge가 있으면 trade five까지 진행한다. 다만 missed order block은 chasing하지 않고 trade off table 처리한다.",
            "2026-03-18 UTC-4. TradeZella/Notion row에서 5 trades, final net +$10,999.41, rows +$345, -$2,706, +$7,789, -$2,566, +$8,137.41이 확인됨.",
        ),
        session(
            "cIryRKYMiT4",
            "SOLUSDT|BTCUSDT|ETHUSDT",
            "주간 목표 +$20K 대비 현재 +$9.7K이고 다음 날은 거래하지 않을 예정이라는 목표/시간 제약이 있다. BTC daily major support, 75k 위 break, 88k까지 열리는 bullish scenario, HTF bearish FVG/critical support를 큰 지도처럼 둔다.",
            "초반에는 order가 한 틱 차이로 miss/cancel되면 기다리고, 구조 break나 lower break가 나오기 전까지 인내한다. 이후 high-opportunity technical area에서 long response, Asia volume/order block, late FVG/sweep branch로 확장된다.",
            "SOL이 대부분 실행 중심이고 BTC는 daily support/breakout map이다. ETH는 watchlist로 섞이지만 프레임상 SOL 박스가 우세하다.",
            "Elliott가 명시적 도구로 크게 보이진 않지만, impulse leg extension, liquidity line, order block, sweep/FVG가 파동적 위치 판단을 대신한다. 이 영상은 파동 숫자보다 daily map과 intraday structure가 강하다.",
            "하루 목표가 있어도 좋은 edge가 남으면 멈추지 않고, 동시에 make-shift/bad trade는 스스로 낮은 품질로 분류한다. 기회가 크면 risk를 정상화하고, 애매하면 주문을 취소한다.",
            "2026-04-16 UTC-4. TradeZella Apr 16 필터와 bottom axis가 일치하며, 1m/15m SOL 프레임 및 rows가 확인됨.",
        ),
        session(
            "7j5JrAfmM-s",
            "SOLUSDT|BTCUSDT|ETHUSDT",
            "최근 losing streak 뒤의 세션이라 revenge가 아니라 quality setup만 보겠다고 전제한다. macro recap에서는 BTC가 200-day MA라는 institutional level을 테스트하고 resistance/rejection을 보였다고 정리한다.",
            "처음에는 sweep/continuation long을 보지만 너무 late이면 조심한다. 이후 CHoCH, FVG tap, BOS/retest로 long winner를 만들고, 후반에는 HTF FVG 안의 midpoint/low break를 이용한 short continuation으로 분기한다.",
            "SOL 실행이 전부다. BTC는 200-day MA와 macro resistance context를 제공한다.",
            "명시적 Elliott는 약하고, 구조 완성(structure completion), HTF gap, sweep, CHoCH, BOS, FVG, trendline/PDH가 핵심이다.",
            "losing streak 후에도 좋은 세팅이면 risk를 쓰되, daily goal 달성 뒤에도 과도한 revenge 없이 quality만 유지한다. 최종 dashboard는 +$10,570.1, 6 trades, 2 wins/4 losses를 보여준다.",
            "2026-05-06 UTC-4. Day View +$5,529.4 중간 상태와 Dashboard +$10,570.1 최종 상태가 둘 다 프레임으로 확인되어 세션 진행 상태를 분리 기록.",
        ),
        session(
            "MDRzCMqETZw",
            "ETHUSDT|SOLUSDT|BTCUSDT",
            "이 영상은 ETH 중심이다. 세션 초반부터 lower delivery/short 가능성을 보고, FVG가 생겨도 봉이 닫히기 전에는 확정으로 취급하지 않는다고 말한다.",
            "초반 short plan은 61.8 area와 resistance/FVG에서 출발한다. 이후 가격이 추세적으로 위로 밀리면 state of delivery 변화로 보고, confirmed CHOCH/close below low가 나오기 전까지 성급히 반대하지 않는다.",
            "ETH chart/Bybit/TradeZella가 모두 명확하다. SOL은 ticker 또는 이전 세션 배경 정도다.",
            "Elliott 숫자보다 61.8 fib level, FVG close, CHOCH, low close confirmation, exhaustion/opposite delivery가 중심이다.",
            "두 손실, 두 BE, 한 win 이후에도 다음 확실한 reversal/continuation만 기다린다. second lot lock, 1:4 lock, runner management가 핵심.",
            "2026-05-28 UTC-4. ETH sell entry 09:40, later long TradeZella net +$3,874.83, replay runner/1:4 box가 확인됨.",
        ),
        session(
            "a7x0yKL6jkI",
            "SOLUSDT|ETHUSDT|BTCUSDT",
            "초반에는 15m broader picture와 1m execution을 분리해서 설명한다. ETH 15m wedge/triangle과 SOL 15m FVG/PDH/PDL 위치를 보고, 실제 실행은 SOL 1m FVG/CHoCH midpoint에서 한다.",
            "시나리오는 short rejection 또는 long continuation 둘 다 열어둔다. 좋은 long winner 뒤에도 두 손실이 나오지만, 그는 손실 자체가 아니라 edge가 끝났는지 여부로 다음 trade를 판단한다.",
            "SOL이 실제 winner/loss rows의 중심이다. ETH는 15m macro structure 예시로 등장한다.",
            "이 영상은 Elliott labels (1)-(5)가 차트에 보이고, wedge/triangle, liquidity line, FVG, PDH/PDL과 결합된다. 파동 카운트는 목표/과열 판단의 보조 신호다.",
            "두 loss와 두 win 구조에서 winners는 크게, losses는 작게 유지하는 session continuation 원칙이 선명하다. Day View 최종은 4 trades, 2/2, net +$15,712.62로 보인다.",
            "2026-07-22 UTC-4. TradeZella Day View와 chart bottom axis가 일치하며, main long +$10,852.44 및 후반 loss rows가 확인됨.",
        ),
    ]


def build_contexts() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    add = rows.append

    add(ctx(
        "6DUOPBNmR7A", 1,
        decision_type="session_macro_actionable_setup_context",
        symbol="BTCUSDT|SOLUSDT",
        direction="conditional_long_then_short_risk",
        youtube_window="02:37-07:07",
        anchor_seconds="217|293|383",
        market_time="pre-open to 10:23 NY local UTC-5",
        visible_note="Frames around 10m23 show Fri 06 Feb '26, SOL 1m/15m split, HFT 5m/15m bullish and 1H/4H bearish, lower support and 15m bearish FVG zones.",
        realized_result="actionable setup map; later trades execute both risk-on and risk-off branches",
        session_macro="BTC daily lower support and prior selloff create caution, but he still allows upside if the open responds from support.",
        scenario_tree="If SOL holds lower support and pushes into 15m bearish FVG, long/upside continuation is tradable. If macro selloff resumes, avoid fighting it and prefer short/risk-off.",
        selection="SOL is chosen because its lower-timeframe response is cleaner and visible on both 1m and 15m panes.",
        wave="No explicit Elliott count; lower support plus HFT mixed stack replaces wave thesis.",
        thesis="Do not impose bearish macro immediately; wait for price action at support and FVG.",
        structure="BTC daily support, SOL lower support shelf, 15m bearish FVG overhead, liquidity inflection high/low.",
        setup="The setup is complete once support response plus 1m structure appears; fill is secondary to the map.",
        entry="Prepare long only after support response/pullback; prepare short if the inflection area fails and macro selloff expands.",
        management="Use macro as throttle. If move is late or TP1 is missed, lower risk and protect quickly.",
        live_changes="He starts cautious from selloff, then accepts upside opportunity, then later becomes defensive when fundamental selling appears.",
        exit_result="This row is the day map feeding the later executed short and early-exit runner contexts.",
        rule_seed="daily_support_plus_15m_fvg_map; trade_support_response_long_until_macro_selling_reclaims_control",
        invalidation="Support response fails or price rejects before entering the 15m FVG branch.",
        uncertainty="Macro plan is complete; no standalone fill/result by design.",
        labels=("auto_01", "auto_02", "auto_03"),
        gold_status="v03_gold_actionable_context_ready",
    ))
    add(ctx(
        "6DUOPBNmR7A", 2,
        decision_type="executed_short_winner_context",
        symbol="SOLUSDT",
        direction="short",
        youtube_window="04:53-11:49",
        anchor_seconds="623|709",
        market_time="around 14:00 NY local UTC-5 visible",
        visible_note="Frame 10m23 shows TradeZella SOLUSD Fri Feb 06 2026 short, net P&L $9,374.04, SOL 1m/15m split and short target box.",
        realized_result="TradeZella short net P&L $9,374.04; gross $9,622.04, commissions/fees $248",
        session_macro="Macro selloff is still active enough that he warns not to fight it too much.",
        scenario_tree="If liquidity inflection fails and downside starts moving, short continuation toward lower box is valid. If the pullback holds, skip or protect.",
        selection="SOL short is explicit in TradeZella and chart box.",
        wave="No Elliott; liquidity inflection and FVG/structure break dominate.",
        thesis="After the late/inflection move, downside momentum aligns with macro risk-off and creates the short.",
        structure="Inflection high/low, 1m break, blue profit box below, red stop shelf above, HFT mixed with higher TF bearish.",
        setup="He waits for the response/pullback area, sees price fail and expand lower, and treats it as a contained short rather than a blind macro short.",
        entry="Frame-relative SOL short after the inflection failure; exact entry in TradeZella not fully readable.",
        management="Because TP1 was nearly missed and headline/fundamental selling is present, reduce risk and move stop to BE quickly.",
        live_changes="He shifts from 'possible upside' to 'do not fight macro' as selling accelerates.",
        exit_result="Closed short winner for +$9,374.04 net.",
        rule_seed="short_when_liquidity_inflection_fails_during_macro_riskoff; reduce_risk_after_tp1_or_headline_volatility",
        invalidation="Reclaim above failed inflection/FVG area or failure to extend after entry.",
        uncertainty="Exact fill price is frame-relative; result and direction are fully visible.",
        labels=("auto_03", "auto_04"),
    ))
    add(ctx(
        "6DUOPBNmR7A", 3,
        decision_type="risk_management_after_fundamental_move_context",
        symbol="SOLUSDT",
        direction="short",
        youtube_window="06:19-11:49",
        anchor_seconds="709",
        market_time="post-entry, same Feb 06 NY afternoon UTC-5",
        visible_note="Frame 10m23/near 11m49 shows large downside move and short position management; SRT mentions fundamental happening, TP1 missed, risk off/BE.",
        realized_result="risk reduced / BE protection after winner leg",
        session_macro="Fundamental selling changes the quality of the move from normal technical continuation to headline/risk-off.",
        scenario_tree="If move keeps dropping, hold runner. If bounce/reclaim starts, do not let a large winner turn into avoidable loss.",
        selection="SOL remains selected because live position is active.",
        wave="No Elliott; risk management is driven by realized movement and missed TP1.",
        thesis="After entry, the trade edge is no longer just setup quality; volatility source and missed partial matter.",
        structure="TP1 zone, entry/BE line, expanding downside leg, higher-timeframe bearish backdrop.",
        setup="Executed setup has already worked; the context is whether to hold or neutralize.",
        entry="No new entry; convert existing position to protected state.",
        management="Take risk off, stop to break-even, do not add while headline volatility is unresolved.",
        live_changes="He becomes more conservative because the market is moving on a fundamental catalyst.",
        exit_result="Winner protected; exact runner close is included in broader day result.",
        rule_seed="after_fast_move_from_catalyst_if_tp1_missed_move_stop_be_and_reduce_exposure",
        invalidation="A protected trade should not be allowed to become a fresh full-risk idea.",
        uncertainty="Exact partial fill not isolated, but management logic is explicit and visible.",
        labels=("auto_04",),
        gold_status="v03_gold_actionable_context_ready",
    ))
    add(ctx(
        "6DUOPBNmR7A", 4,
        decision_type="early_exit_runner_context",
        symbol="SOLUSDT",
        direction="long_or_reversal_runner",
        youtube_window="14:20-20:27",
        anchor_seconds="1100",
        market_time="around 14:51 NY local UTC-5 visible",
        visible_note="Frame 18m20 shows Fri 06 Feb '26 14:51, SOL 1m/15m split, large blue runner box, high 88.57 and higher-timeframe response zone.",
        realized_result="early exit; would have run materially further according to recap",
        session_macro="Higher-timeframe area response creates a runner opportunity despite earlier selloff.",
        scenario_tree="If the higher-timeframe response holds, runner can continue. If leaving desk/gym increases execution risk, early exit is acceptable but opportunity cost must be logged.",
        selection="SOL remains the execution symbol.",
        wave="No explicit Elliott; response from high-timeframe support/resistance zone is the main read.",
        thesis="A higher-timeframe reaction after the risk-off move can produce a reversal/runner, but only if he can manage it.",
        structure="Large blue target box, high-timeframe response zone, local high at 88.57, 1m/15m alignment table.",
        setup="He has a valid runner setup but closes early because of practical management constraints.",
        entry="Existing/recent position only; no fresh entry price is isolated in the frame.",
        management="If unable to manage, close rather than leave unmanaged; log that this sacrifices potential upside.",
        live_changes="He recognizes afterward that the early exit cost was large, but the decision was tied to attention/risk capacity.",
        exit_result="Early exit kept profit but missed a larger move; this becomes a process rule, not a signal failure.",
        rule_seed="if_valid_runner_but_attention_unavailable_close_or_hard_protect; track_opportunity_cost_separately",
        invalidation="Runner thesis invalid if high-timeframe response fails or price loses the box base.",
        uncertainty="Exact P&L for this runner not isolated; context is complete as management/exit rule.",
        labels=("auto_05",),
        gold_status="v03_gold_actionable_context_ready",
    ))

    add(ctx(
        "9-zrNcDeGeo", 1,
        decision_type="executed_small_initial_loss_context",
        symbol="SOLUSDT",
        direction="long",
        youtube_window="03:27-08:57",
        anchor_seconds="537|954",
        market_time="10:44 open row, Thu Feb 26 NY local UTC-5 visible in day view",
        visible_note="Frame 15m54 day view shows Thu Feb 26 2026 row 10:44 SOLUSD LONG -$176; earlier frame shows area-break plan and 15m midpoint rejection context.",
        realized_result="SOLUSD long -$176",
        session_macro="No high-impact news means the day is more technical and less catalyst-driven.",
        scenario_tree="Wait for area break. If the first long cannot hold after midpoint/rejection context, accept small loss and reset.",
        selection="SOL has the clearest intraday structure and all TradeZella rows.",
        wave="No Elliott; 15m midpoint/rejection and area break are the filters.",
        thesis="Initial long is only valid if it breaks/holds the area instead of rejecting.",
        structure="15m midpoint, area break line, local support/rejection shelf.",
        setup="He does not force direction; the first attempt is a low-damage probe around the level.",
        entry="TradeZella row confirms a SOL long at 10:44; exact price not readable.",
        management="Cut quickly when the area does not confirm; small loss keeps the day open.",
        live_changes="After the failed/flat early attempt, he waits for a cleaner response rather than revenge trading.",
        exit_result="Closed for -$176, negligible relative to later winners.",
        rule_seed="when_no_news_day_area_break_probe_fails_exit_small_and_wait_for_cleaner_structure",
        invalidation="Failure to hold above the break/midpoint level.",
        uncertainty="Exact entry/stop hidden; direction/time/result are visible.",
        labels=("auto_01", "auto_04"),
    ))
    add(ctx(
        "9-zrNcDeGeo", 2,
        decision_type="no_fill_missed_order_context",
        symbol="SOLUSDT",
        direction="long_or_continuation",
        youtube_window="04:33-10:03",
        anchor_seconds="603",
        market_time="between 10:44 loss and 13:41 winner, NY local UTC-5",
        visible_note="Contact sheet and SRT show order missed/no fill, would have reached daily goal, then he waits for another shorter-timeframe response.",
        realized_result="no fill; no chase",
        session_macro="No catalyst day increases the importance of precise fills at technical levels.",
        scenario_tree="If order fills at response level, take the planned trade. If missed and price runs, do not chase; wait for another structure.",
        selection="SOL remains selected, but execution discipline overrides desire.",
        wave="No Elliott; response level and shorter-timeframe trigger are the complete setup.",
        thesis="A valid setup can be learned even if it never fills; fill quality is part of Craig's edge.",
        structure="Response level, consolidation/level break, projected daily goal target.",
        setup="Order is placed at the technical level; price misses it by a small amount and runs.",
        entry="Limit order only; no executed entry.",
        management="Mark as opportunity cost, not a trade. Avoid emotional chase after seeing it would have paid.",
        live_changes="He stays patient after frustration, waiting for a new level rather than reusing a stale order.",
        exit_result="No trade result; the setup/result relationship is recorded as no-fill.",
        rule_seed="if_limit_at_response_level_misses_and_price_runs_do_not_chase_wait_new_structure",
        invalidation="Missed fill plus price already extended beyond planned R.",
        uncertainty="Exact missed price is not readable; spoken no-fill context is complete.",
        labels=("auto_02",),
        gold_status="v03_gold_actionable_context_ready",
    ))
    add(ctx(
        "9-zrNcDeGeo", 3,
        decision_type="executed_large_long_winner_context",
        symbol="SOLUSDT",
        direction="long",
        youtube_window="08:10-13:40",
        anchor_seconds="537|820",
        market_time="13:41 open row, Thu Feb 26 NY local UTC-5 visible",
        visible_note="Frame 08m57 shows TradeZella SOLUSD Thu Feb 26 2026 long net P&L $11,357, crypto traded 9550, 1m/15m split and HFT table.",
        realized_result="SOLUSD long +$11,357 net; gross $11,625, fees $268",
        session_macro="Technical day with no high-impact news allows a clean level-to-FVG move.",
        scenario_tree="If price accepts above the response level and runs into HTF FVG/resistance, ride the move but partial/close once R is large.",
        selection="SOL has the cleanest fill/result and visible HFT mixed-but-supportive state.",
        wave="No Elliott; HTF FVG midpoint and resistance are the main targets.",
        thesis="After the no-fill patience reset, a clean long into HTF FVG/resistance provides the day's main edge.",
        structure="HTF FVG midpoint, resistance above, consolidation shelf, 1m trend leg.",
        setup="The long is taken after shorter-timeframe response confirms and price begins moving toward the high-timeframe imbalance.",
        entry="TradeZella confirms open at 13:41; exact price hidden by UI.",
        management="At 6.3R and emotional size pressure, take off/partial instead of demanding perfect top.",
        live_changes="He explicitly notices emotion from bigger size and manages the trade more defensively.",
        exit_result="Closed for +$11,357 net, the first large winner of the day.",
        rule_seed="long_after_clean_response_into_htf_fvg; at_6r_plus_with_size_emotion_partial_or_close",
        invalidation="Loss of the response shelf or rejection before acceptance into the HTF FVG.",
        uncertainty="Exact stop/TP hidden; result and setup relation are complete.",
        labels=("auto_01", "auto_03"),
    ))
    add(ctx(
        "9-zrNcDeGeo", 4,
        decision_type="executed_late_short_winner_context",
        symbol="SOLUSDT",
        direction="short",
        youtube_window="10:44-18:01",
        anchor_seconds="954",
        market_time="19:16 open row, Thu Feb 26 NY local UTC-5 visible",
        visible_note="Frame 15m54 shows day view +$17,183, row 19:16 SOLUSD SHORT +$6,002 and chart bottom Thu 26 Feb '26 18:33 UTC-5.",
        realized_result="SOLUSD short +$6,002; full day net +$17,183",
        session_macro="After the long winner, he still trades the next edge if red-zone breakdown creates a new short opportunity.",
        scenario_tree="If price dumps/breaks red zone and closes below, target lower gap for about 4R. If it cannot close below, protect or scratch.",
        selection="SOL remains active and liquid enough for late-day continuation.",
        wave="No Elliott; red zone break/close and lower gap target are the trigger-target pair.",
        thesis="A new bearish branch is valid only after price accepts below the red zone, not because the previous long is finished.",
        structure="Red zone, lower gap target, consolidation partial area, BE/trailing line.",
        setup="He waits for candle close below the marked red zone, then uses the lower gap as the objective.",
        entry="Short row at 19:16; exact price hidden.",
        management="Account for about $400 slippage, move to BE after acceptance, and take partials around consolidation/support.",
        live_changes="He remains willing to flip from big long winner to short if the structure changes.",
        exit_result="Closed short winner +$6,002; daily +$17,183 across 3 trades.",
        rule_seed="short_after_red_zone_break_and_close_target_lower_gap; slippage_cost_tracked; be_after_acceptance",
        invalidation="No close below red zone or reclaim above breakdown shelf.",
        uncertainty="Exact order price hidden, but TradeZella row/result and chart branch are visible.",
        labels=("auto_04",),
    ))

    add(ctx(
        "KB4vL1x9ZcM", 1,
        decision_type="executed_correct_thesis_wrong_size_context",
        symbol="SOLUSDT",
        direction="long",
        youtube_window="06:44-12:14",
        anchor_seconds="584|734",
        market_time="13:25 frame time, Wed Mar 18 NY local UTC-4; early rows visible",
        visible_note="Frame 12m14 shows SOL position open, Notion rows +$345 and -$2,706, Wed Mar 18 2026 bottom axis and UTC-4.",
        realized_result="Small win around +$345 because thesis/fill was not sized as intended; later row shows -$2,706 loss",
        session_macro="Bearish broader market, but he still trades pullback/reversal if the level response is clean.",
        scenario_tree="If the thesis is right and position size is correct, let it run. If sizing is wrong, treat result separately from signal quality.",
        selection="SOL is selected because the 1m/15m split has clear CHoCH/FVG structure.",
        wave="No Elliott; liquidity line, CHoCH and FVG response are the frame-confirmed features.",
        thesis="The market read can be correct while execution/position units make the realized result poor.",
        structure="1m liquidity line, local CHoCH, small FVG support, overhead target box, 15m FVG backdrop.",
        setup="Long attempt after pullback/reversal structure; thesis points upward but order sizing is off.",
        entry="SOL long around the visible 88.98 area; exact trade row not fully isolated.",
        management="Let the position trail only if the execution matches plan; otherwise record the sizing error.",
        live_changes="He separates 'I was right about direction' from 'I failed the trade implementation'.",
        exit_result="Logged as small win/then early sequence loss, not as a strategy failure alone.",
        rule_seed="tag_signal_quality_and_execution_quality_separately; wrong_units_do_not_invalidate_thesis",
        invalidation="Loss of entry/FVG shelf or inability to execute planned size.",
        uncertainty="Transcript references +$588 while visible log shows +$345; store as small-win sizing-error context.",
        labels=("auto_02",),
    ))
    add(ctx(
        "KB4vL1x9ZcM", 2,
        decision_type="no_chase_missed_pullback_context",
        symbol="SOLUSDT",
        direction="short_or_pullback",
        youtube_window="08:09-13:39",
        anchor_seconds="669|759",
        market_time="13:12-13:39 NY local UTC-4 visible",
        visible_note="Frames 11m09/12m39 show large projected box after sharp drop and later pullback area; SRT says missed entry/full profit and not chasing.",
        realized_result="missed setup; no chase",
        session_macro="Fast selloff creates opportunity but also late-entry risk.",
        scenario_tree="If pullback returns to the level/order block, enter. If price runs without filling, skip instead of forcing late entry.",
        selection="SOL remains the clean execution market.",
        wave="No Elliott; order block/pullback and lower target are complete.",
        thesis="A perfect setup that is missed is still a rule seed: no fill means no trade if risk/reward is gone.",
        structure="Pullback level/order block, lower TP1/support target, liquidity line.",
        setup="He waits for price to return to the planned area after the impulse instead of chasing the impulse itself.",
        entry="Only at planned pullback/order block; otherwise no entry.",
        management="No management because no trade. Log opportunity cost and wait for another setup.",
        live_changes="He resists the urge to enter because the move would already have hit target.",
        exit_result="No fill, no realized result.",
        rule_seed="after_missed_pullback_do_not_chase_if_target_would_already_be_hit",
        invalidation="Price too extended from entry zone or risk/reward compressed.",
        uncertainty="Exact planned order price not readable, but pass logic is explicit.",
        labels=("auto_03",),
        gold_status="v03_gold_actionable_context_ready",
    ))
    add(ctx(
        "KB4vL1x9ZcM", 3,
        decision_type="executed_midday_long_winner_context",
        symbol="SOLUSDT",
        direction="long",
        youtube_window="10:42-17:37",
        anchor_seconds="792|1065",
        market_time="around 17:59 row shown later, Wed Mar 18 NY local UTC-4",
        visible_note="Frames 13m12/17m25 show SOL long boxes, BE/target lines, later Notion rows including +$7,789 and -$2,566.",
        realized_result="SOL long +$7,789 visible in final row set",
        session_macro="He wants momentum only after price moves through the level enough to reduce risk.",
        scenario_tree="If price pushes through level, reduce risk and target next liquidity. If it cannot close/hold, avoid increasing exposure.",
        selection="SOL is the active intraday product.",
        wave="No Elliott; 15m FVG and 1m CHoCH/BOS are the filters.",
        thesis="A long is valid after the flush response if price proves itself by moving up through the decision level.",
        structure="15m FVG, 1m CHoCH, FVG shelf, next liquidity target, BE line.",
        setup="He waits for a push through the level before reducing risk; the move then becomes a runner/partial candidate.",
        entry="Frame-relative long from the response shelf; exact price not isolated.",
        management="Move to BE only after sufficient swing/level break, then target next liquidity.",
        live_changes="He becomes more conservative about BE timing: do not reduce just because price ticks in favor, wait for structure.",
        exit_result="Final Notion row set includes +$7,789 long winner.",
        rule_seed="long_after_15m_fvg_choch_response; be_after_structural_level_break_not_before",
        invalidation="Failure to hold FVG/CHoCH shelf or no break through the risk-reduction level.",
        uncertainty="Specific row matching is inferred from final visible log, but direction/setup/result are consistent.",
        labels=("auto_04", "auto_05"),
    ))
    add(ctx(
        "KB4vL1x9ZcM", 4,
        decision_type="executed_slippage_loss_context",
        symbol="SOLUSDT",
        direction="long",
        youtube_window="14:25-19:55",
        anchor_seconds="1032|1135",
        market_time="Mar 18 late afternoon/evening NY local UTC-4",
        visible_note="Frames 17m25/18m55 show active SOL setup and final Notion rows; SRT says another trade stopped full loss and previous trade with slippage lost $2,566.",
        realized_result="SOL long -$2,566 with slippage/full-loss context",
        session_macro="Even with earlier profit, he treats bad fill/slippage as execution drag rather than changing the whole market thesis.",
        scenario_tree="If 15m FVG/CHoCH after flush gives response, enter. If the response fails and stop slips, take full loss and reassess.",
        selection="SOL remains because the 15m FVG response is visible.",
        wave="No Elliott; FVG/CHoCH and swing low are the decisive features.",
        thesis="A valid setup can still lose because fill quality and continuation fail.",
        structure="15m FVG, 1m swing low, stop shelf, liquidity/target above.",
        setup="He enters after response but requires aggressive selling/buying confirmation to keep holding.",
        entry="Frame-relative long; exact fill not readable.",
        management="Do not reduce risk until swing low/confirmation breaks; accept full loss when stop is hit.",
        live_changes="He notes the setup quality but does not excuse the slippage. The loss is logged as part of the day's process.",
        exit_result="Final visible row set includes -$2,566 loss.",
        rule_seed="valid_setup_can_be_loss_if_no_structural_confirmation; slippage_tagged_as_execution_feature",
        invalidation="Stop hit or failure to break the confirming swing low/high.",
        uncertainty="Exact stop price hidden; P&L row and spoken slippage are clear.",
        labels=("auto_05", "auto_06"),
    ))
    add(ctx(
        "KB4vL1x9ZcM", 5,
        decision_type="executed_final_short_winner_context",
        symbol="SOLUSDT",
        direction="short",
        youtube_window="16:20-22:57",
        anchor_seconds="1195|1310",
        market_time="around 17:59-22:08 NY local UTC-4 visible",
        visible_note="Frame 21m50/21m57 show final rows: 5 trades, 60% win, sum +$10,999.41, selected SOL short +$8,137.41 and large blue short box.",
        realized_result="SOL short +$8,137.41; day net +$10,999.41",
        session_macro="After several trades, he still takes a clean final short if structure completes.",
        scenario_tree="If response off FVG produces aggressive selling and swing low closes/breaks, hold short to support/TP. If no close below swing, do not reduce or overstate confirmation.",
        selection="SOL final short is visible in row and chart.",
        wave="No Elliott; FVG response, swing low close, support partials, BOS are the rules.",
        thesis="The short is valid only after the market proves downside with aggressive selling and swing-low break.",
        structure="15m/1m FVG, swing low, support target, large blue short box, stop shelf above.",
        setup="Price responds from FVG, rejects upward continuation, and then breaks toward support.",
        entry="Final SOL short row; exact entry hidden, visible box has stop above and target below.",
        management="Take half partials at support, lock half, and only reduce risk after the swing low truly breaks/closes.",
        live_changes="He corrects himself: a break without a candle close is not enough to reduce yet.",
        exit_result="Closed final short +$8,137.41; full day +$10,999.41.",
        rule_seed="short_fvg_response_requires_aggressive_selling_and_swing_low_close; partial_at_support_lock_half",
        invalidation="Failure to close below swing low or reclaim above FVG/rejection shelf.",
        uncertainty="Entry/SL exact prices not readable, but final result and management logic are visible.",
        labels=("auto_07", "auto_08"),
    ))

    add(ctx(
        "cIryRKYMiT4", 1,
        decision_type="daily_macro_trade_plan_context",
        symbol="BTCUSDT|SOLUSDT",
        direction="conditional_bullish_breakout",
        youtube_window="00:31-06:27",
        anchor_seconds="237|327",
        market_time="pre-open to 10:13 NY local UTC-4",
        visible_note="Frame 03m57 shows Apr 16 2026 filter, SOL 1m/15m, HFT bullish, CHoCH/FVG zones; SRT details BTC daily major support and breakout scenario.",
        realized_result="actionable macro map for the session",
        session_macro="BTC is sitting around major daily support with a possible breakout above 75k and pathway toward 88k, while HTF bearish FVG/critical support defines the risk map.",
        scenario_tree="If BTC/SOL accept above the key area, favor long continuation. If the level rejects or breaks lower, wait for lower-break structure instead of forcing the breakout.",
        selection="BTC sets direction; SOL provides the executable 1m/15m setup.",
        wave="No explicit count, but the breakout-to-88 idea is an extension path from daily support.",
        thesis="Macro support plus intraday CHoCH/FVG response creates a bullish candidate, but only after intraday confirmation.",
        structure="BTC daily support/breakout level, SOL CHoCH, 15m FVG, green support shelves.",
        setup="The plan is to wait for price to prove acceptance through the area before entering.",
        entry="No automatic entry from macro; entry waits for SOL response/FVG fill.",
        management="If breakout branch triggers, reduce risk after level holds; if not, stand aside.",
        live_changes="He starts with scenarios rather than a fixed direction, because tomorrow is a no-trade day and he wants quality.",
        exit_result="This is the macro context feeding later long/late setups.",
        rule_seed="daily_major_support_breakout_map_plus_1m_fvg_confirmation_required",
        invalidation="Failure to accept above key support/breakout or lower-break continuation against the plan.",
        uncertainty="Macro map is fully spoken and visually supported; no standalone fill.",
        labels=("auto_01", "auto_02"),
        gold_status="v03_gold_actionable_context_ready",
    ))
    add(ctx(
        "cIryRKYMiT4", 2,
        decision_type="no_fill_cancelled_order_context",
        symbol="SOLUSDT",
        direction="long_or_breakout",
        youtube_window="08:10-11:34",
        anchor_seconds="544|634",
        market_time="around 09:30-10:34 NY local UTC-4",
        visible_note="Frames 09m04/10m34 show SOL 1m position planning and SRT says order missed/cancelled by a fraction, then waits for break lower or structure breakout.",
        realized_result="missed/cancelled order; no trade",
        session_macro="The daily bullish plan is valid only if intraday structure gives a clean fill.",
        scenario_tree="If limit fills at the level, trade the response. If price misses by a fraction, cancel/wait for a fresh structural break.",
        selection="SOL setup is clean enough to plan but not to chase.",
        wave="No Elliott; fill discipline at FVG/order area is the rule.",
        thesis="A near-fill is not an executed edge; the same context should be logged as no-fill, not backfilled as a win.",
        structure="Local order area, break lower alternative, structure breakout alternative.",
        setup="He has a complete setup but refuses to enter after price runs away.",
        entry="Limit order only; cancelled/missed by small amount.",
        management="No position management; reset to next structural trigger.",
        live_changes="He explicitly chooses patience after the miss.",
        exit_result="No realized result; setup is useful for rule learning.",
        rule_seed="if_order_missed_by_fraction_cancel_and_wait_for_new_breakout_or_lower_break",
        invalidation="No fill and price extended beyond planned risk/reward.",
        uncertainty="Exact missed price not visible; spoken context is complete.",
        labels=("auto_03", "auto_04"),
        gold_status="v03_gold_actionable_context_ready",
    ))
    add(ctx(
        "cIryRKYMiT4", 3,
        decision_type="executed_long_response_context",
        symbol="SOLUSDT",
        direction="long",
        youtube_window="10:47-14:11",
        anchor_seconds="647|791",
        market_time="around 14:17 NY local UTC-4 visible later in row set",
        visible_note="Frames 11m41/13m17 show SOL long box, HFT bullish, FVG/support response and later Notion rows including a +$9,773 win.",
        realized_result="large SOL long winner visible in row set (+$9,773 row appears in frames)",
        session_macro="Macro momentum is supportive once the high-opportunity technical area responds.",
        scenario_tree="If price responds from the FVG/high-opportunity area and closes over the high, move to BE and let target work. If no close/acceptance, keep risk on until invalidation or exit.",
        selection="SOL is selected for the clean bullish response and visible row set.",
        wave="No explicit Elliott; impulse extension from support is the relevant wave-like behavior.",
        thesis="The missed order is followed by a cleaner response trade where macro and intraday structure align.",
        structure="FVG response, local high/close trigger, long box, HFT 5m/15m/1H/4H bullish in frames.",
        setup="Long after price responds from the area and begins moving with macro momentum.",
        entry="Frame-relative SOL long; exact fill hidden.",
        management="Only move to BE after candle closes over the high. Do not reduce risk prematurely.",
        live_changes="He emphasizes the need for a close, not just a wick, before declaring safety.",
        exit_result="Visible row set contains the large winner, and the title/day confirms major profit.",
        rule_seed="long_high_opportunity_fvg_response_with_macro_momentum; be_after_close_over_high",
        invalidation="Failure to close over high or loss of response/FVG shelf.",
        uncertainty="Exact row matching is partial; setup, direction, and large-winner outcome are frame-supported.",
        labels=("auto_05", "auto_06"),
    ))
    add(ctx(
        "cIryRKYMiT4", 4,
        decision_type="lower_quality_make_shift_trade_context",
        symbol="SOLUSDT",
        direction="mixed_or_long",
        youtube_window="20:26-26:01",
        anchor_seconds="1236|1471",
        market_time="later Apr 16 session, NY local UTC-4",
        visible_note="Frames 23m06/24m31/26m01 show later SOL boxes and TradeZella row set; SRT calls one setup makeshift/bad while volume/trend may still break resistance.",
        realized_result="mixed later trades; lower-quality trade identified by Craig",
        session_macro="After being up on the day, he does not stop automatically, but quality threshold still matters.",
        scenario_tree="If resistance top breaks with volume/uptrend, continuation can work. If the setup is makeshift and at resistance, downgrade quality and avoid overconfidence.",
        selection="SOL remains active, but selection alone is not enough without quality.",
        wave="No explicit Elliott; volume/uptrend and resistance break are the features.",
        thesis="This is a process-quality sample: a trade can have some confluence yet still be lower quality.",
        structure="Resistance top, trend/volume push, FVG/order area, visible later boxes.",
        setup="He recognizes the trade is not as clean as prior high-opportunity setups.",
        entry="Frame-relative; not elevated to exact fill rule.",
        management="If taken, manage more tightly and avoid expanding risk because setup quality is lower.",
        live_changes="He self-labels the trade quality rather than retrofitting it as perfect.",
        exit_result="Stored as mixed/lower-quality context, not a clean outcome exemplar.",
        rule_seed="downgrade_makeshift_trade_even_if_directional_confluence_exists; quality_score_feature",
        invalidation="Resistance rejection or failure of volume/uptrend continuation.",
        uncertainty="Exact result row not isolated; context is used for quality-classification rule.",
        labels=("auto_07", "auto_08"),
        gold_status="v03_gold_actionable_context_ready",
    ))
    add(ctx(
        "cIryRKYMiT4", 5,
        decision_type="late_sweep_fvg_branch_context",
        symbol="SOLUSDT",
        direction="conditional_short_or_continuation",
        youtube_window="26:31-31:15",
        anchor_seconds="1681|1815",
        market_time="late Apr 16 session, NY local UTC-4",
        visible_note="Frames 28m01/29m10/30m15/31m15 show consolidated lows, sweep/FVG boxes, later long and short scenarios, and Apr 16 row set.",
        realized_result="actionable late-session branch; final outcome not isolated to one row",
        session_macro="Late session still follows the same daily map, but liquidity and Asia-volume behavior matter more.",
        scenario_tree="If consolidated lows sweep and FVG accepts lower, continue down hard. If price reclaims/holds, the move can continue higher instead.",
        selection="SOL remains the execution symbol.",
        wave="Order block and sweep/FVG replace explicit wave count; impulse continuation is the target behavior.",
        thesis="The late setup is not a single-direction prediction; it is a branch around sweep and FVG acceptance.",
        structure="Consolidated lows, sweep level, FVG, order block candle, downside target box and reclaim branch.",
        setup="Wait for break/acceptance rather than entering in the middle of the consolidation.",
        entry="Conditional entry only after sweep/FVG branch confirms.",
        management="If accepted lower, hold for big continuation; if reclaimed, abandon short branch quickly.",
        live_changes="He explicitly keeps both 'continue higher' and 'huge way down' possibilities open.",
        exit_result="No single executed result isolated; branch logic is complete for rules.",
        rule_seed="late_session_sweep_plus_fvg_acceptance_branch; do_not_enter_mid_consolidation",
        invalidation="Reclaim above swept/FVG level for short branch or loss of reclaim for long branch.",
        uncertainty="Used as conditional setup row; final trade row not isolated.",
        labels=("auto_09", "auto_10", "auto_11"),
        gold_status="v03_gold_actionable_context_ready",
    ))

    add(ctx(
        "7j5JrAfmM-s", 1,
        decision_type="macro_after_losing_streak_context",
        symbol="BTCUSDT|SOLUSDT",
        direction="conditional",
        youtube_window="00:42-06:54",
        anchor_seconds="300|414",
        market_time="pre-open to 10:16 NY local UTC-4",
        visible_note="Frame 05m00 shows Wed 06 May '26, SOL 1m/15m, HFT bullish, BTC tab and TradeZella add trade pane; recap later cites BTC 200-day MA institutional level.",
        realized_result="session map after losing streak",
        session_macro="BTC is around 200-day MA/resistance, so macro can reject even while SOL intraday HFT shows bullish rows.",
        scenario_tree="If sweep/continuation holds and FVG taps cleanly, long. If BTC institutional resistance rejects and SOL loses structure, be ready for short.",
        selection="SOL is the execution vehicle; BTC gives the institutional resistance context.",
        wave="No explicit Elliott; structure completion and HTF gap are the wave-equivalent context.",
        thesis="After losing streak, only take quality setups that line up with structure, not revenge impulses.",
        structure="BTC 200-day MA, SOL 1m/15m split, sweep, FVG, trendline, PDH/PDL.",
        setup="Session plan waits for CHoCH/FVG tap rather than immediately buying the first push.",
        entry="No standalone entry; this is the session rule map.",
        management="Keep normal process despite losing streak; do not stop seeing valid setups.",
        live_changes="He frames the day as process recovery, not forcing a comeback.",
        exit_result="Feeds the two-phase day: mid-day +$5,529.4, final +$10,570.1.",
        rule_seed="after_losing_streak_require_quality_setup_btc_200dma_macro_context_plus_sol_structure",
        invalidation="Macro rejection plus SOL structure loss or late/chased entry.",
        uncertainty="Macro note is from recap plus frames; complete as session context.",
        labels=("auto_01", "auto_02", "auto_09"),
        gold_status="v03_gold_actionable_context_ready",
    ))
    add(ctx(
        "7j5JrAfmM-s", 2,
        decision_type="executed_initial_long_loss_context",
        symbol="SOLUSDT",
        direction="long",
        youtube_window="06:54-09:59",
        anchor_seconds="414|599",
        market_time="09:33 row, Wed May 06 NY local UTC-4 visible",
        visible_note="Frame 14m57 day view later shows 09:33 SOLUSD LONG -$2,416.6; earlier frames show sweep/continuation long idea around FVG.",
        realized_result="SOLUSD long -$2,416.6",
        session_macro="Early bullish HFT does not override the need for clean timing.",
        scenario_tree="If sweep continuation is late or fails to hold support/FVG, take the loss and wait for better CHoCH/tap.",
        selection="SOL trade row and chart are explicit.",
        wave="No Elliott; sweep, FVG tap, support hold are the features.",
        thesis="The first attempt captures the idea but is too late/weak, so it becomes a controlled loss.",
        structure="Sweep level, FVG, local support, long box from early session.",
        setup="Long attempt after sweep/continuation but before the later cleaner retest.",
        entry="TradeZella row at 09:33; exact price hidden.",
        management="Accept loss; do not revenge after losing streak.",
        live_changes="He stays process-focused and waits for the cleaner retest/structure.",
        exit_result="Closed for -$2,416.6.",
        rule_seed="if_sweep_continuation_long_is_late_or_support_fails_accept_loss_then_wait_cleaner_retap",
        invalidation="Loss of FVG/support or no continuation after sweep.",
        uncertainty="Exact entry/stop hidden; row/result visible.",
        labels=("auto_02", "auto_04"),
    ))
    add(ctx(
        "7j5JrAfmM-s", 3,
        decision_type="executed_clean_long_winner_context",
        symbol="SOLUSDT",
        direction="long",
        youtube_window="09:59-14:57",
        anchor_seconds="737|897",
        market_time="10:23 row, Wed May 06 NY local UTC-4 visible",
        visible_note="Frame 14m57 shows Day View Wed May 06 2026 net +$5,529.4, row 10:23 SOLUSD LONG +$7,946; chart shows BOS/retest/long box.",
        realized_result="SOLUSD long +$7,946; interim day net +$5,529.4 after two trades",
        session_macro="After first loss, the clean structural long is still valid because the setup quality improves.",
        scenario_tree="If CHoCH/FVG tap holds and price breaks over midpoint/gap, long toward high-timeframe targets. If it loses the tap, stop under low.",
        selection="SOL structure is clear and matches TradeZella row.",
        wave="Structure completion/HTF gap, not numeric Elliott, is the path.",
        thesis="The better version of the earlier long appears after CHoCH and FVG tap.",
        structure="CHoCH, FVG tap, BOS over level, two retests, stop under low, PDH/HTF targets.",
        setup="Waited for CHoCH, tapped FVG, held support, broke upside and retested twice.",
        entry="SOL long row at 10:23; visible box stop under low and target above.",
        management="Push over highs, move stop under low, lock 1R, partials as it advances.",
        live_changes="He distinguishes this from the earlier late loss: same direction, much cleaner confirmation.",
        exit_result="Closed +$7,946; recovers first loss and creates positive day.",
        rule_seed="long_after_choch_fvg_tap_bos_retest_twice; stop_under_low; partials_and_1r_lock",
        invalidation="Failure to hold FVG tap/retest or loss below stop-under-low.",
        uncertainty="Exact price not readable; row/result and box are visible.",
        labels=("auto_03", "auto_04"),
    ))
    add(ctx(
        "7j5JrAfmM-s", 4,
        decision_type="executed_mtf_fvg_short_sequence_context",
        symbol="SOLUSDT",
        direction="short",
        youtube_window="17:59-25:15",
        anchor_seconds="1079|1297|1447|1515",
        market_time="late May 06 session, final dashboard 21:56 NY local UTC-4 visible",
        visible_note="Frames 17m59/20m09/24m07/25m15 show high-impact MTF FVG short boxes; final dashboard frame 25m36/25m42 shows +$10,570.1 day, 6 trades, 2 wins/4 losses.",
        realized_result="later short sequence contributes to final net +$10,570.1; exact row isolation not fully visible",
        session_macro="BTC institutional resistance/rejection gives permission to consider downside even after a long winner.",
        scenario_tree="If price fills midpoint of FVG inside HTF FVG and closes below low, short continuation toward flush. If it reclaims, move BE or cut.",
        selection="SOL remains active; short is based on the cleanest MTF FVG.",
        wave="No Elliott; HTF gap inside gap, CHoCH below low, and flush target are the rules.",
        thesis="A bearish branch becomes valid once price rejects the high-impact FVG and breaks down.",
        structure="HTF FVG, midpoint of FVG, low close/CHoCH, gap target, BE/trail line.",
        setup="Short fill in high-impact area; he wants close below low and then momentum flush.",
        entry="Frame-relative short in MTF FVG zone.",
        management="At nearly 2R move SL to BE; aim for big flush but protect after close criteria.",
        live_changes="He wants the flush but remains careful about needing an actual close/break.",
        exit_result="Final dashboard confirms day +$10,570.1; this short sequence is the late-day contributor.",
        rule_seed="short_from_mtf_fvg_midpoint_inside_htf_fvg; need_close_below_low; move_be_near_2r",
        invalidation="Reclaim above FVG midpoint/high-impact area or no close below low.",
        uncertainty="Final dashboard visible, but exact late short row P&L not isolated due dashboard view.",
        labels=("auto_05", "auto_06", "auto_07", "auto_08", "auto_09"),
    ))
    add(ctx(
        "7j5JrAfmM-s", 5,
        decision_type="process_rule_after_quality_day_context",
        symbol="SOLUSDT|BTCUSDT",
        direction="session_management",
        youtube_window="24:06-25:42",
        anchor_seconds="1536|1542",
        market_time="21:56 NY local UTC-4 dashboard visible",
        visible_note="Frame 25m42 shows TradeZella dashboard net P&L $10,570.1, trade win % 33.33, avg win/loss 5.72 and recent trades dated 05/06/2026.",
        realized_result="final day +$10,570.1, 6 trades, 2 wins/4 losses",
        session_macro="Quality setups can overcome low win rate if winners are large and losses controlled.",
        scenario_tree="After daily goal, continue only if quality remains; losing streak does not justify stopping valid edges or revenge trading.",
        selection="SOL was the only executed product.",
        wave="No Elliott; this row is session-level process.",
        thesis="Craig's copy model must include continuation permission after loss/win sequences, not only entry signals.",
        structure="Daily dashboard: 2 winners/4 losers, high avg win/loss, final positive day.",
        setup="This is not an entry setup but a session-management rule.",
        entry="No new entry.",
        management="Let large winners pay for several losses; keep taking only quality setups.",
        live_changes="He frames the day as proof of process after a losing streak.",
        exit_result="Dashboard final +$10,570.1.",
        rule_seed="session_continuation_allowed_if_quality_setups_remain_even_after_losses; avg_win_loss_feature",
        invalidation="Overtrading/revenge or taking non-quality setups after goal/losses.",
        uncertainty="Dashboard confirms totals; individual late rows remain partially hidden.",
        labels=("auto_08", "auto_09"),
        gold_status="v03_gold_actionable_context_ready",
    ))

    add(ctx(
        "MDRzCMqETZw", 1,
        decision_type="fvg_close_confirmation_filter_context",
        symbol="ETHUSDT",
        direction="conditional_short",
        youtube_window="03:13-10:56",
        anchor_seconds="500|656",
        market_time="around 09:50-10:56 NY local UTC-4",
        visible_note="Frames 05m00/08m36/10m56 show ETH 1m/15m, bearish HFT, short boxes and SRT says FVG is not established until candle closes.",
        realized_result="actionable confirmation filter before/around short attempts",
        session_macro="ETH is in bearish delivery with visible higher-timeframe FVG/resistance above.",
        scenario_tree="If candle closes and confirms FVG/resistance, short. If it wicks without close, do not count the FVG as valid.",
        selection="ETH has the clearest bearish structure and actual order panel.",
        wave="No Elliott; confirmation close and 61.8/fib area are the important filters.",
        thesis="The setup is not valid until the candle closes; incomplete FVG is only a watch condition.",
        structure="Bearish HFT, 15m FVGs overhead, local low/high, proposed short box.",
        setup="Wait for completed candle/FVG confirmation before executing.",
        entry="No automatic entry until close condition is satisfied.",
        management="Avoid front-running the FVG; this prevents false positives.",
        live_changes="He explicitly delays commitment despite seeing a possible area.",
        exit_result="Used as a filter for subsequent short/reversal trades.",
        rule_seed="fvg_valid_only_after_candle_close; no_front_run_on_unconfirmed_gap",
        invalidation="Candle fails to close in a way that defines the FVG/resistance.",
        uncertainty="Complete as a setup filter, not an executed row.",
        labels=("auto_01", "auto_02"),
        gold_status="v03_gold_actionable_context_ready",
    ))
    add(ctx(
        "MDRzCMqETZw", 2,
        decision_type="executed_eth_short_attempt_context",
        symbol="ETHUSDT",
        direction="short",
        youtube_window="10:56-14:32",
        anchor_seconds="712|872",
        market_time="09:40 entry row visible, Thu May 28 NY local UTC-4",
        visible_note="Frame 05m00 shows TradeZella Add Trade ETHUSD 05/28/2026 09:40 SELL 738 @ 1980.57, stop near 1980.80 and target near 1969.31.",
        realized_result="short attempt; later session recap says two losses/two BE/one win before final runner",
        session_macro="Bearish delivery and 61.8/resistance make a short reasonable, but not guaranteed.",
        scenario_tree="If 61.8/resistance rejects, short toward lower fill. If price breaks up through the zone, accept loss/BE and reassess.",
        selection="ETH order panel, chart, and TradeZella form are visible.",
        wave="61.8 fib level functions as the wave/fib confluence.",
        thesis="Short into resistance/FVG after bearish delivery, but only while price rejects.",
        structure="61.8 level, bearish FVG, stop shelf 1980.80, lower target 1969.31, local low.",
        setup="ETH pushes into resistance/FVG and short is placed with defined stop/target.",
        entry="SELL 738 ETHUSD @ 1980.57 visible in TradeZella form.",
        management="If it does not reject quickly or breaks up, do not hold the bearish idea.",
        live_changes="Later he acknowledges prior losses/BE before the cleaner long/reversal.",
        exit_result="Outcome not isolated to one row; treated as short-attempt context inside a mixed early session.",
        rule_seed="eth_short_at_61_8_resistance_fvg_with_defined_stop_target; abandon_if_reclaim",
        invalidation="Break/hold above 1980.80 or rejection failure.",
        uncertainty="Entry visible; exact final P&L for this attempt not isolated in frame.",
        labels=("auto_02", "auto_03"),
        gold_status="v03_gold_actionable_context_ready",
    ))
    add(ctx(
        "MDRzCMqETZw", 3,
        decision_type="executed_eth_long_reversal_winner_context",
        symbol="ETHUSDT",
        direction="long",
        youtube_window="18:11-21:42",
        anchor_seconds="1091|1302",
        market_time="12:32 NY local UTC-4 visible",
        visible_note="Frame 21m42 shows ETHUSD Thu May 28 2026 long net P&L $3,874.83, entry area around 1999.20/2000.62 and position box to PDL/target.",
        realized_result="ETHUSD long net P&L $3,874.83; gross $4,249.83, fees $375",
        session_macro="State of delivery changes as price chugs through the level/trends up after early bearish attempts.",
        scenario_tree="If price reclaims and trends up through resistance, stop forcing shorts and take long continuation. If no CHOCH/close confirmation, wait.",
        selection="ETH is confirmed by TradeZella trade detail.",
        wave="No numeric Elliott; state-change/CHOCH plus FVG reclaim are the wave-like transition.",
        thesis="A reversal/continuation long is valid after bearish delivery fails and price accepts higher.",
        structure="Reclaim level, FVG shelves, stop at 1993.32/1993.37 zone, PDL/target above, CHOCH markers.",
        setup="After early failures, price breaks up, holds the reclaimed level and creates a long box.",
        entry="ETH long around visible 1999.20/2000.62 zone; exact execution in TradeZella detail.",
        management="Lock second lot/partial and let confirmed trend work; avoid flipping short until actual close below low.",
        live_changes="He changes from bearish to bullish because the market's delivery state changes.",
        exit_result="Closed long +$3,874.83 net.",
        rule_seed="flip_long_when_bearish_delivery_fails_and_price_accepts_above_reclaim; require_choch_close_for_next_flip",
        invalidation="Loss of reclaim/FVG shelf or close back below the structure.",
        uncertainty="Exact multi-execution details hidden, but trade detail/result and chart are visible.",
        labels=("auto_04", "auto_05", "auto_06"),
    ))
    add(ctx(
        "MDRzCMqETZw", 4,
        decision_type="runner_lock_and_no_premature_choch_context",
        symbol="ETHUSDT",
        direction="long",
        youtube_window="21:42-24:12",
        anchor_seconds="1452",
        market_time="12:13-13:23 replay window, Thu May 28 NY local UTC-4",
        visible_note="Frame 24m12 replay shows long position box, open P&L about 20.12 on 641 qty, target 28.43, risk/reward 9.11, and strong move through PDL.",
        realized_result="runner/lock context; title-day profit $7,215 and trade detail winner visible",
        session_macro="Trend has shifted up, so he avoids calling CHOCH until a close below the relevant low occurs.",
        scenario_tree="If price continues through PDL and no close below low appears, keep runner/lock 1:4. If close below low occurs, stop treating it as bullish continuation.",
        selection="ETH long remains the active trade.",
        wave="No Elliott; no-CHOCH-until-close-below-low is the structural rule.",
        thesis="The profitable long should be held while structure keeps validating, not because it feels extended.",
        structure="PDL, FVG shelves beneath, long target box, no close below low, 1:4/runner overlay.",
        setup="Existing long has already worked; this context defines when to keep or exit runner.",
        entry="No new entry; maintain existing long.",
        management="Lock 1:4 and avoid premature reversal calls until close confirmation.",
        live_changes="He explicitly refuses to label a CHOCH before the candle closes below the low.",
        exit_result="Runner management supports the final profitable day.",
        rule_seed="do_not_call_choch_until_close_below_low; lock_1_to_4_then_run_if_structure_validates",
        invalidation="Close below the key low or loss of reclaimed FVG/PDL structure.",
        uncertainty="Runner final close not isolated, but management rule is visible and explicit.",
        labels=("auto_06",),
        gold_status="v03_gold_actionable_context_ready",
    ))

    add(ctx(
        "a7x0yKL6jkI", 1,
        decision_type="macro_15m_to_1m_execution_plan_context",
        symbol="ETHUSDT|SOLUSDT",
        direction="conditional",
        youtube_window="02:10-05:34",
        anchor_seconds="180|334",
        market_time="Jul 20-22 broader chart, then Jul 22 NY local UTC-4",
        visible_note="Frame 03m00 shows ETH 15m wedge/triangle, PDH/PDL, HFT bullish; frame 05m34 shows SOL 1m/15m and target FVGs/SR.",
        realized_result="session map; later SOL long executes the bullish branch",
        session_macro="He separates 15m broader picture from 1m execution. ETH wedge/triangle and SOL FVG/SR define where a trade is worth taking.",
        scenario_tree="If 15m FVG rejects and 1m CHOCH midpoint holds, short is possible. If 1m accepts and continues from FVG/support, long into PDH/FVG targets.",
        selection="ETH is used to explain broader structure; SOL is the actual execution market.",
        wave="Elliott labels (1)-(5) are visible on SOL/ETH charts and act as extension/context, not as a sole trigger.",
        thesis="A trade is copied by aligning 15m location with 1m trigger and visible FVG/SR.",
        structure="15m wedge, liquidity line, PDH/PDL, 1m FVG shelves, CHOCH midpoint.",
        setup="Wait for price to reach the pre-marked 15m/1m overlap zone before executing.",
        entry="No standalone entry; this is the top-down plan.",
        management="Use the 15m range and 1m stop shelf to keep risk contained.",
        live_changes="He is comfortable switching from short idea to long idea if the 1m trigger proves it.",
        exit_result="Feeds the main SOL long winner and later loss sequence.",
        rule_seed="top_down_15m_location_plus_1m_fvg_choch_trigger; elliott_labels_as_context_only",
        invalidation="No 1m trigger at the 15m location or break of the overlap support/resistance.",
        uncertainty="Complete session map; not an executed row.",
        labels=("session_macro_scan", "auto_01", "auto_02"),
        gold_status="v03_gold_actionable_context_ready",
    ))
    add(ctx(
        "a7x0yKL6jkI", 2,
        decision_type="executed_main_sol_long_winner_context",
        symbol="SOLUSDT",
        direction="long",
        youtube_window="07:46-10:16",
        anchor_seconds="548|616",
        market_time="10:49 open row; Wed Jul 22 NY local UTC-4 visible",
        visible_note="Frames 09m08/09m16/10m16 show SOL long box, Day View Jul 22 2026, row 10:49 SOLUSD LONG +$10,852.44 and final Trade Preview entries 77.72, 78.24, 78.96.",
        realized_result="SOLUSD long +$10,852.44; trade preview gross +$11,439.44",
        session_macro="The broader plan allows a bullish branch once SOL holds the 1m FVG/PDL zone.",
        scenario_tree="If CHOCH/FVG midpoint holds and price pushes toward PDH/upper FVG, take long and scale. If it loses stop shelf, cut.",
        selection="SOL is selected because the entry/Day View row is explicit.",
        wave="Visible Elliott labels (1)-(5) and liquidity line help judge extension; FVG/PDH are the actionable levels.",
        thesis="The main winner comes from 1m execution at a 15m-relevant FVG/support area.",
        structure="FVG shelf near 77.60-77.72, stop line 77.60/77.72 zone, PDH 78.64/78.95 area, upper target box, liquidity line.",
        setup="Price taps FVG/support after CHOCH and then expands upward, aligning with HFT bullish stack.",
        entry="Trade preview shows executions: 07-22-2026 10:49 @ 77.72, then partial/execution rows around 78.24 and 78.96.",
        management="Let first winner run; scale at marked targets instead of closing instantly.",
        live_changes="The earlier short-rejection idea is abandoned because the bullish branch triggers cleanly.",
        exit_result="Closed/recorded SOL long +$10,852.44 net.",
        rule_seed="sol_long_from_fvg_support_choch_midpoint_with_pdh_target; scale_out_at_78_24_78_96",
        invalidation="Loss of FVG/support shelf around stop or failure to push from CHOCH midpoint.",
        uncertainty="Day View and preview are visible; exact stop label partly hidden but stop shelf is clear.",
        labels=("auto_03", "auto_04"),
    ))
    add(ctx(
        "a7x0yKL6jkI", 3,
        decision_type="executed_two_loss_reset_context",
        symbol="SOLUSDT",
        direction="long_and_short_losses",
        youtube_window="12:58-16:56",
        anchor_seconds="778|1016",
        market_time="13:23 and 13:30 rows, Wed Jul 22 NY local UTC-4 visible",
        visible_note="Frame 16m56 shows Day View Jul 22 with rows 13:23 SOLUSD LONG -$2,722.9 and 13:30 SOLUSD SHORT -$2,872.92 after the main long winner.",
        realized_result="SOLUSD long -$2,722.9; SOLUSD short -$2,872.92",
        session_macro="After a big win, the market continues up through a technical response, so prior short/read must be dropped.",
        scenario_tree="If technical response fails and market continues to next leg up, stop short/long attempts and consider long only if a big push creates fresh structure.",
        selection="SOL remains active but he explicitly guards against overtrading.",
        wave="Wave/extension context warns against fighting a continuing leg.",
        thesis="Back-to-back losses after a winner are not a reason to force a reversal; they indicate the branch is invalid.",
        structure="Post-winner FVG, local high/low, continuation leg, stop shelves.",
        setup="He sees a technical response but market does not follow through, so the attempts lose.",
        entry="Rows at 13:23 long and 13:30 short; exact prices hidden.",
        management="Contain both losses and reassess. If a big push up gives a cleaner long, only then consider re-entry.",
        live_changes="He changes from short/reversal idea to accepting the market wants higher.",
        exit_result="Two losses are recorded in Day View while the day remains strongly positive.",
        rule_seed="after_big_winner_two_losses_allowed_if_small; reset_bias_when_market_continues_against_response",
        invalidation="Continuation through the technical response level.",
        uncertainty="Exact stop prices hidden; rows/results visible.",
        labels=("auto_05", "auto_06"),
    ))
    add(ctx(
        "a7x0yKL6jkI", 4,
        decision_type="session_summary_winners_big_losses_contained_context",
        symbol="SOLUSDT",
        direction="session_management",
        youtube_window="16:56-18:26",
        anchor_seconds="1016|1106",
        market_time="17:44 NY local UTC-4 day view visible",
        visible_note="Frame 16m56 shows Day View net P&L $15,712.62, 4 trades, 2 winners/2 losers, gross $18,839.62, commissions $3,127.",
        realized_result="final visible day net +$15,712.62; title states +$14,832 risk $2k",
        session_macro="The day is a clean example of edge distribution: two big winners absorb two contained losses.",
        scenario_tree="Continue trading after losses only if a fresh edge appears; otherwise stop once process quality deteriorates.",
        selection="SOL is the execution product for all visible rows.",
        wave="Elliott/wave context is secondary to session expectancy.",
        thesis="A Craig-copy rule model must preserve the asymmetry: big winners, contained losses, and willingness to reset bias.",
        structure="Day View rows: 00:00 long +$10,456, 10:49 long +$10,852.44, 13:23 long -$2,722.9, 13:30 short -$2,872.92.",
        setup="This row summarizes the session, not a new entry.",
        entry="No new entry.",
        management="Protect the day by not overtrading after the 4-trade sequence; winners remain the reason the day works.",
        live_changes="He says the good trade hit TP and the losses were contained; he is above daily goal.",
        exit_result="Visible day summary +$15,712.62 net, 50% win rate.",
        rule_seed="session_expectancy_rule_two_big_winners_can_pay_for_two_losses_if_losses_contained",
        invalidation="Taking lower-quality trades after expectancy edge is exhausted.",
        uncertainty="Title and dashboard net differ; store frame-confirmed net and title amount separately.",
        labels=("auto_06",),
        gold_status="v03_gold_actionable_context_ready",
    ))

    return rows


def build_hold_rows() -> list[dict[str, str]]:
    return []


def audit_rows(contexts: list[dict[str, str]], hold: list[dict[str, str]], sessions: list[dict[str, str]]) -> list[dict[str, str]]:
    out = []
    by_video: dict[str, list[dict[str, str]]] = {video_id: [] for video_id in BATCH_IDS}
    for row in contexts + hold:
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
                "v03_quality_note_ko": "로컬 SRT, 선별 프레임, 실제 NY market date/time, TradeZella row/day view, 1m OHLCV 캐시를 연결해 v0.3 기준으로 gold/actionable context만 승격.",
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
    audit = audit_rows(ready_contexts, hold_contexts, sessions)

    write_csv(PROCESSED / "gold_v03_batch_03_video_session_maps.csv", sessions, SESSION_FIELDS)
    write_csv(PROCESSED / "gold_v03_batch_03_trade_context_queue.csv", ready_contexts, CTX_FIELDS)
    write_csv(PROCESSED / "gold_v03_batch_03_hold_context_queue.csv", hold_contexts, CTX_FIELDS)
    write_csv(PROCESSED / "gold_v03_batch_03_all_context_queue.csv", all_contexts, CTX_FIELDS)
    write_csv(PROCESSED / "gold_v03_batch_03_rule_seed_queue.csv", rules, RULE_FIELDS)
    write_csv(PROCESSED / "gold_v03_batch_03_quality_audit.csv", audit, AUDIT_FIELDS)

    append_without_batch("gold_v03_video_session_maps.csv", sessions, SESSION_FIELDS)
    append_without_batch("gold_v03_trade_context_queue.csv", ready_contexts, CTX_FIELDS)
    append_without_batch("gold_v03_hold_context_queue.csv", hold_contexts, CTX_FIELDS)
    combined_ready = read_csv(PROCESSED / "gold_v03_trade_context_queue.csv")
    combined_hold = read_csv(PROCESSED / "gold_v03_hold_context_queue.csv")
    write_csv(PROCESSED / "gold_v03_all_context_queue.csv", combined_ready + combined_hold, CTX_FIELDS)
    append_without_batch("gold_v03_rule_seed_queue.csv", rules, RULE_FIELDS)

    old_audit = [row for row in read_csv(PROCESSED / "gold_v03_quality_audit.csv") if row.get("video_id") not in set(BATCH_IDS)]
    write_csv(PROCESSED / "gold_v03_quality_audit.csv", old_audit + audit, AUDIT_FIELDS)

    by_video_count = Counter(row["video_id"] for row in ready_contexts)
    by_video_hold = Counter(row["video_id"] for row in hold_contexts)
    summary_lines = [
        "# v0.3 Batch 03 - Final 7 Local Videos",
        "",
        f"- sessions added: {len(sessions)}",
        f"- gold/actionable contexts added: {len(ready_contexts)}",
        f"- hold contexts added: {len(hold_contexts)}",
        f"- rule seed rows added: {len(rules)}",
        "",
        "| upload order | video_id | title | market dates | ready contexts | hold | note |",
        "|---:|---|---|---|---:|---:|---|",
    ]
    for video_id in BATCH_IDS:
        summary_lines.append(
            f"| {progress_value(video_id, 'local_index_oldest_first')} | {video_id} | {progress_value(video_id, 'video_title')} | {VIDEO_DATES[video_id]['session_dates']} | {by_video_count[video_id]} | {by_video_hold[video_id]} | {VIDEO_DATES[video_id]['confidence']} |"
        )
    OUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    OUT_SUMMARY.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(
        f"batch03 sessions={len(sessions)} contexts={len(ready_contexts)} hold={len(hold_contexts)} rules={len(rules)} summary={OUT_SUMMARY}"
    )


if __name__ == "__main__":
    main()
