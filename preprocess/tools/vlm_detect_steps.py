#!/usr/bin/env python3
"""
Tool: VLM Step Boundary Detection

Send a manual page image to VLM and detect the x-coordinate boundaries
of each assembly step diagram.

Usage:
  python -m preprocess.tools.vlm_detect_steps PAGE_IMAGE --steps 2
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env", override=False)

from core.openrouter_labeler import OpenRouterLabeler
from core.interfaces import LabelerInput


DETECT_PROMPT = (
    "This image is a page from an assembly instruction manual. "
    "It contains {n_steps} assembly steps laid out side by side horizontally. "
    "Each step has a circled number (like ① ② ③), a diagram, and instruction text below.\n\n"
    "I need to crop each step separately. "
    "Tell me the horizontal split points as percentages of the total image width.\n\n"
    "For example, if there are 3 steps and step 1 ends at 35% width, step 2 ends at 68%:\n"
    "```json\n"
    '[{{"step": 1, "start_pct": 0, "end_pct": 35}}, '
    '{{"step": 2, "start_pct": 35, "end_pct": 68}}, '
    '{{"step": 3, "start_pct": 68, "end_pct": 100}}]\n'
    "```\n\n"
    "IMPORTANT:\n"
    "- Each step must include its FULL diagram and ALL its instruction text\n"
    "- Do NOT cut a step's text or diagram in half\n"
    "- If a step has 'ADDITIONAL PARTS' shown to its right, include that in the step\n"
    "- Output ONLY the JSON array, no other text"
)


def detect_step_boundaries(
    image_path: str,
    n_steps: int,
    model: str = "google/gemini-2.5-flash",
    api_key: str = None,
) -> List[dict]:
    """Detect step boundaries in a manual page image.

    Args:
        image_path: Path to page image
        n_steps: Expected number of steps on this page
        model: VLM model
        api_key: API key

    Returns:
        List of {"step": N, "start_pct": float, "end_pct": float}
    """
    labeler = OpenRouterLabeler(
        name="vlm_detect_steps",
        model=model,
        api_key=api_key,
        temperature=0.1,
        max_tokens=500,
    )

    prompt = DETECT_PROMPT.format(n_steps=n_steps)
    input_data = LabelerInput(
        text="",
        image_paths=[image_path],
        instruction=prompt,
    )

    output = labeler.label(input_data)
    content = output.result.get("content", "")

    # Parse JSON from response
    try:
        # Try direct parse
        boundaries = json.loads(content)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code block
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
        if m:
            boundaries = json.loads(m.group(1).strip())
        else:
            # Try to find [...] block
            start = content.find("[")
            end = content.rfind("]")
            if start != -1 and end > start:
                boundaries = json.loads(content[start:end + 1])
            else:
                raise ValueError(f"Cannot parse step boundaries from VLM response:\n{content}")

    # Validate
    if len(boundaries) != n_steps:
        print(f"  [detect] WARNING: Expected {n_steps} steps, got {len(boundaries)}")

    return boundaries


def crop_by_boundaries(
    image_path: str,
    boundaries: List[dict],
    out_dir: str,
    step_numbers: List[int],
) -> List[str]:
    """Crop image by detected step boundaries.

    Args:
        image_path: Source image
        boundaries: From detect_step_boundaries
        out_dir: Output directory
        step_numbers: Step numbers for naming

    Returns:
        List of cropped image paths
    """
    from PIL import Image
    img = Image.open(image_path)
    img_w, img_h = img.size

    os.makedirs(out_dir, exist_ok=True)
    paths = []

    for i, (boundary, step_num) in enumerate(zip(boundaries, step_numbers)):
        x_start = int(img_w * boundary["start_pct"] / 100)
        x_end = int(img_w * boundary["end_pct"] / 100)
        # Clamp
        x_start = max(0, x_start)
        x_end = min(img_w, x_end)

        cropped = img.crop((x_start, 0, x_end, img_h))
        fname = f"step_{step_num:02d}.png"
        fpath = os.path.join(out_dir, fname)
        cropped.save(fpath, quality=95)
        paths.append(fpath)
        w = x_end - x_start
        print(f"  [crop] Step {step_num}: {boundary['start_pct']}%-{boundary['end_pct']}% -> {fpath} ({w}x{img_h})")

    return paths


def main():
    parser = argparse.ArgumentParser(description="Detect step boundaries in manual page")
    parser.add_argument("image", help="Page image path")
    parser.add_argument("--steps", type=int, required=True, help="Number of steps on page")
    parser.add_argument("--out-dir", type=str, default=".", help="Output dir for crops")
    parser.add_argument("--step-start", type=int, default=1, help="First step number")
    args = parser.parse_args()

    step_numbers = list(range(args.step_start, args.step_start + args.steps))
    boundaries = detect_step_boundaries(args.image, args.steps)
    print(f"Detected boundaries: {json.dumps(boundaries, indent=2)}")

    if args.out_dir:
        paths = crop_by_boundaries(args.image, boundaries, args.out_dir, step_numbers)
        print(f"Cropped {len(paths)} steps")


if __name__ == "__main__":
    main()
