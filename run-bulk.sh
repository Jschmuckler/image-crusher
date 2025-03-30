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

# Parse command line arguments and pass through to the Python script
ARGS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --folder=*)
      ARGS="$ARGS $1"
      shift
      ;;
    --folder)
      ARGS="$ARGS --folder=\"$2\""
      shift 2
      ;;
    --height=*)
      ARGS="$ARGS $1"
      shift
      ;;
    --height)
      ARGS="$ARGS --height=$2"
      shift 2
      ;;
    --no-recursive)
      ARGS="$ARGS --no-recursive"
      shift
      ;;
    *)
      echo "Unknown option: $1"
      exit 1
      ;;
  esac
done

# Run the bulk processing script
echo "Starting bulk processing..."

# Run the Python script directly without eval to handle special characters
if [ -z "$ARGS" ]; then
  python RunBulk.py
else
  # Need to use eval with proper quoting for args with spaces
  eval "python RunBulk.py $ARGS"
fi