import requests
import base64
import io
import random
import time
from PIL import Image, ImageDraw
from concurrent.futures import ThreadPoolExecutor, as_completed

def generate_random_frame(width=640, height=480):
    """Generate a random image frame and encode it to base64."""
    # Create a random image with some shapes
    img = Image.new('RGB', (width, height), color=(random.randint(0, 255), random.randint(0, 255), random.randint(0, 255)))
    draw = ImageDraw.Draw(img)
    
    # Add some random shapes to make it look like a frame
    for _ in range(5):
        x1, y1 = random.randint(0, width), random.randint(0, height)
        x2, y2 = random.randint(0, width), random.randint(0, height)
        color = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
        draw.rectangle([x1, y1, x2 + x1, y2 + y1], outline=color, width=2)
    
    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG')
    img_bytes = buffer.getvalue()
    base64_str = base64.b64encode(img_bytes).decode('utf-8')
    
    return base64_str

def test_inference_api():
    """Test the /inference API endpoint with 7 random frames."""
    # API endpoint
    url = "http://localhost:8000/anomalies/inference"
    
    # Test with different resolutions
    resolutions = [
        (320, 240, "QVGA - Low Resolution"),
        (640, 480, "VGA - Standard Resolution"),
        (1280, 720, "HD - High Resolution"),
        (1920, 1080, "Full HD - Very High Resolution")
    ]
    
    results = []
    
    for width, height, description in resolutions:
        print("\n" + "=" * 60)
        print(f"Testing with {description} ({width}x{height})")
        print("=" * 60)
        
        # Generate 7 random base64 encoded frames
        print(f"Generating 7 frames at {width}x{height}...")
        frame_list = []
        generation_start = time.time()
        
        for i in range(7):
            frame = generate_random_frame(width, height)
            frame_list.append(frame)
            print(f"  Frame {i+1} generated (size: {len(frame):,} chars)")
        
        generation_time = time.time() - generation_start
        print(f"\n⏱️  Frame generation time: {generation_time:.2f} seconds")
        
        # Calculate total payload size
        total_size = sum(len(frame) for frame in frame_list)
        print(f"📦 Total payload size: {total_size:,} chars (~{total_size/1024:.2f} KB)")
        
        # Send POST request
        print("\nSending request to API...")
        request_start = time.time()
        
        try:
            # Send the list directly, not wrapped in an object
            response = requests.post(url, json=frame_list, timeout=60)
            request_time = time.time() - request_start
            
            # Check response
            if response.status_code == 200:
                print(f"\n✅ Success! Status code: {response.status_code}")
                print(f"⏱️  API response time: {request_time:.2f} seconds")
                
                result = response.json()
                num_detections = len(result.get('detections', []))
                print(f"🔍 Number of detections: {num_detections}")
                
                # Display first 3 detections only
                for idx, detection in enumerate(result.get('detections', [])[:3], 1):
                    print(f"\n  Detection {idx}:")
                    print(f"    - Anomaly Score: {detection.get('anomaly_score', 'N/A')}")
                    print(f"    - Bounding Box: {detection.get('bounding_box', 'N/A')}")
                    print(f"    - Class ID: {detection.get('class_id', 'N/A')}")
                
                if num_detections > 3:
                    print(f"\n  ... and {num_detections - 3} more detections")
                
                # Store result for summary
                results.append({
                    'resolution': f"{width}x{height}",
                    'description': description,
                    'generation_time': generation_time,
                    'request_time': request_time,
                    'total_time': generation_time + request_time,
                    'payload_size_kb': total_size / 1024,
                    'detections': num_detections,
                    'success': True
                })
                
            else:
                print(f"\n❌ Error! Status code: {response.status_code}")
                print(f"Response: {response.text[:500]}")
                
                results.append({
                    'resolution': f"{width}x{height}",
                    'description': description,
                    'generation_time': generation_time,
                    'request_time': 0,
                    'total_time': generation_time,
                    'payload_size_kb': total_size / 1024,
                    'detections': 0,
                    'success': False,
                    'error': response.status_code
                })
                
        except requests.exceptions.ConnectionError:
            print("\n❌ Error: Cannot connect to API server. Make sure the server is running on http://localhost:8000")
            results.append({
                'resolution': f"{width}x{height}",
                'description': description,
                'generation_time': generation_time,
                'request_time': 0,
                'total_time': generation_time,
                'payload_size_kb': total_size / 1024,
                'detections': 0,
                'success': False,
                'error': 'Connection Error'
            })
            break  # Stop testing if server is not available
            
        except requests.exceptions.Timeout:
            print("\n❌ Error: Request timed out. AI server might be slow or not responding.")
            results.append({
                'resolution': f"{width}x{height}",
                'description': description,
                'generation_time': generation_time,
                'request_time': 0,
                'total_time': generation_time,
                'payload_size_kb': total_size / 1024,
                'detections': 0,
                'success': False,
                'error': 'Timeout'
            })
            
        except Exception as e:
            print(f"\n❌ Unexpected error: {str(e)}")
            results.append({
                'resolution': f"{width}x{height}",
                'description': description,
                'generation_time': generation_time,
                'request_time': 0,
                'total_time': generation_time,
                'payload_size_kb': total_size / 1024,
                'detections': 0,
                'success': False,
                'error': str(e)
            })
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 PERFORMANCE SUMMARY")
    print("=" * 60)
    
    if results:
        print(f"\n{'Resolution':<15} {'Payload':<12} {'Gen Time':<12} {'API Time':<12} {'Total':<12} {'Detections':<12} {'Status'}")
        print("-" * 95)
        
        for r in results:
            status = "✅ Success" if r['success'] else f"❌ {r.get('error', 'Failed')}"
            print(f"{r['resolution']:<15} {r['payload_size_kb']:>8.2f} KB  {r['generation_time']:>8.2f}s    {r['request_time']:>8.2f}s    {r['total_time']:>8.2f}s    {r['detections']:>6}       {status}")
        
        # Calculate averages for successful tests
        successful = [r for r in results if r['success']]
        if successful:
            avg_gen = sum(r['generation_time'] for r in successful) / len(successful)
            avg_api = sum(r['request_time'] for r in successful) / len(successful)
            avg_total = sum(r['total_time'] for r in successful) / len(successful)
            avg_detections = sum(r['detections'] for r in successful) / len(successful)
            
            print("\n" + "-" * 95)
            print(f"{'AVERAGE':<15} {'':>12} {avg_gen:>8.2f}s    {avg_api:>8.2f}s    {avg_total:>8.2f}s    {avg_detections:>6.1f}")
        
        # Find fastest and slowest
        if len(successful) > 1:
            fastest = min(successful, key=lambda x: x['request_time'])
            slowest = max(successful, key=lambda x: x['request_time'])
            
            print(f"\n🏆 Fastest: {fastest['resolution']} - {fastest['request_time']:.2f}s")
            print(f"🐌 Slowest: {slowest['resolution']} - {slowest['request_time']:.2f}s")
            print(f"📈 Performance difference: {((slowest['request_time'] / fastest['request_time']) - 1) * 100:.1f}% slower")


def send_single_request(url, frame_list, request_id):
    """Send a single inference request and return the result."""
    try:
        start_time = time.time()
        response = requests.post(url, json=frame_list, timeout=60)
        elapsed_time = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            num_detections = len(result.get('detections', []))
            return {
                'request_id': request_id,
                'success': True,
                'time': elapsed_time,
                'detections': num_detections,
                'status_code': 200
            }
        else:
            return {
                'request_id': request_id,
                'success': False,
                'time': elapsed_time,
                'detections': 0,
                'status_code': response.status_code,
                'error': f"HTTP {response.status_code}"
            }
    except Exception as e:
        elapsed_time = time.time() - start_time if 'start_time' in locals() else 0
        return {
            'request_id': request_id,
            'success': False,
            'time': elapsed_time,
            'detections': 0,
            'status_code': 0,
            'error': str(e)
        }


def test_concurrent_requests():
    """Test concurrent API requests to measure throughput and performance."""
    print("\n" + "=" * 60)
    print("🚀 CONCURRENT REQUESTS TEST")
    print("=" * 60)
    
    # API endpoint
    url = "http://localhost:8000/anomalies/inference"
    
    # Test configuration
    num_requests = 30
    resolution = (1280, 720)  # Standard VGA resolution
    
    print(f"\nPreparing to send {num_requests} concurrent requests...")
    print(f"Resolution: {resolution[0]}x{resolution[1]}")
    
    # Generate frames once and reuse for all requests
    print("\nGenerating 7 frames...")
    frame_generation_start = time.time()
    frame_list = [generate_random_frame(*resolution) for _ in range(7)]
    frame_generation_time = time.time() - frame_generation_start
    
    total_size = sum(len(frame) for frame in frame_list)
    print(f"✅ Frames generated in {frame_generation_time:.2f}s")
    print(f"📦 Payload size per request: {total_size/1024:.2f} KB")
    print(f"📦 Total data to send: {(total_size * num_requests)/1024:.2f} KB")
    
    # Send concurrent requests
    print(f"\n🚀 Sending {num_requests} requests concurrently...")
    overall_start = time.time()
    
    results = []
    with ThreadPoolExecutor(max_workers=num_requests) as executor:
        # Submit all requests
        futures = {
            executor.submit(send_single_request, url, frame_list, i+1): i+1 
            for i in range(num_requests)
        }
        
        # Collect results as they complete
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            status_icon = "✅" if result['success'] else "❌"
            print(f"  {status_icon} Request #{result['request_id']}: {result['time']:.2f}s - {result['detections']} detections")
    
    overall_time = time.time() - overall_start
    
    # Calculate statistics
    print("\n" + "=" * 60)
    print("📊 CONCURRENT TEST RESULTS")
    print("=" * 60)
    
    successful = [r for r in results if r['success']]
    failed = [r for r in results if not r['success']]
    
    print(f"\n✅ Successful requests: {len(successful)}/{num_requests}")
    print(f"❌ Failed requests: {len(failed)}/{num_requests}")
    
    if successful:
        times = [r['time'] for r in successful]
        detections = [r['detections'] for r in successful]
        
        print(f"\n⏱️  TIMING STATISTICS:")
        print(f"   Total wall time: {overall_time:.2f}s")
        print(f"   Average request time: {sum(times)/len(times):.2f}s")
        print(f"   Fastest request: {min(times):.2f}s")
        print(f"   Slowest request: {max(times):.2f}s")
        print(f"   Time range: {max(times) - min(times):.2f}s")
        
        print(f"\n🔍 DETECTION STATISTICS:")
        print(f"   Total detections: {sum(detections)}")
        print(f"   Average per request: {sum(detections)/len(detections):.1f}")
        print(f"   Min detections: {min(detections)}")
        print(f"   Max detections: {max(detections)}")
        
        print(f"\n📈 THROUGHPUT:")
        requests_per_second = len(successful) / overall_time
        print(f"   Requests per second: {requests_per_second:.2f}")
        print(f"   Data throughput: {(total_size * len(successful) / 1024 / overall_time):.2f} KB/s")
        
        # Calculate speedup from parallelization
        sequential_time = sum(times)
        speedup = sequential_time / overall_time
        print(f"\n🚀 PARALLELIZATION EFFICIENCY:")
        print(f"   Sequential time (estimated): {sequential_time:.2f}s")
        print(f"   Parallel time (actual): {overall_time:.2f}s")
        print(f"   Speedup: {speedup:.2f}x")
        print(f"   Efficiency: {(speedup/num_requests)*100:.1f}%")
    
    if failed:
        print(f"\n❌ FAILED REQUESTS:")
        for r in failed:
            print(f"   Request #{r['request_id']}: {r.get('error', 'Unknown error')}")
    
    return results


if __name__ == "__main__":
    print("=" * 60)
    print("Testing /anomalies/inference API endpoint")
    print("=" * 60)
    
    # Run sequential tests with different resolutions
    # test_inference_api()
    
    # Run concurrent test
    test_concurrent_requests()
    
    print("\n" + "=" * 60)
    print("All tests completed")
    print("=" * 60)
