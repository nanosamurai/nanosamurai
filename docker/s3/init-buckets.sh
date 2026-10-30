#!/bin/sh
set -eu

# Create the local buckets (idempotent). Runs in the s3_init job, which uses
# the AWS CLI with AWS_ENDPOINT_URL pointing at the local S3 service.
for bucket in \
  "${NANOSAMURAI_ENROLLMENT_BUCKET:-nanosamurai-enrollment}" \
  "${XAMURAI_ENROLLMENT_BUCKET:-xamurai-enrollment}" \
  "${NANOSAMURAI_RECORDINGS_BUCKET:-nanosamurai-recordings}"; do
  if aws s3api head-bucket --bucket "$bucket" >/dev/null 2>&1; then
    echo "Bucket exists: $bucket"
  else
    aws s3api create-bucket --bucket "$bucket" >/dev/null
    echo "Bucket created: $bucket"
  fi
done
