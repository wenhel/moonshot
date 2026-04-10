#!/usr/bin/env python3
"""
Scene Detector

Detects scene boundaries in videos using various algorithms.
Provides standalone scene detection functionality that can be used independently
or integrated with KeyFrameExtractor.
"""

import os
import cv2
import numpy as np
from typing import List, Dict, Optional


class SceneDetector:
    """Detect scene boundaries in videos.

    Uses frame difference analysis to identify points where significant
    visual changes occur, indicating scene transitions.
    """

    def __init__(
        self,
        threshold: float = 30.0,
        min_scene_duration: float = 1.0,
        method: str = 'frame_diff',
    ):
        """Initialize scene detector.

        Args:
            threshold: Scene change threshold (0-255). Higher values = fewer scenes detected.
                Typical range: 20-50. Default: 30.0
            min_scene_duration: Minimum scene duration in seconds.
                Prevents detecting rapid flickers as separate scenes. Default: 1.0
            method: Detection method. Currently supports:
                - 'frame_diff': Frame difference analysis (default)
        """
        self.threshold = threshold
        self.min_scene_duration = min_scene_duration
        self.method = method

        # Validate method
        valid_methods = ['frame_diff']
        if method not in valid_methods:
            raise ValueError(
                f"Invalid method: {method}. Must be one of {valid_methods}"
            )

    def detect_scenes(self, video_path: str) -> List[int]:
        """Detect scene boundaries in video.

        Args:
            video_path: Path to video file

        Returns:
            List of frame indices where scene boundaries occur.
            Always includes frame 0 as the first scene start.

        Raises:
            FileNotFoundError: Video file not found
            ValueError: Cannot open video file

        Example:
            >>> detector = SceneDetector(threshold=30.0)
            >>> boundaries = detector.detect_scenes('video.mp4')
            >>> print(f"Found {len(boundaries)} scenes at frames: {boundaries}")
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        if self.method == 'frame_diff':
            return self._detect_frame_diff(video_path)
        else:
            raise ValueError(f"Unknown detection method: {self.method}")

    def _detect_frame_diff(self, video_path: str) -> List[int]:
        """Detect scenes using frame difference analysis.

        Algorithm:
        1. Convert frames to grayscale
        2. Calculate absolute difference between consecutive frames
        3. Compute mean of difference as change score
        4. If score > threshold AND min duration satisfied -> scene boundary
        5. Apply minimum scene duration constraint

        Args:
            video_path: Path to video file

        Returns:
            List of frame indices marking scene boundaries
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video file: {video_path}")

        try:
            fps = cap.get(cv2.CAP_PROP_FPS)
            min_frames = int(self.min_scene_duration * fps)

            scene_boundaries = [0]  # First frame is always a scene start
            prev_gray = None
            frame_idx = 0

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # Convert to grayscale for faster processing
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                if prev_gray is not None:
                    # Calculate frame difference
                    diff = cv2.absdiff(prev_gray, gray)
                    diff_score = np.mean(diff)

                    # Detect scene change
                    if diff_score > self.threshold:
                        # Check minimum scene duration constraint
                        if frame_idx - scene_boundaries[-1] >= min_frames:
                            scene_boundaries.append(frame_idx)

                prev_gray = gray
                frame_idx += 1

            return scene_boundaries

        finally:
            cap.release()

    def get_scene_info(self, video_path: str) -> Dict:
        """Get detailed scene statistics for video.

        Args:
            video_path: Path to video file

        Returns:
            Dict containing:
                - scene_count: Number of scenes detected
                - scene_boundaries: List of frame indices
                - scene_durations: Duration of each scene in seconds
                - avg_scene_duration: Average scene duration
                - fps: Video frame rate
                - total_frames: Total number of frames
                - total_duration: Total video duration in seconds

        Example:
            >>> detector = SceneDetector()
            >>> info = detector.get_scene_info('video.mp4')
            >>> print(f"Detected {info['scene_count']} scenes")
            >>> print(f"Average scene duration: {info['avg_scene_duration']:.1f}s")
        """
        # Detect scenes
        scene_boundaries = self.detect_scenes(video_path)

        # Get video metadata
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        total_duration = total_frames / fps if fps > 0 else 0
        cap.release()

        # Calculate scene durations
        scene_durations = []
        for i in range(len(scene_boundaries)):
            if i < len(scene_boundaries) - 1:
                # Duration from this boundary to next
                duration = (scene_boundaries[i + 1] - scene_boundaries[i]) / fps
            else:
                # Duration from last boundary to end of video
                duration = (total_frames - scene_boundaries[i]) / fps
            scene_durations.append(duration)

        return {
            'scene_count': len(scene_boundaries),
            'scene_boundaries': scene_boundaries,
            'scene_durations': scene_durations,
            'avg_scene_duration': np.mean(scene_durations) if scene_durations else 0,
            'min_scene_duration': np.min(scene_durations) if scene_durations else 0,
            'max_scene_duration': np.max(scene_durations) if scene_durations else 0,
            'fps': fps,
            'total_frames': total_frames,
            'total_duration': total_duration,
        }

    def analyze_video_dynamics(self, video_path: str, sample_rate: int = 5) -> Dict:
        """Analyze how dynamic/static the video content is.

        Useful for determining if scene detection is appropriate for a video.

        Args:
            video_path: Path to video file
            sample_rate: Sample every Nth frame (higher = faster but less accurate)

        Returns:
            Dict containing:
                - avg_frame_diff: Average frame difference score
                - max_frame_diff: Maximum frame difference observed
                - is_static: Whether video appears mostly static (bool)
                - recommended_method: 'scene_detect' or 'uniform'

        Example:
            >>> detector = SceneDetector()
            >>> analysis = detector.analyze_video_dynamics('video.mp4')
            >>> if analysis['recommended_method'] == 'scene_detect':
            >>>     scenes = detector.detect_scenes('video.mp4')
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video file: {video_path}")

        try:
            prev_gray = None
            frame_idx = 0
            diff_scores = []

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # Sample frames
                if frame_idx % sample_rate == 0:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

                    if prev_gray is not None:
                        diff = cv2.absdiff(prev_gray, gray)
                        diff_score = np.mean(diff)
                        diff_scores.append(diff_score)

                    prev_gray = gray

                frame_idx += 1

            avg_diff = np.mean(diff_scores) if diff_scores else 0
            max_diff = np.max(diff_scores) if diff_scores else 0

            # Heuristics for determining if video is static
            is_static = avg_diff < 5.0  # Very low average change
            has_scenes = max_diff > 30.0  # Some significant changes detected

            # Recommend method
            if is_static:
                recommended_method = 'uniform'
            elif has_scenes:
                recommended_method = 'scene_detect'
            else:
                recommended_method = 'uniform'

            return {
                'avg_frame_diff': avg_diff,
                'max_frame_diff': max_diff,
                'is_static': is_static,
                'has_scene_changes': has_scenes,
                'recommended_method': recommended_method,
                'samples_analyzed': len(diff_scores),
            }

        finally:
            cap.release()


if __name__ == "__main__":
    # Simple test
    import sys

    if len(sys.argv) < 2:
        print("Usage: python scene_detector.py <video_path>")
        sys.exit(1)

    video_path = sys.argv[1]

    # Test scene detector
    detector = SceneDetector(threshold=30.0, min_scene_duration=1.0)

    try:
        print(f"\n=== Analyzing Video: {video_path} ===\n")

        # Analyze video dynamics
        print("[1/3] Analyzing video dynamics...")
        dynamics = detector.analyze_video_dynamics(video_path)
        print(f"  Average frame difference: {dynamics['avg_frame_diff']:.2f}")
        print(f"  Maximum frame difference: {dynamics['max_frame_diff']:.2f}")
        print(f"  Is static: {dynamics['is_static']}")
        print(f"  Recommended method: {dynamics['recommended_method']}")

        # Detect scenes
        print(f"\n[2/3] Detecting scenes (threshold={detector.threshold})...")
        scene_boundaries = detector.detect_scenes(video_path)
        print(f"  Detected {len(scene_boundaries)} scene boundaries")
        print(f"  Scene boundaries at frames: {scene_boundaries[:10]}...")

        # Get detailed info
        print(f"\n[3/3] Getting scene statistics...")
        scene_info = detector.get_scene_info(video_path)
        print(f"  Total scenes: {scene_info['scene_count']}")
        print(f"  Average scene duration: {scene_info['avg_scene_duration']:.1f}s")
        print(f"  Min scene duration: {scene_info['min_scene_duration']:.1f}s")
        print(f"  Max scene duration: {scene_info['max_scene_duration']:.1f}s")
        print(f"  Video FPS: {scene_info['fps']:.2f}")
        print(f"  Total duration: {scene_info['total_duration']:.1f}s")

        print(f"\n=== Analysis Complete ===")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
