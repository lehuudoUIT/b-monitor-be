from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_
from typing import Optional, List
from datetime import datetime, date
from fastapi import HTTPException, status
from app.core.ai_client import get_ai_client

from app.models.models import Anomaly, Camera, AnomalyLevel
from app.schemas.schemas import AnomalyCreate


async def create_anomaly(db: AsyncSession, anomaly_data: AnomalyCreate, user_id: int) -> Anomaly:
    """
    Create a new anomaly.
    Validates that the camera belongs to the user.
    """
    # Check if camera exists and belongs to user
    camera_result = await db.execute(
        select(Camera).filter(Camera.id == anomaly_data.cam_id)
    )
    camera = camera_result.scalar_one_or_none()
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera not found"
        )
    
    if camera.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to create anomaly for this camera"
        )
    
    # Create anomaly
    db_anomaly = Anomaly(
        time=anomaly_data.time or datetime.utcnow(),
        type=anomaly_data.type,
        description=anomaly_data.description,
        level=anomaly_data.level,
        cam_id=anomaly_data.cam_id
    )
    
    db.add(db_anomaly)
    await db.commit()
    await db.refresh(db_anomaly)
    return db_anomaly


async def get_anomaly_by_id(db: AsyncSession, anomaly_id: int) -> Optional[Anomaly]:
    """
    Get an anomaly by ID.
    """
    result = await db.execute(select(Anomaly).filter(Anomaly.id == anomaly_id))
    return result.scalar_one_or_none()


async def get_anomalies(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    order: str = "desc",
    field: str = "time",
    camera_id: Optional[int] = None,
    level: Optional[AnomalyLevel] = None,
    frame_id: Optional[int] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    user_id: Optional[int] = None
) -> tuple[List[Anomaly], int]:
    """
    Get list of anomalies with filtering and pagination.
    Returns tuple of (anomalies, total_count).
    """
    # Build query
    query = select(Anomaly)
    filters = []
    
    # Filter by camera_id
    if camera_id is not None:
        filters.append(Anomaly.cam_id == camera_id)
    
    # Filter by level
    if level is not None:
        filters.append(Anomaly.level == level)
    
    # Filter by date range
    if start_date:
        filters.append(Anomaly.time >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        filters.append(Anomaly.time <= datetime.combine(end_date, datetime.max.time()))
    
    # Filter by user's cameras only
    if user_id is not None:
        # Subquery to get camera IDs belonging to user
        camera_subquery = select(Camera.id).filter(Camera.user_id == user_id)
        filters.append(Anomaly.cam_id.in_(camera_subquery))

    if frame_id is not None:
        filters.append(Anomaly.frame_id == frame_id)
    
    # Apply filters
    if filters:
        query = query.filter(and_(*filters))
    
    # Get total count
    count_query = select(func.count()).select_from(Anomaly)
    if filters:
        count_query = count_query.filter(and_(*filters))
    
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    
    # Apply pagination and ordering
    if field == "frame_id":
        query = query.order_by(Anomaly.frame_id.asc() if order == "asc" else Anomaly.frame_id.desc())
    else:
        query = query.order_by(Anomaly.time.asc() if order == "asc" else Anomaly.time.desc())
    query = query.offset(skip).limit(limit)
    
    result = await db.execute(query)
    anomalies = result.scalars().all()
    
    return list(anomalies), total

async def get_anomalies_by_camera(
    db: AsyncSession,
    order: str = "asc",
    camera_id: Optional[int] = None,
    level: Optional[AnomalyLevel] = None,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    user_id: Optional[int] = None
) -> tuple[List[Anomaly], int]:
    """
    Get list of anomalies with filtering and pagination.
    Returns tuple of (anomalies, total_count).
    """
    # Build query
    query = select(Anomaly)
    filters = []
    
    # Filter by camera_id
    if camera_id is not None:
        filters.append(Anomaly.cam_id == camera_id)
    
    # Filter by level
    if level is not None:
        filters.append(Anomaly.level == level)
    
    # Filter by date range
    if start_date:
        filters.append(Anomaly.time >= datetime.combine(start_date, datetime.min.time()))
    if end_date:
        filters.append(Anomaly.time <= datetime.combine(end_date, datetime.max.time()))
    
    # Filter by user's cameras only
    if user_id is not None:
        # Subquery to get camera IDs belonging to user
        camera_subquery = select(Camera.id).filter(Camera.user_id == user_id)
        filters.append(Anomaly.cam_id.in_(camera_subquery))
    
    # Apply filters
    if filters:
        query = query.filter(and_(*filters))
    
    # Get total count
    count_query = select(func.count()).select_from(Anomaly)
    if filters:
        count_query = count_query.filter(and_(*filters))
    
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    
    # Apply pagination and ordering
    query = query.order_by(Anomaly.frame_id.desc() if order == "desc" else Anomaly.frame_id.asc())
    
    result = await db.execute(query)
    anomalies = result.scalars().all()
    
    return list(anomalies), total


async def verify_anomaly_access(db: AsyncSession, anomaly_id: int, user_id: int) -> Anomaly:
    """
    Verify that the user has access to the anomaly (through camera ownership).
    """
    # Get anomaly with camera
    result = await db.execute(
        select(Anomaly)
        .join(Camera)
        .filter(Anomaly.id == anomaly_id)
    )
    anomaly = result.scalar_one_or_none()
    
    if not anomaly:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Anomaly not found"
        )
    
    # Get camera to check ownership
    camera_result = await db.execute(
        select(Camera).filter(Camera.id == anomaly.cam_id)
    )
    camera = camera_result.scalar_one_or_none()
    
    if not camera or camera.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this anomaly"
        )
    
    return anomaly


async def inference_anomaly(frame_list: List[str]) -> List[dict]:
    """
    Create an anomaly detected by inference system.
    """
    ai_client = get_ai_client()
    # Check health of AI server
    if not await ai_client.check_health():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI server is not available"
        )
    results = await ai_client.send_batch(frames_base64=frame_list, batch_index=None)
    if not results.get("success", False):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AI server failed to process frames"
        )

    anomaly_threshold = 0.5  # Configurable threshold for saving anomalies
    list_detections = []
    detections = results.get("detections", [])
    for detection in detections:
        anomaly_score = detection.get("anomaly_score_normalized", 0.0)
        
        # Only save if anomaly score is above threshold
        if anomaly_score >= anomaly_threshold:
            bbox = detection.get("bbox", {})
            bbox_str = f"{bbox.get('x_min', 0)},{bbox.get('y_min', 0)},{bbox.get('x_max', 0)},{bbox.get('y_max', 0)}"
        list_detections.append({
            "anomaly_score": anomaly_score,
            "bounding_box": bbox_str,
            "class_id": detection.get("class_id", 0)
        })
    
    return list_detections