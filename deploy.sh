#!/bin/bash

# Environment variables
export PROJECT_ID="personal-life-451815"
export BUCKET_NAME="schmucklemier-long-term"  # Fallback value for local testing
export FUNCTION_NAME="image-crusher"
export REGION="us-central1"
export MEMORY="256MB"
export TIMEOUT="60s" 
export SERVICE_ACCOUNT="${FUNCTION_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "$SERVICE_ACCOUNT" --project="$PROJECT_ID" &>/dev/null; then
  echo "Creating service account $SERVICE_ACCOUNT"
  gcloud iam service-accounts create "$FUNCTION_NAME" \
    --display-name="Image Crusher Service Account" \
    --project="$PROJECT_ID"
  
  # Grant necessary roles
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/storage.objectAdmin"
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/secretmanager.secretAccessor"
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/eventarc.eventReceiver"
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/run.invoker" 
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/run.admin"
  
  echo "Service account created and roles assigned"
fi

# Enable required APIs
echo "Enabling required APIs..."
gcloud services enable run.googleapis.com --project="$PROJECT_ID"
gcloud services enable cloudfunctions.googleapis.com --project="$PROJECT_ID"
gcloud services enable cloudbuild.googleapis.com --project="$PROJECT_ID"
gcloud services enable eventarc.googleapis.com --project="$PROJECT_ID"
gcloud services enable artifactregistry.googleapis.com --project="$PROJECT_ID"
gcloud services enable pubsub.googleapis.com --project="$PROJECT_ID"

# Grant the Cloud Storage service account pubsub.publisher role
# This service account format: service-{PROJECT_NUMBER}@gs-project-accounts.iam.gserviceaccount.com
echo "Granting Pub/Sub publisher role to Cloud Storage service account..."
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
GCS_SERVICE_ACCOUNT="service-${PROJECT_NUMBER}@gs-project-accounts.iam.gserviceaccount.com"

# Grant the necessary role
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$GCS_SERVICE_ACCOUNT" \
  --role="roles/pubsub.publisher"

# Get bucket name from Secret Manager
echo "Retrieving bucket name from Secret Manager..."
BUCKET_SECRET=$(gcloud secrets versions access latest --project="$PROJECT_ID" --secret=image-bucket 2>/dev/null)

# If no secret is available yet, use the environment variable value
if [ -z "$BUCKET_SECRET" ]; then
  echo "Secret not found, using environment variable value."
  BUCKET_SECRET="$BUCKET_NAME"
fi

# Deploy the Cloud Function
echo "Deploying Cloud Function with bucket name: $BUCKET_SECRET"
gcloud functions deploy "$FUNCTION_NAME" \
  --gen2 \
  --region="$REGION" \
  --runtime=python311 \
  --source=. \
  --entry-point=process_image \
  --trigger-resource="$BUCKET_SECRET" \
  --trigger-event=google.cloud.storage.object.v1.finalized \
  --service-account="$SERVICE_ACCOUNT" \
  --memory="$MEMORY" \
  --timeout="$TIMEOUT" \
  --set-env-vars="PROJECT_ID=$PROJECT_ID,BUCKET_NAME=$BUCKET_SECRET" \
  --project="$PROJECT_ID" \
  --min-instances=0 \
  --max-instances=5

echo "Deployment completed"
