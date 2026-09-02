from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "gold_context_trades"
FRAME_MANIFEST = ROOT / "data" / "source" / "craig_frames" / "local_v03_batch_02" / "local_v03_batch_02_frame_manifest.json"
QUALITY_INPUTS = ROOT / "outputs" / "craig_quality_tracker_v0_3" / "quality_tracker_inputs.json"
OUT_SUMMARY = ROOT / "outputs" / "v03_batch_02_7_video_summary.md"

BATCH_IDS = [
    "6rBumkbDi5M",
    "GBRR0JjhOZk",
    "C_R4sLaM0eo",
    "pBkAG3h2QRA",
    "-erhHuJUJiE",
    "o5PdlOfi0-8",
    "SR9eJClrtLU",
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
    "6rBumkbDi5M": {
        "session_dates": "2025-08-20|2025-08-21",
        "default_date": "2025-08-20",
        "confidence": "high_frame_bottom_axis_and_notion_date_rows_aug20_aug21_utc_minus4",
    },
    "GBRR0JjhOZk": {
        "session_dates": "2025-09-08",
        "default_date": "2025-09-08",
        "confidence": "high_frame_bottom_axis_mon_08_sep_25_and_notion_filter",
    },
    "C_R4sLaM0eo": {
        "session_dates": "2025-10-17",
        "default_date": "2025-10-17",
        "confidence": "high_tradezella_daily_journal_fri_oct_17_2025",
    },
    "pBkAG3h2QRA": {
        "session_dates": "2025-11-06|2025-11-07",
        "default_date": "2025-11-06",
        "confidence": "high_user_verified_and_tradezella_filter_nov06_nov07_2025",
    },
    "-erhHuJUJiE": {
        "session_dates": "2025-12-04",
        "default_date": "2025-12-04",
        "confidence": "high_user_verified; late_video_frames_corrupt_after_10m45s",
    },
    "o5PdlOfi0-8": {
        "session_dates": "2025-12-11",
        "default_date": "2025-12-11",
        "confidence": "high_frame_tradezella_12_11_2025_gmt_minus5; late_video_frames_corrupt_after_08m48s",
    },
    "SR9eJClrtLU": {
        "session_dates": "2026-01-07",
        "default_date": "2026-01-07",
        "confidence": "high_user_verified_and_tradezella_jan_07_2026_utc_minus5_visible",
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
    symbols_list = [symbol.strip() for symbol in symbols.split("|") if symbol.strip()]
    date_list = [date.strip() for date in date_text.split("|") if date.strip() and "_or_" not in date.strip()]
    checks = []
    for date in date_list:
        for symbol in symbols_list:
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
        "session_context_id": f"{video_id}_session_v03_batch02",
        "video_id": video_id,
        "video_title": p["video_title"],
        "local_index_oldest_first": p["local_index_oldest_first"],
        "source_stage_v03": "v0_3_batch_02_local_srt_frame_ohlcv",
        "market_dates_utc_minus4": meta["session_dates"],
        "primary_symbols": symbols,
        "confirmed_timeframes": "1m visible; 15m split or 4H/daily/HFT context when shown or spoken",
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
        "context_id": f"{video_id}_v03_batch02_{n:02d}",
        "session_context_id": f"{video_id}_session_v03_batch02",
        "video_id": video_id,
        "video_title": progress_value(video_id, "video_title"),
        "local_index_oldest_first": progress_value(video_id, "local_index_oldest_first"),
        "source_stage_v03": "v0_3_batch_02_local_srt_frame_ohlcv",
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
    negative = ""
    text = f"{row['decision_type']} {row['realized_result']}".lower()
    if "hold" in row["gold_status"]:
        negative = "검증보류 샘플"
    elif "loss" in text or "손실" in row["realized_result"] or "-$" in row["realized_result"] or "-1.2r" in text:
        negative = "손실/무효화 샘플"
    elif "conditional" in row["decision_type"] or "no_fill" in row["decision_type"]:
        negative = "미체결/조건부 setup 샘플"
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
            "6rBumkbDi5M",
            "BTCUSDT|ETHUSDT|SOLUSDT",
            "세션은 Aug 20-21 구간의 여러 trade를 보여준다. 초반에는 daily/HFT bias와 1분봉 open momentum을 같이 보고, FOMC/금리 이벤트 가능성을 별도 리스크로 인식한다. 프레임상 ETH/SOL 1m, HFT 5m/15m/1H/4H 상태, Notion trade log가 같이 보인다.",
            "초기 momentum이 강하면 FVG/CHoCH/critical swing break를 따라가되, front-side short처럼 confirmation이 약하면 risk를 작게 보고 BE 전환을 빠르게 한다. 저녁 구간에는 채널을 다시 그리며 top channel/fib/wave 위치를 재평가한다.",
            "ETH가 큰 winner(+5,781)와 후반 short management의 중심으로 보이고, SOL은 로그에 다수 섞인다. BTC는 macro/HFT 배경보다는 watchlist 축이다.",
            "프레임에 Elliott wave 표기와 fib 0.236/0.382/0.5/0.618/0.786/1.618/2.618이 반복적으로 보인다. 파동 count가 entry 단독조건이라기보다 trend channel, CHoCH, FVG, prior day high/low와 결합된다.",
            "기본 risk는 trade당 1% 또는 $1,000. 손실이 여러 번 있어도 BE 전환, fee 포함 작은 손실(-$162), 2R 이상 lock, runner 추적을 반복한다.",
            "이번 배치에서 날짜가 새로 확정됨. Aug 20 bottom axis/UTC-4, Aug20/Aug21 Notion rows, 1m OHLCV 캐시를 연결. 일부 세부 row는 로그 필터 범위상 session recap 성격으로 둠.",
        ),
        session(
            "GBRR0JjhOZk",
            "SOLUSDT|BTCUSDT|ETHUSDT",
            "오전 8:45에 market open 9:30을 앞두고 방향을 먼저 가늠한다. 초반에는 trend가 끝나지 않아 더 아래를 볼 수도 있고, 반대로 broken trend level을 reclaim하면 bullish day가 될 수도 있다고 양방향 시나리오를 세운다.",
            "clear daily bias가 없다고 직접 말한다. 그래서 특정 방향 고집이 아니라 critical resistance/FVG short, broken level retest, contained loss, runner의 조건으로 판단한다. 9:00 전에는 아직 out of woods가 아니며, 9:30 이후 break가 진짜 확인이라고 본다.",
            "SOL 1m이 실행 중심이다. BTC/ETH는 시장 전반 tickers로 같이 보이지만 실제 position box/log는 SOL이 가장 명확하다.",
            "프레임에는 Elliott/fib 도구와 HFT bullish가 보이나, 핵심 설명은 FVG, resistance/support flip, broken trend retest다. 파동은 보조 시각화이지 주된 발화 근거는 아니다.",
            "$1,000 risk로 $5K-$7K good day를 노리는 risk/reward 철학을 말한다. 손실은 계산된 contained loss로 받아들이고, winner는 일부 lock 후 rest runner를 본다.",
            "Sep 8 2025 bottom axis, UTC-4, SOL position box, Notion log(+4,163, -211), final +8,465 recap이 모두 확인됨.",
        ),
        session(
            "C_R4sLaM0eo",
            "SOLUSDT|ETHUSDT|BTCUSDT",
            "몸이 아픈 상태지만 주간 +$13K에서 +$20K를 목표로 하는 심리/목표 맥락이 있다. 전일 저점(previous day low) 반응과 4H area response를 보며 sell-off 가능성을 크게 보지만, short bias를 맞추려고 trade 수를 소진하지 않겠다고 제약을 둔다.",
            "초반 bearish scenario는 trend break, CHoCH, inefficiency retest로 구성된다. 다만 시장이 lower trend에서 stabilize하면 high break/continuation 여부를 보고 long/reversal 쪽도 받아들인다. 후반에는 시장이 강해지는 것을 인정하고 open-ended로 대응한다.",
            "SOL이 대부분의 trade log 중심이고, ETH short도 점심 이후/저녁 구간에 나온다. TradeLocker 소액 계정은 실험용으로 언급되며 본 모델에는 보조 메타로만 남긴다.",
            "명시적인 Elliott count보다 previous day low, 4H area, CHoCH, BOS, inefficiency/FVG가 핵심이다. 'five-wave'보다는 구조 전환과 FVG 반응이 주로 쓰인다.",
            "trade당 risk factor $1,000. 1:2 RR에서 보통 half off로 1R을 lock하지만 momentum이 강하면 더 열어둔다. 손실 뒤에도 남은 risk factor와 win rate를 계속 언급한다.",
            "Oct 17 2025 daily journal, 8 trades, 6 winners, 2 losers, net P&L $8,597.92가 프레임으로 확인됨.",
        ),
        session(
            "pBkAG3h2QRA",
            "SOLUSDT|BTCUSDT|ETHUSDT",
            "세션 준비에서 Discord daily bias를 확인한다. daily bias는 bullish지만, 그는 이것을 단순 long-only 규칙으로 쓰지 않고 실제 1분봉 구조와 dip/underside level 반응으로 trade 방향을 결정한다.",
            "초기에는 underside/dip level/1.618 반응을 보며 first trade를 잠그고, 이후 fill되면 바로 다른 order를 추가한다. 마지막에는 support, trend retest, moving averages alignment, no five-wave top, higher high/higher low로 long continuation을 판단한다.",
            "SOL 1m 실행이 중심이다. BTC는 daily bias/시장 배경, ETH는 watchlist 정도로 보인다.",
            "이 영상은 Elliott가 직접 주연이다. 특히 five-wave structure가 아직 없다는 부정 조건과 1.618 reaction을 reversal/TP 판단에 사용한다.",
            "5 trades, 100% win day. 목표 $15K를 의식하고 trade 수/quality를 같이 본다. Fill 후 다른 orders를 추가하고, gym 중 self-management를 허용한다.",
            "Nov 06-07 2025 TradeZella dashboard, net P&L $15,597.22, 5 trades, 100% win, chart position boxes가 확인됨.",
        ),
        session(
            "-erhHuJUJiE",
            "SOLUSDT|ETHUSDT|BTCUSDT",
            "목표보다 risk management와 strategy execution을 먼저 강조한다. 약 9:00 시작, key areas 위/아래 어느 쪽이 깨지는지로 daily direction conviction을 얻겠다고 말한다.",
            "초기 short가 late/fee 최적화 부족으로 stop out되면 즉시 contained loss로 journal하고, secondary move로 bias를 바꾼다. 이후 SOL weakness, failed high break, support-to-resistance flip, significant FVG로 short continuation을 구성한다.",
            "초반은 SOL 중심. 후반 SRT에는 ETH로 switching하는 구간이 있으나 로컬 영상 프레임이 10:45 이후 손상되어 gold 승격은 보류했다.",
            "명시적 Elliott count보다 CHoCH, FVG midpoint, daily resistance, previous day low, support/resistance flip이 중심이다.",
            "나쁜 시작 이후 더 selective하겠다고 말한다. 목표보다 contained loss, stop walking, profit lock이 우선이다.",
            "사용자 검증 2025-12-04. 후반 자막은 있으나 MP4가 10:45 이후 H.264 NAL 오류로 안정 프레임을 만들지 못해 초반 frame-confirmed 구간만 gold로 승격.",
        ),
        session(
            "o5PdlOfi0-8",
            "SOLUSDT|ETHUSDT|BTCUSDT",
            "초반에는 higher high/higher low와 failed high break를 시각적으로 설명하며 구조 전환을 가르친다. TradeZella 계정 시간은 GMT-05로 보이고, 2025-12-11 10:17 BUY row가 확인된다.",
            "처음에는 whiplash down 이후 깨지지 못한 level의 opposite side retest에서 short. 이후 low sweep/reclaim이 나오면 bullish reversal/FVG retest long으로 시나리오를 바꾼다. 후반에는 다수 trade가 있었으나 프레임 손상으로 gold는 앞부분만 유지한다.",
            "SOL 1m이 핵심. SRT에는 ETH short도 나오지만, 후반 프레임 검증 불능 구간은 hold로 분리했다.",
            "Elliott count는 핵심이 아니고, HH/HL 구조, failed high break, CHoCH, FVG, trend retest가 중심이다.",
            "실시간 실행에서 slippage/bad fill(-$275)을 명시한다. position box와 TradeZella row를 같이 봐야 strategy signal과 execution error를 분리할 수 있다.",
            "2025-12-11 앞부분 프레임은 매우 선명하나, 08:48 이후 MP4 손상으로 후반 trade 5-9는 SRT-only가 되어 hold 처리.",
        ),
        session(
            "SR9eJClrtLU",
            "SOLUSDT|BTCUSDT|ETHUSDT",
            "목표는 proper risk management와 position sizing. 시작부터 1분봉/15분봉 split view가 보여 멀티타임프레임으로 short/long 위치를 확인한다.",
            "첫 trade는 previous day low break 후 support/FVG에서 exit해 5.5R을 잠근다. 이후 level break가 137로 되돌릴 수 있다는 long/reversal 가정이 실패하면 -1.2R을 받아들이고, 다시 FVG short 또는 sweep 후 bullish opportunity를 본다.",
            "SOL 실행이 거의 전부다. BTC/ETH는 watchlist와 시장 배경 역할.",
            "Elliott보다 1m/15m alignment, previous day high/low, FVG, support, sweep, flip이 핵심이다.",
            "첫 trade +5.5R 이후에도 위험을 완전히 off table로 만들고, 다음 trade 실패(-1.2R)를 세션 전체 맥락에서 수용한다.",
            "Jan 07 2026, TradeZella trade view, SOL long Trade 4 +$2,091.81/$2,098 overlay, UTC-5 visible. 겨울 NY 시간 표기를 note로 남김.",
        ),
    ]


def build_contexts() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    add = rows.append

    add(ctx(
        "6rBumkbDi5M",
        1,
        decision_type="executed_winner_context",
        symbol="ETHUSDT",
        direction="long",
        youtube_window="02:45-09:06",
        anchor_seconds="345|396|486",
        market_date="2025-08-20",
        market_time="11:00-12:20 UTC-4 visible",
        visible_note="Frame 08m06 shows ETHUSDT 1m, Wed 20 Aug '25 12:20, UTC-4, HFT 5m/15m bullish, 1H bearish, 4H bullish, Notion rows and position box.",
        entry_price="4201.13",
        stop_price="4183.53",
        target_price="4355.48",
        realized_result="+$5,781 visible/logged; title-day contributes to +$8,558",
        session_macro="Open momentum and HFT alignment are read together. The broader session is not one-direction-only, but this trade has bullish lower-timeframe HFT and room toward PDH.",
        scenario_tree="If ETH holds the reclaimed level and continues through the marked trend, he can run the trade toward PDH/TP. If it loses the red entry/SL shelf, the long is invalid.",
        selection="ETH is selected because the position box, chart, and Notion row are all explicit; SOL appears in the broader log but this context is ETH-specific.",
        wave="Visible Elliott/fib annotations frame the move: trend leg up from a lower swing, fib zones, PDH target. Wave/fib are confluence, not a standalone trigger.",
        thesis="Critical swing/CHoCH and FVG response turn into a long continuation attempt toward prior-day high.",
        structure="1m ETH trendline rising from the low, CHoCH/BOS markers, green FVG/support shelves beneath entry, PDH/TP above.",
        setup="Price reclaims/holds the post-open support area, leaves bullish FVGs, and starts moving in a clean impulsive leg with HFT 5m/15m bullish.",
        entry="Long around the displayed entry 4201.13, with SL just under the failed/reclaimed support shelf at 4183.53 and TP at 4355.48.",
        management="Let the large positive response develop rather than closing too early; use the entry shelf/trendline as invalidation and treat PDH as the main magnet.",
        live_changes="He treats the move as a possible larger runner but keeps the hard stop clear. The visible log shows several prior losses, so this winner is also recovery context.",
        exit_result="The visible position overlay/log shows +$5,781 on Aug 20 for a 1m ETH long.",
        rule_seed="long_if_1m_reclaims_support_fvg_with_bullish_5m_15m_hft_and_pdh_target; entry_support_shelf; sl_below_reclaim; tp_pdh_or_box_target",
        invalidation="Break back below 4183.53/entry support shelf or failure of the bullish 1m structure.",
        uncertainty="Exact fill is directly visible. Whether this is trade number within two-day sequence is secondary; context/result are complete.",
        labels=("auto_02", "auto_03"),
    ))

    add(ctx(
        "6rBumkbDi5M",
        2,
        decision_type="executed_break_even_or_small_loss_context",
        symbol="SOLUSDT|ETHUSDT",
        direction="short",
        youtube_window="09:02-17:44",
        anchor_seconds="722|933",
        market_date="2025-08-20",
        market_time="FOMC/pre-news to afternoon window",
        visible_note="Frames 12m02-17m44 show short boxes around a volatile front-side move; SRT says BE tag then upside rip, then another position ends -$162 with fees.",
        realized_result="break-even then -$162 with fees; risk contained",
        session_macro="FOMC/rate decision is treated as a two-sided volatility driver. He avoids pretending to know the news direction.",
        scenario_tree="Shorting front side before a new trend low is riskier. If price gives immediate downside confirmation, trail; if it returns to entry, BE/small fee loss is acceptable.",
        selection="SOL/ETH are both being monitored; the row is about the front-side short decision model rather than one clean single-symbol winner.",
        wave="Visible fib/wave drawings exist, but the spoken driver is lack of confirmation and event volatility.",
        thesis="A front-side short can be taken if volatility and a high-impact area line up, but it must be managed more conservatively because no new low has broken.",
        structure="Red FVG/resistance zones above, blue target area below, no confirmed fresh lower low at entry.",
        setup="Price rallies into a resistance/FVG area before FOMC; he recognizes that the setup is lower confidence because the trend has not confirmed with a fresh breakdown.",
        entry="Short at/near the resistance/FVG shelf only with contained risk, not a chase after event candles.",
        management="Move stop to break-even quickly. Fees can make the journal slightly negative, but strategically it is treated as BE.",
        live_changes="He explicitly says more patience could have extracted more risk factors from the previous position, then resets to find another opportunity in volatility.",
        exit_result="One trade tags break-even and rips; another is journaled as -$162 with fees but classified by him as risk-contained/BE.",
        rule_seed="front_side_short_before_confirmation_requires_fast_be_and_news_volatility_filter; classify_fee_loss_as_be_if_strategy_risk_removed",
        invalidation="Price pushes through the resistance/FVG and does not break the next low before entry retest.",
        uncertainty="Exact symbol for each sub-leg is mixed in the SRT, so this is a sequence-level management context, not a single exact-price row.",
        labels=("auto_04", "auto_05", "auto_06"),
        gold_status="v03_gold_actionable_context_ready",
    ))

    add(ctx(
        "6rBumkbDi5M",
        3,
        decision_type="executed_channel_reassessment_context",
        symbol="ETHUSDT|SOLUSDT",
        direction="short",
        youtube_window="15:32-20:16",
        anchor_seconds="1082",
        market_date="2025-08-20",
        market_time="afternoon channel retest",
        visible_note="Frames 18m02-20m16 show upper-channel/top-channel redraw and short position logic after he admits the channel was drawn incorrectly.",
        realized_result="risk-contained BE/small fee loss, then new short idea materializes",
        session_macro="After multiple trades, the macro context is less about daily bias and more about whether volatility creates a blowoff-top reversal into a channel/FVG zone.",
        scenario_tree="If the corrected top-channel area rejects, short continuation is valid. If price breaks and holds above the red zone/channel, the top thesis is wrong.",
        selection="ETH/SOL are both in the log; the chart sequence is more about the channel correction rule than symbol selection.",
        wave="Fib/wave overlays support the blowoff-top idea; they are used after the redraw, so the rule needs a 'redraw/revalidate before entry' feature.",
        thesis="Do not keep the first drawn channel if price proves it wrong; redraw the correct channel and only then judge the top/reversal area.",
        structure="Corrected top channel, red FVG/supply, prior swing high/lower high, possible blowoff top.",
        setup="Price returns to the corrected channel top and resistance/FVG after an earlier BE. The setup is valid only after chart object correction.",
        entry="Short near the corrected top-channel/FVG area with stop beyond the blowoff high.",
        management="If the move starts, reduce risk quickly. If it stalls or retests entry, treat it as BE/small fee loss.",
        live_changes="He openly says the previous channel was drawn incorrectly and changes the framework. This is a real-time thesis-repair sample.",
        exit_result="No large result isolated here; this row captures the corrected setup and BE-style management before the next runner.",
        rule_seed="before_channel_retest_trade_revalidate_trendline_anchor_points; only_trade_redrawn_channel_if_multiple_contacts_and_fvg_overlap",
        invalidation="Sustained breakout above corrected top channel/FVG or no downside response after fill.",
        uncertainty="Result is sequence-level and merges into next short runner; keep as actionable/reassessment context.",
        labels=("auto_06",),
        gold_status="v03_gold_actionable_context_ready",
    ))

    add(ctx(
        "6rBumkbDi5M",
        4,
        decision_type="executed_winner_context",
        symbol="ETHUSDT",
        direction="short",
        youtube_window="17:55-24:16",
        anchor_seconds="1225|1315|1385",
        market_date="2025-08-20",
        market_time="17:40-20:45 UTC-4 visible",
        visible_note="Frames 21m55/23m05 show ETHUSDT 1m, Wed 20 Aug '25 17:41/17:21 UTC-4, HFT 5m/15m/1H bearish and 4H bullish, Notion Aug20/Aug21 rows.",
        realized_result="+$2,857 captured on this trade; visible table sum $6,130 for filtered Aug20-Aug21 rows",
        session_macro="After a volatile day, lower-timeframe HFT turns bearish while 4H remains bullish. He treats the short as intraday continuation, not a higher-timeframe bear market call.",
        scenario_tree="If the downtrend continues, trail and extract more. If price breaks out of the downtrend, lock the two-risk-factor profit and do not give it back.",
        selection="ETH chart is visible for the runner; Notion rows include SOL and ETH, but the position box/frame evidence for this context is ETH.",
        wave="Fib/wave count remains on chart, with lower-high/downtrend sequence and FVG shelves guiding the trailing decision.",
        thesis="Corrected channel/top idea transitions into a short runner once the move starts making lower highs and bearish HFT aligns.",
        structure="Downtrend line, lower highs, red resistance/FVG shelves, blue target box, prior support levels below.",
        setup="Price rejects from the top/channel region and starts moving down. He waits for enough movement, then removes risk and follows the downtrend.",
        entry="Short after the rejection/downtrend continuation; exact entry is frame-relative because the position table is partially obscured.",
        management="At about +$2,000, reduce risk to break-even. When price breaks out of the downtrend, lock slightly more than 2R rather than forcing a larger runner.",
        live_changes="He hopes for a larger move, then changes from open-ended runner to profit lock when the downtrend line breaks.",
        exit_result="Captured $2,857 after all said and done; still trying to finish the two-day sequence strong.",
        rule_seed="short_runner_after_top_channel_rejection_reduce_to_be_at_plus_2r_exit_when_downtrend_breaks",
        invalidation="Breakout above active downtrend line or reclaim of the last bearish FVG shelf.",
        uncertainty="Frame confirms date/time and log rows. Title PnL $8,558 includes additional rows outside this isolated context.",
        labels=("auto_07",),
    ))

    add(ctx(
        "GBRR0JjhOZk",
        1,
        decision_type="executed_winner_context",
        symbol="SOLUSDT",
        direction="short",
        youtube_window="00:00-12:41",
        anchor_seconds="15|611|761",
        market_date="2025-09-08",
        market_time="11:59-15:22 UTC-4 visible",
        visible_note="Frames 00m15 and 12m41 show SOLUSDT 1m, Mon 08 Sep '25, UTC-4, short position boxes and Notion date filter Sep 8. Frame 12m41 shows row +$4,163.",
        entry_price="216.57",
        stop_price="216.89",
        target_price="214.34",
        realized_result="+$4,162/+4,163 locked; one earlier small row -$211 also visible",
        session_macro="At 8:45 he has no super clear daily bias. Market open is 9:30, and the job is to infer direction from trend/level behavior before and after open.",
        scenario_tree="Bearish case: trend not over and price can move lower into the next area. Bullish alternate: broken trend level is reclaimed and retested, which would make the day bullish.",
        selection="SOL is chosen because the critical resistance/FVG short is the cleanest executable structure and visible on both TradingView and exchange panel.",
        wave="Fib/Elliott tools are visible, but he speaks mainly in trend/FVG/resistance terms. HFT is bullish in frame, so this short is a local reversal/level trade.",
        thesis="Short from an important FVG into critical resistance, expecting the level to reject and the market to continue lower.",
        structure="Broken/bounced level that becomes resistance, red FVG/supply, prior high risk area, lower target/TP box around 214.34.",
        setup="Price pushes into the resistance/FVG zone and begins moving in his direction. Before 9:30 he still wants a break beneath the local level to confirm.",
        entry="Short around 216.57 on the FVG/resistance retest; stop above 216.89; TP around 214.34.",
        management="Risk is contained to the red resistance area. Once movement starts, he is not 'out of the woods' until the level below breaks; later he locks the winner.",
        live_changes="He repeatedly reminds that a no-bias morning demands flexibility: if it pushes up, take contained loss; if it breaks lower, follow the trend.",
        exit_result="Visible Notion row logs +$4,163; SRT says he locked about $4,162 from the trade.",
        rule_seed="no_clear_daily_bias_short_only_at_critical_resistance_fvg_with_defined_loss_and_lower_level_break_confirmation",
        invalidation="Push through/hold above 216.89 resistance or failure to break the level below after entry.",
        uncertainty="Frame 00m15 also shows a -$211 row and a different short box entry 215.47/SL 215.72/TP 213.01; that is treated as adjacent row, not merged into this winner.",
        labels=("auto_01", "auto_05"),
    ))

    add(ctx(
        "GBRR0JjhOZk",
        2,
        decision_type="executed_loss_or_contained_risk_context",
        symbol="SOLUSDT",
        direction="short",
        youtube_window="02:59-11:12",
        anchor_seconds="329|476|522",
        market_date="2025-09-08",
        market_time="pre-09:30 to late morning",
        visible_note="Frame 00m15 shows a separate SOL short box with entry 215.47, SL 215.72, TP 213.01, and Notion row -$211. SRT emphasizes contained loss if price moves against him.",
        entry_price="215.47",
        stop_price="215.72",
        target_price="213.01",
        realized_result="visible adjacent row -$211; strategy framed as contained loss if invalidated",
        session_macro="No clear bias is explicitly stated. The lesson is to size the idea so a wrong direction is a calculated loss, not a thesis crisis.",
        scenario_tree="If reclaimed trend level holds and breaks up, bullish scenario wins and the short is wrong. If resistance holds and price breaks down, trend-follow lower.",
        selection="SOL has the actionable box; other symbols are background only.",
        wave="Elliott not primary; support/resistance flip and FVG define the decision.",
        thesis="Try the local short at a resistance/FVG zone even without strong daily bias because risk is narrowly defined.",
        structure="Resistance/retest area above, target below, small red stop zone and large blue reward zone.",
        setup="A prior level was broken, bounced, broken under, then retested as resistance. That repeated touch history gives the resistance zone meaning.",
        entry="Limit short around 215.47 with stop 215.72 and deep TP 213.01.",
        management="If the market flips upward, mark the loss and move on; do not widen the stop because the no-bias context is fragile.",
        live_changes="He holds both theories in mind instead of forcing certainty. This is a clean no-bias/contained-loss rule seed.",
        exit_result="Adjacent visible log shows a small loss; not the same as the later +$4,163 winner.",
        rule_seed="in_no_bias_session_allow_small_short_at_retested_sr_only_if_loss_is_tightly_capped",
        invalidation="Break and hold above the repeated resistance/retest zone.",
        uncertainty="Result is inferred from visible Notion row and nearby box; keep as contained-risk sample rather than main PnL driver.",
        labels=("auto_02", "auto_03", "auto_04"),
        gold_status="v03_gold_actionable_context_ready",
    ))

    add(ctx(
        "GBRR0JjhOZk",
        3,
        decision_type="executed_runner_exit_context",
        symbol="SOLUSDT",
        direction="short",
        youtube_window="14:12-21:19",
        anchor_seconds="1002|1152",
        market_date="2025-09-08",
        market_time="evening recap/night desk",
        visible_note="Frames 16m42-19m22 show night recap and chart/log view. SRT says rest likely stopped at the area after $4K already locked.",
        realized_result="+$4,513 on that trade; day +$8,465; 66% win rate",
        session_macro="The day becomes high win-rate relative to his normal 37-40%. He remains aware that back-to-back trades are unusually clean.",
        scenario_tree="After locking $4K, the only question is whether the rest can run. If it returns to the stop/area, exit the rest and accept the locked winner.",
        selection="SOL remains primary; LINK auto-label in the old queue is not supported by the visible chart and is ignored.",
        wave="No Elliott-specific exit; this is runner management at an area.",
        thesis="Do not re-risk a locked winner. Once partial profit is secured, runner failure should still end as a strong trade.",
        structure="Existing short box/area, rest position, stop/area where price can tag him out.",
        setup="Continuation short already worked; this row captures end-stage management, not new entry.",
        entry="No new entry; carry the remaining position after partial lock.",
        management="Keep the rest open only while the continuation remains valid; if stopped at the area, journal the locked result.",
        live_changes="He acknowledges the rest may stop, but psychologically anchors on the already locked $4K rather than trying to force more.",
        exit_result="Locked $4,513 on that trade and +$8,465 on the day.",
        rule_seed="after_partial_lock_runner_can_stop_without_negative_review_if_day_trade_thesis_paid",
        invalidation="Price tags runner stop/management area after partial profit.",
        uncertainty="Recap-level row; exact runner stop price not visible.",
        labels=("auto_06",),
    ))

    add(ctx(
        "C_R4sLaM0eo",
        1,
        decision_type="executed_opening_loss_sequence_context",
        symbol="SOLUSDT|BTCUSDT",
        direction="short",
        youtube_window="00:00-06:15",
        anchor_seconds="31|399|460",
        market_date="2025-10-17",
        market_time="09:30-09:53 visible in journal",
        visible_note="Frame 21m06 TradeZella journal shows Fri Oct 17 2025 rows: 09:30 SOL short -$1,518.12, 09:50 SOL short -$1,022.81, 09:53 SOL short +$140.4.",
        realized_result="opening short attempts include -$1,518.12 and -$1,022.81, then small +$140.4",
        session_macro="Weekly goal pressure is high: sick but up nearly $13K and trying to reach $20K. He sees previous day low reversal and possible large sell-off.",
        scenario_tree="Bearish case: previous day low reaction, trend break, CHoCH, inefficiency retest leads to sell-off. Guardrail: do not exhaust all trades guessing short bias if market breaks back over the high.",
        selection="SOL journal rows confirm actual execution. BTC appears in old auto candidate as macro symbol, but visible log is SOL.",
        wave="No explicit Elliott count; 4H area, previous day low, CHoCH, inefficiency are the core higher/lower timeframe bridge.",
        thesis="Opening short bias is reasonable only if the retest/inefficiency rejects and follow-through appears quickly.",
        structure="Previous day low, 4H response area, trend break, CHoCH, inefficiency/FVG, local high that would invalidate shorts.",
        setup="He wants price to move back up into the high-impact area and reject for continuation down. Early attempts show how the same thesis can create losses if follow-through is weak.",
        entry="Short entries around the opening retest/inefficiency areas; exact prices are journal-visible only through replay, not table text.",
        management="After early losses, avoid spending every trade on short-bias guessing. Wait for break over high or lower continuation before trade four.",
        live_changes="He explicitly notes he wants to pick the day's real direction, not burn all trades proving the initial short thesis.",
        exit_result="Daily journal confirms early losses and small offsetting short; later day recovers.",
        rule_seed="opening_short_bias_from_pdl_4h_choch_fvg_requires_fast_followthrough_and_trade_count_guardrail",
        invalidation="Break over the local high or no continuation after FVG/inefficiency rejection.",
        uncertainty="Journal side/time/result are clear; exact entry/SL/TP for the early losses require replay extraction.",
        labels=("auto_01", "auto_02", "auto_03", "auto_08"),
    ))

    add(ctx(
        "C_R4sLaM0eo",
        2,
        decision_type="executed_recovery_trade_context",
        symbol="SOLUSDT",
        direction="long_or_reversal_sequence",
        youtube_window="05:35-12:12",
        anchor_seconds="515|582",
        market_date="2025-10-17",
        market_time="09:59-11:42 visible in journal",
        visible_note="Journal frame shows 09:59 SOL long +$1,768 and 11:42 SOL long +$2,216.6. Earlier frames show 10:30 Trade 4 and management around a large blue box.",
        realized_result="+$1,768 and +$2,216.6 SOL long rows visible",
        session_macro="After opening losses, he needs recovery without overtrading. The market stabilizes around lower trend/support rather than giving clean one-way sell-off.",
        scenario_tree="If lower trend/support breaks down, bearish continuation remains possible. If price stabilizes and pushes through local levels, take the cleaner reversal/continuation and manage at 1:2.",
        selection="SOL is chosen because the journal and frames align; BTC in auto transcript is treated as broad market analysis, not the logged instrument.",
        wave="No explicit Elliott count; support response and FVG/CHoCH are primary.",
        thesis="After the early short thesis fails to pay cleanly, accept the market's stabilizing/reversal structure and recover with SOL long continuation.",
        structure="Lower trend response, local highs to break, blue reward box, red invalidation shelf, FVG/support blocks.",
        setup="Price stabilizes, responds from the lower trend/support, then starts breaking levels. He adds to the position for more bang if the large move appears.",
        entry="Long/reversal position on support/FVG response; add only after the expected level break starts.",
        management="Normally take half off at 1:2 to lock 1R; in this case he lets momentum play, while still tracking remaining session drawdown and unrealized profit.",
        live_changes="He moves from proving bearish bias to letting the market show direction, and turns the session from early drawdown into positive unrealized.",
        exit_result="Visible journal logs +$1,768 and +$2,216.6 SOL long winners.",
        rule_seed="after_failed_opening_bias_accept_support_reversal_long_if_local_highs_break_and_manage_half_at_1_to_2_or_momentum_hold",
        invalidation="Failure to hold lower trend/support or loss of the FVG shelf after entry.",
        uncertainty="The spoken transcript still uses sell-off language in places, so this row is marked as reversal sequence aligned to visible journal sides.",
        labels=("auto_04", "auto_05", "auto_08"),
    ))

    add(ctx(
        "C_R4sLaM0eo",
        3,
        decision_type="executed_high_potency_reversal_setup_context",
        symbol="SOLUSDT|ETHUSDT",
        direction="short_or_reversal",
        youtube_window="08:50-16:13",
        anchor_seconds="680|840",
        market_date="2025-10-17",
        market_time="12:48 and afternoon visible in journal",
        visible_note="Frames around 11m20-14m00 show short boxes; journal frame shows 12:48 ETH short +$1,257.3.",
        realized_result="ETH short +$1,257.3 visible; previous trade stopped, session then down only $632 before recovery",
        session_macro="The day is still not clean; he describes 50% win rate and not great/not terrible session, so the next trade must have high potency.",
        scenario_tree="If a level invalidates to the upside, then retests the opposite side into inefficiency, a reversal area is valid. If the retest does not reject, stand down.",
        selection="ETH appears in the final journal as a 12:48 short winner, while frames show the same FVG/retest logic across SOL/ETH screens.",
        wave="No Elliott count; 'high potency reversal area' is built from level invalidation plus inefficiency.",
        thesis="Invalidated level can flip into a new high-impact reversal area when price retests the opposite side and fills inefficiency.",
        structure="Broken level, opposite-side retest, red FVG/inefficiency, target box below, recent stop-out context.",
        setup="After a stopped-out trade, price pushes down into the retest/fill zone; he waits for fill while tracking remaining risk factor.",
        entry="Short/reversal entry at the opposite-side retest into inefficiency, with stop beyond the invalidated level.",
        management="Because the session has prior losses, walk risk quickly once response appears and avoid letting the trade become a full additional loss.",
        live_changes="He labels the area high potency only after the previous level is invalidated and retested from the other side.",
        exit_result="Visible journal confirms ETH short +$1,257.3 later in the session.",
        rule_seed="level_invalidation_plus_opposite_side_retest_into_fvg_is_reversal_setup_after_prior_stopout",
        invalidation="Retest fails to reject and price reclaims the invalidated level.",
        uncertainty="Exact mapping from chart frame to 12:48 ETH row is recap-linked, not tick-by-tick reconstructed.",
        labels=("auto_06", "auto_08"),
    ))

    add(ctx(
        "C_R4sLaM0eo",
        4,
        decision_type="executed_afternoon_strength_reassessment_context",
        symbol="SOLUSDT|ETHUSDT",
        direction="mixed_open_ended",
        youtube_window="14:14-19:39",
        anchor_seconds="1004",
        market_date="2025-10-17",
        market_time="13:30-16:00 approximate, 16:00 visible in journal",
        visible_note="SRT says he is around +$1,000 on a trade but cannot get the dump; markets are getting strong. Journal shows 16:00 SOL long +$3,004.55.",
        realized_result="+$3,004.55 SOL long row visible later; trade around +$1K before reassessment",
        session_macro="After midday, market strength starts contradicting the earlier sell-off expectation.",
        scenario_tree="If the dump does not come and market strength appears, stop forcing shorts and keep yourself open-ended for the next big move.",
        selection="SOL becomes the cleaner long/strength instrument in the visible journal.",
        wave="No explicit Elliott; strength/reclaim and failed dump are the decision features.",
        thesis="Open-ended trader mindset: when expected dump fails, the next best trade may be the strength continuation rather than another short.",
        structure="Failed downside continuation, support/reclaim, later long winner in journal.",
        setup="He notices the trade cannot dump, acknowledges market strength, and prepares to trade the rest of the afternoon for one or two larger moves.",
        entry="Do not enter more shorts without renewed weakness; later long context is accepted when strength confirms.",
        management="Take profits or flatten if the short idea returns to TP/entry instead of dumping; reset before dinner.",
        live_changes="He says he honestly does not know how to read these markets and chooses to keep himself open-ended.",
        exit_result="Journal confirms a 16:00 SOL long +$3,004.55, consistent with the strength reassessment.",
        rule_seed="if_expected_dump_fails_and_market_gets_strong_switch_from_short_bias_to_open_ended_or_long_strength",
        invalidation="Fresh breakdown with weakness would re-enable bearish scenario; otherwise no short forcing.",
        uncertainty="This is a thesis-change context linked to later journal result, not a single continuous on-screen position.",
        labels=("auto_07", "auto_08"),
        gold_status="v03_gold_actionable_context_ready",
    ))

    add(ctx(
        "C_R4sLaM0eo",
        5,
        decision_type="session_recap_result_context",
        symbol="SOLUSDT|ETHUSDT",
        direction="mixed",
        youtube_window="17:06-24:47",
        anchor_seconds="1176|1266|1336",
        market_date="2025-10-17",
        market_time="09:30-19:00 visible journal range",
        visible_note="Frame 21m06 shows Fri Oct 17, 2025 daily journal: net P&L $8,597.92, 8 trades, 6 winners, 2 losers, 75% winrate, row-level times/results.",
        realized_result="daily net P&L $8,597.92; 8 trades; 6 winners; 2 losers; gross P&L $9,303.92; commissions $706",
        session_macro="The entire day demonstrates recovering from early losses while under weekly-goal pressure and illness.",
        scenario_tree="Early short bias can be wrong and still end as a strong day if losses are capped and later strength/reversal trades are accepted.",
        selection="SOL dominates the row log; ETH short contributes one midday winner.",
        wave="Elliott is not dominant in this session; prior-day levels, 4H area, FVG, CHoCH, and strength/weakness shifts are the replicated features.",
        thesis="Session-level rule seed: copy Craig's adaptation path, not just isolated entries.",
        structure="Journal rows: 09:30 short loss, 09:50 short loss, 09:53 short small win, 09:59 long win, 11:42 long win, 12:48 ETH short win, 16:00 SOL long win, 19:00 SOL short win.",
        setup="The recap ties the intraday thesis changes to objective row-level results.",
        entry="No new entry; this row is the recap/audit anchor for the session.",
        management="Use journal totals to validate whether earlier context rows are complete and not double-counted.",
        live_changes="The day moves from strong bearish expectation to mixed/open-ended adaptation and ends with a late SOL short winner.",
        exit_result="Final journal net P&L $8,597.92.",
        rule_seed="session_quality_requires_row_log_reconciliation_after_context_extraction",
        invalidation="If a candidate trade cannot be tied to one of the visible row outcomes, keep it as setup/actionable rather than executed PnL.",
        uncertainty="Some individual chart frames are blurred or side labels conflict with transcript auto-symbols; the journal row is the reliable result anchor.",
        labels=("auto_08",),
        gold_status="v03_gold_actionable_context_ready",
    ))

    add(ctx(
        "pBkAG3h2QRA",
        1,
        decision_type="session_macro_bias_context",
        symbol="SOLUSDT|BTCUSDT",
        direction="bullish_bias_but_flexible",
        youtube_window="00:38-07:20",
        anchor_seconds="128",
        market_date="2025-11-06",
        market_time="pre-session setup, breakfast 11:45 shown",
        visible_note="Frames 01m00-03m00 show TradingView, Discord daily bias area, Bybit panel, and setup screens; SRT says Discord head trader daily bias is bullish.",
        realized_result="macro/setup context; session later +$15,597.22",
        session_macro="Daily bias from team/Discord is bullish, but Craig says that does not necessarily mean only long positions.",
        scenario_tree="Use bullish bias as background. If 1m gives a short from underside/dip level, take it; if higher-high/higher-low continuation appears, return to long bias.",
        selection="SOL is the main chart/order instrument; BTC is broader daily-bias reference.",
        wave="Elliott/fib appears later; this row is macro/prep rather than wave entry.",
        thesis="Daily bias is not an order. It only sets the scenario tree that must still be confirmed by intraday structure.",
        structure="Discord bias, TradingView chart, key levels, exchange panel, TradeZella logging workspace.",
        setup="Pre-session workspace setup and daily bias intake before trade one.",
        entry="No direct entry in this row; use it to label the session macro state.",
        management="Do not overfit bullish bias; validate each trade against local 1m structure.",
        live_changes="He immediately frames daily bias as context, not a rigid direction rule.",
        exit_result="Session later confirms strong 5/5 win day, but this row's value is macro input.",
        rule_seed="daily_bias_is_context_not_direction_filter; require_intraday_setup_to_execute_against_or_with_bias",
        invalidation="If local 1m structure contradicts the bias, bias alone cannot justify entry.",
        uncertainty="No trade execution in this row by design.",
        labels=("auto_01",),
        gold_status="v03_gold_actionable_context_ready",
    ))

    add(ctx(
        "pBkAG3h2QRA",
        2,
        decision_type="executed_winner_context",
        symbol="SOLUSDT",
        direction="short",
        youtube_window="04:15-09:45",
        anchor_seconds="435",
        market_date="2025-11-06",
        market_time="midday before/after breakfast",
        visible_note="Frames 07m15-09m45 show short box, dip/underside levels, Bybit and TradeZella entry panes. SRT says reaction off 1.618 and fully out first trade +$2,500.",
        realized_result="trade 1 about +$2,500 fully out",
        session_macro="Even with bullish daily bias, the first completed opportunity is a tactical short from underside/dip/fib confluence.",
        scenario_tree="If underside into dip level two reacts and 1.618 extension holds, take profit at the lower level. If support holds too strongly, do not overstay.",
        selection="SOL is the visible instrument.",
        wave="1.618 reaction is explicitly used for the trade one exit/target decision.",
        thesis="Short the underside/dip-level retest when it aligns with fib extension reaction, even inside a broadly bullish day.",
        structure="Underside retest, dip level two, 1.618 fib reaction, support/TP level below.",
        setup="Price comes into the underside/dip level and reacts off 1.618; he watches whether it can reach full TP.",
        entry="Short from underside/dip level two; exact price is frame-relative.",
        management="Observe support at the target level and fully exit when +$2,500 is available.",
        live_changes="He is willing to hold an L1 bomb for the rest of day only if the move keeps validating; support changes the exit decision.",
        exit_result="Fully out of first trade, +$2,500.",
        rule_seed="bullish_daily_does_not_block_short_if_underside_dip_level_1618_reacts_take_profit_at_support",
        invalidation="Break and hold above underside/dip level or no downside reaction from 1.618.",
        uncertainty="Exact entry/SL price requires frame coordinate/OHLCV calculation.",
        labels=("auto_02",),
    ))

    add(ctx(
        "pBkAG3h2QRA",
        3,
        decision_type="executed_winner_context",
        symbol="SOLUSDT",
        direction="long",
        youtube_window="08:20-13:50",
        anchor_seconds="680|770",
        market_date="2025-11-06",
        market_time="afternoon, before gym",
        visible_note="Frames 11m20 and 12m50 show a long box/order panel. SRT says he gets filled, adds other orders, closes trade 3 for $3,156 total.",
        realized_result="trade 3 +$3,156 total",
        session_macro="After first trades are green, he is trying to reach the $15K mark with up to five high-quality trades.",
        scenario_tree="If price breaks over the high after fill, he can go to the gym and let management rules run. If it fails the level, keep risk defined.",
        selection="SOL is still the cleanest visible execution instrument.",
        wave="No explicit count in this row; continuation structure and high break are central.",
        thesis="Once the long setup fills and structure starts pushing toward the high, add the planned orders and manage for continuation.",
        structure="Long box with red invalidation below, green target above, local high that must break.",
        setup="Filled on the long idea and immediately adds supporting orders, then watches the break over the high as the confirmation for self-managed continuation.",
        entry="Long after planned fill; other orders added only after entry is live.",
        management="Close trade 3 when +$3,156 total is available, then log and look for up to two more trades.",
        live_changes="He is balancing ambition to hit $15K with the need for clean fills and enough structure to leave the desk.",
        exit_result="Out of trade number three, +$3,156 total.",
        rule_seed="after_long_fill_add_orders_only_if_high_break_path_exists_close_when_trade_goal_hit",
        invalidation="Failure to hold the red support/stop shelf or rejection before high break.",
        uncertainty="Exact entry/SL/TP are visually present but too small for reliable OCR.",
        labels=("auto_03",),
    ))

    add(ctx(
        "pBkAG3h2QRA",
        4,
        decision_type="executed_winner_context",
        symbol="SOLUSDT",
        direction="long",
        youtube_window="10:59-17:01",
        anchor_seconds="809|899",
        market_date="2025-11-06|2025-11-07",
        market_time="20:30-00:30 chart span; dashboard Nov06-Nov07",
        visible_note="Frame 14m59 shows dashboard Nov 06, 2025-Nov 07, 2025, net P&L $15,597.22, 5 trades, 100% win, and a long box from dip_buy 1 support.",
        entry_price="154.7 visible order panel",
        stop_price="153.91 chart stoploss label",
        target_price="158.55 high/target area visible",
        realized_result="session +$15,597.22; 5 trades; 100% win",
        session_macro="Bullish day bias is now supported by local uptrend structure, not just pre-session opinion.",
        scenario_tree="If support holds and price reattempts the trend level with moving averages aligned, take long. If a five-wave structure is already complete, avoid late long; here he says there is no five-wave structure yet.",
        selection="SOL remains the execution vehicle with the clearest trend continuation.",
        wave="Explicit negative Elliott filter: no five-wave structure within the trend, plus HH/HL indicating new uptrend still valid.",
        thesis="Long from support/dip-buy area when MAs align, HH/HL is intact, and the move has not completed a five-wave structure.",
        structure="Dip_buy 1 support zone, stoploss below, higher high/higher low sequence, trend retest, moving averages same direction.",
        setup="Price pulls into support/dip-buy area, reattempts trend level, and maintains new uptrend structure.",
        entry="First long into the support/trend retest area, visible order panel around 154.7.",
        management="If it works, he can go five-for-five and reach the $15K goal. Keep stop below dip/stoploss and let target run toward high.",
        live_changes="He explicitly uses the absence of five waves to avoid calling the trend exhausted too early.",
        exit_result="Dashboard verifies +$15,597.22 net P&L and 100% win rate for the day.",
        rule_seed="long_if_support_retest_ma_alignment_hh_hl_and_no_completed_five_wave_structure",
        invalidation="Break below dip_buy/support/stoploss or evidence of completed five-wave exhaustion before entry.",
        uncertainty="The final dashboard covers session total; individual final trade exact PnL not isolated from dashboard.",
        labels=("auto_04",),
    ))

    add(ctx(
        "-erhHuJUJiE",
        1,
        decision_type="executed_loss_context",
        symbol="SOLUSDT",
        direction="short",
        youtube_window="00:00-09:41",
        anchor_seconds="29|376|431",
        market_date="2025-12-04",
        market_time="09:00-10:00 approximate",
        visible_note="Frames 01m00-08m46 show SOL 1m, short boxes, FVG/CHoCH areas, Bybit and TradeZella entry panes. SRT says first trade stopped out after late/fee-suboptimal entry.",
        realized_result="contained loss on first trade",
        session_macro="The day starts with explicit risk-management priority over daily goal. He wants one of the key areas to break for conviction.",
        scenario_tree="Short if CHoCH comes into FVG midpoint and other criteria agree. If the key area fails or stop is hit, journal contained loss and switch to secondary move.",
        selection="SOL is the visible execution instrument at the open.",
        wave="No Elliott count; CHoCH into FVG midpoint is the precise setup language.",
        thesis="A short is allowed when change of character enters the midpoint of the fair value gap, but only with all other criteria aligned.",
        structure="Key upper/lower areas, FVG midpoint, CHoCH marker, daily/resistance zones.",
        setup="He identifies key areas first, then wants break under or over for direction. The first short entry is late and fee optimization is poor.",
        entry="Short near FVG midpoint after CHoCH, but entry quality is not ideal.",
        management="Accept the stop. Do not widen or rationalize; journal it and prepare the secondary move.",
        live_changes="Immediately after stop-out he says it is okay because he has a switched bias opportunity available.",
        exit_result="Stopped out for contained loss.",
        rule_seed="choch_into_fvg_midpoint_short_requires_other_criteria_and_good_execution; late_fee_bad_entry_remains_valid_loss_sample",
        invalidation="Stop above the FVG/key area or failure of the CHoCH to produce continuation.",
        uncertainty="Exact price not readable; context and result are SRT+frame complete.",
        labels=("auto_01", "auto_02", "auto_03"),
    ))

    add(ctx(
        "-erhHuJUJiE",
        2,
        decision_type="executed_bias_switch_context",
        symbol="SOLUSDT",
        direction="short",
        youtube_window="04:11-10:45",
        anchor_seconds="431|495|585",
        market_date="2025-12-04",
        market_time="after first stop, morning",
        visible_note="Frames 08m15-10m45 show SOL weakness, failed high break, blue short target zone, red invalidation/FVG shelves, and account/dashboard panes.",
        realized_result="short moves into profit; management toward previous day low begins",
        session_macro="Bad start/down more than desired raises selectivity threshold. He does not stop trading, but the next trade must be cleaner.",
        scenario_tree="After failed high break and support-to-resistance flip, bearish scenario targets lows/previous day low. If price reclaims the underside/trend, get out.",
        selection="SOL shows clear weakness relative to the key level.",
        wave="No Elliott; support/resistance flip plus FVG is the main structure.",
        thesis="Switch bias after the first stop because SOL fails to break the high and creates a significant bearish FVG under former support.",
        structure="Failed high, trend level, support/support/support then push down as resistance, significant bearish FVG, lows/previous day low below.",
        setup="Price cannot break over the high, forms a trend level, breaks it with a significant FVG, then retests the former support as resistance.",
        entry="Short on the support-to-resistance/FVG retest after the break.",
        management="Walk stop down as it approaches previous day low; do not leave too much on table if whiplash appears.",
        live_changes="He goes from bad start/selective mode to a concrete SOL weakness short, showing bias switch rather than revenge trade.",
        exit_result="SRT confirms active profit management; later exact final is not frame-confirmed beyond 10:45.",
        rule_seed="after_stop_switch_bias_only_if_failed_high_plus_support_resistance_flip_plus_bearish_fvg",
        invalidation="Reaction off underside fails and price continues moving up through the trend/retest zone.",
        uncertainty="Frames after 10:45 are unavailable; this row stops at the frame-confirmed management phase.",
        labels=("auto_03", "auto_04"),
        gold_status="v03_gold_actionable_context_ready",
    ))

    add(ctx(
        "-erhHuJUJiE",
        3,
        decision_type="executed_trailing_management_context",
        symbol="SOLUSDT",
        direction="short",
        youtube_window="09:00-14:30",
        anchor_seconds="720",
        market_date="2025-12-04",
        market_time="late morning continuation, frame-confirmed through 10:45",
        visible_note="Frames 09m41/09m45/10m45 show continued downside chart state and management screens; SRT says target previous day low and keep walking stop loss down.",
        realized_result="profit protected/trailing; final PnL not frame-confirmed",
        session_macro="After recovering from bad start, he prioritizes extracting from the valid position without giving too much back.",
        scenario_tree="If price breaks underneath the next level, continue toward previous day low. If it fails to react off the underside trend and moves up, exit.",
        selection="SOL short remains active.",
        wave="No Elliott; lower trend/underside and previous day low are key.",
        thesis="A good short should be trailed as it approaches previous day low, but whiplash risk requires locking profit.",
        structure="Lower lows, underside trend, previous day low target, stop walking above lower highs.",
        setup="Already in the short from the support/resistance/FVG flip; this row captures the management rule as price moves down.",
        entry="No new entry; manage existing short.",
        management="Move stop loss further into profit. If price does not react from underside trend or takes too long, get out.",
        live_changes="He balances desire for a dump to previous day low against the risk of leaving too much on the table.",
        exit_result="Partial/trailing management is complete; final result belongs to unverified later frames.",
        rule_seed="trail_short_to_previous_day_low_but_exit_if_underside_retest_fails_or_whiplash_risk_rises",
        invalidation="No reaction off underside trend, reclaim of trailing stop, or excessive time without continuation.",
        uncertainty="Final exit/recap after 10:45 cannot be visually verified from local MP4.",
        labels=("auto_04",),
        gold_status="v03_gold_actionable_context_ready",
    ))

    add(ctx(
        "o5PdlOfi0-8",
        1,
        decision_type="executed_short_then_risk_reduction_context",
        symbol="SOLUSDT",
        direction="short",
        youtube_window="02:20-07:50",
        anchor_seconds="320|410|470",
        market_date="2025-12-11",
        market_time="09:30-10:17 NY local visible",
        visible_note="Frames 03m00-07m50 show HH/HL teaching overlay, failed high break, SOL 1m short box, HFT table, Bybit/TradeZella. TradeZella account timezone says GMT-05.",
        realized_result="active short; subsequent result not fully frame-confirmed",
        session_macro="He first teaches structure: higher high/higher low and failed break over high can flip trend interpretation.",
        scenario_tree="Short if price whiplashes down and retests the opposite side of the level it could not break. Reduce risk only after push under the low. Bullish alternate opens after low sweep/reclaim.",
        selection="SOL is visible and logged. ETH appears in later SRT but not in this early frame-confirmed short.",
        wave="No Elliott; HH/HL and failed high break are the structural lens.",
        thesis="A whiplash down into failed level retest is high probability enough for a short, even if premeditation was limited because he was late.",
        structure="Failed high break, opposite-side level retest, CHoCH level, low that must break for risk reduction, red/blue position box.",
        setup="Price whiplashes down, then reattempts the opposite side of the level that could not be broken. This creates his short area.",
        entry="Short is already active by 05m20. Entry is frame-relative; stop sits above the retest/failed level.",
        management="Typically reduce risk once price pushes underneath the low level, because that confirms the trend level/CHoCH break.",
        live_changes="He admits the trade was not heavily premeditated due to being late, so execution-quality tagging matters.",
        exit_result="Result after early phase is not fully visible; keep as executed/setup-management context.",
        rule_seed="short_after_whiplash_down_and_opposite_side_failed_level_retest_reduce_risk_only_after_low_break",
        invalidation="No push under the low after entry or reclaim above the failed level/retest zone.",
        uncertainty="Final PnL for this exact short is not frame-confirmed because later MP4 frames are corrupt.",
        labels=("auto_01",),
        gold_status="v03_gold_actionable_context_ready",
    ))

    add(ctx(
        "o5PdlOfi0-8",
        2,
        decision_type="conditional_bullish_flip_setup_context",
        symbol="SOLUSDT",
        direction="long",
        youtube_window="03:35-09:05",
        anchor_seconds="395|485",
        market_date="2025-12-11",
        market_time="10:00-10:20 NY local visible",
        visible_note="Frames 06m35/08m05 show low sweep, reclaim, green FVG shelves and large blue long box; 08m05 also shows split chart context.",
        realized_result="complete setup relation; fill/result partly overlaps next row",
        session_macro="The session starts volatile and direction can flip quickly. He wants movement more than a fixed bias.",
        scenario_tree="After sweeping the low and reversing, break over the level plus new FVG/retest creates bullish opportunity. If it fails into support, a downside idea may return.",
        selection="SOL remains the visible instrument.",
        wave="No Elliott; sweep/reclaim/FVG is the model.",
        thesis="Low sweep can invalidate the short idea and create a bullish reversal if price breaks back over the level while maintaining criteria.",
        structure="Swept low, reclaimed level, newly produced FVG, retest area, support below.",
        setup="Price sweeps the low, reverses, begins breaking over the level, and he waits for another FVG while criteria remain aligned.",
        entry="Long only after push over the level and retest/FVG fill, not on the first emotional reversal candle.",
        management="If filled, look for continuation but keep risk tight because the market is whippy.",
        live_changes="This is a direct thesis flip from early short to potential long; he verbalizes the alternate scenario before acting.",
        exit_result="Setup relation is complete; exact fill/result is captured in next trade 4 row.",
        rule_seed="after_low_sweep_flip_long_only_if_reclaim_level_plus_new_fvg_retest_while_criteria_hold",
        invalidation="Reclaim fails and price falls back into support/under swept low.",
        uncertainty="No standalone PnL; included because setup-intention relation is complete and useful for rule design.",
        labels=("auto_02", "auto_03"),
        gold_status="v03_gold_actionable_context_ready",
    ))

    add(ctx(
        "o5PdlOfi0-8",
        3,
        decision_type="executed_trade4_long_setup_context",
        symbol="SOLUSDT",
        direction="long",
        youtube_window="05:48-12:09",
        anchor_seconds="528|579",
        market_date="2025-12-11",
        market_time="10:17-10:30 NY local/GMT-05 visible",
        visible_note="Frame 08m48 shows TradeZella Add Trade row 12/11/2025 10:17:00 BUY SOLUSD 3800 contracts at 131.16, another SELL row at 132.49, HFT 15m bearish/5m bullish, PDL target, stoploss 131.16.",
        entry_price="131.16",
        stop_price="131.16 stoploss label/BE area visible",
        target_price="PDL/large blue box toward 135 area visible",
        realized_result="trade 4 setup and partial management; SRT notes -$275 slippage/bad fill and heavy resistance before TP1",
        session_macro="Higher timeframe is mixed: HFT 15m bearish, 5m bullish, 1H/4H bearish. He still takes the local long because reclaim/FVG criteria align.",
        scenario_tree="If reclaim holds and price fills the high-impact FVG/trend retest, continuation can run quickly into resistance/PDL. If resistance blocks or fill is poor, protect earlier.",
        selection="SOL is confirmed by TradeZella and chart. This row separates execution slippage from the setup signal.",
        wave="No Elliott; trend retest, high-impact FVG, reclaim and PDL are the features.",
        thesis="After reclaiming the opposite level, buy the high-impact FVG/trend retest if all tested confluences align.",
        structure="Reclaimed level, bullish FVG shelves, trend retest, stoploss/BE shelf at 131.16, PDL/large target zone above, heavy resistance overhead.",
        setup="Price reclaims the opposite level, pushes into trend retest, dips slightly below to fill FVG, then flips upward.",
        entry="BUY around 131.16 at 10:17 NY local; second execution row shows SELL 132.49, likely partial/closing execution.",
        management="Move risk off/near BE after push; watch heavy resistance and larger timeframe FVG for TP1. Bad fill/slippage is tagged separately.",
        live_changes="He acknowledges real-time execution cost (-$275 slippage/bad fill) while keeping the setup thesis intact.",
        exit_result="Result is not fully frame-confirmed beyond the early management; the row is kept as setup+execution-quality gold, not final PnL gold.",
        rule_seed="long_reclaim_opposite_level_high_impact_fvg_trend_retest_with_execution_slippage_tag_and_resistance_tp1",
        invalidation="Loss of reclaim/FVG shelf or inability to push through heavy resistance after fill.",
        uncertainty="Frames after 08:48 are unavailable; final TP/stop outcome is not visually verified.",
        labels=("auto_04",),
        gold_status="v03_gold_actionable_context_ready",
    ))

    add(ctx(
        "SR9eJClrtLU",
        1,
        decision_type="executed_first_trade_winner_context",
        symbol="SOLUSDT",
        direction="short",
        youtube_window="00:00-09:29",
        anchor_seconds="139|419",
        market_date="2026-01-07",
        market_time="opening to early session; 1m/15m split visible",
        visible_note="Frames 01m00-04m59 show 1 Min and 15 Min split, SOL short position area, HFT table, exchange and TradeZella panes.",
        realized_result="+5.5R first trade, about 5-6 risk factors",
        session_macro="Session goal is proper risk management and position sizing. Multi-timeframe split is part of the initial context.",
        scenario_tree="Short works if previous day low breaks and continuation reaches lower support/FVG. Exit if support/FVG starts holding because first trade profit should be banked.",
        selection="SOL is the visible instrument and journal symbol.",
        wave="No Elliott; 1m/15m alignment, previous day low and support/FVG are the core features.",
        thesis="First trade short captures downside through previous day low, but support/FVG after the break is a reason to lock instead of overstay.",
        structure="1m/15m split, previous day low, support level, FVG, blue target/short box.",
        setup="Price breaks previous day low and moves into the support/FVG area. He closes more portions as it approaches support.",
        entry="Short was active before the excerpt; exact entry is frame-relative.",
        management="Close another small portion, then fully exit at support/FVG to bank first-trade profit.",
        live_changes="He chooses profit lock because it is the first trade out of the gate, despite the break of previous day low.",
        exit_result="Fully out for about 5.5R.",
        rule_seed="first_trade_short_bank_5r_at_support_fvg_after_pdl_break_even_if_more_downside_possible",
        invalidation="Support/FVG holds and price starts reversing; for remaining runner, exit rather than let first winner come back.",
        uncertainty="Exact price is not visible in the selected frames, but direction/management/result are complete.",
        labels=("auto_01", "auto_02"),
    ))

    add(ctx(
        "SR9eJClrtLU",
        2,
        decision_type="executed_loss_context",
        symbol="SOLUSDT",
        direction="long_or_flip_attempt",
        youtube_window="05:35-11:05",
        anchor_seconds="515",
        market_date="2026-01-07",
        market_time="after first trade, mid session",
        visible_note="Frames 08m35/10m05 show SOL box after a level-break idea; SRT says all out about -1.2R, still good day.",
        realized_result="-1.2R",
        session_macro="Because first trade made +5.5R, he can accept a controlled -1.2R and remain ahead.",
        scenario_tree="If the level breaks, it can bring price back up to 137. If it fails, close the loss and wait for bearish continuation or cleaner setup.",
        selection="SOL is still the instrument.",
        wave="No Elliott; level break/reclaim toward 137 is the idea.",
        thesis="A level break can justify a flip/long attempt toward 137, but the trade must be cut if follow-through fails.",
        structure="Broken/reclaimed level, target 137, red invalidation shelf, previous support/resistance.",
        setup="He watches whether the level breaks. Once it fails to produce the expected continuation, he exits.",
        entry="Flip/long attempt around the broken level; exact price is frame-relative.",
        management="Take the -1.2R and reset because the day remains good after the first winner.",
        live_changes="He immediately considers maybe playing bearish continuation next, showing no attachment to the failed long.",
        exit_result="All out about -1.2R.",
        rule_seed="after_big_first_winner_take_small_flip_loss_if_level_break_to_target_137_fails",
        invalidation="Failure of level break/reclaim to continue toward 137.",
        uncertainty="Direction is inferred from spoken 137 upside target and box; exact order row not visible.",
        labels=("auto_03",),
    ))

    add(ctx(
        "SR9eJClrtLU",
        3,
        decision_type="executed_risk_free_short_context",
        symbol="SOLUSDT",
        direction="short",
        youtube_window="06:21-11:51",
        anchor_seconds="561|651",
        market_date="2026-01-07",
        market_time="after sweep, before Trade 4",
        visible_note="Frames 09m21/11m51 show SOL short/blue target boxes and dashboard panes. SRT says swept low, big push, risk completely off table, then retest/dump vs flip decision.",
        realized_result="risk-free trade; result partially merged with later context",
        session_macro="He wants volatility more than a fixed view; after first winner and small loss, movement is the priority.",
        scenario_tree="If sweep/retest continues to dump, hold short risk-free. If it flips, look for bullish opportunities instead.",
        selection="SOL remains visible and liquid.",
        wave="No Elliott; sweep, FVG, previous day high/session lows are spoken structures.",
        thesis="A fair value gap short after session low/previous day high response is valid, but only as risk-free once the sweep/push appears.",
        structure="Swept low, previous day high response, session lows, FVG short zone, retest level.",
        setup="He gets short off a FVG and wants break under session lows after responding off previous day high.",
        entry="Short off the FVG after the loss reset; exact price frame-relative.",
        management="Move risk completely off table quickly. Let it retest and dump if it wants; otherwise be ready to flip bullish.",
        live_changes="He explicitly says if it flips he can find bullish opportunities, so the short thesis is conditional, not dogmatic.",
        exit_result="Risk-free management state is confirmed; final PnL belongs to subsequent trade grouping.",
        rule_seed="fvg_short_after_sweep_response_move_to_be_fast_then_decide_dump_retest_or_bullish_flip",
        invalidation="Flip above the retest/FVG structure after risk is removed.",
        uncertainty="Runner outcome is not isolated; keep as risk-management context.",
        labels=("auto_04",),
        gold_status="v03_gold_actionable_context_ready",
    ))

    add(ctx(
        "SR9eJClrtLU",
        4,
        decision_type="executed_trade4_winner_context",
        symbol="SOLUSDT",
        direction="long",
        youtube_window="08:35-09:29",
        anchor_seconds="561",
        market_date="2026-01-07",
        market_time="16:22-16:25 UTC-5 visible",
        visible_note="Frame 09m29 shows Trade 4 overlay +$2,098, TradeZella SOLUSD Wed Jan 07 2026, long, net P&L $2,091.81, chart bottom 16:25 UTC-5.",
        entry_price="135.06",
        stop_price="134.58",
        target_price="136.85",
        realized_result="Trade 4 +$2,098 overlay; TradeZella net P&L $2,091.81",
        session_macro="Late-day SOL setup after earlier winner/loss sequence; HFT table in frame is bullish across visible rows.",
        scenario_tree="If price reclaims PDL/support and holds the long shelf, target the upper box around 136.85. If it loses the 134.58 stop area, exit.",
        selection="SOL is confirmed by TradeZella and order panel.",
        wave="No Elliott; PDL reclaim/support, FVG shelves and trend break are the features.",
        thesis="Long after sweep/flip when price holds above PDL/support and HFT is bullish, targeting the next liquidity/box high.",
        structure="PDL horizontal, local support at 135 area, green FVG beneath, blue target box to 136.85, stop at 134.58.",
        setup="Price sweeps/reclaims and starts holding the level. The long box is placed with about 3.7R reward/risk.",
        entry="Long around 135.06, stop 134.58, target 136.85; visible order panel quantity 2083 SOL.",
        management="Let the long work while risk is defined; take profit when Trade 4 reaches about $2.1K.",
        live_changes="This is the bullish-opportunity branch that he said would be available if the prior short flipped.",
        exit_result="Trade 4 closed/recorded for +$2,098 overlay and +$2,091.81 net in TradeZella.",
        rule_seed="bullish_flip_long_after_pdl_reclaim_with_hft_bullish_entry_13506_sl_13458_tp_13685",
        invalidation="Break below 134.58 or loss of PDL/reclaim support.",
        uncertainty="UTC-5 is visible despite legacy field name UTC_minus4; stored as NY local with note.",
        labels=("auto_02", "auto_04"),
    ))

    return rows


def build_hold_rows() -> list[dict[str, str]]:
    return [
        ctx(
            "-erhHuJUJiE",
            98,
            decision_type="hold_late_eth_switch_and_dual_runner_unverified",
            symbol="ETHUSDT|SOLUSDT",
            direction="long_or_mixed",
            youtube_window="11:21-19:57",
            anchor_seconds="861|920|1047",
            market_date="2025-12-04",
            market_time="late session after 10:45",
            visible_note="SRT contains bullish FVG long, ETH switch, support/resistance flip and two running positions, but local MP4 produces no stable frames after 10:45 due H.264/NAL errors.",
            realized_result="hold",
            session_macro="Later session likely includes recovery toward title +$6,157, but visual evidence is incomplete.",
            scenario_tree="Potential long if bullish FVG fills and level flips; potential ETH setup after high-impact area. Needs frame verification.",
            selection="ETH switch is spoken; not visually confirmed from local frames.",
            wave="No confirmed Elliott visual evidence.",
            thesis="Do not gold-upgrade SRT-only late trades when chart/position/result cannot be checked.",
            structure="Spoken underside/overside level, bullish FVG, ETH resistance/support flip.",
            setup="Candidate setup is plausible but incomplete under v0.3 rules.",
            entry="Unknown visually.",
            management="Unknown visually beyond SRT comments about risk elimination and runners.",
            live_changes="He switches symbols and talks about near-entry reversals, but frame context is missing.",
            exit_result="Not visually verified.",
            rule_seed="hold_if_srt_has_trade_but_frames_after_corruption_missing",
            invalidation="Need recovered video frame or alternate source.",
            uncertainty="MP4 frames after 10:45 failed; keep out of rule-seed gold until recovered.",
            labels=("auto_04",),
            gold_status="v03_hold_context_needs_frame_recovery",
        ),
        ctx(
            "o5PdlOfi0-8",
            98,
            decision_type="hold_late_trade5_to_trade9_unverified",
            symbol="SOLUSDT|ETHUSDT",
            direction="mixed",
            youtube_window="09:50-22:22",
            anchor_seconds="740|1039|1111|1192",
            market_date="2025-12-11",
            market_time="after 10:30 NY local",
            visible_note="SRT contains trade 5, ETH short trade 6, trend-level short, long-shot 139 scenario, gym/missed-trend and trailing context. Local MP4 does not produce stable frames after 08:48.",
            realized_result="hold",
            session_macro="The title implies many trades and +$4,759, but the later trade outcomes cannot be frame-reconciled.",
            scenario_tree="Later day includes short continuation, heavy resistance/FVG, possible 139 upside, missed trend and trailing short. Needs visual verification.",
            selection="SOL and ETH are both spoken in SRT-only section.",
            wave="No visual Elliott confirmation.",
            thesis="Do not treat late SRT-only trade cluster as gold because chart zoom, cursor explanation, and position boxes are unavailable.",
            structure="Spoken support/reclaim/rejection, trend level, heavy resistance/FVG, consolidation sweep.",
            setup="Multiple plausible setups but not v0.3-complete.",
            entry="Unknown visually.",
            management="SRT says small win, BE, trail, reduce stop to BE, but exact link to boxes/results is missing.",
            live_changes="He changes from short to possible 139 upside and back to missed-trend/trailing short, but frames are unavailable.",
            exit_result="Not visually verified.",
            rule_seed="hold_late_corrupt_mp4_trade_cluster_do_not_gold_without_frame_or_repaired_video",
            invalidation="Need alternate intact video or recovered frames.",
            uncertainty="MP4 corruption after 08:48 blocks visual audit.",
            labels=("auto_04",),
            gold_status="v03_hold_context_needs_frame_recovery",
        ),
    ]


def audit_rows(contexts: list[dict[str, str]], hold: list[dict[str, str]], sessions: list[dict[str, str]]) -> list[dict[str, str]]:
    out = []
    by_video: dict[str, list[dict[str, str]]] = {video_id: [] for video_id in BATCH_IDS}
    for row in contexts + hold:
        by_video.setdefault(row["video_id"], []).append(row)
    session_ids = {row["video_id"] for row in sessions}
    notes = {
        "-erhHuJUJiE": "초반 3개 context는 SRT+프레임+차트 구조가 완결. 10:45 이후 MP4 손상으로 후반 ETH/SOL switch cluster는 hold.",
        "o5PdlOfi0-8": "앞부분 3개 context는 프레임/TradeZella 시간까지 확인. 08:48 이후 MP4 손상으로 trade 5-9 cluster는 hold.",
    }
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
                "v03_quality_note_ko": notes.get(video_id, "로컬 SRT 후보, 선별 프레임, 실제 시장 날짜/시간, 1m OHLCV 캐시를 연결해 v0.3 필드로 정리."),
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

    write_csv(PROCESSED / "gold_v03_batch_02_video_session_maps.csv", sessions, SESSION_FIELDS)
    write_csv(PROCESSED / "gold_v03_batch_02_trade_context_queue.csv", ready_contexts, CTX_FIELDS)
    write_csv(PROCESSED / "gold_v03_batch_02_hold_context_queue.csv", hold_contexts, CTX_FIELDS)
    write_csv(PROCESSED / "gold_v03_batch_02_all_context_queue.csv", all_contexts, CTX_FIELDS)
    write_csv(PROCESSED / "gold_v03_batch_02_rule_seed_queue.csv", rules, RULE_FIELDS)
    write_csv(PROCESSED / "gold_v03_batch_02_quality_audit.csv", audit, AUDIT_FIELDS)

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
        "# v0.3 Batch 02 - Next 7 Oldest Remaining Videos",
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
        f"batch02 sessions={len(sessions)} contexts={len(ready_contexts)} hold={len(hold_contexts)} rules={len(rules)} summary={OUT_SUMMARY}"
    )


if __name__ == "__main__":
    main()
