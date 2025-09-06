#!/usr/bin/env bash
set -euo pipefail

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  source .env
fi

STACK_NAME="resume-match"
REGION="ap-south-1"
BUCKET="resume-match-jmanoj0905-ap-south-1"

echo "==> Emptying S3 bucket: s3://${BUCKET}"
aws s3 rm "s3://${BUCKET}" --recursive --region "${REGION}" || true

echo "==> Deleting CloudFormation stack: ${STACK_NAME} (region: ${REGION})"
aws cloudformation delete-stack \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}"

echo "==> Waiting for stack deletion to complete..."
aws cloudformation wait stack-delete-complete \
  --stack-name "${STACK_NAME}" \
  --region "${REGION}"

echo "Done. Stack deleted."
