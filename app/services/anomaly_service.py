from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_
from typing import Optional, List
from datetime import datetime, date
from fastapi import HTTPException, status

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
