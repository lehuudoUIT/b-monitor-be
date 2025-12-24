"""
Video processing utilities for anomaly detection.
Handles video loading, frame extraction, encoding, and batching.
"""

import cv2
import base64
import numpy as np
from typing import List, Tuple, Optional
import os


class VideoProcessor:
    """Utility class for video processing operations"""
    
    @staticmethod
    def load_video(video_path: str) -> cv2.VideoCapture:
        """
        Load video from path.
        
        Args:
            video_path: Path to video file
            
        Returns:
            cv2.VideoCapture object
            
        Raises:
            FileNotFoundError: If video file doesn't exist
            ValueError: If video cannot be opened
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Cannot open video: {video_path}")
        
        return cap
    
    @staticmethod
    def extract_frames(video_path: str) -> List[np.ndarray]:
        """
        Extract all frames from video.
        
        Args:
            video_path: Path to video file
            
        Returns:
            List of frames as numpy arrays
        """
        cap = VideoProcessor.load_video(video_path)
        frames = []
        
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                frames.append(frame)
        finally:
            cap.release()
        
        return frames
    
    @staticmethod
    def frame_to_base64(frame: np.ndarray) -> str:
        """
        Convert frame (numpy array) to base64 string.
        
        Args:
            frame: Frame as numpy array (from cv2.read())
            
        Returns:
            Base64 encoded string of the frame
        """
        # Encode frame to JPEG
        _, buffer = cv2.imencode('.jpg', frame)
        
        # Convert to base64
        frame_base64 = base64.b64encode(buffer).decode('utf-8')
        
        return frame_base64
    
    @staticmethod
    def create_batches(
        frames: List[np.ndarray],
        batch_size: int = 7,
        sliding_window: int = 1
    ) -> List[Tuple[List[str], int, List[int]]]:
        """
        Create batches of frames with sliding window.
        
        Args:
            frames: List of frames as numpy arrays
            batch_size: Number of frames per batch (default: 7)
            sliding_window: Step size for sliding window (default: 1)
            
        Returns:
            List of tuples: (batch_frames_base64, middle_frame_index, frame_ids)
            - batch_frames_base64: List of base64 encoded frames
            - middle_frame_index: Index of middle frame in the batch (relative)
            - frame_ids: List of original frame indices in video
            
        Example:
            For 10 frames with batch_size=7 and sliding_window=1:
            Batch 0: frames [0,1,2,3,4,5,6] -> middle_frame_id = 3 (frame index 3)
            Batch 1: frames [1,2,3,4,5,6,7] -> middle_frame_id = 4 (frame index 4)
            Batch 2: frames [2,3,4,5,6,7,8] -> middle_frame_id = 5 (frame index 5)
            Batch 3: frames [3,4,5,6,7,8,9] -> middle_frame_id = 6 (frame index 6)
        """
        if len(frames) < batch_size:
            raise ValueError(
                f"Not enough frames. Need at least {batch_size} frames, got {len(frames)}"
            )
        
        batches = []
        middle_index = batch_size // 2  # For batch_size=7, middle_index=3
        
        # Create batches with sliding window
        for i in range(0, len(frames) - batch_size + 1, sliding_window):
            # Get batch frames
            batch_frames = frames[i:i + batch_size]
            
            # Convert frames to base64
            batch_frames_base64 = [
                VideoProcessor.frame_to_base64(frame) 
                for frame in batch_frames
            ]
            
            # Frame IDs in original video (0-indexed)
            frame_ids = list(range(i, i + batch_size))
            
            # Middle frame ID in original video
            middle_frame_id = i + middle_index
            
            batches.append((batch_frames_base64, middle_frame_id, frame_ids))
        
        return batches
    
    @staticmethod
    def get_video_info(video_path: str) -> dict:
        """
        Get video information.
        
        Args:
            video_path: Path to video file
            
        Returns:
            Dictionary with video info (fps, frame_count, width, height, duration)
        """
        cap = VideoProcessor.load_video(video_path)
        
        try:
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration = frame_count / fps if fps > 0 else 0
            
            return {
                "fps": fps,
                "frame_count": frame_count,
                "width": width,
                "height": height,
                "duration": duration
            }
        finally:
            cap.release()
