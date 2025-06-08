import os
import tempfile
import subprocess
import time
import json
import threading
import datetime
import requests
from google.auth.transport.requests import AuthorizedSession

from src.constants import *
from src.CompressionUtils import CompressionUtils
from src.VideoCompressionUtils import VideoCompressionUtils

class FileProcessor:
    @classmethod
    def is_image_file(cls, content_type=None, file_name=None):
        """Check if the file is an image.
        Args:
            content_type: The content type of the file
            file_name: The name of the file
        Returns:
            Boolean indicating if the file is an image
        """
        return CompressionUtils.is_supported_image(content_type, file_name)
    
    @classmethod
    def is_video_file(cls, content_type=None, file_name=None):
        """Check if the file is a video.
        Args:
            content_type: The content type of the file
            file_name: The name of the file
        Returns:
            Boolean indicating if the file is a video
        """
        # Method 1: Check by content type
        if content_type and content_type.startswith("video/"):
            print(f"Identified as video by content type: {content_type}")
            return True
            
        # Method 2: Check by file extension
        if file_name:
            ext = os.path.splitext(file_name.lower())[1]
            if ext in VIDEO_FORMATS:
                print(f"Identified as video by extension: {ext}")
                return True
                
        return False
    
    @classmethod
    def get_file_type(cls, content_type=None, file_name=None):
        """Determine the type of file based on content_type or file_name.
        Args:
            content_type: The content type of the file
            file_name: The name of the file
        Returns:
            File type category (image, video, or unknown)
        """
        print(f"Determining file type for: {file_name} (content type: {content_type})")
        
        # Check for video files first (so video files with image-like extensions are handled correctly)
        if cls.is_video_file(content_type, file_name):
            return TYPE_VIDEO
            
        # Check for image files
        if cls.is_image_file(content_type, file_name):
            print(f"Identified file as image")
            return TYPE_IMAGE
        
        # If we got here, we couldn't identify the file type
        print(f"Could not identify file type: content_type={content_type}, file_name={file_name}")
        return TYPE_UNKNOWN
    
    @classmethod
    def process(cls, file_info, storage_client=None, bucket=None, options=None):
        """Process a file based on its type.
        Args:
            file_info: Dictionary with file info including 'content_type' and 'name'
            storage_client: Google Cloud Storage client
            bucket: Google Cloud Storage bucket
            options: Dictionary with processing options (e.g., height)
        Returns:
            Dictionary with processed file info including 'output_file', 'output_type' and 'extension'
        """
        if options is None:
            options = {}
            
        # Determine file type
        file_type = cls.get_file_type(
            content_type=file_info.get('content_type'),
            file_name=file_info.get('name')
        )
        
        # Process based on file type
        if file_type == TYPE_IMAGE:
            return cls.process_image(file_info, storage_client, bucket, options)
        elif file_type == TYPE_VIDEO:
            return cls.process_video(file_info, storage_client, bucket, options)
        else:
            raise ValueError(f"Unsupported file type for {file_info.get('name')}")
    
    @classmethod
    def process_image(cls, file_info, storage_client, bucket, options):
        """Process an image file - downloads the file fully and then processes it.
        Args:
            file_info: Dictionary with file info
            storage_client: Google Cloud Storage client
            bucket: Google Cloud Storage bucket
            options: Dictionary with processing options
        Returns:
            Dictionary with processed file info
        """
        file_name = file_info.get('name')
        
        # Download the image to a temporary file
        blob = bucket.blob(file_name)
        _, temp_local_filename = tempfile.mkstemp()
        blob.download_to_filename(temp_local_filename)
        
        try:
            # Get height option or use default from constants
            height = options.get('height', THUMBNAIL_HEIGHT)
            
            # Compress the image
            output_file = CompressionUtils.compress_image(temp_local_filename, height)
            
            return {
                'output_file': output_file,
                'output_type': f'image/{IMAGE_OUTPUT_FORMAT}',
                'extension': f'.{IMAGE_OUTPUT_FORMAT}',
                'temp_input_file': temp_local_filename  # Return this so it can be cleaned up
            }
        except Exception as e:
            # Clean up the temp file in case of error
            os.remove(temp_local_filename)
            raise e
    
    @classmethod
    def process_video(cls, file_info, storage_client, bucket, options):
        """Process a video file - stream, compress, and extract thumbnail.
        Args:
            file_info: Dictionary with file info
            storage_client: Google Cloud Storage client
            bucket: Google Cloud Storage bucket
            options: Dictionary with processing options
        Returns:
            Dictionary with processed file info (thumbnail)
        """
        # Record start time for performance tracking
        start_time = time.time()
        
        file_name = file_info.get('name')
        content_type = file_info.get('content_type')
        print(f"Processing video: {file_name}, type: {content_type}")
        
        # Prepare file paths
        file_paths = cls._prepare_file_paths(file_name)
        
        # Make sure directories exist in GCS
        cls._ensure_directory_exists(bucket, f"{file_paths['file_dir']}/{THUMBS_DIRECTORY}/")
        cls._ensure_directory_exists(bucket, f"{file_paths['file_dir']}/{COMPRESSED_DIRECTORY}/")
        
        # Create temporary files
        _, thumb_local_path = tempfile.mkstemp(suffix=f".{IMAGE_OUTPUT_FORMAT}")
        _, metadata_local_path = tempfile.mkstemp(suffix=".json")
        
        # Create signed URL for input video streaming
        signed_download_url = cls._get_signed_url(bucket, file_name, 'read')
        
        try:
            # Get file size and determine compression settings
            blob = bucket.blob(file_name)
            blob.reload()
            file_size_bytes = blob.size
            file_size_mb = file_size_bytes / (1024 * 1024)
            file_size_gb = file_size_bytes / (1024 * 1024 * 1024)
            
            # Log the original file size
            print(f"Original video size: {file_size_mb:.2f}MB ({file_size_gb:.2f}GB)")
            
            # Determine quality settings based on file size
            compression_settings = VideoCompressionUtils.determine_video_settings(file_size_bytes)
            print(f"Using compression settings: CRF:{compression_settings['crf']}, Resolution:{compression_settings['resolution']}p, Audio:{compression_settings['audio_bitrate']}k")
            
            # Extract video metadata
            metadata, metadata_local_path, metadata_time = VideoCompressionUtils.extract_video_metadata(signed_download_url)
            
            # Parse metadata to get duration and video height
            duration, video_height = VideoCompressionUtils.parse_video_dimensions(metadata)
            
            # Adjust resolution to avoid upscaling
            if video_height > 0 and video_height < compression_settings['resolution']:
                print(f"Original height ({video_height}) is less than target ({compression_settings['resolution']}), keeping original resolution")
                compression_settings['resolution'] = video_height
            
            # Determine thumbnail position
            thumb_time = VideoCompressionUtils.determine_thumbnail_position(duration)
            
            # Get height from options or use default
            thumb_height = options.get('height', THUMBNAIL_HEIGHT)
            
            # Extract thumbnail
            thumb_local_path, thumbnail_time = VideoCompressionUtils.extract_thumbnail(
                signed_download_url, 
                thumb_time, 
                thumb_height
            )
            
            # Start video compression with direct streaming to GCS using named pipe
            print(f"Starting video compression to {compression_settings['resolution']}p with CRF {compression_settings['crf']} and streaming to GCS...")
            
            # Record compression start time
            compression_start_time = time.time()
            
            # Create an authorized transport
            credentials = storage_client._credentials
            auth_session = AuthorizedSession(credentials)
            
            # Create named pipe for streaming
            pipe_path = VideoCompressionUtils.create_named_pipe()
            
            # Setup GCS blob
            compressed_blob = bucket.blob(file_paths['compressed_path'])
            compressed_blob.content_type = "video/webm"
            
            # Create upload worker
            upload_worker, upload_success, upload_error = VideoCompressionUtils.create_upload_worker(
                pipe_path, 
                compressed_blob
            )
            
            # Start upload thread
            upload_thread = threading.Thread(target=upload_worker)
            upload_thread.daemon = True
            upload_thread.start()
            time.sleep(0.5)  # Ensure thread is ready
            
            # Build FFmpeg command
            compress_cmd = VideoCompressionUtils.build_ffmpeg_command(
                signed_download_url, 
                pipe_path, 
                compression_settings
            )
            
            # Start video compression
            print("Starting FFmpeg to write to named pipe...")
            ffmpeg_process = None
            try:
                # Start FFmpeg process
                ffmpeg_process = subprocess.Popen(
                    compress_cmd,
                    stderr=subprocess.PIPE
                )
                
                # Monitor progress
                while ffmpeg_process.poll() is None:
                    stderr_line = ffmpeg_process.stderr.readline().decode('utf-8', errors='replace')
                    if stderr_line and 'frame=' in stderr_line:
                        print(f"FFmpeg progress: {stderr_line.strip()}")
                    time.sleep(1)
                
                # Check for errors
                if ffmpeg_process.returncode != 0:
                    remaining_stderr = ffmpeg_process.stderr.read().decode('utf-8', errors='replace')
                    print(f"FFmpeg error: {remaining_stderr}")
                    raise Exception(f"FFmpeg failed with code {ffmpeg_process.returncode}")
                
                print("FFmpeg processing completed, waiting for upload to finish...")
                upload_success.wait(timeout=60)
                
                if upload_error:
                    raise Exception(f"Upload failed: {str(upload_error)}")
                
                print("Video compression and upload completed successfully")
                
            except Exception as e:
                print(f"Error in video processing pipeline: {str(e)}")
                if ffmpeg_process and ffmpeg_process.poll() is None:
                    ffmpeg_process.terminate()
                    ffmpeg_process.wait(timeout=5)
                raise
            finally:
                # Cleanup
                if os.path.exists(pipe_path):
                    os.unlink(pipe_path)
            
            # Calculate compression time
            compression_time = time.time() - compression_start_time
            
            # Get the compressed file size
            compressed_blob.reload()
            compressed_size_bytes = compressed_blob.size
            
            # Log compression results
            VideoCompressionUtils.log_compression_results(
                file_paths['file_basename'],
                file_size_bytes,
                compressed_size_bytes,
                compression_time
            )
            
            # Calculate total processing time
            total_time = time.time() - start_time
            total_minutes, total_seconds = VideoCompressionUtils.format_time(total_time)
            
            print(f"Total processing time: {total_minutes}m {total_seconds}s")
            
            # Return the thumbnail path for upload in the main process
            return {
                'output_file': thumb_local_path,
                'output_type': f'image/{IMAGE_OUTPUT_FORMAT}',
                'extension': f'.{IMAGE_OUTPUT_FORMAT}',
                'temp_input_file': None  # No temp input file to clean up when streaming
            }
            
        except Exception as e:
            print(f"Error processing video {file_name}: {str(e)}")
            # Clean up any temporary files
            for path in [thumb_local_path, metadata_local_path]:
                if os.path.exists(path):
                    os.remove(path)
            raise
    
    @classmethod
    def _prepare_file_paths(cls, file_name):
        """Prepare file paths for video processing.
        Args:
            file_name: Original file name
        Returns:
            Dictionary with various file paths
        """
        file_dir = os.path.dirname(file_name)
        file_basename = os.path.basename(file_name)
        file_name_without_ext = os.path.splitext(file_basename)[0]
        
        # Define output locations
        thumb_dir = os.path.join(file_dir, THUMBS_DIRECTORY)
        compressed_dir = os.path.join(file_dir, COMPRESSED_DIRECTORY)
        
        # Prepare file names
        thumbs_path = os.path.join(thumb_dir, f"{file_name_without_ext}.{IMAGE_OUTPUT_FORMAT}")
        compressed_path = os.path.join(compressed_dir, f"{file_name_without_ext}.webm")
        
        return {
            'file_dir': file_dir,
            'file_basename': file_basename,
            'file_name_without_ext': file_name_without_ext,
            'thumb_dir': thumb_dir,
            'compressed_dir': compressed_dir,
            'thumbs_path': thumbs_path,
            'compressed_path': compressed_path
        }
    
    @classmethod
    def _ensure_directory_exists(cls, bucket, directory_path):
        """Make sure a directory exists in GCS by creating a placeholder object."""
        dir_blob = bucket.blob(directory_path)
        if not dir_blob.exists():
            dir_blob.upload_from_string('')
    
    @classmethod
    def _get_signed_url(cls, bucket, blob_name, method='read'):
        """Generate a signed URL for a blob with specified permissions."""
        # Get the blob
        blob = bucket.blob(blob_name)
        
        # Set the expiration time for the URL (4 hours)
        expiration = datetime.datetime.utcnow() + datetime.timedelta(hours=4)
        
        # Generate the signed URL
        if method == 'read':
            url = blob.generate_signed_url(
                version='v4',
                expiration=expiration,
                method='GET'
            )
        elif method == 'write':
            url = blob.generate_signed_url(
                version='v4',
                expiration=expiration,
                method='PUT',
                content_type=blob.content_type
            )
        
        return url