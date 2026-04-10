#!/usr/bin/env python3
"""
Video Segmentation + Keyframe Description Demo

Two segmentation modes:
  - scene_detect: dynamic scene boundaries via frame difference
  - fixed: fixed-length segments (e.g., every 5 seconds)

For each segment: extract keyframes, align SRT subtitles, call VLM for description.
Output: segments.json + report.md
"""

import argparse
import base64
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    index: int
    start_sec: float
    end_sec: float
    start_frame: int
    end_frame: int
    title: str = ""
    keyframe_paths: List[str] = field(default_factory=list)
    transcript: str = ""
    vlm_description: str = ""


# ---------------------------------------------------------------------------
# SRT parser
# ---------------------------------------------------------------------------

def parse_srt(srt_path: str) -> List[dict]:
    """Parse SRT file into list of {start, end, text} dicts (times in seconds)."""
    if not os.path.exists(srt_path):
        return []

    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = re.split(r"\n\s*\n", content.strip())
    entries = []

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        # line 0: index, line 1: timestamps, line 2+: text
        ts_match = re.match(
            r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",
            lines[1],
        )
        if not ts_match:
            continue
        g = [int(x) for x in ts_match.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        text = " ".join(lines[2:]).strip()
        # strip HTML-like tags from auto subs
        text = re.sub(r"<[^>]+>", "", text)
        entries.append({"start": start, "end": end, "text": text})

    return entries


def get_transcript_for_range(srt_entries: List[dict], start_sec: float, end_sec: float) -> str:
    """Get concatenated subtitle text overlapping [start_sec, end_sec)."""
    texts = []
    seen = set()
    for e in srt_entries:
        if e["end"] <= start_sec or e["start"] >= end_sec:
            continue
        t = e["text"].strip()
        if t and t not in seen:
            seen.add(t)
            texts.append(t)
    return " ".join(texts)


# ---------------------------------------------------------------------------
# Video utilities
# ---------------------------------------------------------------------------

def get_video_info(video_path: str) -> dict:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return {
        "fps": fps,
        "frame_count": frame_count,
        "duration": frame_count / fps if fps > 0 else 0,
        "width": w,
        "height": h,
    }


def detect_scene_boundaries(video_path: str, threshold: float = 25.0, min_scene_sec: float = 2.0) -> List[int]:
    """Return list of frame indices marking scene starts (always includes 0)."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    min_frames = int(min_scene_sec * fps)

    boundaries = [0]
    prev_gray = None
    idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if prev_gray is not None:
            diff_score = np.mean(cv2.absdiff(prev_gray, gray))
            if diff_score > threshold and idx - boundaries[-1] >= min_frames:
                boundaries.append(idx)
        prev_gray = gray
        idx += 1

    cap.release()
    print(f"[scene_detect] Detected {len(boundaries)} scene boundaries (threshold={threshold}, min_sec={min_scene_sec})")
    return boundaries


def build_segments_from_boundaries(boundaries: List[int], total_frames: int, fps: float) -> List[Segment]:
    """Convert frame boundary list into Segment objects."""
    segments = []
    for i, start_f in enumerate(boundaries):
        end_f = boundaries[i + 1] if i + 1 < len(boundaries) else total_frames
        segments.append(Segment(
            index=i,
            start_sec=start_f / fps,
            end_sec=end_f / fps,
            start_frame=start_f,
            end_frame=end_f,
        ))
    return segments


def build_segments_fixed(total_frames: int, fps: float, interval_sec: float) -> List[Segment]:
    """Split video into fixed-length segments."""
    duration = total_frames / fps
    segments = []
    t = 0.0
    idx = 0
    while t < duration:
        end_t = min(t + interval_sec, duration)
        segments.append(Segment(
            index=idx,
            start_sec=t,
            end_sec=end_t,
            start_frame=int(t * fps),
            end_frame=int(end_t * fps),
        ))
        t = end_t
        idx += 1
    print(f"[fixed] Created {len(segments)} segments at {interval_sec}s intervals")
    return segments


# ---------------------------------------------------------------------------
# Keyframe extraction per segment
# ---------------------------------------------------------------------------

def extract_keyframes_for_segments(
    video_path: str,
    segments: List[Segment],
    output_dir: str,
    frames_per_segment: int = 2,
    keyframe_interval_sec: float = 0.0,
) -> None:
    """Extract keyframes for each segment and populate segment.keyframe_paths.

    Two modes:
    - frames_per_segment > 0 and keyframe_interval_sec == 0: uniform N frames per segment
    - keyframe_interval_sec > 0: one frame every N seconds within each segment
    """
    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS)

    for seg in segments:
        span = seg.end_frame - seg.start_frame
        if span <= 0:
            continue

        if keyframe_interval_sec > 0:
            # interval-based: one frame every N seconds
            interval_frames = int(keyframe_interval_sec * fps)
            indices = list(range(seg.start_frame, seg.end_frame, max(interval_frames, 1)))
            if not indices:
                indices = [seg.start_frame]
        else:
            # uniform N frames per segment
            n = min(frames_per_segment, span)
            indices = [seg.start_frame + int(i * span / n) for i in range(n)]

        paths = []
        for fi in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
            ret, frame = cap.read()
            if not ret:
                continue
            fname = f"seg{seg.index:03d}_frame{fi:06d}.jpg"
            fpath = os.path.join(output_dir, fname)
            cv2.imwrite(fpath, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            paths.append(fpath)
        seg.keyframe_paths = paths

    cap.release()
    total_kf = sum(len(s.keyframe_paths) for s in segments)
    print(f"[keyframes] Extracted {total_kf} keyframes across {len(segments)} segments -> {output_dir}")


# ---------------------------------------------------------------------------
# Load pre-computed semantic segments
# ---------------------------------------------------------------------------

def load_semantic_segments(json_path: str, fps: float, max_sec: float = 0.0) -> List[Segment]:
    """Load segments from semantic_segments.json (output of srt2segment.py)."""
    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    segments = []
    for s in raw:
        start = s["start_sec"]
        end = s["end_sec"]
        # filter by max_sec
        if max_sec > 0 and start >= max_sec:
            continue
        if max_sec > 0 and end > max_sec:
            end = max_sec
        segments.append(Segment(
            index=len(segments),
            start_sec=start,
            end_sec=end,
            start_frame=int(start * fps),
            end_frame=int(end * fps),
            title=s.get("title", ""),
        ))

    print(f"[semantic] Loaded {len(segments)} segments from {json_path}" +
          (f" (clamped to {max_sec}s)" if max_sec > 0 else ""))
    return segments


# ---------------------------------------------------------------------------
# VLM description via OpenRouter
# ---------------------------------------------------------------------------

def encode_image_base64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def describe_segment_vlm(
    seg: Segment,
    api_key: str,
    model: str = "google/gemini-2.5-flash",
) -> str:
    """Call OpenRouter VLM to describe a segment based on its keyframes."""
    import requests

    if not seg.keyframe_paths:
        return "(no keyframes)"

    # Build multimodal content
    content_parts = []
    for kf in seg.keyframe_paths:
        b64 = encode_image_base64(kf)
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
        })

    time_range = f"{seg.start_sec:.1f}s - {seg.end_sec:.1f}s"
    transcript_hint = f'\nNarration during this segment: "{seg.transcript}"' if seg.transcript else ""

    content_parts.append({
        "type": "text",
        "text": (
            f"These are keyframes from a hardware assembly video segment ({time_range}).{transcript_hint}\n"
            "Provide TWO sections:\n"
            "1. **Description**: Describe what is happening in 2-3 sentences. "
            "Focus on the main action, components being assembled, and any text visible on screen.\n"
            "2. **Tools**: List ONLY the tools and consumable supplies the person is USING to perform the work. "
            "Tools are things you hold and operate with (soldering iron, screwdriver, pliers, tweezers, lighter, multimeter). "
            "Consumable supplies are materials that assist assembly (solder, flux, blue Loctite, electrical tape, heat shrink tubing, zip ties, blue tack, double-sided tape). "
            "Do NOT list parts/components being assembled (motors, ESC, frame, flight controller, camera, receiver, wires, screws, capacitor, connector). "
            "Those are PARTS, not tools.\n"
            "Format each as [TOOL: name]. If no tools are visible or mentioned, write [TOOL: none]."
        ),
    })

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content_parts}],
        "max_tokens": 500,
        "temperature": 0.3,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    url = "https://openrouter.ai/api/v1/chat/completions"
    max_retries = 3

    for attempt in range(max_retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            if resp.status_code >= 500 or resp.status_code == 429:
                wait = 3 * (attempt + 1)
                print(f"  [vlm] API {resp.status_code}, retrying in {wait}s ...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            if attempt >= max_retries - 1:
                return f"(VLM error: {e})"
            time.sleep(3 * (attempt + 1))

    return "(VLM error: retries exhausted)"


def describe_all_segments(segments: List[Segment], api_key: str, model: str) -> None:
    """Describe all segments via VLM, populating seg.vlm_description."""
    total = len(segments)
    for i, seg in enumerate(segments):
        print(f"  [vlm] Describing segment {i+1}/{total} ({seg.start_sec:.1f}s - {seg.end_sec:.1f}s) ...")
        seg.vlm_description = describe_segment_vlm(seg, api_key, model)
        # rate limit
        if i < total - 1:
            time.sleep(0.5)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def fmt_time(sec: float) -> str:
    m, s = divmod(sec, 60)
    return f"{int(m):02d}:{s:05.2f}"


def save_results(segments: List[Segment], output_dir: str, video_info: dict, report_name: str = "report.md") -> Tuple[str, str]:
    """Save segments.json and report. Returns (json_path, md_path)."""
    os.makedirs(output_dir, exist_ok=True)

    # JSON
    data = {
        "video_info": video_info,
        "segment_count": len(segments),
        "segments": [asdict(s) for s in segments],
    }
    json_path = os.path.join(output_dir, "segments.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    # Markdown report
    md_lines = [
        "# Video Segmentation Report\n",
        f"**Duration:** {video_info['duration']:.1f}s | "
        f"**Resolution:** {video_info['width']}x{video_info['height']} | "
        f"**FPS:** {video_info['fps']:.2f} | "
        f"**Segments:** {len(segments)}\n",
        "---\n",
    ]

    for seg in segments:
        title_suffix = f" — {seg.title}" if seg.title else ""
        md_lines.append(f"## Segment {seg.index} [{fmt_time(seg.start_sec)} - {fmt_time(seg.end_sec)}]{title_suffix}\n")

        # keyframe thumbnails — horizontal scroll row
        if seg.keyframe_paths:
            img_tags = " ".join(
                f'<img src="keyframes/{Path(p).name}" height="120">'
                for p in seg.keyframe_paths
            )
            md_lines.append(f'<div style="overflow-x:auto;white-space:nowrap;padding:4px 0">{img_tags}</div>\n')

        if seg.vlm_description:
            md_lines.append(f"**Visual:** {seg.vlm_description}\n")

        if seg.transcript:
            md_lines.append(f"<details><summary>Transcript</summary>\n\n{seg.transcript}\n\n</details>\n")

        md_lines.append("")

    md_path = os.path.join(output_dir, report_name)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"[output] Saved {json_path}")
    print(f"[output] Saved {md_path}")
    return json_path, md_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Video segmentation + keyframe description")
    parser.add_argument("video", help="Path to video file")
    parser.add_argument("--mode", choices=["scene_detect", "fixed", "semantic"], default="fixed",
                        help="Segmentation mode (default: fixed)")
    parser.add_argument("--segments-json", type=str, default=None,
                        help="Pre-computed segments JSON (from srt2segment.py). Implies --mode semantic")
    parser.add_argument("--max-sec", type=float, default=0.0,
                        help="Only process up to this time in seconds (0=no limit)")
    parser.add_argument("--interval", type=float, default=5.0,
                        help="Segment length in seconds for fixed mode (default: 5)")
    parser.add_argument("--threshold", type=float, default=25.0,
                        help="Scene detection threshold 0-255 (default: 25)")
    parser.add_argument("--min-scene", type=float, default=2.0,
                        help="Minimum scene duration in seconds (default: 2)")
    parser.add_argument("--frames-per-seg", type=int, default=2,
                        help="Keyframes to extract per segment (default: 2)")
    parser.add_argument("--keyframe-interval", type=float, default=0.0,
                        help="Extract one keyframe every N seconds (overrides --frames-per-seg)")
    parser.add_argument("--srt", type=str, default=None,
                        help="Path to SRT subtitle file for transcript alignment")
    parser.add_argument("--output", type=str, default=None,
                        help="Output directory (default: ./output)")
    parser.add_argument("--report-name", type=str, default="report.md",
                        help="Report filename (default: report.md)")
    parser.add_argument("--model", type=str, default="google/gemini-2.5-flash",
                        help="OpenRouter model for VLM description")
    parser.add_argument("--no-vlm", action="store_true",
                        help="Skip VLM description (keyframes + subtitles only)")

    args = parser.parse_args()

    # --segments-json implies semantic mode
    if args.segments_json:
        args.mode = "semantic"

    # Resolve paths
    script_dir = Path(__file__).resolve().parent
    output_dir = Path(args.output) if args.output else script_dir / "output"
    keyframe_dir = output_dir / "keyframes"

    # Video info
    print(f"=== Video Segmentation Demo ===")
    info = get_video_info(args.video)
    print(f"Video: {args.video}")
    print(f"Duration: {info['duration']:.1f}s | {info['width']}x{info['height']} @ {info['fps']:.2f}fps")
    if args.max_sec > 0:
        print(f"Processing up to: {fmt_time(args.max_sec)}")

    # Step 1: Segment
    print(f"\n[1/4] Segmenting video (mode={args.mode}) ...")
    if args.mode == "semantic":
        segments = load_semantic_segments(args.segments_json, info["fps"], args.max_sec)
    elif args.mode == "scene_detect":
        boundaries = detect_scene_boundaries(args.video, args.threshold, args.min_scene)
        segments = build_segments_from_boundaries(boundaries, info["frame_count"], info["fps"])
        if args.max_sec > 0:
            segments = [s for s in segments if s.start_sec < args.max_sec]
            if segments and segments[-1].end_sec > args.max_sec:
                segments[-1].end_sec = args.max_sec
                segments[-1].end_frame = int(args.max_sec * info["fps"])
    else:
        effective_duration = args.max_sec if args.max_sec > 0 else info["duration"]
        effective_frames = int(effective_duration * info["fps"])
        segments = build_segments_fixed(effective_frames, info["fps"], args.interval)

    # Step 2: Extract keyframes
    kf_desc = f"every {args.keyframe_interval}s" if args.keyframe_interval > 0 else f"{args.frames_per_seg} per segment"
    print(f"\n[2/4] Extracting keyframes ({kf_desc}) ...")
    extract_keyframes_for_segments(
        args.video, segments, str(keyframe_dir),
        frames_per_segment=args.frames_per_seg,
        keyframe_interval_sec=args.keyframe_interval,
    )

    # Step 3: Align subtitles
    print(f"\n[3/4] Aligning subtitles ...")
    srt_entries = []
    if args.srt:
        srt_entries = parse_srt(args.srt)
        print(f"  Loaded {len(srt_entries)} subtitle entries from {args.srt}")
    else:
        # auto-detect SRT next to video
        video_stem = Path(args.video).stem
        for suffix in [".en-orig.srt", ".en.srt", ".srt"]:
            candidate = Path(args.video).parent / (video_stem + suffix)
            if candidate.exists():
                srt_entries = parse_srt(str(candidate))
                print(f"  Auto-detected SRT: {candidate} ({len(srt_entries)} entries)")
                break
    if not srt_entries:
        print("  No SRT found, skipping transcript alignment")

    for seg in segments:
        seg.transcript = get_transcript_for_range(srt_entries, seg.start_sec, seg.end_sec)

    # Step 4: VLM description
    if args.no_vlm:
        print(f"\n[4/4] VLM description skipped (--no-vlm)")
    else:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            print(f"\n[4/4] WARNING: OPENROUTER_API_KEY not set, skipping VLM description")
        else:
            print(f"\n[4/4] Generating VLM descriptions ({args.model}) ...")
            describe_all_segments(segments, api_key, args.model)

    # Save
    print(f"\n[output] Saving results ...")
    save_results(segments, str(output_dir), info, report_name=args.report_name)

    # Summary
    print(f"\n=== Done ===")
    print(f"Segments: {len(segments)}")
    described = sum(1 for s in segments if s.vlm_description and not s.vlm_description.startswith("("))
    print(f"VLM described: {described}/{len(segments)}")
    with_transcript = sum(1 for s in segments if s.transcript)
    print(f"With transcript: {with_transcript}/{len(segments)}")


if __name__ == "__main__":
    main()
