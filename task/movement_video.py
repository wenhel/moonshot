#!/usr/bin/env python3
"""
Movement Video Demo — render a segment with movement annotations overlaid.

For each movement event, the annotation is displayed on the video frames
that fall between the keyframes where it was observed.

Usage:
  cd moonshot/code
  python -m task.movement_video SEG_INDEX [--src-dir DIR] [--video PATH]
"""

import argparse
import json
import os
import re
import cv2
import textwrap
from pathlib import Path
from typing import List, Tuple, Optional

from tools.smart_partition import SmartPartitionTool, Zone
from core.interfaces import LabelerInput
from core.openrouter_labeler import OpenRouterLabeler


# ---------------------------------------------------------------------------
# Step 1: Re-label with frame numbers
# ---------------------------------------------------------------------------

MOVEMENT_PROMPT = """These are {n_frames} keyframes from a hardware assembly video segment ({time_range}).
The keyframes are sampled at these frame positions (global video frame IDs):
{frame_id_list}

This workspace has 4 functional zones:
- **workspace**: The active assembly area where hands perform work
- **tools**: Where screwdrivers/hex drivers rest
- **parts**: Where frame components and structural parts are stored
- **screws_board**: The whiteboard showing screws by type

Zone coordinates: {zone_info}

For EACH distinct movement or action you observe, report:
- Which keyframes it spans (use global frame IDs)
- What moved and between which zones

Format each movement as:
[MOVE] #<start_frame>-#<end_frame> | <object> | <from_zone> -> <to_zone> | <brief description>

Example:
[MOVE] #3000-#3250 | hex screwdriver 2.0mm | tools -> workspace | Person picks up screwdriver
[MOVE] #3250-#3500 | M3x16mm screw | screws_board -> workspace | Screw inserted into frame

Also provide a brief **Summary** of the overall activity in 1-2 sentences.

Return movements first, then summary."""


def label_segment_with_frames(
    labeler: OpenRouterLabeler,
    keyframe_paths: List[str],
    frame_ids: List[int],
    time_range: str,
    zones: List[dict],
) -> str:
    """Label a segment with frame-number-aware movement prompt."""

    zone_info = ", ".join(
        f"{z['name']}=({z['bbox'][0]:.2f},{z['bbox'][1]:.2f},{z['bbox'][2]:.2f},{z['bbox'][3]:.2f})"
        for z in zones
    )
    frame_id_list = ", ".join(f"#{fid}" for fid in frame_ids)

    prompt = MOVEMENT_PROMPT.format(
        n_frames=len(keyframe_paths),
        time_range=time_range,
        frame_id_list=frame_id_list,
        zone_info=zone_info,
    )

    inp = LabelerInput(
        text="",
        image_paths=keyframe_paths,
        instruction=prompt,
    )
    output = labeler.label(inp)
    return output.result.get("content", "")


def parse_movements(text: str) -> List[dict]:
    """Parse [MOVE] lines into structured dicts."""
    moves = []
    pattern = r'\[MOVE\]\s*#(\d+)\s*-\s*#(\d+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*->\s*(.+?)\s*\|\s*(.+)'
    for m in re.finditer(pattern, text):
        moves.append({
            "start_frame": int(m.group(1)),
            "end_frame": int(m.group(2)),
            "object": m.group(3).strip(),
            "from_zone": m.group(4).strip(),
            "to_zone": m.group(5).strip(),
            "description": m.group(6).strip(),
        })
    return moves


# ---------------------------------------------------------------------------
# Step 2: Render video with movement overlay
# ---------------------------------------------------------------------------

def render_movement_video(
    video_path: str,
    start_frame: int,
    end_frame: int,
    movements: List[dict],
    zones: List[dict],
    output_path: str,
    fps: float = 25.0,
) -> str:
    """Render a video clip with movement annotations overlaid.

    Each movement is displayed on the frames it spans.
    Zone boundaries are drawn on every frame.
    """
    cap = cv2.VideoCapture(video_path)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(output_path, fourcc, fps, (w, h))

    # Zone colors
    zone_colors = {
        "workspace": (0, 255, 0),
        "tools": (255, 0, 0),
        "parts": (0, 0, 255),
        "screws_board": (255, 255, 0),
    }

    frame_idx = start_frame
    while frame_idx <= end_frame:
        ret, frame = cap.read()
        if not ret:
            break

        # Draw zone boundaries
        for z in zones:
            bbox = z.get("bbox", [0, 0, 0, 0])
            if bbox == [0, 0, 0, 0]:
                continue
            color = zone_colors.get(z["name"], (128, 128, 128))
            px1, py1 = int(bbox[0] * w), int(bbox[1] * h)
            px2, py2 = int(bbox[2] * w), int(bbox[3] * h)
            cv2.rectangle(frame, (px1, py1), (px2, py2), color, 2)
            cv2.putText(frame, z["name"], (px1 + 4, py1 + 18),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        # Find active movements for this frame
        active = [m for m in movements if m["start_frame"] <= frame_idx <= m["end_frame"]]

        # Overlay movement text in top-left
        y_offset = 30
        seg_local = frame_idx - start_frame

        # Frame counter
        cv2.putText(frame, f"Frame #{frame_idx} (seg:{seg_local})",
                    (10, y_offset), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        y_offset += 28

        for mov in active:
            text = f"{mov['object']}: {mov['from_zone']} -> {mov['to_zone']}"
            subtext = f"  #{mov['start_frame']}-#{mov['end_frame']} {mov['description']}"

            # Background rectangle for readability
            cv2.rectangle(frame, (8, y_offset - 16), (w - 8, y_offset + 32), (0, 0, 0), -1)
            cv2.putText(frame, text, (12, y_offset),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)
            y_offset += 22
            cv2.putText(frame, subtext, (12, y_offset),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)
            y_offset += 26

        writer.write(frame)
        frame_idx += 1

    cap.release()
    writer.release()
    print(f"[movement_video] Saved {output_path} ({frame_idx - start_frame} frames)")
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Movement video demo")
    parser.add_argument("seg_index", type=int, help="Segment index to render")
    parser.add_argument("--src-dir", default="output/v1_fixed-with-loc_zoom-move-description",
                        help="Dir with segments.json")
    parser.add_argument("--video",
                        default="/home/wenhel/dsta-stance-project/dsta-stance-clean-refactor-s2/moonshot/videos/correct_assemble_v1.mp4")
    parser.add_argument("--model", default="google/gemini-2.5-flash")
    parser.add_argument("--relabel", action="store_true",
                        help="Re-label movement with frame numbers (otherwise use existing)")
    args = parser.parse_args()

    with open(os.path.join(args.src_dir, "segments.json")) as f:
        data = json.load(f)

    seg = data["segments"][args.seg_index]
    zones = seg.get("zones", [])
    fps = data["video_info"]["fps"]

    # Resolve keyframe paths
    kf_paths = []
    for p in seg.get("keyframe_paths", []):
        if os.path.exists(p):
            kf_paths.append(p)
        else:
            local = os.path.join(args.src_dir, "keyframes", Path(p).name)
            if os.path.exists(local):
                kf_paths.append(local)

    # Extract frame IDs from keyframe filenames (seg000_frame000125.jpg -> 125)
    frame_ids = []
    for p in kf_paths:
        m = re.search(r'frame(\d+)', Path(p).stem)
        if m:
            frame_ids.append(int(m.group(1)))

    # Step 1: Label with frame numbers
    if args.relabel or not seg.get("movements"):
        print(f"[movement] Labeling seg{args.seg_index} with frame-aware prompt ...")
        labeler = OpenRouterLabeler(
            name="movement_labeler",
            model=args.model,
            temperature=0.2,
            max_tokens=1200,
        )
        time_range = f"{seg['start_sec']:.1f}s - {seg['end_sec']:.1f}s"
        raw = label_segment_with_frames(labeler, kf_paths, frame_ids, time_range, zones)
        print(f"\n--- VLM output ---\n{raw}\n--- end ---\n")
        movements = parse_movements(raw)
        seg["movement_raw"] = raw
        seg["movements"] = movements
    else:
        movements = seg["movements"]

    print(f"[movement] Found {len(movements)} movements:")
    for m in movements:
        print(f"  #{m['start_frame']}-#{m['end_frame']} | {m['object']} | {m['from_zone']} -> {m['to_zone']}")

    # Step 2: Render video
    out_path = os.path.join(args.src_dir, f"seg{args.seg_index:03d}_movement.mp4")
    render_movement_video(
        video_path=args.video,
        start_frame=seg["start_frame"],
        end_frame=seg["end_frame"],
        movements=movements,
        zones=zones,
        output_path=out_path,
        fps=fps,
    )

    # Save updated segments
    with open(os.path.join(args.src_dir, "segments.json"), "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
