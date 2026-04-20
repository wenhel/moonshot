#!/usr/bin/env python3
"""
Tool: PDF Text Extraction

Extract vector text from PDF using PyMuPDF (no OCR needed for vector text).

Usage:
  python -m preprocess.tools.pdf_text INPUT.pdf [--pages 1-5] [--out text.md]
"""

import argparse
import os
import fitz  # PyMuPDF


def extract_text(
    pdf_path: str,
    page_start: int = 0,
    page_end: int = -1,
) -> dict:
    """Extract text from PDF pages.

    Args:
        pdf_path: Path to PDF
        page_start: First page (0-indexed)
        page_end: Last page (-1 = all)

    Returns:
        Dict mapping page number (1-indexed) to extracted text
    """
    doc = fitz.open(pdf_path)
    if page_end < 0:
        page_end = len(doc) - 1

    results = {}
    for i in range(page_start, min(page_end + 1, len(doc))):
        page = doc[i]
        text = page.get_text("text").strip()
        results[i + 1] = text
        n_chars = len(text)
        print(f"  [pdf_text] Page {i + 1}: {n_chars} chars")

    doc.close()
    return results


def main():
    parser = argparse.ArgumentParser(description="PDF text extraction")
    parser.add_argument("pdf", help="Input PDF path")
    parser.add_argument("--pages", type=str, default=None,
                        help="Page range e.g. '1-5' (1-indexed, default all)")
    parser.add_argument("--out", type=str, default=None,
                        help="Output file (default: stdout)")
    args = parser.parse_args()

    page_start = 0
    page_end = -1
    if args.pages:
        parts = args.pages.split("-")
        page_start = int(parts[0]) - 1
        page_end = int(parts[-1]) - 1

    results = extract_text(args.pdf, page_start, page_end)

    output_lines = []
    for page_num, text in sorted(results.items()):
        output_lines.append(f"## Page {page_num}\n")
        if text:
            output_lines.append(text)
        else:
            output_lines.append("(no extractable text)")
        output_lines.append("")

    output = "\n".join(output_lines)

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"[pdf_text] Saved to {args.out}")
    else:
        print(output)


if __name__ == "__main__":
    main()
