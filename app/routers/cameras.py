import cv2
from fastapi import APIRouter, Depends, Form, HTTPException, status, Query, UploadFile, File, Request
from fastapi.responses import StreamingResponse
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
from app.schemas.schemas import CameraUpdate, CameraResponse, CameraListResponse, CameraCreate, StopStreamRequest
from app.services import camera_service
from app.services.video_processing_service import process_video_for_anomalies

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
    camera_type: Optional[str] = Query(None, description="Filter by camera type (local/youtube)"),
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
    
    cameras, total = await camera_service.get_cameras(db, skip, limit, user_id, camera_type)
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
    current_user: CurrentUser,
    name: str = Form(...),
    location: str = Form(""),
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
        
        
        video_fps = 30
        video_resolution = "1920,1080"
        # Use cv2 to extract metadata 
        try:
            cap = cv2.VideoCapture(file_path)
            if cap.isOpened():
                fps = cap.get(cv2.CAP_PROP_FPS)
                if fps > 0:
                    video_fps = int(round(fps)) 
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                if width > 0 and height > 0:
                    video_resolution = f"{width},{height}"
                cap.release()
            else:
                print(f"Warning: Could not open video file {file_path} to read metadata.")
        except Exception as e:
            print(f"Error reading video metadata: {e}")
        



        # Create camera record
        camera_data = CameraCreate(
            name=name,
            location=location,
            thumbnail="",
            status="inactive",
            url=file_path,
            type="local",
            fps=video_fps,
            resolution=video_resolution,
            user_id=current_user.id
        )
        
        camera = await camera_service.create_camera(db, camera_data)
        
        # Start video processing in background (không đợi kết quả)
        from app.services.video_processing_service import process_video_background
        video_width, video_height = map(int, video_resolution.split(","))
        resolution_area = video_width * video_height
        sliding_window = 1
        if resolution_area <= 300000:
            sliding_window = 1
        elif resolution_area > 300000 and resolution_area <= 1000000:
            sliding_window = 3
        elif resolution_area > 1000000 and resolution_area <= 4000000:
            sliding_window = 5
        else:
            sliding_window = 7

        asyncio.create_task(process_video_background(
            camera_id=camera.id,
            user_id=current_user.id,
            batch_size=7,
            sliding_window=sliding_window
        ))

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


@router.get("/{camera_id}/stream")
async def stream_video(
    camera_id: int,
    request: Request,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db)
):
    """
    Stream video file from a local camera with Range request support.
    
    This endpoint streams video files for cameras with type='local'.
    Supports HTTP Range requests to enable video seeking/scrubbing in browsers.
    
    **Features:**
    - Streaming video playback
    - Byte-range request support (seek/scrub)
    - Proper Content-Type headers
    - Resume capability
    
    **Path Parameters:**
    - **camera_id**: ID of the camera (must be type='local')
    
    **Headers:**
    - **Range**: Optional byte range (e.g., "bytes=0-1023")
    
    **Response:**
    - 200: Full video content
    - 206: Partial content (when Range header is provided)
    - 404: Camera or video file not found
    - 403: Not authorized to access this camera
    - 400: Camera type is not 'local'
    
    **Example:**
    ```html
    <video controls>
        <source src="http://localhost:8000/cameras/1/stream" type="video/mp4">
    </video>
    ```
    
    **Browser Usage:**
    - Video player will automatically send Range requests
    - Enables seeking to any position in the video
    - Reduces initial loading time
    """
    # Get camera and validate
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
    
    # Check camera type
    if camera.type.value != "local":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only cameras with type='local' support video streaming"
        )
    
    # Get video file path
    video_path = camera.url
    
    if not os.path.exists(video_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Video file not found"
        )
    
    # Get file size
    file_size = os.path.getsize(video_path)
    
    # Parse Range header
    range_header = request.headers.get("range")
    
    # Determine content type from file extension
    ext = os.path.splitext(video_path)[1].lower()
    content_type_map = {
        ".mp4": "video/mp4",
        ".avi": "video/x-msvideo",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
        ".flv": "video/x-flv",
        ".wmv": "video/x-ms-wmv",
        ".webm": "video/webm"
    }
    content_type = content_type_map.get(ext, "video/mp4")
    
    if range_header:
        # Parse Range header (format: "bytes=start-end")
        range_match = range_header.replace("bytes=", "").split("-")
        start = int(range_match[0]) if range_match[0] else 0
        end = int(range_match[1]) if range_match[1] else file_size - 1
        end = min(end, file_size - 1)
        
        # Validate range
        if start >= file_size or start > end:
            raise HTTPException(
                status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
                detail="Invalid range"
            )
        
        chunk_size = end - start + 1
        
        # Generator to read file chunk
        async def file_iterator():
            async with aiofiles.open(video_path, mode="rb") as f:
                await f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    read_size = min(8192, remaining)  # 8KB chunks
                    data = await f.read(read_size)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data
        
        # Return partial content (206)
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
            "Content-Type": content_type,
        }
        
        return StreamingResponse(
            file_iterator(),
            status_code=206,
            headers=headers,
            media_type=content_type
        )
    
    else:
        # No range header - stream entire file
        async def file_iterator():
            async with aiofiles.open(video_path, mode="rb") as f:
                while chunk := await f.read(8192):  # 8KB chunks
                    yield chunk
        
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Type": content_type,
        }
        
        return StreamingResponse(
            file_iterator(),
            status_code=200,
            headers=headers,
            media_type=content_type
        )


@router.get("/{camera_id}/stream-youtube")
async def stream_youtube_camera(
    camera_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db),
    session_id: Optional[str] = Query(None, description="Session ID for tracking and stopping stream"),
    batch_size: int = Query(7, ge=5, le=15, description="Number of frames per inference batch"),
    skip_frames: int = Query(5, ge=1, le=30, description="Number of frames to skip between inferences"),
    fps: int = Query(30, ge=15, le=60, description="Target FPS for output stream"),
    width: int = Query(1280, ge=640, le=1920, description="Target frame width"),
    height: int = Query(720, ge=480, le=1080, description="Target frame height"),
):
    """
    Stream YouTube livestream with real-time anomaly detection.
    
    This endpoint streams from YouTube livestream cameras (type='youtube') and performs
    real-time anomaly detection using AI inference. Detected anomalies are drawn on frames
    with bounding boxes, class names, and anomaly scores.
    
    **Features:**
    - Real-time YouTube livestream processing
    - Sliding window anomaly detection (7 frames per batch)
    - Frame skipping to prevent GPU overload
    - Automatic reconnection on stream interruption
    - Color-coded bounding boxes by anomaly severity
    - 5-7 second delay for smooth inference processing
    
    **Path Parameters:**
    - **camera_id**: ID of the camera (must be type='youtube')
    
    **Query Parameters:**
    - **batch_size**: Number of frames per inference batch (5-15, default: 7)
    - **skip_frames**: Frames to skip between inferences (1-30, default: 5)
    - **fps**: Target output FPS (15-60, default: 30)
    - **width**: Target frame width (640-1920, default: 1280)
    - **height**: Target frame height (480-1080, default: 720)
    
    **Inference Method:**
    - Uses sliding window with configurable skip
    - Example (skip_frames=5):
      - Batch 1: frames 1-7 → inference for frame 4
      - Batch 2: frames 6-12 → inference for frame 9
      - Batch 3: frames 11-17 → inference for frame 14
    
    **Bounding Box Colors:**
    - 🔴 Red: Critical (score ≥ 0.8)
    - 🟠 Orange: High (score ≥ 0.6)
    - 🟡 Yellow: Medium (score ≥ 0.4)
    - 🟢 Green: Low (score < 0.4)
    
    **Response:**
    - Content-Type: multipart/x-mixed-replace; boundary=frame
    - Continuous MJPEG stream with detection overlays
    - 200: Stream started successfully
    - 404: Camera not found
    - 403: Not authorized
    - 400: Invalid camera type (must be 'youtube')
    - 503: AI server unavailable
    
    **Example:**
    ```html
    <img src="http://localhost:8000/cameras/1/stream-youtube?skip_frames=5&fps=30" />
    ```
    
    **Browser Usage:**
    - Use <img> tag or video.js for MJPEG playback
    - Stream includes real-time anomaly detection overlays
    - Automatic reconnection on connection loss
    
    **Performance Notes:**
    - Default delay: 5-7 seconds behind live stream
    - Adjust skip_frames to balance detection frequency vs. GPU load
    - Higher skip_frames = lower GPU usage, less frequent detection
    - Lower skip_frames = higher GPU usage, more frequent detection
    """
    from app.services.youtube_stream_service import stream_youtube_with_anomaly_detection
    
    # Get camera and validate
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
    
    # Check camera type
    if camera.type.value != "youtube":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only cameras with type='youtube' support YouTube streaming with detection"
        )
    
    # Get YouTube URL
    youtube_url = camera.url
    
    # Start streaming with anomaly detection
    return StreamingResponse(
        stream_youtube_with_anomaly_detection(
            youtube_url=youtube_url,
            session_id=session_id,
            batch_size=batch_size,
            skip_frames=skip_frames,
            target_fps=fps,
            target_width=width,
            target_height=height
        ),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@router.post("/{camera_id}/stop-stream")
async def stop_youtube_stream(
    camera_id: int,
    request_data: StopStreamRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db)
):
    """
    Stop an active YouTube stream session.
    
    This endpoint stops a running YouTube stream by session ID.
    The stream and AI inference will be stopped gracefully.
    
    **Path Parameters:**
    - **camera_id**: ID of the camera
    
    **Request Body:**
    - **session_id**: Session ID of the stream to stop (required)
    
    **Response:**
    - 200: Stream stopped successfully
    - 404: Camera not found or session not found
    - 403: Not authorized to access this camera
    
    **Example:**
    ```bash
    curl -X POST "http://localhost:8000/cameras/1/stop-stream" \\
      -H "Authorization: Bearer YOUR_TOKEN" \\
      -H "Content-Type: application/json" \\
      -d '{"session_id": "abc123"}'
    ```
    """
    from app.services.youtube_stream_service import stop_stream_session
    
    # Get camera and validate
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
    
    # Stop the stream session
    success = stop_stream_session(request_data.session_id)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stream session '{request_data.session_id}' not found or already stopped"
        )
    
    return {
        "message": "Stream stopped successfully",
        "session_id": request_data.session_id,
        "camera_id": camera_id
    }
