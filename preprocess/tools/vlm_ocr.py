#!/usr/bin/env python3
"""
Tool: VLM-based OCR

Send image(s) to OpenRouter VLM and extract text content.

Usage:
  python -m preprocess.tools.vlm_ocr IMAGE [--out text.txt]
  python -m preprocess.tools.vlm_ocr IMAGE1 IMAGE2 --out result.json
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List

# Auto-load .env
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env", override=False)

from core.openrouter_labeler import OpenRouterLabeler
from core.interfaces import LabelerInput


DEFAULT_OCR_PROMPT = (
    "Read ALL text visible in this image. "
    "Output the text exactly as written, preserving line breaks and formatting. "
    "If the image contains diagrams or illustrations with labels, "
    "list each label with its position description. "
    "If no text is visible, output '(no text)'."
)

ASSEMBLY_OCR_PROMPT = """\
This is a page from an assembly instruction manual.

Extract the information and output in EXACTLY this markdown format (copy the headers exactly):

---

#### Step [N]

**Instruction:** [The written assembly instruction text, copied verbatim from the image]

**Parts:**
- [part name 1]
- [part name 2]

**Screws:**
- [screw type and size 1]
- [screw type and size 2]

**Diagram:** [One sentence describing what the diagram shows]

---

Rules:
- Use the EXACT format above with the EXACT headers (#### Step, **Instruction:**, **Parts:**, **Screws:**, **Diagram:**)
- Each field on its own line, lists use bullet points (- item)
- If multiple steps are visible, repeat the block for each step
- If a field has no content, write "None"
- Do NOT add extra commentary or change the header names
- CRITICAL: Extract Parts and Screws from the INSTRUCTION TEXT, not from diagram labels.
  The instruction text is the most reliable source. Read the instruction first,
  then list every part name and every screw specification (e.g. M3x6mm) mentioned in it.
  Do NOT guess or abbreviate screw sizes — copy them exactly from the instruction text.
"""


def vlm_ocr(
    image_paths: List[str],
    prompt: str = DEFAULT_OCR_PROMPT,
    model: str = "google/gemini-2.5-flash",
    api_key: str = None,
) -> str:
    """Send image(s) to VLM for text extraction.

    Args:
        image_paths: List of image paths
        prompt: OCR instruction prompt
        model: OpenRouter model name
        api_key: API key (or from env)

    Returns:
        Extracted text from VLM
    """
    labeler = OpenRouterLabeler(
        name="vlm_ocr",
        model=model,
        api_key=api_key,
        temperature=0.1,
        max_tokens=2000,
    )

    input_data = LabelerInput(
        text="",
        image_paths=image_paths,
        instruction=prompt,
    )

    output = labeler.label(input_data)
    return output.result.get("content", "")


def main():
    parser = argparse.ArgumentParser(description="VLM-based OCR")
    parser.add_argument("images", nargs="+", help="Input image path(s)")
    parser.add_argument("--prompt", type=str, default="default",
                        choices=["default", "assembly"],
                        help="Prompt type (default or assembly)")
    parser.add_argument("--custom-prompt", type=str, default=None,
                        help="Custom prompt (overrides --prompt)")
    parser.add_argument("--model", type=str, default="google/gemini-2.5-flash")
    parser.add_argument("--out", type=str, default=None, help="Output file")
    args = parser.parse_args()

    if args.custom_prompt:
        prompt = args.custom_prompt
    elif args.prompt == "assembly":
        prompt = ASSEMBLY_OCR_PROMPT
    else:
        prompt = DEFAULT_OCR_PROMPT

    result = vlm_ocr(args.images, prompt, args.model)

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"[vlm_ocr] Saved to {args.out}")
    else:
        print(result)


if __name__ == "__main__":
    main()
