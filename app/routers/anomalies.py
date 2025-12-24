from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import date

from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.schemas.schemas import AnomalyCreate, AnomalyListResponse, AnomalyResponse, AnomalyLevel, VideoProcessRequest, VideoProcessResponse
from app.services import anomaly_service
from app.services.video_processing_service import process_video_for_anomalies

router = APIRouter()


@router.post("/", response_model=AnomalyResponse, status_code=status.HTTP_201_CREATED)
async def create_anomaly(
    anomaly_data: AnomalyCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new anomaly (manual logging).
    
    The anomaly can only be created for cameras owned by the authenticated user.
    
    - **time**: Time when anomaly occurred (defaults to now if not provided)
    - **type**: Type of anomaly (e.g., "traffic jam", "accident", "illegal parking")
    - **description**: Detailed description of the anomaly
    - **level**: Severity level (violations, critical, high, medium, low)
    - **cam_id**: ID of the camera that detected the anomaly (required)
    """
    anomaly = await anomaly_service.create_anomaly(db, anomaly_data, current_user.id)
    return anomaly


@router.get("/", response_model=AnomalyListResponse)
async def list_anomalies(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(10, ge=1, le=100, description="Number of records to return"),
    order: str = Query("desc", regex="^(asc|desc)$", description="Order by frame id: asc or desc"),
    field: str = Query("time", regex="^(time|frame_id)$", description="Field to order by: time or frame_id"),
    camera_id: Optional[int] = Query(None, description="Filter by camera ID"),
    level: Optional[AnomalyLevel] = Query(None, description="Filter by anomaly level"),
    frame_id: Optional[int] = Query(None, description="Filter by specific frame ID"),
    start_date: Optional[date] = Query(None, description="Filter by start date (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Filter by end date (YYYY-MM-DD)")
):
    """
    List anomalies with filtering and pagination.
    
    Returns anomalies from cameras belonging to the authenticated user.
    
    **Query Parameters:**
    - **skip**: Number of records to skip (for pagination)
    - **limit**: Maximum number of records to return (max 100)
    - **camera_id**: Filter by specific camera ID
    - **level**: Filter by anomaly level (violations, critical, high, medium, low)
    - **start_date**: Filter anomalies from this date onwards (format: YYYY-MM-DD)
    - **end_date**: Filter anomalies up to this date (format: YYYY-MM-DD)
    
    **Returns:**
    - **items**: List of anomalies
    - **total**: Total number of anomalies matching filters
    - **skip**: Current skip value
    - **limit**: Current limit value
    - **filters**: Applied filters
    
    **Example:**
    ```
    GET /anomalies?camera_id=1&level=critical&start_date=2025-01-01&limit=20
    ```
    """
    # Validate camera ownership if camera_id is provided
    if camera_id:
        from app.services.camera_service import get_camera_by_id
        camera = await get_camera_by_id(db, camera_id)
        if camera and camera.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access anomalies for this camera"
            )
    
    anomalies, total = await anomaly_service.get_anomalies(
        db=db,
        skip=skip,
        limit=limit,
        order=order,
        field=field,
        frame_id=frame_id,
        camera_id=camera_id,
        level=level,
        start_date=start_date,
        end_date=end_date,
        user_id=current_user.id
    )
    
    return {
        "items": anomalies,
        "total": total,
        "skip": skip,
        "limit": limit,
        "order": order,
        "filters": {
            "camera_id": camera_id,
            "level": level.value if level else None,
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None
        }
    }


@router.get("/{anomaly_id}", response_model=AnomalyResponse)
async def get_anomaly(
    anomaly_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific anomaly by ID.
    
    Only returns anomalies from cameras belonging to the authenticated user.
    """
    anomaly = await anomaly_service.verify_anomaly_access(db, anomaly_id, current_user.id)
    return anomaly


@router.get("/camera/{camera_id}/summary", response_model=dict)
async def get_camera_anomaly_summary(
    camera_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    days: int = Query(7, ge=1, le=90, description="Number of days to include in summary")
):
    """
    Get anomaly summary for a specific camera.
    
    Returns statistics about anomalies for the camera over the specified period.
    
    - **camera_id**: ID of the camera
    - **days**: Number of days to include (default: 7, max: 90)
    
    Returns count by level and recent anomalies.
    """
    from app.services.camera_service import get_camera_by_id
    from datetime import datetime, timedelta
    
    # Verify camera ownership
    camera = await get_camera_by_id(db, camera_id)
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera not found"
        )
    
    if camera.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this camera"
        )
    
    # Get anomalies for the period
    start_date = (datetime.now() - timedelta(days=days)).date()
    anomalies, total = await anomaly_service.get_anomalies(
        db=db,
        skip=0,
        limit=1000,  # Get all for counting
        camera_id=camera_id,
        start_date=start_date,
        user_id=current_user.id
    )
    
    # Count by level
    level_counts = {
        "violations": 0,
        "critical": 0,
        "high": 0,
        "medium": 0,
        "low": 0
    }
    
    for anomaly in anomalies:
        level_counts[anomaly.level.value] += 1
    
    return {
        "camera_id": camera_id,
        "camera_name": camera.name,
        "period_days": days,
        "total_anomalies": total,
        "by_level": level_counts,
        "recent_anomalies": anomalies[:5]  # Most recent 5
    }


@router.post("/process-video", response_model=VideoProcessResponse)
async def process_video(
    request: VideoProcessRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db)
):
    """
    Process video from a local camera to detect anomalies using AI server.
    
    **Workflow:**
    1. Validate camera (must be type='local' and owned by current user)
    2. Load video from camera's local path
    3. Extract frames and encode to base64
    4. Create batches with sliding window (default: 7 frames per batch, step=1)
    5. Send batches to AI server for inference (max 10 concurrent requests)
    6. Parse detection results (bounding boxes, anomaly scores, class IDs)
    7. Save anomalies with score >= 0.5 to database
    
    **Request Body:**
    - **camera_id**: ID of the camera (must be type='local')
    - **batch_size**: Number of frames per batch (default: 7, range: 3-30)
    - **sliding_window**: Step size for sliding window (default: 1, range: 1-10)
    
    **Response:**
    - **success**: Whether processing succeeded
    - **message**: Status message
    - **video_info**: Video metadata (fps, resolution, duration, frame count)
    - **total_frames**: Number of frames extracted
    - **total_batches**: Number of batches created and sent to AI
    - **anomalies_detected**: Number of anomalies saved (score >= 0.5)
    - **anomalies**: List of detected anomaly objects
    
    **Error Cases:**
    - 404: Camera not found or video file not found
    - 403: Camera does not belong to user
    - 400: Camera type is not 'local' or video has insufficient frames
    - 500: Video processing error or AI server error
    
    **Example:**
    ```json
    {
        "camera_id": 1,
        "batch_size": 7,
        "sliding_window": 1
    }
    ```
    
    **AI Server Expectation:**
    - Endpoint: POST http://localhost:5000/worker/inference
    - Request: {"frames": ["base64_frame1", "base64_frame2", ...]}
    - Response: {"detections": [{"bbox": {"x_min": 10, "y_min": 20, "x_max": 100, "y_max": 200}, "anomaly_score": 0.85, "class_id": 1}]}
    
    **Note:** Only cameras with type='local' are supported. For YouTube cameras, use a different endpoint.
    """
    result = await process_video_for_anomalies(
        db=db,
        camera_id=request.camera_id,
        user_id=current_user.id,
        batch_size=request.batch_size,
        sliding_window=request.sliding_window
    )
    
    return VideoProcessResponse(**result)
