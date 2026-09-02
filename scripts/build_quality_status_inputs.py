from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIDEO_DIR = ROOT / "video source"
PROCESSED = ROOT / "data" / "processed" / "gold_context_trades"
DETAILS = ROOT / "data" / "source" / "craig_youtube" / "details.csv"
USER_DATES = ROOT / "data" / "source" / "craig_youtube" / "user_verified_market_dates.csv"
OUTPUT_DIR = ROOT / "outputs" / "craig_quality_tracker_v0_3"
OUTPUT_JSON = OUTPUT_DIR / "quality_tracker_inputs.json"


TERM_GROUPS = {
    "macro_hft": [
        r"\bmacro\b",
        r"\bhigher time\s*frame\b",
        r"\bhft\b",
        r"\b4h\b",
        r"\bdaily\b",
        r"\bday bias\b",
        r"\bdaily bias\b",
        r"\bbias\b",
        r"\bscenario\b",
        r"\bplan\b",
    ],
    "session_context": [
        r"\bnew york\b",
        r"\bny open\b",
        r"\bmarket open\b",
        r"\bsession\b",
        r"\bmorning\b",
        r"\bafternoon\b",
        r"\bovernight\b",
        r"\bgym\b",
    ],
    "symbol_selection": [
        r"\bbitcoin\b",
        r"\bbtc\b",
        r"\beth\b",
        r"\bethereum\b",
        r"\bsol\b",
        r"\bsolana\b",
        r"\brelative\b",
        r"\bstronger\b",
        r"\bweaker\b",
    ],
    "elliott_wave_fib": [
        r"\belliott\b",
        r"\bwave\b",
        r"\b1st wave\b",
        r"\bsecond wave\b",
        r"\bthird wave\b",
        r"\bfourth wave\b",
        r"\bfifth wave\b",
        r"\b5 wave\b",
        r"\b2\.618\b",
        r"\b3\.618\b",
        r"\b4\.618\b",
        r"\bfib\b",
        r"\bfibonacci\b",
        r"\bextension\b",
    ],
    "setup_terms": [
        r"\bfair value gap\b",
        r"\bfvg\b",
        r"\bchange of character\b",
        r"\bchoch\b",
        r"\bbreak of structure\b",
        r"\bbos\b",
        r"\btrend line\b",
        r"\btrendline\b",
        r"\bsupport\b",
        r"\bresistance\b",
        r"\bretest\b",
        r"\bunderside\b",
        r"\boverside\b",
        r"\bliquidity\b",
        r"\bsweep\b",
    ],
    "execution_management": [
        r"\bentry\b",
        r"\bfilled\b",
        r"\bstop loss\b",
        r"\bstopped\b",
        r"\btake profit\b",
        r"\btarget\b",
        r"\brisk\b",
        r"\bbreak even\b",
        r"\bbe\b",
        r"\btrail\b",
        r"\bclose\b",
        r"\brecap\b",
        r"\bjournal\b",
    ],
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def norm_title(value: str) -> str:
    value = value.lower()
    value = value.replace("’", "'").replace("“", '"').replace("”", '"')
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def iso_date(raw: str) -> str:
    raw = (raw or "").strip()
    if re.fullmatch(r"\d{8}", raw):
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
    return raw


def srt_text(path: Path) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    text = re.sub(r"^\d+\s*$", " ", text, flags=re.MULTILINE)
    text = re.sub(r"\d{2}:\d{2}:\d{2},\d{3}\s+-->\s+\d{2}:\d{2}:\d{2},\d{3}", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def count_terms(text: str) -> dict[str, int]:
    lower = text.lower()
    counts = {}
    for group, patterns in TERM_GROUPS.items():
        total = 0
        for pattern in patterns:
            total += len(re.findall(pattern, lower))
        counts[group] = total
    return counts


def group_count(rows: list[dict[str, str]], key: str) -> Counter:
    c: Counter = Counter()
    for row in rows:
        if row.get(key):
            c[row[key]] += 1
    return c


def group_statuses(rows: list[dict[str, str]], key: str, status_key: str) -> dict[str, Counter]:
    out: dict[str, Counter] = defaultdict(Counter)
    for row in rows:
        if row.get(key):
            out[row[key]][row.get(status_key, "") or "blank"] += 1
    return out


def stage_for_video(video_id: str, counts: dict[str, Counter]) -> tuple[str, int, str, str]:
    frame_rows = counts["frame_data"][video_id]
    pilot_rows = counts["pilot3"][video_id]
    manual_rows = counts["manual"][video_id]
    bdg_rows = counts["bdg"][video_id]
    remaining_rows = counts["remaining"][video_id]

    if frame_rows:
        return (
            "Q3 frame+OHLCV first pass",
            3,
            "정식 3개 품질. v0_3에서는 macro/wave/scenario를 별도 필드로 승격하고 about price를 보강.",
            "schema_upgrade",
        )
    if pilot_rows:
        return (
            "Q2 visual candidate",
            2,
            "프레임+자막 해석은 있음. UTC-4 시간, OHLCV 대조, entry/SL/TP/result 매칭을 보강.",
            "promote_pilot3",
        )
    if manual_rows or bdg_rows:
        return (
            "Q1 manual/BdG seed",
            1,
            "사용자 메모 또는 bDg 후보 큐 기반. 로컬 영상 프레임, SRT 재정독, 데이터 대조로 재구성.",
            "upgrade_manual_seed",
        )
    if remaining_rows:
        return (
            "Q0 auto transcript queue",
            0,
            "자동 후보 큐만 있음. 새 영상 절차로 처음부터 frame+data 검증 필요.",
            "process_new_video",
        )
    return (
        "Q0 source ready",
        0,
        "로컬 영상/SRT만 준비됨. 새 영상 절차로 후보 추출부터 시작.",
        "process_new_video",
    )


def main() -> None:
    details = read_csv(DETAILS)
    details_by_title = {norm_title(r.get("title", "")): r for r in details}
    details_by_id = {r.get("id", ""): r for r in details if r.get("id")}
    verified_dates = {
        r.get("video_id", ""): r.get("verified_market_date", "")
        for r in read_csv(USER_DATES)
        if r.get("video_id")
    }

    manual = read_csv(PROCESSED / "manual_seed_contexts.csv")
    bdg = read_csv(PROCESSED / "context_review_queue.csv")
    pilot3 = read_csv(PROCESSED / "pilot_3_context_review.csv")
    frame_data = read_csv(PROCESSED / "frame_data_trade_context_queue_v0_2.csv")
    remaining = read_csv(PROCESSED / "remaining_context_queue_v0_2.csv")
    final_master = read_csv(PROCESSED / "final_context_master_v0_2.csv")
    v03_sessions = read_csv(PROCESSED / "gold_v03_video_session_maps.csv")
    v03_contexts = read_csv(PROCESSED / "gold_v03_trade_context_queue.csv")
    v03_hold = read_csv(PROCESSED / "gold_v03_hold_context_queue.csv")
    v03_rules = read_csv(PROCESSED / "gold_v03_rule_seed_queue.csv")
    v03_audit = read_csv(PROCESSED / "gold_v03_quality_audit.csv")
    v03_session_dates = {
        r.get("video_id", ""): r.get("market_dates_utc_minus4", "")
        for r in v03_sessions
        if r.get("video_id")
    }
    v03_audit_notes = {
        r.get("video_id", ""): r.get("v03_quality_note_ko", "")
        for r in v03_audit
        if r.get("video_id")
    }

    counts = {
        "manual": group_count(manual, "video_id"),
        "bdg": group_count(bdg, "video_id"),
        "pilot3": group_count(pilot3, "video_id"),
        "frame_data": group_count(frame_data, "video_id"),
        "remaining": group_count(remaining, "video_id"),
        "final_master": group_count(final_master, "video_id"),
        "v03_sessions": group_count(v03_sessions, "video_id"),
        "v03_contexts": group_count(v03_contexts, "video_id"),
        "v03_hold": group_count(v03_hold, "video_id"),
        "v03_rules": group_count(v03_rules, "video_id"),
    }
    pilot_status = group_statuses(pilot3, "video_id", "evidence_status")
    frame_status = group_statuses(frame_data, "video_id", "gold_status")

    videos = sorted(VIDEO_DIR.glob("*.mp4"))
    srt_by_stem = {}
    for srt in VIDEO_DIR.glob("*.srt"):
        stem = srt.stem
        if stem.endswith(".en"):
            stem = stem[:-3]
        srt_by_stem[norm_title(stem)] = srt

    rows = []
    unmatched = []
    for video in videos:
        title = video.stem
        detail = details_by_title.get(norm_title(title))
        if not detail:
            unmatched.append(title)
            detail = {}
        video_id = detail.get("id", "")
        srt = srt_by_stem.get(norm_title(title))
        text = srt_text(srt) if srt else ""
        term_counts = count_terms(text)
        if counts["v03_sessions"][video_id]:
            hold_rows = counts["v03_hold"][video_id]
            audit_note = v03_audit_notes.get(video_id, "")
            if hold_rows:
                hold_note = f" hold {hold_rows}개 있음: {audit_note}" if audit_note else f" hold {hold_rows}개 있음."
            else:
                hold_note = f" {audit_note}" if audit_note else ""
            quality, score, gap_note, next_action = (
                "Q4 v0.3 gold-ready integrated",
                4,
                f"v0.3 session/context/rule queue에 통합 완료. 새 영상 처리 전 기준 샘플로 사용.{hold_note}",
                "complete_v03_or_spot_review",
            )
        else:
            quality, score, gap_note, next_action = stage_for_video(video_id, counts)
        if not video_id:
            quality, score, gap_note, next_action = (
                "Q0 source ready - title unmatched",
                0,
                "details.csv title 매칭 실패. video_id 수동 확인 필요.",
                "fix_metadata_match",
            )
        resolved_market_date = verified_dates.get(video_id, "") or v03_session_dates.get(video_id, "")
        market_date_source = ""
        if verified_dates.get(video_id, ""):
            market_date_source = "user_verified"
        elif v03_session_dates.get(video_id, ""):
            market_date_source = "v03_frame_or_session_verified"
        rows.append(
            {
                "local_index_oldest_first": None,
                "video_id": video_id,
                "video_title": title,
                "upload_date": iso_date(detail.get("upload_date", "")),
                "playlist_index_newest_first": detail.get("playlist_index", ""),
                "duration": detail.get("duration_string", ""),
                "video_file": str(video.relative_to(ROOT)),
                "srt_file": str(srt.relative_to(ROOT)) if srt else "",
                "verified_market_date": resolved_market_date,
                "market_date_source": market_date_source,
                "quality_level": quality,
                "quality_score": score,
                "manual_seed_rows": counts["manual"][video_id],
                "bdg_partial_rows": counts["bdg"][video_id],
                "pilot3_rows": counts["pilot3"][video_id],
                "frame_data_rows": counts["frame_data"][video_id],
                "remaining_auto_rows": counts["remaining"][video_id],
                "final_master_rows": counts["final_master"][video_id],
                "v03_session_rows": counts["v03_sessions"][video_id],
                "v03_context_rows": counts["v03_contexts"][video_id],
                "v03_hold_rows": counts["v03_hold"][video_id],
                "v03_rule_rows": counts["v03_rules"][video_id],
                "pilot3_status_mix": "; ".join(f"{k}:{v}" for k, v in sorted(pilot_status.get(video_id, {}).items())),
                "frame_status_mix": "; ".join(f"{k}:{v}" for k, v in sorted(frame_status.get(video_id, {}).items())),
                "asset_ready": "yes" if video.exists() and srt else "missing_srt" if video.exists() else "missing_video",
                "macro_hft_term_hits": term_counts["macro_hft"],
                "session_term_hits": term_counts["session_context"],
                "symbol_selection_term_hits": term_counts["symbol_selection"],
                "elliott_wave_fib_term_hits": term_counts["elliott_wave_fib"],
                "setup_term_hits": term_counts["setup_terms"],
                "execution_management_term_hits": term_counts["execution_management"],
                "macro_status_v0_3": "needs_structured_field" if score >= 3 else "needs_extract",
                "elliott_status_v0_3": "needs_structured_field" if term_counts["elliott_wave_fib"] else "scan_low_or_absent",
                "time_data_status": "validated_window_present" if score >= 3 else "needs_utc4_ohlcv_alignment",
                "entry_sl_tp_status": "present_or_about" if score >= 3 else "needs_frame_ocr_or_visual_read",
                "result_status": "recap_aligned" if score >= 3 else "needs_recap_or_outcome_check",
                "next_action": next_action,
                "gap_note": gap_note,
                "working_status": "완료/hold있음" if score >= 4 and counts["v03_hold"][video_id] else "완료" if score >= 4 else "대기" if score < 3 else "보강필요",
            }
        )

    rows.sort(key=lambda r: (r["upload_date"] or "9999-99-99", r["video_title"]))
    for i, row in enumerate(rows, 1):
        row["local_index_oldest_first"] = i

    stage_summary = Counter(r["quality_level"] for r in rows)
    action_summary = Counter(r["next_action"] for r in rows)
    scope_summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "local_video_count": len(videos),
        "local_srt_count": len(list(VIDEO_DIR.glob("*.srt"))),
        "matched_video_id_count": sum(1 for r in rows if r["video_id"]),
        "unmatched_titles": unmatched,
        "stage_summary": dict(stage_summary),
        "action_summary": dict(action_summary),
    }

    quality_gates = [
        ["G01", "로컬 소스", "mp4+srt+video_id+title", "영상/SRT가 로컬에 있고 details.csv와 매칭됨"],
        ["G02", "세션 매크로/HFT", "초반 HFT, daily bias, BTC/SOL/ETH 상위 맥락", "당일 기본 방향과 조건부 시나리오가 분리 기록됨"],
        ["G03", "시나리오 트리", "if bullish / if bearish / wait condition", "Craig가 어느 조건에서 방향을 바꾸는지 기록됨"],
        ["G04", "심볼 선택", "BTC/ETH/SOL 상대 강약, 왜 이 종목인지", "거래 종목 선택 이유가 trade row와 연결됨"],
        ["G05", "Elliott/Fib", "wave count, extension, invalidation, pass reason", "파동/피보가 쓰였으면 프레임 또는 자막 근거로 구조화됨"],
        ["G06", "차트 구조", "TF, FVG, CHoCH/BOS, SR, trendline, liquidity", "어떤 고점/저점/존을 기준으로 했는지 설명됨"],
        ["G07", "주문 구조", "direction, entry, SL, TP, R/R, position box", "프레임에서 박스/숫자 또는 상대 구조 확인됨"],
        ["G08", "실제 시간", "market date/time UTC-4", "하단축/발화/차트 데이터로 시간 창이 확인됨"],
        ["G09", "OHLCV 대조", "1m candles for symbol/date/window", "fill/stop/TP/no-fill/BE가 데이터 흐름과 모순 없음"],
        ["G10", "관리/의견 변화", "BE, trail, cancel, pass, confidence shift", "실시간 생각 변화와 행동 트리거가 기록됨"],
        ["G11", "종료/recap", "journal, PnL, R multiple, trade number", "결과와 setup row가 대응됨"],
        ["G12", "룰 추출", "feature, trigger, invalidation, management rule", "정량화 가능한 rule seed로 분해됨"],
        ["G13", "불확실성", "OCR/시간/방향/체결 의문", "불확실하면 gold 승격 대신 보류/제외 사유 기록"],
    ]

    extraction_steps = [
        [1, "소스 고정", "로컬 mp4+srt를 details.csv와 매칭하고 로컬 index를 확정", "Progress_Index"],
        [2, "SRT 후보 스캔", "entry/fill/stop/TP/FVG/CHoCH/wave/macro/recap term으로 후보 창 생성", "candidate queue"],
        [3, "세션 맵 작성", "영상 앞쪽 macro/HFT/daily bias/scenario/symbol preference를 먼저 구조화", "session_macro_context"],
        [4, "파동 맵 작성", "Elliott count, 2.618/3.618/4.618, wave extension/pass logic을 별도 구조화", "elliott_wave_context"],
        [5, "decision unit 분할", "실행/미체결/취소/패스/재진입/관리 변경을 의사결정 단위로 자름", "trade_context_queue"],
        [6, "필요 프레임 추출", "setup box, TF, 하단축, 차트 구조, management, recap만 로컬 영상에서 캡처", "frame evidence"],
        [7, "차트 구조 판독", "SR/FVG/CHoCH/trendline/liquidity/wave가 어떤 캔들/존에서 나온 것인지 메모", "chart_context"],
        [8, "UTC-4 시간 정렬", "하단축/발화/가격으로 실제 날짜와 시간창을 확정", "market_time_window"],
        [9, "OHLCV 검증", "1분봉으로 fill, no-fill, stop, TP, BE, runner 가능성을 대조", "ohlcv_alignment"],
        [10, "결과 대조", "recap/journal/PnL/R/trade number와 row를 연결", "exit_result"],
        [11, "룰 seed 변환", "bias -> trigger -> entry -> invalidation -> management -> exit 구조로 정리", "rule_seed"],
        [12, "gold 판정", "G01-G13 충족 여부와 불확실성으로 ready/hold/discard 결정", "gold_status"],
    ]

    category_audit = [
        [
            "세션 매크로/HFT",
            "기존 v0_2에는 들어가 있으나 pre_trade_context에 섞임",
            "v0_3에서는 영상 단위 session_macro_context와 trade_thesis_link로 분리",
        ],
        [
            "Daily bias와 조건부 시나리오",
            "bearish/bullish bias는 적었지만 if/then 시나리오 구조가 일관 컬럼은 아님",
            "scenario_tree_ko, bias_invalidation_ko 추가",
        ],
        [
            "심볼 선택/상대 강도",
            "ETH/SOL/BTC 비교가 일부 narrative에만 있음",
            "symbol_selection_context_ko와 reference_symbol_context_ko 추가",
        ],
        [
            "Elliott wave/Fib",
            "일부 row에 5파/2.618이 있으나 별도 카테고리가 없음",
            "elliott_wave_context_ko, fib_extension_context_ko, wave_pass_reason_ko 추가",
        ],
        [
            "실시간 의견 변경",
            "management_ko에는 있으나 bias flip/cancel/pass의 원인이 충분히 분리되지 않음",
            "live_thesis_changes_ko와 decision_change_trigger_ko 추가",
        ],
        [
            "프레임에서 보이는 구조의 좌표적 설명",
            "현재는 사람이 읽을 수 있는 설명 위주",
            "structure_reference_ko에 '어떤 고점/저점/존/캔들' 기준인지 강제 기록",
        ],
        [
            "정량화 준비도",
            "rule_extraction_notes는 좋지만 feature값/trigger/invalidation이 한 문장에 섞임",
            "rule_feature_vector_seed_ko와 invalidation_condition_ko 분리",
        ],
        [
            "No-fill/pass/cancel setup",
            "포함 원칙은 확정됐지만 품질 gate가 실행 trade와 구분되어 있지 않음",
            "decision_type별 필수 evidence checklist를 다르게 적용",
        ],
    ]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(
        json.dumps(
            {
                "scope_summary": scope_summary,
                "videos": rows,
                "quality_gates": quality_gates,
                "extraction_steps": extraction_steps,
                "category_audit": category_audit,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(OUTPUT_JSON)


if __name__ == "__main__":
    main()
