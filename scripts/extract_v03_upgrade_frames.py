from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(".codex_local_deps/python").resolve()))

from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg


ROOT = Path(__file__).resolve().parents[1]
VIDEO_DIR = ROOT / "video source"
PROCESSED = ROOT / "data" / "processed" / "gold_context_trades"
DETAILS = ROOT / "data" / "source" / "craig_youtube" / "details.csv"
OUT = ROOT / "data" / "source" / "craig_frames" / "local_v03_upgrade"

UPGRADE_IDS = {
    "KXIF1Ll5Exg",
    "wm4tmXgKlz8",
    "Ifc1VzcNlCg",
    "pA7rzimO9y4",
    "bDgZhBFm1mU",
    "XlnvwMIRByQ",
    "nfRXDRJooyg",
    "iYpYWnkUyVI",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def norm_title(value: str) -> str:
    value = value.lower().replace("’", "'")
    return re.sub(r"\s+", " ", value).strip()


def time_to_sec(value: str) -> int | None:
    value = value.strip()
    parts = value.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return None


def sec_to_stamp(sec: int) -> str:
    return f"{sec // 60:02d}m{sec % 60:02d}s"


def find_times(*texts: str) -> list[int]:
    out = []
    for text in texts:
        if not text:
            continue
        for m in re.finditer(r"(?<!\d)(\d{1,2}:\d{2})(?!\d)", text):
            sec = time_to_sec(m.group(1))
            if sec is not None:
                out.append(sec)
        for m in re.finditer(r"(?<!\d)(\d{1,2}:\d{2})-(\d{1,2}:\d{2})(?!\d)", text):
            a = time_to_sec(m.group(1))
            b = time_to_sec(m.group(2))
            if a is not None:
                out.append(a)
            if b is not None:
                out.append(b)
            if a is not None and b is not None and b > a:
                out.append((a + b) // 2)
    return out


def details_maps() -> tuple[dict[str, dict[str, str]], dict[str, Path]]:
    details = read_csv(DETAILS)
    by_id = {r["id"]: r for r in details if r.get("id")}
    videos = {norm_title(p.stem): p for p in VIDEO_DIR.glob("*.mp4")}
    by_id_path = {}
    for vid, row in by_id.items():
        path = videos.get(norm_title(row.get("title", "")))
        if path:
            by_id_path[vid] = path
    return by_id, by_id_path


def add_frame(plan: dict[str, dict[int, set[str]]], video_id: str, sec: int, label: str) -> None:
    if video_id not in UPGRADE_IDS:
        return
    if sec < 0:
        return
    plan[video_id][sec].add(label[:80])


def build_plan() -> dict[str, dict[int, set[str]]]:
    plan: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))

    for row in read_csv(PROCESSED / "manual_seed_contexts.csv"):
        vid = row.get("video_id", "")
        if vid not in UPGRADE_IDS:
            continue
        tid = row.get("trade_id", "manual")
        texts = [
            row.get("youtube_anchor", ""),
            row.get("source_anchors_ko", ""),
            row.get("original_notes_ko", ""),
        ]
        for sec in find_times(*texts):
            add_frame(plan, vid, sec, tid)
        for sec in find_times(row.get("youtube_anchor", "")):
            add_frame(plan, vid, sec + 30, f"{tid}_plus30")

    for row in read_csv(PROCESSED / "context_review_queue.csv"):
        vid = row.get("video_id", "")
        cid = row.get("candidate_id", "bdg")
        texts = [
            row.get("youtube_window", ""),
            row.get("source_anchors_ko", ""),
            row.get("context_summary_ko", ""),
            row.get("setup_summary_ko", ""),
        ]
        for sec in find_times(*texts):
            add_frame(plan, vid, sec, cid)

    for row in read_csv(PROCESSED / "pilot_3_context_review.csv"):
        vid = row.get("video_id", "")
        cid = row.get("candidate_id", "pilot3")
        texts = [
            row.get("youtube_window", ""),
            row.get("source_anchors_ko", ""),
            row.get("transcript_context_ko", ""),
            row.get("chart_understanding_ko", ""),
        ]
        for sec in find_times(*texts):
            add_frame(plan, vid, sec, cid)

    # Add early context frames for the session-level macro/HFT pass.
    for vid in UPGRADE_IDS:
        for sec in (60, 180, 300):
            add_frame(plan, vid, sec, "session_macro_scan")

    return plan


def extract_frame(ffmpeg: str, video_path: Path, sec: int, out_path: Path) -> bool:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        str(sec),
        "-i",
        str(video_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        "-y",
        str(out_path),
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return proc.returncode == 0 and out_path.exists() and out_path.stat().st_size > 1000


def build_contact_sheet(video_id: str, frames: list[dict[str, str]]) -> str:
    if not frames:
        return ""
    thumbs = []
    thumb_w = 560
    pad = 14
    label_h = 44
    for frame in frames:
        img = Image.open(ROOT / frame["path"]).convert("RGB")
        scale = thumb_w / img.width
        thumb_h = int(img.height * scale)
        img = img.resize((thumb_w, thumb_h))
        canvas = Image.new("RGB", (thumb_w, thumb_h + label_h), "white")
        canvas.paste(img, (0, label_h))
        draw = ImageDraw.Draw(canvas)
        draw.rectangle([0, 0, thumb_w, label_h], fill=(18, 52, 59))
        label = f"{frame['stamp']} | {frame['labels']}"
        draw.text((8, 8), label[:95], fill="white")
        thumbs.append(canvas)
    cols = 2
    rows = (len(thumbs) + cols - 1) // cols
    cell_w = thumb_w + pad
    cell_h = max(t.height for t in thumbs) + pad
    sheet = Image.new("RGB", (cols * cell_w + pad, rows * cell_h + pad), (238, 242, 245))
    for idx, thumb in enumerate(thumbs):
        x = pad + (idx % cols) * cell_w
        y = pad + (idx // cols) * cell_h
        sheet.paste(thumb, (x, y))
    out_path = OUT / video_id / f"{video_id}_local_v03_contact_sheet.jpg"
    sheet.save(out_path, quality=88)
    return str(out_path.relative_to(ROOT))


def main() -> None:
    _, paths = details_maps()
    plan = build_plan()
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    manifest: dict[str, list[dict[str, str]]] = {}

    for vid in sorted(UPGRADE_IDS):
        video_path = paths.get(vid)
        if not video_path:
            manifest[vid] = []
            continue
        frames = []
        for idx, sec in enumerate(sorted(plan.get(vid, {}))):
            labels = ",".join(sorted(plan[vid][sec]))
            safe_labels = re.sub(r"[^A-Za-z0-9가-힣_-]+", "_", labels)[:55].strip("_")
            name = f"{idx + 1:03d}_{sec_to_stamp(sec)}_{safe_labels or 'frame'}.png"
            out_path = OUT / vid / name
            ok = extract_frame(ffmpeg, video_path, sec, out_path)
            if ok:
                frames.append(
                    {
                        "video_id": vid,
                        "second": sec,
                        "stamp": sec_to_stamp(sec),
                        "labels": labels,
                        "path": str(out_path.relative_to(ROOT)),
                    }
                )
        contact = build_contact_sheet(vid, frames)
        if contact:
            frames.insert(0, {"video_id": vid, "second": "", "stamp": "contact", "labels": "", "path": contact})
        manifest[vid] = frames

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "local_v03_frame_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(OUT / "local_v03_frame_manifest.json")
    for vid, frames in manifest.items():
        print(vid, max(len(frames) - 1, 0), "frames")


if __name__ == "__main__":
    main()
