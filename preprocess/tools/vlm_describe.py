#!/usr/bin/env python3
"""
Tool: VLM Image Description

Send image(s) to OpenRouter VLM with a custom prompt for structured description.

Usage:
  python -m preprocess.tools.vlm_describe IMAGE --prompt "Describe this assembly step"
  python -m preprocess.tools.vlm_describe IMG1 IMG2 --prompt-file prompt.txt --out result.txt
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env", override=False)

from core.openrouter_labeler import OpenRouterLabeler
from core.interfaces import LabelerInput


def vlm_describe(
    image_paths: List[str],
    prompt: str,
    model: str = "google/gemini-2.5-flash",
    api_key: str = None,
    temperature: float = 0.2,
    max_tokens: int = 1000,
) -> str:
    """Send image(s) to VLM with custom prompt.

    Args:
        image_paths: List of image paths
        prompt: Description instruction
        model: OpenRouter model name
        api_key: API key (or from env)
        temperature: Sampling temperature
        max_tokens: Max response tokens

    Returns:
        VLM response text
    """
    labeler = OpenRouterLabeler(
        name="vlm_describe",
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    input_data = LabelerInput(
        text="",
        image_paths=image_paths,
        instruction=prompt,
    )

    output = labeler.label(input_data)
    return output.result.get("content", "")


def main():
    parser = argparse.ArgumentParser(description="VLM image description")
    parser.add_argument("images", nargs="+", help="Input image path(s)")
    parser.add_argument("--prompt", type=str, default=None, help="Prompt text")
    parser.add_argument("--prompt-file", type=str, default=None,
                        help="Read prompt from file")
    parser.add_argument("--model", type=str, default="google/gemini-2.5-flash")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=1000)
    parser.add_argument("--out", type=str, default=None, help="Output file")
    args = parser.parse_args()

    if args.prompt_file:
        with open(args.prompt_file, "r") as f:
            prompt = f.read().strip()
    elif args.prompt:
        prompt = args.prompt
    else:
        parser.error("Specify --prompt or --prompt-file")

    result = vlm_describe(
        args.images, prompt, args.model,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
    )

    if args.out:
        os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(result)
        print(f"[vlm_describe] Saved to {args.out}")
    else:
        print(result)


if __name__ == "__main__":
    main()
