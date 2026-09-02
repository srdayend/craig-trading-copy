from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_time(value: str) -> float:
    parts = value.split(":")
    if len(parts) == 1:
        return float(parts[0])
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    raise ValueError(f"Unsupported time value: {value}")


def fmt_time(seconds: float) -> str:
    seconds_i = int(seconds)
    return f"{seconds_i // 60:02d}:{seconds_i % 60:02d}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video_id")
    parser.add_argument("start")
    parser.add_argument("end")
    parser.add_argument("--transcript-dir", default="data/source/craig_youtube/transcripts")
    args = parser.parse_args()

    start = parse_time(args.start)
    end = parse_time(args.end)
    path = Path(args.transcript_dir) / f"{args.video_id}.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    for row in rows:
        if start <= row["start"] <= end:
            text = row["text"].replace("\n", " ")
            print(f"{fmt_time(row['start'])} {text}")


if __name__ == "__main__":
    main()
