#!/usr/bin/env python3
"""
Draw 3x3 spatial grid overlay on a keyframe image.

Divides image into 9 regions matching the instruction.md grid:
  top-left    | top-center    | top-right
  mid-left    | mid-center    | mid-right
  bottom-left | bottom-center | bottom-right

Usage:
  python -m task.draw_grid_overlay INPUT_IMAGE [--out OUTPUT_PATH]
"""

import argparse
import os
import cv2
import numpy as np


GRID_LABELS = [
    ["top-left", "top-center", "top-right"],
    ["mid-left", "mid-center", "mid-right"],
    ["bottom-left", "bottom-center", "bottom-right"],
]


def draw_grid(image_path: str, output_path: str) -> str:
    """Draw 3x3 grid with labels on image.

    Args:
        image_path: Path to input image
        output_path: Path to save annotated image

    Returns:
        Path to saved image
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")

    h, w = img.shape[:2]

    # Create overlay for semi-transparent grid
    overlay = img.copy()

    # Grid line positions
    x1 = w // 3
    x2 = 2 * w // 3
    y1 = h // 3
    y2 = 2 * h // 3

    line_color = (0, 255, 255)  # yellow
    line_thickness = 3

    # Draw vertical lines
    cv2.line(overlay, (x1, 0), (x1, h), line_color, line_thickness)
    cv2.line(overlay, (x2, 0), (x2, h), line_color, line_thickness)

    # Draw horizontal lines
    cv2.line(overlay, (0, y1), (w, y1), line_color, line_thickness)
    cv2.line(overlay, (0, y2), (w, y2), line_color, line_thickness)

    # Draw labels
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.8
    font_thickness = 2
    label_color = (0, 255, 255)  # yellow
    bg_color = (0, 0, 0)  # black background for readability

    cell_centers = [
        [(x1 // 2, y1 // 2), (x1 + (x2 - x1) // 2, y1 // 2), (x2 + (w - x2) // 2, y1 // 2)],
        [(x1 // 2, y1 + (y2 - y1) // 2), (x1 + (x2 - x1) // 2, y1 + (y2 - y1) // 2), (x2 + (w - x2) // 2, y1 + (y2 - y1) // 2)],
        [(x1 // 2, y2 + (h - y2) // 2), (x1 + (x2 - x1) // 2, y2 + (h - y2) // 2), (x2 + (w - x2) // 2, y2 + (h - y2) // 2)],
    ]

    for row in range(3):
        for col in range(3):
            label = GRID_LABELS[row][col]
            cx, cy = cell_centers[row][col]

            # Get text size for background rectangle
            (tw, th), baseline = cv2.getTextSize(label, font, font_scale, font_thickness)
            tx = cx - tw // 2
            ty = cy + th // 2

            # Draw black background rectangle
            padding = 6
            cv2.rectangle(
                overlay,
                (tx - padding, ty - th - padding),
                (tx + tw + padding, ty + baseline + padding),
                bg_color,
                -1,  # filled
            )

            # Draw label text
            cv2.putText(overlay, label, (tx, ty), font, font_scale, label_color, font_thickness)

    # Blend overlay with original (0.7 original + 0.3 overlay for subtle effect)
    result = cv2.addWeighted(img, 0.6, overlay, 0.4, 0)

    # Re-draw lines and labels on blended result for full opacity
    cv2.line(result, (x1, 0), (x1, h), line_color, line_thickness)
    cv2.line(result, (x2, 0), (x2, h), line_color, line_thickness)
    cv2.line(result, (0, y1), (w, y1), line_color, line_thickness)
    cv2.line(result, (0, y2), (w, y2), line_color, line_thickness)

    for row in range(3):
        for col in range(3):
            label = GRID_LABELS[row][col]
            cx, cy = cell_centers[row][col]
            (tw, th), baseline = cv2.getTextSize(label, font, font_scale, font_thickness)
            tx = cx - tw // 2
            ty = cy + th // 2
            padding = 6
            cv2.rectangle(
                result,
                (tx - padding, ty - th - padding),
                (tx + tw + padding, ty + baseline + padding),
                bg_color,
                -1,
            )
            cv2.putText(result, label, (tx, ty), font, font_scale, label_color, font_thickness)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    cv2.imwrite(output_path, result, [cv2.IMWRITE_JPEG_QUALITY, 95])
    print(f"[grid] Saved {output_path} ({w}x{h})")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Draw 3x3 grid overlay on keyframe")
    parser.add_argument("image", help="Input image path")
    parser.add_argument("--out", type=str, default=None,
                        help="Output path (default: <input>_grid.jpg)")
    args = parser.parse_args()

    if args.out is None:
        base, ext = os.path.splitext(args.image)
        args.out = f"{base}_grid{ext}"

    draw_grid(args.image, args.out)


if __name__ == "__main__":
    main()
