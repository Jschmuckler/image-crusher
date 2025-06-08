#!/bin/bash

# Environment variables
export PROJECT_ID="personal-life-451815"
export IMAGE_NAME="image-crusher-local"
export PORT=8080

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

# Stop any existing container with the same name
echo "Stopping any existing containers..."
docker stop $IMAGE_NAME 2>/dev/null || true
docker rm $IMAGE_NAME 2>/dev/null || true

# Build the Docker image locally
echo "Building Docker image for local testing..."
docker build -t $IMAGE_NAME -f DockerFile .

# Service account configuration
export SERVICE_ACCOUNT_NAME="image-crusher-sa"
export SECRET_NAME="image-crusher-sa-key"

# Get service account key from Secret Manager
echo "Fetching service account key from Secret Manager..."
SA_KEY=$(gcloud secrets versions access latest --project="$PROJECT_ID" --secret="$SECRET_NAME" 2>/dev/null)

# Don't echo the service account key - it's sensitive

# Check if the secret was retrieved successfully
if [ -z "$SA_KEY" ]; then
  echo "Service account key not found in Secret Manager."
  echo "Please run setup-service-account.sh first."
  exit 1
fi

# Create a temporary file for the service account key
SA_KEY_FILE=$(mktemp)
# Make sure we're writing the key properly by using printf instead of echo
printf "%s" "$SA_KEY" > "$SA_KEY_FILE"
# Verify the key file was created correctly
if [ ! -s "$SA_KEY_FILE" ]; then
  echo "ERROR: Failed to write service account key to temporary file."
  exit 1
fi
echo "Service account key saved to temporary file."

# Run the Docker container
echo "Starting Docker container for local testing with service account..."
docker run --name $IMAGE_NAME \
  -p $PORT:$PORT \
  -e PROJECT_ID=$PROJECT_ID \
  -e BUCKET_NAME=$BUCKET_NAME \
  -e PORT=$PORT \
  -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/sa-key.json \
  -e GOOGLE_CLOUD_PROJECT=$PROJECT_ID \
  -d $IMAGE_NAME

# Inject the service account key into the container using a more direct approach
echo "Injecting service account key into container..."
docker cp "$SA_KEY_FILE" "$IMAGE_NAME:/tmp/sa-key.json"

# Set proper permissions on the key file
docker exec $IMAGE_NAME bash -c "chmod 600 /tmp/sa-key.json"

# Verify the key was properly injected
echo "Verifying service account key..."
docker exec $IMAGE_NAME bash -c "if [ -s /tmp/sa-key.json ]; then 
  echo 'Service account key file exists and is not empty'
  echo 'Checking JSON structure (sensitive values redacted):'
  grep -o '\"type\": \"[^\"]*\"' /tmp/sa-key.json || echo 'No type field found'
  grep -q '\"private_key\":' /tmp/sa-key.json && echo '\"private_key\": \"[REDACTED]\"' || echo 'No private_key field found'
  grep -o '\"client_email\": \"[^\"]*\"' /tmp/sa-key.json || echo 'No client_email field found'
else 
  echo 'ERROR: Service account key file is empty'
fi"

# Clean up the temporary file
rm "$SA_KEY_FILE"

echo "Container started with service account authentication."

echo "Local development server started."
echo "Function will be available at: http://localhost:${PORT}"
echo
echo "To test processing a single file:"
echo "python3 local-test.py --file-path='2024/J&C_Wedding/Everyone_Else/20241220_230146.jpg'"
echo
echo "To bulk process an entire folder and its subfolders:"
echo "python bulk-process.py --folder=\"2024/J&C_Wedding/Everyone_Else\""
echo
echo "Or with more options:"
echo "python bulk-process.py --folder=\"path/to/folder\" --height=512 --no-recursive --port=8080"
echo
echo "To view container logs:"
echo "docker logs -f $IMAGE_NAME"
echo
echo "To stop the container:"
echo "docker stop $IMAGE_NAME"
