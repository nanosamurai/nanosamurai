#!/usr/bin/env sh
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
PYTHON_BIN="${PYTHON_BIN:-python}"

echo "[smoke] Running Tier 1 against ${BASE_URL}"
"${PYTHON_BIN}" utilities/k8s_local_smoke_test/tier1_bff_connectivity.py --base-url "${BASE_URL}"

if [ "${RUN_TIER2:-false}" = "true" ]; then
  echo "[smoke] Running Tier 2 against ${BASE_URL}"
  "${PYTHON_BIN}" utilities/k8s_local_smoke_test/tier2_realtime_asr.py \
    --base-url "${BASE_URL}" \
    --wav "${TIER2_WAV:-tests/data/test_cs.wav}" \
    --lang "${TIER2_LANG:-cs}"
fi
