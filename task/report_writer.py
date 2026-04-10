#!/usr/bin/env python3
"""
Report Writer for video segmentation pipeline.

Functions copied verbatim from moonshot/demo/segment_video.py (L366-421).
"""

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import List, Tuple


# --- copied verbatim from segment_video.py L366-368 ---
def fmt_time(sec: float) -> str:
    m, s = divmod(sec, 60)
    return f"{int(m):02d}:{s:05.2f}"


class ReportWriter:
    """Write segments.json + report.md matching demo/output/ format."""

    def write(
        self,
        segments: list,
        out_dir: str,
        video_info: dict,
        report_name: str = "report.md",
    ) -> Tuple[str, str]:
        """Save segments.json and report.md.

        Function body copied verbatim from segment_video.py save_results() L371-421.

        Args:
            segments: List of Segment objects
            out_dir: Output directory
            video_info: Dict with fps, duration, width, height, frame_count
            report_name: Markdown filename

        Returns:
            (json_path, md_path)
        """
        os.makedirs(out_dir, exist_ok=True)

        # JSON
        data = {
            "video_info": video_info,
            "segment_count": len(segments),
            "segments": [asdict(s) for s in segments],
        }
        json_path = os.path.join(out_dir, "segments.json")
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

        md_path = os.path.join(out_dir, report_name)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        print(f"[output] Saved {json_path}")
        print(f"[output] Saved {md_path}")
        return json_path, md_path
