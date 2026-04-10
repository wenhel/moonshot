#!/usr/bin/env python3
"""
Moonshot Video Report Pipeline — thin orchestrator

Composes:
  - processors/keyframe_extractor.py  (KeyFrameExtractor)
  - task/assembly_video_labeler.py    (AssemblyVideoLabeler)
  - task/report_writer.py             (ReportWriter)
  - config/                           (YAML configs)

Usage:
  cd moonshot/code
  python -m task.video_report_pipeline VIDEO [options]
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

from processors.keyframe_extractor import KeyFrameExtractor
from task.assembly_video_labeler import AssemblyVideoLabeler
from task.report_writer import ReportWriter, fmt_time


# ---------------------------------------------------------------------------
# Segment dataclass — copied verbatim from demo/segment_video.py L31-41
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
# SRT parser — copied verbatim from demo/segment_video.py L48-92
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
# Config loading
# ---------------------------------------------------------------------------

def load_pipeline_config(config_dir: str) -> dict:
    """Load config/defaults/pipeline.yaml."""
    path = os.path.join(config_dir, "defaults", "pipeline.yaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_extractor_config(pipeline_cfg: dict, extractor_name: str) -> dict:
    """Get a named extractor preset from pipeline config, merged with defaults."""
    defaults = pipeline_cfg.get("extractor", {})
    extractors = pipeline_cfg.get("extractors", [])

    entry = None
    for e in extractors:
        if e.get("name") == extractor_name:
            entry = e
            break
    if entry is None:
        available = [e.get("name", "?") for e in extractors]
        raise ValueError(f"Extractor '{extractor_name}' not found. Available: {available}")

    merged = dict(defaults)
    merged.update(entry)
    return merged


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_extract(
    video_path: str,
    out_dir: str,
    extractor_cfg: dict,
    srt_path: Optional[str] = None,
    max_sec: float = 0.0,
) -> List[Segment]:
    """Run extraction: segment video + extract keyframes + align transcript."""

    # Probe video
    kfe = KeyFrameExtractor(method="uniform")
    video_info = kfe.get_video_info(video_path)
    fps = video_info["fps"]
    frame_count = video_info["frame_count"]
    duration = video_info["duration"]

    print(f"Video: {video_path}")
    print(f"Duration: {duration:.1f}s | {video_info['width']}x{video_info['height']} @ {fps:.2f}fps")

    effective_duration = max_sec if max_sec > 0 else duration
    effective_frames = int(effective_duration * fps)

    mode = extractor_cfg.get("mode", "fixed")
    interval_sec = extractor_cfg.get("interval_sec", 30.0)
    keyframe_interval_sec = extractor_cfg.get("keyframe_interval_sec", 5.0)
    max_frames = extractor_cfg.get("max_frames_per_segment", 0)

    # Step 1: Segmentation
    print(f"\n[1/3] Segmenting (mode={mode}) ...")
    segments = []

    if mode == "fixed":
        # --- build_segments_fixed logic from segment_video.py L162-180 ---
        t = 0.0
        idx = 0
        while t < effective_duration:
            end_t = min(t + interval_sec, effective_duration)
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

    elif mode == "scene_detect":
        # Use KeyFrameExtractor's scene_detect via SceneDetector
        from processors.scene_detector import SceneDetector
        threshold = extractor_cfg.get("threshold", 25.0)
        min_scene_sec = extractor_cfg.get("min_scene_sec", 2.0)
        compare_interval_sec = extractor_cfg.get("compare_interval_sec", 0.0)

        detector = SceneDetector(
            threshold=threshold,
            min_scene_duration=min_scene_sec,
        )

        # If compare_interval_sec > 0, we do frame-skip detection
        if compare_interval_sec > 0:
            import cv2
            import numpy as np
            cap = cv2.VideoCapture(video_path)
            skip = max(1, int(compare_interval_sec * fps))
            min_frames = int(min_scene_sec * fps)
            boundaries = [0]
            prev_gray = None
            idx = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                if idx % skip == 0:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    if prev_gray is not None:
                        diff_score = np.mean(cv2.absdiff(prev_gray, gray))
                        if diff_score > threshold and idx - boundaries[-1] >= min_frames:
                            boundaries.append(idx)
                    prev_gray = gray
                idx += 1
            cap.release()
        else:
            boundaries = detector.detect_scenes(video_path)

        # Build raw segments from boundaries
        raw_segments = []
        for i, start_f in enumerate(boundaries):
            end_f = boundaries[i + 1] if i + 1 < len(boundaries) else effective_frames
            seg_start = start_f / fps
            seg_end = end_f / fps
            if max_sec > 0 and seg_start >= max_sec:
                break
            if max_sec > 0 and seg_end > max_sec:
                seg_end = max_sec
                end_f = int(max_sec * fps)
            raw_segments.append((seg_start, seg_end, start_f, end_f))

        # Merge based on min_keyframes:
        #   Calculate how many keyframes each segment would get,
        #   if < min_keyframes, merge backward into previous segment,
        #   repeat until all segments have >= min_keyframes.
        min_kf = extractor_cfg.get("min_keyframes", 5)
        kf_interval = keyframe_interval_sec if keyframe_interval_sec > 0 else 0

        def _count_kf(start_f, end_f):
            """Predict keyframe count for a segment."""
            span = end_f - start_f
            if span <= 0:
                return 0
            if kf_interval > 0:
                interval_frames = int(kf_interval * fps)
                return len(range(start_f, end_f, max(interval_frames, 1)))
            else:
                fps_val = extractor_cfg.get("frames_per_segment", 2)
                return min(fps_val, span)

        merged = list(raw_segments)
        changed = True
        while changed:
            changed = False
            new_merged = []
            for seg in merged:
                if new_merged and _count_kf(seg[2], seg[3]) < min_kf:
                    # Merge into previous
                    prev = new_merged[-1]
                    new_merged[-1] = (prev[0], seg[1], prev[2], seg[3])
                    changed = True
                else:
                    new_merged.append(seg)
            merged = new_merged

        # Check last segment
        if len(merged) > 1 and _count_kf(merged[-1][2], merged[-1][3]) < min_kf:
            prev = merged[-2]
            last = merged[-1]
            merged[-2] = (prev[0], last[1], prev[2], last[3])
            merged.pop()

        n_before = len(raw_segments)
        n_after = len(merged)
        for i, (seg_start, seg_end, start_f, end_f) in enumerate(merged):
            segments.append(Segment(
                index=i,
                start_sec=seg_start,
                end_sec=seg_end,
                start_frame=start_f,
                end_frame=end_f,
            ))
        if n_before != n_after:
            print(f"[scene_detect] {n_before} raw -> {n_after} after merge (min_keyframes={min_kf})")
        print(f"[scene_detect] Created {len(segments)} segments from {len(boundaries)} boundaries")

    else:
        raise ValueError(f"Unknown mode: {mode}")

    # Step 2: Extract keyframes
    kf_dir = os.path.join(out_dir, "keyframes")
    os.makedirs(kf_dir, exist_ok=True)

    print(f"\n[2/3] Extracting keyframes ...")
    import cv2
    cap = cv2.VideoCapture(video_path)

    for seg in segments:
        span = seg.end_frame - seg.start_frame
        if span <= 0:
            continue

        if keyframe_interval_sec > 0:
            interval_frames = int(keyframe_interval_sec * fps)
            indices = list(range(seg.start_frame, seg.end_frame, max(interval_frames, 1)))
            if not indices:
                indices = [seg.start_frame]
        else:
            frames_per_seg = extractor_cfg.get("frames_per_segment", 2)
            n = min(frames_per_seg, span)
            indices = [seg.start_frame + int(i * span / n) for i in range(n)]

        # Apply max_frames cap
        if max_frames > 0 and len(indices) > max_frames:
            step = len(indices) / max_frames
            indices = [indices[int(i * step)] for i in range(max_frames)]

        paths = []
        for fi in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
            ret, frame = cap.read()
            if not ret:
                continue
            fname = f"seg{seg.index:03d}_frame{fi:06d}.jpg"
            fpath = os.path.join(kf_dir, fname)
            cv2.imwrite(fpath, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            paths.append(fpath)
        seg.keyframe_paths = paths

    cap.release()
    total_kf = sum(len(s.keyframe_paths) for s in segments)
    print(f"[keyframes] Extracted {total_kf} keyframes across {len(segments)} segments")

    # Step 3: Transcript alignment
    print(f"\n[3/3] Aligning transcript ...")
    srt_entries = []
    if srt_path:
        srt_entries = parse_srt(srt_path)
        print(f"  Loaded {len(srt_entries)} subtitle entries")
    else:
        # Auto-detect SRT next to video
        video_stem = Path(video_path).stem
        for suffix in [".en-orig.srt", ".en.srt", ".srt"]:
            candidate = Path(video_path).parent / (video_stem + suffix)
            if candidate.exists():
                srt_entries = parse_srt(str(candidate))
                print(f"  Auto-detected SRT: {candidate} ({len(srt_entries)} entries)")
                break
    if not srt_entries:
        print("  No SRT found, transcripts will be empty")

    for seg in segments:
        seg.transcript = get_transcript_for_range(srt_entries, seg.start_sec, seg.end_sec)

    # Save segments.json
    os.makedirs(out_dir, exist_ok=True)
    data = {
        "video_info": video_info,
        "segment_count": len(segments),
        "segments": [asdict(s) for s in segments],
    }
    json_path = os.path.join(out_dir, "segments.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n[output] Saved {json_path}")

    with_transcript = sum(1 for s in segments if s.transcript)
    print(f"=== Extract done: {len(segments)} segments, {total_kf} keyframes, {with_transcript} with transcript ===")
    return segments


def run_label(
    out_dir: str,
    labeler: AssemblyVideoLabeler,
    report_name: str = "report.md",
    dryrun: bool = False,
) -> None:
    """Run labeling: load segments.json, call VLM, write report.md."""

    json_path = os.path.join(out_dir, "segments.json")
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"segments.json not found in {out_dir}. Run --steps extract first.")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    video_info = data["video_info"]

    # Reconstruct Segment objects
    segments = []
    for s in data["segments"]:
        segments.append(Segment(
            index=s["index"],
            start_sec=s["start_sec"],
            end_sec=s["end_sec"],
            start_frame=s["start_frame"],
            end_frame=s["end_frame"],
            title=s.get("title", ""),
            keyframe_paths=s.get("keyframe_paths", []),
            transcript=s.get("transcript", ""),
        ))

    print(f"[label] Loaded {len(segments)} segments from {json_path}")
    print(f"[label] Labeler: {labeler.name} ({labeler.model})")

    if dryrun:
        if not segments:
            print("  No segments to label")
            return
        first = segments[0]
        print(f"  [dryrun] Calling VLM on segment 0 only ...")
        result = labeler.label_segment(
            keyframe_paths=first.keyframe_paths,
            time_range=f"{first.start_sec:.1f}s - {first.end_sec:.1f}s",
            transcript=first.transcript,
        )
        print(f"\n  --- VLM response ---\n  {result}\n  --- end ---")
        print(f"[dryrun] OK. report.md NOT written.")
        return

    print(f"\n[label] Generating VLM descriptions ...")
    labeler.label_all_segments(segments)

    writer = ReportWriter()
    writer.write(segments, out_dir, video_info, report_name=report_name)

    described = sum(1 for s in segments if s.vlm_description and not s.vlm_description.startswith("("))
    print(f"=== Label done: {described}/{len(segments)} described ===")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Moonshot video report pipeline",
        usage="cd moonshot/code && python -m task.video_report_pipeline VIDEO [options]",
    )
    parser.add_argument("video", nargs="?", help="Path to video file")
    parser.add_argument("--out", type=str, default="output",
                        help="Output directory (default: output)")
    parser.add_argument("--config-dir", type=str, default="config",
                        help="Path to config/ directory (default: config)")
    parser.add_argument("--extractor", type=str, default="fixed-keyframe",
                        help="Extractor preset name (default: fixed-keyframe)")
    parser.add_argument("--labeler", type=str, default="assembly_structured",
                        help="Labeler name matching config/labeler/*.yaml (default: assembly_structured)")
    parser.add_argument("--srt", type=str, default=None,
                        help="SRT subtitle file (auto-detected if omitted)")
    parser.add_argument("--max-sec", type=float, default=0.0,
                        help="Process up to S seconds (0 = full video)")
    parser.add_argument("--report-name", type=str, default="report.md",
                        help="Report filename (default: report.md)")
    # CLI overrides for extractor params
    parser.add_argument("--interval", type=float, default=None,
                        help="Override interval_sec")
    parser.add_argument("--keyframe-interval", type=float, default=None,
                        help="Override keyframe_interval_sec")
    parser.add_argument("--max-frames", type=int, default=None,
                        help="Override max_frames_per_segment")
    parser.add_argument("--steps", choices=["extract", "label", "all"], default="all",
                        help="extract / label / all (default: all)")
    parser.add_argument("--dryrun", action="store_true",
                        help="VLM call on segment 0 only, no report.md")
    parser.add_argument("--config-dryrun", action="store_true",
                        help="Print config summary and exit")

    args = parser.parse_args()

    config_dir = args.config_dir

    # Config dryrun
    if args.config_dryrun:
        pipeline_cfg = load_pipeline_config(config_dir)
        print("=== Extractor presets ===")
        for e in pipeline_cfg.get("extractors", []):
            merged = dict(pipeline_cfg.get("extractor", {}))
            merged.update(e)
            print(f"\n  {e['name']} (mode={e.get('mode', '?')}):")
            for k, v in merged.items():
                if k != "name":
                    print(f"    {k}: {v}")

        print("\n=== Labelers ===")
        labeler_dir = os.path.join(config_dir, "labeler")
        if os.path.isdir(labeler_dir):
            for f in sorted(os.listdir(labeler_dir)):
                if f.endswith(".yaml"):
                    name = f.replace(".yaml", "")
                    with open(os.path.join(labeler_dir, f), "r") as fh:
                        cfg = yaml.safe_load(fh)
                    desc = cfg.get("labeler_info", {}).get("description", "")
                    gen = cfg.get("generation_config", {})
                    print(f"\n  {name}:")
                    print(f"    description: {desc}")
                    print(f"    temperature: {gen.get('temperature', '(default)')}")
                    print(f"    max_tokens: {gen.get('max_tokens', '(default)')}")
        return

    # Validate args
    if args.steps != "label" and not args.video:
        parser.error("video is required (unless --steps label)")

    # Load extractor config
    extractor_cfg = {}
    if args.steps in ("all", "extract"):
        pipeline_cfg = load_pipeline_config(config_dir)
        extractor_cfg = get_extractor_config(pipeline_cfg, args.extractor)
        # CLI overrides
        if args.interval is not None:
            extractor_cfg["interval_sec"] = args.interval
        if args.keyframe_interval is not None:
            extractor_cfg["keyframe_interval_sec"] = args.keyframe_interval
        if args.max_frames is not None:
            extractor_cfg["max_frames_per_segment"] = args.max_frames

    # Load labeler
    labeler = None
    if args.steps in ("all", "label"):
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            print("ERROR: OPENROUTER_API_KEY required for labeling")
            sys.exit(1)
        labeler = AssemblyVideoLabeler.from_config(config_dir, args.labeler, api_key)

    # Run
    if args.steps == "extract":
        run_extract(args.video, args.out, extractor_cfg, srt_path=args.srt, max_sec=args.max_sec)

    elif args.steps == "label":
        run_label(args.out, labeler, report_name=args.report_name, dryrun=args.dryrun)

    elif args.steps == "all":
        segments = run_extract(args.video, args.out, extractor_cfg, srt_path=args.srt, max_sec=args.max_sec)

        if args.dryrun:
            if not segments:
                print("No segments to label")
                return
            first = segments[0]
            print(f"\n[dryrun] Calling VLM on segment 0 ...")
            result = labeler.label_segment(
                keyframe_paths=first.keyframe_paths,
                time_range=f"{first.start_sec:.1f}s - {first.end_sec:.1f}s",
                transcript=first.transcript,
            )
            print(f"\n  --- VLM response ---\n  {result}\n  --- end ---")
            print(f"[dryrun] OK.")
            return

        print(f"\n[label] Generating VLM descriptions ...")
        labeler.label_all_segments(segments)

        writer = ReportWriter()
        video_info = KeyFrameExtractor(method="uniform").get_video_info(args.video)
        writer.write(segments, args.out, video_info, report_name=args.report_name)

        described = sum(1 for s in segments if s.vlm_description and not s.vlm_description.startswith("("))
        with_transcript = sum(1 for s in segments if s.transcript)
        print(f"\n=== Done: {len(segments)} segments, {described} described, {with_transcript} with transcript ===")


if __name__ == "__main__":
    main()
