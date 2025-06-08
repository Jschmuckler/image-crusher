#!/bin/bash

# Environment variables
export PROJECT_ID="personal-life-451815"
export SERVICE_ACCOUNT_NAME="image-crusher-sa"
export SERVICE_ACCOUNT_DISPLAY_NAME="Image Crusher Service Account"
export SECRET_NAME="image-crusher-sa-key"

# Check if service account already exists
if gcloud iam service-accounts describe "$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com" --project="$PROJECT_ID" &>/dev/null; then
  echo "Service account $SERVICE_ACCOUNT_NAME already exists."
else
  # Create service account
  echo "Creating service account $SERVICE_ACCOUNT_NAME..."
  gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
    --display-name="$SERVICE_ACCOUNT_DISPLAY_NAME" \
    --project="$PROJECT_ID"
  
  echo "Service account created."
fi

# Grant necessary permissions
echo "Granting permissions to service account..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# Check if secret already exists
if gcloud secrets describe "$SECRET_NAME" --project="$PROJECT_ID" &>/dev/null; then
  echo "Secret $SECRET_NAME already exists."
  echo "Skipping key creation."
else
  # Create and download the key
  echo "Creating service account key..."
  gcloud iam service-accounts keys create key.json \
    --iam-account="$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com"

  # Upload to Secret Manager
  echo "Uploading key to Secret Manager..."
  gcloud secrets create "$SECRET_NAME" \
    --data-file=key.json \
    --project="$PROJECT_ID"
  
  # Clean up local copy
  rm key.json
  
  echo "Service account key created and stored in Secret Manager."
fi

# Grant permission to access the secret
echo "Granting permission to access the secret..."
gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --member="serviceAccount:$SERVICE_ACCOUNT_NAME@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" \
  --project="$PROJECT_ID"

echo "Setup complete. Service account is ready to use."