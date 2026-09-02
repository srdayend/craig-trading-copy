#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs" / "position_box_detection"


@dataclass
class ColorBox:
    color_role: str
    x1: int
    y1: int
    x2: int
    y2: int
    area: int
    fill_ratio: float

    @property
    def width(self) -> int:
        return self.x2 - self.x1 + 1

    @property
    def height(self) -> int:
        return self.y2 - self.y1 + 1

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2


@dataclass
class PositionBoxCandidate:
    image: str
    direction_guess: str
    confidence: float
    entry_y: float
    stop_y: float
    target_y: float
    red_box: ColorBox
    profit_box: ColorBox
    chart_region: tuple[int, int, int, int]
    price_axis_ocr_status: str
    notes: str


def chart_crop_bounds(image: Image.Image) -> tuple[int, int, int, int]:
    w, h = image.size
    # Craig videos often show TradingView on the left and exchange/journal panels on the right.
    # Keep the chart canvas and exclude browser/player chrome.
    return (
        max(0, int(w * 0.02)),
        max(0, int(h * 0.06)),
        min(w - 1, int(w * 0.64)),
        min(h - 1, int(h * 0.92)),
    )


def color_masks(image: Image.Image, bounds: tuple[int, int, int, int]) -> dict[str, np.ndarray]:
    arr = np.asarray(image.convert("RGB")).astype(np.int16)
    x1, y1, x2, y2 = bounds
    crop = arr[y1 : y2 + 1, x1 : x2 + 1]
    r, g, b = crop[:, :, 0], crop[:, :, 1], crop[:, :, 2]
    bright = (r + g + b) / 3
    red = (r > 150) & (r > g + 12) & (r > b + 8) & (bright > 105)
    red |= (r > 185) & (g > 105) & (g < 215) & (b > 105) & (b < 215) & (r > g + 8)
    profit = ((g > 155) & (b > 130) & (r < 210) & (g > r + 12)) | (
        (g > 145) & (r < 170) & (b < 190) & (g > r + 20)
    )
    structure = np.ones((3, 5), dtype=bool)
    return {
        "red": ndimage.binary_closing(red, structure=structure),
        "profit": ndimage.binary_closing(profit, structure=structure),
    }


def components(mask: np.ndarray, color_role: str, bounds: tuple[int, int, int, int], image_size: tuple[int, int]) -> list[ColorBox]:
    labels, n = ndimage.label(mask)
    x_off, y_off, _, _ = bounds
    width, height = image_size
    min_area = max(80, int(width * height * 0.00045))
    out: list[ColorBox] = []
    for label in range(1, n + 1):
        ys, xs = np.where(labels == label)
        if len(xs) < min_area:
            continue
        x1, x2 = int(xs.min() + x_off), int(xs.max() + x_off)
        y1, y2 = int(ys.min() + y_off), int(ys.max() + y_off)
        box_area = max(1, (x2 - x1 + 1) * (y2 - y1 + 1))
        fill_ratio = len(xs) / box_area
        box = ColorBox(color_role, x1, y1, x2, y2, int(len(xs)), round(float(fill_ratio), 3))
        if box.width < max(18, width * 0.035) or box.height < max(6, height * 0.015):
            continue
        if box.fill_ratio < 0.10:
            continue
        out.append(box)
    return sorted(out, key=lambda b: b.area, reverse=True)


def overlap_ratio(a: ColorBox, b: ColorBox) -> float:
    overlap = max(0, min(a.x2, b.x2) - max(a.x1, b.x1) + 1)
    return overlap / max(1, min(a.width, b.width))


def pair_score(red: ColorBox, profit: ColorBox, image_size: tuple[int, int]) -> float:
    w, h = image_size
    x_overlap = overlap_ratio(red, profit)
    center_gap = abs(red.cx - profit.cx) / max(1, w)
    width_ratio = min(red.width, profit.width) / max(red.width, profit.width)
    vertical_gap = max(0, max(red.y1, profit.y1) - min(red.y2, profit.y2)) / max(1, h)
    area_bonus = min(1.0, (red.area + profit.area) / (w * h * 0.08))
    score = 0.42 * x_overlap + 0.22 * width_ratio + 0.18 * area_bonus + 0.18 * max(0.0, 1 - center_gap * 8)
    if vertical_gap > 0.05:
        score -= min(0.25, vertical_gap * 2)
    return round(max(0.0, min(1.0, score)), 3)


def build_candidate(image_path: Path, red: ColorBox, profit: ColorBox, bounds: tuple[int, int, int, int], score: float) -> PositionBoxCandidate:
    if profit.cy < red.cy:
        direction = "long"
        entry_y = (profit.y2 + red.y1) / 2
        stop_y = red.y2
        target_y = profit.y1
    else:
        direction = "short"
        entry_y = (red.y2 + profit.y1) / 2
        stop_y = red.y1
        target_y = profit.y2
    notes = "색상/기하 기반 후보다. 가격 확정에는 price-axis OCR 또는 수동 검증이 필요하다."
    return PositionBoxCandidate(
        image=str(image_path),
        direction_guess=direction,
        confidence=score,
        entry_y=round(entry_y, 2),
        stop_y=round(float(stop_y), 2),
        target_y=round(float(target_y), 2),
        red_box=red,
        profit_box=profit,
        chart_region=bounds,
        price_axis_ocr_status="not_run_optional_easyocr_or_paddleocr",
        notes=notes,
    )


def detect_position_boxes(image_path: Path) -> list[PositionBoxCandidate]:
    image = Image.open(image_path).convert("RGB")
    bounds = chart_crop_bounds(image)
    masks = color_masks(image, bounds)
    reds = components(masks["red"], "stop_loss_red", bounds, image.size)
    profits = components(masks["profit"], "profit_blue_green", bounds, image.size)
    candidates: list[PositionBoxCandidate] = []
    for red in reds[:12]:
        for profit in profits[:12]:
            score = pair_score(red, profit, image.size)
            if score < 0.45:
                continue
            candidates.append(build_candidate(image_path, red, profit, bounds, score))
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return candidates[:5]


def annotate(image_path: Path, candidates: list[PositionBoxCandidate], output_path: Path) -> None:
    image = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(image)
    colors = ["yellow", "lime", "cyan", "orange", "white"]
    for idx, candidate in enumerate(candidates):
        color = colors[idx % len(colors)]
        rb = candidate.red_box
        pb = candidate.profit_box
        draw.rectangle([rb.x1, rb.y1, rb.x2, rb.y2], outline="red", width=3)
        draw.rectangle([pb.x1, pb.y1, pb.x2, pb.y2], outline="cyan", width=3)
        x1, _, x2, _ = candidate.chart_region
        draw.line([x1, candidate.entry_y, x2, candidate.entry_y], fill=color, width=2)
        draw.line([x1, candidate.stop_y, x2, candidate.stop_y], fill="red", width=2)
        draw.line([x1, candidate.target_y, x2, candidate.target_y], fill="cyan", width=2)
        draw.text(
            (max(rb.x1, pb.x1), min(rb.y1, pb.y1) - 14),
            f"{candidate.direction_guess} conf={candidate.confidence:.2f}",
            fill=color,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def flatten(candidate: PositionBoxCandidate) -> dict[str, str | float]:
    row = {
        "image": candidate.image,
        "direction_guess": candidate.direction_guess,
        "confidence": candidate.confidence,
        "entry_y": candidate.entry_y,
        "stop_y": candidate.stop_y,
        "target_y": candidate.target_y,
        "chart_region": json.dumps(candidate.chart_region),
        "price_axis_ocr_status": candidate.price_axis_ocr_status,
        "notes": candidate.notes,
    }
    for prefix, box in [("red", candidate.red_box), ("profit", candidate.profit_box)]:
        for key, value in asdict(box).items():
            row[f"{prefix}_{key}"] = value
    return row


def write_outputs(image_paths: list[Path], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str | float]] = []
    summary = []
    for image_path in image_paths:
        candidates = detect_position_boxes(image_path)
        rows.extend(flatten(c) for c in candidates)
        annotated = output_dir / f"{image_path.stem}_position_box_annotated.jpg"
        annotate(image_path, candidates, annotated)
        summary.append(
            {
                "image": str(image_path),
                "candidate_count": len(candidates),
                "best_direction": candidates[0].direction_guess if candidates else "",
                "best_confidence": candidates[0].confidence if candidates else 0.0,
                "annotated": str(annotated),
            }
        )

    csv_path = output_dir / "position_box_candidates.csv"
    if rows:
        with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    else:
        csv_path.write_text("", encoding="utf-8")

    summary_path = output_dir / "position_box_detection_summary.md"
    lines = [
        "# Position Box Detection Probe",
        "",
        "이 결과는 색상/기하 기반 1차 후보이며, 아직 가격축 OCR로 entry/SL/TP 가격을 확정한 결과가 아니다.",
        "",
        "| image | 후보 수 | best 방향 | best confidence | annotated |",
        "|---|---:|---|---:|---|",
    ]
    for item in summary:
        lines.append(
            f"| `{Path(item['image']).name}` | {item['candidate_count']} | `{item['best_direction']}` | "
            f"{float(item['best_confidence']):.3f} | `{Path(item['annotated']).name}` |"
        )
    lines.extend(
        [
            "",
            "## 판단",
            "",
            "- 0.70 이상이면 box 후보 자체는 꽤 그럴듯하지만, 가격은 아직 확정하지 않는다.",
            "- 0.45-0.70은 사람이 annotated 이미지를 보고 승인해야 한다.",
            "- 0.45 미만은 자동 후보에서 제외한다.",
            "- 다음 단계는 EasyOCR/PaddleOCR로 우측 가격축 숫자를 읽고 y좌표와 가격을 선형 매핑하는 것이다.",
        ]
    )
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"images={len(image_paths)} rows={len(rows)} output={csv_path}")
    print(f"summary={summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("images", nargs="+", help="Frame image paths")
    parser.add_argument("--output-dir", default=str(OUT_DIR), help="Directory for CSV and annotated frames")
    args = parser.parse_args()
    write_outputs([Path(p) for p in args.images], Path(args.output_dir))


if __name__ == "__main__":
    main()
