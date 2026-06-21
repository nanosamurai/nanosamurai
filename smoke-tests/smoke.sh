#!/usr/bin/env sh
set -euo pipefail

echo "[smoke] Checking docker compose services..."
docker compose ps

echo "[smoke] OK"