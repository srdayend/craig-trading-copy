from __future__ import annotations

import csv
import json
import re
import argparse
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(".codex_local_deps/python").resolve()))

from PIL import Image, ImageDraw
import imageio_ffmpeg


ROOT = Path(__file__).resolve().parents[1]
VIDEO_DIR = ROOT / "video source"
DETAILS = ROOT / "data" / "source" / "craig_youtube" / "details.csv"
PROCESSED = ROOT / "data" / "processed" / "gold_context_trades"
DEFAULT_OUT_NAME = "local_v03_batch_01"
OUT = ROOT / "data" / "source" / "craig_frames" / DEFAULT_OUT_NAME

DEFAULT_BATCH_IDS = [
    "NvK0bj-2MiA",
    "yEyoTXmvDWY",
    "2Sn-yI9eL9M",
    "spSY9ExzUuY",
    "o1S_w9o34Ao",
    "tUEQDc56pKE",
    "1zmixRfB8co",
]
BATCH_IDS = DEFAULT_BATCH_IDS


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def norm_title(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower().replace("’", "'")).strip()


def sec_to_stamp(sec: int) -> str:
    return f"{sec // 60:02d}m{sec % 60:02d}s"


def details_paths() -> tuple[dict[str, dict[str, str]], dict[str, Path]]:
    details = {r["id"]: r for r in read_csv(DETAILS) if r.get("id")}
    local = {norm_title(p.stem): p for p in VIDEO_DIR.glob("*.mp4")}
    paths = {}
    for vid, row in details.items():
        p = local.get(norm_title(row.get("title", "")))
        if p:
            paths[vid] = p
    return details, paths


def add(plan: dict[str, dict[int, set[str]]], vid: str, sec: int, label: str) -> None:
    if vid not in BATCH_IDS or sec < 0:
        return
    plan[vid][sec].add(label[:80])


def build_plan() -> dict[str, dict[int, set[str]]]:
    plan: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    capture = read_csv(PROCESSED / "remaining_frame_capture_plan_v0_2.csv")
    for vid in BATCH_IDS:
        for sec in (60, 180, 300):
            add(plan, vid, sec, "session_macro_scan")
    for row in capture:
        vid = row.get("video_id", "")
        if vid not in BATCH_IDS:
            continue
        cid = row.get("candidate_id", "candidate")
        for value in row.get("suggested_capture_secs", "").split("|"):
            if value.strip().isdigit():
                add(plan, vid, int(value.strip()), cid)
    return plan


def extract(ffmpeg: str, video: Path, sec: int, out: Path) -> bool:
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        str(sec),
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        "-y",
        str(out),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc.returncode == 0 and out.exists() and out.stat().st_size > 1000


def contact_sheet(vid: str, frames: list[dict[str, str]]) -> list[str]:
    if not frames:
        return []
    thumb_w = 500
    label_h = 42
    pad = 14
    contacts = []
    chunk_size = 24
    for chunk_idx in range(0, len(frames), chunk_size):
        chunk = frames[chunk_idx : chunk_idx + chunk_size]
        thumbs = []
        for frame in chunk:
            img = Image.open(ROOT / frame["path"]).convert("RGB")
            scale = thumb_w / img.width
            img = img.resize((thumb_w, int(img.height * scale)))
            canvas = Image.new("RGB", (img.width, img.height + label_h), "white")
            draw = ImageDraw.Draw(canvas)
            draw.rectangle([0, 0, canvas.width, label_h], fill=(18, 52, 59))
            draw.text((8, 8), f"{frame['stamp']} | {frame['labels']}"[:95], fill="white")
            canvas.paste(img, (0, label_h))
            thumbs.append(canvas)
        cols = 2
        rows = (len(thumbs) + cols - 1) // cols
        cell_w = thumb_w + pad
        cell_h = max(t.height for t in thumbs) + pad
        sheet = Image.new("RGB", (cols * cell_w + pad, rows * cell_h + pad), (238, 242, 245))
        for idx, thumb in enumerate(thumbs):
            sheet.paste(thumb, (pad + (idx % cols) * cell_w, pad + (idx // cols) * cell_h))
        out = OUT / vid / f"{vid}_{OUT.name}_contact_sheet_{chunk_idx // chunk_size + 1:02d}.jpg"
        sheet.save(out, quality=88)
        contacts.append(str(out.relative_to(ROOT)))
    return contacts


def main() -> None:
    global BATCH_IDS, OUT
    parser = argparse.ArgumentParser()
    parser.add_argument("--ids", nargs="+", default=DEFAULT_BATCH_IDS)
    parser.add_argument("--ids-csv", default="")
    parser.add_argument("--out-name", default=DEFAULT_OUT_NAME)
    parser.add_argument("--max-frames", type=int, default=36)
    args = parser.parse_args()
    BATCH_IDS = [part.strip() for part in args.ids_csv.split(",") if part.strip()] or args.ids
    OUT = ROOT / "data" / "source" / "craig_frames" / args.out_name

    _, paths = details_paths()
    plan = build_plan()
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    manifest = {}
    for vid in BATCH_IDS:
        video = paths.get(vid)
        frames = []
        if not video:
            manifest[vid] = frames
            continue
        limited_secs = sorted(plan[vid])
        if len(limited_secs) > args.max_frames:
            step = len(limited_secs) / args.max_frames
            picked = []
            for i in range(args.max_frames):
                picked.append(limited_secs[int(i * step)])
            limited_secs = sorted(set(picked))
        for idx, sec in enumerate(limited_secs):
            labels = ",".join(sorted(plan[vid][sec]))
            safe = re.sub(r"[^A-Za-z0-9가-힣_-]+", "_", labels)[:70].strip("_") or "frame"
            path = OUT / vid / f"{idx + 1:03d}_{sec_to_stamp(sec)}_{safe}.png"
            if extract(ffmpeg, video, sec, path):
                frames.append(
                    {
                        "video_id": vid,
                        "second": sec,
                        "stamp": sec_to_stamp(sec),
                        "labels": labels,
                        "path": str(path.relative_to(ROOT)),
                    }
                )
        contacts = contact_sheet(vid, frames)
        for contact in reversed(contacts):
            frames.insert(0, {"video_id": vid, "second": "", "stamp": "contact", "labels": "", "path": contact})
        manifest[vid] = frames
        print(vid, max(len(frames) - 1, 0), "frames")
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / f"{args.out_name}_frame_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(manifest_path)


if __name__ == "__main__":
    main()
