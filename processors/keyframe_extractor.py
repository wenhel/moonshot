#!/usr/bin/env python3
"""
Key Frame Extractor for Video Analysis

Extracts representative frames from videos using multiple strategies:
- uniform: Evenly spaced frames
- scene_detect: Scene boundary detection
- adaptive: Content-aware sampling
- hybrid: Scene detection with uniform fallback

DEPRECATION WARNING:
This module should be accessed through src/data/frame_utils.py as the unified entry point.
Direct imports from stance.processors.keyframe_extractor are deprecated.
Future refactoring will merge this functionality into frame_utils.
"""

import os
import hashlib
import tempfile
import shutil
import glob
from pathlib import Path
from typing import List, Optional, Dict, Tuple
import numpy as np
import cv2
from PIL import Image


class KeyFrameExtractor:
    """Extract representative key frames from video clips."""

    def __init__(
        self,
        method: str = 'uniform',
        max_frames: int = 10,
        min_scene_duration: float = 1.0,
        threshold: float = 30.0,
        output_format: str = 'jpg',
        output_quality: int = 95,
        deduplicate: bool = False,
        similarity_threshold: float = 0.95,
        adaptive_num_frames: bool = False,
    ):
        """Initialize key frame extractor.

        Args:
            method: Extraction method ('uniform', 'scene_detect', 'adaptive', 'hybrid')
            max_frames: Maximum number of frames to extract (only for 'uniform' method)
            min_scene_duration: Minimum scene duration in seconds (for scene_detect)
            threshold: Scene change threshold 0-100 (for scene_detect)
            output_format: Image format (jpg, png)
            output_quality: Image quality 0-100
            deduplicate: Whether to remove similar frames
            similarity_threshold: Similarity threshold for deduplication (0-1)
            adaptive_num_frames: If True, number of frames is determined by content (scene_detect, hybrid)
                                 If False, respects max_frames limit
        """
        self.method = method
        self.max_frames = max_frames
        self.min_scene_duration = min_scene_duration
        self.threshold = threshold
        self.output_format = output_format
        self.output_quality = output_quality
        self.deduplicate = deduplicate
        self.similarity_threshold = similarity_threshold
        self.adaptive_num_frames = adaptive_num_frames

        # Validate method
        valid_methods = ['uniform', 'scene_detect', 'adaptive', 'hybrid']
        if method not in valid_methods:
            raise ValueError(f"Invalid method: {method}. Must be one of {valid_methods}")

    def get_video_info(self, video_path: str) -> Dict:
        """Get video metadata.

        Args:
            video_path: Path to video file

        Returns:
            Dict with fps, duration, frame_count, resolution, etc.

        Raises:
            FileNotFoundError: Video file not found
            ValueError: Cannot open video
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video file: {video_path}")

        try:
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 0

            return {
                'fps': fps,
                'frame_count': frame_count,
                'duration': duration,
                'width': width,
                'height': height,
                'resolution': f"{width}x{height}",
            }
        finally:
            cap.release()

    def _is_image_sequence(self, path: str) -> bool:
        """Check if path is a directory containing image sequence.

        Args:
            path: Path to check

        Returns:
            True if path is a directory with image files
        """
        if not os.path.isdir(path):
            return False

        # Check for common image extensions
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.tiff']
        for ext in image_extensions:
            if glob.glob(os.path.join(path, f'*{ext}')):
                return True

        return False

    def _get_image_sequence_paths(self, image_dir: str) -> List[str]:
        """Get sorted list of image paths from directory.

        Args:
            image_dir: Directory containing images

        Returns:
            Sorted list of image file paths
        """
        image_extensions = ['*.jpg', '*.jpeg', '*.png', '*.bmp', '*.tiff', '*.JPG', '*.PNG']
        image_paths = []

        for ext in image_extensions:
            image_paths.extend(glob.glob(os.path.join(image_dir, ext)))

        # Sort by filename to maintain sequence order
        image_paths.sort()

        return image_paths

    def get_image_sequence_info(self, image_dir: str) -> Dict:
        """Get metadata for image sequence.

        Args:
            image_dir: Directory containing image sequence

        Returns:
            Dict with fps (assumed 10), frame_count, duration, resolution, etc.

        Raises:
            FileNotFoundError: Directory not found
            ValueError: No images found in directory
        """
        if not os.path.exists(image_dir):
            raise FileNotFoundError(f"Directory not found: {image_dir}")

        image_paths = self._get_image_sequence_paths(image_dir)

        if not image_paths:
            raise ValueError(f"No images found in directory: {image_dir}")

        # Read first image to get resolution
        first_image = cv2.imread(image_paths[0])
        if first_image is None:
            raise ValueError(f"Cannot read image: {image_paths[0]}")

        height, width = first_image.shape[:2]
        frame_count = len(image_paths)

        # Assume 10 fps for image sequences (can be overridden)
        fps = 10.0
        duration = frame_count / fps

        return {
            'fps': fps,
            'frame_count': frame_count,
            'duration': duration,
            'width': width,
            'height': height,
            'resolution': f"{width}x{height}",
            'image_paths': image_paths
        }

    def extract_frames_uniform_from_images(
        self,
        image_dir: str,
        num_frames: int
    ) -> Tuple[List[np.ndarray], List[str], List[int]]:
        """Extract frames uniformly from image sequence.

        Args:
            image_dir: Directory containing image sequence
            num_frames: Number of frames to extract

        Returns:
            Tuple of (frame arrays, selected image paths, original indices)
        """
        info = self.get_image_sequence_info(image_dir)
        image_paths = info['image_paths']
        total_frames = len(image_paths)

        # Calculate frame indices
        if total_frames <= num_frames:
            indices = list(range(total_frames))
        else:
            indices = [
                int(i * total_frames / num_frames)
                for i in range(num_frames)
            ]

        frames = []
        selected_paths = []
        selected_indices = []

        for idx in indices:
            image_path = image_paths[idx]
            frame = cv2.imread(image_path)

            if frame is not None:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frames.append(frame_rgb)
                selected_paths.append(image_path)
                selected_indices.append(idx)
            else:
                print(f"Warning: Failed to read image at {image_path}")

        return frames, selected_paths, selected_indices

    def extract_frames_scene_detect_from_images(
        self,
        image_dir: str,
        max_frames: Optional[int] = None
    ) -> Tuple[List[np.ndarray], List[str], List[int]]:
        """Extract frames at scene boundaries from image sequence.

        Args:
            image_dir: Directory containing image sequence
            max_frames: Maximum number of frames to extract

        Returns:
            Tuple of (frame arrays at scene boundaries, selected image paths, original indices)
        """
        info = self.get_image_sequence_info(image_dir)
        image_paths = info['image_paths']

        scene_boundaries = [0]  # Always include first frame
        frames = []
        selected_paths = []

        prev_gray = None
        min_frames = int(self.min_scene_duration * info['fps'])

        print(f"Analyzing {len(image_paths)} images for scene changes...")

        for idx, image_path in enumerate(image_paths):
            frame = cv2.imread(image_path)

            if frame is None:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            if prev_gray is not None:
                diff = cv2.absdiff(prev_gray, gray)
                diff_score = np.mean(diff)

                if diff_score > self.threshold:
                    if idx - scene_boundaries[-1] >= min_frames:
                        scene_boundaries.append(idx)

            prev_gray = gray

        print(f"Detected {len(scene_boundaries)} scene boundaries")

        # Limit to max_frames only if not adaptive
        if not self.adaptive_num_frames:
            if max_frames is not None and len(scene_boundaries) > max_frames:
                scene_boundaries = scene_boundaries[:max_frames]
                print(f"Limited to {max_frames} frames (set adaptive_num_frames=True for all scenes)")
        else:
            print(f"Adaptive mode: extracting all {len(scene_boundaries)} scene boundaries")

        # Extract frames at scene boundaries
        for idx in scene_boundaries:
            frame = cv2.imread(image_paths[idx])
            if frame is not None:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frames.append(frame_rgb)
                selected_paths.append(image_paths[idx])

        return frames, selected_paths, scene_boundaries

    def extract_frames_hybrid_from_images(
        self,
        image_dir: str,
        max_frames: Optional[int] = None
    ) -> Tuple[List[np.ndarray], List[str], List[int]]:
        """Extract frames using hybrid strategy from image sequence.

        Args:
            image_dir: Directory containing image sequence
            max_frames: Maximum number of frames to extract

        Returns:
            Tuple of (frame arrays, selected image paths, original indices)
        """
        if max_frames is None:
            max_frames = self.max_frames

        info = self.get_image_sequence_info(image_dir)
        image_paths = info['image_paths']
        total_frames = len(image_paths)

        # Calculate uniform indices
        uniform_indices = set([
            int(i * total_frames / max_frames)
            for i in range(max_frames)
        ])

        # Analyze for scene detection
        scene_boundaries = [0]
        frame_diffs = []
        prev_gray = None
        min_frames = int(self.min_scene_duration * info['fps'])

        print(f"Analyzing {total_frames} images...")

        for idx, image_path in enumerate(image_paths):
            frame = cv2.imread(image_path)

            if frame is None:
                continue

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            if prev_gray is not None:
                diff = cv2.absdiff(prev_gray, gray)
                diff_score = np.mean(diff)
                frame_diffs.append(diff_score)

                if diff_score > self.threshold:
                    if idx - scene_boundaries[-1] >= min_frames:
                        scene_boundaries.append(idx)

            prev_gray = gray

        # Strategy selection
        avg_frame_diff = np.mean(frame_diffs) if frame_diffs else 0
        scene_count = len(scene_boundaries)

        print(f"Video analysis: avg_diff={avg_frame_diff:.2f}, scene_count={scene_count}")

        selected_indices = []
        method_used = ''

        if self.adaptive_num_frames:
            # Adaptive mode: let content determine the number
            if avg_frame_diff < 4.0 or scene_count < 3:
                # Static video -> extract based on duration (e.g., 1 frame per 10 seconds)
                duration = total_frames / info['fps']
                num_frames = max(int(duration / 10), 5)  # At least 5 frames
                selected_indices = [
                    int(i * total_frames / num_frames)
                    for i in range(num_frames)
                ]
                method_used = 'uniform'
                print(f"Strategy: UNIFORM (static, {num_frames} frames based on {duration:.1f}s duration)")
            else:
                # Dynamic video -> extract ALL scene boundaries
                selected_indices = scene_boundaries
                method_used = 'scene_detect'
                print(f"Strategy: SCENE_DETECT (dynamic, all {len(scene_boundaries)} scenes)")
        else:
            # Fixed max_frames mode (original behavior)
            if avg_frame_diff < 4.0 or scene_count < 3:
                # Static -> uniform
                selected_indices = sorted(uniform_indices)
                method_used = 'uniform'
                print(f"Strategy: Using UNIFORM method (static sequence)")

            elif scene_count >= max_frames:
                # Dynamic -> scene_detect
                selected_indices = scene_boundaries[:max_frames]
                method_used = 'scene_detect'
                print(f"Strategy: Using SCENE_DETECT method (dynamic sequence)")

            else:
                # Hybrid
                selected_indices = list(scene_boundaries)

                if len(selected_indices) < max_frames:
                    supplement = [
                        idx for idx in sorted(uniform_indices)
                        if idx not in scene_boundaries
                    ]
                    need_count = max_frames - len(selected_indices)
                    selected_indices.extend(supplement[:need_count])

                selected_indices = sorted(selected_indices[:max_frames])
                method_used = 'hybrid'
                print(f"Strategy: Using HYBRID method")

        # Extract selected frames
        frames = []
        selected_paths = []

        for idx in selected_indices:
            frame = cv2.imread(image_paths[idx])
            if frame is not None:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frames.append(frame_rgb)
                selected_paths.append(image_paths[idx])

        print(f"Extracted {len(frames)} frames using {method_used} strategy")

        return frames, selected_paths, selected_indices

    def extract_frames_uniform(self, video_path: str, num_frames: int) -> List[np.ndarray]:
        """Extract frames at uniform intervals.

        Args:
            video_path: Path to video file
            num_frames: Number of frames to extract

        Returns:
            List of frame arrays (RGB format)
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")

        try:
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            # Calculate frame indices
            if total_frames <= num_frames:
                # Video has fewer frames than requested, extract all
                indices = list(range(total_frames))
            else:
                # Calculate evenly spaced indices
                indices = [
                    int(i * total_frames / num_frames)
                    for i in range(num_frames)
                ]

            frames = []
            for idx in indices:
                # Seek to frame
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()

                if ret:
                    # Convert BGR to RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frames.append(frame_rgb)
                else:
                    print(f"Warning: Failed to read frame at index {idx}")

            return frames

        finally:
            cap.release()

    def extract_frames_scene_detect(
        self,
        video_path: str,
        max_frames: Optional[int] = None
    ) -> List[np.ndarray]:
        """Extract frames at scene boundaries using scene detection.

        Args:
            video_path: Path to video file
            max_frames: Maximum number of frames to extract (None = all scenes)

        Returns:
            List of frame arrays (RGB format) at detected scene boundaries
        """
        from processors.scene_detector import SceneDetector

        # Initialize scene detector with parameters from self
        detector = SceneDetector(
            threshold=self.threshold,
            min_scene_duration=self.min_scene_duration,
        )

        # Detect scene boundaries
        scene_indices = detector.detect_scenes(video_path)
        print(f"Detected {len(scene_indices)} scene boundaries")

        # Limit to max_frames if specified
        if max_frames is not None and len(scene_indices) > max_frames:
            scene_indices = scene_indices[:max_frames]
            print(f"Limited to first {max_frames} scenes")

        # Extract frames at these indices
        frames = self._extract_frames_at_indices(video_path, scene_indices)

        return frames

    def _extract_frames_at_indices(
        self,
        video_path: str,
        indices: List[int]
    ) -> List[np.ndarray]:
        """Extract frames at specific indices.

        Args:
            video_path: Path to video file
            indices: List of frame indices to extract

        Returns:
            List of frame arrays (RGB format)
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")

        try:
            frames = []
            for idx in indices:
                # Seek to frame
                cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
                ret, frame = cap.read()

                if ret:
                    # Convert BGR to RGB
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    frames.append(frame_rgb)
                else:
                    print(f"Warning: Failed to read frame at index {idx}")

            return frames

        finally:
            cap.release()

    def extract_frames_hybrid(
        self,
        video_path: str,
        max_frames: Optional[int] = None
    ) -> List[np.ndarray]:
        """Extract frames using hybrid strategy with disk caching.

        This method:
        1. Single pass through video, caching both uniform and scene boundary frames to disk
        2. Analyzes video characteristics (frame difference, scene count)
        3. Selects optimal strategy based on analysis:
           - Static video (avg_diff < 4.0 or scenes < 3) -> use uniform frames
           - Dynamic video (scenes >= max_frames) -> use scene_detect frames
           - Medium dynamics -> hybrid: scene boundaries + uniform supplement

        Args:
            video_path: Path to video file
            max_frames: Maximum number of frames to extract (default: self.max_frames)

        Returns:
            List of frame arrays (RGB format)
        """
        if max_frames is None:
            max_frames = self.max_frames

        # Create temporary cache directory
        cache_dir = Path(tempfile.gettempdir()) / f"keyframe_cache_{abs(hash(video_path))}"
        cache_dir.mkdir(exist_ok=True)

        uniform_cache_dir = cache_dir / "uniform"
        scene_cache_dir = cache_dir / "scene"
        uniform_cache_dir.mkdir(exist_ok=True)
        scene_cache_dir.mkdir(exist_ok=True)

        # Phase 1: Single pass - cache both uniform and scene frames
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")

        try:
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps > 0 else 0

            # Precompute uniform sampling indices
            # If adaptive mode, cache based on potential max frames (duration / 10 + buffer)
            if self.adaptive_num_frames:
                potential_max = max(int(duration / 10) + 5, max_frames)
            else:
                potential_max = max_frames

            uniform_indices = set([
                int(i * total_frames / potential_max)
                for i in range(potential_max)
            ])

            # Calculate minimum frames between scenes
            min_frames = int(self.min_scene_duration * fps) if fps > 0 else 25

            # Cache maps and analysis data
            uniform_cache_map = {}  # {frame_idx: cache_path}
            scene_cache_map = {}    # {frame_idx: cache_path}
            frame_diffs = []
            scene_boundaries = [0]

            frame_idx = 0
            prev_gray = None

            print(f"Analyzing video and caching candidate frames...")

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # Calculate frame difference
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                if prev_gray is not None:
                    diff = cv2.absdiff(prev_gray, gray)
                    diff_score = np.mean(diff)
                    frame_diffs.append(diff_score)

                    # Detect scene boundary
                    if diff_score > self.threshold:
                        if frame_idx - scene_boundaries[-1] >= min_frames:
                            scene_boundaries.append(frame_idx)
                            # Cache scene boundary frame to disk
                            scene_path = scene_cache_dir / f"scene_{frame_idx:06d}.jpg"
                            cv2.imwrite(str(scene_path), frame, [cv2.IMWRITE_JPEG_QUALITY, self.output_quality])
                            scene_cache_map[frame_idx] = scene_path

                # Cache uniform sampling points to disk
                if frame_idx in uniform_indices:
                    uniform_path = uniform_cache_dir / f"uniform_{frame_idx:06d}.jpg"
                    cv2.imwrite(str(uniform_path), frame, [cv2.IMWRITE_JPEG_QUALITY, self.output_quality])
                    uniform_cache_map[frame_idx] = uniform_path

                prev_gray = gray
                frame_idx += 1

        finally:
            cap.release()

        # Phase 2: Strategy selection based on analysis
        avg_frame_diff = np.mean(frame_diffs) if frame_diffs else 0
        scene_count = len(scene_boundaries)
        duration = total_frames / fps if fps > 0 else 0

        print(f"Video analysis: avg_diff={avg_frame_diff:.2f}, scene_count={scene_count}")

        selected_cache_paths = []
        method_used = ''

        if self.adaptive_num_frames:
            # Adaptive mode: let content determine the number
            if avg_frame_diff < 4.0 or scene_count < 3:
                # Static video -> extract based on duration (1 frame per 10 seconds)
                num_frames = max(int(duration / 10), 5)  # At least 5 frames
                # Use the cached uniform frames, select num_frames evenly from them
                all_uniform_indices = sorted(uniform_cache_map.keys())
                if len(all_uniform_indices) >= num_frames:
                    # Select evenly spaced indices from cached frames
                    step = len(all_uniform_indices) / num_frames
                    selected_indices = [all_uniform_indices[int(i * step)] for i in range(num_frames)]
                else:
                    selected_indices = all_uniform_indices
                selected_cache_paths = [uniform_cache_map[idx] for idx in selected_indices]
                method_used = 'uniform'
                print(f"Strategy: UNIFORM (static, {len(selected_cache_paths)} frames based on {duration:.1f}s duration)")
            else:
                # Dynamic video -> extract ALL scene boundaries
                selected_cache_paths = [scene_cache_map[idx] for idx in scene_boundaries if idx in scene_cache_map]
                method_used = 'scene_detect'
                print(f"Strategy: SCENE_DETECT (dynamic, all {len(selected_cache_paths)} scenes)")
        else:
            # Fixed max_frames mode (original behavior)
            if avg_frame_diff < 4.0 or scene_count < 3:
                # Static video -> use uniform sampling
                selected_indices = sorted(uniform_cache_map.keys())
                selected_cache_paths = [uniform_cache_map[idx] for idx in selected_indices]
                method_used = 'uniform'
                print(f"Strategy: Using UNIFORM method (static video)")

            elif scene_count >= max_frames:
                # Dynamic video with many scenes -> use scene_detect
                selected_indices = scene_boundaries[:max_frames]
                selected_cache_paths = [
                    scene_cache_map[idx] for idx in selected_indices
                    if idx in scene_cache_map
                ]
                method_used = 'scene_detect'
                print(f"Strategy: Using SCENE_DETECT method (dynamic video)")

            else:
                # Medium dynamics -> hybrid approach
                scene_indices = list(scene_cache_map.keys())
                scene_paths = [scene_cache_map[idx] for idx in scene_indices]

                if len(scene_paths) < max_frames:
                    # Supplement with uniform frames (avoid overlap)
                    uniform_supplement = [
                        (idx, uniform_cache_map[idx])
                        for idx in sorted(uniform_cache_map.keys())
                        if idx not in scene_boundaries
                    ]
                    need_count = max_frames - len(scene_paths)
                    selected_cache_paths = scene_paths + [path for _, path in uniform_supplement[:need_count]]
                else:
                    selected_cache_paths = scene_paths[:max_frames]

                method_used = 'hybrid'
                print(f"Strategy: Using HYBRID method (scene={len(scene_paths)}, supplement={len(selected_cache_paths) - len(scene_paths)})")

        # Phase 3: Read cached frames from disk
        frames = []
        for cache_path in selected_cache_paths:
            frame_bgr = cv2.imread(str(cache_path))
            if frame_bgr is not None:
                frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                frames.append(frame_rgb)

        # Cleanup cache directory
        try:
            shutil.rmtree(cache_dir)
        except Exception as e:
            print(f"Warning: Failed to cleanup cache directory: {e}")

        print(f"Extracted {len(frames)} frames using {method_used} strategy")

        return frames

    def _save_frames(
        self,
        frames: List[np.ndarray],
        output_dir: str,
        video_id: str,
        frame_indices: Optional[List[int]] = None
    ) -> List[str]:
        """Save frames to disk.

        Args:
            frames: List of frame arrays
            output_dir: Directory to save frames
            video_id: Video identifier for naming
            frame_indices: Optional list of original frame indices (for image sequences)

        Returns:
            List of saved frame paths
        """
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

        frame_paths = []
        for i, frame in enumerate(frames):
            # Generate filename - use original index if available
            if frame_indices is not None and i < len(frame_indices):
                frame_idx = frame_indices[i]
            else:
                frame_idx = i

            filename = f"{video_id}_frame_{frame_idx:04d}.{self.output_format}"
            frame_path = os.path.join(output_dir, filename)

            # Convert numpy array to PIL Image
            pil_image = Image.fromarray(frame)

            # Save with quality settings
            if self.output_format.lower() in ['jpg', 'jpeg']:
                pil_image.save(frame_path, quality=self.output_quality, optimize=True)
            else:
                pil_image.save(frame_path)

            frame_paths.append(frame_path)

        return frame_paths

    def _generate_video_id(self, video_path: str) -> str:
        """Generate unique identifier for video.

        Args:
            video_path: Path to video file

        Returns:
            Unique identifier string
        """
        # Use filename + file size + mtime for ID
        stat = os.stat(video_path)
        content = f"{video_path}_{stat.st_size}_{stat.st_mtime}"
        hash_id = hashlib.md5(content.encode()).hexdigest()[:16]

        filename = Path(video_path).stem
        # Clean filename (remove special characters)
        filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_'))
        filename = filename.replace(' ', '_')

        return f"{filename}_{hash_id}"

    def extract_frames(
        self,
        video_path: str,
        output_dir: Optional[str] = None,
        save_frames: bool = True,
        video_id: Optional[str] = None,
    ) -> List[str]:
        """Main entry point: Extract key frames from video or image sequence.

        Args:
            video_path: Path to input video file or image sequence directory
            output_dir: Directory to save frames (auto-created if None)
            save_frames: Whether to save frames to disk
            video_id: Optional identifier for naming output files

        Returns:
            List of paths to extracted frame images (if save_frames=True)
            or list of frame arrays (if save_frames=False)

        Raises:
            FileNotFoundError: Video file or directory not found
            ValueError: Video cannot be opened or is corrupted
        """
        # Validate input
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file or directory not found: {video_path}")

        # Check if input is image sequence or video file
        is_image_seq = self._is_image_sequence(video_path)

        # Generate video ID if not provided
        if video_id is None:
            video_id = self._generate_video_id(video_path)

        # Get info and extract frames
        frame_indices = None  # Will hold original indices for image sequences

        if is_image_seq:
            # Process image sequence
            info = self.get_image_sequence_info(video_path)
            print(f"Image sequence info: {info['duration']:.1f}s, {info['frame_count']} frames, {info['resolution']}")

            # Extract frames based on method
            if self.method == 'uniform':
                frames, source_paths, frame_indices = self.extract_frames_uniform_from_images(video_path, self.max_frames)
            elif self.method == 'scene_detect':
                frames, source_paths, frame_indices = self.extract_frames_scene_detect_from_images(video_path, self.max_frames)
            elif self.method == 'hybrid':
                frames, source_paths, frame_indices = self.extract_frames_hybrid_from_images(video_path, self.max_frames)
            elif self.method == 'adaptive':
                raise NotImplementedError(
                    f"Method '{self.method}' not implemented yet. "
                    f"Available methods: 'uniform', 'scene_detect', 'hybrid'"
                )
            else:
                raise ValueError(
                    f"Invalid method: {self.method}. "
                    f"Available methods: 'uniform', 'scene_detect', 'hybrid'"
                )
        else:
            # Process video file
            info = self.get_video_info(video_path)
            print(f"Video info: {info['duration']:.1f}s, {info['frame_count']} frames, {info['resolution']}")

            # Extract frames based on method
            if self.method == 'uniform':
                frames = self.extract_frames_uniform(video_path, self.max_frames)
            elif self.method == 'scene_detect':
                frames = self.extract_frames_scene_detect(video_path, self.max_frames)
            elif self.method == 'hybrid':
                frames = self.extract_frames_hybrid(video_path, self.max_frames)
            elif self.method == 'adaptive':
                raise NotImplementedError(
                    f"Method '{self.method}' not implemented yet. "
                    f"Available methods: 'uniform', 'scene_detect', 'hybrid'"
                )
            else:
                raise ValueError(
                    f"Invalid method: {self.method}. "
                    f"Available methods: 'uniform', 'scene_detect', 'hybrid'"
                )

            source_paths = None  # Video files don't have source paths

        print(f"Extracted {len(frames)} frames using method '{self.method}'")

        # Deduplication (if enabled)
        if self.deduplicate and len(frames) > 1:
            original_count = len(frames)
            frames = self.deduplicate_frames(frames, self.similarity_threshold)
            print(f"Deduplication: {original_count} -> {len(frames)} frames")

        # Save or return frames
        if save_frames:
            if output_dir is None:
                output_dir = f"/tmp/keyframes/{video_id}"

            frame_paths = self._save_frames(frames, output_dir, video_id, frame_indices)
            print(f"Frames saved to: {output_dir}")
            return frame_paths
        else:
            return frames

    def deduplicate_frames(
        self,
        frames: List[np.ndarray],
        threshold: float = 0.95
    ) -> List[np.ndarray]:
        """Remove highly similar consecutive frames.

        Args:
            frames: List of frame arrays
            threshold: Similarity threshold (0-1), frames more similar than this are removed

        Returns:
            Deduplicated list of frames
        """
        if len(frames) <= 1:
            return frames

        unique_frames = [frames[0]]

        for i in range(1, len(frames)):
            similarity = self._calculate_frame_similarity(frames[i-1], frames[i])

            if similarity < threshold:
                unique_frames.append(frames[i])
            else:
                print(f"Skipping frame {i} (similarity: {similarity:.3f})")

        return unique_frames

    def _calculate_frame_similarity(self, frame1: np.ndarray, frame2: np.ndarray) -> float:
        """Calculate similarity between two frames using histogram comparison.

        Args:
            frame1: First frame array
            frame2: Second frame array

        Returns:
            Similarity score (0-1), where 1 means identical
        """
        # Resize for faster computation
        f1 = cv2.resize(frame1, (64, 64))
        f2 = cv2.resize(frame2, (64, 64))

        # Convert to OpenCV format (RGB -> BGR for histogram)
        f1_bgr = cv2.cvtColor(f1, cv2.COLOR_RGB2BGR)
        f2_bgr = cv2.cvtColor(f2, cv2.COLOR_RGB2BGR)

        # Calculate RGB histograms (8 bins per channel)
        hist1 = cv2.calcHist([f1_bgr], [0, 1, 2], None, [8, 8, 8],
                            [0, 256, 0, 256, 0, 256])
        hist2 = cv2.calcHist([f2_bgr], [0, 1, 2], None, [8, 8, 8],
                            [0, 256, 0, 256, 0, 256])

        # Normalize histograms
        hist1 = cv2.normalize(hist1, hist1).flatten()
        hist2 = cv2.normalize(hist2, hist2).flatten()

        # Calculate correlation
        similarity = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)

        return similarity


if __name__ == "__main__":
    # Simple test
    import sys

    if len(sys.argv) < 2:
        print("Usage: python keyframe_extractor.py <video_path>")
        sys.exit(1)

    video_path = sys.argv[1]

    # Test extractor
    extractor = KeyFrameExtractor(
        method='uniform',
        max_frames=10,
        deduplicate=False,
    )

    try:
        # Get video info
        info = extractor.get_video_info(video_path)
        print(f"\n=== Video Information ===")
        for key, value in info.items():
            print(f"{key}: {value}")

        # Extract frames
        print(f"\n=== Extracting Frames ===")
        frame_paths = extractor.extract_frames(
            video_path=video_path,
            save_frames=True,
        )

        print(f"\n=== Results ===")
        print(f"Extracted {len(frame_paths)} frames:")
        for i, path in enumerate(frame_paths, 1):
            print(f"  {i}. {path}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
