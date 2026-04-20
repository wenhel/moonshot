#!/usr/bin/env python3
"""
Tool: VLM PDF Layout Detection V2 — boundary-focused

Improvement over v1: instead of asking VLM to estimate percentages,
ask it to find the vertical whitespace gaps between steps.

Stage 1: All pages -> structure (same as v1)
Stage 2: Per multi-step page -> find gap positions by describing
         what's at specific x-positions (binary search style)

Usage:
  python -m preprocess.tools.vlm_detect_layout_v2 PAGE_DIR --out layout.json
"""

import argparse
import json
import os
import re
import glob
import time
from pathlib import Path
from typing import List

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env", override=False)

from core.openrouter_labeler import OpenRouterLabeler
from core.interfaces import LabelerInput


# Stage 1: same as v1
STRUCTURE_PROMPT = """\
These images are ALL pages of an assembly instruction manual (one image per page, in order).

Analyze and output a JSON object:

{
  "name": "product name from cover",
  "total_pages": N,
  "parts_pages": [
    {"page": 2, "desc": "structural parts and plates"},
    ...
  ],
  "step_pages": [
    {"page": 5, "steps": [1, 2, 3]},
    {"page": 6, "steps": [4, 5]},
    ...
  ]
}

Rules:
- Page numbers are 1-indexed
- Cover pages: skip
- Parts/screws list pages: add to parts_pages
- Assembly step pages: add to step_pages with the circled step numbers visible
- Optional/info pages (e.g. "7 inch version"): skip entirely
- Do NOT include "boundaries" yet

Output ONLY valid JSON.
"""

# Stage 2: boundary-focused prompt
BOUNDARY_V2_PROMPT = """\
This image is {img_w}x{img_h} pixels. It shows {n_steps} assembly steps side by side.

I will crop each step separately. I need you to find the VERTICAL GAP (empty/blank column) \
between adjacent steps.

Look at this image carefully:
- Steps are separated by vertical whitespace (a narrow column with no content)
- The gap is usually 20-80 pixels wide
- There should be {n_gaps} gap(s) between {n_steps} steps

For each gap between steps, tell me:
1. The x-pixel position where the gap STARTS (left edge of empty space)
2. The x-pixel position where the gap ENDS (right edge of empty space)

I will split at the CENTER of each gap.

IMPORTANT:
- Look for columns where there is NO diagram content, NO text, NO labels — just background
- The gap runs from top to bottom of the image
- Do NOT guess or estimate — examine the actual image content

Output ONLY a JSON array of gaps:
[
  {{"gap_between": [{first_step}, {second_step}], "gap_start_px": <int>, "gap_end_px": <int>}}
]

For example, if steps 4 and 5 have a gap from x=980 to x=1020:
[{{"gap_between": [4, 5], "gap_start_px": 980, "gap_end_px": 1020}}]
"""


def _call_vlm(image_paths: List[str], prompt: str, model: str, api_key: str,
              max_tokens: int = 2000) -> str:
    labeler = OpenRouterLabeler(
        name="vlm_detect_layout_v2",
        model=model,
        api_key=api_key,
        temperature=0.1,
        max_tokens=max_tokens,
    )
    input_data = LabelerInput(text="", image_paths=image_paths, instruction=prompt)
    output = labeler.label(input_data)
    return output.result.get("content", "")


def _parse_json(content: str):
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    for open_ch, close_ch in [('{', '}'), ('[', ']')]:
        start = content.find(open_ch)
        end = content.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(content[start:end + 1])
            except json.JSONDecodeError:
                pass
    raise ValueError(f"Cannot parse JSON from VLM:\n{content[:500]}")


def _gaps_to_boundaries(gaps: List[dict], steps: List[int], img_w: int) -> List[dict]:
    """Convert gap positions to step boundaries.

    Split at center of each gap.
    """
    # Sort gaps by position
    gaps_sorted = sorted(gaps, key=lambda g: g["gap_start_px"])

    boundaries = []
    for i, step_num in enumerate(steps):
        if i == 0:
            start_px = 0
        else:
            # Center of gap between previous and current step
            gap = gaps_sorted[i - 1]
            start_px = (gap["gap_start_px"] + gap["gap_end_px"]) // 2

        if i == len(steps) - 1:
            end_px = img_w
        else:
            gap = gaps_sorted[i]
            end_px = (gap["gap_start_px"] + gap["gap_end_px"]) // 2

        boundaries.append({
            "step": step_num,
            "start_pct": round(start_px / img_w * 100, 1),
            "end_pct": round(end_px / img_w * 100, 1),
        })

    return boundaries


def detect_layout_v2(
    page_images: List[str],
    model: str = "google/gemini-2.5-flash",
    api_key: str = None,
) -> dict:
    """Two-stage layout detection with gap-based boundaries."""

    # Stage 1: Structure
    print(f"  [stage 1] Detecting structure from {len(page_images)} pages ...")
    content = _call_vlm(page_images, STRUCTURE_PROMPT, model, api_key, max_tokens=1500)
    layout = _parse_json(content)
    print(f"  [stage 1] Name: {layout.get('name', '?')}")
    print(f"  [stage 1] Parts: {[p['page'] for p in layout.get('parts_pages', [])]}")
    print(f"  [stage 1] Steps: {[(p['page'], p['steps']) for p in layout.get('step_pages', [])]}")

    # Stage 2: Gap detection for multi-step pages
    for step_page in layout.get("step_pages", []):
        steps = step_page.get("steps", [])
        if len(steps) <= 1:
            if steps:
                step_page["boundaries"] = [{"step": steps[0], "start_pct": 0, "end_pct": 100}]
            else:
                step_page["boundaries"] = []
            continue

        page_idx = step_page["page"] - 1
        if page_idx >= len(page_images):
            continue

        from PIL import Image as PILImage
        img = PILImage.open(page_images[page_idx])
        img_w, img_h = img.size

        n_gaps = len(steps) - 1
        print(f"\n  [stage 2] Page {step_page['page']}: finding {n_gaps} gap(s) between steps {steps} ({img_w}x{img_h}) ...")
        time.sleep(0.5)

        prompt = BOUNDARY_V2_PROMPT.format(
            n_steps=len(steps),
            n_gaps=n_gaps,
            first_step=steps[0],
            second_step=steps[1],
            img_w=img_w,
            img_h=img_h,
        )

        content = _call_vlm([page_images[page_idx]], prompt, model, api_key, max_tokens=500)
        gaps = _parse_json(content)

        print(f"  [stage 2] Gaps: {json.dumps(gaps)}")

        if len(gaps) == n_gaps:
            boundaries = _gaps_to_boundaries(gaps, steps, img_w)
            step_page["boundaries"] = boundaries
            print(f"  [stage 2] Boundaries: {json.dumps(boundaries)}")
        else:
            print(f"  [stage 2] WARNING: expected {n_gaps} gaps, got {len(gaps)}, using raw")
            # Try to use whatever we got
            if gaps:
                boundaries = _gaps_to_boundaries(gaps, steps, img_w)
                step_page["boundaries"] = boundaries
            else:
                step_page["boundaries"] = []

    return layout


def main():
    parser = argparse.ArgumentParser(description="Detect manual PDF layout via VLM v2 (gap-based)")
    parser.add_argument("page_dir", help="Directory containing page PNG images")
    parser.add_argument("--out", type=str, default="layout.json", help="Output JSON path")
    parser.add_argument("--model", type=str, default="google/gemini-2.5-flash")
    args = parser.parse_args()

    page_images = sorted(glob.glob(os.path.join(args.page_dir, "page_*.png")))
    if not page_images:
        print(f"ERROR: No page_*.png found in {args.page_dir}")
        return

    layout = detect_layout_v2(page_images, model=args.model)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(layout, f, indent=2, ensure_ascii=False)
    print(f"\n[detect_layout_v2] Saved {args.out}")


if __name__ == "__main__":
    main()
