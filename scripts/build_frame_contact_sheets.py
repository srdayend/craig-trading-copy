from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def load_font(size: int) -> ImageFont.ImageFont:
    for name in ("arial.ttf", "seguiemj.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("frame_dir")
    parser.add_argument("--cols", type=int, default=3)
    parser.add_argument("--thumb-width", type=int, default=560)
    args = parser.parse_args()

    frame_dir = Path(args.frame_dir)
    manifest_path = frame_dir / "capture_manifest.json"
    rows = json.loads(manifest_path.read_text(encoding="utf-8"))
    font = load_font(18)
    label_font = load_font(16)
    padding = 12
    label_h = 72

    thumbs: list[tuple[Image.Image, str]] = []
    for row in rows:
        img = Image.open(row["path"]).convert("RGB")
        scale = args.thumb_width / img.width
        thumb = img.resize((args.thumb_width, int(img.height * scale)), Image.LANCZOS)
        req = int(row.get("requested_sec", row.get("targetSec", 0)))
        actual = int(float(row.get("actual_sec", row.get("currentTime", req))))
        raw_label = row.get("label") or Path(row["path"]).stem
        label = f"{req//60:02d}:{req%60:02d} -> {actual//60:02d}:{actual%60:02d}  {raw_label}"
        thumbs.append((thumb, label))

    cols = args.cols
    rows_n = (len(thumbs) + cols - 1) // cols
    cell_w = args.thumb_width + padding * 2
    cell_h = max(t.height for t, _ in thumbs) + label_h + padding * 2
    sheet = Image.new("RGB", (cell_w * cols, cell_h * rows_n), "white")
    draw = ImageDraw.Draw(sheet)

    for idx, (thumb, label) in enumerate(thumbs):
        x = (idx % cols) * cell_w + padding
        y = (idx // cols) * cell_h + padding
        sheet.paste(thumb, (x, y))
        wrapped = "\n".join(textwrap.wrap(label, width=54)[:3])
        draw.text((x, y + thumb.height + 8), wrapped, fill=(20, 20, 20), font=label_font)
        draw.rectangle((x, y, x + thumb.width - 1, y + thumb.height - 1), outline=(160, 160, 160), width=1)

    title = frame_dir.name
    draw.rectangle((0, 0, sheet.width, 30), fill=(245, 245, 245))
    draw.text((padding, 5), title, fill=(0, 0, 0), font=font)
    out = frame_dir / f"{frame_dir.name}_contact_sheet.jpg"
    sheet.save(out, quality=92)
    print(out)


if __name__ == "__main__":
    main()
