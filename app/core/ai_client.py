"""
AI Server client for sending inference requests.
Handles communication with the AI anomaly detection server.
"""

import aiohttp
import asyncio
from typing import List, Dict, Any, Optional
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration from environment
AI_SERVER_BASE_URL = os.getenv("AI_SERVER_BASE_URL", "http://localhost:5000")
MAX_CONCURRENT_REQUESTS = int(os.getenv("AI_MAX_CONCURRENT_REQUESTS", "10"))


class AIServerClient:
    """Client for communicating with AI anomaly detection server"""
    
    def __init__(
        self,
        server_url: str = AI_SERVER_BASE_URL,
        max_concurrent: int = MAX_CONCURRENT_REQUESTS,
        timeout: int = 300  # 5 minutes timeout for inference
    ):
        """
        Initialize AI server client.
        
        Args:
            server_url: URL of the AI inference endpoint
            max_concurrent: Maximum number of concurrent requests
            timeout: Request timeout in seconds
        """
        self.server_url = server_url
        self.max_concurrent = max_concurrent
        self._semaphore = None
        self._semaphore_loop = None
        self.timeout = aiohttp.ClientTimeout(total=timeout)
    
    @property
    def semaphore(self):
        """Get or create semaphore for current event loop"""
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop running, create one
            current_loop = asyncio.get_event_loop()
        
        # Create new semaphore if it doesn't exist or is bound to different loop
        if self._semaphore is None or self._semaphore_loop != current_loop:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
            self._semaphore_loop = current_loop
        
        return self._semaphore
    
    async def check_health(self) -> bool:
        """
        Check health of the AI server.
        
        Returns:
            True if server is healthy, False otherwise
        """
        health_url = self.server_url + "/health"
        
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.get(health_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("status") == "healthy"
                    else:
                        return False
        except aiohttp.ClientError:
            return False

    async def send_video_file(
        self,
        video_path: str
    ) -> Dict[str, Any]:
        """
        Send entire video file to AI server for processing (v2 endpoint).
        
        Args:
            video_path: Path to the video file
            
        Returns:
            Response from AI server with all detections
            
        Raises:
            aiohttp.ClientError: If request fails
        """
        inference_url = self.server_url + "/worker/inference/video"
        
        # Create multipart form data with video file
        data = aiohttp.FormData()
        data.add_field('video',
                      open(video_path, 'rb'),
                      filename=os.path.basename(video_path),
                      content_type='video/mp4')
        data.add_field('sliding_window', os.getenv("AI_SLIDING_WINDOW", "1"))
        data.add_field('batch_size', os.getenv("AI_DETECTION_BATCH_SIZE", "4"))
        
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(inference_url, data=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        return result
                    else:
                        error_text = await response.text()
                        raise aiohttp.ClientError(
                            f"AI server returned status {response.status}: {error_text}"
                        )
        except aiohttp.ClientError as e:
            raise e

    async def send_batch(
        self,
        frames_base64: List[str],
        batch_index: int
    ) -> Dict[str, Any]:
        """
        Send a single batch of frames to AI server.
        
        Args:
            frames_base64: List of base64 encoded frames
            batch_index: Index of this batch (for logging/tracking)
            
        Returns:
            Response from AI server
            
        Raises:
            aiohttp.ClientError: If request fails
        """
        payload = {
            "frames": frames_base64
        }
        
        async with self.semaphore:  # Limit concurrent requests
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                try:
                    async with session.post(self.server_url + "/worker/inference", json=payload) as response:
                        response.raise_for_status()
                        result = await response.json()
                        
                        # Add batch index for tracking
                        result["batch_index"] = batch_index
                        
                        return result
                        
                except aiohttp.ClientError as e:
                    raise Exception(
                        f"Failed to send batch {batch_index} to AI server: {str(e)}"
                    )
    
    async def send_batches_parallel(
        self,
        batches: List[List[str]]
    ) -> List[Dict[str, Any]]:
        """
        Send multiple batches to AI server in parallel (with semaphore limit).
        
        Args:
            batches: List of batches, where each batch is a list of base64 frames
            
        Returns:
            List of responses from AI server, in order
        """
        # Create tasks for all batches
        tasks = [
            self.send_batch(batch, index)
            for index, batch in enumerate(batches)
        ]
        
        # Execute all tasks with semaphore limiting concurrency
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Check for errors
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                raise Exception(f"Batch {i} failed: {str(result)}")
            processed_results.append(result)
        
        return processed_results
    
    async def process_video_batches(
        self,
        batches_data: List[tuple]
    ) -> List[Dict[str, Any]]:
        """
        Process all video batches and return results with frame information.
        
        Args:
            batches_data: List of (frames_base64, middle_frame_id, frame_ids) tuples
            
        Returns:
            List of results with added frame information
        """
        # Extract just the frames for sending
        batches_frames = [batch[0] for batch in batches_data]
        
        # Send all batches
        results = await self.send_batches_parallel(batches_frames)
        
        # Add frame information to results
        enriched_results = []
        for i, result in enumerate(results):
            frames_base64, middle_frame_id, frame_ids = batches_data[i]
            
            enriched_result = {
                **result,
                "middle_frame_id": middle_frame_id,
                "frame_ids": frame_ids,
                "batch_index": i
            }
            
            enriched_results.append(enriched_result)
        
        return enriched_results


# Singleton instance
_ai_client = None


def get_ai_client() -> AIServerClient:
    """Get or create AI client singleton"""
    global _ai_client
    if _ai_client is None:
        _ai_client = AIServerClient()
    return _ai_client
