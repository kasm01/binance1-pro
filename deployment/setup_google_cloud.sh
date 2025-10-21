#!/bin/bash
# deployment/setup_google_cloud.sh
# Google Cloud ortamını hazırlamak için script

# GCP proje ayarları
PROJECT_ID="your-gcp-project-id"
REGION="us-central1"
IMAGE_NAME="binance1-pro-bot"

# Docker image build ve push
gcloud builds submit --tag gcr.io/$PROJECT_ID/$IMAGE_NAME

# Cloud Run servisi deploy
gcloud run deploy $IMAGE_NAME \
  --image gcr.io/$PROJECT_ID/$IMAGE_NAME \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated
