#!/bin/bash

# Environment variables
export PROJECT_ID="personal-life-451815"
export BUCKET_NAME="schmucklemier-long-term"  # Fallback value for local testing
export FUNCTION_NAME="image-crusher"
export REGION="us-central1"
export MEMORY="512MB"  # Increased memory for ffmpeg processing
export TIMEOUT="240s"  # Increased timeout for video processing
export SERVICE_ACCOUNT_NAME="image-crusher-sa"
export SERVICE_ACCOUNT="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
export ARTIFACT_REGISTRY="${REGION}-docker.pkg.dev"
export REPOSITORY="cloud-functions"
export IMAGE_NAME="${FUNCTION_NAME}"

# Check if service account exists
if ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT" --project="$PROJECT_ID" &>/dev/null; then
  echo "Service account $SERVICE_ACCOUNT does not exist."
  echo "Please run setup-service-account.sh first."
  exit 1
fi

# Grant Cloud Function specific roles to the service account
echo "Granting Cloud Function specific roles to service account..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/eventarc.eventReceiver"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/run.invoker" 

echo "Service account roles configured for deployment"

# Enable required APIs
echo "Enabling required APIs..."
gcloud services enable run.googleapis.com --project="$PROJECT_ID"
gcloud services enable cloudfunctions.googleapis.com --project="$PROJECT_ID"
gcloud services enable cloudbuild.googleapis.com --project="$PROJECT_ID"
gcloud services enable eventarc.googleapis.com --project="$PROJECT_ID"
gcloud services enable artifactregistry.googleapis.com --project="$PROJECT_ID"
gcloud services enable pubsub.googleapis.com --project="$PROJECT_ID"

# Grant the Cloud Storage service account pubsub.publisher role
echo "Granting Pub/Sub publisher role to Cloud Storage service account..."
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
GCS_SERVICE_ACCOUNT="service-${PROJECT_NUMBER}@gs-project-accounts.iam.gserviceaccount.com"

# Grant the necessary role
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$GCS_SERVICE_ACCOUNT" \
  --role="roles/pubsub.publisher"

# Create Artifact Registry repository if it doesn't exist
if ! gcloud artifacts repositories describe "$REPOSITORY" --project="$PROJECT_ID" --location="$REGION" &>/dev/null; then
  echo "Creating Artifact Registry repository: $REPOSITORY"
  gcloud artifacts repositories create "$REPOSITORY" \
    --repository-format=docker \
    --location="$REGION" \
    --description="Docker repository for Cloud Functions" \
    --project="$PROJECT_ID"
fi

# Get bucket name from Secret Manager
echo "Retrieving bucket name from Secret Manager..."
BUCKET_SECRET=$(gcloud secrets versions access latest --project="$PROJECT_ID" --secret=image-bucket 2>/dev/null)

# If no secret is available yet, use the environment variable value
if [ -z "$BUCKET_SECRET" ]; then
  echo "Secret not found, using environment variable value."
  BUCKET_SECRET="$BUCKET_NAME"
fi

# Build and push the Docker image
echo "Building and pushing Docker image..."
IMAGE_URI="${ARTIFACT_REGISTRY}/${PROJECT_ID}/${REPOSITORY}/${IMAGE_NAME}:latest"

# Configure Docker to use Google Cloud credentials
gcloud auth configure-docker ${REGION}-docker.pkg.dev --quiet

# Build and push the Docker image
docker build -t "$IMAGE_URI" -f DockerFile .
docker push "$IMAGE_URI"

# Deploy the Cloud Function with the Docker image
echo "Deploying Cloud Function with bucket name: $BUCKET_SECRET"
gcloud functions deploy "$FUNCTION_NAME" \
  --gen2 \
  --region="$REGION" \
  --runtime=python311 \
  --trigger-resource="$BUCKET_SECRET" \
  --trigger-event=google.cloud.storage.object.v1.finalized \
  --service-account="$SERVICE_ACCOUNT" \
  --memory="$MEMORY" \
  --timeout="$TIMEOUT" \
  --set-env-vars="PROJECT_ID=$PROJECT_ID,BUCKET_NAME=$BUCKET_SECRET" \
  --project="$PROJECT_ID" \
  --docker-registry=artifact-registry \
  --image="$IMAGE_URI" \
  --min-instances=0 \
  --max-instances=5

echo "Deployment completed"
