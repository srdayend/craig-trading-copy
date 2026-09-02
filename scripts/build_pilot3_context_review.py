from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path("data/source/craig_frames/browser_review")
OUT_CSV = Path("data/processed/gold_context_trades/pilot_3_context_review.csv")
OUT_MD = Path("outputs/pilot_3_context_review_summary.md")

VIDEOS = {
    "XlnvwMIRByQ": {
        "scope_order": 12,
        "upload_date": "2025-02-09",
        "title": "LIVE TRADING CRYPTO - Making $4,525 (SNIPER MODE)",
    },
    "nfRXDRJooyg": {
        "scope_order": 13,
        "upload_date": "2025-03-02",
        "title": "LIVE TRADING CRYPTO - How I Profit $4,504 in 5 Trades",
    },
    "iYpYWnkUyVI": {
        "scope_order": 14,
        "upload_date": "2025-03-23",
        "title": "Live Day Trading Making $7,521 (MY TRADING WAS INSANE)",
    },
}


def frame_paths(video_id: str, contains: list[str]) -> str:
    folder = ROOT / f"{video_id}_pilot3"
    paths: list[str] = []
    for needle in contains:
        matches = sorted(folder.glob(f"*_{needle}.png"))
        if not matches:
            matches = sorted(folder.glob(f"*{needle}*.png"))
        paths.extend(matches)
    unique = []
    seen = set()
    for path in paths:
        rel = path.as_posix()
        if rel not in seen:
            seen.add(rel)
            unique.append(rel)
    return "; ".join(unique)


def row(
    candidate_id: str,
    video_id: str,
    youtube_window: str,
    symbol: str,
    direction: str,
    decision_type: str,
    evidence_status: str,
    timeframe_evidence_ko: str,
    transcript_context_ko: str,
    chart_understanding_ko: str,
    execution_result_ko: str,
    rule_features_ko: str,
    frame_needles: list[str],
    source_anchors_ko: str,
    remaining_checks_ko: str,
) -> dict[str, str | int]:
    meta = VIDEOS[video_id]
    return {
        "candidate_id": candidate_id,
        "scope_order": meta["scope_order"],
        "video_id": video_id,
        "video_title": meta["title"],
        "upload_date": meta["upload_date"],
        "youtube_window": youtube_window,
        "symbol": symbol,
        "direction": direction,
        "decision_type": decision_type,
        "evidence_status": evidence_status,
        "timeframe_evidence_ko": timeframe_evidence_ko,
        "transcript_context_ko": transcript_context_ko,
        "chart_understanding_ko": chart_understanding_ko,
        "execution_result_ko": execution_result_ko,
        "rule_features_ko": rule_features_ko,
        "chart_frame_paths": frame_paths(video_id, frame_needles),
        "source_anchors_ko": source_anchors_ko,
        "remaining_checks_ko": remaining_checks_ko,
    }


ROWS = [
    row(
        "XlnvwMIRByQ_01",
        "XlnvwMIRByQ",
        "04:14-07:36",
        "SOL",
        "long",
        "planned_no_fill",
        "gold_actionable_setup_candidate",
        "자막 05:08에서 SOL 1분봉으로 내려간다고 명시. 직전에는 BTC/큰 시간대 bias를 확인.",
        "BTC는 전일 고점을 가져가고 bullish close였으며, 핵심 레벨 위에 머물면 당일 상승 모멘텀 가능성이 있다고 본다. SOL은 224 부근이 더 큰 지지라고 보면서, 뉴욕 오픈 직후 하락 추세에서 momentum shift/CHoCH가 나오고 FVG가 남으면 long으로 range 회복을 노린다. stop은 저점 아래이자 order block처럼 보이는 swing 아래에 두고, TP는 너무 일찍 먹지 않도록 위로 넓게 열어 두려 했다.",
        "06:25 프레임에서 큰 하락 뒤 green FVG/entry zone 위에 long box가 놓이고, 빨간 stop은 직전 swing low/order-block 저점 아래에 있다. 07:27 프레임에서는 가격이 해당 zone까지 되돌리지 않고 먼저 상승해 position box가 미체결 상태로 남는다.",
        "주문은 체결되지 않았고, 좋은 방향성 판단은 맞았지만 dip back into key zone이 오지 않아 아이디어를 제거했다.",
        "bullish daily bias + 1m CHoCH + bullish FVG midpoint + order-block/swing-low stop + no-chase when no pullback.",
        ["xln01_0622", "xln01_0724"],
        "04:14 BTC critical level; 05:08 SOL 1m; 06:14 CHoCH; 06:19 FVG; 06:38 stop under low/order block; 07:24 no dip into key zone.",
        "정확한 숫자 entry/SL/TP OCR은 미수행. 구조/조건/미체결 결과는 rule 학습에 충분.",
    ),
    row(
        "XlnvwMIRByQ_02",
        "XlnvwMIRByQ",
        "07:36-09:19",
        "SOL",
        "long",
        "planned_then_cancel",
        "gold_pass_rule_candidate",
        "동일 SOL 1분봉 구간.",
        "첫 롱 미체결 뒤 가격이 critical level을 상방 돌파하자 overside retest long을 고려한다. 다만 위치가 높아 chase가 될 수 있음을 인식했고, 그래서 entry를 조금 낮춰 trendline bounce까지 함께 받으려 했다. 이후 본인이 FVG를 잘못 봤고 실제 좋은 FVG retest는 이미 key level에서 발생해 가격이 출발했다는 것을 깨닫고 주문을 취소한다.",
        "08:17 프레임에서 수평 SR flip 레벨 위 retest와 하락 추세선/임시 지지선이 만나는 부근에 long box가 있다. 09:05 프레임에서는 실제 FVG가 이미 아래쪽 key level과 겹친 곳에서 채워지고 상승한 뒤라, 현재 box는 뒤늦은 진입으로 보인다.",
        "체결 전 취소. 핵심 결과는 '좋은 셋업을 놓쳤으면 다시 그럴듯한 위치를 억지로 따라가지 않음'이다.",
        "overside retest는 가능하지만 true FVG/level touch가 이미 지나갔으면 cancel; late recognition/no-chase filter.",
        ["xln02_0815", "xln02_0903"],
        "07:38 breaking above critical level; 07:55 overside retest; 08:00 lower entry for trendline bounce; 08:57 realized wrong wick/FVG; 09:18 cancel order.",
        "pass/cancel rule로는 충분. 실행 trade로 쓰지 않음.",
    ),
    row(
        "XlnvwMIRByQ_03",
        "XlnvwMIRByQ",
        "09:42-10:43",
        "SOL",
        "long",
        "executed_trade_loss",
        "gold_executed_trade_candidate",
        "자막 10:35에서 SOL 1분봉 long이라고 로그에 입력.",
        "bullish day thesis는 유지하되, 앞선 FVG entry가 오지 않았고 가격이 전체 상승 추세의 61.8% 부근 consolidation으로 내려온다고 판단한다. 해당 level에서 range 회복 continuation을 노리며 long을 세팅한다.",
        "10:05 프레임에서 Fib 0.618 부근과 작은 지지/되돌림 영역에 long entry가 있고, stop은 바로 아래 zone 밑에 있다. 10:28 프레임에서 가격이 stop 아래로 밀리며 position이 손절된 구조가 보인다.",
        "첫 실제 trade는 full loss. 자막상 -$646.",
        "bullish bias continuation attempt at 61.8 pullback; FVG가 아닌 discretionary/key-level long은 손절로 끝남.",
        ["xln03_1003", "xln03_1026"],
        "09:53 bullish sentiment; 09:58 61.8 consolidation; 10:03 entry off level; 10:26 pushed through stop; 10:35 SOL 1m long; 10:40 lost 646.",
        "금액과 결과는 자막/로그 확인. exact price OCR만 생략.",
    ),
    row(
        "XlnvwMIRByQ_04",
        "XlnvwMIRByQ",
        "10:56-13:15",
        "SOL",
        "long",
        "executed_trade_be",
        "gold_executed_trade_candidate",
        "자막상 SOL 1분봉. trade journal에는 두 번째 trade로 기록.",
        "SOL이 session 대부분 하락했고 기존 daily bias가 틀렸을 수 있음을 인정한다. 그래도 여러 reversal signal은 지나쳤고, 이제 처음으로 valid reversal signal과 bullish FVG가 나온다고 판단해 long을 시도한다. candle이 특정 high 위에서 close하면 risk를 BE로 줄이고, 위쪽 큰 key level까지 13R 가능성을 본다.",
        "11:12 프레임에서 하락 후 저점권에 bullish FVG/entry가 형성되고 long box가 위쪽으로 크게 열려 있다. 11:40 프레임은 가격이 반응한 뒤 entry/BE 부근으로 stop이 당겨진 상태를 보여준다.",
        "close above high 후 risk를 BE로 줄였고, 곧 wick이 entry를 다시 찍으며 BE stop. slippage/fees로 -$131.",
        "valid reversal after downtrend + bullish FVG + close above trigger high enables immediate BE; BE protection can miss later full move.",
        ["xln04_1110", "xln04_1137"],
        "10:56 SOL trending down; 11:03 only valid reversal signal; 11:08 bullish FVG; 11:14 close above level reduces risk; 11:37 BE; 11:54 stopped BE; 12:14 notes BE tradeoff; 13:12 -131.",
        "setup/management/result 완전. exact entry price OCR만 필요시 후속.",
    ),
    row(
        "XlnvwMIRByQ_05",
        "XlnvwMIRByQ",
        "12:47-16:31",
        "SOL",
        "short",
        "executed_trade_win",
        "gold_executed_trade_candidate",
        "SOL 1분 execution 위에 큰 시간대/당일 critical zone을 얹은 셋업.",
        "BE long 뒤 가격이 support turned resistance로 올라오면 숏도 보겠다고 바꾼다. 그는 이 레벨을 당일 가장 중요한 zone으로 보고, 실제로 failure가 나오자 short thesis로 전환한다. longer-term support/resistance flip, critical level failure, 아래 level break가 결합되면 1:18~1:20까지도 가능한 숏이라고 본다. 저점/채널 외곽과 $227 부근 consolidation/wick/low를 목표로 하되, 진행 중 trend retest가 나오면 수익을 확정한다.",
        "13:48 프레임에서 이전 지지/저항 flip zone 아래로 하방 CHOCH가 나오며 short box가 아래로 크게 열려 있다. 14:19 프레임은 risk가 zero/BE로 줄고 하락이 진행된 상태다. 16:10 프레임에서는 큰 하락 뒤 가격이 하락 trendline을 되찾으려는 retest에 들어와, 수동 익절 근거가 화면과 맞는다.",
        "risk를 0으로 줄인 뒤 trend를 따라 stop을 내렸고, 최종적으로 trend retest에서 수동 청산. 자막상 5.3R, +$2,551.",
        "failed retest of macro SR flip + CHOCH + break under trigger level; target lower wick/consolidation/channel edge; trail by current downtrend and exit when trend retest/reclaim probability rises.",
        ["xln05_1346", "xln05_1417", "xln05_1608"],
        "12:47 support turned resistance; 13:22 failure off critical level; 13:46 CHOCH; 13:52 drop below level; 14:17 risk zero; 14:48 target $227/10.68R; 15:25 trail over high; 16:08 trend retest; 16:28 5.3R/$2551.",
        "가장 좋은 gold 후보 중 하나. exact prices는 필요시 OCR/확대.",
    ),
    row(
        "XlnvwMIRByQ_06",
        "XlnvwMIRByQ",
        "17:54-19:32",
        "SOL",
        "short",
        "executed_trade_win_overnight",
        "gold_executed_trade_candidate",
        "동일 세션 후반 SOL 차트. 19:30 이후는 다음날 recap/결과.",
        "오랜 대기 후 SOL이 normal range로 되돌아오고 head-and-shoulders와 underside trend retest가 동시에 보인다. 두 개의 FVG가 존중되고 reject되는 것을 보고 마지막 short를 잡는다. 목표는 전체 추세의 61.8 부근/general support zone이며, overnight에는 큰 변동성을 감수하고 full loss 또는 full win을 받아들이기로 해 risk reduction을 거의 하지 않는다.",
        "18:11 프레임에서 상승 추세선 underside retest와 head-and-shoulders 우측 어깨 부근에 short box가 있고, stop은 직전 고점/어깨 위, TP는 아래 61.8/지지 영역으로 놓인다. 19:32 프레임에서는 가격이 야간에 크게 하락해 TP가 체결되고 로그에 +$2,751이 보인다.",
        "overnight TP 체결. 자막상 +$2,750~$2,751. 이날 총합은 약 +$4,500.",
        "range reclaim after big day + head-and-shoulders + underside trend retest + FVG rejection; if holding overnight, accept binary full-loss/full-win rather than micro-manage.",
        ["xln06_1809", "xln06_1930"],
        "17:58 SOL running into normal range; 18:03 head-and-shoulders; 18:07 underside trend retest; 18:14 FVGs respected/rejected; 18:25 target 61.8; 19:01 almost TP; 19:28 took profit $2750.",
        "recap와 프레임 일치. exact TP price만 미확인.",
    ),
    row(
        "nfRXDRJooyg_01",
        "nfRXDRJooyg",
        "03:43-13:08",
        "SOL",
        "long",
        "executed_trade_win",
        "gold_executed_trade_candidate",
        "ETH 설명에서는 5분봉 전략 예시가 나오고, 이 trade journal에는 1분봉 long으로 입력.",
        "프리세션에서 SOL은 큰 저항 실패 뒤 free fall 중이지만, reclaim 중인 핵심 영역에서는 temporary bounce long이 가능하다고 본다. ETH와 SOL을 비교하다가 SOL에서 하락 추세 이후 CHOCH와 FVG가 critical level에서 발생하자 long을 잡는다. 이 level은 massive run-up 전 마지막 touch point라 지지 재시험으로 중요하다고 본다.",
        "10:10 프레임에서 급락 뒤 61.8/수평 지지와 green FVG 부근에 long box가 놓여 있고, 위쪽 목표는 fair value gap/resistance 쪽으로 열려 있다. 11:19 프레임은 high close 후 entry zone으로 stop이 당겨진 상태를 보여주고, 12:23 프레임은 FVG/resistance 근처에서 이익 실현된 장면이다.",
        "risk를 entry로 줄인 뒤, 위쪽 FVG/resistance에서 manual TP. 자막/로그상 +$3,151, 약 6.4R.",
        "temporary long against broader weakness only at reclaimed critical level + CHOCH + FVG; reduce at close above high; take profit into multi-timeframe FVG/resistance when market runs without pullback.",
        ["nf01_1008", "nf01_1116", "nf01_1221"],
        "03:48 discounted zone; 04:33 temporary long if reclaim holds; 05:17 pair selection ETH/SOL; 10:05 SOL momentum; 10:08 FVG at CHOCH; 11:15 reduce risk; 12:18 TP; 13:06 +3151.",
        "gold 후보. exact price OCR 생략.",
    ),
    row(
        "nfRXDRJooyg_02",
        "nfRXDRJooyg",
        "14:28-16:08",
        "ETH",
        "short",
        "executed_trade_be_loss",
        "gold_executed_trade_candidate",
        "자막 06:33에서 ETH는 5분에서 보고 1분으로 내려간다고 말함. 실행 구간 timeframe은 프레임상 intraday 세밀 차트.",
        "아침에 예측했던 ETH underside trend retest와 FVG midpoint가 실제로 터치되고 반응한다. 이후 현재 move에서 bearish FVG가 생기자 short fishing order를 놓고, 회의 중에도 관리하려 한다. 핵심은 FVG+trend underside+critical support turned resistance가 겹치는 위치에서 failure를 노리는 숏이다.",
        "14:48 프레임에서 ETH가 상승 추세선 underside와 수평 저항을 재시험하고, 그 아래로 short position box가 크게 열린다. 16:08 프레임에서는 한차례 하락 반응 뒤 stop이 BE/entry 부근으로 당겨져 있고 가격이 다시 올라와 BE성 stop 처리된 상황이다.",
        "반응은 나왔지만 breakdown wall을 뚫지 못하고 BE stop. slippage/fees로 -$53.",
        "underside trend retest + bearish FVG + SR flip short; if initial reaction fails to break lower wall, BE stop protects but may exit before later move.",
        ["nf02_1446", "nf02_1605"],
        "14:31 ETH underside trend retest; 14:42 bearish FVG; 14:46 short entry order; 15:21 needs level breakdown; 15:33 stop at BE; 16:05 BE trade -53.",
        "구조/관리/결과 충분. exact target price는 frame 확대 필요.",
    ),
    row(
        "nfRXDRJooyg_03",
        "nfRXDRJooyg",
        "16:47-18:20",
        "ETH",
        "short",
        "missed_fill",
        "gold_actionable_setup_candidate",
        "ETH intraday chart. FOMC 전 12:45 근처라고 자막에서 시간 맥락 제공.",
        "원래 ETH short entry를 놓친 뒤에도 가격이 H&S 구조를 만들고 있다고 보고, 우측 어깨/underside retest/FVG zone으로 올라오면 숏을 재시도하려 한다. FOMC가 bearish하게 나오면 all-day runner가 될 수 있다고 보며, stop은 high 위, 목표는 아래 큰 range/low까지 열어둔다.",
        "17:12 프레임에서 shoulder-head-shoulder 구조와 대각 trend underside, entry 라벨, stop above high, 아래쪽 TP 라벨이 모두 보인다. 18:07 프레임에서는 가격이 order 근처까지 왔지만 fill이 안 된 뒤 크게 하락했고, position box는 실제로 유효한 하락 방향을 가리킨다.",
        "주문이 hair 차이로 미체결. 그는 좋은 setup/good execution이었지만 trade는 아니므로 넘어간다고 말한다.",
        "missed-fill gold setup: H&S + underside retest + FVG + FOMC bearish runner thesis; no market chase after near-fill.",
        ["nf03_1710", "nf03_1805"],
        "16:55 head-and-shoulders; 17:08 position into zone; 17:12 risk over high; 17:17 underside retest; 17:21 FOMC bearish runner; 18:03 should have filled but order missed by hair.",
        "셋업/entry/SL/TP/no-fill은 프레임으로 확인. 실행 trade로는 미사용.",
    ),
    row(
        "nfRXDRJooyg_04",
        "nfRXDRJooyg",
        "18:24-19:57",
        "SOL",
        "long",
        "executed_trade_loss",
        "gold_executed_trade_candidate",
        "SOL intraday. FOMC volatility 중.",
        "시장 전체가 bleed off하던 중 SOL이 이전 break-of-structure low 아래로 실패하고, high를 밀어올리며 CHOCH와 green displacement/FVG를 남겼다고 본다. 이미 clean level sweep 후 반응했다고 보고, 넓은 stop으로 bullish continuation/FOMC upside volatility를 노린다.",
        "18:42 프레임에서 강한 하락 후 저점권에서 small long box가 FVG/entry zone에 있고, stop은 마지막 low 아래, TP는 위쪽 회복 range로 잡혀 있다. 19:29 프레임은 이 long이 실패한 뒤 같은 영역 아래쪽으로 다시 움직였음을 보여준다.",
        "long은 -$619 손절. 자막상 이날 +$3,151 이익에서 손실이 먹혀 들어간다고 설명.",
        "failed breakdown/sweep + CHOCH + bullish FVG long in high-volatility news environment; wide stop reduces R, and discretionary FOMC long failed.",
        ["nf04_1840", "nf04_1927"],
        "18:24 SOL after bleed; 18:30 failed to go below BOS; 18:33 CHOCH; 18:40 discretionary entry; 18:44 stop below low; 19:24 took loss; 19:54 -619.",
        "실행/결과 충분. 다만 recap에서는 이 trade를 제목의 5 trades와 어떻게 세는지 애매하므로 sequence는 후보 단계.",
    ),
    row(
        "nfRXDRJooyg_05",
        "nfRXDRJooyg",
        "19:27-20:15",
        "SOL",
        "long",
        "manual_flat_or_cancelled_trade",
        "context_incomplete_not_gold",
        "SOL intraday. 같은 FOMC 변동성 직후.",
        "직전 long 손절 후 clean break/push under와 massive displacement candle/CHOCH가 보이면 같은 영역/order block retest에서 다시 upside를 시도한다. 하지만 곧 price action이 지지를 받을 모습이 아니고 더 떨어질 수 있다고 판단해 flat으로 제거한다.",
        "19:29 프레임에 같은 하단 zone 부근의 long/entry 구조는 보이나, 이 trade의 독립적인 fill/flat 로그와 최종 PnL이 recap에서 선명하게 매칭되지 않는다.",
        "자막상 'took this trade off for flat'. 하지만 journal/recap 금액 매칭이 불명확하다.",
        "important but not gold yet: immediate reattempt after loss, order-block retest idea, and discretionary flat exit when support fails visually.",
        ["nf04_1927"],
        "19:27 clean break/push underneath; 19:36 FVG/order block; 20:15 took trade off flat; 20:24 find better setup.",
        "보류. 별도 frame/ledger가 없으면 rule evidence로 승격하지 않음.",
    ),
    row(
        "nfRXDRJooyg_06",
        "nfRXDRJooyg",
        "20:35-22:42",
        "ETH",
        "long",
        "executed_trade_profit_reduced",
        "gold_executed_trade_candidate",
        "ETH intraday. FOMC 이후 변동성 높음.",
        "ETH는 resistance를 FOMC candle이 돌파한 뒤 trend 위에서 consolidation하고 lower FVG 쪽에서 support를 잡는다고 본다. overside retest + FVG support long으로, 변동성이 높아 빠른 risk reduction을 전제로 들어간다. 목표는 equal highs 부근 1:8R이나, 실패/급변 때문에 stop을 이익권으로 당긴다.",
        "20:40 프레임에서 상승 impulse 후 green FVG/overside retest 부근에 long box가 있고, stop은 구조 아래, TP는 위 equal highs 쪽이다. 21:23 프레임에서는 위로 반응한 뒤 risk가 BE로 줄어든 모습이고, 22:02 프레임에서는 가격이 되돌아와 작게 이익권에서 종료된 흐름이 보인다.",
        "full TP 전 되돌림으로 이익권 stop/manual 결과. 자막상 +$443.",
        "FOMC breakout/reclaim + overside retest + FVG support long; high volatility requires fast BE/profit stop; equal-high TP can be missed by sharp reversal.",
        ["nf06_2037", "nf06_2121", "nf06_2200"],
        "20:35 ETH FVG setup; 21:06 entry on overside retest/FVG; 21:21 reduce risk to zero; 21:29 target equal highs 1:8; 22:27 +443 after fees.",
        "gold 후보. exact management stop level은 frame 확대 시 더 선명.",
    ),
    row(
        "nfRXDRJooyg_07",
        "nfRXDRJooyg",
        "23:20-23:37",
        "unknown",
        "short",
        "recap_only_be_trade",
        "context_incomplete_not_gold",
        "다음날/야간 recap 구간. timeframe 명시 없음.",
        "저녁 이후 trendline break에 진입했고, low 아래 break가 나오자 risk를 0으로 줄였다. 곧 가격이 되돌아와 BE stop이 나갔다.",
        "이번 파일럿 프레임 세트에서는 이 trade의 live setup/position box를 별도로 충분히 캡처하지 않았다. 자막만으로 trendline break 외의 zone/FVG/SL/TP가 부족하다.",
        "BE성 손실 -$54.",
        "trendline-break entry + immediate BE after low break is useful, but not complete enough without setup geometry.",
        [],
        "23:20 coming home from dinner; 23:24 break of trendline; 23:30 reduced risk to zero; 23:33 stopped for zero; 23:35 -54.",
        "보류. 프로젝트 원칙상 recap-only/geometry 부족은 gold에서 제외.",
    ),
    row(
        "nfRXDRJooyg_08",
        "nfRXDRJooyg",
        "23:42-24:31",
        "ETH",
        "long",
        "executed_trade_recap_detailed",
        "gold_executed_trade_candidate",
        "다음날 morning trade recap. chart frame에서 ETH intraday 구조 확인.",
        "다음날 아침 ETH의 overall uptrend가 broken down된 뒤, response area와 충분한 displacement가 나오고 high를 다시 시도한 구간을 critical support로 본다. 가격이 해당 support/FVG midpoint로 내려오며 entry를 주고, high break 전에는 risk를 줄이지 않았으며, 최종적으로 3.73R 부근에서 take profit한다.",
        "23:47 프레임은 전체 상승 추세가 무너졌다가 회복되는 큰 구조를 보여주고, 24:22 프레임은 하락 후 FVG midpoint/critical support에서 long box가 채워지고 위쪽 target zone까지 진행된 recap 장면이다.",
        "TP 청산. 자막상 +$1,663, recap later +$1,636로도 언급되어 약간의 ASR/수수료 차이가 있음. 총합 +$4,504와는 +$1,636을 쓰면 일치.",
        "recap-derived but complete: broken uptrend response area + displacement + FVG midpoint support + no risk reduction until high break + TP at 3.7R.",
        ["nf08_2345", "nf08_2420"],
        "23:45 overall uptrend broken; 23:55 displacement; 24:00 critical support; 24:06 entry; 24:12 no reduce because high not broken; 24:20 TP 3.73R; 24:25 +1663; 27:04 +1636 total-day math.",
        "recap 기반이라 live thought 변화는 제한. 그래도 setup/entry/SL/TP/result는 충분해 후보로 유지.",
    ),
    row(
        "iYpYWnkUyVI_01",
        "iYpYWnkUyVI",
        "02:15-07:11",
        "SOL",
        "long",
        "planned_then_cancel",
        "gold_actionable_setup_candidate",
        "자막 03:53에서 15분/5분으로 current trend를 보고, 이후 1분 실행 구간으로 내려가는 흐름.",
        "뉴스는 크지 않지만 Nvidia earnings가 전통시장/crypto에 영향 가능. 큰 흐름은 많이 하락했으므로 rebound 가능성도 있지만, daily candle 분석은 bearish다. 그는 daily bias에 과하게 기대지 않고 패턴대로 하겠다고 한다. 초기에는 downtrend에서 higher high/CHoCH와 FVG가 형성되면 green strip으로 pullback해 long reversal을 잡아 몇 시간 ride하려 했다. 하지만 pullback이 즉시 오지 않고 위 key levels에서 반응 가능성이 커지자 order를 지우고 short setup을 찾는다.",
        "05:04 프레임에서 하락 추세선 break/green FVG 구간에 long order box가 있고, stop은 저점 아래, target은 위쪽 큰 회복 구간이다. 07:09 프레임은 차트가 아니라 face-cam이라 chart cancel 화면은 직접 확인 못 했지만, 자막상 cancel 이유는 명확하다.",
        "체결 전 취소. daily bearish와 위 key-level 반응 가능성 때문에 short를 새로 찾기로 함.",
        "bearish daily bias can override early reversal long if pullback timing is poor and upper key levels react; actionable no-fill/cancel setup.",
        ["iyp01_0502"],
        "02:15 no news until 2:45, Nvidia earnings; 02:27 market down/rebound possible; 03:08 previous day low closed bearish; 04:44 5m/trendline; 05:02 order set; 05:14 CHOCH; 05:37 FVG; 06:49 waiting fill; 07:07 clear order/look short.",
        "cancel 순간 chart frame은 face-cam으로 놓쳤지만, initial setup box는 확인. gold setup으로 쓰되 cancel frame은 보강 가능.",
    ),
    row(
        "iYpYWnkUyVI_02",
        "iYpYWnkUyVI",
        "07:13-13:24",
        "SOL",
        "short",
        "executed_trade_win",
        "gold_executed_trade_candidate",
        "SOL intraday. 초기 15/5분 bias 위에 세부 execution.",
        "초기 long을 취소한 뒤 SOL이 상승 후 momentum을 잃고 H&S를 만든다고 본다. 저항으로 들어가는 FVG가 있고 완벽한 CHOCH는 아니지만 momentum shift가 시작되며 약한 영역을 깰 가능성이 높다고 판단해 short exposure를 잡는다. low/level을 깨면 risk를 줄이고, 1:4 달성 후 trend high를 따라 stop을 이익권으로 내린다. 아래 low 재시도에서는 temporary support 가능성을 인식하면서도, low break가 big candle로 나올 경우 momentum이 죽을 때 exit할 계획을 세운다.",
        "07:26 프레임에서 H&S/저항 박스/FVG에 short box가 있고 stop은 right shoulder high 위, TP는 아래 range low까지 열린다. 08:47 프레임은 level 아래 clean break가 나온 상태, 10:44 프레임은 1:4 이후 stop을 lower high 위로 trailing한 상태, 13:02 프레임은 큰 하락 candle 뒤 수익 실현 장면이다.",
        "7.48R로 청산. 자막/로그상 +$3,735.",
        "bearish daily + H&S at resistance + FVG into resistance + momentum-shift short even without perfect CHOCH; let breathe, trail after 1:4, exit after big low-break candle when momentum starts to die.",
        ["iyp02_0724", "iyp02_0845", "iyp02_1042", "iyp02_1300"],
        "07:13 SOL opportunity; 07:20 H&S; 07:22 FVG into resistance; 07:25 not perfect CHOCH; 08:43 clean break; 10:40 hit 1:4; 12:00 support/low-break plan; 12:58 big candle; 13:06 exit; 13:24 +3735.",
        "강한 gold 후보. exact stop/TP 숫자만 생략.",
    ),
    row(
        "iYpYWnkUyVI_03",
        "iYpYWnkUyVI",
        "13:54-15:28",
        "SOL",
        "long",
        "executed_trade_be",
        "gold_executed_trade_candidate",
        "SOL intraday. reversal attempt.",
        "큰 하락 후 low break가 실패하고 fair value gap이 남는다. 완전한 CHOCH라기보다 change in state of delivery/impulse candle이지만, 많이 직선 하락했기 때문에 FVG impulse bounce를 노린다. planned entry보다 현재가가 더 낮아도 trade가 여전히 valid하다고 보고 market/현재가로 더 낮게 진입해 risk 효율을 높인다.",
        "14:05 프레임에서 직선 하락 후 low 근처 bullish FVG에 long box가 있고 stop은 구조 저점 아래, TP는 위쪽 되돌림 구간이다. 15:27 프레임에서는 초기 반등 후 stop이 BE/약간 이익권으로 당겨졌고 되돌림으로 종료된 모습이다.",
        "BE 또는 소액 이익. 자막은 'break even trade, little bit of profit'으로 정리.",
        "straight-line selloff into low response + CISD/impulse FVG long; current market entry allowed if still valid; reduce to BE/profit after close over high.",
        ["iyp03_1402", "iyp03_1525"],
        "13:54 failed to break low; 13:57 FVG after big push up; 14:01 not technically CHOCH/CISD; 14:51 reduce in profit at FVG; 15:21 stopped BE/little profit.",
        "result is BE/small profit, exact PnL not stated. Rule evidence로는 충분.",
    ),
    row(
        "iYpYWnkUyVI_04",
        "iYpYWnkUyVI",
        "16:14-17:23",
        "SOL",
        "long",
        "executed_trade_loss",
        "gold_executed_trade_candidate",
        "SOL intraday.",
        "점심 후 다시 전체 trend flip을 노린다. CHOCH와 FVG가 동시에 보이자 빠르게 position을 넣는다. 그는 특히 이전 level들이 trend에 점점 가까이 접촉하다가 확실한 displacement candle로 추세선을 뚫고, FVG midpoint가 overside trend contact와 겹치는 구조를 좋아한다고 설명한다.",
        "16:24 프레임에서 주문 입력창과 함께 CHOCH/FVG long 계획이 보이고, entry/TP/SL 숫자가 일부 보인다. 17:17 프레임에서는 price가 FVG/entry 아래로 밀려 stop loss가 난 상태다.",
        "full loss. 자막상 -$618. Craig는 setup 자신감 5/5였고, 손실을 좋은 setup을 잡기 위한 opportunity cost로 본다.",
        "high-confidence CHOCH + FVG + overside trend retest can still fail; loss is acceptable if setup quality is high and R is contained.",
        ["iyp04_1622", "iyp04_1714"],
        "16:14 CHOCH/FVG; 16:20 target midpoint; 16:31 repeated trend contacts; 16:39 displacement candle; 16:48 overside trend contact; 17:14 loss; 17:22 -618.",
        "entry/TP/SL 입력창까지 보이는 좋은 후보. exact OCR은 필요 시 가능.",
    ),
    row(
        "iYpYWnkUyVI_05",
        "iYpYWnkUyVI",
        "17:47-20:16",
        "SOL",
        "long",
        "executed_trade_be_after_reentry",
        "gold_executed_trade_candidate",
        "SOL intraday. trend-flip 재시도.",
        "직전 손절 뒤에도 전체 trend flip을 한 번 더 노린다. low break 실패와 FVG into that zone이 다시 생겼고, 처음에는 주문가를 잘못 입력해 의도치 않은 작은 gain이 났지만, 곧 proper position을 다시 잡는다. failed new low + FVG response + high break를 확인하면 risk를 BE로 줄이려 한다. 이후 larger trend의 heavy resistance/underside와 BTC 급락을 보며 빠르게 반응한다.",
        "18:17 프레임에서 저점 sweep/failed breakdown 뒤 FVG zone에 long box가 다시 놓여 있고, stop은 저점 아래다. 19:18 프레임에서는 가격이 위로 진행되어 resistance zone에 접근하고, 더 큰 downtrend underside가 위에 남아 있다.",
        "recap상 BE stop. 중간에 잘못 입력한 작은 gain은 모델 evidence에서 제외하고, proper reentry long만 기록.",
        "after high-confidence loss, one more stab only when failed low break + new FVG appears; reduce after high break; BTC relative weakness can force fast defensive exit.",
        ["iyp05_1815", "iyp05_1916"],
        "17:47 one more stab; 17:55 failed to break low; 17:56 FVG into zone; 18:01 accidental order/gain; 18:11 proper position; 18:30 desired move; 18:52 reduce risk; 19:42 heavy resistance; 20:03 BTC dumping; recap 24:48-25:02 BE.",
        "정확한 종료 순간 프레임은 덜 선명하지만 recap과 management가 충분히 맞음.",
    ),
    row(
        "iYpYWnkUyVI_06",
        "iYpYWnkUyVI",
        "20:27-22:51",
        "ATOM",
        "short",
        "executed_trade_win",
        "gold_executed_trade_candidate",
        "ATOM intraday. Craig가 잘 안 보던 pair지만 weakness가 뚜렷하다고 판단.",
        "SOL timing이 조금 틀린 뒤, ATOM에서 훨씬 좋은 short를 본다. 그는 weakness into afternoon, 5-wave completion, sell signal, volume drying, change in state of delivery 뒤 생긴 FVG를 근거로 한다. position은 tight하며, low로 되돌아가면 massive RR가 가능하다. 반응 후 stop을 BE로 줄이고, close under level 후 profit stop을 내려 잠그며 gym/dinner 중 관리한다.",
        "20:32 프레임에서 ATOM은 강한 상승 5파 뒤 빨간 sell/FVG 구간에 tight short box가 있고, stop은 직전 high 위, TP는 아래 range low 쪽이다. 21:48 프레임은 하락이 진행되어 stop이 최근 high 위로 내려와 수익이 잠긴 상태, 22:51 프레임은 short가 종료되고 로그에 large green PnL이 기록된 장면이다.",
        "거의 9R 청산. 자막상 8.9R, +$4,353. 일중 총합 약 +$7,500.",
        "non-core pair allowed when structure is cleaner: 5-wave into weakness + sell signal + volume dry-up + CISD/FVG + tight stop; trail over lower highs and lock near 10R.",
        ["iyp06_2030", "iyp06_2145", "iyp06_2248"],
        "20:27 ATOM opportunity; 20:30 sell signal; 20:32 volume drying; 20:35 FVG after CISD; 21:15 stop BE; 21:24 close under level; 21:45 stop over high; 22:17 lock close to 10R; 22:48 closed; 23:12 +4353; 25:13 recap 5-wave.",
        "강한 gold 후보. exact numerical levels optional.",
    ),
]


def write_csv() -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(ROWS[0].keys()))
        writer.writeheader()
        writer.writerows(ROWS)


def write_summary() -> None:
    by_video: dict[str, Counter] = defaultdict(Counter)
    for item in ROWS:
        by_video[item["video_id"]][item["evidence_status"]] += 1

    lines: list[str] = [
        "# Pilot 3 Context Review Summary",
        "",
        "## Scope",
        "",
        "Oldest-first continuation after `bDgZhBFm1mU`:",
        "",
    ]
    for video_id, meta in VIDEOS.items():
        lines.append(
            f"- {meta['scope_order']}. `{video_id}` ({meta['upload_date']}): {meta['title']}"
        )
    lines += [
        "",
        "## Method",
        "",
        "- Transcript-first: strong anchors such as setup, fill, reduce risk, stop, take profit, and recap were read before any frame capture.",
        "- Frame review: 43 browser-captured YouTube player crops were saved only around setup/entry/management/recap moments.",
        "- Visual interpretation used chart geometry visible in the crops: position box direction, FVG rectangles, CHOCH/level references, trendline underside/overside retests, H&S/wave/fib context, and journal/result panels.",
        "- Rows are still candidate evidence. They should be promoted into `gold_trade_contexts.csv` only after any desired exact price OCR/recap sequence checks are done.",
        "",
        "## Counts",
        "",
    ]
    total = Counter(item["evidence_status"] for item in ROWS)
    for video_id, counter in by_video.items():
        status_text = ", ".join(f"{k}: {v}" for k, v in sorted(counter.items()))
        lines.append(f"- `{video_id}`: {sum(counter.values())} rows ({status_text})")
    lines.append(f"- Total: {len(ROWS)} rows ({', '.join(f'{k}: {v}' for k, v in sorted(total.items()))})")
    lines += [
        "",
        "## Notable Pilot Findings",
        "",
        "- `XlnvwMIRByQ`: strategy is still bias-aware but increasingly flexible; bullish daily bias was abandoned when SOL failed and the critical support-turned-resistance short appeared.",
        "- `nfRXDRJooyg`: the title says 5 trades, but the transcript math implies more decision units. The dataset records decision units, not title count.",
        "- `iYpYWnkUyVI`: unfilled/canceled setups are important because Craig explicitly cancels/reorients from early long thesis to bearish shorts, then later permits reversal attempts only after failed low breaks/FVGs.",
        "- The strongest rule examples in this pilot are `XlnvwMIRByQ_05`, `nfRXDRJooyg_01`, `iYpYWnkUyVI_02`, and `iYpYWnkUyVI_06`.",
        "",
        "## Outputs",
        "",
        f"- CSV: `{OUT_CSV.as_posix()}`",
        "- Frame folders:",
        "  - `data/source/craig_frames/browser_review/XlnvwMIRByQ_pilot3/`",
        "  - `data/source/craig_frames/browser_review/nfRXDRJooyg_pilot3/`",
        "  - `data/source/craig_frames/browser_review/iYpYWnkUyVI_pilot3/`",
    ]
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    write_csv()
    write_summary()
    print(OUT_CSV)
    print(OUT_MD)


if __name__ == "__main__":
    main()
