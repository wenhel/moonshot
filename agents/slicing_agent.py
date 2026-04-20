"""
SlicingAgent: orchestrates SmartPartitionTool + BboxZoomTool.
Decides partition strategy, selects zones by query, and zooms.
"""

import cv2
import json
import numpy as np
from typing import List, Optional
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.smart_partition import SmartPartitionTool, Zone
from tools.bbox_zoom import BboxZoomTool, ZoomResult
from core.openrouter_labeler import OpenRouterLabeler
from core.interfaces import LabelerInput


class SlicingAgent:
    """Orchestrates partition + zoom for video frame analysis.

    Usage:
        agent = SlicingAgent.create()
        zones = agent.partition("frame.jpg", context="drone assembly")
        result = agent.zoom_by_query("frame.jpg", "screwdrivers", zones=zones)
    """

    def __init__(
        self,
        partition_tool: SmartPartitionTool,
        zoom_tool: BboxZoomTool,
        vlm: Optional[OpenRouterLabeler] = None,
    ):
        self.partition_tool = partition_tool
        self.zoom_tool = zoom_tool
        # vlm for query->zone matching (reuse partition_tool if not given)
        self._vlm = vlm or partition_tool

    @classmethod
    def create(
        cls,
        model: str = "google/gemini-2.5-flash",
        api_key: Optional[str] = None,
        margin: float = 0.1,
    ) -> "SlicingAgent":
        """Factory: create agent with default tool configuration."""
        partition_tool = SmartPartitionTool(
            model=model, api_key=api_key, temperature=0.2, max_tokens=1000,
        )
        zoom_tool = BboxZoomTool(default_margin=margin)
        return cls(partition_tool=partition_tool, zoom_tool=zoom_tool)

    # -- partition ----------------------------------------------------------

    def partition(
        self,
        image_path: str,
        context: str = "",
        visualize_path: Optional[str] = None,
    ) -> List[Zone]:
        """Partition image into semantic zones.

        Args:
            image_path: path to image.
            context: hint for VLM (e.g. "drone assembly workspace").
            visualize_path: if given, save visualization.

        Returns:
            List of Zone objects.
        """
        zones = self.partition_tool.partition(image_path, context=context)
        if visualize_path:
            self.partition_tool.visualize(image_path, zones, output_path=visualize_path)
        return zones

    # -- zoom ---------------------------------------------------------------

    def zoom_by_zone_name(
        self,
        image_path: str,
        zone_name: str,
        zones: List[Zone],
        margin: Optional[float] = None,
        save_path: Optional[str] = None,
    ) -> Optional[ZoomResult]:
        """Zoom into a zone by its name."""
        target = None
        for z in zones:
            if z.name == zone_name:
                target = z
                break
        if target is None:
            print(f"[SlicingAgent] Zone '{zone_name}' not found. Available: {[z.name for z in zones]}")
            return None
        return self.zoom_tool.zoom_from_path(image_path, target.bbox, margin, save_path)

    def zoom_by_query(
        self,
        image_path: str,
        query: str,
        zones: Optional[List[Zone]] = None,
        context: str = "",
        margin: Optional[float] = None,
        save_path: Optional[str] = None,
    ) -> Optional[ZoomResult]:
        """Query-driven zoom: match query to best zone, then zoom.

        If zones are not provided, runs partition first.
        Uses VLM to pick the best matching zone.
        """
        if zones is None:
            zones = self.partition(image_path, context=context)
        if not zones:
            print("[SlicingAgent] No zones found, cannot zoom.")
            return None

        best = self._match_query_to_zone(query, zones)
        if best is None:
            print(f"[SlicingAgent] Could not match query '{query}' to any zone.")
            return None

        print(f"[SlicingAgent] Matched query '{query}' -> zone '{best.name}' {best.bbox}")
        return self.zoom_tool.zoom_from_path(image_path, best.bbox, margin, save_path)

    # -- query matching -----------------------------------------------------

    def _match_query_to_zone(self, query: str, zones: List[Zone]) -> Optional[Zone]:
        """Use VLM to match a query to the best zone.

        Sends zone list to VLM and asks which one best matches the query.
        Falls back to simple keyword matching if VLM fails.
        """
        zone_desc = json.dumps([
            {"index": i, "name": z.name, "objects": z.objects, "description": z.description}
            for i, z in enumerate(zones)
        ], indent=2)

        prompt = (
            f"Given these image zones:\n{zone_desc}\n\n"
            f"Which zone best matches the query: \"{query}\"?\n"
            f"Return ONLY a JSON object: {{\"index\": <int>, \"reason\": \"...\"}}"
        )

        inp = LabelerInput(
            text=prompt,
            instruction="You are a zone selection assistant. Return valid JSON only.",
        )

        try:
            output = self._vlm.label(inp)
            raw = output.result.get("content", "")
            data = self._vlm._extract_json(raw)
            idx = int(data.get("index", 0))
            if 0 <= idx < len(zones):
                return zones[idx]
        except Exception as e:
            print(f"[SlicingAgent] VLM zone matching failed: {e}, falling back to keyword match")

        # fallback: keyword matching
        query_lower = query.lower()
        best_score = 0
        best_zone = zones[0]
        for z in zones:
            score = 0
            for obj in z.objects:
                if query_lower in obj.lower() or obj.lower() in query_lower:
                    score += 2
            if query_lower in z.name.lower() or query_lower in z.description.lower():
                score += 1
            if score > best_score:
                best_score = score
                best_zone = z
        return best_zone


# -- CLI for quick testing --------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SlicingAgent: partition + zoom")
    parser.add_argument("image", help="Path to input image")
    parser.add_argument("--context", default="hardware assembly workspace",
                        help="Scene context hint")
    parser.add_argument("--query", default=None,
                        help="If given, zoom into the zone matching this query")
    parser.add_argument("--model", default="google/gemini-2.5-flash")
    parser.add_argument("--out", default="output/slicing", help="Output directory")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    agent = SlicingAgent.create(model=args.model)

    # 1. Partition
    print(f"Partitioning {args.image} ...")
    vis_path = str(out_dir / "partition_vis.jpg")
    zones = agent.partition(args.image, context=args.context, visualize_path=vis_path)
    print(f"Found {len(zones)} zones:")
    for z in zones:
        print(f"  {z.name}: bbox={z.bbox}, objects={z.objects}")

    # Save zones JSON
    zones_json = [{"name": z.name, "bbox": list(z.bbox), "objects": z.objects,
                    "description": z.description} for z in zones]
    with open(out_dir / "zones.json", "w") as f:
        json.dump(zones_json, f, indent=2)

    # 2. Zoom (if query given)
    if args.query:
        print(f"\nZooming for query: '{args.query}' ...")
        zoom_path = str(out_dir / f"zoom_{args.query.replace(' ', '_')}.jpg")
        result = agent.zoom_by_query(
            args.image, args.query, zones=zones, save_path=zoom_path,
        )
        if result:
            print(f"Zoomed region saved to {zoom_path}")
            print(f"  source_bbox: {result.source_bbox}")
            print(f"  pixel_bbox: {result.pixel_bbox}")
    else:
        # Zoom each zone for demo
        for z in zones:
            zoom_path = str(out_dir / f"zoom_{z.name}.jpg")
            agent.zoom_by_zone_name(args.image, z.name, zones, save_path=zoom_path)
            print(f"  Saved zoom: {zoom_path}")
