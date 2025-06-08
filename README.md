# Image Crusher

A Google Cloud Function that automatically processes files uploaded to a Cloud Storage bucket, creating WebP thumbnails for images and processing videos.

## Features

- Automatically processes different file types uploaded to Cloud Storage
- For images: Creates WebP thumbnails with configurable height while maintaining aspect ratio
- For videos: Extracts frames and creates WebP thumbnails (in development)
- Supports all common image formats (JPEG, PNG, GIF, BMP, TIFF, WebP)
- Stores processed files in a `THUMBS` subdirectory within the original file's directory
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

1. Run the setup script to create a service account with the necessary permissions:
   ```bash
   ./setup-service-account.sh
   ```

   This will:
   - Create a service account named `image-crusher-sa`
   - Grant it necessary permissions (storage.objectAdmin)
   - Create a key for the service account
   - Store the key in Secret Manager as `image-crusher-sa-key`

### Deployment

Once the service account is set up, deploy the function:

```bash
./deploy.sh
```

## Configuration

The default thumbnail height is set to 256 pixels. You can modify this by changing the `THUMBNAIL_HEIGHT` variable in `src/CompressionUtils.py`.

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

### Cloud Environment

In a production environment, you can use the RunBulk.py script directly:

```bash
# Set environment variables
export PROJECT_ID="personal-life-451815"
export BUCKET_NAME="schmucklemier-long-term"

# Run the bulk processing
python RunBulk.py --folder="2024/Photos"

# With additional options
python RunBulk.py --folder="2024/Photos" --height=512 --no-recursive
```

## How It Works

1. **Automatic Processing**: When a file is uploaded to the bucket, the Cloud Function is triggered automatically
   - The function identifies the file type (image, video, etc.)
   - For images:
     - The file is downloaded to a temporary location
     - The image is resized to the configured height while maintaining aspect ratio and orientation
     - The image is converted to WebP format for better compression
     - The processed file is uploaded to a `THUMBS` subdirectory
   - For videos (in development):
     - The video is streamed rather than fully downloaded
     - FFmpeg is used to extract key frames
     - A WebP thumbnail is created from the extracted frame
     - The processed file is uploaded to a `THUMBS` subdirectory

2. **Bulk Processing**: For existing files, the bulk processing feature:
   - Recursively scans the specified folder for supported files
   - Checks if each file already has a processed version
   - Processes files that don't have processed versions
   - Uses multi-threading for efficient processing

3. **Docker Integration**:
   - The function runs in a container with FFmpeg and other dependencies
   - Uses a service account for authentication
   - Can be deployed to Cloud Functions or run locally for testing

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

5. For Docker issues, check the container logs:
   ```bash
   docker logs image-crusher-local
   ```

## License

See the LICENSE file for details.