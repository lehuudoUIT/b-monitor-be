from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import os
import aiofiles
import asyncio
from datetime import datetime
from pathlib import Path
import time

from app.core.database import get_db
from app.core.dependencies import CurrentUser
from app.schemas.schemas import CameraCreate, CameraUpdate, CameraResponse, CameraListResponse
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


@router.get("/", response_model=CameraListResponse)
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
    user_id = current_user.id
    
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


@router.post("/upload-video", response_model=CameraResponse, status_code=status.HTTP_201_CREATED)
async def upload_video(
    name: str,
    current_user: CurrentUser,
    location: str = "",
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a video file and create a new local camera.
    
    This endpoint allows uploading video files for local cameras.
    The video will be saved to the server and a camera record will be created.
    
    **File Upload Limits:**
    - Max file size: 500MB (configurable via MAX_VIDEO_SIZE_MB)
    - Upload speed limit: 10MB/s (configurable via MAX_UPLOAD_SPEED_MB_PER_SEC)
    - Supported formats: .mp4, .avi, .mov, .mkv, .flv
    
    **Form Data:**
    - **name**: Camera name (required)
    - **location**: Camera location/address (optional)
    - **file**: Video file to upload (required)
    
    **Response:**
    - Returns the created camera object with:
      - **url**: Local file path where video is saved
      - **type**: Automatically set to "local"
      - **status**: Automatically set to "active"
    
    **Error Cases:**
    - 400: Invalid file type or file too large
    - 413: File size exceeds limit
    - 500: File upload or save error
    
    **Example:**
    ```bash
    curl -X POST "http://localhost:8000/cameras/upload-video" \
      -H "Authorization: Bearer YOUR_TOKEN" \
      -F "name=Front Gate Camera" \
      -F "location=Building A Entrance" \
      -F "file=@/path/to/video.mp4"
    ```
    """
    # Get configuration from environment
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads/videos")
    MAX_VIDEO_SIZE_MB = int(os.getenv("MAX_VIDEO_SIZE_MB", "500"))
    MAX_UPLOAD_SPEED_MB_PER_SEC = int(os.getenv("MAX_UPLOAD_SPEED_MB_PER_SEC", "10"))
    
    # Convert MB to bytes
    MAX_SIZE_BYTES = MAX_VIDEO_SIZE_MB * 1024 * 1024
    MAX_SPEED_BYTES_PER_SEC = MAX_UPLOAD_SPEED_MB_PER_SEC * 1024 * 1024
    CHUNK_SIZE = 1024 * 1024  # 1MB chunks
    
    # Validate file type
    allowed_extensions = [".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv", ".webm"]
    file_ext = os.path.splitext(file.filename)[1].lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # Create upload directory if it doesn't exist
    Path(UPLOAD_DIR).mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = f"{timestamp}_{current_user.id}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    
    try:
        # Upload file with size and speed limits
        total_size = 0
        start_time = time.time()
        
        async with aiofiles.open(file_path, "wb") as f:
            while chunk := await file.read(CHUNK_SIZE):
                chunk_size = len(chunk)
                total_size += chunk_size
                
                # Check file size limit
                if total_size > MAX_SIZE_BYTES:
                    # Delete partial file
                    await f.close()
                    os.remove(file_path)
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File size exceeds limit of {MAX_VIDEO_SIZE_MB}MB"
                    )
                
                # Write chunk
                await f.write(chunk)
                
                # Apply speed limit
                elapsed = time.time() - start_time
                expected_time = total_size / MAX_SPEED_BYTES_PER_SEC
                if elapsed < expected_time:
                    await asyncio.sleep(expected_time - elapsed)
        
        # Create camera record
        camera_data = CameraCreate(
            name=name,
            location=location,
            thumbnail="",
            status="active",
            url=file_path,
            type="local",
            user_id=current_user.id
        )
        
        camera = await camera_service.create_camera(db, camera_data)
        
        return camera
        
    except HTTPException:
        raise
    except Exception as e:
        # Clean up file if camera creation fails
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload video: {str(e)}"
        )
