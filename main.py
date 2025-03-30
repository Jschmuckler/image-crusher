import os
import tempfile
import functions_framework
from google.cloud import storage
from src.CompressionUtils import CompressionUtils

# For bulk processing
import RunBulk

# Environment variables
PROJECT_ID = os.environ.get('PROJECT_ID')
BUCKET_NAME = os.environ.get('BUCKET_NAME')

# Initialize global clients with explicit credentials from gcloud
import subprocess
import json
import tempfile

def get_credentials_from_gcloud():
    """Get credentials for the active gcloud account"""
    try:
        # Run gcloud command to get access token for the configured account
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
        print(f"Error getting credentials from gcloud: {e}")
        print("Falling back to default credentials")
        return None

# Try to get credentials from gcloud, otherwise use default
credentials = get_credentials_from_gcloud()
if credentials:
    storage_client = storage.Client(project=PROJECT_ID, credentials=credentials)
    print(f"Using explicit credentials from gcloud")
else:
    storage_client = storage.Client(project=PROJECT_ID)
    print(f"Using default credentials")

bucket = storage_client.bucket(BUCKET_NAME)

@functions_framework.cloud_event
def process_image(cloud_event):
    """Cloud Function triggered by Cloud Storage when a file is uploaded,
    or by a manual request to bulk process a folder.
    Args:
        cloud_event: Cloud Event containing Storage event data or bulk processing request
    """
    # Get data from the event
    data = cloud_event.data
    
    # Check if this is a bulk processing request
    if data.get("bulk_process", False) and "folder_path" in data:
        # Handle bulk processing request
        print(f"Received bulk processing request for folder: {data['folder_path']}")
        
        # Get parameters
        folder_path = data["folder_path"]
        recursive = data.get("recursive", True)
        height = data.get("height", None)
        
        # Call RunBulk to process the folder
        success, fail = RunBulk.process_folder(
            folder_path=folder_path,
            height=height,
            recursive=recursive
        )
        
        print(f"Bulk processing complete: {success} successful, {fail} failed")
        return
    
    # Regular single file processing for storage event
    file_name = data.get("name", "")
    content_type = data.get("contentType", "")
    
    if not file_name:
        print("No file name provided in event data")
        return
    
    # Skip if it's already in any THUMBS directory or not a supported image
    if "/THUMBS/" in file_name or file_name.endswith("/THUMBS") or "/THUMBS/" in file_name.upper() or not CompressionUtils.is_supported_image(content_type, file_name):
        print(f"Skipping {file_name}: in THUMBS directory or not a supported image type")
        return
    
    print(f"Processing file: {file_name}")
    
    try:
        # Download the image to a temporary file
        blob = bucket.blob(file_name)
        _, temp_local_filename = tempfile.mkstemp()
        blob.download_to_filename(temp_local_filename)
        
        # Create the thumbnail path
        file_dir = os.path.dirname(file_name)
        thumb_dir = os.path.join(file_dir, "THUMBS")
        file_basename = os.path.basename(file_name)
        file_name_without_ext = os.path.splitext(file_basename)[0]
        thumb_path = os.path.join(thumb_dir, f"{file_name_without_ext}.webp")
        
        # Create the compressed image
        compressed_file = CompressionUtils.compress_image(temp_local_filename)
        
        # Upload the thumbnail
        thumb_blob = bucket.blob(thumb_path)
        thumb_blob.upload_from_filename(compressed_file)
        thumb_blob.content_type = "image/webp"
        thumb_blob.patch()
        
        # Clean up temporary files
        os.remove(temp_local_filename)
        os.remove(compressed_file)
        
        print(f"Successfully created thumbnail: {thumb_path}")
        
    except Exception as e:
        print(f"Error processing {file_name}: {str(e)}")
        raise

if __name__ == "__main__":
    # For local testing
    class MockEvent:
        data = {"name": "test/image.jpg", "contentType": "image/jpeg"}
    
    process_image(MockEvent())
