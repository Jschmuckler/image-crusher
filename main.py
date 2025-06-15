import os
import tempfile
import functions_framework
from google.cloud import storage
from src.FileProcessor import FileProcessor
import flask
from flask import Flask, jsonify

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

# Define Flask app - this will be used for both functions-framework local testing and Cloud Run
app = flask.Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for Cloud Run."""
    try:
        # Try a simple storage operation to verify service account credentials
        buckets = list(storage_client.list_buckets(max_results=1))
        return jsonify({
            "status": "healthy",
            "project": PROJECT_ID,
            "bucket": BUCKET_NAME,
            "storage_client": "initialized",
            "ffmpeg_available": os.system("which ffmpeg > /dev/null") == 0
        }), 200
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e)
        }), 500

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
    
    # Skip if it's already in any THUMBS or COMPRESSED directory
    if ("/THUMBS/" in file_name or file_name.endswith("/THUMBS") or "/THUMBS/" in file_name.upper() or
        "/COMPRESSED/" in file_name or file_name.endswith("/COMPRESSED") or "/COMPRESSED/" in file_name.upper() or
        file_name.endswith(".webp") or file_name.endswith(".ts")):
        print(f"Skipping {file_name}: in THUMBS or COMPRESSED directory or already processed format")
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
            thumb_blob.content_type = output_type 
            thumb_blob.upload_from_filename(processed_file)
            
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

# HTTP function for Cloud Run
@app.route('/', methods=['POST'])
def http_handler():
    """HTTP endpoint for Cloud Run, handles both direct HTTP requests and CloudEvents from Eventarc."""
    # Check if this is a CloudEvent
    content_type = flask.request.headers.get('Content-Type', '')
    
    if 'application/cloudevents' in content_type:
        # This is a CloudEvent from Eventarc
        print("Received CloudEvent from Eventarc")
        
        # Parse the CloudEvent
        try:
            cloud_event = None
            
            if content_type == 'application/cloudevents+json':
                # JSON formatted CloudEvent
                cloud_event_data = flask.request.get_json()
                
                # Create a simple CloudEvent-like object
                class SimpleCloudEvent:
                    def __init__(self, data):
                        self.data = data
                
                # Extract just the data portion we need
                if 'data' in cloud_event_data:
                    cloud_event = SimpleCloudEvent(cloud_event_data['data'])
                else:
                    return jsonify({"error": "Missing data field in CloudEvent"}), 400
                
            else:
                # Binary mode CloudEvent
                # Get CloudEvent data from HTTP headers
                ce_id = flask.request.headers.get('ce-id')
                ce_source = flask.request.headers.get('ce-source')
                ce_type = flask.request.headers.get('ce-type')
                
                # Parse the data
                data = flask.request.get_json()
                
                # Create a CloudEvent-like object
                class SimpleCloudEvent:
                    def __init__(self, data):
                        self.data = data
                
                cloud_event = SimpleCloudEvent(data)
            
            # Process the CloudEvent
            process(cloud_event)
            return jsonify({"status": "success"}), 200
            
        except Exception as e:
            print(f"Error processing CloudEvent: {str(e)}")
            return jsonify({"error": str(e)}), 500
    
    else:
        # This is a direct HTTP request, not a CloudEvent
        print("Received direct HTTP request (not a CloudEvent)")
        
        try:
            # Parse the request data
            request_data = flask.request.get_json()
            
            # Create a CloudEvent-like object
            class SimpleCloudEvent:
                def __init__(self, data):
                    self.data = data
            
            cloud_event = SimpleCloudEvent(request_data)
            
            # Process the request
            process(cloud_event)
            return jsonify({"status": "success"}), 200
            
        except Exception as e:
            print(f"Error processing HTTP request: {str(e)}")
            return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    # For local development with Flask
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)