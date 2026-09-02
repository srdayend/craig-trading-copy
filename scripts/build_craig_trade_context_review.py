#!/usr/bin/env python3
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAKES = ROOT / "outputs" / "craig_all_live_take_candidate_queue.csv"
TRANSCRIPTS = ROOT / "data" / "source" / "craig_youtube" / "transcripts"
OUT_CSV = ROOT / "outputs" / "craig_trade_context_review.csv"
OUT_MD = ROOT / "outputs" / "craig_trade_context_review.md"
OUT_BY_VIDEO = ROOT / "outputs" / "craig_trade_context_by_video.md"


def rx(value: str) -> re.Pattern[str]:
    return re.compile(value, flags=re.IGNORECASE)


CATEGORY_PATTERNS: dict[str, list[tuple[str, re.Pattern[str]]]] = {
    "htf_view": [
        ("higher time frame", rx(r"\bhigher[- ]time[- ]frame\b")),
        ("macro", rx(r"\bmacro\b")),
        ("larger picture", rx(r"\blarger (picture|time frame|timeframe)\b")),
        ("daily bias", rx(r"\bdaily bias\b")),
        ("4 hour", rx(r"\b(4 ?h|four hour|4 hour)\b")),
        ("1 hour", rx(r"\b(1 ?h|one hour|1 hour)\b")),
        ("15 minute", rx(r"\b(15 ?m|15 minute|fifteen minute)\b")),
    ],
    "trendline": [
        ("trendline", rx(r"\btrend ?line\b")),
        ("uptrend", rx(r"\buptrend\b")),
        ("downtrend", rx(r"\bdowntrend\b")),
        ("diagonal", rx(r"\bdiagonal\b")),
    ],
    "sr_level": [
        ("support", rx(r"\bsupport\b")),
        ("resistance", rx(r"\bresistance\b")),
        ("key level", rx(r"\bkey level\b")),
        ("previous level", rx(r"\b(previous|rejected|low|high|macro) level\b")),
        ("this level", rx(r"\bthis level\b")),
        ("that level", rx(r"\bthat level\b")),
        ("rejected area", rx(r"\brejected area\b")),
        ("macro area", rx(r"\bmacro area\b")),
        ("this area", rx(r"\bthis area\b")),
        ("that area", rx(r"\bthat area\b")),
        ("zone", rx(r"\bzone\b")),
        ("rejected area", rx(r"\brejected area\b")),
    ],
    "flip_retest": [
        ("flip", rx(r"\bflip(ped|s|ping)?\b")),
        ("retest", rx(r"\bretest(ing|ed)?\b")),
        ("responded", rx(r"\brespond(ed|ing)?\b")),
        ("reject", rx(r"\breject(ed|ion|ing)?\b")),
        ("break underneath", rx(r"\bbreak (underneath|below|down)\b")),
        ("break above", rx(r"\bbreak (above|over|out)\b")),
        ("holding", rx(r"\bhold(ing)?\b")),
    ],
    "fvg": [
        ("fair value gap", rx(r"\bfair value gap\b")),
        ("gap", rx(r"\bgap\b")),
    ],
    "midpoint": [
        ("midpoint", rx(r"\bmid[- ]?point\b")),
    ],
    "structure": [
        ("change of character", rx(r"\bchange of character\b")),
        ("choch", rx(r"\bchoch\b")),
        ("break of structure", rx(r"\bbreak of structure\b")),
        ("bos", rx(r"\bbos\b")),
        ("candle close", rx(r"\bcandle close\b|\bclose above\b|\bclose below\b")),
    ],
    "liquidity_target": [
        ("liquidity", rx(r"\bliquidity\b")),
        ("previous day high", rx(r"\bprevious day high\b")),
        ("previous day low", rx(r"\bprevious day low\b")),
        ("take profit", rx(r"\btake[- ]profit\b")),
        ("target", rx(r"\btarget(ing)?\b")),
        ("fill", rx(r"\bfill(ed|ing)?\b")),
        ("sweep", rx(r"\bsweep\b")),
    ],
    "pair_market": [
        ("solana", rx(r"\bsolana\b|\bsolusdt\b|\bsol\b")),
        ("bitcoin", rx(r"\bbitcoin\b|\bbtc\b|\bbtcusdt\b")),
        ("ethereum", rx(r"\beth(ereum)?\b|\bethusdt\b")),
        ("market", rx(r"\bmarket\b")),
        ("momentum", rx(r"\bmomentum\b")),
        ("strength", rx(r"\bstrength\b|\bstrong\b|\bweak(ness)?\b")),
    ],
    "volatility_session": [
        ("volatile", rx(r"\bvolatil(e|ity)\b")),
        ("volume", rx(r"\bvolume\b")),
        ("asia", rx(r"\basia(n)?\b")),
        ("london", rx(r"\blondon\b")),
        ("new york", rx(r"\bnew york\b|\bny\b")),
        ("session", rx(r"\bsession\b")),
        ("open", rx(r"\bopen(ing)?\b")),
        ("power hour", rx(r"\bpower hour\b")),
        ("chop", rx(r"\bchop(py)?\b")),
        ("slow", rx(r"\bslow\b")),
    ],
    "risk_management": [
        ("risk", rx(r"\brisk\b")),
        ("stop loss", rx(r"\bstop[- ]loss\b")),
        ("break even", rx(r"\bbreak[- ]?even\b")),
        ("reduce risk", rx(r"\breduce my risk\b|\breduc(e|ing) risk\b")),
        ("partial", rx(r"\bpartial(s)?\b|\bhalf out\b")),
        ("runner", rx(r"\brun(ners?|ning)?\b")),
        ("contained loss", rx(r"\bcontained loss\b")),
        ("daily goal", rx(r"\bdaily goal\b")),
    ],
    "psychology_state": [
        ("revenge", rx(r"\brevenge trading\b")),
        ("tilt", rx(r"\btilt\b")),
        ("forcing", rx(r"\bforc(e|ing)\b")),
        ("careful", rx(r"\bcareful\b")),
        ("objective", rx(r"\bobjective\b")),
        ("pressure", rx(r"\bpressure\b")),
        ("buffer", rx(r"\bbuffer\b")),
    ],
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def parse_float(value: str) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def parse_transcript(video_id: str) -> list[dict[str, str | float]]:
    path = TRANSCRIPTS / f"{video_id}.txt"
    rows: list[dict[str, str | float]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "\t" not in line:
            continue
        ts, text = line.split("\t", 1)
        try:
            rows.append({"time": float(ts), "text": text.strip()})
        except ValueError:
            continue
    return rows


def first_take_by_video(takes: list[dict[str, str]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in takes:
        video_id = row["video_id"]
        ts = parse_float(row.get("timestamp_start_sec", ""))
        if video_id not in out or ts < out[video_id]:
            out[video_id] = ts
    return out


def in_window(rows: list[dict[str, str | float]], start: float, end: float) -> list[dict[str, str | float]]:
    return [row for row in rows if start <= float(row["time"]) <= end]


def category_hits(rows: list[dict[str, str | float]]) -> dict[str, list[tuple[float, str]]]:
    hits: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for row in rows:
        text = str(row["text"])
        for category, patterns in CATEGORY_PATTERNS.items():
            for label, pattern in patterns:
                if pattern.search(text):
                    hits[category].append((float(row["time"]), label))
                    break
    return hits


def merge_hits(*parts: dict[str, list[tuple[float, str]]]) -> dict[str, list[tuple[float, str]]]:
    out: dict[str, list[tuple[float, str]]] = defaultdict(list)
    for part in parts:
        for category, values in part.items():
            out[category].extend(values)
    for values in out.values():
        values.sort(key=lambda x: x[0])
    return out


def count_hits(hits: dict[str, list[tuple[float, str]]], category: str) -> int:
    return len(hits.get(category, []))


def has(hits: dict[str, list[tuple[float, str]]], category: str) -> bool:
    return count_hits(hits, category) > 0


def level_from_score(score: int) -> str:
    if score >= 4:
        return "strong"
    if score >= 2:
        return "moderate"
    if score >= 1:
        return "weak"
    return "none"


def short_evidence(hits: dict[str, list[tuple[float, str]]], categories: list[str], limit: int = 10) -> str:
    items: list[str] = []
    for category in categories:
        seen = set()
        for ts, label in hits.get(category, []):
            key = (int(ts), label)
            if key in seen:
                continue
            seen.add(key)
            items.append(f"{category}@{int(ts)}s:{label}")
            if len(items) >= limit:
                return "|".join(items)
    return "|".join(items)


def setup_components(hits: dict[str, list[tuple[float, str]]], take_features: str) -> list[str]:
    components: list[str] = []
    if has(hits, "htf_view") or "htf_zone" in take_features:
        components.append("HTF_뷰")
    if has(hits, "trendline"):
        components.append("추세선")
    if has(hits, "sr_level") and has(hits, "flip_retest"):
        components.append("SR_플립_반응")
    elif has(hits, "sr_level"):
        components.append("주요_SR")
    if has(hits, "fvg"):
        components.append("FVG")
    if has(hits, "midpoint") or "midpoint" in take_features:
        components.append("FVG_중앙값")
    if has(hits, "structure") or any(x in take_features for x in ["choch", "bos"]):
        components.append("1분_구조전환")
    if has(hits, "liquidity_target"):
        components.append("유동성_타겟")
    if has(hits, "risk_management") or "risk" in take_features:
        components.append("손절_TP_관리")
    if has(hits, "volatility_session"):
        components.append("변동성_세션_맥락")
    if has(hits, "pair_market"):
        components.append("페어_시장_움직임")
    if has(hits, "psychology_state"):
        components.append("심리_상태관리")
    return components


def classify(row: dict[str, str], hits: dict[str, list[tuple[float, str]]]) -> dict[str, str]:
    features = row.get("take_features", "")
    explicit_htf = has(hits, "htf_view") or "htf_zone" in features
    explicit_liquidity = has(hits, "liquidity_target")
    explicit_sr_reaction = has(hits, "sr_level") and has(hits, "flip_retest")
    explicit_trendline = has(hits, "trendline")

    htf_score = 0
    if explicit_htf:
        htf_score += 2
    if explicit_liquidity:
        htf_score += 1
    if explicit_sr_reaction:
        htf_score += 1
    if has(hits, "fvg") and (explicit_htf or explicit_liquidity or explicit_sr_reaction):
        htf_score += 1
    htf_level = level_from_score(htf_score)

    trend_score = 0
    if explicit_trendline:
        trend_score += 2
    if explicit_trendline and (has(hits, "flip_retest") or explicit_liquidity):
        trend_score += 1
    trendline_level = level_from_score(trend_score)

    sr_score = 0
    if has(hits, "sr_level"):
        sr_score += 1
    if has(hits, "flip_retest"):
        sr_score += 2
    if has(hits, "htf_view"):
        sr_score += 1
    sr_level = level_from_score(sr_score)

    ltf_score = 0
    if has(hits, "fvg") or "fvg" in features:
        ltf_score += 1
    if has(hits, "midpoint") or "midpoint" in features:
        ltf_score += 1
    if has(hits, "structure") or any(x in features for x in ["choch", "bos"]):
        ltf_score += 1
    if has(hits, "risk_management") or "risk" in features:
        ltf_score += 1
    ltf_quality = "high" if ltf_score >= 3 else "medium" if ltf_score >= 2 else "low"

    if explicit_trendline and trendline_level in {"strong", "moderate"} and htf_level in {"strong", "moderate"}:
        archetype = "HTF_trendline_reaction"
    elif sr_level in {"strong", "moderate"} and htf_level in {"strong", "moderate"}:
        archetype = "HTF_SR_flip_reaction"
    elif htf_level in {"strong", "moderate"} and (has(hits, "fvg") or "fvg" in features):
        archetype = "HTF_FVG_reaction"
    elif has(hits, "liquidity_target") and (has(hits, "flip_retest") or has(hits, "structure")):
        archetype = "range_liquidity_reaction"
    elif has(hits, "htf_view") or has(hits, "pair_market"):
        archetype = "daily_bias_continuation_or_flip"
    elif ltf_quality in {"high", "medium"}:
        archetype = "LTF_setup_with_unclear_HTF"
    else:
        archetype = "unclear_transcript_only"

    gaps: list[str] = []
    if htf_level in {"strong", "moderate"}:
        gaps.append("HTF_plan_first_pipeline")
    if trendline_level != "none":
        gaps.append("HTF_trendline_detector")
    elif htf_level in {"strong", "moderate"}:
        gaps.append("frame_review_manual_trendline")
    if sr_level != "none":
        gaps.append("SR_flip_box_detector")
    if has(hits, "fvg") or "fvg" in features:
        gaps.append("FVG_role_entry_vs_target")
    if has(hits, "liquidity_target"):
        gaps.append("real_HTF_target_not_synthetic_4R")
    if has(hits, "risk_management"):
        gaps.append("position_box_SL_TP_management")
    if has(hits, "volatility_session"):
        gaps.append("time_as_volatility_context")
    if has(hits, "pair_market"):
        gaps.append("pair_market_context")
    if has(hits, "psychology_state"):
        gaps.append("state_after_loss_or_goal")

    if htf_level in {"strong", "moderate"} and ltf_quality == "high":
        action = "decision_layer_rewrite_seed"
    elif htf_level in {"strong", "moderate"}:
        action = "use_for_HTF_plan_label_then_frame_review"
    elif ltf_quality == "high":
        action = "frame_review_before_model_training"
    else:
        action = "low_confidence_reference_only"

    visual_needed = []
    if "frame_review_manual_trendline" in gaps or trendline_level == "none":
        visual_needed.append("manual_line_box")
    if "position_box_SL_TP_management" in gaps or row.get("needs_review"):
        visual_needed.append("entry_SL_TP_box")
    if row.get("symbol_hint") == "unknown":
        visual_needed.append("symbol")

    return {
        "primary_trade_archetype": archetype,
        "htf_evidence_level": htf_level,
        "trendline_evidence_level": trendline_level,
        "sr_flip_evidence_level": sr_level,
        "ltf_entry_quality": ltf_quality,
        "management_specificity": "detailed" if has(hits, "risk_management") else "weak",
        "pair_context_level": "explicit" if has(hits, "pair_market") else "mostly_assume_SOL",
        "volatility_context_level": "explicit" if has(hits, "volatility_session") else "not_spoken",
        "setup_components_ko": "|".join(setup_components(hits, features)),
        "model_gap_tags": "|".join(gaps),
        "recommended_model_action": action,
        "frame_review_required": "|".join(dict.fromkeys(visual_needed)),
    }


def build_rows() -> list[dict[str, str]]:
    takes = read_csv(TAKES)
    first_take = first_take_by_video(takes)
    transcripts = {video_id: parse_transcript(video_id) for video_id in sorted({r["video_id"] for r in takes})}
    rows_out: list[dict[str, str]] = []

    for row in takes:
        video_id = row["video_id"]
        transcript = transcripts.get(video_id, [])
        ts = parse_float(row.get("timestamp_start_sec", ""))
        next_exit = parse_float(row.get("next_exit_time_sec", "")) or ts + 600
        first = first_take.get(video_id, ts)

        video_plan = category_hits(in_window(transcript, 0, min(first, 480)))
        pre = category_hits(in_window(transcript, max(0, ts - 900), ts + 10))
        entry = category_hits(in_window(transcript, max(0, ts - 120), ts + 150))
        management = category_hits(in_window(transcript, ts, min(next_exit + 120, ts + 720)))
        all_hits = merge_hits(video_plan, pre, entry, management)
        classes = classify(row, all_hits)

        count_fields = {
            f"{category}_hits": str(count_hits(all_hits, category)) for category in CATEGORY_PATTERNS
        }
        out = {
            "trade_candidate_id": row["trade_candidate_id"],
            "video_id": video_id,
            "market_date": row.get("market_date", ""),
            "timestamp_start_sec": row.get("timestamp_start_sec", ""),
            "timestamp_url": row.get("timestamp_url", ""),
            "title": row.get("title", ""),
            "observed_direction": row.get("observed_direction", ""),
            "symbol_hint": row.get("symbol_hint", ""),
            "take_features": row.get("take_features", ""),
            **classes,
            **count_fields,
            "compact_evidence_terms": short_evidence(
                all_hits,
                [
                    "htf_view",
                    "trendline",
                    "sr_level",
                    "flip_retest",
                    "fvg",
                    "midpoint",
                    "structure",
                    "liquidity_target",
                    "risk_management",
                    "pair_market",
                    "volatility_session",
                    "psychology_state",
                ],
                limit=14,
            ),
        }
        rows_out.append(out)
    return rows_out


def md_count_table(counter: Counter[str], title: str) -> list[str]:
    lines = [f"## {title}", "", "| 항목 | 개수 |", "|---|---:|"]
    for key, value in counter.most_common():
        lines.append(f"| `{key or 'blank'}` | {value} |")
    lines.append("")
    return lines


def write_reports(rows: list[dict[str, str]]) -> None:
    total = len(rows)
    archetypes = Counter(row["primary_trade_archetype"] for row in rows)
    htf_levels = Counter(row["htf_evidence_level"] for row in rows)
    actions = Counter(row["recommended_model_action"] for row in rows)
    frame_review = sum(1 for row in rows if row["frame_review_required"])
    ltf_high = sum(1 for row in rows if row["ltf_entry_quality"] == "high")
    trendline_any = sum(1 for row in rows if row["trendline_evidence_level"] != "none")
    sr_any = sum(1 for row in rows if row["sr_flip_evidence_level"] != "none")
    htf_strongish = sum(1 for row in rows if row["htf_evidence_level"] in {"strong", "moderate"})

    lines = [
        "# Craig LIVE Trade Context Review",
        "",
        "이 보고서는 LIVE Take 후보 36개를 대상으로 자막에서 확인 가능한 근거를 HTF/셋업/페어/관리 맥락으로 다시 라벨링한 결과다.",
        "",
        "## Executive Summary",
        "",
        f"- **결론은 보완보다 의사결정 레이어 재작성에 가깝다.** 데이터 수집, 1분 FVG/CHoCH 탐지, replay 로직은 유지하되, 진입 판단은 `HTF plan 먼저 -> reaction zone -> 1분 trigger` 순서로 바꿔야 한다.",
        f"- **자막 기준 HTF 근거가 moderate 이상인 후보는 {htf_strongish}/{total}개다.** 즉 Craig의 trade 설명은 단순 1분 FVG가 아니라 큰 레벨, gap, liquidity, trend/session context를 먼저 두는 경우가 많다.",
        f"- **1분 entry quality가 high로 보이는 후보는 {ltf_high}/{total}개다.** 이들은 모델 학습용 seed가 될 수 있지만, 실제 entry/SL/TP는 TradingView position box 프레임으로 검증해야 한다.",
        f"- **추세선 언급은 자막 기준 {trendline_any}/{total}개뿐이다.** 그러나 사용자가 제공한 프레임처럼 화면에는 HTF trendline이 핵심 근거로 보이는 케이스가 있으므로, trendline은 자막이 아니라 프레임/차트 계산에서 반드시 복원해야 한다.",
        "",
        "## 모델 수정 판단",
        "",
        "이번 결과로 기존 모델은 `부분 튜닝`이 아니라 `decision layer rewrite`가 필요하다고 판단한다.",
        "",
        "유지할 것:",
        "",
        "- Binance OHLCV 캐시와 재생/백테스트 구조",
        "- 1분 FVG, midpoint, CHoCH/BOS 보조 라벨",
        "- risk, BE, partial, target 추적 구조",
        "",
        "갈아엎을 것:",
        "",
        "- 1분 FVG를 먼저 찾고 HTF 근거를 나중에 붙이는 순서",
        "- 시간대를 hard gate로 자르는 방식",
        "- 15m/1h/4h FVG를 모두 같은 entry zone으로 취급하는 방식",
        "- synthetic 4R target을 Craig target처럼 쓰는 방식",
        "",
        "새 순서:",
        "",
        "1. 4H/1H/15m에서 trendline, SR flip box, repeated SR box, HTF FVG, 전일 고저점/liquidity draw를 먼저 만든다.",
        "2. 그중 지금 가격이 반응할 수 있는 `primary reaction zone`만 watchlist에 남긴다.",
        "3. 가격이 그 zone을 sweep/retest/reclaim/reject할 때만 1분 CHoCH/BOS/FVG를 본다.",
        "4. entry는 FVG midpoint/retest, stop은 sweep high/low 또는 구조 invalidation 밖, target은 실제 HTF draw로 잡는다.",
        "5. 시간은 진입 금지 조건이 아니라 변동성/세션 context 점수로만 쓴다.",
        "",
    ]
    lines.extend(md_count_table(archetypes, "Trade Archetype 분포"))
    lines.extend(md_count_table(htf_levels, "HTF 근거 강도"))
    lines.extend(md_count_table(actions, "모델 반영 우선순위"))
    lines.extend(
        [
            "## 시각 검증이 필요한 부분",
            "",
            f"- frame review 필요 후보: {frame_review}/{total}",
            "- TradingView의 빨간/파란 position box로 entry, stop, TP를 확인해야 한다.",
            "- 자막에 `trendline`이라는 단어가 없어도, 프레임의 점선/수동 라인이 HTF thesis인 경우가 있으므로 프레임 검증 없이는 누락될 수 있다.",
            "- Bybit 포지션 패널은 PnL 보조 확인용이고, 가격 구조 판정의 중심은 좌측 TradingView 차트다.",
            "",
            "## 오픈소스 도구 검토",
            "",
            "- `smartmoneyconcepts`: FVG, swing high/low, BOS/CHoCH, order block, liquidity, previous high/low, session 라벨을 자동 생성하는 보조 엔진 후보. 우리 모델에서는 정답 판정이 아니라 LuxAlgo 보조 라벨과 비슷한 참고 레이어로만 쓴다. <https://github.com/joshyattridge/smart-money-concepts>",
            "- `trendln`: 가격 시계열에서 support/resistance trend line을 계산하고 시각화하는 후보. 4H/1H/15m 추세선 후보 생성에 적합하다. <https://github.com/GregoryMorse/trendln>",
            "- `pytrendline`: OHLC 캔들 차트에서 high/close 기반 support/resistance trendline을 탐지하는 후보. 작은 day-trading 윈도우의 offline 분석에 적합하다. <https://github.com/ednunezg/pytrendline>",
            "",
            "주의: 이 도구들은 Craig의 화면 해석을 대체하지 않는다. 후보 라인/박스를 많이 만들고, Craig 자막/프레임과 겹치는 것만 high-confidence로 올리는 용도다.",
            "",
            "## 파일",
            "",
            f"- 상세 CSV: `{OUT_CSV.relative_to(ROOT)}`",
            f"- 영상별 요약: `{OUT_BY_VIDEO.relative_to(ROOT)}`",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")

    by_video: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_video[row["video_id"]].append(row)
    video_lines = [
        "# Craig Trade Context By Video",
        "",
        "각 영상별 Take 후보의 HTF/셋업/관리 근거 요약이다. 표의 근거는 자막 기반이며, trendline/SR box는 프레임 검증으로 보완해야 한다.",
        "",
    ]
    for video_id, group in sorted(by_video.items(), key=lambda x: min(r["market_date"] for r in x[1])):
        title = group[0]["title"]
        date = group[0]["market_date"]
        video_lines.extend([f"## {date} / {video_id}", "", title, ""])
        video_lines.extend(
            [
                "| 시간초 | 방향 | archetype | HTF | LTF | 모델 액션 | 시각 검증 |",
                "|---:|---|---|---|---|---|---|",
            ]
        )
        for row in sorted(group, key=lambda r: parse_float(r["timestamp_start_sec"])):
            video_lines.append(
                f"| {row['timestamp_start_sec']} | {row['observed_direction']} | "
                f"`{row['primary_trade_archetype']}` | `{row['htf_evidence_level']}` | "
                f"`{row['ltf_entry_quality']}` | `{row['recommended_model_action']}` | "
                f"`{row['frame_review_required'] or 'none'}` |"
            )
        video_lines.append("")
    OUT_BY_VIDEO.write_text("\n".join(video_lines) + "\n", encoding="utf-8")


def main() -> None:
    rows = build_rows()
    write_csv(OUT_CSV, rows)
    write_reports(rows)
    print(f"rows={len(rows)} output={OUT_CSV}")
    print(f"report={OUT_MD}")
    print(f"by_video={OUT_BY_VIDEO}")


if __name__ == "__main__":
    main()
