#!/usr/bin/env python
"""
RunBulk.py - Process a folder in the bucket and create processed versions of files.
This script can be run directly or imported and used by main.py.
"""

import os
import sys
import argparse
import tempfile
import concurrent.futures
from google.cloud import storage
from src.CompressionUtils import CompressionUtils
from src.FileProcessor import FileProcessor

# Number of worker threads for parallel processing
MAX_WORKERS = 10

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
        # Skip THUMBS directories
        if "/THUMBS/" in blob.name or blob.name.endswith("/THUMBS"):
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
    # Skip files in THUMBS directories (case insensitive)
    if "/THUMBS/" in blob.name or "/thumbs/" in blob.name:
        return False
    
    # Check if the file type is supported
    file_type = FileProcessor.get_file_type(content_type=blob.content_type, file_name=blob.name)
    if file_type == FileProcessor.TYPE_UNKNOWN:
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

def processed_file_exists(storage_client, bucket_name, original_path):
    """Check if a processed file exists for the original file.
    
    Args:
        storage_client: The storage client
        bucket_name: Name of the bucket
        original_path: Path to the original file
    
    Returns:
        True if the processed file exists, False otherwise
    """
    bucket = storage_client.bucket(bucket_name)
    output_path = get_thumb_path(original_path)
    output_blob = bucket.blob(output_path)
    return output_blob.exists()

def process_single_file(storage_client, bucket_name, blob_name, content_type=None, height=None):
    """Process a single file.
    
    Args:
        storage_client: The storage client
        bucket_name: Name of the bucket
        blob_name: Name of the blob to process
        content_type: Content type of the blob (optional)
        height: Output height (optional)
    
    Returns:
        True if successful, False otherwise
    """
    try:
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        # If content type not provided, get it from the blob
        if not content_type:
            blob.reload()  # Get latest metadata
            content_type = blob.content_type
        
        # Create file info dictionary
        file_info = {
            'name': blob_name,
            'content_type': content_type
        }
        
        # Process options
        options = {}
        if height is not None:
            options['height'] = height
            
        # Process the file with FileProcessor
        process_result = FileProcessor.process(
            file_info=file_info,
            storage_client=storage_client, 
            bucket=bucket,
            options=options
        )
        
        # Get the processed file and info
        processed_file = process_result['output_file']
        output_extension = process_result['extension']
        output_type = process_result['output_type']
        temp_input_file = process_result.get('temp_input_file')
        
        # Create the output path
        file_dir = os.path.dirname(blob_name)
        thumb_dir = os.path.join(file_dir, "THUMBS")
        file_basename = os.path.basename(blob_name)
        file_name_without_ext = os.path.splitext(file_basename)[0]
        output_path = os.path.join(thumb_dir, f"{file_name_without_ext}{output_extension}")
        
        # Make sure THUMBS directory exists
        thumbs_dir_blob = bucket.blob(f"{file_dir}/THUMBS/")
        if not thumbs_dir_blob.exists():
            thumbs_dir_blob.upload_from_string('')
        
        # Upload the processed file
        thumb_blob = bucket.blob(output_path)
        thumb_blob.upload_from_filename(processed_file)
        thumb_blob.content_type = output_type
        thumb_blob.patch()
        
        # Clean up temporary files
        os.remove(processed_file)
        if temp_input_file:
            os.remove(temp_input_file)
        
        print(f"✅ Created processed file: {output_path}")
        return True
        
    except NotImplementedError as e:
        # Handle case where processing for this file type is not yet implemented
        print(f"⚠️ Skipping {blob_name}: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ Error processing {blob_name}: {str(e)}")
        return False

def process_files_in_parallel(storage_client, bucket_name, blobs, height=None):
    """Process multiple files in parallel using ThreadPoolExecutor.
    
    Args:
        storage_client: The storage client
        bucket_name: Name of the bucket
        blobs: List of blob objects to process
        height: Output height for processed files (optional)
    
    Returns:
        Tuple of (success_count, fail_count)
    """
    success_count = 0
    fail_count = 0
    
    # Define function for parallel execution
    def process_blob(blob):
        # Skip if processed file already exists
        if processed_file_exists(storage_client, bucket_name, blob.name):
            print(f"⏭️ Processed file already exists for {blob.name}")
            return True
        
        # Process the file
        return process_single_file(storage_client, bucket_name, blob.name, blob.content_type, height)
    
    # Process in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for blob in blobs:
            if should_process_file(blob):
                futures.append(executor.submit(process_blob, blob))
        
        for future in concurrent.futures.as_completed(futures):
            if future.result():
                success_count += 1
            else:
                fail_count += 1
    
    return success_count, fail_count

def process_folder(folder_path=None, height=None, recursive=True):
    """Process all files in a folder, optionally recursively.
    
    Args:
        folder_path: Path to the folder (e.g., "2024/Photos")
        height: Thumbnail height (optional)
        recursive: Whether to include subfolders
    
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
    return process_files_in_parallel(storage_client, bucket_name, to_process, height)

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Bulk process files in a bucket folder')
    parser.add_argument('--folder', type=str, help='Folder path to process (e.g., "2024/Photos")')
    parser.add_argument('--height', type=int, help='Output height for processed files (default: 256)')
    parser.add_argument('--no-recursive', action='store_true', help='Do not process subfolders')
    
    args = parser.parse_args()
    
    # Set custom height if provided
    if args.height:
        CompressionUtils.set_thumbnail_height(args.height)
    
    # Process the folder
    success, fail = process_folder(args.folder, args.height, not args.no_recursive)
    
    # Print summary
    print(f"\nProcessing complete: {success} successful, {fail} failed")