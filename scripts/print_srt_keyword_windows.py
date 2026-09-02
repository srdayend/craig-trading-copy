from __future__ import annotations

import re
from pathlib import Path


VIDEO_TITLES = {
    "NvK0bj-2MiA": "Live Day Trading (THIS TRADE WAS INSANE)",
    "yEyoTXmvDWY": "Day In The Life Of A 28 Year Old Millionaire Day Trader In NYC",
    "2Sn-yI9eL9M": "LIVE DAY TRADING - (PULLED OUT A WIN)",
    "spSY9ExzUuY": "LIVE TRADING CRYPTO - Making $11,725 Profit Risking $1k",
    "o1S_w9o34Ao": "LIVE TRADING CRYPTO - Making $7,806 [I Went Crazy]",
    "tUEQDc56pKE": "Day In The Life Of A Millionaire 28 Year Old Day Trader In NYC",
    "1zmixRfB8co": "LIVE TRADING CRYPTO - Losing $2,428 In A Day Risking $1k",
}

KEYWORDS = re.compile(
    r"trade number|position number|trade one|trade two|trade three|trade four|trade five|trade six|trade seven|"
    r"break even|stop-loss|stop loss|stopped out|loss|profit|take profit|take.*off|fully out|journal|"
    r"fair value gap|change of character|elliot|elliott|wave|61\\.8|2\\.618|3\\.618|4\\.618|"
    r"daily bias|bias|bitcoin|solana|ethereum|new york|9:30",
    re.I,
)


def parse_time(t: str) -> float:
    h, m, rest = t.split(":")
    s, ms = rest.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def stamp(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def parse_srt(path: Path) -> list[tuple[float, str]]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    blocks = re.split(r"\n\s*\n", text.strip())
    cues = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if len(lines) < 3:
            continue
        time_line = next((ln for ln in lines if "-->" in ln), "")
        if not time_line:
            continue
        start = parse_time(time_line.split("-->")[0].strip())
        body = " ".join(ln for ln in lines if "-->" not in ln and not ln.isdigit())
        cues.append((start, body))
    return cues


def print_window(cues: list[tuple[float, str]], idx: int, seen: set[int]) -> None:
    if idx in seen:
        return
    seen.add(idx)
    start = max(0, idx - 5)
    end = min(len(cues), idx + 8)
    print(f"\n-- {stamp(cues[start][0])}-{stamp(cues[end-1][0])} --")
    for sec, body in cues[start:end]:
        print(f"{stamp(sec)} {body}")


for vid, title in VIDEO_TITLES.items():
    path = Path("video source") / f"{title}.en.srt"
    cues = parse_srt(path)
    print("\n###", vid, title)
    seen: set[int] = set()
    for idx, (_, body) in enumerate(cues):
        if KEYWORDS.search(body):
            print_window(cues, idx, seen)
