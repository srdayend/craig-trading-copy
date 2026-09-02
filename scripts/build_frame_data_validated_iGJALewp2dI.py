from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRAME_DIR = ROOT / "data/source/craig_frames/browser_review/iGJALewp2dI_frame_data_pass"
OUT_DIR = ROOT / "data/processed/gold_context_trades"
OUT_SESSIONS = OUT_DIR / "frame_data_video_session_maps_v0_1.csv"
OUT_TRADES = OUT_DIR / "frame_data_trade_context_queue_v0_1.csv"
OUT_RULES = OUT_DIR / "frame_data_rule_seed_queue_v0_1.csv"
OUT_SUMMARY = ROOT / "outputs/frame_data_validated_iGJALewp2dI_summary.md"


def rel(name: str) -> str:
    return (FRAME_DIR / name).relative_to(ROOT).as_posix()


SESSION_FIELDS = [
    "session_context_id",
    "video_id",
    "scope_order",
    "video_title",
    "processed_status",
    "market_dates_utc_minus4",
    "primary_symbols",
    "confirmed_timeframes",
    "session_map_ko",
    "strategy_map_ko",
    "data_used_ko",
    "frame_method_ko",
    "frame_contact_sheet",
    "remaining_uncertainty_ko",
]

TRADE_FIELDS = [
    "context_id",
    "video_id",
    "scope_order",
    "sequence_in_video",
    "decision_type",
    "gold_status",
    "symbol",
    "direction",
    "chart_timeframe",
    "market_date_utc_minus4",
    "market_time_window_utc_minus4",
    "market_time_confidence",
    "youtube_window",
    "youtube_anchor_sec",
    "entry_price",
    "stop_price",
    "target_price",
    "realized_result",
    "risk_management_result",
    "pre_trade_context_ko",
    "setup_context_ko",
    "entry_plan_ko",
    "management_ko",
    "exit_result_ko",
    "frame_evidence_paths",
    "ohlcv_alignment_ko",
    "rule_extraction_notes_ko",
    "remaining_uncertainty_ko",
]

RULE_FIELDS = [
    "rule_seed_id",
    "context_id",
    "rule_family",
    "market_state_filter_ko",
    "setup_trigger_ko",
    "entry_rule_seed_ko",
    "invalidation_rule_seed_ko",
    "management_rule_seed_ko",
    "take_profit_rule_seed_ko",
    "do_not_trade_or_exit_rule_seed_ko",
    "quant_features_to_measure",
    "source_strength",
]


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    sessions = [
        {
            "session_context_id": "iGJALewp2dI_session_01",
            "video_id": "iGJALewp2dI",
            "scope_order": "15",
            "video_title": "LIVE TRADING CRYPTO - How I Profit $2,963 With Controlled Risk",
            "processed_status": "frame_plus_ohlcv_validated_first_pass",
            "market_dates_utc_minus4": "2025-03-26 SOL session; 2025-03-27 ETH morning extension",
            "primary_symbols": "SOLUSDT, ETHUSDT",
            "confirmed_timeframes": "TradingView 1m chart visible in frames; Craig also monitors session-level structure and NY open.",
            "session_map_ko": (
                "SOL이 메인 watchlist이고 ETH/ATOM도 보조 후보. 초반에는 2025-03-26 NY 09:30 개장 이후 변동성이 커진 SOL을 본다. "
                "그는 하루 bias가 하방으로 기울 수 있음을 말하면서도, downtrend break와 bullish FVG retest가 나오면 long도 받을 수 있다고 설명한다. "
                "오전에는 SOL에서 long loss -> capitulation bounce long small win -> CHoCH/sell-signal short big win -> rejection-wick long BE가 이어진다. "
                "저녁 9:30 PM에는 SOL에서 5파 상승/트렌드 break/retest short를 시도했다가 실패하고, 다음날 아침 9:30경 ETH short로 하루를 마감한다."
            ),
            "strategy_map_ko": (
                "공통 구조는 1m FVG midpoint/zone에서 limit 또는 live entry를 잡고, trend break, CHoCH, sell/buy signal, underside/overside retest, "
                "local high/low break를 필터로 쓴다. 목표는 큰 R multiple이지만, Craig의 영역은 setup 완성/entry/stop/management까지이고, "
                "이후 가격이 안 움직이면 BE 또는 small win으로 끊는다. 손실은 hard stop으로 제한하고, trend continuation이 확인되면 risk를 BE/inside로 줄인다."
            ),
            "data_used_ko": (
                "SOLUSDT 1m 2025-03-26 NY cache, ETHUSDT 1m 2025-03-27 NY cache. "
                "2025-03-27 ETH/BTC/SOL 캐시는 이번 검증 중 추가로 받아 저장했다."
            ),
            "frame_method_ko": (
                "로그인된 YouTube 탭에서 theater mode로 확대 후, 후보별 setup/entry/management/recap 지점만 timestamp URL로 이동해 캡처했다. "
                "자막이 숫자를 가리는 주요 프레임은 captions off 재캡처를 추가했다."
            ),
            "frame_contact_sheet": rel("iGJALewp2dI_frame_data_pass_contact_sheet.jpg"),
            "remaining_uncertainty_ko": "하단축 OCR이 아니라 프레임 가격 + 자막 시간 + OHLCV 구조 정렬이다. 일부 체결 시각은 분 단위 추정으로 유지한다.",
        }
    ]

    trades = [
        {
            "context_id": "iGJALewp2dI_fd_01_trade1_sol_long_loss",
            "video_id": "iGJALewp2dI",
            "scope_order": "15",
            "sequence_in_video": "1",
            "decision_type": "executed_trade",
            "gold_status": "gold_frame_data_context_ready",
            "symbol": "SOLUSDT",
            "direction": "long",
            "chart_timeframe": "1m",
            "market_date_utc_minus4": "2025-03-26",
            "market_time_window_utc_minus4": "09:47-09:50",
            "market_time_confidence": "medium_frame_price_ohlcv_alignment",
            "youtube_window": "04:58-07:08",
            "youtube_anchor_sec": "321|383|407|1238",
            "entry_price": "143.41",
            "stop_price": "143.19",
            "target_price": "145.26",
            "realized_result": "-$676 full loss",
            "risk_management_result": "Hard stop respected immediately; no averaging or holding loss.",
            "pre_trade_context_ko": (
                "초반 macro/session 생각은 하방 momentum 전환 가능성을 열어둔 상태였다. 다만 그는 market이 위로 flip할 경우 long도 배제하지 않았다. "
                "NY 09:30 open 이후 변동성이 커지고, SOL에서 하락 추세선이 위로 깨진 뒤 retest/FVG long 기회가 생겼다고 판단했다."
            ),
            "setup_context_ko": (
                "SOL 1m에서 downtrend break 이후 bullish FVG/green demand zone으로 되돌림을 기다린 setup. "
                "처음에는 entry를 놓쳤다고 말하지만, 가격이 다시 내려오면 consistency 있게 같은 risk sizing으로 fishing limit를 둘 계획이었다."
            ),
            "entry_plan_ko": "Position calculator로 $500 risk 기준 limit long. Frame에서 entry 143.41, SL 143.19, TP 145.26, R/R 8.41 확인.",
            "management_ko": "체결 직후 빠른 flip을 기대했지만, sell-side pressure가 zone을 관통하면 손실을 제한하고 다음 trade를 찾겠다는 태도.",
            "exit_result_ko": "가격이 key area를 관통해 stop을 맞고 full loss. Journal에는 -$676 loss, confidence 2로 기록.",
            "frame_evidence_paths": "|".join(
                [
                    rel("0298_session_map_ny_open_first_setup.png"),
                    rel("0321_trade1_order_box_entry_sl_tp.png"),
                    rel("0383_trade1_box_nocaption.png"),
                    rel("0407_trade1_stopped_out.png"),
                    rel("1238_recap_trade1.png"),
                ]
            ),
            "ohlcv_alignment_ko": (
                "SOL 2025-03-26 09:20-09:50: high 144.38 at 09:40, then 09:50 candle low 142.67. "
                "Frame entry 143.41 and SL 143.19 are both crossed by the 09:50 selloff candle, matching immediate stop-out."
            ),
            "rule_extraction_notes_ko": (
                "Bearish macro bias가 있어도 intraday downtrend break + bullish FVG retest가 나오면 counter long 허용. "
                "단, opening volatility에서는 zone 관통 시 즉시 손절하고 thesis를 하방 momentum 쪽으로 전환."
            ),
            "remaining_uncertainty_ko": "하단축 직접 OCR은 하지 않았으므로 setup/order exact minute는 09:47-09:50 window로 둔다.",
        },
        {
            "context_id": "iGJALewp2dI_fd_02_trade2_sol_long_small_win",
            "video_id": "iGJALewp2dI",
            "scope_order": "15",
            "sequence_in_video": "2",
            "decision_type": "executed_trade",
            "gold_status": "gold_frame_data_context_ready",
            "symbol": "SOLUSDT",
            "direction": "long",
            "chart_timeframe": "1m",
            "market_date_utc_minus4": "2025-03-26",
            "market_time_window_utc_minus4": "10:42-12:00+",
            "market_time_confidence": "medium_frame_price_ohlcv_alignment",
            "youtube_window": "07:46-11:27",
            "youtube_anchor_sec": "497|535|658|1254",
            "entry_price": "139.17",
            "stop_price": "138.76",
            "target_price": "141.93",
            "realized_result": "+$131 small win / near breakeven",
            "risk_management_result": "Alert at recent high and stop; exited when chop and bearish response invalidated the expected flip.",
            "pre_trade_context_ko": (
                "Trade1 이후 SOL이 크게 매도되었고, 그는 큰 selloff 뒤에는 rebound가 자주 나온다고 설명한다. "
                "핵심은 무작정 저점 매수가 아니라, FVG 반응과 bullish momentum indication이 있어야 임시 반등을 long으로 플레이한다는 점."
            ),
            "setup_context_ko": (
                "강한 하락이 bullish FVG/key level로 내려온 뒤, 해당 zone을 두 번 invalidate/react하면서 저점이 버티면 flip과 session upside continuation이 가능하다고 보았다. "
                "중요 관찰 레벨은 위쪽 local break level이며, 이 레벨이 깨져야 rest-of-session bullish break로 판단한다."
            ),
            "entry_plan_ko": "FVG midpoint/zone long. Frame에서 entry 139.17, SL 138.76, TP 141.93, R/R 6.73 확인.",
            "management_ko": (
                "가격이 방향으로 움직이기 시작하자 recent high와 stop-loss level에 alert를 건다. "
                "이후 bearish price action이 다시 나오면 bounce가 없거나 local low를 깨면 trade를 접겠다고 말한다."
            ),
            "exit_result_ko": "오랫동안 sideways chop이 이어지고 원하는 deliberate direction이 나오지 않아 break-even 수준에서 정리. Journal/recap 기준 +$131.",
            "frame_evidence_paths": "|".join(
                [
                    rel("0497_trade2_box_nocaption.png"),
                    rel("0535_trade2_key_break_level.png"),
                    rel("0658_trade2_close_be_small_win.png"),
                    rel("1254_recap_trade2.png"),
                ]
            ),
            "ohlcv_alignment_ko": (
                "SOL 10:42-10:45에 139.17 entry zone이 터치되고, 10:45 low는 138.83으로 frame SL 138.76을 narrowly hold. "
                "10:54 high 140.51까지 반등했지만 TP 141.93은 미도달. 이후 12시대에는 139-140 부근 chop으로, small-win/BE exit narrative와 일치."
            ),
            "rule_extraction_notes_ko": (
                "Capitulation 후 long은 FVG reaction + low hold + local break 필요. "
                "목표 방향 돌파가 안 나오고 chop이 길어지면 작은 이익/BE로 종료한다."
            ),
            "remaining_uncertainty_ko": "정확한 exit minute은 recap/journal과 자막 기반이며 하단축 직접 판독은 미완.",
        },
        {
            "context_id": "iGJALewp2dI_fd_03_trade3_sol_short_big_win",
            "video_id": "iGJALewp2dI",
            "scope_order": "15",
            "sequence_in_video": "3",
            "decision_type": "executed_trade",
            "gold_status": "gold_frame_data_context_ready",
            "symbol": "SOLUSDT",
            "direction": "short",
            "chart_timeframe": "1m",
            "market_date_utc_minus4": "2025-03-26",
            "market_time_window_utc_minus4": "12:49-13:35",
            "market_time_confidence": "medium_frame_price_ohlcv_alignment",
            "youtube_window": "11:28-14:00",
            "youtube_anchor_sec": "699|778|815|1271",
            "entry_price": "139.61",
            "stop_price": "139.90",
            "target_price": "138.06 initial/placeholder; lower box target about 137.30 visible later",
            "realized_result": "+$2,596 / about 5.55R",
            "risk_management_result": "Reduced risk to near breakeven after candle close below neckline/new low; intended to trail, but placeholder TP caused early exit.",
            "pre_trade_context_ko": (
                "Trade2 long이 원하는 upside continuation을 만들지 못하고 weakness가 감지되자 bias를 short로 flip한다. "
                "그는 sell signal과 change of character가 나왔고, 이전 long 구간에서 보던 구조가 이제 short thesis로 바뀌었다고 설명한다."
            ),
            "setup_context_ko": (
                "Local high에서 rejection을 받은 뒤 price가 아래 session lows/neckline을 깨면 큰 downside continuation이 가능하다고 보았다. "
                "Frame에는 SL 139.90, entry 139.61, TP 138.06 short box가 보인다."
            ),
            "entry_plan_ko": "CHoCH + sell signal 이후 FVG/entry zone short. 목표는 단순 TP보다 session downside trail.",
            "management_ko": (
                "Neckline 아래 candle close를 기다려 risk를 profit/BE inside로 낮춘다. "
                "그 후 low break가 이어지면 all-day runner로 trail하려 했으나, chart에 남겨둔 placeholder take-profit이 체결되어 조기 청산."
            ),
            "exit_result_ko": "Recap 기준 +$2,596, 약 5.5R. 그는 여전히 들고 있었다면 더 큰 downside를 먹을 수 있었다며 아쉬워함.",
            "frame_evidence_paths": "|".join(
                [
                    rel("0699_trade3_box_nocaption.png"),
                    rel("0778_trade3_reduce_risk_break_low.png"),
                    rel("0815_trade3_accidental_tp.png"),
                    rel("1271_recap_trade3.png"),
                ]
            ),
            "ohlcv_alignment_ko": (
                "SOL 12:30-13:40 window에서 12:49 candle이 139.61 level을 터치하고, 13:20 이후 138.4대, 13:33 low 137.73까지 하락. "
                "139.90 stop은 entry 이후 유지되고, 138.06/138.0 부근 exit narrative와 데이터가 맞다."
            ),
            "rule_extraction_notes_ko": (
                "Failed bullish continuation -> CHoCH/sell signal -> resistance rejection -> neckline break short. "
                "Risk reduction trigger는 candle close below key neckline/new low."
            ),
            "remaining_uncertainty_ko": "실제 placeholder TP 가격은 recap 발화상 138 근처, frame box에는 138.06과 lower 137.30 target이 함께 보임.",
        },
        {
            "context_id": "iGJALewp2dI_fd_04_trade4_sol_long_breakeven",
            "video_id": "iGJALewp2dI",
            "scope_order": "15",
            "sequence_in_video": "4",
            "decision_type": "executed_trade",
            "gold_status": "gold_frame_data_context_ready",
            "symbol": "SOLUSDT",
            "direction": "long",
            "chart_timeframe": "1m",
            "market_date_utc_minus4": "2025-03-26",
            "market_time_window_utc_minus4": "14:10-14:55",
            "market_time_confidence": "high_visible_time_overlay_plus_ohlcv",
            "youtube_window": "14:19-16:29",
            "youtube_anchor_sec": "860|975|1292",
            "entry_price": "about 137.90",
            "stop_price": "about 137.56",
            "target_price": "upper flip/runner target, not fixed; frame box projects toward 139+",
            "realized_result": "breakeven",
            "risk_management_result": "Manual close at breakeven before price retested trend overside and stop area.",
            "pre_trade_context_ko": (
                "Trade3 조기 익절 후 SOL이 더 밀리는 것을 보며 아쉬워하지만, 또 다른 large R 기회를 찾는다. "
                "그는 원래 FVG retest를 노렸으나 가격이 더 빠르게 더 낮게 움직였다고 설명한다."
            ),
            "setup_context_ko": (
                "낮은 위치의 rejection wick이 아래에 대기하던 주문/liquidity를 보여준다고 보고, 큰 push up이 나온 뒤 빠른 flip long을 시도한다. "
                "다만 'little bit weird'한 포지션이라고 스스로 보수적으로 말한다."
            ),
            "entry_plan_ko": "$500 risk 기준 deep SOL long. 또 다른 low가 깨지면 $500 loss로 종료, 위쪽 level에 닿으면 risk reduction.",
            "management_ko": "Lunch/gym 전후로 수동 관찰. All-day runner 가능성을 기대하지만, trend overside를 다시 테스트하면 stop까지 이어질 수 있어 breakeven close.",
            "exit_result_ko": "Recap 기준 breakeven. 이후 데이터상 가격은 14:54-14:57에 137.56 부근을 깨고 15:13 low 136.13까지 내려가므로 BE 방어가 타당했다.",
            "frame_evidence_paths": "|".join(
                [
                    rel("0860_trade4_long_rejection_wick.png"),
                    rel("0975_trade4_close_breakeven.png"),
                    rel("1292_recap_trade4.png"),
                ]
            ),
            "ohlcv_alignment_ko": (
                "SOL 14:10 low 137.63/14:09 low 137.58 이후 14:31 high 138.63까지 반등. "
                "그러나 14:54-14:57에 137.56 level을 재차 침범하고 15:13 low 136.13으로 이어져, Craig의 BE close reason과 일치."
            ),
            "rule_extraction_notes_ko": (
                "Rejection wick/liquidity sweep 이후 long은 가능하지만, 구조가 이상하고 runner confirmation이 없으면 BE로 방어. "
                "다음 level 도달 전 trend overside retest 위험이 커지면 포지션 종료."
            ),
            "remaining_uncertainty_ko": "Frame의 full calculator 숫자는 일부 작아 entry/SL은 약값으로 기록.",
        },
        {
            "context_id": "iGJALewp2dI_fd_05_trade5_sol_short_loss",
            "video_id": "iGJALewp2dI",
            "scope_order": "15",
            "sequence_in_video": "5",
            "decision_type": "executed_trade",
            "gold_status": "gold_frame_data_context_ready",
            "symbol": "SOLUSDT",
            "direction": "short",
            "chart_timeframe": "1m",
            "market_date_utc_minus4": "2025-03-26",
            "market_time_window_utc_minus4": "21:30-22:00+",
            "market_time_confidence": "high_visible_time_overlay_plus_ohlcv",
            "youtube_window": "17:20-18:47 + recap 21:45",
            "youtube_anchor_sec": "1075|1305",
            "entry_price": "138.11",
            "stop_price": "about 138.40-138.41",
            "target_price": "136.63",
            "realized_result": "-$613 full loss",
            "risk_management_result": "No risk reduction because expected low retest/continuation failed; stopped as price trended up.",
            "pre_trade_context_ko": (
                "Gym/dinner 후 market이 sideways chop이라 어느 key level이 깨지는지 기다린다. "
                "그는 위 trend break 또는 아래 trend break 중 방향이 정해진 뒤 그 방향으로만 trade하겠다고 말한다."
            ),
            "setup_context_ko": (
                "SOL이 5파 상승 구조를 만든 뒤 trendline을 깨고 underside를 retest. "
                "Change of character와 sell signal 이후 FVG를 통해 short entry를 잡았고, local low retest와 downside continuation을 기대했다."
            ),
            "entry_plan_ko": "9:30 PM visible overlay. Frame에서 entry 138.11, TP 136.63, SL 138.4대 short position box 확인.",
            "management_ko": "Underside trend response가 나오면 alert 아래 level을 두고 trade를 방치. 그러나 low retest/continuation이 나오지 않으면 stop으로 종료.",
            "exit_result_ko": "Recap 기준 -$613 full loss. 가격은 아래로 이어지지 못하고 위로 trend해 stop 영역을 넘어섰다.",
            "frame_evidence_paths": "|".join(
                [
                    rel("1075_trade5_box_nocaption.png"),
                    rel("1305_recap_trade5.png"),
                ]
            ),
            "ohlcv_alignment_ko": (
                "SOL 21:28-21:34에 138.11 entry level을 여러 번 터치. 21:50-21:53에 138.40 stop zone을 침범하고, 22:19 high 139.50까지 상승. "
                "TP 136.63은 해당 window에서 미도달."
            ),
            "rule_extraction_notes_ko": (
                "Wave/trendline break + underside retest + FVG/CHoCH sell setup은 short 후보. "
                "하지만 key low retest가 나오지 않고 stop zone 위로 올라가면 full loss로 종료."
            ),
            "remaining_uncertainty_ko": "정확한 stop fill minute은 recap 기반. 데이터상 21:50-21:53 사이 stop zone 침범이 첫 강한 후보.",
        },
        {
            "context_id": "iGJALewp2dI_fd_06_trade6_eth_short_win",
            "video_id": "iGJALewp2dI",
            "scope_order": "15",
            "sequence_in_video": "6",
            "decision_type": "executed_trade",
            "gold_status": "gold_frame_data_context_ready",
            "symbol": "ETHUSDT",
            "direction": "short",
            "chart_timeframe": "1m",
            "market_date_utc_minus4": "2025-03-27",
            "market_time_window_utc_minus4": "09:30-10:25",
            "market_time_confidence": "high_spoken_time_plus_frame_price_ohlcv_alignment",
            "youtube_window": "18:42-20:32 + recap 22:08",
            "youtube_anchor_sec": "1145|1225|1328",
            "entry_price": "about 2005.7",
            "stop_price": "about 2011.1",
            "target_price": "about 1991.6 initial; managed manually before/after low break failure",
            "realized_result": "+$1,514 / about 2R",
            "risk_management_result": "Moved stop/exit line above local high; closed manually when price failed to keep breaking lower.",
            "pre_trade_context_ko": (
                "다음날 아침, 전날 밤 SOL short loss 후 좋은 trade가 없어서 밤새 trade하지 않았다고 말한다. "
                "하루를 BE~small profit로 끝낼 수도 있지만, 마지막 좋은 setup이 나오면 수익을 늘리려는 상태."
            ),
            "setup_context_ko": (
                "ETH가 전체 session에서 하락 추세를 만들고 있었고, midpoint FVG와 trend underside retest가 겹친다. "
                "그는 break 아래에서 local low를 깨고 rest-of-day continuation이 나오길 기대한다."
            ),
            "entry_plan_ko": "ETH 1m short. Frame에서 ETHUSDT, entry 약 2005.7, SL 약 2011.1, TP 약 1991.6 수준의 short box 확인.",
            "management_ko": (
                "가격이 아래로 움직인 후 약 2-2.5R이 열리자 stop을 local high 위로 옮기거나, 그 high를 넘으면 작은 win으로 닫는 계획을 말한다. "
                "더 큰 downside runner를 원하지만 하루 종일 붙잡고 있지 않겠다고 판단."
            ),
            "exit_result_ko": "Manual exit for +$1,514. Recap에서는 trend break 후 FVG entry, underside retest, 약 2R trade였다고 정리.",
            "frame_evidence_paths": "|".join(
                [
                    rel("1145_trade6_eth_fvg_entry.png"),
                    rel("1225_trade6_exit.png"),
                    rel("1328_recap_trade6.png"),
                ]
            ),
            "ohlcv_alignment_ko": (
                "ETH 2025-03-27 09:30 open 2006.90, 09:32 low 1996.48, 09:40 low 1985.71로 frame target zone 방향 급락. "
                "이후 10:00-10:20에는 2007 부근까지 되돌리며 lower-break continuation이 둔화되어 manual exit logic과 부합."
            ),
            "rule_extraction_notes_ko": (
                "Fresh morning session에서 ETH downtrend + midpoint FVG + underside retest short. "
                "좋은 move가 나온 뒤 lower low continuation이 실패하고 local high를 넘을 위험이 있으면 runner 욕심보다 realized win을 확보."
            ),
            "remaining_uncertainty_ko": "2025-03-27 데이터는 이번 검증 중 새로 fetch. 하단축 직접 OCR은 아직 없지만 spoken 9:30 + ETH price structure alignment가 강함.",
        },
    ]

    rules = [
        {
            "rule_seed_id": "iGJ_rule_01_counter_long_after_break_retest",
            "context_id": "iGJALewp2dI_fd_01_trade1_sol_long_loss",
            "rule_family": "counter_bias_fvg_long",
            "market_state_filter_ko": "Macro/session bias가 하방이어도 NY open 이후 local downtrend가 상방 break되고 bullish FVG retest가 있으면 long 허용.",
            "setup_trigger_ko": "하락 추세선 break -> FVG/demand zone retest -> limit entry.",
            "entry_rule_seed_ko": "FVG midpoint 또는 green zone 안에서 $risk 고정 position calculator entry.",
            "invalidation_rule_seed_ko": "FVG/zone을 강하게 관통하거나 SL 아래 candle wick/print가 나오면 thesis 폐기.",
            "management_rule_seed_ko": "Opening volatility에서는 반응이 빠르게 안 나오면 손실을 작게 제한.",
            "take_profit_rule_seed_ko": "초기 TP는 distant liquidity/high target, high R/R.",
            "do_not_trade_or_exit_rule_seed_ko": "Zone 관통 후 hope-hold 금지.",
            "quant_features_to_measure": "NY open minutes; trendline break; FVG midpoint touch; local low distance; immediate adverse excursion",
            "source_strength": "strong_frame_price_plus_ohlcv",
        },
        {
            "rule_seed_id": "iGJ_rule_02_capitulation_fvg_bounce_long",
            "context_id": "iGJALewp2dI_fd_02_trade2_sol_long_small_win",
            "rule_family": "post_selloff_bounce_long",
            "market_state_filter_ko": "Massive selloff 이후 rebound 가능성을 찾지만, 반드시 key FVG reaction과 low hold가 필요.",
            "setup_trigger_ko": "Selloff into FVG -> two reactions/invalidations -> watch local break level.",
            "entry_rule_seed_ko": "FVG/key level long, SL just below defended low.",
            "invalidation_rule_seed_ko": "Local low가 깨지거나 bearish response가 계속되면 close/avoid.",
            "management_rule_seed_ko": "Recent high와 stop에 alert. Break가 없고 chop이면 small win/BE exit.",
            "take_profit_rule_seed_ko": "Full TP는 upper FVG/high, 하지만 continuation 확인 전에는 욕심 줄임.",
            "do_not_trade_or_exit_rule_seed_ko": "Deliberate direction 없이 sideways chop이 길면 포지션 유지하지 않음.",
            "quant_features_to_measure": "selloff magnitude; FVG touch count; low hold; time-in-trade; local break success/failure",
            "source_strength": "strong_frame_price_plus_ohlcv",
        },
        {
            "rule_seed_id": "iGJ_rule_03_failed_long_to_choch_short",
            "context_id": "iGJALewp2dI_fd_03_trade3_sol_short_big_win",
            "rule_family": "bias_flip_choch_short",
            "market_state_filter_ko": "Long thesis가 chop/weakness로 실패하고 sell signal + CHoCH가 생길 때 short bias로 flip.",
            "setup_trigger_ko": "Rejection off local high/resistance -> CHoCH/sell signal -> neckline/new low break.",
            "entry_rule_seed_ko": "FVG/entry zone에서 short, SL above rejection high.",
            "invalidation_rule_seed_ko": "Rejection high/SL 위로 회복하면 short thesis 폐기.",
            "management_rule_seed_ko": "Candle close below neckline/new low 후 risk를 BE 또는 profit 안쪽으로 축소.",
            "take_profit_rule_seed_ko": "목표는 low/liquidity 및 possible all-day runner; placeholder TP가 있으면 조기 청산 위험.",
            "do_not_trade_or_exit_rule_seed_ko": "Neckline close가 없으면 risk reduction/continuation 가정 금지.",
            "quant_features_to_measure": "prior failed long; CHoCH marker; resistance rejection wick; close below neckline; MFE before retrace",
            "source_strength": "strong_frame_price_plus_ohlcv",
        },
        {
            "rule_seed_id": "iGJ_rule_04_rejection_wick_deep_long_be_defense",
            "context_id": "iGJALewp2dI_fd_04_trade4_sol_long_breakeven",
            "rule_family": "liquidity_rejection_quick_flip_long",
            "market_state_filter_ko": "강한 하락 뒤 아래 주문/liquidity가 rejection wick으로 드러나고 빠른 flip 가능성이 있을 때만 deep long.",
            "setup_trigger_ko": "Original FVG target보다 더 빠르게 낮게 밀림 -> rejection wick -> push up -> quick flip attempt.",
            "entry_rule_seed_ko": "Rejection area 근처 deep entry, next low break를 hard invalidation.",
            "invalidation_rule_seed_ko": "Another low break 또는 trend overside retest 위험이 커지면 종료.",
            "management_rule_seed_ko": "다음 upside level에 도달하면 risk reduction. Confirmation이 없으면 BE close.",
            "take_profit_rule_seed_ko": "Runner 가능성을 보되 fixed TP보다 구조 확인 우선.",
            "do_not_trade_or_exit_rule_seed_ko": "Weird/lower-quality position은 오래 버티지 않고 BE 방어.",
            "quant_features_to_measure": "wick depth below level; push-up impulse; next low distance; failure-to-hold overside",
            "source_strength": "medium_strong_frame_plus_ohlcv",
        },
        {
            "rule_seed_id": "iGJ_rule_05_wave_trendline_retest_short",
            "context_id": "iGJALewp2dI_fd_05_trade5_sol_short_loss",
            "rule_family": "trendline_break_underside_retest_short",
            "market_state_filter_ko": "Sideways chop 이후 방향이 나올 때까지 기다린다. 5파 상승 구조 후 trendline break면 short 후보.",
            "setup_trigger_ko": "1-2-3-4-5 rise -> trend break -> underside retest -> FVG + CHoCH sell signal.",
            "entry_rule_seed_ko": "Underside/FVG retest에서 short, SL over retest high.",
            "invalidation_rule_seed_ko": "Low retest 실패 후 retest high/SL 위로 밀면 full loss.",
            "management_rule_seed_ko": "아래 alert level이 깨져야 continuation 관리. 안 깨지면 no risk reduction.",
            "take_profit_rule_seed_ko": "Target lower liquidity/136.63 zone.",
            "do_not_trade_or_exit_rule_seed_ko": "Key low를 깨지 못하고 위로 trend하면 thesis 폐기.",
            "quant_features_to_measure": "wave count proxy; trendline break; underside retest touch; low retest failure; stop hit time",
            "source_strength": "strong_frame_price_plus_ohlcv",
        },
        {
            "rule_seed_id": "iGJ_rule_06_eth_morning_fvg_underside_short",
            "context_id": "iGJALewp2dI_fd_06_trade6_eth_short_win",
            "rule_family": "morning_downtrend_fvg_short",
            "market_state_filter_ko": "다음날 morning session, ETH가 session 내내 하락 추세이고 trend underside/FVG가 겹칠 때 short.",
            "setup_trigger_ko": "Downtrend -> break area underside retest -> midpoint FVG short -> local low break expectation.",
            "entry_rule_seed_ko": "FVG midpoint 근처 short, SL over local high/underside retest.",
            "invalidation_rule_seed_ko": "Local high 위로 회복하면 close 또는 reduced win.",
            "management_rule_seed_ko": "2R+ MFE가 나오면 stop을 local high 위/inside로 옮기고, lower continuation 실패 시 manual close.",
            "take_profit_rule_seed_ko": "Initial target lower liquidity/FVG target, but runner보다 realized win 우선 가능.",
            "do_not_trade_or_exit_rule_seed_ko": "하루 종일 붙잡을 의도가 없으면 failed breakdown에서 이익 확정.",
            "quant_features_to_measure": "morning 9:30 anchor; downtrend slope; FVG midpoint; local low break; MFE retrace; manual exit trigger",
            "source_strength": "strong_frame_spoken_time_plus_ohlcv",
        },
    ]

    write_csv(OUT_SESSIONS, SESSION_FIELDS, sessions)
    write_csv(OUT_TRADES, TRADE_FIELDS, trades)
    write_csv(OUT_RULES, RULE_FIELDS, rules)

    lines = [
        "# Frame + Data Validated Context: iGJALewp2dI",
        "",
        "첫 남은 영상에 대해 로그인된 YouTube 프레임과 Binance 1m 데이터를 함께 사용해 문맥 큐를 만들었다.",
        "",
        "## Outputs",
        "",
        f"- session map: `{OUT_SESSIONS.relative_to(ROOT).as_posix()}`",
        f"- trade context queue: `{OUT_TRADES.relative_to(ROOT).as_posix()}`",
        f"- rule seed queue: `{OUT_RULES.relative_to(ROOT).as_posix()}`",
        f"- frame folder: `{FRAME_DIR.relative_to(ROOT).as_posix()}`",
        "",
        "## Counts",
        "",
        f"- sessions: {len(sessions)}",
        f"- trades/decision units: {len(trades)}",
        f"- rule seeds: {len(rules)}",
        "",
        "## Method",
        "",
        "- YouTube frame capture: setup/entry/management/recap only, not exhaustive scraping.",
        "- Visual anchors: symbol, timeframe, position box entry/SL/TP, time overlays, recap journal.",
        "- Data anchors: SOLUSDT 2025-03-26 1m; ETHUSDT 2025-03-27 1m.",
        "- Gold rule principle: rows are usable for rule extraction, but exact minute fields remain `medium` unless directly visible or strongly aligned.",
    ]
    OUT_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    OUT_SUMMARY.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(OUT_TRADES)
    print(OUT_RULES)
    print(OUT_SUMMARY)


if __name__ == "__main__":
    main()
