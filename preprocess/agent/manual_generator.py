#!/usr/bin/env python3
"""
Agent: Manual Generator

Fully VLM-driven pipeline that parses any assembly manual PDF into structured markdown.
No hardcoded layouts — VLM auto-detects the PDF structure.

Pipeline:
  Phase 0: pdf2img           -> page PNGs
  Phase 1: vlm_detect_layout -> layout.json (or load existing)
  Phase 2: img_crop          -> crop parts + step diagrams (using layout.json boundaries)
  Phase 3: vlm_ocr           -> OCR each crop
  Phase 4: compile           -> manual_steps.md + manual_parsed.json

Usage:
  cd moonshot/code
  python -m preprocess.agent.manual_generator MANUAL.pdf --out OUTPUT_DIR

Output:
  OUTPUT_DIR/
  ├── pages/              # Full page PNGs
  ├── parts/              # Cropped parts list images
  ├── steps/              # Cropped step images
  ├── text/               # Extracted text per page (if any)
  ├── layout.json         # VLM-detected layout (editable, reusable)
  ├── manual_steps.md     # Final structured markdown
  └── manual_parsed.json  # Raw OCR results
"""

import argparse
import json
import os
import time
from pathlib import Path
from shutil import copy2

from preprocess.tools.pdf2img import pdf_to_images
from preprocess.tools.pdf_text import extract_text
from preprocess.tools.vlm_ocr import vlm_ocr, ASSEMBLY_OCR_PROMPT
from preprocess.tools.vlm_detect_layout import detect_layout as detect_layout_v1
from preprocess.tools.vlm_detect_layout_v2 import detect_layout_v2


def _crop_by_pct(image_path: str, start_pct: float, end_pct: float, out_path: str) -> str:
    """Crop image horizontally by percentage boundaries."""
    from PIL import Image
    img = Image.open(image_path)
    w, h = img.size
    x_start = max(0, int(w * start_pct / 100))
    x_end = min(w, int(w * end_pct / 100))
    cropped = img.crop((x_start, 0, x_end, h))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    cropped.save(out_path, quality=95)
    cw = x_end - x_start
    print(f"  [crop] {start_pct:.0f}%-{end_pct:.0f}% -> {out_path} ({cw}x{h})")
    return out_path


def run_pipeline(pdf_path: str, out_dir: str, layout_path: str = None,
                 layout_version: str = "v2") -> str:
    """Run the full manual parsing pipeline.

    Args:
        pdf_path: Path to assembly manual PDF
        out_dir: Output directory
        layout_path: Path to existing layout.json (skip VLM detection if provided)
        layout_version: "v1" (percentage-based) or "v2" (gap-based, default)

    Returns:
        Path to generated manual_steps.md
    """
    pages_dir = os.path.join(out_dir, "pages")
    parts_dir = os.path.join(out_dir, "parts")
    steps_dir = os.path.join(out_dir, "steps")
    text_dir = os.path.join(out_dir, "text")

    for d in [pages_dir, parts_dir, steps_dir, text_dir]:
        os.makedirs(d, exist_ok=True)

    # ========================================
    # Phase 0: PDF -> page images
    # ========================================
    print("=" * 60)
    print("[Phase 0] Converting PDF to page images")
    print("=" * 60)

    page_images = pdf_to_images(pdf_path, pages_dir, dpi=300)

    # Also extract vector text (may be empty for image-only PDFs)
    page_texts = extract_text(pdf_path)
    for page_num, text in page_texts.items():
        text_path = os.path.join(text_dir, f"page_{page_num:03d}.txt")
        with open(text_path, "w", encoding="utf-8") as f:
            f.write(text)

    # ========================================
    # Phase 1: Detect layout (VLM or load JSON)
    # ========================================
    print("\n" + "=" * 60)
    print("[Phase 1] Detecting PDF layout")
    print("=" * 60)

    default_layout_path = os.path.join(out_dir, "layout.json")

    if layout_path and os.path.exists(layout_path):
        # Use provided layout
        with open(layout_path, "r", encoding="utf-8") as f:
            layout = json.load(f)
        print(f"[layout] Loaded from {layout_path}")
    elif os.path.exists(default_layout_path):
        # Reuse previously generated layout
        with open(default_layout_path, "r", encoding="utf-8") as f:
            layout = json.load(f)
        print(f"[layout] Loaded existing {default_layout_path}")
        print(f"  (delete this file to re-detect)")
    else:
        # VLM auto-detect
        print(f"[layout] Sending {len(page_images)} pages to VLM (version={layout_version}) ...")
        if layout_version == "v2":
            layout = detect_layout_v2(page_images)
        else:
            layout = detect_layout_v1(page_images)
        with open(default_layout_path, "w", encoding="utf-8") as f:
            json.dump(layout, f, indent=2, ensure_ascii=False)
        print(f"[layout] Saved to {default_layout_path}")

    print(f"[layout] Name: {layout.get('name', '?')}")
    print(f"[layout] Parts pages: {[p['page'] for p in layout.get('parts_pages', [])]}")
    print(f"[layout] Step pages: {[p['page'] for p in layout.get('step_pages', [])]}")

    # ========================================
    # Phase 2: Crop parts and steps
    # ========================================
    print("\n" + "=" * 60)
    print("[Phase 2] Cropping parts and step diagrams")
    print("=" * 60)

    # Crop parts pages (full page)
    parts_crops = []
    for parts_info in layout.get("parts_pages", []):
        page_idx = parts_info["page"] - 1
        if page_idx < len(page_images):
            src = page_images[page_idx]
            dst = os.path.join(parts_dir, f"parts_page{parts_info['page']}.png")
            copy2(src, dst)
            desc = parts_info.get("desc", f"Parts page {parts_info['page']}")
            parts_crops.append({"path": dst, "desc": desc, "page": parts_info["page"]})
            print(f"  [parts] Page {parts_info['page']} -> {dst}")

    # Crop step diagrams using layout.json boundaries
    step_crops = []
    for step_page in layout.get("step_pages", []):
        page_idx = step_page["page"] - 1
        if page_idx >= len(page_images):
            continue
        src = page_images[page_idx]
        steps = step_page.get("steps", [])
        if not steps:
            print(f"  [skip] Page {step_page['page']}: no steps (optional/info page)")
            continue
        boundaries = step_page.get("boundaries", [])

        if len(steps) == 1 and not boundaries:
            # Single step, full page
            final_path = os.path.join(steps_dir, f"step_{steps[0]:02d}.png")
            copy2(src, final_path)
            step_crops.append({"step": steps[0], "path": final_path, "page": step_page["page"]})
            print(f"  [crop] Step {steps[0]} (full page) -> {final_path}")

        elif boundaries and len(boundaries) == len(steps):
            # Use VLM-detected boundaries from layout.json
            for step_num, boundary in zip(steps, boundaries):
                final_path = os.path.join(steps_dir, f"step_{step_num:02d}.png")
                _crop_by_pct(src, boundary["start_pct"], boundary["end_pct"], final_path)
                step_crops.append({"step": step_num, "path": final_path, "page": step_page["page"]})

        else:
            # Fallback: equal split
            n = len(steps)
            print(f"  [crop] Page {step_page['page']}: no boundaries, equal {n}-split fallback")
            from PIL import Image
            img = Image.open(src)
            img_w, img_h = img.size
            seg_w = img_w // n
            for i, step_num in enumerate(steps):
                x = i * seg_w
                w = seg_w if i < n - 1 else img_w - x
                cropped = img.crop((x, 0, x + w, img_h))
                final_path = os.path.join(steps_dir, f"step_{step_num:02d}.png")
                cropped.save(final_path, quality=95)
                step_crops.append({"step": step_num, "path": final_path, "page": step_page["page"]})
                print(f"  [crop] Step {step_num} (equal split) -> {final_path}")

    print(f"\n[Phase 2] Cropped {len(parts_crops)} parts pages, {len(step_crops)} step diagrams")

    # ========================================
    # Phase 3: VLM OCR on each crop
    # ========================================
    print("\n" + "=" * 60)
    print("[Phase 3] VLM OCR on parts and steps")
    print("=" * 60)

    parts_ocr_results = []
    for i, parts_info in enumerate(parts_crops):
        print(f"\n  [vlm_ocr] Parts page {parts_info['page']} ({i + 1}/{len(parts_crops)}) ...")
        result = vlm_ocr(
            [parts_info["path"]],
            prompt=(
                "This is a parts list page from an assembly manual. "
                "List EVERY part shown with:\n"
                "- Part name (as labeled)\n"
                "- Quantity (e.g. x1, x4)\n"
                "Output as a clean list. Include screws if visible."
            ),
        )
        parts_ocr_results.append({
            "page": parts_info["page"],
            "desc": parts_info["desc"],
            "ocr_text": result,
        })
        time.sleep(0.5)

    step_ocr_results = []
    for i, step_info in enumerate(step_crops):
        print(f"\n  [vlm_ocr] Step {step_info['step']} ({i + 1}/{len(step_crops)}) ...")
        result = vlm_ocr(
            [step_info["path"]],
            prompt=ASSEMBLY_OCR_PROMPT,
        )
        step_ocr_results.append({
            "step": step_info["step"],
            "page": step_info["page"],
            "path": step_info["path"],
            "ocr_text": result,
        })
        time.sleep(0.5)

    # ========================================
    # Phase 4: Compile markdown
    # ========================================
    print("\n" + "=" * 60)
    print("[Phase 4] Compiling manual_steps.md")
    print("=" * 60)

    manual_name = layout.get("name", Path(pdf_path).stem)
    md_lines = [
        f"# {manual_name} — Assembly Manual\n",
        f"Auto-generated from {Path(pdf_path).name} using VLM.\n",
        "---\n",
    ]

    md_lines.append("## Parts List\n")
    for parts_info in parts_ocr_results:
        md_lines.append(f"### Page {parts_info['page']} — {parts_info['desc']}\n")
        rel_path = os.path.relpath(
            os.path.join(parts_dir, f"parts_page{parts_info['page']}.png"), out_dir
        )
        md_lines.append(f'[![parts page {parts_info["page"]}]({rel_path})]({rel_path})\n')
        md_lines.append(f"{parts_info['ocr_text']}\n")
        md_lines.append("")

    md_lines.append("---\n")
    md_lines.append("## Assembly Steps\n")
    for step_info in step_ocr_results:
        md_lines.append(f"### Step {step_info['step']}\n")
        rel_path = os.path.relpath(step_info["path"], out_dir)
        md_lines.append(f'[![step {step_info["step"]}]({rel_path})]({rel_path})\n')
        md_lines.append(f"{step_info['ocr_text']}\n")
        md_lines.append("")

    md_path = os.path.join(out_dir, "manual_steps.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    print(f"\n[output] Saved {md_path}")

    json_path = os.path.join(out_dir, "manual_parsed.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "layout": layout,
            "parts": parts_ocr_results,
            "steps": step_ocr_results,
        }, f, indent=2, ensure_ascii=False)
    print(f"[output] Saved {json_path}")

    return md_path


def main():
    parser = argparse.ArgumentParser(
        description="Manual Generator — parse any assembly manual PDF into structured markdown"
    )
    parser.add_argument("pdf", help="Input PDF path")
    parser.add_argument("--out", type=str, default=None,
                        help="Output directory (default: output/<pdf_stem>_parsed)")
    parser.add_argument("--layout", type=str, default=None,
                        help="Path to existing layout.json (skip VLM detection)")
    parser.add_argument("--layout-version", type=str, default="v2",
                        choices=["v1", "v2"],
                        help="Layout detector version: v1 (percentage) or v2 (gap-based, default)")
    args = parser.parse_args()

    if args.out is None:
        stem = Path(args.pdf).stem.lower()
        args.out = f"output/{stem}_parsed"

    run_pipeline(args.pdf, args.out, layout_path=args.layout,
                 layout_version=args.layout_version)


if __name__ == "__main__":
    main()
