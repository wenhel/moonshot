"""
BboxZoomTool: crop a bbox region from an image, expand with margin, resize to original size.
Pure cv2 operations, no API calls.
"""

import cv2
import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple, List
from pathlib import Path


@dataclass
class ZoomResult:
    """Result of a zoom operation."""
    zoomed_image: np.ndarray
    source_bbox: Tuple[float, float, float, float]   # normalized (x1,y1,x2,y2)
    pixel_bbox: Tuple[int, int, int, int]             # actual pixel coords after margin
    original_size: Tuple[int, int]                     # (width, height)


class BboxZoomTool:
    """Crop a bounding box region from an image and resize to original dimensions.

    All bbox coordinates are normalized 0.0-1.0: (x1, y1, x2, y2).
    """

    def __init__(self, default_margin: float = 0.1):
        self.default_margin = default_margin

    def zoom(
        self,
        image: np.ndarray,
        bbox: Tuple[float, float, float, float],
        margin: Optional[float] = None,
    ) -> ZoomResult:
        """Crop bbox region with margin and resize to original image size.

        Args:
            image: OpenCV image (BGR or RGB).
            bbox: (x1, y1, x2, y2) normalized 0-1.
            margin: fractional expansion around bbox (default: self.default_margin).

        Returns:
            ZoomResult with zoomed image and metadata.
        """
        margin = margin if margin is not None else self.default_margin
        h, w = image.shape[:2]
        x1, y1, x2, y2 = bbox

        # normalized -> pixel
        px1, py1 = int(x1 * w), int(y1 * h)
        px2, py2 = int(x2 * w), int(y2 * h)

        # add margin
        bw, bh = px2 - px1, py2 - py1
        mw, mh = int(bw * margin), int(bh * margin)
        px1 = max(0, px1 - mw)
        py1 = max(0, py1 - mh)
        px2 = min(w, px2 + mw)
        py2 = min(h, py2 + mh)

        # crop and resize back to original dimensions
        crop = image[py1:py2, px1:px2]
        zoomed = cv2.resize(crop, (w, h), interpolation=cv2.INTER_LINEAR)

        return ZoomResult(
            zoomed_image=zoomed,
            source_bbox=bbox,
            pixel_bbox=(px1, py1, px2, py2),
            original_size=(w, h),
        )

    def zoom_from_path(
        self,
        image_path: str,
        bbox: Tuple[float, float, float, float],
        margin: Optional[float] = None,
        save_path: Optional[str] = None,
    ) -> ZoomResult:
        """Read image from file, zoom, optionally save."""
        image = cv2.imread(image_path)
        if image is None:
            raise FileNotFoundError(f"Cannot read image: {image_path}")
        result = self.zoom(image, bbox, margin)
        if save_path:
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(save_path, result.zoomed_image)
        return result

    def multi_zoom(
        self,
        image: np.ndarray,
        bboxes: List[Tuple[float, float, float, float]],
        margin: Optional[float] = None,
    ) -> List[ZoomResult]:
        """Zoom into multiple bboxes from the same image."""
        return [self.zoom(image, bbox, margin) for bbox in bboxes]

    @staticmethod
    def draw_bbox(
        image: np.ndarray,
        bbox: Tuple[float, float, float, float],
        label: str = "",
        color: Tuple[int, int, int] = (0, 255, 0),
        thickness: int = 2,
    ) -> np.ndarray:
        """Draw a bbox on an image (for visualization). Returns a copy."""
        vis = image.copy()
        h, w = vis.shape[:2]
        x1, y1, x2, y2 = bbox
        px1, py1 = int(x1 * w), int(y1 * h)
        px2, py2 = int(x2 * w), int(y2 * h)
        cv2.rectangle(vis, (px1, py1), (px2, py2), color, thickness)
        if label:
            cv2.putText(vis, label, (px1, max(py1 - 8, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        return vis
