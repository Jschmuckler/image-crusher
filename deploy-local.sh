#!/bin/bash

# Check if Python virtual environment exists, create if not
if [ ! -d "venv" ]; then
  echo "Creating Python virtual environment..."
  python -m venv venv
  echo "Virtual environment created"
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Export environment variables
export PROJECT_ID="personal-life-451815"

# Get the bucket name from Secret Manager
echo "Fetching bucket name from Secret Manager..."
BUCKET_VALUE=$(gcloud secrets versions access latest --project=$PROJECT_ID --secret=image-bucket 2>/dev/null)

# If secret access fails, use default fallback
if [ -z "$BUCKET_VALUE" ]; then
  echo "Could not access secret. Using default bucket name for local testing."
  export BUCKET_NAME="schmucklemier-long-term"
else
  echo "Successfully retrieved bucket name from Secret Manager."
  export BUCKET_NAME="$BUCKET_VALUE"
fi

# For local testing, we'll use port 8080
export PORT=8080

echo "Starting local development server..."
echo "Function will be available at: http://localhost:${PORT}"
echo
echo "To test processing a single file:"
echo "python local-test.py --file-path=\"2024/J&C_Wedding/Everyone_Else/20241220_230146.jpg\""
echo
echo "To bulk process an entire folder and its subfolders:"
echo "python bulk-process.py --folder=\"2024/J&C_Wedding/Everyone_Else\""
echo
echo "Or with more options:"
echo "python bulk-process.py --folder=\"path/to/folder\" --height=512 --no-recursive --port=8080"
echo

# Start the Functions Framework server
functions-framework --target=process_image --debug
