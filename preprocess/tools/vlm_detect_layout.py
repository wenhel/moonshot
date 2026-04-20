#!/usr/bin/env python3
"""
Tool: VLM PDF Layout Detection (two-stage)

Stage 1: Send all pages -> detect structure (which pages are parts/steps, step numbers)
Stage 2: For each multi-step page, send that single page -> detect precise boundaries

Output: layout.json

Usage:
  python -m preprocess.tools.vlm_detect_layout PAGE_DIR --out layout.json
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


# Stage 1: Structure detection (all pages at once)
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
    {"page": 8, "steps": [8]},
    ...
  ]
}

Rules:
- Page numbers are 1-indexed
- Cover pages: skip
- Parts/screws list pages: add to parts_pages
- Assembly step pages: add to step_pages with the circled step numbers visible
- Optional/info pages (e.g. "7 inch version"): skip entirely
- Do NOT include "boundaries" yet — only structure

Output ONLY valid JSON.
"""

# Stage 2: Precise boundary detection (one page at a time)
BOUNDARY_PROMPT = """\
This image is {img_w}x{img_h} pixels. It contains {n_steps} assembly steps \
laid out horizontally (steps: {step_list}).

Each step has a circled number (like ④ ⑤), a diagram, and instruction text below.

YOUR TASK: Find the EXACT x-pixel coordinate where each step's content starts and ends.

How to find boundaries:
1. Find each step's circled number label — note its x position in pixels
2. The boundary between step N and step N+1 is the MIDPOINT of the gap between them
3. Step 1 always starts at x=0
4. The last step always ends at x={img_w}

CRITICAL:
- Do NOT divide equally — measure actual positions
- Each step must include ALL its diagram + ALL its text + any "ADDITIONAL PARTS" sidebar
- The split line should be in empty space between steps, not through any content

Output ONLY a JSON array with pixel coordinates:
[
  {{"step": {first_step}, "start_px": 0, "end_px": <pixel>}},
  {{"step": {second_step}, "start_px": <pixel>, "end_px": <pixel>}},
  ...
]
"""


def _call_vlm(image_paths: List[str], prompt: str, model: str, api_key: str,
              max_tokens: int = 2000) -> str:
    """Call VLM and return content string."""
    labeler = OpenRouterLabeler(
        name="vlm_detect_layout",
        model=model,
        api_key=api_key,
        temperature=0.1,
        max_tokens=max_tokens,
    )
    input_data = LabelerInput(text="", image_paths=image_paths, instruction=prompt)
    output = labeler.label(input_data)
    return output.result.get("content", "")


def _parse_json(content: str):
    """Extract JSON from VLM response."""
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
    # Find outermost { } or [ ]
    for open_ch, close_ch in [('{', '}'), ('[', ']')]:
        start = content.find(open_ch)
        end = content.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(content[start:end + 1])
            except json.JSONDecodeError:
                pass
    raise ValueError(f"Cannot parse JSON from VLM:\n{content[:500]}")


def detect_layout(
    page_images: List[str],
    model: str = "google/gemini-2.5-flash",
    api_key: str = None,
) -> dict:
    """Two-stage layout detection.

    Stage 1: All pages -> structure (parts/step pages + step numbers)
    Stage 2: Each multi-step page -> precise boundaries
    """
    # Stage 1: Structure
    print(f"  [stage 1] Detecting structure from {len(page_images)} pages ...")
    content = _call_vlm(page_images, STRUCTURE_PROMPT, model, api_key, max_tokens=1500)
    layout = _parse_json(content)
    print(f"  [stage 1] Name: {layout.get('name', '?')}")
    print(f"  [stage 1] Parts: {[p['page'] for p in layout.get('parts_pages', [])]}")
    print(f"  [stage 1] Steps: {[(p['page'], p['steps']) for p in layout.get('step_pages', [])]}")

    # Stage 2: Boundaries for multi-step pages
    for step_page in layout.get("step_pages", []):
        steps = step_page.get("steps", [])
        if len(steps) <= 1:
            # Single step: full page
            if steps:
                step_page["boundaries"] = [{"step": steps[0], "start_pct": 0, "end_pct": 100}]
            else:
                step_page["boundaries"] = []
            continue

        page_idx = step_page["page"] - 1
        if page_idx >= len(page_images):
            continue

        print(f"\n  [stage 2] Page {step_page['page']}: detecting boundaries for steps {steps} ...")
        time.sleep(0.5)

        # Get image dimensions
        from PIL import Image as PILImage
        img = PILImage.open(page_images[page_idx])
        img_w, img_h = img.size

        prompt = BOUNDARY_PROMPT.format(
            n_steps=len(steps),
            step_list=", ".join(str(s) for s in steps),
            first_step=steps[0],
            second_step=steps[1] if len(steps) > 1 else steps[0],
            img_w=img_w,
            img_h=img_h,
        )

        content = _call_vlm([page_images[page_idx]], prompt, model, api_key, max_tokens=500)
        raw_boundaries = _parse_json(content)

        # Convert px to pct for consistency with crop code
        boundaries = []
        for b in raw_boundaries:
            if "start_px" in b:
                boundaries.append({
                    "step": b["step"],
                    "start_pct": round(b["start_px"] / img_w * 100, 1),
                    "end_pct": round(b["end_px"] / img_w * 100, 1),
                })
            else:
                boundaries.append(b)  # already pct format

        if len(boundaries) == len(steps):
            step_page["boundaries"] = boundaries
            print(f"  [stage 2] Boundaries (pct): {json.dumps(boundaries)}")
        else:
            print(f"  [stage 2] WARNING: expected {len(steps)} boundaries, got {len(boundaries)}")
            step_page["boundaries"] = boundaries

    return layout


def main():
    parser = argparse.ArgumentParser(description="Detect manual PDF layout via VLM (two-stage)")
    parser.add_argument("page_dir", help="Directory containing page PNG images")
    parser.add_argument("--out", type=str, default="layout.json", help="Output JSON path")
    parser.add_argument("--model", type=str, default="google/gemini-2.5-flash")
    args = parser.parse_args()

    page_images = sorted(glob.glob(os.path.join(args.page_dir, "page_*.png")))
    if not page_images:
        print(f"ERROR: No page_*.png found in {args.page_dir}")
        return

    layout = detect_layout(page_images, model=args.model)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(layout, f, indent=2, ensure_ascii=False)
    print(f"\n[detect_layout] Saved {args.out}")


if __name__ == "__main__":
    main()
