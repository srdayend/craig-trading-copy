from __future__ import annotations

import csv
import re
from pathlib import Path

IDS = [
    "NvK0bj-2MiA",
    "yEyoTXmvDWY",
    "2Sn-yI9eL9M",
    "spSY9ExzUuY",
    "o1S_w9o34Ao",
    "tUEQDc56pKE",
    "1zmixRfB8co",
]

path = Path("data/processed/gold_context_trades/remaining_context_queue_v0_2.csv")
with path.open(encoding="utf-8-sig", newline="") as f:
    rows = [r for r in csv.DictReader(f) if r["video_id"] in IDS]

for vid in IDS:
    print("\n###", vid)
    for row in rows:
        if row["video_id"] != vid:
            continue
        excerpt = re.sub(r"\s+", " ", row["candidate_transcript_excerpt_auto"]).strip()[:700]
        print(
            row["candidate_id"],
            row["youtube_window"],
            "anchor",
            row["youtube_anchor_sec"],
            "sym",
            row["symbol"],
            "dir",
            row["direction"],
            "status",
            row["evidence_status"],
        )
        print(" ", excerpt)
