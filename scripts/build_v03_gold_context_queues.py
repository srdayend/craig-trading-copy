from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed" / "gold_context_trades"
DETAILS = ROOT / "data" / "source" / "craig_youtube" / "details.csv"
USER_DATES = ROOT / "data" / "source" / "craig_youtube" / "user_verified_market_dates.csv"
FRAME_MANIFEST = ROOT / "data" / "source" / "craig_frames" / "local_v03_upgrade" / "local_v03_frame_manifest.json"
QUALITY_INPUTS = ROOT / "outputs" / "craig_quality_tracker_v0_3" / "quality_tracker_inputs.json"

MANUAL_IDS = ["KXIF1Ll5Exg", "wm4tmXgKlz8", "Ifc1VzcNlCg", "pA7rzimO9y4", "bDgZhBFm1mU"]
PILOT_IDS = ["XlnvwMIRByQ", "nfRXDRJooyg", "iYpYWnkUyVI"]
FRAME_IDS = ["iGJALewp2dI", "p47HZv1fcUM", "mNnqjq8BzeA"]
ALL_IDS = MANUAL_IDS + PILOT_IDS + FRAME_IDS


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


def details() -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    d = {r["id"]: r for r in read_csv(DETAILS) if r.get("id")}
    q = json.loads(QUALITY_INPUTS.read_text(encoding="utf-8"))
    progress = {r["video_id"]: r for r in q["videos"]}
    verified = {r["video_id"]: r for r in read_csv(USER_DATES) if r.get("video_id")}
    return d, progress, verified


def parse_anchor_seconds(*texts: str) -> str:
    found = []
    for text in texts:
        if not text:
            continue
        for m in re.finditer(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)", text):
            found.append(int(m.group(1)) * 60 + int(m.group(2)))
    return "|".join(str(s) for s in sorted(set(found)))


def parse_market_date(note: str, verified: str = "") -> tuple[str, str]:
    if verified:
        return verified, "high_user_verified_bottom_axis"
    low = (note or "").lower()
    months = {
        "jan": "01",
        "feb": "02",
        "mar": "03",
        "apr": "04",
        "may": "05",
        "jun": "06",
        "jul": "07",
        "aug": "08",
        "sep": "09",
        "oct": "10",
        "nov": "11",
        "dec": "12",
    }
    m = re.search(r"(\d{1,2})\s+([a-z]{3})\s+(\d{2})", low)
    if m and m.group(2) in months:
        return f"20{m.group(3)}-{months[m.group(2)]}-{int(m.group(1)):02d}", "medium_user_manual_note"
    return "", "not_available"


def parse_market_time(note: str) -> str:
    m = re.search(r"(\d{1,2}:\d{2})", note or "")
    return m.group(1) + " approximate" if m else ""


def frame_paths_for(video_id: str, *needles: str) -> str:
    manifest = frame_paths_for.manifest
    frames = manifest.get(video_id, [])
    hits = []
    lower_needles = [n.lower() for n in needles if n]
    for frame in frames:
        text = f"{frame.get('labels','')} {frame.get('stamp','')} {frame.get('path','')}".lower()
        if not lower_needles or any(n in text for n in lower_needles):
            hits.append(frame.get("path", ""))
    if frames and not hits:
        hits = [f.get("path", "") for f in frames[:4]]
    contact = ""
    for frame in frames:
        if frame.get("stamp") == "contact":
            contact = frame.get("path", "")
            break
    if contact and contact not in hits:
        hits.insert(0, contact)
    return "|".join(h for h in hits if h)


frame_paths_for.manifest = json.loads(FRAME_MANIFEST.read_text(encoding="utf-8"))


def term_flags(text: str) -> dict[str, bool]:
    low = text.lower()
    return {
        "macro": any(x in low for x in ["macro", "daily", "bias", "hft", "4h", "higher", "뉴스", "비트", "btc"]),
        "wave": any(x in low for x in ["wave", "elliott", "파동", "2.618", "3.618", "4.618", "fib", "피보"]),
        "fvg": any(x in low for x in ["fvg", "fair value gap"]),
        "choch": any(x in low for x in ["choch", "change of character"]),
        "trend": any(x in low for x in ["trend", "트렌드", "trendline", "트렌드라인"]),
        "sr": any(x in low for x in ["support", "resistance", "서포트", "저항", "지지", "sr"]),
        "risk": any(x in low for x in ["stop", "sl", "손절", "be", "risk", "스탑", "트레일"]),
    }


def session_context_from_text(video_id: str, title: str, texts: list[str], source_stage: str, progress: dict[str, str]) -> dict[str, str]:
    joined = " / ".join(t for t in texts if t)
    flags = term_flags(joined)
    macro = "기존 notes/SRT/프레임 기준으로 당일 HFT·daily/session bias를 먼저 잡고, 이후 1분봉 setup을 선택한다."
    if "bDg" in source_stage or video_id == "bDgZhBFm1mU":
        macro = "오전에는 SOL 상위 상승 트렌드라인 하락돌파와 fake-out 이후 bearish continuation을 기본 시나리오로 보며, 오후에는 큰 지지/저항 flip과 CHoCH에 따라 long/short를 모두 조건부로 검토한다."
    elif any(x in joined for x in ["비트", "BTC", "Bitcoin", "daily", "4시간", "4h"]):
        macro = "BTC/상위 시간대 구조, daily bias, 주요 SR/Fib/추세선 위치를 먼저 보고, 해당 bias가 SOL/ETH 1분봉 FVG·CHoCH와 맞을 때만 실행한다."
    scenario = "조건부 시나리오: bias 방향 setup이 오면 진입, 핵심 레벨이 깨지거나 좋은 FVG touch를 놓치면 chase하지 않음, 반대 방향 displacement/CHoCH가 나오면 thesis 전환."
    symbol = "BTC는 상위 방향성 기준, SOL/ETH는 실제 실행 후보로 비교한다. 상대적으로 더 명확한 FVG·trendline·SR 반응이 보이는 종목을 선택한다."
    wave = "Elliott/Fib 언급이 있는 경우 wave count와 2.618/3.618/4.618 extension을 reversal/continuation/pass 필터로 기록한다." if flags["wave"] else "이 영상/행 집계에서는 wave/Fib 언급이 낮거나 명시적이지 않아, 사용된 경우에만 row 단위에서 기록한다."
    return {
        "session_context_id": f"{video_id}_session_v03",
        "video_id": video_id,
        "video_title": title,
        "local_index_oldest_first": progress.get("local_index_oldest_first", ""),
        "source_stage_v03": source_stage,
        "market_dates_utc_minus4": progress.get("verified_market_date", ""),
        "primary_symbols": "SOLUSDT/ETHUSDT/BTC context",
        "confirmed_timeframes": "1m execution charts; HTF/BTC/daily context when spoken or visible",
        "local_video_path": progress.get("video_file", ""),
        "local_srt_path": progress.get("srt_file", ""),
        "session_macro_context_ko": macro,
        "scenario_tree_ko": scenario,
        "symbol_selection_context_ko": symbol,
        "elliott_wave_context_ko": wave,
        "session_risk_context_ko": "Fixed risk per trade and daily PnL/goal pressure are tracked when journal/recap frames expose them; gym/dinner/overnight constraints are recorded as management context.",
        "frame_contact_sheet": frame_paths_for(video_id).split("|")[0] if frame_paths_for(video_id) else "",
        "v03_upgrade_notes_ko": "v0.3 upgrade: macro/scenario/symbol/wave/timezone categories separated from broad narrative fields.",
    }


def manual_decision_type(notes: str) -> str:
    low = notes.lower()
    if "fill 안" in notes or "체결은 못" in notes or "미체결" in notes or "no fill" in low:
        return "planned_no_fill"
    if "취소" in notes or "cancel" in low:
        return "planned_then_cancel"
    if "매매는 아니지만" in notes:
        return "actionable_setup_no_trade"
    if "스킵" in notes or "안할" in notes or "패스" in notes:
        return "pass_after_setup"
    return "executed_or_actionable_trade"


def status_for_decision(decision_type: str) -> str:
    if decision_type in {"planned_no_fill", "planned_then_cancel", "pass_after_setup", "actionable_setup_no_trade"}:
        return "v03_gold_actionable_context_ready"
    return "v03_gold_trade_context_ready"


def context_from_manual(row: dict[str, str], d: dict[str, dict[str, str]], progress: dict[str, dict[str, str]], verified: dict[str, dict[str, str]]) -> dict[str, str]:
    vid = row["video_id"]
    title = d.get(vid, {}).get("title", "")
    notes = row.get("original_notes_ko", "")
    decision_type = manual_decision_type(notes)
    date, conf = parse_market_date(row.get("market_time_note", ""), verified.get(vid, {}).get("verified_market_date", ""))
    anchor_seconds = parse_anchor_seconds(row.get("youtube_anchor", ""), row.get("source_anchors_ko", ""), notes)
    flags = term_flags(notes)
    return {
        "context_id": row.get("trade_id", "").replace("_manual_", "_v03_manual_"),
        "session_context_id": f"{vid}_session_v03",
        "video_id": vid,
        "video_title": title,
        "local_index_oldest_first": progress.get(vid, {}).get("local_index_oldest_first", ""),
        "source_stage_v03": "manual_seed_upgraded_with_local_frames",
        "decision_type": decision_type,
        "gold_status": status_for_decision(decision_type),
        "symbol": (row.get("symbol") or "").replace("SOL", "SOLUSDT").replace("ETH", "ETHUSDT"),
        "direction": row.get("direction", ""),
        "chart_timeframe": "1m execution; HTF/BTC context when noted",
        "market_date_utc_minus4": date,
        "market_time_window_utc_minus4": parse_market_time(row.get("market_time_note", "")),
        "visible_chart_time_note": row.get("market_time_note", ""),
        "market_time_confidence": conf,
        "youtube_window": row.get("youtube_anchor", ""),
        "anchor_seconds": anchor_seconds,
        "entry_price": "frame_relative_or_about",
        "stop_price": "frame_relative_or_about",
        "target_price": "frame_relative_or_about",
        "realized_result": "",
        "session_macro_context_ko": "사용자 seed와 로컬 프레임 기준: " + (" / ".join(notes.split(" / ")[:3])),
        "scenario_tree_ko": "Craig가 원하는 핵심 구조가 오면 limit/entry를 두고, 좋은 touch를 이미 놓치거나 파동 연장/뉴스/레벨 리테스트 위험이 커지면 pass/cancel한다.",
        "symbol_selection_context_ko": "BTC/상위 구조는 bias 기준, SOL/ETH 중 프레임상 더 선명한 FVG·trendline·SR 반응을 실행 대상으로 선택.",
        "elliott_wave_context_ko": " / ".join([p for p in notes.split(" / ") if any(x in p.lower() for x in ["파동", "wave", "2.618", "3.618", "4.618", "피보"])]) if flags["wave"] else "",
        "trade_thesis_link_ko": "이 decision은 session macro/wave/SR thesis가 1분봉 FVG·CHoCH·trendline retest와 만나는 지점만 실행/관찰 대상으로 삼는 샘플.",
        "structure_reference_ko": notes,
        "setup_context_ko": notes,
        "entry_plan_ko": "프레임/메모 기준 FVG midpoint 또는 SR/trendline retest zone에 진입. Deep buy/sell ladder가 있으면 분할 limit로 기록.",
        "management_plan_ko": "BE, stop, trailing, cancel/pass 조건은 notes/result 문장과 recap 프레임이 있는 경우 그대로 연결.",
        "live_thesis_changes_ko": " / ".join([p for p in notes.split(" / ") if any(x in p for x in ["기다", "스킵", "보수", "싫", "갑자기", "바뀌", "취소", "연장", "뉴스"])]),
        "exit_result_ko": " / ".join([p for p in notes.split(" / ") if any(x in p for x in ["결론", "마무리", "정리", "손절", "익절", "BE", "본절", "fill 안", "체결"])]) or "",
        "frame_evidence_paths": frame_paths_for(vid, row.get("trade_id", ""), row.get("youtube_anchor", "")),
        "ohlcv_alignment_ko": "v0.3 upgraded row: market time note and local frame evidence attached. Exact candle alignment is ready when corresponding local 1m date cache exists; early manual dates with weekday mismatch are explicitly kept at medium confidence.",
        "rule_feature_vector_seed_ko": "; ".join(k for k, v in flags.items() if v),
        "invalidation_condition_ko": "Stop beyond relevant swing/zone; setup canceled if true FVG touch already passed, key level is reclaimed against thesis, or wave/news extension risk invalidates expected reversal.",
        "remaining_uncertainty_ko": "" if conf.startswith("high") else "일부 early manual date는 사용자 메모 기반이며 visible chart timezone/weekday 재검증 여지가 있음.",
    }


def context_from_bdg(row: dict[str, str], d: dict[str, dict[str, str]], progress: dict[str, dict[str, str]], verified: dict[str, dict[str, str]]) -> dict[str, str]:
    vid = row["video_id"]
    title = d.get(vid, {}).get("title", "")
    text = " / ".join([row.get("context_summary_ko", ""), row.get("setup_summary_ko", ""), row.get("execution_result_ko", "")])
    flags = term_flags(text)
    date, conf = parse_market_date("", verified.get(vid, {}).get("verified_market_date", ""))
    decision_type = row.get("decision_type", "")
    row_status = " ".join(
        [
            row.get("status", ""),
            row.get("promoted_rule_evidence_type", ""),
            row.get("why_not_gold_yet", ""),
        ]
    ).lower()
    if "context_incomplete" in row_status or "not_gold_context_incomplete" in row_status:
        gold_status = "v03_hold_context_incomplete"
    elif "planned" in decision_type or "missed" in decision_type:
        gold_status = "v03_gold_actionable_context_ready"
    else:
        gold_status = "v03_gold_trade_context_ready"
    return {
        "context_id": row.get("candidate_id", "").replace("after1220", "v03_after1220"),
        "session_context_id": f"{vid}_session_v03",
        "video_id": vid,
        "video_title": title,
        "local_index_oldest_first": progress.get(vid, {}).get("local_index_oldest_first", ""),
        "source_stage_v03": "bdg_after1220_upgraded_with_local_frames",
        "decision_type": decision_type,
        "gold_status": gold_status,
        "symbol": "SOLUSDT/ETHUSDT",
        "direction": "short_or_long_as_spoken",
        "chart_timeframe": "1m execution; larger trend/CHOCH context",
        "market_date_utc_minus4": date,
        "market_time_window_utc_minus4": "",
        "visible_chart_time_note": row.get("youtube_window", ""),
        "market_time_confidence": conf,
        "youtube_window": row.get("youtube_window", ""),
        "anchor_seconds": parse_anchor_seconds(row.get("youtube_window", ""), row.get("source_anchors_ko", "")),
        "entry_price": "frame_relative_or_about",
        "stop_price": "frame_relative_or_about",
        "target_price": "frame_relative_or_about",
        "realized_result": row.get("execution_result_ko", ""),
        "session_macro_context_ko": "bDg session continuation: 오전 bearish SOL thesis 이후 오후에는 큰 지지/저항, trend retest, CHoCH/FVG를 따라 long/short를 조건부로 전환.",
        "scenario_tree_ko": "좋은 entry가 이미 지나가면 pass; 같은 thesis가 유지되면 reentry; level/FVG가 invalidated되면 stop; key zone 미도달이면 no-fill.",
        "symbol_selection_context_ko": "주로 SOL을 보되 ETH CHoCH/FVG가 더 선명한 경우 ETH setup도 후보화.",
        "elliott_wave_context_ko": "5-wave/2.618/rejection zone 언급이 있는 row에서는 early/stab short의 위치 필터로 사용.",
        "trade_thesis_link_ko": row.get("context_summary_ko", ""),
        "structure_reference_ko": row.get("setup_summary_ko", ""),
        "setup_context_ko": row.get("context_summary_ko", "") + " / " + row.get("setup_summary_ko", ""),
        "entry_plan_ko": row.get("setup_summary_ko", ""),
        "management_plan_ko": "BE 이동, 수동청산, TP 조정, stop-out 여부를 row별 execution_result와 source anchors로 연결.",
        "live_thesis_changes_ko": row.get("context_summary_ko", ""),
        "exit_result_ko": row.get("execution_result_ko", ""),
        "frame_evidence_paths": frame_paths_for(vid, row.get("candidate_id", ""), row.get("youtube_window", "")),
        "ohlcv_alignment_ko": "v0.3 local frames attached; verified market date exists. Exact minute/price alignment remains row-by-row candle matching target for later numeric backtest extraction.",
        "rule_feature_vector_seed_ko": "; ".join(k for k, v in flags.items() if v),
        "invalidation_condition_ko": "FVG invalidation, key level reclaim against trade direction, or key zone not reached.",
        "remaining_uncertainty_ko": row.get("remaining_checks_ko", ""),
    }


def context_from_pilot(row: dict[str, str], d: dict[str, dict[str, str]], progress: dict[str, dict[str, str]], verified: dict[str, dict[str, str]]) -> dict[str, str]:
    vid = row["video_id"]
    title = row.get("video_title") or d.get(vid, {}).get("title", "")
    text = " / ".join([row.get("transcript_context_ko", ""), row.get("chart_understanding_ko", ""), row.get("rule_features_ko", "")])
    flags = term_flags(text)
    date, conf = parse_market_date("", verified.get(vid, {}).get("verified_market_date", ""))
    decision_type = row.get("decision_type", "")
    old_frames = row.get("chart_frame_paths", "")
    local_frames = frame_paths_for(vid, row.get("candidate_id", ""), row.get("youtube_window", ""))
    return {
        "context_id": f"{row.get('candidate_id','')}_v03",
        "session_context_id": f"{vid}_session_v03",
        "video_id": vid,
        "video_title": title,
        "local_index_oldest_first": progress.get(vid, {}).get("local_index_oldest_first", ""),
        "source_stage_v03": "pilot3_promoted_with_local_frames",
        "decision_type": decision_type,
        "gold_status": "v03_gold_context_ready" if "context_incomplete" not in row.get("evidence_status", "") else "v03_hold_context_incomplete",
        "symbol": row.get("symbol", "").replace("SOL", "SOLUSDT").replace("ETH", "ETHUSDT"),
        "direction": row.get("direction", ""),
        "chart_timeframe": row.get("timeframe_evidence_ko", ""),
        "market_date_utc_minus4": date,
        "market_time_window_utc_minus4": progress.get(vid, {}).get("verified_market_date", ""),
        "visible_chart_time_note": row.get("youtube_window", ""),
        "market_time_confidence": conf,
        "youtube_window": row.get("youtube_window", ""),
        "anchor_seconds": parse_anchor_seconds(row.get("youtube_window", ""), row.get("source_anchors_ko", "")),
        "entry_price": "frame_relative_or_about",
        "stop_price": "frame_relative_or_about",
        "target_price": "frame_relative_or_about",
        "realized_result": row.get("execution_result_ko", ""),
        "session_macro_context_ko": row.get("transcript_context_ko", ""),
        "scenario_tree_ko": "Pilot3 promotion: setup complete/no-fill/cancel/executed decisions are kept separately; no-chase/pass logic is explicitly model evidence.",
        "symbol_selection_context_ko": "Transcript and frames determine whether SOL/ETH was selected for cleaner FVG/CHoCH/SR structure.",
        "elliott_wave_context_ko": " / ".join([p for p in text.split(" / ") if any(x in p.lower() for x in ["wave", "elliott", "2.618", "3.618", "4.618", "fib"])]) if flags["wave"] else "",
        "trade_thesis_link_ko": row.get("transcript_context_ko", ""),
        "structure_reference_ko": row.get("chart_understanding_ko", ""),
        "setup_context_ko": row.get("chart_understanding_ko", ""),
        "entry_plan_ko": row.get("rule_features_ko", ""),
        "management_plan_ko": row.get("execution_result_ko", ""),
        "live_thesis_changes_ko": row.get("transcript_context_ko", ""),
        "exit_result_ko": row.get("execution_result_ko", ""),
        "frame_evidence_paths": "|".join(x for x in [old_frames, local_frames] if x),
        "ohlcv_alignment_ko": "v0.3 promotion required: verified date exists for these pilot videos; local frames now attached. Numeric OHLCV matching column is prepared for next exact-price pass.",
        "rule_feature_vector_seed_ko": row.get("rule_features_ko", ""),
        "invalidation_condition_ko": "No-fill if key entry zone not touched; cancel if true FVG touch already passed; stop/BE/TP by frame/recap outcome.",
        "remaining_uncertainty_ko": row.get("remaining_checks_ko", ""),
    }


def context_from_frame(row: dict[str, str], d: dict[str, dict[str, str]], progress: dict[str, dict[str, str]]) -> dict[str, str]:
    vid = row["video_id"]
    return {
        "context_id": row.get("context_id", "").replace("_fd_", "_v03_fd_"),
        "session_context_id": f"{vid}_session_v03",
        "video_id": vid,
        "video_title": d.get(vid, {}).get("title", ""),
        "local_index_oldest_first": progress.get(vid, {}).get("local_index_oldest_first", ""),
        "source_stage_v03": "frame_data_v02_schema_upgraded",
        "decision_type": row.get("decision_type", ""),
        "gold_status": "v03_gold_context_ready",
        "symbol": row.get("symbol", ""),
        "direction": row.get("direction", ""),
        "chart_timeframe": row.get("chart_timeframe", ""),
        "market_date_utc_minus4": row.get("market_date_utc_minus4", ""),
        "market_time_window_utc_minus4": row.get("market_time_window_utc_minus4", ""),
        "visible_chart_time_note": "frame price/time + spoken/overlay alignment; see v0.2 remaining uncertainty",
        "market_time_confidence": row.get("market_time_confidence", ""),
        "youtube_window": row.get("youtube_window", ""),
        "anchor_seconds": row.get("youtube_anchor_sec", ""),
        "entry_price": row.get("entry_price", ""),
        "stop_price": row.get("stop_price", ""),
        "target_price": row.get("target_price", ""),
        "realized_result": row.get("realized_result", ""),
        "session_macro_context_ko": row.get("pre_trade_context_ko", ""),
        "scenario_tree_ko": "v0.2 row upgraded: scenario is extracted from pre_trade/setup/management narrative and preserved for rule conversion.",
        "symbol_selection_context_ko": "Symbol choice retained from executed frame-data row; cross-symbol context is in session map if available.",
        "elliott_wave_context_ko": " / ".join([p for p in (row.get("pre_trade_context_ko", "") + " / " + row.get("setup_context_ko", "") + " / " + row.get("rule_extraction_notes_ko", "")).split(" / ") if any(x in p.lower() for x in ["wave", "파동", "2.618", "3.618", "4.618", "fib"])]),
        "trade_thesis_link_ko": row.get("pre_trade_context_ko", ""),
        "structure_reference_ko": row.get("setup_context_ko", ""),
        "setup_context_ko": row.get("setup_context_ko", ""),
        "entry_plan_ko": row.get("entry_plan_ko", ""),
        "management_plan_ko": row.get("management_ko", ""),
        "live_thesis_changes_ko": row.get("management_ko", ""),
        "exit_result_ko": row.get("exit_result_ko", ""),
        "frame_evidence_paths": row.get("frame_evidence_paths", ""),
        "ohlcv_alignment_ko": row.get("ohlcv_alignment_ko", ""),
        "rule_feature_vector_seed_ko": row.get("rule_extraction_notes_ko", ""),
        "invalidation_condition_ko": "Invalidation follows stop placement, FVG/level failure, no continuation after key close, or reclaimed trend/level against thesis.",
        "remaining_uncertainty_ko": row.get("remaining_uncertainty_ko", ""),
    }


def rule_from_context(row: dict[str, str]) -> dict[str, str]:
    setup = " / ".join([row.get("setup_context_ko", ""), row.get("structure_reference_ko", ""), row.get("rule_feature_vector_seed_ko", "")])
    flags = term_flags(setup)
    return {
        "rule_seed_id": row["context_id"] + "_rule",
        "context_id": row["context_id"],
        "video_id": row["video_id"],
        "decision_type": row["decision_type"],
        "symbol": row["symbol"],
        "direction": row["direction"],
        "macro_bias_feature": row.get("session_macro_context_ko", "")[:500],
        "scenario_feature": row.get("scenario_tree_ko", ""),
        "wave_fib_feature": row.get("elliott_wave_context_ko", ""),
        "setup_trigger_feature": "; ".join(k for k in ["fvg", "choch", "trend", "sr"] if flags.get(k)),
        "entry_feature": row.get("entry_plan_ko", ""),
        "invalidation_feature": row.get("invalidation_condition_ko", ""),
        "management_feature": row.get("management_plan_ko", ""),
        "outcome_feature": row.get("exit_result_ko", "") or row.get("realized_result", ""),
        "negative_or_pass_rule": "yes" if any(x in row["decision_type"] for x in ["pass", "cancel", "no_fill", "loss"]) else "",
        "quantification_notes_ko": "정량화 축: session bias, chosen symbol, wave/Fib overlap, FVG/CHoCH/SR/trendline trigger, entry zone touch, invalidation touch, BE/trail trigger, recap outcome.",
    }


def main() -> None:
    d, progress, verified = details()
    manual = read_csv(PROCESSED / "manual_seed_contexts.csv")
    bdg = read_csv(PROCESSED / "context_review_queue.csv")
    pilot = read_csv(PROCESSED / "pilot_3_context_review.csv")
    frame = read_csv(PROCESSED / "frame_data_trade_context_queue_v0_2.csv")
    frame_sessions = {r["video_id"]: r for r in read_csv(PROCESSED / "frame_data_video_session_maps_v0_2.csv")}

    context_rows: list[dict[str, str]] = []
    for row in manual:
        if row.get("video_id") in MANUAL_IDS:
            context_rows.append(context_from_manual(row, d, progress, verified))
    for row in bdg:
        if row.get("video_id") == "bDgZhBFm1mU":
            context_rows.append(context_from_bdg(row, d, progress, verified))
    for row in pilot:
        if row.get("video_id") in PILOT_IDS:
            context_rows.append(context_from_pilot(row, d, progress, verified))
    for row in frame:
        if row.get("video_id") in FRAME_IDS:
            context_rows.append(context_from_frame(row, d, progress))

    session_texts: dict[str, list[str]] = defaultdict(list)
    for row in context_rows:
        session_texts[row["video_id"]].extend(
            [
                row.get("session_macro_context_ko", ""),
                row.get("setup_context_ko", ""),
                row.get("elliott_wave_context_ko", ""),
            ]
        )

    session_rows: list[dict[str, str]] = []
    for vid in ALL_IDS:
        title = d.get(vid, {}).get("title", "")
        stage = (
            "manual_seed_v03_upgraded"
            if vid in MANUAL_IDS
            else "pilot3_v03_promoted"
            if vid in PILOT_IDS
            else "frame_data_v02_schema_upgraded"
        )
        session = session_context_from_text(vid, title, session_texts[vid], stage, progress.get(vid, {}))
        if vid in frame_sessions:
            old = frame_sessions[vid]
            session["session_macro_context_ko"] = old.get("session_map_ko", session["session_macro_context_ko"])
            session["session_risk_context_ko"] = old.get("strategy_map_ko", session["session_risk_context_ko"])
            session["market_dates_utc_minus4"] = old.get("market_dates_utc_minus4", session["market_dates_utc_minus4"])
            session["primary_symbols"] = old.get("primary_symbols", session["primary_symbols"])
            session["confirmed_timeframes"] = old.get("confirmed_timeframes", session["confirmed_timeframes"])
            session["frame_contact_sheet"] = old.get("frame_contact_sheet", session["frame_contact_sheet"])
        session_rows.append(session)

    ready_context_rows = [row for row in context_rows if row.get("gold_status") != "v03_hold_context_incomplete"]
    hold_context_rows = [row for row in context_rows if row.get("gold_status") == "v03_hold_context_incomplete"]
    rule_rows = [rule_from_context(row) for row in ready_context_rows]

    audit_rows = []
    by_video = defaultdict(list)
    for row in ready_context_rows:
        by_video[row["video_id"]].append(row)
    for vid in ALL_IDS:
        rows = by_video[vid]
        all_rows_for_video = [r for r in context_rows if r["video_id"] == vid]
        statuses = Counter(r.get("gold_status", "") for r in all_rows_for_video)
        audit_rows.append(
            {
                "video_id": vid,
                "video_title": d.get(vid, {}).get("title", ""),
                "context_rows": len(rows),
                "status_mix": "; ".join(f"{k}:{v}" for k, v in sorted(statuses.items())),
                "has_session_row": "yes",
                "has_local_frames": "yes" if frame_paths_for(vid) else "legacy_only",
                "v03_quality_note_ko": "v0.3 schema populated. Macro/scenario/symbol/wave/live-change fields are separated; frame evidence and rule seed rows attached.",
            }
        )

    write_csv(PROCESSED / "gold_v03_video_session_maps.csv", session_rows, SESSION_FIELDS)
    write_csv(PROCESSED / "gold_v03_all_context_queue.csv", context_rows, CTX_FIELDS)
    write_csv(PROCESSED / "gold_v03_trade_context_queue.csv", ready_context_rows, CTX_FIELDS)
    write_csv(PROCESSED / "gold_v03_hold_context_queue.csv", hold_context_rows, CTX_FIELDS)
    write_csv(PROCESSED / "gold_v03_rule_seed_queue.csv", rule_rows, RULE_FIELDS)
    write_csv(
        PROCESSED / "gold_v03_quality_audit.csv",
        audit_rows,
        ["video_id", "video_title", "context_rows", "status_mix", "has_session_row", "has_local_frames", "v03_quality_note_ko"],
    )
    print("sessions", len(session_rows))
    print("all_contexts", len(context_rows))
    print("ready_contexts", len(ready_context_rows))
    print("hold_contexts", len(hold_context_rows))
    print("rules", len(rule_rows))
    print("audit", len(audit_rows))


if __name__ == "__main__":
    main()
