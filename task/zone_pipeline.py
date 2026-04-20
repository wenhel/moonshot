#!/usr/bin/env python3
"""
Zone Pipeline: partition + zone-based labeling (movement + state).

Steps:
  1. Load segments.json
  2. Partition every keyframe → refine per segment → consistent zones
  3. Label each segment using zone-aware prompt (movement + zone states)
  4. Write enriched report

Usage:
  cd moonshot/code
  python -m task.zone_pipeline OUTPUT_DIR [--model MODEL] [--rate-sleep SEC]
"""

import argparse
import json
import os
import time
from pathlib import Path
from typing import List, Optional

from tools.smart_partition import SmartPartitionTool
from tools.bbox_zoom import BboxZoomTool
from task.partition_report import partition_segment, GUIDED_PROMPT
from task.assembly_video_labeler import AssemblyVideoLabeler
from task.report_writer import ReportWriter, fmt_time
from core.interfaces import LabelerInput


ZONE_NAMES = ["workspace", "tools", "parts", "screws_board"]


# ---------------------------------------------------------------------------
# Zone-aware labeler
# ---------------------------------------------------------------------------

class ZoneLabeler(AssemblyVideoLabeler):
    """Labeler that injects zone coordinates into the prompt."""

    def label_segment_with_zones(
        self,
        keyframe_paths: List[str],
        time_range: str,
        zones: List[dict],
        transcript: str = "",
        zoom_paths: Optional[List[List[str]]] = None,
    ) -> str:
        """Label segment with zone info injected into prompt.

        Args:
            keyframe_paths: original keyframe images.
            time_range: segment time range string.
            zones: list of zone dicts with name, bbox.
            transcript: optional transcript.
            zoom_paths: optional list of zoom image paths per zone
                        (for zone state description via separate images).
        """
        if not keyframe_paths:
            return "(no keyframes)"

        # Format zone info for prompt
        zone_lines = []
        for z in zones:
            bbox = z.get("bbox", [0, 0, 0, 0])
            zone_lines.append(
                f"  - {z['name']}: bbox=({bbox[0]:.2f}, {bbox[1]:.2f}, {bbox[2]:.2f}, {bbox[3]:.2f})"
            )
        zone_info = "\n".join(zone_lines) if zone_lines else "  (no zones detected)"

        transcript_hint = (
            f'\nNarration during this segment: "{transcript}"'
            if transcript else ""
        )

        prompt_text = self.prompt_template.format(
            time_range=time_range,
            transcript_hint=transcript_hint,
            zone_info=zone_info,
        )

        # Collect images: original keyframes + optionally zoom crops
        all_images = list(keyframe_paths)
        if zoom_paths:
            for zp_list in zoom_paths:
                all_images.extend(zp_list)

        input_data = LabelerInput(
            text="",
            image_paths=all_images,
            instruction=prompt_text,
        )

        output = self.label(input_data)
        return output.result.get("content", "")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_zone_pipeline(
    src_dir: str,
    out_name: str = "v1_fixed-with-loc_zoom-move-description",
    model: str = "google/gemini-2.5-flash",
    api_key: Optional[str] = None,
    rate_sleep: float = 1.5,
    include_zoom_images: bool = True,
) -> None:
    """Full pipeline: partition → label → report."""

    # Paths
    src_json = os.path.join(src_dir, "segments.json")
    if not os.path.exists(src_json):
        raise FileNotFoundError(f"segments.json not found in {src_dir}")

    out_dir = os.path.join(os.path.dirname(src_dir.rstrip("/")), out_name)
    os.makedirs(out_dir, exist_ok=True)

    # Symlink keyframes from source
    kf_src = os.path.join(src_dir, "keyframes")
    kf_dst = os.path.join(out_dir, "keyframes")
    if not os.path.exists(kf_dst):
        os.symlink(os.path.abspath(kf_src), kf_dst)

    with open(src_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data["segments"]
    video_info = data["video_info"]

    # ---- Step 1: Partition ----
    print(f"=== Step 1: Partitioning {len(segments)} segments ===\n")

    partition_tool = SmartPartitionTool(
        name="zone_partition",
        model=model,
        prompt_template=GUIDED_PROMPT,
        api_key=api_key,
        temperature=0.2,
        max_tokens=1200,
    )

    partition_out = os.path.join(out_dir, "partitions")
    os.makedirs(partition_out, exist_ok=True)

    for i, seg in enumerate(segments):
        kf_paths = _resolve_keyframe_paths(seg, src_dir, out_dir)
        time_range = f"{seg['start_sec']:.0f}s-{seg['end_sec']:.0f}s"
        print(f"  seg{i:03d} [{time_range}] ({len(kf_paths)} kf) ...", end=" ", flush=True)

        zones = partition_segment(
            partition_tool, kf_paths, partition_out, i, zone_names=ZONE_NAMES
        )
        seg["zones"] = zones
        seg["_resolved_kf_paths"] = kf_paths
        print(f"{len(zones)} zones")

        if i < len(segments) - 1:
            time.sleep(rate_sleep)

    # ---- Step 2: Label with zone-aware prompt ----
    print(f"\n=== Step 2: Zone-aware labeling ===\n")

    labeler = ZoneLabeler.from_config(
        config_dir="config",
        labeler_name="assembly_zone-move-description",
        api_key=api_key,
    )

    for i, seg in enumerate(segments):
        kf_paths = seg.get("_resolved_kf_paths", [])
        zones = seg.get("zones", [])
        time_range = f"{seg['start_sec']:.1f}s - {seg['end_sec']:.1f}s"

        # Collect zoom images for first keyframe of each zone (zone state input)
        zoom_paths = None
        if include_zoom_images and kf_paths and zones:
            zoom_dir = os.path.join(partition_out, "zones")
            # Use first keyframe's zooms as representative
            first_kf = Path(kf_paths[0]).stem
            zoom_paths = []
            for z in zones:
                zp = os.path.join(zoom_dir, f"{first_kf}_{z['name']}.jpg")
                if os.path.exists(zp):
                    zoom_paths.append([zp])
                else:
                    zoom_paths.append([])

        print(f"  seg{i:03d} [{time_range}] labeling ...", end=" ", flush=True)
        seg["vlm_description"] = labeler.label_segment_with_zones(
            keyframe_paths=kf_paths,
            time_range=time_range,
            zones=zones,
            transcript=seg.get("transcript", ""),
            zoom_paths=zoom_paths,
        )
        print("done")

        if i < len(segments) - 1:
            time.sleep(rate_sleep)

    # ---- Step 3: Write report ----
    print(f"\n=== Step 3: Writing report ===\n")

    # Clean up temp field
    for seg in segments:
        seg.pop("_resolved_kf_paths", None)

    _write_zone_report(segments, video_info, out_dir, partition_out)

    # Save enriched JSON
    enriched = {
        "video_info": video_info,
        "segment_count": len(segments),
        "segments": segments,
    }
    json_path = os.path.join(out_dir, "segments.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(enriched, f, indent=2, ensure_ascii=False)

    print(f"\n=== Done: {out_dir} ===")


def _resolve_keyframe_paths(seg: dict, src_dir: str, out_dir: str) -> List[str]:
    """Resolve keyframe paths: try as-is, then relative to src/out keyframes dir."""
    resolved = []
    for p in seg.get("keyframe_paths", []):
        if os.path.exists(p):
            resolved.append(p)
        else:
            for base in [out_dir, src_dir]:
                local = os.path.join(base, "keyframes", Path(p).name)
                if os.path.exists(local):
                    resolved.append(local)
                    break
    return resolved


def _write_zone_report(
    segments: list,
    video_info: dict,
    out_dir: str,
    partition_out: str,
) -> None:
    """Write markdown report with partition overlays + zone descriptions."""

    rel_part = os.path.relpath(partition_out, out_dir)

    lines = [
        "# Zone-Based Movement & State Report\n",
        f"**Duration:** {video_info['duration']:.1f}s | "
        f"**Resolution:** {video_info['width']}x{video_info['height']} | "
        f"**Segments:** {len(segments)}\n",
        "---\n",
    ]

    for seg in segments:
        i = seg["index"]
        zones = seg.get("zones", [])

        lines.append(
            f"## Segment {i} [{fmt_time(seg['start_sec'])} - {fmt_time(seg['end_sec'])}]\n"
        )

        # Keyframes with partition overlay
        kf_paths = seg.get("keyframe_paths", [])
        overlay_tags = []
        for p in kf_paths:
            overlay_name = f"{Path(p).stem}_partition.jpg"
            overlay_path = os.path.join(partition_out, "overlays", overlay_name)
            if os.path.exists(overlay_path):
                overlay_tags.append(
                    f'<img src="{rel_part}/overlays/{overlay_name}" height="150">'
                )
        if overlay_tags:
            lines.append(
                f'<div style="overflow-x:auto;white-space:nowrap;padding:4px 0">'
                f'{"  ".join(overlay_tags)}</div>\n'
            )

        # Zone summary table
        if zones:
            lines.append("| Zone | Bbox | Objects |")
            lines.append("|---|---|---|")
            for z in zones:
                bbox = z.get("bbox", [0, 0, 0, 0])
                bbox_str = f"({bbox[0]:.2f}, {bbox[1]:.2f}, {bbox[2]:.2f}, {bbox[3]:.2f})"
                objs = ", ".join(str(o) for o in z.get("objects", [])[:5])
                lines.append(f"| {z['name']} | {bbox_str} | {objs} |")
            lines.append("")

        # VLM description
        desc = seg.get("vlm_description", "")
        if desc:
            lines.append(f"{desc}\n")

        lines.append("")

    report_path = os.path.join(out_dir, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[output] Saved {report_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Zone pipeline: partition + label + report")
    parser.add_argument("src_dir", help="Source dir with segments.json + keyframes/")
    parser.add_argument("--out-name", default="v1_fixed-with-loc_zoom-move-description",
                        help="Output directory name")
    parser.add_argument("--model", default="google/gemini-2.5-flash")
    parser.add_argument("--rate-sleep", type=float, default=1.5)
    parser.add_argument("--no-zoom", action="store_true",
                        help="Skip sending zoom images to labeler (partition-as-prompt only)")
    args = parser.parse_args()

    run_zone_pipeline(
        src_dir=args.src_dir,
        out_name=args.out_name,
        model=args.model,
        rate_sleep=args.rate_sleep,
        include_zoom_images=not args.no_zoom,
    )


if __name__ == "__main__":
    main()
