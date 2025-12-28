"""
Service for streaming YouTube livestream with real-time anomaly detection.
"""

import cv2
import asyncio
import base64
import numpy as np
from typing import AsyncGenerator, Optional, List, Dict
import logging
from collections import deque
from concurrent.futures import ThreadPoolExecutor

from app.services.anomaly_service import inference_anomaly

logger = logging.getLogger(__name__)
# Global session manager to track active streams
active_stream_sessions: Dict[str, 'YouTubeStreamProcessor'] = {}

# Thread pool for non-blocking video capture reads
thread_pool = ThreadPoolExecutor(max_workers=10)

class YouTubeStreamProcessor:
    """
    Process YouTube livestream with anomaly detection.
    Implements sliding window inference with frame skipping.
    """
    
    def __init__(
        self,
        youtube_url: str,
        session_id: Optional[str] = None,
        batch_size: int = 7,
        skip_frames: int = 5,
        target_fps: int = 30,
        target_width: int = 1280,
        target_height: int = 720
    ):
        """
        Initialize YouTube stream processor.
        
        Args:
            youtube_url: YouTube livestream URL
            session_id: Session ID for tracking and stopping stream
            batch_size: Number of frames per batch (default 7)
            skip_frames: Number of frames to skip between inferences
            target_fps: Target FPS for output stream
            target_width: Target frame width
            target_height: Target frame height
        """
        self.youtube_url = youtube_url
        self.session_id = session_id
        self.batch_size = batch_size
        self.skip_frames = skip_frames
        self.target_fps = target_fps
        self.target_width = target_width
        self.target_height = target_height
        
        # Flag to stop stream
        self.should_stop = False
        
        # Frame buffer for sliding window
        self.frame_buffer = deque(maxlen=batch_size)
        self.frame_count = 0
        
        # Detection results cache - maps frame_id to detections
        self.detection_cache: Dict[int, List[dict]] = {}
        
        # Output frame buffer for delayed streaming (to wait for inference)
        self.output_buffer = deque(maxlen=60)  # Buffer up to 60 frames (~2 seconds)
        
        # Track which frames should display which detections (persistent bbox)
        self.persistent_detections: Dict[int, List[dict]] = {}
        
        # Video capture
        self.cap: Optional[cv2.VideoCapture] = None
        
    async def get_youtube_stream_url(self) -> str:
        """
        Extract direct stream URL from YouTube URL using yt-dlp.
        Falls back to direct URL if yt-dlp fails.
        """
        try:
            # Try using yt-dlp if available
            import yt_dlp
            
            ydl_opts = {
                'format': 'best[height<=720]',
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(self.youtube_url, download=False)
                stream_url = info['url']
                logger.info(f"Extracted YouTube stream URL using yt-dlp")
                return stream_url
        except ImportError:
            logger.warning("yt-dlp not available, using direct URL")
            return self.youtube_url
        except Exception as e:
            logger.warning(f"Failed to extract stream URL: {e}, using direct URL")
            return self.youtube_url
    
    def _frame_to_base64(self, frame: np.ndarray) -> str:
        """Convert frame to base64 string."""
        _, buffer = cv2.imencode('.jpg', frame)
        return base64.b64encode(buffer).decode('utf-8')
    
    def _draw_detections(self, frame: np.ndarray, detections: List[dict]) -> np.ndarray:
        """
        Draw bounding boxes, class names, and anomaly scores on frame.
        
        Args:
            frame: Input frame
            detections: List of detection results with bbox, class_id, anomaly_score
            
        Returns:
            Frame with drawn detections
        """
        frame_copy = frame.copy()
        
        for detection in detections:
            try:
                # Parse bounding box
                bbox_str = detection.get("bounding_box", "0,0,0,0")
                bbox_parts = bbox_str.split(',')
                if len(bbox_parts) != 4:
                    continue
                    
                x_min, y_min, x_max, y_max = map(int, bbox_parts)
                
                # Get detection info
                anomaly_score = detection.get("anomaly_score", 0.0)
                class_id = detection.get("class_id", 0)
                
                # Determine color based on anomaly score
                if anomaly_score >= 0.8:
                    color = (0, 0, 255)  # Red - critical
                elif anomaly_score >= 0.6:
                    color = (0, 165, 255)  # Orange - high
                elif anomaly_score >= 0.4:
                    color = (0, 255, 255)  # Yellow - medium
                else:
                    color = (0, 255, 0)  # Green - low
                
                # Draw bounding box
                cv2.rectangle(frame_copy, (x_min, y_min), (x_max, y_max), color, 2)
                
                # Prepare text
                text = f"Class {class_id} | Score: {anomaly_score:.2f}"
                
                # Calculate text size for background
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 0.6
                thickness = 2
                (text_width, text_height), baseline = cv2.getTextSize(
                    text, font, font_scale, thickness
                )
                
                # Draw text background
                cv2.rectangle(
                    frame_copy,
                    (x_min, y_min - text_height - baseline - 5),
                    (x_min + text_width, y_min),
                    color,
                    -1
                )
                
                # Draw text
                cv2.putText(
                    frame_copy,
                    text,
                    (x_min, y_min - baseline - 5),
                    font,
                    font_scale,
                    (255, 255, 255),
                    thickness
                )
                
            except Exception as e:
                logger.error(f"Error drawing detection: {e}")
                continue
        
        return frame_copy
    
    def stop(self):
        """Stop the stream gracefully."""
        logger.info(f"Stopping stream for session {self.session_id}")
        self.should_stop = True
        if self.cap:
            self.cap.release()
    
    def _read_frame_sync(self):
        """Synchronous frame read for use in thread pool."""
        if self.cap is None or self.should_stop:
            return False, None
        return self.cap.read()
    
    async def _run_inference_batch(self, frames: List[np.ndarray], middle_frame_id: int):
        """
        Run inference on a batch of frames asynchronously.
        Store results in cache and mark for persistent display.
        """
        try:
            # Convert frames to base64
            frames_base64 = [self._frame_to_base64(frame) for frame in frames]
            
            # Run inference
            detections = await inference_anomaly(frames_base64)
            
            # Cache results for middle frame
            self.detection_cache[middle_frame_id] = detections
            
            # Make detections persistent across multiple frames
            # Display bbox on frames from middle_frame to middle_frame + (skip_frames * 2)
            # This ensures bbox is visible even with stream delay
            persist_duration = self.skip_frames * 3  # Show bbox for 3x skip duration
            for offset in range(persist_duration + 1):
                frame_to_mark = middle_frame_id + offset
                self.persistent_detections[frame_to_mark] = detections
            
            logger.info(f"Inference completed for frame {middle_frame_id}: {len(detections)} detections (persistent for {persist_duration} frames)")
            
        except Exception as e:
            logger.error(f"Error in inference for frame {middle_frame_id}: {e}")
            self.detection_cache[middle_frame_id] = []
    
    async def stream_with_detection(self) -> AsyncGenerator[bytes, None]:
        """
        Stream YouTube video with real-time anomaly detection.
        
        Yields:
            JPEG-encoded frames with drawn bounding boxes
        """
        try:
            # Get stream URL
            stream_url = await self.get_youtube_stream_url()
            
            # Open video capture
            self.cap = cv2.VideoCapture(stream_url)
            
            if not self.cap.isOpened():
                raise ValueError("Failed to open YouTube stream")
            
            logger.info(f"Started YouTube stream: {self.youtube_url}")
            
            # Set buffer size to reduce latency
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            inference_task: Optional[asyncio.Task] = None
            last_inference_frame = -1
            min_buffer_size = 60  # Minimum frames to buffer before streaming (for inference delay)
            
            while True:
                # Check if stream should stop
                if self.should_stop:
                    logger.info(f"Stream stopped by request for session {self.session_id}")
                    break
                
                # Read frame using thread pool to avoid blocking
                try:
                    ret, frame = await asyncio.wait_for(
                        asyncio.to_thread(self._read_frame_sync),
                        timeout=5.0  # 5 second timeout
                    )
                except asyncio.TimeoutError:
                    logger.warning("Frame read timeout, checking if should stop...")
                    if self.should_stop:
                        break
                    continue
                
                # Check again after potentially blocking read
                if self.should_stop:
                    logger.info(f"Stream stopped by request for session {self.session_id}")
                    break
                
                if not ret:
                    logger.warning("Failed to read frame, checking if should stop...")
                    if self.should_stop:
                        break
                    
                    logger.warning("Attempting to reconnect...")
                    await asyncio.sleep(1)
                    
                    # Check again after sleep
                    if self.should_stop:
                        break
                    
                    # Try to reconnect
                    self.cap.release()
                    stream_url = await self.get_youtube_stream_url()
                    self.cap = cv2.VideoCapture(stream_url)
                    continue
                
                # Resize frame to target resolution
                if frame.shape[1] != self.target_width or frame.shape[0] != self.target_height:
                    frame = cv2.resize(frame, (self.target_width, self.target_height))
                
                self.frame_count += 1
                
                # Add frame to inference buffer
                self.frame_buffer.append(frame.copy())
                
                # Add frame with its ID to output buffer
                self.output_buffer.append((self.frame_count, frame.copy()))
                
                # Check if we should run inference
                middle_frame_id = self.frame_count - self.batch_size // 2
                should_inference = (
                    len(self.frame_buffer) == self.batch_size and
                    self.frame_count >= self.batch_size and
                    (self.frame_count - last_inference_frame) >= self.skip_frames
                )
                
                if should_inference:
                    # Run inference in background
                    batch_frames = list(self.frame_buffer)
                    inference_task = asyncio.create_task(
                        self._run_inference_batch(batch_frames, middle_frame_id)
                    )
                    last_inference_frame = self.frame_count
                    logger.info(f"Started inference for frame {middle_frame_id} (current: {self.frame_count})")
                
                # Wait until buffer has enough frames (create delay for inference)
                if len(self.output_buffer) < min_buffer_size:
                    await asyncio.sleep(1.0 / self.target_fps)
                    continue
                
                # Check if should stop before yielding
                if self.should_stop:
                    logger.info(f"Stream stopped by request for session {self.session_id}")
                    break
                
                # Get oldest frame from output buffer
                frame_id, output_frame = self.output_buffer.popleft()
                
                # Check if we have persistent detections for this frame
                current_detections = self.persistent_detections.get(frame_id, [])
                
                # Draw detections on frame
                if current_detections:
                    output_frame = self._draw_detections(output_frame, current_detections)
                    logger.debug(f"Drawing {len(current_detections)} detections on frame {frame_id}")
                
                # Clear old persistent detections to save memory
                old_frame_id = frame_id - 100
                if old_frame_id in self.persistent_detections:
                    del self.persistent_detections[old_frame_id]
                if old_frame_id in self.detection_cache:
                    del self.detection_cache[old_frame_id]
                
                # Encode frame as JPEG
                _, buffer = cv2.imencode('.jpg', output_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                frame_bytes = buffer.tobytes()
                
                # Yield frame in multipart format
                yield (
                    b'--frame\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n'
                )
                
                # Control frame rate (add small delay to prevent overwhelming the system)
                await asyncio.sleep(1.0 / self.target_fps)
                
        except Exception as e:
            logger.error(f"Error in YouTube stream processing: {e}")
            raise
        
        finally:
            # Cleanup
            if self.cap:
                self.cap.release()
            logger.info("YouTube stream closed")


async def stream_youtube_with_anomaly_detection(
    youtube_url: str,
    session_id: Optional[str] = None,
    batch_size: int = 7,
    skip_frames: int = 5,
    target_fps: int = 30,
    target_width: int = 1280,
    target_height: int = 720
) -> AsyncGenerator[bytes, None]:
    """
    Stream YouTube livestream with real-time anomaly detection.
    
    Args:
        youtube_url: YouTube livestream URL
        session_id: Session ID for tracking and stopping stream
        batch_size: Number of frames per batch for inference (default 7)
        skip_frames: Number of frames to skip between inferences (default 5)
        target_fps: Target FPS for output stream (default 30)
        target_width: Target frame width (default 1280)
        target_height: Target frame height (default 720)
        
    Yields:
        JPEG-encoded frames with drawn anomaly detections
    """
    processor = YouTubeStreamProcessor(
        youtube_url=youtube_url,
        session_id=session_id,
        batch_size=batch_size,
        skip_frames=skip_frames,
        target_fps=target_fps,
        target_width=target_width,
        target_height=target_height
    )
    
    # Register session if session_id is provided
    if session_id:
        active_stream_sessions[session_id] = processor
        logger.info(f"Registered stream session {session_id}")
    
    try:
        async for frame_data in processor.stream_with_detection():
            yield frame_data
    finally:
        # Cleanup session
        if session_id and session_id in active_stream_sessions:
            del active_stream_sessions[session_id]
            logger.info(f"Cleaned up stream session {session_id}")


def stop_stream_session(session_id: str) -> bool:
    """
    Stop an active stream session.
    
    Args:
        session_id: Session ID to stop
        
    Returns:
        True if session was found and stopped, False otherwise
    """
    if session_id in active_stream_sessions:
        processor = active_stream_sessions[session_id]
        processor.stop()
        logger.info(f"Stopped stream session {session_id}")
        return True
    else:
        logger.warning(f"Stream session {session_id} not found")
        return False
