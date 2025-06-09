"""
Utility functions for video compression and thumbnail extraction.
"""
import os
import json
import time
import datetime
import tempfile
import subprocess
import threading
import requests
from src.constants import *

class VideoCompressionUtils:
    @classmethod
    def determine_video_settings(cls, file_size_bytes):
        """
        Determine video compression settings based on file size.
        
        Args:
            file_size_bytes: Size of the video in bytes
            
        Returns:
            Dictionary with compression settings (crf, resolution, audio_bitrate)
        """
        file_size_gb = file_size_bytes / (1024 * 1024 * 1024)
        
        if file_size_gb < SMALL_VIDEO_THRESHOLD:
            return SMALL_VIDEO_SETTINGS
        elif file_size_gb < MEDIUM_VIDEO_THRESHOLD:
            return MEDIUM_VIDEO_SETTINGS
        else:
            return LARGE_VIDEO_SETTINGS
    
    @classmethod
    def extract_video_metadata(cls, signed_download_url):
        """
        Extract metadata from a video file.
        
        Args:
            signed_download_url: Signed URL to access the video file
            
        Returns:
            Tuple of (metadata_dict, metadata_local_path, metadata_extraction_time)
        """
        # Create temp file for metadata
        _, metadata_local_path = tempfile.mkstemp(suffix=".json")
        
        # Record time at start of metadata extraction
        metadata_start_time = time.time()
        
        # Extract video metadata
        metadata_cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json',
            '-show_format', '-show_streams', signed_download_url
        ]
        
        # Run the metadata extraction
        metadata_result = subprocess.run(
            metadata_cmd, 
            capture_output=True, 
            text=True, 
            check=True
        )
        
        metadata_time = time.time() - metadata_start_time
        print(f"Metadata extraction completed in {metadata_time:.2f} seconds")
        
        # Save metadata for analysis
        with open(metadata_local_path, 'w') as f:
            f.write(metadata_result.stdout)
        
        # Parse metadata
        metadata = json.loads(metadata_result.stdout)
        
        return metadata, metadata_local_path, metadata_time
    
    @classmethod
    def parse_video_dimensions(cls, metadata):
        """
        Parse video dimensions and duration from metadata.
        
        Args:
            metadata: Video metadata dictionary from ffprobe
            
        Returns:
            Tuple of (duration, video_height)
        """
        duration = 0
        video_height = 0
        
        # Find video stream and get duration and resolution
        for stream in metadata.get('streams', []):
            if stream.get('codec_type') == 'video':
                if 'duration' in stream:
                    duration = float(stream['duration'])
                if 'height' in stream:
                    video_height = int(stream['height'])
                break
        
        # If duration wasn't in the video stream, check format section
        if duration == 0 and 'format' in metadata and 'duration' in metadata['format']:
            duration = float(metadata['format']['duration'])
        
        print(f"Video duration: {duration:.2f} seconds")
        print(f"Video height: {video_height} pixels")
        
        return duration, video_height
    
    @classmethod
    def determine_thumbnail_position(cls, duration):
        """
        Determine the optimal position for extracting a thumbnail.
        
        Args:
            duration: Video duration in seconds
            
        Returns:
            Position in seconds for thumbnail extraction
        """
        # For videos under 10 seconds, use the middle
        # For longer videos, use the 3-second mark which typically has good content
        if duration < 10:
            thumb_time = duration / 2
            print(f"Using middle frame at {thumb_time:.2f}s for thumbnail (short video)")
        else:
            thumb_time = min(3, duration / 10)  # Either 3 seconds or 10% in, whichever is smaller
            print(f"Using frame at {thumb_time:.2f}s for thumbnail")
            
        return thumb_time
    
    @classmethod
    def extract_thumbnail(cls, signed_download_url, thumb_time, thumb_height):
        """
        Extract a thumbnail from a video at the specified time.
        
        Args:
            signed_download_url: Signed URL to access the video file
            thumb_time: Position in seconds for thumbnail extraction
            thumb_height: Height of the thumbnail in pixels
            
        Returns:
            Tuple of (thumbnail_local_path, thumbnail_extraction_time)
        """
        # Create temp file for thumbnail
        _, thumb_local_path = tempfile.mkstemp(suffix=".webp")
        
        # Start thumbnail extraction time tracking
        thumbnail_start_time = time.time()
        
        print("Generating video thumbnail...")
        
        # Make sure thumb_height is a valid integer
        if thumb_height is None:
            thumb_height = THUMBNAIL_HEIGHT
        
        # Ensure it's a string for the command
        thumb_height_str = str(thumb_height)
        
        # Use the most reliable method: seeking to position BEFORE input
        # Scale with the specified height but maintain aspect ratio
        thumbnail_cmd = [
            'ffmpeg', '-y', 
            '-ss', str(thumb_time),
            '-i', signed_download_url, 
            '-vframes', '1',
            # -2 means auto-calculate width to maintain aspect ratio
            f'-vf', f'scale=-2:{thumb_height_str}:flags=accurate_rnd,format=yuv420p',
            '-c:v', 'webp',
            '-pix_fmt', 'yuv420p',
            '-quality', str(IMAGE_OUTPUT_QUALITY),
            thumb_local_path
        ]
        
        # Execute the thumbnail command with shorter timeout
        try:
            print(f"Extracting thumbnail at position {thumb_time}s...")
            subprocess.run(thumbnail_cmd, check=True, timeout=10)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            print("First thumbnail attempt failed, trying simpler approach...")
            # Try a different approach if the first fails - first frame
            # Use the same height and quality settings as the first attempt
            fallback_cmd = [
                'ffmpeg', '-y',
                '-i', signed_download_url,
                '-vframes', '1',
                '-vf', f'scale=-2:{thumb_height_str}:flags=accurate_rnd,format=yuv420p',
                '-c:v', 'webp',
                '-pix_fmt', 'yuv420p',
                '-quality', str(IMAGE_OUTPUT_QUALITY),
                thumb_local_path
            ]
            subprocess.run(fallback_cmd, check=True)
        
        thumbnail_time = time.time() - thumbnail_start_time
        print(f"Thumbnail extraction completed in {thumbnail_time:.2f} seconds")
        
        return thumb_local_path, thumbnail_time
    
    @classmethod
    def build_ffmpeg_command(cls, signed_download_url, pipe_path, settings, output_format=None):
        """
        Build the FFmpeg command for video compression.
        
        Args:
            signed_download_url: Signed URL to access the video file
            pipe_path: Path to the named pipe for output
            settings: Dictionary with compression settings
            output_format: Output format (webm or mp4), defaults to VIDEO_OUTPUT_FORMAT
        """
        # Use the specified format or fall back to the default
        format_type = output_format or VIDEO_OUTPUT_FORMAT
        
        # Common settings
        command = [
            'ffmpeg', '-y', '-i', signed_download_url,
            '-vf', f'scale=-2:{settings["resolution"]}',
        ]
        
        # Format-specific settings
        if format_type == VIDEO_FORMAT_WEBM:
            # WebM with VP9
            command.extend([
                '-c:v', WEBM_VIDEO_CODEC,
                '-b:v', '0',
                '-crf', str(settings['crf']),
                '-g', str(VIDEO_KEYFRAME_INTERVAL),
                '-keyint_min', str(VIDEO_KEYFRAME_INTERVAL),
                '-c:a', WEBM_AUDIO_CODEC,
                '-ac', str(WEBM_AUDIO_CHANNELS),
                '-b:a', f'{settings["audio_bitrate"]}k',
                # WebM container format settings for better seeking
                '-index_correction', WEBM_INDEX_CORRECTION,
                '-cluster_size_limit', WEBM_CLUSTER_SIZE_LIMIT,
                '-cluster_time_limit', WEBM_CLUSTER_TIME_LIMIT,
                '-skip_threshold', WEBM_SKIP_THRESHOLD,
                '-f', 'webm'
            ])
        elif format_type == VIDEO_FORMAT_MP4:
            # MP4 with H.265/HEVC - using MPEG-TS format for pipe output
            # MP4 muxer doesn't support non-seekable output, so use TS format for the pipe
            command.extend([
                '-c:v', MP4_VIDEO_CODEC,
                '-crf', str(settings['crf']),
                '-preset', MP4_PRESET,
                '-x265-params', MP4_X265_PARAMS,
                '-c:a', MP4_AUDIO_CODEC,
                '-ac', str(MP4_AUDIO_CHANNELS),
                '-b:a', f'{settings["audio_bitrate"]}k',
                '-f', 'mpegts'  # Use MPEG-TS format for pipe output which supports streaming
            ])
        elif format_type == VIDEO_FORMAT_TS:
            # MPEG-TS with H.264/AVC
            command.extend([
                '-c:v', TS_VIDEO_CODEC,        # Use H.264 codec
                '-crf', str(settings['crf']),
                '-preset', TS_PRESET,
                '-profile:v', TS_PROFILE,      # High profile for better quality
                '-level', TS_LEVEL,            # Widely compatible level
                '-tune', TS_TUNE,              # Film tuning for general content
                '-x264-params', TS_X264_PARAMS,# Optimized encoding parameters
                '-c:a', TS_AUDIO_CODEC,        # Use AAC audio
                '-ac', str(TS_AUDIO_CHANNELS),
                '-b:a', f'{settings["audio_bitrate"]}k',
                '-movflags', '+faststart',     # Optimize for streaming
                '-f', 'mpegts'                 # MPEG-TS format supports streaming
            ])
        else:
            # Fallback to WebM if format is unknown
            command.extend([
                '-c:v', WEBM_VIDEO_CODEC,
                '-b:v', '0',
                '-crf', str(settings['crf']),
                '-g', str(VIDEO_KEYFRAME_INTERVAL),
                '-keyint_min', str(VIDEO_KEYFRAME_INTERVAL),
                '-c:a', WEBM_AUDIO_CODEC,
                '-ac', str(WEBM_AUDIO_CHANNELS),
                '-b:a', f'{settings["audio_bitrate"]}k',
                '-f', 'webm'
            ])
        
        # Add output path
        command.append(pipe_path)
        
        return command
    
    @classmethod
    def create_upload_worker(cls, pipe_path, compressed_blob, output_format=None):
        """
        Create an upload worker function for streaming to GCS.
        
        Args:
            pipe_path: Path to the named pipe for input
            compressed_blob: GCS blob object for the output
            output_format: Output format (webm, mp4, or ts), defaults to VIDEO_OUTPUT_FORMAT
            
        Returns:
            Tuple of (upload_worker_function, upload_success_event, upload_error_reference)
        """
        # Thread synchronization
        upload_success = threading.Event()
        upload_error = None
        
        # Use the specified format or fall back to the default
        format_type = output_format or VIDEO_OUTPUT_FORMAT
        
        # Upload worker function - uses closure to access the variables
        def upload_worker():
            nonlocal upload_error
            try:
                print("Upload worker thread starting")
                
                # Get signed URL for direct upload
                # Use the appropriate content type based on format
                if format_type == VIDEO_FORMAT_MP4:
                    content_type = "video/mp4"
                elif format_type == VIDEO_FORMAT_TS:
                    content_type = "video/mp2t"
                else:
                    content_type = "video/webm"
                signed_url = compressed_blob.generate_signed_url(
                    version="v4",
                    expiration=datetime.datetime.utcnow() + datetime.timedelta(hours=1),
                    method="PUT",
                    content_type=content_type
                )
                
                # Stream data from pipe to GCS
                with open(pipe_path, 'rb') as pipe_file:
                    print("Starting streaming upload to GCS")
                    response = requests.put(
                        signed_url,
                        data=pipe_file,
                        headers={"Content-Type": content_type}
                    )
                    
                    if response.status_code in (200, 201):
                        print(f"Upload successful: HTTP {response.status_code}")
                    else:
                        raise Exception(f"Upload failed: HTTP {response.status_code} - {response.text}")
                
                print("Upload worker thread completed successfully")
                upload_success.set()
            except Exception as e:
                upload_error = e
                print(f"Upload worker thread error: {str(e)}")
                upload_success.set()
        
        return upload_worker, upload_success, upload_error
    
    @classmethod
    def create_named_pipe(cls):
        """
        Create a named pipe for streaming data.
        
        Returns:
            Path to the created named pipe
        """
        # Use the appropriate file extension based on format
        if VIDEO_OUTPUT_FORMAT == VIDEO_FORMAT_MP4:
            suffix = ".mp4"
        elif VIDEO_OUTPUT_FORMAT == VIDEO_FORMAT_TS:
            suffix = ".ts"
        else:
            suffix = ".webm"
        pipe_path = tempfile.mktemp(suffix=suffix)
        try:
            os.mkfifo(pipe_path)
            print(f"Created named pipe at {pipe_path}")
            return pipe_path
        except Exception as e:
            print(f"Error creating named pipe: {str(e)}")
            raise
    
    @classmethod
    def log_compression_results(cls, file_basename, file_size_bytes, compressed_size_bytes, compression_time):
        """
        Log the results of video compression.
        
        Args:
            file_basename: Original file name
            file_size_bytes: Original file size in bytes
            compressed_size_bytes: Compressed file size in bytes
            compression_time: Time taken for compression in seconds
        """
        # Calculate sizes in MB
        file_size_mb = file_size_bytes / (1024 * 1024)
        compressed_size_mb = compressed_size_bytes / (1024 * 1024)
        
        # Calculate compression ratio and savings
        compression_ratio = file_size_bytes / compressed_size_bytes if compressed_size_bytes > 0 else 0
        space_saved_mb = (file_size_bytes - compressed_size_bytes) / (1024 * 1024)
        space_saved_percent = (space_saved_mb / file_size_mb) * 100 if file_size_mb > 0 else 0
        
        # Format compression time as minutes:seconds
        compression_minutes = int(compression_time // 60)
        compression_seconds = int(compression_time % 60)
        
        # Create detailed compression log
        print("=" * 80)
        print(f"VIDEO COMPRESSION COMPLETE: {file_basename}")
        print(f"Original size:    {file_size_mb:.2f}MB")
        print(f"Compressed size:  {compressed_size_mb:.2f}MB")
        print(f"Space saved:      {space_saved_mb:.2f}MB ({space_saved_percent:.1f}%)")
        print(f"Compression ratio: {compression_ratio:.2f}x")
        print(f"Compression time: {compression_minutes}m {compression_seconds}s")
        print(f"Processing speed: {(file_size_mb/compression_time):.2f}MB/sec")
        print("=" * 80)
    
    @classmethod
    def format_time(cls, seconds):
        """
        Format time in seconds as minutes and seconds.
        
        Args:
            seconds: Time in seconds
            
        Returns:
            Tuple of (minutes, seconds)
        """
        minutes = int(seconds // 60)
        remaining_seconds = int(seconds % 60)
        return minutes, remaining_seconds