#!/usr/bin/env python3
"""
Tool: Image Cropping

Crop regions from images by pixel coordinates or 3x3 grid cell.

Usage:
  # By coordinates (x, y, width, height)
  python -m preprocess.tools.img_crop IMAGE --coords 100,200,500,300 --out cropped.jpg

  # By grid cell (row, col in 3x3 grid, 0-indexed)
  python -m preprocess.tools.img_crop IMAGE --grid 0,0 --out top_left.jpg

  # By horizontal split (divide into N equal columns)
  python -m preprocess.tools.img_crop IMAGE --hsplit 3 --out-dir crops/
"""

import argparse
import os
from PIL import Image
from typing import List, Tuple


def crop_by_coords(
    image_path: str,
    x: int, y: int, w: int, h: int,
    output_path: str,
) -> str:
    """Crop image by pixel coordinates.

    Args:
        image_path: Input image path
        x, y: Top-left corner
        w, h: Width and height
        output_path: Output path

    Returns:
        Saved path
    """
    img = Image.open(image_path)
    cropped = img.crop((x, y, x + w, y + h))
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    cropped.save(output_path, quality=95)
    print(f"  [crop] {image_path} -> {output_path} (coords {x},{y},{w},{h})")
    return output_path


def crop_by_grid(
    image_path: str,
    row: int, col: int,
    output_path: str,
    grid_rows: int = 3,
    grid_cols: int = 3,
) -> str:
    """Crop image by grid cell position.

    Args:
        image_path: Input image path
        row, col: Grid cell (0-indexed)
        output_path: Output path
        grid_rows, grid_cols: Grid dimensions (default 3x3)

    Returns:
        Saved path
    """
    img = Image.open(image_path)
    img_w, img_h = img.size
    cell_w = img_w // grid_cols
    cell_h = img_h // grid_rows

    x = col * cell_w
    y = row * cell_h
    w = cell_w if col < grid_cols - 1 else img_w - x
    h = cell_h if row < grid_rows - 1 else img_h - y

    return crop_by_coords(image_path, x, y, w, h, output_path)


def crop_horizontal_split(
    image_path: str,
    n_splits: int,
    out_dir: str,
    prefix: str = "split",
) -> List[str]:
    """Split image into N equal horizontal segments.

    Args:
        image_path: Input image path
        n_splits: Number of horizontal divisions
        out_dir: Output directory
        prefix: Filename prefix

    Returns:
        List of saved paths
    """
    img = Image.open(image_path)
    img_w, img_h = img.size
    segment_w = img_w // n_splits

    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for i in range(n_splits):
        x = i * segment_w
        w = segment_w if i < n_splits - 1 else img_w - x
        cropped = img.crop((x, 0, x + w, img_h))
        fname = f"{prefix}_{i}.png"
        fpath = os.path.join(out_dir, fname)
        cropped.save(fpath, quality=95)
        paths.append(fpath)
        print(f"  [crop] split {i} -> {fpath} ({w}x{img_h})")

    return paths


def crop_horizontal_ratios(
    image_path: str,
    ratios: List[float],
    out_dir: str,
    prefix: str = "split",
) -> List[str]:
    """Split image horizontally by ratios (e.g. [0.55, 0.45]).

    Args:
        image_path: Input image path
        ratios: List of float ratios (must sum to ~1.0)
        out_dir: Output directory
        prefix: Filename prefix

    Returns:
        List of saved paths
    """
    img = Image.open(image_path)
    img_w, img_h = img.size

    os.makedirs(out_dir, exist_ok=True)
    paths = []
    x = 0
    for i, ratio in enumerate(ratios):
        w = int(img_w * ratio) if i < len(ratios) - 1 else img_w - x
        cropped = img.crop((x, 0, x + w, img_h))
        fname = f"{prefix}_{i}.png"
        fpath = os.path.join(out_dir, fname)
        cropped.save(fpath, quality=95)
        paths.append(fpath)
        print(f"  [crop] ratio split {i} ({ratio:.0%}) -> {fpath} ({w}x{img_h})")
        x += w

    return paths


def crop_vertical_split(
    image_path: str,
    n_splits: int,
    out_dir: str,
    prefix: str = "split",
) -> List[str]:
    """Split image into N equal vertical segments.

    Args:
        image_path: Input image path
        n_splits: Number of vertical divisions
        out_dir: Output directory
        prefix: Filename prefix

    Returns:
        List of saved paths
    """
    img = Image.open(image_path)
    img_w, img_h = img.size
    segment_h = img_h // n_splits

    os.makedirs(out_dir, exist_ok=True)
    paths = []
    for i in range(n_splits):
        y = i * segment_h
        h = segment_h if i < n_splits - 1 else img_h - y
        cropped = img.crop((0, y, img_w, y + h))
        fname = f"{prefix}_{i}.png"
        fpath = os.path.join(out_dir, fname)
        cropped.save(fpath, quality=95)
        paths.append(fpath)
        print(f"  [crop] split {i} -> {fpath} ({img_w}x{h})")

    return paths


def main():
    parser = argparse.ArgumentParser(description="Image cropping tool")
    parser.add_argument("image", help="Input image path")
    parser.add_argument("--coords", type=str, default=None,
                        help="Crop by coords: x,y,w,h")
    parser.add_argument("--grid", type=str, default=None,
                        help="Crop by 3x3 grid cell: row,col (0-indexed)")
    parser.add_argument("--hsplit", type=int, default=None,
                        help="Split into N horizontal segments")
    parser.add_argument("--vsplit", type=int, default=None,
                        help="Split into N vertical segments")
    parser.add_argument("--out", type=str, default=None, help="Output path (for coords/grid)")
    parser.add_argument("--out-dir", type=str, default=None, help="Output dir (for split)")
    parser.add_argument("--prefix", type=str, default="split", help="Filename prefix for split")
    args = parser.parse_args()

    if args.coords:
        parts = [int(x) for x in args.coords.split(",")]
        out = args.out or "cropped.jpg"
        crop_by_coords(args.image, *parts, out)
    elif args.grid:
        row, col = [int(x) for x in args.grid.split(",")]
        out = args.out or "grid_crop.jpg"
        crop_by_grid(args.image, row, col, out)
    elif args.hsplit:
        out_dir = args.out_dir or "crops"
        crop_horizontal_split(args.image, args.hsplit, out_dir, args.prefix)
    elif args.vsplit:
        out_dir = args.out_dir or "crops"
        crop_vertical_split(args.image, args.vsplit, out_dir, args.prefix)
    else:
        parser.error("Specify --coords, --grid, --hsplit, or --vsplit")


if __name__ == "__main__":
    main()
