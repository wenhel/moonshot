#!/usr/bin/env python3
"""
Tool: PDF to Images

Convert PDF pages to PNG images using PyMuPDF.

Usage:
  python -m preprocess.tools.pdf2img INPUT.pdf --out DIR [--dpi 300] [--pages 1-5]
"""

import argparse
import os
import fitz  # PyMuPDF


def pdf_to_images(
    pdf_path: str,
    out_dir: str,
    dpi: int = 300,
    page_start: int = 0,
    page_end: int = -1,
) -> list:
    """Convert PDF pages to PNG images.

    Args:
        pdf_path: Path to PDF file
        out_dir: Output directory for PNG files
        dpi: Resolution (default 300)
        page_start: First page (0-indexed)
        page_end: Last page (-1 = all)

    Returns:
        List of saved PNG paths
    """
    doc = fitz.open(pdf_path)
    os.makedirs(out_dir, exist_ok=True)

    if page_end < 0:
        page_end = len(doc) - 1

    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    paths = []
    for i in range(page_start, min(page_end + 1, len(doc))):
        page = doc[i]
        pix = page.get_pixmap(matrix=mat)
        fname = f"page_{i + 1:03d}.png"
        fpath = os.path.join(out_dir, fname)
        pix.save(fpath)
        paths.append(fpath)
        print(f"  [pdf2img] Page {i + 1} -> {fpath} ({pix.width}x{pix.height})")

    doc.close()
    print(f"[pdf2img] Converted {len(paths)} pages to {out_dir}")
    return paths


def main():
    parser = argparse.ArgumentParser(description="PDF to PNG images")
    parser.add_argument("pdf", help="Input PDF path")
    parser.add_argument("--out", type=str, required=True, help="Output directory")
    parser.add_argument("--dpi", type=int, default=300, help="Resolution (default 300)")
    parser.add_argument("--pages", type=str, default=None,
                        help="Page range e.g. '1-5' or '3' (1-indexed, default all)")
    args = parser.parse_args()

    page_start = 0
    page_end = -1
    if args.pages:
        parts = args.pages.split("-")
        page_start = int(parts[0]) - 1
        page_end = int(parts[-1]) - 1

    pdf_to_images(args.pdf, args.out, args.dpi, page_start, page_end)


if __name__ == "__main__":
    main()
