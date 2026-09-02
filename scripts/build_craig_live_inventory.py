#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DETAILS_CSV = ROOT / "data/source/craig_youtube/details.csv"
LABELS_CSV = ROOT / "outputs/craig_transcript_observed_labels.csv"
EPISODES_CSV = ROOT / "outputs/craig_episode_map_visual_date_corrected.csv"
USER_DATES_CSV = ROOT / "data/source/craig_youtube/user_verified_market_dates.csv"
TRANSCRIPT_DIR = ROOT / "data/source/craig_youtube/transcripts"
OUT_CSV = ROOT / "outputs/craig_live_trading_video_inventory.csv"
OUT_MD = ROOT / "outputs/craig_live_trading_video_inventory.md"
CURRENT_FLAT_JSON = ROOT / "data/source/craig_youtube/current_flat_list.json"


LIVE_TITLE_RE = re.compile(r"\blive\b", re.I)
TRADING_TITLE_RE = re.compile(r"(trading|trade)", re.I)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def yyyymmdd_to_iso(value: str) -> str:
    value = (value or "").strip()
    if not value or value == "NA":
        return ""
    if "-" in value:
        return value
    if len(value) == 8:
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return value


def is_live_trading_title(title: str) -> bool:
    return bool(LIVE_TITLE_RE.search(title or "") and TRADING_TITLE_RE.search(title or ""))


def refresh_current_flat(limit: int) -> list[dict[str, Any]]:
    try:
        from yt_dlp import YoutubeDL
    except Exception as exc:  # pragma: no cover - environment dependent
        print(f"yt_dlp unavailable: {exc}")
        return []

    opts = {
        "quiet": True,
        "ignoreerrors": True,
        "extract_flat": True,
        "playlistend": limit,
        "extractor_args": {"youtube": {"player_client": ["android"]}},
    }
    with YoutubeDL(opts) as ydl:
        playlist = ydl.extract_info("https://www.youtube.com/@craig_percoco/videos", download=False)
    entries = [entry for entry in (playlist or {}).get("entries", []) if entry]
    rows = []
    for idx, entry in enumerate(entries, 1):
        rows.append(
            {
                "playlist_index": idx,
                "id": entry.get("id"),
                "title": entry.get("title"),
                "url": entry.get("url") or entry.get("webpage_url") or f"https://www.youtube.com/watch?v={entry.get('id')}",
            }
        )
    CURRENT_FLAT_JSON.parent.mkdir(parents=True, exist_ok=True)
    CURRENT_FLAT_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return rows


def build_inventory(refresh_youtube: bool, playlist_limit: int) -> list[dict[str, Any]]:
    details = read_csv(DETAILS_CSV)
    labels = read_csv(LABELS_CSV)
    episodes = read_csv(EPISODES_CSV)
    user_dates = read_csv(USER_DATES_CSV)

    current_ids: set[str] = set()
    if refresh_youtube:
        current_ids = {row["id"] for row in refresh_current_flat(playlist_limit) if row.get("id")}
    elif CURRENT_FLAT_JSON.exists():
        current_ids = {row.get("id") for row in json.loads(CURRENT_FLAT_JSON.read_text(encoding="utf-8")) if row.get("id")}

    label_counts: dict[str, Counter[str]] = defaultdict(Counter)
    label_dirs: dict[str, Counter[str]] = defaultdict(Counter)
    for row in labels:
        vid = row.get("video_id", "")
        action = row.get("observed_action", "")
        direction = row.get("observed_direction", "")
        if vid and action:
            label_counts[vid][action] += 1
        if vid and direction and direction != "unknown":
            label_dirs[vid][direction] += 1

    verified_dates: dict[str, set[str]] = defaultdict(set)
    user_verified_dates: dict[str, str] = {}
    verified_episodes: dict[str, int] = defaultdict(int)
    for row in episodes:
        vid = row.get("video_id", "")
        market_date = row.get("market_date", "")
        if vid and market_date:
            verified_dates[vid].add(market_date)
            verified_episodes[vid] += 1
    for row in user_dates:
        vid = row.get("video_id", "")
        market_date = row.get("verified_market_date", "")
        if vid and market_date:
            user_verified_dates[vid] = market_date

    rows = []
    for detail in details:
        title = detail.get("title", "")
        if not is_live_trading_title(title):
            continue
        vid = detail.get("id", "")
        upload_iso = yyyymmdd_to_iso(detail.get("upload_date", ""))
        dates = sorted(verified_dates.get(vid, []))
        if dates:
            market_date = "|".join(dates)
            date_status = "verified_from_high_res_frame"
            compare_status = "scorable_event_level_if_episode_labeled"
        elif vid in user_verified_dates:
            market_date = user_verified_dates[vid]
            date_status = "user_verified_tradingview_bottom_axis"
            compare_status = "date_verified_needs_event_price_frame_review"
        else:
            market_date = upload_iso
            date_status = "upload_date_proxy_needs_frame_review"
            compare_status = "coarse_transcript_only_not_exact_comparison"

        transcript_txt = TRANSCRIPT_DIR / f"{vid}.txt"
        counts = label_counts.get(vid, Counter())
        dirs = label_dirs.get(vid, Counter())
        rows.append(
            {
                "playlist_index": detail.get("playlist_index", ""),
                "video_id": vid,
                "upload_date": upload_iso,
                "market_date_for_fetch": market_date,
                "market_date_status": date_status,
                "duration": detail.get("duration_string", ""),
                "title": title,
                "url": detail.get("url", "") or f"https://www.youtube.com/watch?v={vid}",
                "transcript_words": detail.get("transcript_words", ""),
                "transcript_available": "yes" if transcript_txt.exists() else "no",
                "observed_take_labels": counts.get("Take", 0),
                "observed_manage_labels": counts.get("Manage_BE_or_RiskReduce", 0),
                "observed_tp_close_labels": counts.get("Exit_TP_or_Close", 0),
                "observed_loss_labels": counts.get("Exit_Stop_or_Loss", 0),
                "observed_missed_labels": counts.get("Missed", 0),
                "observed_pass_labels": counts.get("Pass_or_Cooldown", 0),
                "observed_long_mentions": dirs.get("long", 0),
                "observed_short_mentions": dirs.get("short", 0),
                "verified_episode_rows": verified_episodes.get(vid, 0),
                "current_youtube_flat_seen": "yes" if not current_ids or vid in current_ids else "no",
                "comparison_status": compare_status,
                "next_required_work": "event/price frame review" if not dates else "episode price/management replay",
            }
        )

    rows.sort(key=lambda r: (r["upload_date"], r["playlist_index"]), reverse=True)
    return rows


def write_outputs(rows: list[dict[str, Any]]) -> None:
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "playlist_index",
        "video_id",
        "upload_date",
        "market_date_for_fetch",
        "market_date_status",
        "duration",
        "title",
        "url",
        "transcript_words",
        "transcript_available",
        "observed_take_labels",
        "observed_manage_labels",
        "observed_tp_close_labels",
        "observed_loss_labels",
        "observed_missed_labels",
        "observed_pass_labels",
        "observed_long_mentions",
        "observed_short_mentions",
        "verified_episode_rows",
        "current_youtube_flat_seen",
        "comparison_status",
        "next_required_work",
    ]
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    verified = sum(1 for r in rows if "verified" in r["market_date_status"])
    transcript = sum(1 for r in rows if r["transcript_available"] == "yes")
    take_labels = sum(int(r["observed_take_labels"]) for r in rows)
    scorable = sum(1 for r in rows if int(r["verified_episode_rows"]) > 0)

    lines = [
        "# Craig LIVE TRADING 영상 인벤토리",
        "",
        "이 파일은 Craig의 공개 YouTube LIVE 계열 영상을 비교 연구 대상으로 정리한 것이다.",
        "",
        "## 요약",
        "",
        f"- LIVE/TRADING 제목 기준 영상 수: {total}",
        f"- 자막 확보: {transcript}/{total}",
        f"- transcript Take 라벨: {take_labels}",
        f"- 실제 시장 날짜가 검증된 영상: {verified}/{total}",
        f"- episode 단위 비교가 가능한 영상: {scorable}/{total}",
        "",
        "주의: `market_date_status=upload_date_proxy_needs_frame_review`는 실제 거래일이 아니라 업로드일 proxy다. a7/C3에서 이미 업로드일과 거래일이 다르다는 것이 확인됐으므로, 이 행들은 정밀 일치성 평가에 쓰면 안 된다. `user_verified_tradingview_bottom_axis`는 사용자가 영상 하단 TradingView 날짜축으로 확인한 날짜다.",
        "",
        "## 영상 목록",
        "",
        "| upload | market_date | status | takes | episodes | title |",
        "|---|---|---|---:|---:|---|",
    ]
    for row in rows:
        title = str(row["title"]).replace("|", "/")
        lines.append(
            f"| {row['upload_date']} | {row['market_date_for_fetch']} | {row['market_date_status']} | "
            f"{row['observed_take_labels']} | {row['verified_episode_rows']} | [{title}]({row['url']}) |"
        )
    lines.extend(
        [
            "",
            "## 다음 검증 순서",
            "",
            "1. `observed_take_labels`가 많은 영상부터 프레임으로 실제 거래일과 심볼을 확정한다.",
            "2. 같은 영상 안에서 exit recap, fresh entry, runner management를 분리한다.",
            "3. entry/stop/target이 보이는 프레임만 price-level agreement에 승격한다.",
            "4. 그 뒤에만 Binance/Bybit 1분봉 replay 결과를 Craig 일치성으로 평가한다.",
        ]
    )
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-youtube", action="store_true")
    parser.add_argument("--playlist-limit", type=int, default=160)
    args = parser.parse_args()
    rows = build_inventory(args.refresh_youtube, args.playlist_limit)
    write_outputs(rows)
    print(f"live_videos={len(rows)} output={OUT_CSV}")


if __name__ == "__main__":
    main()
