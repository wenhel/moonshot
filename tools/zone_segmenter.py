"""
ZoneSegmenter: Use DINOv2 features + SAM to segment and identify objects within zones.

Pipeline per zone crop:
  1. DINOv2 extracts dense features → PCA → find salient object regions
  2. SAM segments objects using DINOv2-derived point prompts
  3. Each segment is classified by matching DINOv2 features against reference embeddings

Usage:
  segmenter = ZoneSegmenter(device="cuda:1")
  results = segmenter.segment_zone(image, zone_bbox, object_hints=["screwdriver", "hex driver"])
"""

import os
import cv2
import torch
import numpy as np
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict
from pathlib import Path
from PIL import Image


@dataclass
class SegmentedObject:
    """A segmented object within a zone."""
    mask: np.ndarray               # binary mask (H, W), same size as zone crop
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2) in zone crop coords
    area: int                       # pixel area
    centroid: Tuple[int, int]       # (cx, cy) in zone crop coords
    score: float                    # SAM confidence
    label: str = ""                 # assigned label (from VLM or matching)
    crop: Optional[np.ndarray] = None  # cropped object image


class ZoneSegmenter:
    """Segment objects within zone crops using SAM + DINOv2 features."""

    def __init__(self, device: str = "cuda:1", sam_model: str = "sam2.1_s"):
        self.device = device

        # Load SAM via ultralytics
        from ultralytics import SAM
        print(f"[ZoneSegmenter] Loading SAM model: {sam_model} on {device}")
        self.sam = SAM(f"{sam_model}.pt")

        # Load DINOv2 for feature extraction
        print(f"[ZoneSegmenter] Loading DINOv2 on {device}")
        self.dinov2 = torch.hub.load('facebookresearch/dinov2', 'dinov2_vits14')
        self.dinov2 = self.dinov2.to(device).eval()
        self.dino_transform = self._get_dino_transform()

    @staticmethod
    def _get_dino_transform():
        """Standard DINOv2 preprocessing."""
        from torchvision import transforms
        return transforms.Compose([
            transforms.Resize((518, 518)),  # DINOv2 vits14 expects multiples of 14
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                 std=[0.229, 0.224, 0.225]),
        ])

    def get_dino_features(self, image_rgb: np.ndarray) -> np.ndarray:
        """Extract DINOv2 dense patch features from an image.

        Returns:
            Feature map (H_patches, W_patches, D) where D=384 for vits14.
        """
        pil_img = Image.fromarray(image_rgb)
        tensor = self.dino_transform(pil_img).unsqueeze(0).to(self.device)

        with torch.no_grad():
            features = self.dinov2.forward_features(tensor)
            patch_tokens = features["x_norm_patchtokens"]  # (1, N_patches, D)

        # Reshape to spatial grid
        h_patches = w_patches = int(patch_tokens.shape[1] ** 0.5)
        feat_map = patch_tokens[0].reshape(h_patches, w_patches, -1)
        return feat_map.cpu().numpy()

    def get_salient_points(
        self,
        feat_map: np.ndarray,
        n_points: int = 8,
        n_components: int = 3,
    ) -> List[Tuple[int, int]]:
        """Find salient point locations from DINOv2 features using PCA.

        Returns points in (x, y) pixel coordinates (scaled to original image).
        """
        from sklearn.decomposition import PCA

        h, w, d = feat_map.shape
        flat = feat_map.reshape(-1, d)

        # PCA to find principal component
        pca = PCA(n_components=n_components)
        components = pca.fit_transform(flat)

        # Use first component as saliency (foreground vs background)
        saliency = components[:, 0].reshape(h, w)

        # Normalize to 0-1
        saliency = (saliency - saliency.min()) / (saliency.max() - saliency.min() + 1e-8)

        # Threshold for foreground
        thresh = np.percentile(saliency, 70)
        foreground = saliency > thresh

        # Find connected components and get centroids
        fg_uint8 = (foreground * 255).astype(np.uint8)
        # Resize saliency to get better resolution
        fg_resized = cv2.resize(fg_uint8, (518, 518), interpolation=cv2.INTER_NEAREST)

        contours, _ = cv2.findContours(fg_resized, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        points = []
        for cnt in sorted(contours, key=cv2.contourArea, reverse=True)[:n_points]:
            M = cv2.moments(cnt)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                points.append((cx, cy))

        # If not enough contours, add grid points on foreground
        if len(points) < n_points:
            ys, xs = np.where(fg_resized > 0)
            if len(xs) > 0:
                indices = np.linspace(0, len(xs) - 1, n_points - len(points), dtype=int)
                for idx in indices:
                    points.append((int(xs[idx]), int(ys[idx])))

        return points[:n_points]

    def segment_zone(
        self,
        image: np.ndarray,
        zone_bbox: Tuple[float, float, float, float],
        n_points: int = 8,
        min_area: int = 100,
    ) -> List[SegmentedObject]:
        """Segment objects in a zone.

        Args:
            image: full image (BGR).
            zone_bbox: (x1, y1, x2, y2) normalized 0-1.
            n_points: number of SAM point prompts from DINOv2 saliency.
            min_area: minimum segment area in pixels.

        Returns:
            List of SegmentedObject with masks, bboxes, crops.
        """
        h, w = image.shape[:2]
        x1, y1, x2, y2 = zone_bbox
        px1, py1 = int(x1 * w), int(y1 * h)
        px2, py2 = int(x2 * w), int(y2 * h)

        # Crop zone
        zone_crop = image[py1:py2, px1:px2]
        if zone_crop.size == 0:
            return []

        zone_rgb = cv2.cvtColor(zone_crop, cv2.COLOR_BGR2RGB)
        crop_h, crop_w = zone_crop.shape[:2]

        # Step 1: DINOv2 features → salient points
        feat_map = self.get_dino_features(zone_rgb)
        points_518 = self.get_salient_points(feat_map, n_points=n_points)

        # Scale points from 518x518 to actual crop size
        scale_x = crop_w / 518.0
        scale_y = crop_h / 518.0
        points = [(int(px * scale_x), int(py * scale_y)) for px, py in points_518]

        # Step 2: SAM auto-segmentation (segment everything, then filter by saliency)
        tmp_path = "/tmp/zone_crop_seg.jpg"
        cv2.imwrite(tmp_path, zone_crop)

        results = self.sam(
            tmp_path,
            device=self.device,
        )

        os.remove(tmp_path)

        # Step 3: Parse SAM results into SegmentedObject list
        objects = []
        if results and len(results) > 0 and results[0].masks is not None:
            masks = results[0].masks.data.cpu().numpy()  # (N, H, W)
            boxes = results[0].boxes

            for i in range(masks.shape[0]):
                mask = masks[i].astype(np.uint8)

                # Resize mask to crop size if needed
                if mask.shape != (crop_h, crop_w):
                    mask = cv2.resize(mask, (crop_w, crop_h), interpolation=cv2.INTER_NEAREST)

                area = int(mask.sum())
                if area < min_area:
                    continue

                # Get bbox from mask
                ys, xs = np.where(mask > 0)
                if len(xs) == 0:
                    continue
                bx1, by1 = int(xs.min()), int(ys.min())
                bx2, by2 = int(xs.max()), int(ys.max())
                cx, cy = int(xs.mean()), int(ys.mean())

                # Crop object
                obj_crop = zone_crop[by1:by2, bx1:bx2].copy()
                obj_mask = mask[by1:by2, bx1:bx2]
                # Apply mask (black out background)
                obj_crop[obj_mask == 0] = 255  # white background

                score = float(boxes.conf[i]) if boxes is not None and i < len(boxes.conf) else 0.0

                objects.append(SegmentedObject(
                    mask=mask,
                    bbox=(bx1, by1, bx2, by2),
                    area=area,
                    centroid=(cx, cy),
                    score=score,
                    crop=obj_crop,
                ))

        # Sort by area (largest first)
        objects.sort(key=lambda o: o.area, reverse=True)
        return objects

    def visualize_segments(
        self,
        image: np.ndarray,
        zone_bbox: Tuple[float, float, float, float],
        objects: List[SegmentedObject],
        output_path: Optional[str] = None,
    ) -> np.ndarray:
        """Draw segmentation masks on the zone crop."""
        h, w = image.shape[:2]
        x1, y1, x2, y2 = zone_bbox
        px1, py1 = int(x1 * w), int(y1 * h)
        px2, py2 = int(x2 * w), int(y2 * h)

        zone_crop = image[py1:py2, px1:px2].copy()
        overlay = zone_crop.copy()

        colors = [
            (0, 255, 0), (255, 0, 0), (0, 0, 255), (255, 255, 0),
            (0, 255, 255), (255, 0, 255), (128, 255, 0), (255, 128, 0),
        ]

        for i, obj in enumerate(objects):
            color = colors[i % len(colors)]
            # Draw filled mask
            mask_bool = obj.mask > 0
            overlay[mask_bool] = color

            # Draw bbox
            cv2.rectangle(zone_crop, (obj.bbox[0], obj.bbox[1]),
                          (obj.bbox[2], obj.bbox[3]), color, 2)

            # Label
            label = obj.label or f"obj_{i}"
            cv2.putText(zone_crop, f"{label} ({obj.area}px)",
                        (obj.bbox[0], obj.bbox[1] - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        # Blend
        result = cv2.addWeighted(overlay, 0.3, zone_crop, 0.7, 0)

        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(output_path, result)

        return result

    def label_objects_with_vlm(
        self,
        objects: List[SegmentedObject],
        zone_name: str,
        vlm_labeler=None,
    ) -> List[SegmentedObject]:
        """Use VLM API to label each segmented object crop.

        Args:
            objects: list of SegmentedObject with crops.
            zone_name: context (e.g. "tools").
            vlm_labeler: OpenRouterLabeler instance for API calls.

        Returns:
            Same objects with .label populated.
        """
        if vlm_labeler is None:
            return objects

        from core.interfaces import LabelerInput

        for obj in objects:
            if obj.crop is None:
                continue

            # Save crop to temp
            tmp = f"/tmp/obj_crop_{id(obj)}.jpg"
            cv2.imwrite(tmp, obj.crop)

            prompt = (
                f"This is a cropped object from the '{zone_name}' zone of an assembly workspace. "
                f"Identify this object in 2-5 words (e.g. 'blue hex driver 2.0mm', 'M3x16mm socket head screw', 'carbon fiber frame arm'). "
                f"Return ONLY the object name, nothing else."
            )

            inp = LabelerInput(text=prompt, image_paths=[tmp],
                               instruction="You are a precise object identifier.")
            try:
                out = vlm_labeler.label(inp)
                obj.label = out.result.get("content", "").strip().strip('"').strip("'")
            except Exception as e:
                obj.label = f"unknown ({e})"

            os.remove(tmp)

        return objects


# ---------------------------------------------------------------------------
# CLI test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import argparse

    parser = argparse.ArgumentParser(description="Zone segmentation test")
    parser.add_argument("image", help="Image path")
    parser.add_argument("--zone", nargs=4, type=float, default=[0.55, 0.52, 0.75, 0.76],
                        help="Zone bbox (x1 y1 x2 y2) normalized")
    parser.add_argument("--zone-name", default="tools")
    parser.add_argument("--device", default="cuda:1")
    parser.add_argument("--out", default="output/segmentation_test")
    parser.add_argument("--label", action="store_true", help="Use VLM to label objects")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    segmenter = ZoneSegmenter(device=args.device)

    image = cv2.imread(args.image)
    bbox = tuple(args.zone)

    print(f"Segmenting zone '{args.zone_name}' bbox={bbox} ...")
    objects = segmenter.segment_zone(image, bbox)
    print(f"Found {len(objects)} objects")

    for i, obj in enumerate(objects):
        print(f"  obj_{i}: area={obj.area}, bbox={obj.bbox}, centroid={obj.centroid}")
        if obj.crop is not None:
            cv2.imwrite(os.path.join(args.out, f"obj_{i}_crop.jpg"), obj.crop)

    if args.label:
        from core.openrouter_labeler import OpenRouterLabeler
        vlm = OpenRouterLabeler(name="obj_labeler", model="google/gemini-2.5-flash",
                                temperature=0.1, max_tokens=50)
        objects = segmenter.label_objects_with_vlm(objects, args.zone_name, vlm)
        for i, obj in enumerate(objects):
            print(f"  obj_{i}: label='{obj.label}'")

    vis_path = os.path.join(args.out, "zone_segments.jpg")
    segmenter.visualize_segments(image, bbox, objects, output_path=vis_path)
    print(f"Visualization saved to {vis_path}")
