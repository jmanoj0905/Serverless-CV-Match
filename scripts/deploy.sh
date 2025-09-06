#!/usr/bin/env bash
set -euo pipefail

STACK_NAME="resume-match"
REGION="ap-south-1"
BUCKET="resume-match-jmanoj0905-ap-south-1"

#Build & deploy the SAM stack
sam build
sam deploy \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}" \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides BucketName="${BUCKET}"

#Load Identity Pool ID from .env
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  source .env
fi
IDENTITY_POOL_ID="${IDENTITY_POOL_ID:-ap-south-1:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx}"

#Inject Identity Pool ID into a temp HTML before upload
TMP_HTML="$(mktemp)"
sed "s|ap-south-1:xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx|${IDENTITY_POOL_ID}|" \
  site/upload.html > "${TMP_HTML}"

#Upload static page & dataset
aws s3 cp "${TMP_HTML}" "s3://${BUCKET}/upload.html" \
  --region "${REGION}" \
  --content-type "text/html"

aws s3 cp "data/jobs.json" "s3://${BUCKET}/jobs/jobs.json" \
  --region "${REGION}"

#Apply CORS (since it's not baked into the template)
aws s3api put-bucket-cors \
  --bucket "${BUCKET}" \
  --cors-configuration file://policies/s3-cors.xml \
  --region "${REGION}"

#Ensure website hosting
aws s3 website "s3://${BUCKET}/" --index-document upload.html

# Cleanup temp file
rm -f "${TMP_HTML}"

echo "--------------------------------------------------------------------"
echo "Open:"
echo "  http://${BUCKET}.s3-website-${REGION}.amazonaws.com"
echo "--------------------------------------------------------------------"
