from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.schemas.schemas import CameraCreate, CameraUpdate, CameraResponse
from app.services import camera_service

router = APIRouter()


@router.post("/", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def create_camera(
    camera_data: CameraCreate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new camera.
    
    The camera will be assigned to the authenticated user automatically.
    
    - **name**: Camera name (required)
    - **location**: Camera location/address
    - **thumbnail**: Path to thumbnail image
    - **status**: Camera status (active/inactive)
    - **url**: Camera stream URL (required)
    - **type**: Camera type (local or youtube)
    """
    # Override user_id with current user's id
    camera_data.user_id = current_user.id
    
    camera = await camera_service.create_camera(db, camera_data)
    return camera


@router.get("/", response_model=dict)
async def list_cameras(
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(10, ge=1, le=100, description="Number of records to return"),
    all: bool = Query(False, description="Get all cameras (admin only) or only user's cameras")
):
    """
    List cameras with pagination.
    
    Returns cameras belonging to the authenticated user.
    
    - **skip**: Number of records to skip (for pagination)
    - **limit**: Maximum number of records to return (max 100)
    - **all**: If True, returns all cameras (requires admin privileges - not implemented yet)
    
    Returns:
    - **items**: List of cameras
    - **total**: Total number of cameras
    - **skip**: Current skip value
    - **limit**: Current limit value
    """
    # For now, only return user's own cameras
    # In future, check if user is admin when all=True
    user_id = current_user.id if not all else None
    
    cameras, total = await camera_service.get_cameras(db, skip, limit, user_id)
    
    return {
        "items": cameras,
        "total": total,
        "skip": skip,
        "limit": limit
    }


@router.get("/{camera_id}", response_model=CameraResponse)
async def get_camera(
    camera_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific camera by ID.
    
    Only returns cameras belonging to the authenticated user.
    """
    camera = await camera_service.get_camera_by_id(db, camera_id)
    
    if not camera:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Camera not found"
        )
    
    # Check ownership
    if camera.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this camera"
        )
    
    return camera


@router.put("/{camera_id}", response_model=CameraResponse)
async def update_camera(
    camera_id: int,
    camera_data: CameraUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db)
):
    """
    Update a camera.
    
    Only the camera owner can update it.
    
    All fields are optional - only provided fields will be updated.
    """
    camera = await camera_service.update_camera(db, camera_id, camera_data, current_user.id)
    return camera


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(
    camera_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a camera.
    
    Only the camera owner can delete it.
    This will also delete all associated anomalies and normal features (cascade delete).
    """
    await camera_service.delete_camera(db, camera_id, current_user.id)
    return None
