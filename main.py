import os
import tempfile
import functions_framework
from google.cloud import storage
from src.FileProcessor import FileProcessor

# For bulk processing
import RunBulk

# Environment variables
PROJECT_ID = os.environ.get('PROJECT_ID')
BUCKET_NAME = os.environ.get('BUCKET_NAME')

# Initialize storage client with application default credentials
import json
import tempfile

# Create storage client using the service account credentials
print(f"Initializing storage client for project: {PROJECT_ID}")
storage_client = storage.Client(project=PROJECT_ID)
print(f"Storage client initialized successfully")

bucket = storage_client.bucket(BUCKET_NAME)

@functions_framework.cloud_event
def process(cloud_event):
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
    
    # Skip if it's already in any THUMBS directory
    if "/THUMBS/" in file_name or file_name.endswith("/THUMBS") or "/THUMBS/" in file_name.upper():
        print(f"Skipping {file_name}: in THUMBS directory")
        return
    
    print(f"Processing file: {file_name}")
    
    try:
        # Create file info dictionary
        file_info = {
            'name': file_name,
            'content_type': content_type
        }
        
        # Process the file using the appropriate processor
        try:
            # Process the file with the FileProcessor
            process_result = FileProcessor.process(
                file_info=file_info,
                storage_client=storage_client,
                bucket=bucket,
                options={}  # Empty options will use default height
            )
            
            # Get the processed file and info
            processed_file = process_result['output_file']
            output_extension = process_result['extension']
            output_type = process_result['output_type']
            temp_input_file = process_result.get('temp_input_file')
            
            # Create the output path
            file_dir = os.path.dirname(file_name)
            thumb_dir = os.path.join(file_dir, "THUMBS")
            file_basename = os.path.basename(file_name)
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
                
            print(f"Successfully created processed file: {output_path}")
            
        except NotImplementedError as e:
            # Handle case where processing for this file type is not yet implemented
            print(f"Skipping file: {str(e)}")
            
    except Exception as e:
        print(f"Error processing {file_name}: {str(e)}")
        raise

if __name__ == "__main__":
    # For local testing
    class MockEvent:
        data = {"name": "test/image.jpg", "contentType": "image/jpeg"}
    
    # Test an image
    print("Testing image processing:")
    process(MockEvent())
    
    # Test a video (will raise NotImplementedError but shows it works)
    try:
        print("\nTesting video processing:")
        video_event = MockEvent()
        video_event.data = {"name": "test/video.mp4", "contentType": "video/mp4"}
        process(video_event)
    except NotImplementedError as e:
        print(f"Expected error for video: {e}")
