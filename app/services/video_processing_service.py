"""
Service for processing videos and detecting anomalies using AI server.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any
from fastapi import HTTPException, status
import asyncio
import logging

from app.models.models import Anomaly, Camera
from app.core.video_processor import VideoProcessor
from app.core.ai_client import get_ai_client
from app.core.database import async_session_maker
from datetime import datetime

logger = logging.getLogger(__name__)


async def process_video_for_anomalies(
    db: AsyncSession,
    camera_id: int,
    user_id: int,
    batch_size: int = 7,
    sliding_window: int = 1
) -> Dict[str, Any]:
    """
    Process video from camera and detect anomalies.
    
    Steps:
    1. Validate camera (exists, belongs to user, type is 'local')
    2. Load video and extract frames
    3. Create batches with sliding window
    4. Send batches to AI server (with concurrency limit)
    5. Parse responses and save anomalies to database
    
    Args:
        db: Database session
        camera_id: ID of camera to process
        user_id: ID of current user (for authorization)
        batch_size: Number of frames per batch
        sliding_window: Step size for sliding window
        
    Returns:
        Dictionary with processing results and detected anomalies
        
    Raises:
        HTTPException: If validation fails or processing errors occur
    """
    from app.services.camera_service import get_camera_by_id
    from sqlalchemy.future import select
    
    # Step 1: Validate camera
    camera = await get_camera_by_id(db, camera_id)
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera not found"
        )
    
    # Check ownership
    if camera.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to process this camera"
        )
    
    # Check camera type
    if camera.type.value != "local":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only cameras with type='local' are supported. Use different API for YouTube cameras."
        )
    
    # Check if video file exists
    video_path = camera.url
    
    try:
        # Step 2: Get video info
        video_info = VideoProcessor.get_video_info(video_path)
        
        # Step 3: Extract frames
        frames = VideoProcessor.extract_frames(video_path)
        
        if len(frames) < batch_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Video has only {len(frames)} frames, need at least {batch_size} frames"
            )
        
        # Step 4: Create batches
        batches_data = VideoProcessor.create_batches(
            frames=frames,
            batch_size=batch_size,
            sliding_window=sliding_window
        )
        
        total_batches = len(batches_data)
        
        # Step 5: Send batches to AI server
        ai_client = get_ai_client()

        # Check health of AI server
        if not await ai_client.check_health():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI server is not available"
            )
        results = await ai_client.process_video_batches(batches_data)
        
        # Step 6: Process results and save anomalies
        anomalies_saved = []
        anomaly_threshold = 0.5  # Configurable threshold for saving anomalies
        
        for result in results:
            if not result.get("success", False):
                continue
            
            detections = result.get("detections", [])
            middle_frame_id = result.get("middle_frame_id", 0)
            
            # Process each detection in the batch
            for detection in detections:
                anomaly_score = detection.get("anomaly_score_normalized", 0.0)
                
                # Only save if anomaly score is above threshold
                if anomaly_score >= anomaly_threshold:
                    bbox = detection.get("bbox", {})
                    bbox_str = f"{bbox.get('x_min', 0)},{bbox.get('y_min', 0)},{bbox.get('x_max', 0)},{bbox.get('y_max', 0)}"
                    
                    # Determine anomaly level based on score
                    if anomaly_score >= 0.6:
                        level = "critical"
                    elif anomaly_score >= 0.4:
                        level = "high"
                    elif anomaly_score >= 0.2:
                        level = "medium"
                    else:
                        level = "low"
                    
                    # Create anomaly record
                    anomaly = Anomaly(
                        time=datetime.utcnow(),
                        type="detected_anomaly",
                        description=f"Anomaly detected in frame {middle_frame_id} with score {anomaly_score:.4f}",
                        level=level,
                        cam_id=camera_id,
                        anomaly_score=anomaly_score,
                        bounding_box=bbox_str,
                        frame_id=middle_frame_id,
                        class_id=detection.get("class_id", 0)
                    )
                    
                    db.add(anomaly)
                    anomalies_saved.append(anomaly)
        
        # Commit all anomalies
        await db.commit()
        
        # Refresh anomalies to get IDs
        for anomaly in anomalies_saved:
            await db.refresh(anomaly)
        # Update camera status to 'active' after processing
        camera.status = "active"
        db.add(camera)
        await db.commit()

        return {
            "success": True,
            "message": f"Processed {total_batches} batches from video",
            "camera_id": camera_id,
            "video_info": video_info,
            "total_frames": len(frames),
            "total_batches": total_batches,
            "anomalies_detected": len(anomalies_saved),
            "anomalies": anomalies_saved
        }
        
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video file not found: {str(e)}"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Video processing error: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process video: {str(e)}"
        )


async def process_video_background(camera_id: int, user_id: int, batch_size: int = 7, sliding_window: int = 1):
    """
    Background task to process video for anomalies with its own database session.
    This function catches all exceptions to prevent them from affecting the main request.
    
    Args:
        camera_id: ID of camera to process
        user_id: ID of current user
        batch_size: Number of frames per batch
        sliding_window: Step size for sliding window
    """
    try:
        # Create a new database session for this background task
        async with async_session_maker() as db:
            logger.info(f"Starting background video processing for camera {camera_id}")
            result = await process_video_for_anomalies(
                db=db,
                camera_id=camera_id,
                user_id=user_id,
                batch_size=batch_size,
                sliding_window=sliding_window
            )
            logger.info(f"Completed video processing for camera {camera_id}: {result.get('message')}")
            return result
    except Exception as e:
        logger.error(f"Error in background video processing for camera {camera_id}: {str(e)}", exc_info=True)
        # Update camera status to indicate error
        try:
            async with async_session_maker() as db:
                from app.services.camera_service import get_camera_by_id
                camera = await get_camera_by_id(db, camera_id)
                if camera:
                    camera.status = "error"
                    db.add(camera)
                    await db.commit()
        except Exception as inner_e:
            logger.error(f"Failed to update camera status after error: {str(inner_e)}")
