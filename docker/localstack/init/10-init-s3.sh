#!/usr/bin/env bash
set -euo pipefail

# Ensure enrollment bucket exists (idempotent).
# LocalStack provides the `awslocal` wrapper.
BUCKET_PRIMARY="${NANOSAMURAI_ENROLLMENT_BUCKET:-nanosamurai-enrollment}"
BUCKET_COMPAT="${XAMURAI_ENROLLMENT_BUCKET:-xamurai-enrollment}"
BUCKET_RECORDINGS="${NANOSAMURAI_RECORDINGS_BUCKET:-nanosamurai-recordings}"

awslocal s3 mb "s3://${BUCKET_PRIMARY}" 2>/dev/null || true
awslocal s3 mb "s3://${BUCKET_COMPAT}" 2>/dev/null || true
awslocal s3 mb "s3://${BUCKET_RECORDINGS}" 2>/dev/null || true

# Optional debug output
awslocal s3 ls || true
