#!/bin/sh
set -eu
awslocal s3api create-bucket --bucket recordings
