# Image Crusher

A Google Cloud Function that automatically processes files uploaded to a Cloud Storage bucket, creating WebP thumbnails for images and processing videos.

## Features

- Automatically processes different file types uploaded to Cloud Storage
- For images: Creates WebP thumbnails with configurable height while maintaining aspect ratio
- For videos: Compresses to MPEG-TS (.ts) or WebM formats with H.264/VP9 encoding and creates WebP thumbnails
- Supports all common image formats (JPEG, PNG, GIF, BMP, TIFF, WebP)
- Supports common video formats (MP4, MOV, AVI, MKV, WebM, etc.)
- Stores processed images in a `THUMBS` subdirectory within the original file's directory
- Stores compressed videos in a `COMPRESSED` subdirectory within the original file's directory
- Includes bulk processing functionality to handle existing files
- Uses Docker with FFmpeg for video processing capabilities

## Setup

### Prerequisites

1. Make sure you have the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed
2. [Docker](https://www.docker.com/get-started/) must be installed for both local testing and deployment
3. Clone this repository
4. Make the scripts executable: `chmod +x *.sh`

### Service Account Setup

The project uses a dedicated service account for authentication both locally and in deployment:

1. Set your project ID as an environment variable:
   ```bash
   export PROJECT_ID="your-gcp-project-id"
   ```

2. Run the setup script to create a service account with the necessary permissions:
   ```bash
   ./setup-service-account.sh
   ```

   This script performs the following actions:
   - Creates a service account named `image-crusher-sa` if it doesn't exist
   - Grants it necessary permissions:
     - `storage.objectAdmin` (to read and write files in Cloud Storage)
     - `secretmanager.secretAccessor` (to access secrets in Secret Manager)
   - Creates a key for the service account
   - Stores the key in Secret Manager as `image-crusher-sa-key`
   - Creates a second secret `image-bucket` to store the bucket name
   - Saves your current bucket name to this secret
   
   You will be prompted to:
   - Confirm or provide your project ID
   - Enter the bucket name to use for processing
   - Choose whether to create a new service account or use an existing one

   This setup only needs to be done once per project. The script can also be used to update permissions or recreate keys if needed.

3. After running the script, verify the output to ensure all steps completed successfully:
   ```
   Service account image-crusher-sa@your-project-id.iam.gserviceaccount.com created
   Permissions assigned successfully
   Service account key created and stored in Secret Manager
   Bucket name stored in Secret Manager
   ```

### Deployment

Once the service account is set up, deploy the function:

```bash
./deploy.sh
```

## Configuration

### Image Settings
The default thumbnail height is set to 512 pixels. You can modify this by changing the `THUMBNAIL_HEIGHT` variable in `src/constants.py` or passing the `--height` parameter when running bulk processing.

### Video Settings
Videos are processed with different quality settings based on size:
- Small videos (< 1GB): Higher quality (CRF 25), 720p resolution, 96kbps audio
- Medium videos (1-5GB): Medium quality (CRF 28), 720p resolution, 64kbps audio
- Large videos (> 5GB): Lower quality (CRF 30), 480p resolution, 32kbps audio

You can choose between two output formats:
- MPEG-TS (.ts): Uses H.264 encoding with AAC audio. Better compatibility and streaming performance.
- WebM: Uses VP9 encoding with Opus audio. Better compression but less compatibility.

MPEG-TS is the default format and is recommended for most use cases as it provides:
- Better compatibility across devices and browsers
- Improved streaming performance
- Good compression-to-quality ratio with H.264
- More reliable seeking within videos

These settings can be adjusted in `src/constants.py`.

## Bulk Processing

To generate thumbnails for existing images in the bucket, you can use the bulk processing feature. There are two ways to do this:

### Local Development

For local testing, the function runs in a Docker container:

```bash
./deploy-local.sh
```

This will:
- Build a Docker image with FFmpeg and all dependencies
- Retrieve the service account key from Secret Manager
- Start a container with the function running on port 8080
- Configure the container with the proper authentication

Then in another terminal, use the bulk-process.py script or test individual files:

```bash
# Test processing a single file
python3 local-test.py --file-path='path/to/file.jpg'

# Process an entire folder and its subfolders
python bulk-process.py --folder="2024/Photos"

# Process a specific folder without recursing into subfolders
python bulk-process.py --folder="2024/Photos" --no-recursive

# Override the output height
python bulk-process.py --folder="2024/Photos" --height=512

# Run interactively (will prompt for folder)
python bulk-process.py
```

To view the logs from the container:
```bash
docker logs -f image-crusher-local
```

To stop the container when done:
```bash
docker stop image-crusher-local
```

### Parallel Processing with Docker

For efficient processing of large folders, especially with videos, you can use the RunBulk.py script with Docker containers for parallel processing:

```bash
# Set required environment variables
export PROJECT_ID="your-gcp-project-id"  # Your Google Cloud project ID
export BUCKET_NAME="your-bucket-name"    # Your Google Cloud Storage bucket name

# Optional: if you want to use a specific service account key file directly
# export GOOGLE_APPLICATION_CREDENTIALS="/path/to/keyfile.json"

# First run deploy-local.sh to ensure the Docker image is built and configured
./deploy-local.sh

# Run the bulk processing with Docker containers
python RunBulk.py --folder="2025/Photos" --format ts --containers 8 --reuse-container --keep-container
```

**Important Note on Environment Variables:**
- These environment variables must be set in your terminal session before running any scripts
- If you've run setup-service-account.sh, the deploy-local.sh script will retrieve the bucket name from Secret Manager
- If the variables are not set, the scripts will attempt to get them from gcloud config and Secret Manager

Available options:
- `--folder`: Path to the folder to process (e.g., "2025/Photos")
- `--height`: Output height for thumbnails (default: 512)
- `--no-recursive`: Process only the specified folder, not subfolders
- `--format`: Video output format, "ts" (default) or "webm" 
- `--containers`: Number of Docker containers to use for parallel processing (default: 4)
- `--reuse-container`: Reuse existing container if available
- `--keep-container`: Keep the main container running after processing

For very large folders or video files, increasing the number of containers can significantly speed up processing. Each container processes one file at a time.

## How It Works

1. **Automatic Processing**: When a file is uploaded to the bucket, the Cloud Function is triggered automatically
   - The function identifies the file type (image, video, etc.)
   - For images:
     - The file is downloaded to a temporary location
     - The image is resized to the configured height while maintaining aspect ratio and orientation
     - The image is converted to WebP format for better compression
     - The processed file is uploaded to a `THUMBS` subdirectory
   - For videos:
     - The video is streamed rather than fully downloaded to save memory
     - Video quality settings are selected based on the original file size
     - FFmpeg is used to compress the video to either MPEG-TS or WebM format
     - A WebP thumbnail is extracted from an appropriate frame
     - The compressed video is uploaded to a `COMPRESSED` subdirectory
     - The thumbnail is uploaded to a `THUMBS` subdirectory

2. **Bulk Processing**: For existing files, the bulk processing feature:
   - Recursively scans the specified folder for supported files
   - Checks if each file already has a processed version
   - Processes files that don't have processed versions
   - Uses multi-threading for efficient processing

3. **Docker Integration**:
   - The function runs in containers with FFmpeg and other dependencies
   - Multiple containers can be used for parallel processing
   - Each container processes one file at a time for optimal resource usage
   - Uses a service account for authentication
   - Can be deployed to Cloud Functions or run locally for testing
   - Streaming architecture minimizes memory usage for large files

## Troubleshooting

If you encounter authentication errors:

1. Verify the service account exists:
   ```bash
   gcloud iam service-accounts describe image-crusher-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
   ```

2. Check that the secret exists in Secret Manager:
   ```bash
   gcloud secrets describe image-crusher-sa-key
   ```

3. Verify permissions:
   ```bash
   gcloud projects get-iam-policy YOUR_PROJECT_ID \
     --flatten="bindings[].members" \
     --format='table(bindings.role)' \
     --filter="bindings.members:image-crusher-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com"
   ```

4. If needed, run the setup script again to refresh the configuration.

5. For Docker issues:
   
   Check the main container logs:
   ```bash
   docker logs image-crusher-local
   ```

   Check logs for additional containers (when using parallel processing):
   ```bash
   docker logs image-crusher-local-1
   docker logs image-crusher-local-2
   # etc.
   ```

   Check running containers:
   ```bash
   docker ps
   ```

   If containers won't start, try rebuilding the image:
   ```bash
   docker build -t image-crusher-local -f DockerFile .
   ```
   
   Remove all containers if having issues:
   ```bash
   docker stop $(docker ps -a -q --filter="name=image-crusher-local*")
   docker rm $(docker ps -a -q --filter="name=image-crusher-local*")
   ```

## License

See the LICENSE file for details.