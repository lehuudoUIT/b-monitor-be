from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from typing import Optional, List
from fastapi import HTTPException, status

from app.models.models import Camera
from app.schemas.schemas import CameraCreate, CameraUpdate


async def create_camera(db: AsyncSession, camera_data: CameraCreate) -> Camera:
    """
    Create a new camera.
    """
    db_camera = Camera(
        name=camera_data.name,
        location=camera_data.location,
        thumbnail=camera_data.thumbnail,
        status=camera_data.status,
        url=camera_data.url,
        type=camera_data.type,
        user_id=camera_data.user_id,
        fps=camera_data.fps,
        resolution=camera_data.resolution
    )
    
    db.add(db_camera)
    await db.commit()
    await db.refresh(db_camera)
    return db_camera


async def get_camera_by_id(db: AsyncSession, camera_id: int) -> Optional[Camera]:
    """
    Get a camera by ID.
    """
    result = await db.execute(select(Camera).filter(Camera.id == camera_id))
    return result.scalar_one_or_none()


async def get_cameras(
    db: AsyncSession, 
    skip: int = 0, 
    limit: int = 10,
    user_id: Optional[int] = None,
    camera_type: Optional[str] = None
) -> tuple[List[Camera], int]:
    """
    Get list of cameras with pagination.
    Returns tuple of (cameras, total_count).
    """
    # Build query
    query = select(Camera)
    
    # Filter by user_id if provided
    if user_id is not None:
        query = query.filter(Camera.user_id == user_id)
    
    # Get total count
    count_query = select(func.count()).select_from(Camera)
    if user_id is not None:
        count_query = count_query.filter(Camera.user_id == user_id)
    
    if camera_type is not None:
        query = query.filter(Camera.type == camera_type)
        count_query = count_query.filter(Camera.type == camera_type)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()
    
    # Apply pagination
    query = query.offset(skip).limit(limit).order_by(Camera.created_at.desc())
    
    result = await db.execute(query)
    cameras = result.scalars().all()
    
    return list(cameras), total


async def update_camera(
    db: AsyncSession,
    camera_id: int,
    camera_data: CameraUpdate,
    user_id: int
) -> Camera:
    """
    Update a camera. Only the owner can update.
    """
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
            detail="Not authorized to update this camera"
        )
    
    # Update fields
    update_data = camera_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(camera, field, value)
    
    await db.commit()
    await db.refresh(camera)
    return camera


async def delete_camera(db: AsyncSession, camera_id: int, user_id: int) -> bool:
    """
    Delete a camera. Only the owner can delete.
    """
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
            detail="Not authorized to delete this camera"
        )
    
    if camera.type == "local":
        # Optionally, delete local video file from storage
        import os
        try:
            if os.path.exists(camera.url):
                os.remove(camera.url)
        except Exception as e:
            print(f"Error deleting video file: {e}")
    
    await db.delete(camera)
    await db.commit()
    return True
