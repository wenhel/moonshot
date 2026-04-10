#!/usr/bin/env python3
"""
SRT Semantic Segmentation

Reads an SRT file, merges fragments into continuous text with timestamps,
then calls LLM to identify semantically coherent segments (assembly steps).
Outputs a segments JSON file that can be fed into segment_video.py for
keyframe extraction and VLM description.
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import List

# ---------------------------------------------------------------------------
# SRT parsing — merge overlapping auto-generated fragments
# ---------------------------------------------------------------------------

def parse_srt(srt_path: str) -> List[dict]:
    """Parse SRT into list of {start, end, text} (seconds)."""
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = re.split(r"\n\s*\n", content.strip())
    entries = []
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        ts = re.match(
            r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",
            lines[1],
        )
        if not ts:
            continue
        g = [int(x) for x in ts.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        text = " ".join(lines[2:]).strip()
        text = re.sub(r"<[^>]+>", "", text)
        if text:
            entries.append({"start": start, "end": end, "text": text})
    return entries


def merge_srt_to_text(entries: List[dict], max_sec: float = None) -> str:
    """Merge SRT entries into timestamped text blocks for LLM input.

    Deduplicates overlapping auto-generated fragments and produces
    a clean transcript with timestamps every ~10 seconds.
    """
    if not entries:
        return ""

    # Deduplicate: YouTube auto-subs have overlapping fragments
    # Walk through and build non-overlapping text
    merged = []
    seen_text = set()
    for e in entries:
        if max_sec and e["start"] >= max_sec:
            break
        t = e["text"].strip()
        if t not in seen_text:
            seen_text.add(t)
            merged.append(e)

    # Group into ~10s blocks for readability
    lines = []
    block_start = 0.0
    block_texts = []
    for e in merged:
        if e["start"] - block_start > 10.0 and block_texts:
            ts = f"[{_fmt(block_start)} - {_fmt(e['start'])}]"
            lines.append(f"{ts} {' '.join(block_texts)}")
            block_texts = []
            block_start = e["start"]
        block_texts.append(e["text"])

    if block_texts:
        end_t = merged[-1]["end"] if merged else block_start
        ts = f"[{_fmt(block_start)} - {_fmt(end_t)}]"
        lines.append(f"{ts} {' '.join(block_texts)}")

    return "\n".join(lines)


def _fmt(sec: float) -> str:
    m, s = divmod(sec, 60)
    return f"{int(m):02d}:{s:05.2f}"


# ---------------------------------------------------------------------------
# LLM semantic segmentation
# ---------------------------------------------------------------------------

SEGMENTATION_PROMPT = """\
You are analyzing a transcript of a drone assembly tutorial video (0:00 to ~11:00).

Below is the timestamped transcript. Your task is to identify semantically coherent segments — \
each segment should correspond to ONE assembly step or topic (e.g., "attach arms to frame", \
"solder motor wires to ESC", "mount camera").

Rules:
- Each segment must have a clear start_sec and end_sec (in seconds, float).
- Segments must be contiguous and non-overlapping, covering the full transcript.
- Aim for 10-25 segments. Merge trivially short transitions into adjacent segments.
- Give each segment a short title (5-10 words) describing the assembly step.
- Output ONLY valid JSON array, no other text.

Output format:
```json
[
  {"index": 0, "start_sec": 0.0, "end_sec": 34.0, "title": "Introduction and parts overview"},
  {"index": 1, "start_sec": 34.0, "end_sec": 62.0, "title": "Assemble frame arms"},
  ...
]
```

Transcript:
"""


def call_llm_segmentation(transcript: str, api_key: str, model: str = "google/gemini-2.5-flash") -> list:
    """Call LLM to produce semantic segments from transcript."""
    import requests

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": SEGMENTATION_PROMPT + transcript}
        ],
        "max_tokens": 4096,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = "https://openrouter.ai/api/v1/chat/completions"

    for attempt in range(3):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=90)
            if resp.status_code >= 500 or resp.status_code == 429:
                time.sleep(3 * (attempt + 1))
                continue
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"].strip()
            return _parse_segments_json(raw)
        except Exception as e:
            if attempt >= 2:
                raise RuntimeError(f"LLM segmentation failed: {e}")
            time.sleep(3 * (attempt + 1))

    raise RuntimeError("LLM segmentation failed: retries exhausted")


def _parse_segments_json(text: str) -> list:
    """Extract JSON array from LLM response."""
    # Try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass
    # Fenced code block
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except Exception:
            pass
    # First [ ... ] block
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except Exception:
            pass
    raise ValueError(f"Cannot parse LLM response as JSON array:\n{text[:500]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="SRT semantic segmentation via LLM")
    parser.add_argument("srt", help="Path to SRT file")
    parser.add_argument("--max-sec", type=float, default=660.0,
                        help="Only process transcript up to this time (default: 660 = 11:00)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output JSON path (default: <srt_dir>/semantic_segments.json)")
    parser.add_argument("--model", type=str, default="google/gemini-2.5-flash")

    args = parser.parse_args()

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("ERROR: OPENROUTER_API_KEY not set")
        sys.exit(1)

    # Parse and merge SRT
    print(f"[1/3] Parsing SRT: {args.srt}")
    entries = parse_srt(args.srt)
    print(f"  {len(entries)} raw entries, filtering to <{args.max_sec}s")

    transcript = merge_srt_to_text(entries, max_sec=args.max_sec)
    print(f"  Merged transcript: {len(transcript)} chars")

    # Show transcript preview
    print(f"\n--- Transcript preview (first 500 chars) ---")
    print(transcript[:500])
    print(f"--- end preview ---\n")

    # Call LLM
    print(f"[2/3] Calling LLM for semantic segmentation ({args.model}) ...")
    segments = call_llm_segmentation(transcript, api_key, args.model)
    print(f"  Got {len(segments)} segments")

    # Save
    out_path = args.output or str(Path(args.srt).parent / "semantic_segments.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(segments, f, indent=2, ensure_ascii=False)
    print(f"\n[3/3] Saved to {out_path}")

    # Print summary
    print(f"\n{'='*60}")
    print(f"{'Idx':>4} {'Start':>8} {'End':>8} {'Dur':>6}  Title")
    print(f"{'-'*60}")
    for seg in segments:
        dur = seg["end_sec"] - seg["start_sec"]
        print(f"{seg['index']:>4} {_fmt(seg['start_sec']):>8} {_fmt(seg['end_sec']):>8} {dur:>5.1f}s  {seg['title']}")


if __name__ == "__main__":
    main()
