from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


KEYWORDS = re.compile(
    r"\b("
    r"trade|trades|long|short|entry|entries|stop|stopped|loss|losing|profit|"
    r"take profit|tp|target|risk|break even|breakeven|choch|change|fvg|"
    r"fair value|gap|support|resistance|recap|overall|position|order|filled|"
    r"fill|cancel|missed|looking|wait|waiting|liquidity|trend|retest|level"
    r")\b",
    re.IGNORECASE,
)


def fmt_time(seconds: float) -> str:
    seconds_i = int(seconds)
    return f"{seconds_i // 60:02d}:{seconds_i % 60:02d}"


def load_transcript(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def cluster_hits(rows: list[dict], max_gap: float) -> list[list[dict]]:
    clusters: list[list[dict]] = []
    for row in rows:
        text = row["text"].replace("\n", " ")
        if not KEYWORDS.search(text):
            continue
        if not clusters or row["start"] - clusters[-1][-1]["start"] > max_gap:
            clusters.append([])
        clusters[-1].append({"start": row["start"], "text": text})
    return clusters


def window_text(rows: list[dict], start: float, end: float) -> str:
    selected = [
        f"{fmt_time(row['start'])} {row['text'].replace(chr(10), ' ')}"
        for row in rows
        if start <= row["start"] <= end
    ]
    return "\n".join(selected)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--videos", nargs="+", required=True)
    parser.add_argument("--transcript-dir", default="data/source/craig_youtube/transcripts")
    parser.add_argument("--out", default="")
    parser.add_argument("--max-gap", type=float, default=50.0)
    parser.add_argument("--pad", type=float, default=35.0)
    args = parser.parse_args()

    base = Path(args.transcript_dir)
    lines: list[str] = []
    for video_id in args.videos:
        rows = load_transcript(base / f"{video_id}.json")
        clusters = cluster_hits(rows, args.max_gap)
        lines.append(f"# {video_id}")
        for idx, cluster in enumerate(clusters, 1):
            start = max(0, cluster[0]["start"] - args.pad)
            end = cluster[-1]["start"] + args.pad
            preview = " ".join(item["text"] for item in cluster[:10])
            if len(preview) > 700:
                preview = preview[:700] + "..."
            lines.append("")
            lines.append(
                f"## C{idx:02d} {fmt_time(cluster[0]['start'])}-{fmt_time(cluster[-1]['start'])} "
                f"hits={len(cluster)} review_window={fmt_time(start)}-{fmt_time(end)}"
            )
            lines.append(preview)
            lines.append("")
            lines.append("```")
            lines.append(window_text(rows, start, end))
            lines.append("```")
        lines.append("")

    text = "\n".join(lines).rstrip() + "\n"
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
