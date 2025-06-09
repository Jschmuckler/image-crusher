#!/usr/bin/env python
"""
RunBulk.py - Process a folder in the bucket and create processed versions of files.
Uses Docker containers to process files in parallel.
"""

import os
import sys
import argparse
import tempfile
import concurrent.futures
import subprocess
import time
import uuid
import signal
import shlex
import datetime
import requests  # For direct HTTP requests to containers
from google.cloud import storage
from src.CompressionUtils import CompressionUtils
from src.FileProcessor import FileProcessor
from src.constants import TYPE_UNKNOWN, TYPE_IMAGE, TYPE_VIDEO

# Default number of Docker containers for parallel processing
DEFAULT_CONTAINERS = 4

def get_credentials_from_gcloud():
    """Get credentials for the active gcloud account"""
    try:
        # Run gcloud command to get access token for the configured account
        import subprocess
        result = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True,
            text=True,
            check=True
        )
        token = result.stdout.strip()
        
        # Create credentials from the token
        from google.oauth2.credentials import Credentials
        return Credentials(token)
    except Exception as e:
        print(f"Note: Using default authentication method - {e}")
        return None

def setup_storage_client():
    """Set up and return a storage client with the appropriate credentials"""
    # Get environment variables
    project_id = os.environ.get('PROJECT_ID')
    bucket_name = os.environ.get('BUCKET_NAME')
    
    if not project_id or not bucket_name:
        print("ERROR: PROJECT_ID and BUCKET_NAME environment variables must be set")
        print("Use: export PROJECT_ID='your-project' export BUCKET_NAME='your-bucket'")
        sys.exit(1)
    
    # Try to get credentials from gcloud, otherwise use default
    credentials = get_credentials_from_gcloud()
    if credentials:
        storage_client = storage.Client(project=project_id, credentials=credentials)
        print(f"Using explicit credentials from gcloud")
    else:
        storage_client = storage.Client(project=project_id)
        print(f"Using default credentials")
    
    return storage_client, bucket_name

def list_files_in_folder(storage_client, bucket_name, folder_path=None, recursive=True):
    """List all files in the folder, optionally recursively.
    
    Args:
        storage_client: The storage client
        bucket_name: Name of the bucket
        folder_path: Path to the folder (e.g., "2024/Photos")
        recursive: Whether to include subfolders
    
    Returns:
        List of blob objects
    """
    bucket = storage_client.bucket(bucket_name)
    
    # Ensure the folder path ends with a slash if it's not empty
    if folder_path and not folder_path.endswith('/') and recursive:
        folder_path = f"{folder_path}/"
    
    blobs = []
    
    # Use delimiter if not recursive
    if not recursive and folder_path:
        for blob in bucket.list_blobs(prefix=folder_path, delimiter='/'):
            # Only process actual files, not directory markers
            if not blob.name.endswith('/'):
                blobs.append(blob)
        return blobs
    
    # For recursive listing with prefix
    for blob in bucket.list_blobs(prefix=folder_path):
        # Skip THUMBS and COMPRESSED directories
        if ("/THUMBS/" in blob.name or blob.name.endswith("/THUMBS") or
            "/COMPRESSED/" in blob.name or blob.name.endswith("/COMPRESSED")):
            continue
        blobs.append(blob)
    
    return blobs

def should_process_file(blob):
    """Check if a file should be processed.
    
    Args:
        blob: The storage blob
    
    Returns:
        True if the file should be processed, False otherwise
    """
    # Skip files in THUMBS or COMPRESSED directories (case insensitive)
    if ("/THUMBS/" in blob.name or "/thumbs/" in blob.name or 
        "/COMPRESSED/" in blob.name or "/compressed/" in blob.name):
        return False
    
    # Check if the file type is supported
    file_type = FileProcessor.get_file_type(content_type=blob.content_type, file_name=blob.name)
    if file_type == TYPE_UNKNOWN:
        return False
    
    return True

def get_thumb_path(blob_path):
    """Generate the output path for a processed file.
    
    Args:
        blob_path: The path to the original blob
    
    Returns:
        The path where the processed file should be stored
    """
    # Get the base directory and filename
    directory = os.path.dirname(blob_path)
    basename = os.path.basename(blob_path)
    name_without_ext = os.path.splitext(basename)[0]
    
    # All processed files are WebP images
    return os.path.join(directory, "THUMBS", f"{name_without_ext}.webp")

def get_compressed_path(blob_path, video_format='ts'):
    """Generate the output path for a compressed video file.
    
    Args:
        blob_path: The path to the original blob
        video_format: The video format (webm or ts)
    
    Returns:
        The path where the compressed video should be stored
    """
    # Get the base directory and filename
    directory = os.path.dirname(blob_path)
    basename = os.path.basename(blob_path)
    name_without_ext = os.path.splitext(basename)[0]
    
    # Return path with appropriate extension
    return os.path.join(directory, "COMPRESSED", f"{name_without_ext}.{video_format}")

def processed_file_exists(storage_client, bucket_name, original_path, video_format='ts'):
    """Check if a processed file exists for the original file.
    
    Args:
        storage_client: The storage client
        bucket_name: Name of the bucket
        original_path: Path to the original file
        video_format: Video output format (webm or ts)
    
    Returns:
        True if the processed file exists, False otherwise
    """
    bucket = storage_client.bucket(bucket_name)
    
    # Check if this is a video file
    file_type = FileProcessor.get_file_type(file_name=original_path)
    
    if file_type == TYPE_VIDEO:
        # For videos, check if compressed video file exists
        compressed_path = get_compressed_path(original_path, video_format)
        compressed_blob = bucket.blob(compressed_path)
        
        # Always check for thumbnail too
        thumb_path = get_thumb_path(original_path)
        thumb_blob = bucket.blob(thumb_path)
 
        

        # Check if files exist
        compressed_exists = compressed_blob.exists()
        thumb_exists = thumb_blob.exists()
        
        print(f"Checking {original_path}: Compressed file ({compressed_path}) exists: {compressed_exists}, Thumbnail ({thumb_path}) exists: {thumb_exists}")
        
        # Both thumbnail and compressed file must exist
        return compressed_exists and thumb_exists
    else:
        # For images, just check for thumbnail
        output_path = get_thumb_path(original_path)
        output_blob = bucket.blob(output_path)
        return output_blob.exists()

def process_single_file(container, blob_name, content_type=None, height=None, video_format=None):
    """Process a single file using a Docker container by sending a direct HTTP request.
    
    Args:
        container: Container info dictionary with name and port
        blob_name: Name of the blob to process
        content_type: Content type of the blob (optional)
        height: Output height (optional)
        video_format: Video output format (webm or ts)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        container_name = container["name"]
        port = container["port"]
        
        # Create the CloudEvent formatted request
        event = {
            "specversion": "1.0",
            "id": str(uuid.uuid4()),
            "source": "//storage.googleapis.com",
            "type": "google.cloud.storage.object.v1.finalized",
            "time": datetime.datetime.now().isoformat() + "Z",
            "datacontenttype": "application/json",
            "data": {
                "name": blob_name,
                "contentType": content_type or "application/octet-stream"
            }
        }
        
        # Add processing options if provided
        if height is not None or video_format is not None:
            event["data"]["options"] = {}
            
            if height is not None:
                event["data"]["options"]["height"] = height
                
            if video_format is not None:
                event["data"]["options"]["output_format"] = video_format
        
        # Set up the request headers
        headers = {"Content-Type": "application/cloudevents+json"}
        
        # Send the request directly to the container
        url = f"http://localhost:{port}"
        print(f"Processing {blob_name} on container {container_name} (port {port})...")
        start_time = time.time()
        
        response = requests.post(url, json=event, headers=headers)
        
        # Check result
        processing_time = time.time() - start_time
        if response.status_code == 200:
            print(f"✅ Successfully processed {blob_name} in {processing_time:.2f} seconds")
            
            # Log response if available
            if response.text:
                print(f"  Response: {response.text[:200]}...")
            return True
        else:
            print(f"❌ Error processing {blob_name} - Status code: {response.status_code}")
            print(f"  Error response: {response.text[:500]}...")
            return False
            
    except Exception as e:
        print(f"❌ Error processing {blob_name}: {str(e)}")
        return False

def setup_docker_containers(num_containers, reuse_existing=False):
    """Set up Docker containers for parallel processing.
    
    Args:
        num_containers: Number of containers to set up
        reuse_existing: Whether to reuse an existing container if available
        
    Returns:
        List of container info dictionaries with container_id and port
    """
    containers = []
    base_port = 8080
    
    # Check if a container is already running
    if reuse_existing:
        result = subprocess.run(
            ["docker", "ps", "--filter", "name=image-crusher-local", "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
            check=True
        )
        if "image-crusher-local" in result.stdout:
            print("Reusing existing container 'image-crusher-local'")
            containers.append({
                "name": "image-crusher-local",
                "port": base_port
            })
            # If we need more containers, we'll start at container 1
            if num_containers > 1:
                num_containers -= 1
                for i in range(1, num_containers + 1):
                    container_name = f"image-crusher-local-{i}"
                    port = base_port + i
                    setup_container(container_name, port)
                    containers.append({
                        "name": container_name,
                        "port": port
                    })
            return containers
    
    # No existing container to reuse, or we chose not to
    # Start the first container using deploy-local.sh
    print("Starting Docker container using deploy-local.sh...")
    subprocess.run(["bash", "deploy-local.sh"], check=True)
    containers.append({
        "name": "image-crusher-local",
        "port": base_port
    })
    
    # Start additional containers if needed
    if num_containers > 1:
        for i in range(1, num_containers):
            container_name = f"image-crusher-local-{i}"
            port = base_port + i
            setup_container(container_name, port)
            containers.append({
                "name": container_name,
                "port": port
            })
    
    # Wait a moment for containers to initialize
    time.sleep(3)
    return containers

def setup_container(container_name, port):
    """Set up an additional Docker container.
    
    Args:
        container_name: Name for the container
        port: Port to expose
    """
    # First, stop and remove any existing container with this name
    subprocess.run(["docker", "stop", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["docker", "rm", container_name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Get environment variables from the first container
    env_vars = subprocess.run(
        ["docker", "exec", "image-crusher-local", "env"],
        capture_output=True,
        text=True,
        check=True
    ).stdout.strip().split('\n')
    
    # Parse environment variables
    env_dict = {}
    for var in env_vars:
        if "=" in var:
            key, value = var.split("=", 1)
            if key in ["PROJECT_ID", "BUCKET_NAME", "GOOGLE_CLOUD_PROJECT"]:
                env_dict[key] = value
    
    # Make sure we include the critical GOOGLE_APPLICATION_CREDENTIALS env var
    env_dict["GOOGLE_APPLICATION_CREDENTIALS"] = "/tmp/sa-key.json"
    
    # Run the new container with fixed environment variables
    # This is more direct and less prone to error than extracting from the first container
    cmd = [
        "docker", "run", "--name", container_name,
        "-p", f"{port}:8080",
        "-e", f"PROJECT_ID={env_dict.get('PROJECT_ID', 'personal-life-451815')}",
        "-e", f"BUCKET_NAME={env_dict.get('BUCKET_NAME', 'schmucklemier-long-term')}",
        "-e", "PORT=8080",
        "-e", "GOOGLE_APPLICATION_CREDENTIALS=/tmp/sa-key.json",
        "-e", f"GOOGLE_CLOUD_PROJECT={env_dict.get('GOOGLE_CLOUD_PROJECT', env_dict.get('PROJECT_ID', 'personal-life-451815'))}",
        "-d", "image-crusher-local"
    ]
    
    print(f"Running command: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    
    print(f"Copying service account key to container {container_name}...")
    
    # Copy the service account key file directly from first container to the new one
    # This is a two-step process with a temporary file
    temp_key_path = f"/tmp/{container_name}-sa-key.json"
    
    try:
        # Step 1: Extract key from first container
        subprocess.run([
            "docker", "cp", "image-crusher-local:/tmp/sa-key.json", temp_key_path
        ], check=True)
        
        # Verify the key file exists and has content
        if not os.path.exists(temp_key_path) or os.path.getsize(temp_key_path) == 0:
            print(f"WARNING: Service account key file is empty or missing!")
            
        # Step 2: Copy key to new container
        subprocess.run([
            "docker", "cp", temp_key_path, f"{container_name}:/tmp/sa-key.json"
        ], check=True)
        
        # Step 3: Set correct permissions
        subprocess.run([
            "docker", "exec", container_name, "chmod", "600", "/tmp/sa-key.json"
        ], check=True)
        
        # Step 4: Verify key was properly copied
        result = subprocess.run(
            ["docker", "exec", container_name, "test", "-s", "/tmp/sa-key.json"],
            capture_output=True
        )
        
        if result.returncode != 0:
            print(f"WARNING: Service account key verification failed in container {container_name}")
        else:
            print(f"Service account key copied successfully to container {container_name}")
            
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_key_path):
            os.remove(temp_key_path)
    
    # Verify the container can access GCP
    print(f"Verifying container {container_name} has valid credentials...")
    try:
        # Test authentication and print debug info
        auth_script = """
import os
import sys
try:
    print(f"GOOGLE_APPLICATION_CREDENTIALS = {os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')}")
    
    # Check if the key file exists
    key_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS')
    if key_path:
        if os.path.exists(key_path):
            print(f"Key file exists at {key_path}")
            print(f"Key file size: {os.path.getsize(key_path)} bytes")
        else:
            print(f"Key file does NOT exist at {key_path}")
    
    # Try to initialize the storage client
    from google.cloud import storage
    client = storage.Client()
    print(f"Project: {client.project}")
    # Test listing buckets
    buckets = list(client.list_buckets(max_results=1))
    print(f"Authentication successful! Found {len(buckets)} buckets.")
    sys.exit(0)
except Exception as e:
    print(f"Authentication error: {str(e)}")
    sys.exit(1)
"""
        # Save auth script to a temporary file
        with tempfile.NamedTemporaryFile(suffix='.py', delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(auth_script.encode('utf-8'))
        
        # Copy the script to the container
        container_script_path = f"/tmp/auth_check_{uuid.uuid4().hex}.py"
        subprocess.run([
            "docker", "cp", tmp_path, f"{container_name}:{container_script_path}"
        ], check=True)
        
        # Run the script
        check_cmd = ["docker", "exec", container_name, "python", container_script_path]
        result = subprocess.run(check_cmd, capture_output=True, text=True)
        
        # Print output regardless of success/failure
        print(result.stdout)
        
        if result.returncode == 0:
            print(f"Container {container_name} authentication successful")
        else:
            print(f"WARNING: Container {container_name} authentication failed")
            print(result.stderr)
            # Don't fail - we'll let the actual processing detect and handle any auth issues
            
        # Clean up the script in the container
        subprocess.run(
            ["docker", "exec", container_name, "rm", container_script_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except subprocess.CalledProcessError as e:
        print(f"WARNING: Container {container_name} authentication check failed: {str(e)}")
        # Don't fail - we'll let the actual processing detect and handle any auth issues
    finally:
        # Clean up the temp file
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.remove(tmp_path)
    
    print(f"Container {container_name} started on port {port}")

def cleanup_containers(containers, keep_main=True):
    """Stop and remove Docker containers.
    
    Args:
        containers: List of container info dictionaries
        keep_main: Whether to keep the main container running
    """
    print("Cleaning up Docker containers...")
    for container in containers:
        container_name = container["name"]
        
        # Skip the main container if keep_main is True
        if keep_main and container_name == "image-crusher-local":
            continue
            
        try:
            subprocess.run(["docker", "stop", container_name], check=True)
            subprocess.run(["docker", "rm", container_name], check=True)
            print(f"Container {container_name} stopped and removed")
        except Exception as e:
            print(f"Error stopping container {container_name}: {str(e)}")


def process_files_in_parallel(storage_client, bucket_name, blobs, height=None, video_format=None, num_containers=DEFAULT_CONTAINERS, reuse_container=False, keep_container=False):
    """Process multiple files in parallel using Docker containers.
    
    Args:
        storage_client: The storage client
        bucket_name: Name of the bucket
        blobs: List of blob objects to process
        height: Output height for processed files (optional)
        video_format: Video output format (webm or ts)
        num_containers: Number of Docker containers to use
        reuse_container: Whether to reuse existing container if available
        keep_container: Whether to keep the main container running after processing
    
    Returns:
        Tuple of (success_count, fail_count)
    """
    success_count = 0
    fail_count = 0
    
    # Set up Docker containers
    containers = setup_docker_containers(num_containers, reuse_container)
    
    try:
        # Filter blobs that need processing
        to_process = []
        for blob in blobs:
            if not should_process_file(blob):
                continue
                
            if processed_file_exists(storage_client, bucket_name, blob.name, video_format):
                print(f"⏭️ Processed file already exists for {blob.name}")
                continue
                
            to_process.append(blob)
        
        print(f"Processing {len(to_process)} files using {len(containers)} Docker containers")
        
        # Create a pool of worker functions
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(containers)) as executor:
            # Submit initial batch of tasks
            futures = {}
            container_index = 0
            
            # Helper function to submit a task to a container
            def submit_task(blob, container_idx):
                container = containers[container_idx]
                return executor.submit(process_single_file, container, blob.name, blob.content_type, height, video_format)
            
            # Submit initial batch of tasks
            for i, blob in enumerate(to_process[:len(containers)]):
                futures[submit_task(blob, i)] = (blob, i)
            
            # Process remaining files as containers become available
            completed_count = 0
            total_count = len(to_process)
            
            # Track next blob to process
            next_blob_index = len(containers)
            
            # Process futures as they complete
            while futures:
                # Wait for the next future to complete
                done, _ = concurrent.futures.wait(
                    futures, 
                    return_when=concurrent.futures.FIRST_COMPLETED
                )
                
                for future in done:
                    blob, container_idx = futures.pop(future)
                    
                    # Check result
                    try:
                        if future.result():
                            success_count += 1
                        else:
                            fail_count += 1
                    except Exception as e:
                        print(f"Error processing {blob.name}: {str(e)}")
                        fail_count += 1
                    
                    completed_count += 1
                    print(f"Progress: {completed_count}/{total_count} files ({(completed_count/total_count)*100:.1f}%)")
                    
                    # Submit next task if there are more files to process
                    if next_blob_index < len(to_process):
                        next_blob = to_process[next_blob_index]
                        futures[submit_task(next_blob, container_idx)] = (next_blob, container_idx)
                        next_blob_index += 1
        
    finally:
        # Clean up containers
        cleanup_containers(containers, keep_container)
    
    return success_count, fail_count

def process_folder(folder_path=None, height=None, recursive=True, video_format=None, 
                num_containers=DEFAULT_CONTAINERS, reuse_container=False, keep_container=False):
    """Process all files in a folder, optionally recursively.
    
    Args:
        folder_path: Path to the folder (e.g., "2024/Photos")
        height: Thumbnail height (optional)
        recursive: Whether to include subfolders
        video_format: Video output format (webm or ts)
        num_containers: Number of Docker containers to use
        reuse_container: Whether to reuse existing container if available
        keep_container: Whether to keep the main container running after processing
    
    Returns:
        Tuple of (success_count, fail_count)
    """
    # Set up storage client
    storage_client, bucket_name = setup_storage_client()
    
    # If folder path not provided, ask for it
    if not folder_path:
        folder_path = input("Enter folder path in bucket (e.g., '2024/Photos'): ")
    
    print(f"Processing folder: {folder_path or 'Root'}")
    if recursive:
        print("Including all subfolders recursively")
    else:
        print("Processing only the specified folder (non-recursive)")
    
    # List all files in the folder
    blobs = list_files_in_folder(storage_client, bucket_name, folder_path, recursive)
    
    # Count how many files need processing
    to_process = [blob for blob in blobs if should_process_file(blob)]
    print(f"Found {len(blobs)} total files, {len(to_process)} need processing")
    
    if not to_process:
        print("No files to process.")
        return 0, 0
    
    # Process the files
    return process_files_in_parallel(
        storage_client, 
        bucket_name, 
        to_process, 
        height, 
        video_format, 
        num_containers, 
        reuse_container, 
        keep_container
    )

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Bulk process files in a bucket folder')
    parser.add_argument('--folder', type=str, help='Folder path to process (e.g., "2024/Photos")')
    parser.add_argument('--height', type=int, help='Output height for processed files (default: 256)')
    parser.add_argument('--no-recursive', action='store_true', help='Do not process subfolders')
    parser.add_argument('--format', type=str, choices=['webm', 'ts'], default='ts', help='Video output format (default: ts)')
    parser.add_argument('--containers', type=int, default=DEFAULT_CONTAINERS, help=f'Number of Docker containers to use (default: {DEFAULT_CONTAINERS})')
    parser.add_argument('--reuse-container', action='store_true', help='Reuse existing container if available')
    parser.add_argument('--keep-container', action='store_true', help='Keep the main container running after processing')
    
    args = parser.parse_args()
    
    # Set custom height if provided
    if args.height:
        CompressionUtils.set_thumbnail_height(args.height)
    
    # Handle SIGINT (Ctrl+C) gracefully
    def signal_handler(sig, frame):
        print("\nInterrupted by user. Cleaning up containers...")
        sys.exit(1)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Process the folder
    try:
        success, fail = process_folder(
            args.folder, 
            args.height, 
            not args.no_recursive, 
            args.format,
            args.containers,
            args.reuse_container,
            args.keep_container
        )
        
        # Print summary
        print(f"\nProcessing complete: {success} successful, {fail} failed")
    except KeyboardInterrupt:
        print("\nProcess interrupted by user.")
        sys.exit(1)