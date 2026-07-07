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
