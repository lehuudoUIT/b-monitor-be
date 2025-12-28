"""
Test YouTube stream API with anomaly detection.
This script tests the /cameras/{camera_id}/stream-youtube endpoint.
"""

import cv2
import numpy as np
import requests
import sys
import os
from pathlib import Path

# Add parent directory to path to import from app
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_stream_youtube(
    camera_id: int,
    token: str,
    base_url: str = "http://localhost:8000",
    batch_size: int = 7,
    skip_frames: int = 5,
    fps: int = 30,
    width: int = 1280,
    height: int = 720
):
    """
    Test YouTube stream with anomaly detection.
    
    Args:
        camera_id: ID of the YouTube camera to stream
        token: JWT authentication token
        base_url: Base URL of the API server
        batch_size: Number of frames per inference batch
        skip_frames: Number of frames to skip between inferences
        fps: Target FPS
        width: Target frame width
        height: Target frame height
    """
    # Construct URL
    url = f"{base_url}/cameras/{camera_id}/stream-youtube"
    params = {
        "batch_size": batch_size,
        "skip_frames": skip_frames,
        "fps": fps,
        "width": width,
        "height": height
    }
    
    # Headers
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    print(f"🎥 Starting stream test for camera {camera_id}...")
    print(f"📡 URL: {url}")
    print(f"⚙️  Parameters: {params}")
    print(f"🔑 Using authentication token")
    print(f"\n⏳ Connecting to stream... (this may take a few seconds)")
    
    try:
        # Send request with stream=True
        response = requests.get(
            url,
            params=params,
            headers=headers,
            stream=True,
            timeout=90
        )
        
        # Check response status
        if response.status_code != 200:
            print(f"❌ Error: HTTP {response.status_code}")
            print(f"Response: {response.text}")
            return
        
        print(f"✅ Connected successfully!")
        print(f"📺 Content-Type: {response.headers.get('content-type')}")
        print(f"\n🎬 Displaying stream... (Press 'q' to quit, 's' to save screenshot)")
        
        # Create window
        window_name = f"YouTube Stream - Camera {camera_id}"
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_name, width, height)
        
        # Read MJPEG stream
        byte_buffer = bytes()
        frame_count = 0
        
        for chunk in response.iter_content(chunk_size=1024):
            if not chunk:
                continue
            
            byte_buffer += chunk
            
            # Look for JPEG boundaries
            a = byte_buffer.find(b'\xff\xd8')  # JPEG start
            b = byte_buffer.find(b'\xff\xd9')  # JPEG end
            
            if a != -1 and b != -1:
                # Extract JPEG image
                jpg = byte_buffer[a:b+2]
                byte_buffer = byte_buffer[b+2:]
                
                # Decode image
                img = cv2.imdecode(
                    np.frombuffer(jpg, dtype=np.uint8),
                    cv2.IMREAD_COLOR
                )
                
                if img is not None:
                    frame_count += 1
                    
                    # Add frame counter
                    cv2.putText(
                        img,
                        f"Frame: {frame_count}",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1,
                        (255, 255, 255),
                        2
                    )
                    
                    # Display frame
                    cv2.imshow(window_name, img)
                    
                    # Handle key press
                    key = cv2.waitKey(1) & 0xFF
                    
                    if key == ord('q'):
                        print(f"\n👋 Stopping stream... (Received {frame_count} frames)")
                        break
                    elif key == ord('s'):
                        # Save screenshot
                        screenshot_path = f"screenshot_frame_{frame_count}.jpg"
                        cv2.imwrite(screenshot_path, img)
                        print(f"📸 Screenshot saved: {screenshot_path}")
        
        # Cleanup
        cv2.destroyAllWindows()
        print(f"✅ Stream test completed!")
        print(f"📊 Total frames received: {frame_count}")
        
    except requests.exceptions.Timeout:
        print("❌ Error: Connection timeout")
    except requests.exceptions.ConnectionError:
        print("❌ Error: Could not connect to server")
    except KeyboardInterrupt:
        print(f"\n👋 Interrupted by user")
        cv2.destroyAllWindows()
    except Exception as e:
        print(f"❌ Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()




if __name__ == "__main__":
    # Configuration
    BASE_URL = "http://localhost:8000"
    
    # ============================================
    # CONFIGURATION - Modify these values
    # ============================================
    
    # Option 1: Use existing token
    TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzdHJpbmciLCJleHAiOjE3NjY4MjU0MTV9.smIpeZ8PTZb7VPfqGFqeOnoaVAkl4nhAJXjkEBG8tD4"  # Set your token here or leave None to login
    
    
    # Camera settings
    CAMERA_ID = 11  # Change to your YouTube camera ID
    
    # Stream parameters
    BATCH_SIZE = 7  # Number of frames per inference batch
    SKIP_FRAMES = 6  # Frames to skip between inferences
    FPS = 18  # Target FPS
    WIDTH = 854  # Frame width
    HEIGHT = 480  # Frame height
    
    # ============================================
    
    print("=" * 60)
    print("🎥 YouTube Stream API Test")
    print("=" * 60)
    
    print()
    
    # Test stream
    test_stream_youtube(
        camera_id=CAMERA_ID,
        token=TOKEN,
        base_url=BASE_URL,
        batch_size=BATCH_SIZE,
        skip_frames=SKIP_FRAMES,
        fps=FPS,
        width=WIDTH,
        height=HEIGHT
    )
