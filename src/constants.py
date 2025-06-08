"""
Constants and settings for image and video processing.
"""

# Image settings
THUMBNAIL_HEIGHT = 512
IMAGE_OUTPUT_FORMAT = "webp"
IMAGE_OUTPUT_QUALITY = 90
IMAGE_OUTPUT_METHOD = 6

# Supported image types for compression
SUPPORTED_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".gif", ".webp"]
SUPPORTED_IMAGE_MIMETYPES = ["image/jpeg", "image/png", "image/bmp", "image/tiff", "image/gif", "image/webp"]

# Video settings
VIDEO_FORMATS = [
    ".mp4", ".mov", ".avi", ".wmv", ".flv", ".mkv", 
    ".webm", ".m4v", ".mpg", ".mpeg", ".3gp", ".3g2", 
    ".ts", ".mts", ".m2ts", ".mp2", ".MP4"
]

# Video compression settings for different file sizes
SMALL_VIDEO_SETTINGS = {
    "crf": 25,           # Quality (lower is better)
    "resolution": 720,  # Height in pixels
    "audio_bitrate": 96  # Audio bitrate in kb/s
}

MEDIUM_VIDEO_SETTINGS = {
    "crf": 28,
    "resolution": 720,
    "audio_bitrate": 64
}

LARGE_VIDEO_SETTINGS = {
    "crf": 30,
    "resolution": 480,
    "audio_bitrate": 32
}

# Threshold sizes in GB
SMALL_VIDEO_THRESHOLD = 1    # < 1GB
MEDIUM_VIDEO_THRESHOLD = 5   # 1-5GB

# Video encoding settings
VIDEO_KEYFRAME_INTERVAL = 60  # Keyframe interval in frames
VIDEO_CODEC = "libvpx-vp9"    # Video codec
AUDIO_CODEC = "libopus"       # Audio codec
AUDIO_CHANNELS = 1            # Number of audio channels (1=mono)
ENCODING_PRESET = "good"      # Encoding speed/quality tradeoff

# File type categories
TYPE_UNKNOWN = "unknown"
TYPE_IMAGE = "image"
TYPE_VIDEO = "video"

# Output directories
THUMBS_DIRECTORY = "THUMBS"
COMPRESSED_DIRECTORY = "COMPRESSED"