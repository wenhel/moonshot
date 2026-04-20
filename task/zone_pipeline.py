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
import cv2
from pathlib import Path
from typing import List, Optional

from tools.smart_partition import SmartPartitionTool
from tools.bbox_zoom import BboxZoomTool
from task.partition_report import partition_segment, GUIDED_PROMPT
from task.assembly_video_labeler import AssemblyVideoLabeler
from task.report_writer import ReportWriter, fmt_time
from core.interfaces import LabelerInput


ZONE_NAMES = ["workspace", "tools", "parts", "screws_board"]

# Default video path
DEFAULT_VIDEO = "/home/wenhel/dsta-stance-project/dsta-stance-clean-refactor-s2/moonshot/videos/correct_assemble_v1.mp4"


# ---------------------------------------------------------------------------
# Video-based labeling via Gemini native video input
# ---------------------------------------------------------------------------

def _get_gemini_genai():
    """Lazy-init google.generativeai with API key from .env."""
    import google.generativeai as genai
    with open(os.path.join(os.path.dirname(__file__), '..', '.env')) as f:
        for line in f:
            if line.startswith('GEMINI_API_KEY'):
                key = line.split('=', 1)[1].strip().strip('"')
                genai.configure(api_key=key)
                return genai
    raise RuntimeError("GEMINI_API_KEY not found in .env")


def _extract_clip(video_path: str, start_frame: int, end_frame: int,
                  output_path: str, fps: float = 25.0) -> str:
    """Extract a video clip from start_frame to end_frame."""
    cap = cv2.VideoCapture(video_path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(output_path, fourcc, fps, (w, h))
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    for _ in range(end_frame - start_frame):
        ret, frame = cap.read()
        if not ret:
            break
        writer.write(frame)
    cap.release()
    writer.release()
    return output_path


VID_LABEL_PROMPT = """This is a {duration:.0f}-second video clip from a hardware assembly process ({time_range}).
This is segment {seg_index} of a continuous video stream.{prev_context}

The workspace has 4 functional zones:
- **workspace**: The active assembly area where hands perform work
- **tools**: Where screwdrivers/hex drivers rest when not in use
- **parts**: Where frame components and structural parts are stored
- **screws_board**: The whiteboard/card showing screws organized by type and size

Zone coordinates: {zone_info}

Watch the ENTIRE video carefully and provide FOUR sections:

**Description**: 2-3 sentences describing what happens in this segment. Focus on the assembly step being performed.

**Movement**: List each distinct movement. Use timestamps relative to clip start.
[MOVE] ~Xs-~Ys | object | from_zone -> to_zone | what happens
[ACTION] ~Xs-~Ys | object | zone | what is being done (e.g. tightening screw)
[IDLE] ~Xs-~Ys | zone | nothing happening
Be PRECISE: name tool colors, part types, screw sizes. Only describe what you SEE.

**Zone States**: State of each zone at the END of this segment:
- workspace: what is there
- tools: which tools present vs missing
- parts: which parts remain vs taken
- screws_board: any screws removed

**Tools & Parts Summary**:
Tools: [TOOL: name @ zone]. Parts: [PART: name @ zone].
"""


def label_segment_video(
    genai_module,
    video_path: str,
    seg: dict,
    zones: List[dict],
    prev_summary: str = "",
    model_name: str = "gemini-2.5-flash",
) -> str:
    """Label a segment using Gemini native video input.

    Extracts clip → uploads → generates → cleans up.
    """
    start_frame = seg["start_frame"]
    end_frame = seg["end_frame"]
    start_sec = seg["start_sec"]
    end_sec = seg["end_sec"]
    duration = end_sec - start_sec
    seg_index = seg["index"]

    # Extract clip
    clip_path = f"/tmp/seg{seg_index:03d}_clip.mp4"
    _extract_clip(video_path, start_frame, end_frame, clip_path)

    # Upload
    video_file = genai_module.upload_file(path=clip_path)
    while video_file.state.name == 'PROCESSING':
        time.sleep(1)
        video_file = genai_module.get_file(video_file.name)

    if video_file.state.name != 'ACTIVE':
        os.remove(clip_path)
        return f"(video processing failed: {video_file.state.name})"

    # Format zone info
    zone_info = ", ".join(
        f"{z['name']}=({z['bbox'][0]:.2f},{z['bbox'][1]:.2f},{z['bbox'][2]:.2f},{z['bbox'][3]:.2f})"
        for z in zones
    )

    # Previous segment context for stream continuity
    prev_context = ""
    if prev_summary:
        prev_context = f"\n\nPrevious segment ended with: {prev_summary}"

    prompt = VID_LABEL_PROMPT.format(
        duration=duration,
        time_range=f"{start_sec:.1f}s - {end_sec:.1f}s",
        seg_index=seg_index,
        prev_context=prev_context,
        zone_info=zone_info,
    )

    # Generate — strip provider prefix for Gemini SDK (e.g. "google/gemini-2.5-flash" -> "gemini-2.5-flash")
    if "/" in model_name:
        model_name = model_name.split("/", 1)[1]
    model = genai_module.GenerativeModel(model_name)

    result = ""
    for attempt in range(3):
        try:
            response = model.generate_content([video_file, prompt])
            result = response.text
            break
        except Exception as e:
            if attempt < 2:
                print(f"\n    [vid_label] Retry {attempt+1}/3: {e}")
                time.sleep(5 * (attempt + 1))
            else:
                result = f"(video labeling failed after 3 attempts: {e})"

    # Cleanup
    try:
        genai_module.delete_file(video_file.name)
    except Exception:
        pass
    os.remove(clip_path)

    return result


def _extract_zone_state_summary(description: str) -> str:
    """Extract a brief summary from Zone States for stream context."""
    lines = description.split("\n")
    in_zone_states = False
    summary_parts = []
    for line in lines:
        if "**Zone States**" in line:
            in_zone_states = True
            continue
        if in_zone_states:
            if line.startswith("**") or line.strip() == "":
                break
            summary_parts.append(line.strip().lstrip("- "))
    return "; ".join(summary_parts[:4]) if summary_parts else ""


# ---------------------------------------------------------------------------
# Zone-aware labeler (image mode)
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
    mode: str = "img",
    video_path: Optional[str] = None,
    report_name: str = "report.md",
    skip_partition: bool = False,
) -> None:
    """Full pipeline: partition → label → report.

    Args:
        mode: "img" = keyframe images via OpenRouter (original)
              "vid" = video clips via Gemini native video input (stream)
        video_path: source video path (required for mode=vid)
        skip_partition: if True, reuse existing partitions from segments.json
    """

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
        if os.path.exists(kf_src):
            os.symlink(os.path.abspath(kf_src), kf_dst)

    with open(src_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    segments = data["segments"]
    video_info = data["video_info"]

    # ---- Step 1: Partition ----
    partition_out = os.path.join(out_dir, "partitions")

    if skip_partition and all(seg.get("zones") for seg in segments):
        print(f"=== Step 1: Skipping partition (reusing existing zones) ===\n")
        # Still resolve keyframe paths for later use
        for seg in segments:
            seg["_resolved_kf_paths"] = _resolve_keyframe_paths(seg, src_dir, out_dir)
    else:
        print(f"=== Step 1: Partitioning {len(segments)} segments (mode={mode}) ===\n")

        partition_tool = SmartPartitionTool(
            name="zone_partition",
            model=model,
            prompt_template=GUIDED_PROMPT,
            api_key=api_key,
            temperature=0.2,
            max_tokens=1200,
        )
        os.makedirs(partition_out, exist_ok=True)

        for i, seg in enumerate(segments):
            kf_paths = _resolve_keyframe_paths(seg, src_dir, out_dir)
            time_range = f"{seg['start_sec']:.0f}s-{seg['end_sec']:.0f}s"
            print(f"  seg{i:03d} [{time_range}] ...", end=" ", flush=True)

            if mode == "vid" and video_path:
                # Video-based partition
                zones_list = partition_tool.partition_video(
                    video_path or DEFAULT_VIDEO,
                    seg["start_frame"], seg["end_frame"],
                )
                zones = [{"name": z.name, "bbox": list(z.bbox),
                          "objects": z.objects, "description": z.description}
                         for z in zones_list]
                # Still generate overlays from keyframes for the report
                from tools.bbox_zoom import BboxZoomTool
                zoom_tool = BboxZoomTool(default_margin=0.1)
                vis_dir = os.path.join(partition_out, "overlays")
                zoom_dir = os.path.join(partition_out, "zones")
                os.makedirs(vis_dir, exist_ok=True)
                os.makedirs(zoom_dir, exist_ok=True)
                for kf_path in kf_paths:
                    if not os.path.exists(kf_path):
                        continue
                    kf_name = Path(kf_path).stem
                    partition_tool.visualize(kf_path, zones_list,
                                            output_path=os.path.join(vis_dir, f"{kf_name}_partition.jpg"))
                    for z in zones_list:
                        if z.bbox != (0, 0, 0, 0):
                            try:
                                zoom_tool.zoom_from_path(kf_path, z.bbox,
                                    save_path=os.path.join(zoom_dir, f"{kf_name}_{z.name}.jpg"))
                            except Exception:
                                pass
            else:
                # Image-based partition (batch keyframes)
                zones = partition_segment(
                    partition_tool, kf_paths, partition_out, i, zone_names=ZONE_NAMES
                )

            seg["zones"] = zones
            seg["_resolved_kf_paths"] = kf_paths
            print(f"{len(zones)} zones")

            if i < len(segments) - 1:
                time.sleep(rate_sleep)

    # ---- Step 2: Label ----
    if mode == "vid":
        _run_label_video(segments, video_path or DEFAULT_VIDEO, partition_out,
                         model, rate_sleep, src_dir, out_dir)
    else:
        _run_label_images(segments, partition_out, api_key, include_zoom_images,
                          rate_sleep, src_dir, out_dir)

    # ---- Step 3: Write report ----
    print(f"\n=== Step 3: Writing report ===\n")

    # Clean up temp field
    for seg in segments:
        seg.pop("_resolved_kf_paths", None)

    _write_zone_report(segments, video_info, out_dir, partition_out, report_name=report_name)

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


def _run_label_video(segments, video_path, partition_out, model, rate_sleep, src_dir, out_dir):
    """Step 2: Label using Gemini native video input (stream mode)."""
    print(f"\n=== Step 2: Video-based labeling (stream mode) ===\n")
    print(f"  Video: {video_path}\n")

    genai = _get_gemini_genai()
    prev_summary = ""

    for i, seg in enumerate(segments):
        zones = seg.get("zones", [])
        time_range = f"{seg['start_sec']:.1f}s - {seg['end_sec']:.1f}s"
        print(f"  seg{i:03d} [{time_range}] ...", end=" ", flush=True)

        t0 = time.time()
        seg["vlm_description"] = label_segment_video(
            genai, video_path, seg, zones,
            prev_summary=prev_summary,
            model_name=model,
        )
        elapsed = time.time() - t0
        print(f"done ({elapsed:.1f}s)")

        # Extract zone state summary for stream continuity
        prev_summary = _extract_zone_state_summary(seg["vlm_description"])

        if i < len(segments) - 1:
            time.sleep(rate_sleep)


def _run_label_images(segments, partition_out, api_key, include_zoom_images,
                      rate_sleep, src_dir, out_dir):
    """Step 2: Label using keyframe images via OpenRouter."""
    print(f"\n=== Step 2: Image-based labeling ===\n")

    labeler = ZoneLabeler.from_config(
        config_dir="config",
        labeler_name="assembly_zone-move-description",
        api_key=api_key,
    )

    for i, seg in enumerate(segments):
        kf_paths = seg.get("_resolved_kf_paths", _resolve_keyframe_paths(seg, src_dir, out_dir))
        zones = seg.get("zones", [])
        time_range = f"{seg['start_sec']:.1f}s - {seg['end_sec']:.1f}s"

        zoom_paths = None
        if include_zoom_images and kf_paths and zones:
            zoom_dir = os.path.join(partition_out, "zones")
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
    report_name: str = "report.md",
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

    report_path = os.path.join(out_dir, report_name)
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
    parser.add_argument("--mode", choices=["img", "vid"], default="img",
                        help="Label mode: img (keyframe images) or vid (Gemini video input)")
    parser.add_argument("--video", default=None,
                        help="Source video path (required for --mode vid)")
    parser.add_argument("--model", default="google/gemini-2.5-flash")
    parser.add_argument("--rate-sleep", type=float, default=1.5)
    parser.add_argument("--report-name", default=None,
                        help="Report filename (default: report.md or report-vid.md)")
    parser.add_argument("--no-zoom", action="store_true",
                        help="Skip sending zoom images to labeler (img mode only)")
    parser.add_argument("--skip-partition", action="store_true",
                        help="Reuse existing partitions from segments.json")
    args = parser.parse_args()

    report_name = args.report_name or ("report-vid.md" if args.mode == "vid" else "report.md")

    run_zone_pipeline(
        src_dir=args.src_dir,
        out_name=args.out_name,
        model=args.model,
        rate_sleep=args.rate_sleep,
        include_zoom_images=not args.no_zoom,
        mode=args.mode,
        video_path=args.video,
        report_name=report_name,
        skip_partition=args.skip_partition,
    )


if __name__ == "__main__":
    main()
