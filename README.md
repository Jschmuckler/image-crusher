# Image Crusher

A Google Cloud Function that automatically creates WebP thumbnails for images uploaded to a Cloud Storage bucket.

## Features

- Automatically creates WebP thumbnails for newly uploaded images
- Maintains aspect ratio while resizing to a configurable height
- Supports all common image formats (JPEG, PNG, GIF, BMP, TIFF, WebP)
- Stores thumbnails in a `THUMBS` subdirectory within the original image's directory
- Includes bulk processing functionality to generate thumbnails for existing images

## Setup

1. Make sure you have the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed
2. Clone this repository
3. Run `chmod +x deploy.sh` to make the deployment script executable
4. Run `./deploy.sh` to deploy the function

## Configuration

The default thumbnail height is set to 256 pixels. You can modify this by changing the `THUMBNAIL_HEIGHT` variable in `src/CompressionUtils.py`.

## Bulk Processing

To generate thumbnails for existing images in the bucket, you can use the bulk processing feature. There are two ways to do this:

### Local Development

When testing locally, start the function with:

```bash
./deploy-local.sh
```

Then in another terminal, use the bulk-process.py script:

```bash
# Process an entire folder and its subfolders
python bulk-process.py --folder="2024/Photos"

# Process a specific folder without recursing into subfolders
python bulk-process.py --folder="2024/Photos" --no-recursive

# Override the thumbnail height
python bulk-process.py --folder="2024/Photos" --height=512

# Run interactively (will prompt for folder)
python bulk-process.py
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

1. **Automatic Processing**: When a new image is uploaded to the bucket, the Cloud Function is triggered automatically
   - The function downloads the image to a temporary location
   - The image is resized to the configured height while maintaining aspect ratio and orientation
   - The image is converted to WebP format for better compression
   - The thumbnail is uploaded to a `THUMBS` subdirectory with the same base name (but with .webp extension)

2. **Bulk Processing**: For existing images, the bulk processing feature:
   - Recursively scans the specified folder for images
   - Checks if each image already has a thumbnail
   - Processes images that don't have thumbnails
   - Uses multi-threading for efficient processing

## License

See the LICENSE file for details.