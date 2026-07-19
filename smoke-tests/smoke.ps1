$ErrorActionPreference = "Stop"

$BaseUrl = if ($env:BASE_URL) { $env:BASE_URL } else { "http://127.0.0.1:8000" }
$PythonBin = if ($env:PYTHON_BIN) { $env:PYTHON_BIN } else { "python" }

Write-Host "[smoke] Running Tier 1 against $BaseUrl"
& $PythonBin utilities/k8s_local_smoke_test/tier1_bff_connectivity.py --base-url $BaseUrl

if ($env:RUN_TIER2 -eq "true") {
    $Wav = if ($env:TIER2_WAV) { $env:TIER2_WAV } else { "tests/data/test_cs.wav" }
    $Lang = if ($env:TIER2_LANG) { $env:TIER2_LANG } else { "cs" }
    Write-Host "[smoke] Running Tier 2 against $BaseUrl"
    & $PythonBin utilities/k8s_local_smoke_test/tier2_realtime_asr.py --base-url $BaseUrl --wav $Wav --lang $Lang
}

$KafkaBootstrap = if ($env:KAFKA_BOOTSTRAP) { $env:KAFKA_BOOTSTRAP } else { "127.0.0.1:9092" }

if ($env:RUN_TIER3 -eq "true") {
    $Wav = if ($env:TIER3_WAV) { $env:TIER3_WAV } else { "tests/data/test_cs.wav" }
    $Lang = if ($env:TIER3_LANG) { $env:TIER3_LANG } else { "cs" }
    Write-Host "[smoke] Running Tier 3 against $BaseUrl and Kafka $KafkaBootstrap"
    & $PythonBin utilities/k8s_local_smoke_test/tier3_kafka_audio_raw.py --base-url $BaseUrl --kafka-bootstrap $KafkaBootstrap --wav $Wav --lang $Lang
}

if ($env:RUN_TIER4 -eq "true") {
    $Wav = if ($env:TIER4_WAV) { $env:TIER4_WAV } else { "tests/data/test_cs.wav" }
    $Lang = if ($env:TIER4_LANG) { $env:TIER4_LANG } else { "cs" }
    $Signal = if ($env:TIER4_SIGNAL) { $env:TIER4_SIGNAL } else { "recording-finished" }
    $Timeout = if ($env:TIER4_TIMEOUT) { $env:TIER4_TIMEOUT } else { "180" }
    Write-Host "[smoke] Running Tier 4 signal=$Signal against $BaseUrl and Kafka $KafkaBootstrap"
    & $PythonBin utilities/k8s_local_smoke_test/tier4_async_pipeline.py --base-url $BaseUrl --kafka-bootstrap $KafkaBootstrap --wav $Wav --lang $Lang --signal $Signal --timeout $Timeout
}

if ($env:TRACE_SESSION_ID) {
    Write-Host "[smoke] Auditing Kafka trace propagation for $env:TRACE_SESSION_ID"
    & $PythonBin utilities/k8s_local_smoke_test/kafka_traceparent_audit.py --kafka-bootstrap $KafkaBootstrap --session-id $env:TRACE_SESSION_ID
}
