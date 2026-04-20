"""
SmartPartitionTool: use VLM API to partition an image into semantic zones.
Inherits from OpenRouterLabeler to reuse API call, retry, and JSON parsing.
"""

import json
import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.openrouter_labeler import OpenRouterLabeler
from core.interfaces import LabelerInput


# -- data structures --------------------------------------------------------

@dataclass
class Zone:
    """A semantic region in the image."""
    name: str
    bbox: Tuple[float, float, float, float]   # (x1, y1, x2, y2) normalized 0-1
    objects: List[str] = field(default_factory=list)
    description: str = ""


# -- default prompt ---------------------------------------------------------

DEFAULT_PARTITION_PROMPT = """Analyze this image and identify all distinct functional zones where similar objects are grouped together.

For each zone, return:
- zone_name: a short descriptive snake_case name (e.g. "parts_area", "tools_area", "instruction_board", "workspace")
- bbox: [x1, y1, x2, y2] as normalized coordinates where 0.0 is the top-left and 1.0 is the bottom-right
- objects: list of objects found in this zone
- description: one-line description of the zone

Rules:
- Zones should NOT overlap significantly.
- Cover the entire image. Every visible object should belong to a zone.
- Group objects by their functional role (e.g. all screwdrivers together, all frame parts together).
- Typical zones for assembly scenes: parts area, tools area, fasteners/screws area, instruction manual, workspace/operating area.

{context}

Return ONLY a JSON array. Example:
[
  {{"zone_name": "frame_parts", "bbox": [0.0, 0.0, 0.4, 0.35], "objects": ["carbon plate", "wrench"], "description": "Drone frame parts and wrenches"}},
  {{"zone_name": "screwdrivers", "bbox": [0.6, 0.5, 1.0, 0.9], "objects": ["phillips screwdriver", "hex driver"], "description": "Assembly screwdrivers"}}
]"""


# -- colors for visualization -----------------------------------------------

ZONE_COLORS = [
    (0, 255, 0),    # green
    (255, 0, 0),    # blue (BGR)
    (0, 0, 255),    # red
    (255, 255, 0),  # cyan
    (0, 255, 255),  # yellow
    (255, 0, 255),  # magenta
    (128, 255, 0),  # lime
    (255, 128, 0),  # orange-ish
]


# -- tool class -------------------------------------------------------------

class SmartPartitionTool(OpenRouterLabeler):
    """VLM-based semantic image partitioner.

    Inherits OpenRouterLabeler for API call mechanics.
    Sends an image to VLM with a partition prompt, parses JSON zones.
    """

    def __init__(
        self,
        name: str = "smart_partition",
        model: str = "google/gemini-2.5-flash",
        prompt_template: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 1000,
        timeout: int = 60,
        max_retries: int = 3,
    ):
        super().__init__(
            name=name,
            model=model,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            max_retries=max_retries,
        )
        self.prompt_template = prompt_template or DEFAULT_PARTITION_PROMPT

    # -- main entry ---------------------------------------------------------

    def partition(
        self,
        image_path: str,
        context: str = "",
    ) -> List[Zone]:
        """Partition a single image into semantic zones via VLM.

        Args:
            image_path: path to the image file.
            context: optional hint (e.g. "drone assembly scene").

        Returns:
            List of Zone objects.
        """
        prompt = self.prompt_template.format(context=context)
        inp = LabelerInput(
            text=prompt,
            image_paths=[image_path],
            instruction="You are a precise visual analysis assistant. Return valid JSON only.",
        )
        output = self.label(inp)
        raw = output.result.get("content", "")
        zones = self._parse_zones(raw)
        return zones

    def partition_batch(
        self,
        image_paths: List[str],
        context: str = "",
    ) -> List[Zone]:
        """Partition multiple images (e.g. a segment's keyframes) in ONE API call.

        Sends all images together so the VLM sees the full segment and returns
        one consistent set of zone coordinates.

        Args:
            image_paths: list of keyframe image paths (all in one segment).
            context: optional hint.

        Returns:
            List of Zone objects (one set for the whole segment).
        """
        valid = [p for p in image_paths if Path(p).exists()]
        if not valid:
            return []

        prompt = (
            f"These {len(valid)} images are keyframes from the SAME video segment. "
            f"They show the same workspace from the same camera angle.\n\n"
            f"Analyze ALL images together and identify ONE consistent set of functional zones "
            f"that applies to the entire segment. The zone coordinates should cover "
            f"where objects are across ALL frames, not just one frame.\n\n"
            + self.prompt_template.format(context=context)
        )
        inp = LabelerInput(
            text=prompt,
            image_paths=valid,
            instruction="You are a precise visual analysis assistant. Return valid JSON only.",
        )
        output = self.label(inp)
        raw = output.result.get("content", "")
        zones = self._parse_zones(raw)
        return zones

    # -- parsing ------------------------------------------------------------

    def _parse_zones(self, raw_text: str) -> List[Zone]:
        """Parse VLM output text into Zone objects."""
        try:
            data = self._extract_json(raw_text)
        except ValueError:
            print(f"[SmartPartitionTool] Failed to parse JSON from VLM output:\n{raw_text[:500]}")
            return []

        if not isinstance(data, list):
            data = [data]

        zones = []
        for item in data:
            if not isinstance(item, dict):
                continue
            bbox_raw = item.get("bbox", [0, 0, 1, 1])
            bbox = tuple(float(v) for v in bbox_raw[:4])
            zones.append(Zone(
                name=item.get("zone_name", "unknown"),
                bbox=bbox,
                objects=item.get("objects", []),
                description=item.get("description", ""),
            ))
        return zones

    # -- visualization ------------------------------------------------------

    def visualize(
        self,
        image_path: str,
        zones: List[Zone],
        output_path: Optional[str] = None,
    ) -> np.ndarray:
        """Draw zone boundaries and labels on the image.

        Args:
            image_path: source image.
            zones: list of Zone objects.
            output_path: if given, save the visualization.

        Returns:
            Annotated image (BGR).
        """
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Cannot read image: {image_path}")

        h, w = img.shape[:2]
        overlay = img.copy()

        for i, zone in enumerate(zones):
            color = ZONE_COLORS[i % len(ZONE_COLORS)]
            x1, y1, x2, y2 = zone.bbox
            px1, py1 = int(x1 * w), int(y1 * h)
            px2, py2 = int(x2 * w), int(y2 * h)

            # semi-transparent fill
            cv2.rectangle(overlay, (px1, py1), (px2, py2), color, -1)

            # border
            cv2.rectangle(img, (px1, py1), (px2, py2), color, 3)

            # label background
            label = f"{zone.name}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
            cv2.rectangle(img, (px1, py1), (px1 + tw + 8, py1 + th + 12), color, -1)
            cv2.putText(img, label, (px1 + 4, py1 + th + 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        # blend overlay
        alpha = 0.15
        img = cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0)

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(output_path, img)
            print(f"[SmartPartitionTool] Visualization saved to {output_path}")

        return img
