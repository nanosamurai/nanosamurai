#!/usr/bin/env sh
set -eu

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

KAFKA_BOOTSTRAP="${KAFKA_BOOTSTRAP:-127.0.0.1:9092}"

if [ "${RUN_TIER3:-false}" = "true" ]; then
  echo "[smoke] Running Tier 3 against ${BASE_URL} and Kafka ${KAFKA_BOOTSTRAP}"
  "${PYTHON_BIN}" utilities/k8s_local_smoke_test/tier3_kafka_audio_raw.py \
    --base-url "${BASE_URL}" \
    --kafka-bootstrap "${KAFKA_BOOTSTRAP}" \
    --wav "${TIER3_WAV:-tests/data/test_cs.wav}" \
    --lang "${TIER3_LANG:-cs}"
fi

if [ "${RUN_TIER4:-false}" = "true" ]; then
  echo "[smoke] Running Tier 4 signal=${TIER4_SIGNAL:-recording-finished} against ${BASE_URL} and Kafka ${KAFKA_BOOTSTRAP}"
  "${PYTHON_BIN}" utilities/k8s_local_smoke_test/tier4_async_pipeline.py \
    --base-url "${BASE_URL}" \
    --kafka-bootstrap "${KAFKA_BOOTSTRAP}" \
    --wav "${TIER4_WAV:-tests/data/test_cs.wav}" \
    --lang "${TIER4_LANG:-cs}" \
    --signal "${TIER4_SIGNAL:-recording-finished}" \
    --timeout "${TIER4_TIMEOUT:-180}"
fi

if [ -n "${TRACE_SESSION_ID:-}" ]; then
  echo "[smoke] Auditing Kafka trace propagation for ${TRACE_SESSION_ID}"
  "${PYTHON_BIN}" utilities/k8s_local_smoke_test/kafka_traceparent_audit.py \
    --kafka-bootstrap "${KAFKA_BOOTSTRAP}" \
    --session-id "${TRACE_SESSION_ID}"
fi
