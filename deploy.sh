#!/bin/bash

# Environment variables
export PROJECT_ID="personal-life-451815"
export BUCKET_NAME="schmucklemier-long-term"  # Fallback value for local testing
export SERVICE_NAME="image-crusher"
export REGION="us-central1"
export MEMORY="1024Mi" 
export CPU="1"         
export TIMEOUT="3600s"  
export SERVICE_ACCOUNT_NAME="image-crusher-sa"
export SERVICE_ACCOUNT="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
export ARTIFACT_REGISTRY="${REGION}-docker.pkg.dev"
export REPOSITORY="cloud-run"
export IMAGE_NAME="${SERVICE_NAME}"
export TRIGGER_NAME="${SERVICE_NAME}-trigger"

# Check if service account exists
if ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT" --project="$PROJECT_ID" &>/dev/null; then
  echo "Service account $SERVICE_ACCOUNT does not exist."
  echo "Please run setup-service-account.sh first."
  exit 1
fi

# Grant Cloud Run and Eventarc specific roles to the service account
echo "Granting Cloud Run and Eventarc specific roles to service account..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/eventarc.eventReceiver"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/run.invoker" 
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/secretmanager.secretAccessor"

echo "Service account roles configured for deployment"

# Enable required APIs
echo "Enabling required APIs..."
gcloud services enable run.googleapis.com --project="$PROJECT_ID"
gcloud services enable cloudbuild.googleapis.com --project="$PROJECT_ID"
gcloud services enable eventarc.googleapis.com --project="$PROJECT_ID"
gcloud services enable artifactregistry.googleapis.com --project="$PROJECT_ID"
gcloud services enable pubsub.googleapis.com --project="$PROJECT_ID"
gcloud services enable secretmanager.googleapis.com --project="$PROJECT_ID"

# Grant the Cloud Storage service account pubsub.publisher role
echo "Granting Pub/Sub publisher role to Cloud Storage service account..."
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
GCS_SERVICE_ACCOUNT="service-${PROJECT_NUMBER}@gs-project-accounts.iam.gserviceaccount.com"

# Grant the necessary role
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$GCS_SERVICE_ACCOUNT" \
  --role="roles/pubsub.publisher"

# Make sure service account has appropriate roles
echo "Ensuring service account has appropriate roles..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/storage.objectAdmin"

# Add the role needed for signing URLs
echo "Granting service account token creator role..."
gcloud iam service-accounts add-iam-policy-binding "$SERVICE_ACCOUNT" \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/iam.serviceAccountTokenCreator"

# Create Artifact Registry repository if it doesn't exist
if ! gcloud artifacts repositories describe "$REPOSITORY" --project="$PROJECT_ID" --location="$REGION" &>/dev/null; then
  echo "Creating Artifact Registry repository: $REPOSITORY"
  gcloud artifacts repositories create "$REPOSITORY" \
    --repository-format=docker \
    --location="$REGION" \
    --description="Docker repository for Cloud Run services" \
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

# Build and push the Docker image with explicit platform
docker build --platform=linux/amd64 -t "$IMAGE_URI" -f DockerFile .
docker push "$IMAGE_URI"

# Deploy the Cloud Run service
echo "Deploying Cloud Run service with bucket name: $BUCKET_SECRET"

# Deploy the Cloud Run service
gcloud run deploy "$SERVICE_NAME" \
  --image="$IMAGE_URI" \
  --region="$REGION" \
  --platform=managed \
  --service-account="$SERVICE_ACCOUNT" \
  --memory="$MEMORY" \
  --cpu="$CPU" \
  --timeout="$TIMEOUT" \
  --set-env-vars="PROJECT_ID=$PROJECT_ID,BUCKET_NAME=$BUCKET_SECRET" \
  --project="$PROJECT_ID" \
  --min-instances=0 \
  --max-instances=25 \
  --port=8080 \
  --concurrency=50 \
  --ingress=internal-and-cloud-load-balancing \
  --no-allow-unauthenticated

# Create the Eventarc trigger for Cloud Storage events
echo "Creating Eventarc trigger for Cloud Storage events..."
gcloud eventarc triggers delete "$TRIGGER_NAME" --project="$PROJECT_ID" --location="$REGION" --quiet 2>/dev/null || true

gcloud eventarc triggers create "$TRIGGER_NAME" \
  --project="$PROJECT_ID" \
  --location="$REGION" \
  --destination-run-service="$SERVICE_NAME" \
  --destination-run-region="$REGION" \
  --event-filters="type=google.cloud.storage.object.v1.finalized" \
  --event-filters="bucket=$BUCKET_SECRET" \
  --service-account="$SERVICE_ACCOUNT"

echo "Deployment completed"

# Output health check URL and information
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region="$REGION" --project="$PROJECT_ID" --format="value(status.url)")
echo "Service URL: $SERVICE_URL"
echo "Health check endpoint: $SERVICE_URL/health"
echo ""
echo "You can check the service logs with:"
echo "gcloud logging read 'resource.type=cloud_run_revision AND resource.labels.service_name=$SERVICE_NAME' --project=$PROJECT_ID --limit=10"