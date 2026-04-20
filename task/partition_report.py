#!/usr/bin/env python3
"""
Partition Report — add zone partitioning + zoom to an existing segments.json.

Two prompt modes:
  --mode baseline : VLM freely names zones (no hints)
  --mode guided   : prompt specifies 4 zone categories (workspace, tools, parts, screws_board)

Usage:
  cd moonshot/code
  python -m task.partition_report OUTPUT_DIR [--mode guided|baseline] [--model MODEL]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

from tools.smart_partition import SmartPartitionTool, Zone
from tools.bbox_zoom import BboxZoomTool

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

BASELINE_PROMPT = """Analyze this image and identify all distinct functional zones where similar objects are grouped together.

For each zone, return:
- zone_name: a short descriptive snake_case name
- bbox: [x1, y1, x2, y2] as normalized coordinates where 0.0 is top-left and 1.0 is bottom-right
- objects: list of objects found in this zone
- description: one-line description of the zone

Rules:
- Zones should NOT overlap significantly.
- Cover the entire image. Every visible object should belong to a zone.
- Group objects by their functional role.
{context}

Return ONLY a JSON array."""


GUIDED_PROMPT = """Analyze this image of a hardware assembly workspace.

Identify exactly these 4 functional zones:
1. **workspace**: The area where hands/fingers are actively working or assembling. This should be a SPECIFIC region, NOT the entire image. If no hands are visible, identify the central area where assembly activity is happening or most recently happened.
2. **tools**: The area where screwdrivers / hex drivers are laid out (their home/resting position).
3. **parts**: The area where frame components, standoffs, and other structural parts are arranged (their storage position).
4. **screws_board**: The whiteboard or instruction card showing screws organized by type/size.

For each zone, return:
- zone_name: one of "workspace", "tools", "parts", "screws_board"
- bbox: [x1, y1, x2, y2] as normalized coordinates where 0.0 is top-left and 1.0 is bottom-right
- objects: list of objects found in this zone
- description: one-line description

CRITICAL RULES:
- Do NOT guess positions from prior knowledge. Look at the actual image.
- Zones may overlap slightly at edges but NO zone should fully contain another zone.
- The workspace zone MUST NOT cover the entire image. It should only cover the active working area.
- Each zone should roughly cover 15-40% of the image area, not more.
- If a zone is not visible in this frame, still include it with bbox [0,0,0,0].
{context}

Return ONLY a JSON array with exactly 4 zones."""


PROMPTS = {
    "baseline": BASELINE_PROMPT,
    "guided": GUIDED_PROMPT,
}


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def partition_segment(
    tool: SmartPartitionTool,
    keyframe_paths: List[str],
    out_dir: str,
    seg_index: int,
    zone_names: Optional[List[str]] = None,
) -> List[dict]:
    """Partition a segment: send ALL keyframes in ONE API call for consistency.

    Args:
        tool: SmartPartitionTool instance.
        keyframe_paths: list of keyframe image paths.
        out_dir: output directory for visualizations and zoom images.
        seg_index: segment index.
        zone_names: unused (kept for API compat), zones come from VLM directly.

    Returns list of zone dicts for JSON serialization.
    """
    if not keyframe_paths:
        return []

    valid_paths = [p for p in keyframe_paths if os.path.exists(p)]
    if not valid_paths:
        print(f"  [partition] WARNING: no valid keyframes for seg{seg_index:03d}")
        return []

    # ONE API call with all keyframes → one consistent set of zones
    zones = tool.partition_batch(valid_paths)
    if not zones:
        print(f"  [partition] WARNING: no zones detected for seg{seg_index:03d}")
        return []

    # Draw partition overlay on EVERY keyframe + generate zoom crops
    zoom_tool = BboxZoomTool(default_margin=0.1)
    vis_dir = os.path.join(out_dir, "overlays")
    zoom_dir = os.path.join(out_dir, "zones")
    os.makedirs(vis_dir, exist_ok=True)
    os.makedirs(zoom_dir, exist_ok=True)

    for kf_path in valid_paths:
        kf_name = Path(kf_path).stem

        # Draw overlay on this keyframe
        vis_path = os.path.join(vis_dir, f"{kf_name}_partition.jpg")
        tool.visualize(kf_path, zones, output_path=vis_path)

        # Generate zoom crops for each zone
        for zone in zones:
            if zone.bbox == (0, 0, 0, 0) or zone.bbox == (0.0, 0.0, 0.0, 0.0):
                continue
            save_path = os.path.join(zoom_dir, f"{kf_name}_{zone.name}.jpg")
            try:
                zoom_tool.zoom_from_path(kf_path, zone.bbox, save_path=save_path)
            except Exception as e:
                print(f"  [zoom] ERROR on {kf_name}/{zone.name}: {e}")

    # Save one representative partition vis at segment level
    rep_vis = os.path.join(out_dir, f"seg{seg_index:03d}_partition.jpg")
    tool.visualize(valid_paths[0], zones, output_path=rep_vis)

    # Serialize
    return [
        {
            "name": z.name,
            "bbox": list(z.bbox),
            "objects": z.objects,
            "description": z.description,
        }
        for z in zones
    ]


def run_partition(
    out_dir: str,
    mode: str = "guided",
    model: str = "google/gemini-2.5-flash",
    api_key: Optional[str] = None,
    rate_sleep: float = 1.0,
) -> None:
    """Main: load segments.json, partition each segment, write enriched output."""

    json_path = os.path.join(out_dir, "segments.json")
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"segments.json not found in {out_dir}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data["segments"]
    video_info = data["video_info"]
    prompt_template = PROMPTS[mode]

    tool = SmartPartitionTool(
        name=f"partition_{mode}",
        model=model,
        prompt_template=prompt_template,
        api_key=api_key,
        temperature=0.2,
        max_tokens=1200,
    )

    partition_out = os.path.join(out_dir, f"partitions_{mode}")
    os.makedirs(partition_out, exist_ok=True)

    print(f"[partition] Mode: {mode} | Model: {model} | Segments: {len(segments)}")
    print(f"[partition] Output: {partition_out}\n")

    for i, seg in enumerate(segments):
        # Resolve keyframe paths relative to out_dir
        kf_paths = []
        for p in seg.get("keyframe_paths", []):
            # Try as-is, then relative to out_dir parent
            if os.path.exists(p):
                kf_paths.append(p)
            else:
                # keyframe_paths in json may use old prefix — remap to local keyframes/
                local = os.path.join(out_dir, "keyframes", Path(p).name)
                if os.path.exists(local):
                    kf_paths.append(local)

        time_range = f"{seg['start_sec']:.0f}s-{seg['end_sec']:.0f}s"
        print(f"  seg{i:03d} [{time_range}] ({len(kf_paths)} keyframes) ...", end=" ")

        zn = ["workspace", "tools", "parts", "screws_board"] if mode == "guided" else None
        zones = partition_segment(tool, kf_paths, partition_out, i, zone_names=zn)
        seg["zones"] = zones
        print(f"{len(zones)} zones")

        if i < len(segments) - 1:
            time.sleep(rate_sleep)

    # Save enriched segments
    enriched_path = os.path.join(out_dir, f"segments_partitioned_{mode}.json")
    with open(enriched_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n[partition] Saved {enriched_path}")

    # Write partition report
    _write_partition_report(segments, video_info, out_dir, partition_out, mode)


def _write_partition_report(
    segments: list,
    video_info: dict,
    out_dir: str,
    partition_out: str,
    mode: str,
) -> None:
    """Write a markdown report with partition visualizations."""

    def fmt_time(sec: float) -> str:
        m, s = divmod(sec, 60)
        return f"{int(m):02d}:{s:05.2f}"

    lines = [
        f"# Partition Report ({mode})\n",
        f"**Duration:** {video_info['duration']:.1f}s | "
        f"**Resolution:** {video_info['width']}x{video_info['height']} | "
        f"**Segments:** {len(segments)}\n",
        "---\n",
    ]

    rel_partition = os.path.relpath(partition_out, out_dir)

    for seg in segments:
        i = seg["index"]
        zones = seg.get("zones", [])
        lines.append(
            f"## Segment {i} [{fmt_time(seg['start_sec'])} - {fmt_time(seg['end_sec'])}]\n"
        )

        # Keyframes with partition overlay (all keyframes in segment)
        kf_paths = seg.get("keyframe_paths", [])
        overlay_tags = []
        for p in kf_paths:
            overlay_name = f"{Path(p).stem}_partition.jpg"
            overlay_path = os.path.join(partition_out, "overlays", overlay_name)
            if os.path.exists(overlay_path):
                overlay_tags.append(
                    f'<img src="{rel_partition}/overlays/{overlay_name}" height="150">'
                )
        if overlay_tags:
            lines.append(f'<div style="overflow-x:auto;white-space:nowrap;padding:4px 0">{"  ".join(overlay_tags)}</div>\n')

        # Zone table
        if zones:
            lines.append("| Zone | Bbox | Objects |")
            lines.append("|---|---|---|")
            for z in zones:
                bbox_str = f"({z['bbox'][0]:.2f}, {z['bbox'][1]:.2f}, {z['bbox'][2]:.2f}, {z['bbox'][3]:.2f})"
                objs = ", ".join(str(o) for o in z.get("objects", [])[:5])
                lines.append(f"| {z['name']} | {bbox_str} | {objs} |")
            lines.append("")

        # Zoom thumbnails per zone
        if zones:
            kf_paths = seg.get("keyframe_paths", [])
            if kf_paths:
                first_kf = Path(kf_paths[0]).stem
                zoom_tags = []
                for z in zones:
                    zoom_name = f"{first_kf}_{z['name']}.jpg"
                    zoom_path = os.path.join(partition_out, "zones", zoom_name)
                    if os.path.exists(zoom_path):
                        zoom_tags.append(
                            f'<img src="{rel_partition}/zones/{zoom_name}" height="100" title="{z["name"]}">'
                        )
                if zoom_tags:
                    lines.append(f'<div style="overflow-x:auto;white-space:nowrap;padding:4px 0">{"  ".join(zoom_tags)}</div>\n')

        # VLM description (if exists)
        desc = seg.get("vlm_description", "")
        if desc:
            lines.append(f"<details><summary>VLM Description</summary>\n\n{desc}\n\n</details>\n")

        lines.append("")

    report_path = os.path.join(out_dir, f"report-partition-{mode}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[partition] Saved {report_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Add zone partitioning to segments")
    parser.add_argument("out_dir", help="Output directory containing segments.json")
    parser.add_argument("--mode", choices=["guided", "baseline"], default="guided",
                        help="Prompt mode: guided (4 fixed categories) or baseline (free-form)")
    parser.add_argument("--model", default="google/gemini-2.5-flash")
    parser.add_argument("--rate-sleep", type=float, default=1.0,
                        help="Sleep between segments to avoid rate limiting")
    args = parser.parse_args()

    run_partition(
        out_dir=args.out_dir,
        mode=args.mode,
        model=args.model,
        rate_sleep=args.rate_sleep,
    )


if __name__ == "__main__":
    main()
