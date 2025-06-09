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

# Video output format options
VIDEO_FORMAT_WEBM = "webm"    # WebM with VP9 codec
VIDEO_FORMAT_MP4 = "mp4"      # MP4 with H.265 codec
VIDEO_FORMAT_TS = "ts"        # MPEG-TS with H.265 codec
VIDEO_OUTPUT_FORMAT = VIDEO_FORMAT_TS  # Default format

# Video encoding settings - general
VIDEO_KEYFRAME_INTERVAL = 150  # Keyframe interval in frames (5 seconds at 30fps)

# WebM (VP9) specific settings
WEBM_VIDEO_CODEC = "libvpx-vp9"  # VP9 codec for WebM
WEBM_AUDIO_CODEC = "libopus"     # Opus audio codec for WebM
WEBM_AUDIO_CHANNELS = 1          # Mono audio for WebM
WEBM_ENCODING_PRESET = "good"    # Encoding preset for VP9

# WebM container format settings for better seeking (especially on Android)
WEBM_INDEX_CORRECTION = "1"      # Ensures proper index generation
WEBM_CLUSTER_SIZE_LIMIT = "2M"   # Maximum cluster size
WEBM_CLUSTER_TIME_LIMIT = "5000" # New cluster every 5 seconds (ms)
WEBM_SKIP_THRESHOLD = "0"        # Index all frames for better seeking

# MP4 (H.265) specific settings
MP4_VIDEO_CODEC = "libx265"      # H.265/HEVC codec for MP4
MP4_AUDIO_CODEC = "aac"          # AAC audio codec for MP4
MP4_AUDIO_CHANNELS = 2           # Stereo audio for MP4
MP4_PRESET = "medium"            # Encoding preset for H.265
MP4_X265_PARAMS = "keyint=150:min-keyint=150"  # Keyframe settings for H.265

# TS (H.264) specific settings
TS_VIDEO_CODEC = "libx264"       # H.264/AVC codec for MPEG-TS
TS_AUDIO_CODEC = "aac"           # AAC audio codec for MPEG-TS
TS_AUDIO_CHANNELS = 2            # Stereo audio for MPEG-TS
TS_PRESET = "medium"             # Encoding preset for H.264
# H.264 specific settings for optimized quality/size
TS_PROFILE = "high"              # High profile for better quality
TS_LEVEL = "4.1"                 # Widely supported level
TS_TUNE = "film"                 # Tune for film content (general purpose)
TS_X264_PARAMS = "keyint=150:min-keyint=150:scenecut=40:bframes=3:b-adapt=2:ref=5"  # Keyframe and quality settings

# Legacy settings for backward compatibility
VIDEO_CODEC = WEBM_VIDEO_CODEC     # Default to WebM codec
AUDIO_CODEC = WEBM_AUDIO_CODEC     # Default to WebM audio codec
AUDIO_CHANNELS = WEBM_AUDIO_CHANNELS  # Default to WebM audio channels
ENCODING_PRESET = WEBM_ENCODING_PRESET  # Default to WebM preset

# File type categories
TYPE_UNKNOWN = "unknown"
TYPE_IMAGE = "image"
TYPE_VIDEO = "video"

# Output directories
THUMBS_DIRECTORY = "THUMBS"
COMPRESSED_DIRECTORY = "COMPRESSED"