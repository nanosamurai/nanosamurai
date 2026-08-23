# Evaluator getting started

This guide takes a clean machine from an empty checkout to a first browser
transcription. The supplied Docker Compose configuration is an evaluator stack:
it binds published ports to localhost, uses development credentials, and is not
a production deployment manifest.

## Choose an evaluation path

| Path | What starts | GPU required |
| --- | --- | --- |
| Default stack | UI/API, infrastructure, persistence, realtime transcription, refinement, recording, and finalization | Yes |
| Dual realtime override | Default stack with Faster-Whisper and Qwen3-ASR 0.6B/vLLM evaluated as peer realtime tracks | Yes |
| Observability override | Default stack plus Grafana, Prometheus, Tempo, Loki, Alloy, and OpenTelemetry Collector | No additional GPU |

The default stack is the complete end-to-end speech product. It does not
silently fall back to a UI/API-only deployment when GPU access is unavailable.

## Prerequisites

- Git
- Docker Desktop or Docker Engine
- Docker Compose v2
- Enough disk space for the service images and selected speech models
- For speech processing, an NVIDIA GPU available to Docker through the NVIDIA
  container runtime
- A least-privilege Hugging Face token with access to the required gated
  pyannote models

There is not yet a published minimum GPU-memory guarantee. The July 2026 release
rehearsal passed on an NVIDIA GeForce RTX 5090 Laptop GPU with 24 GB of GPU
memory. Treat that as a tested configuration, not a minimum requirement.
Model downloads and first initialization can take several minutes.

## Start the default stack

Clone the public front-door repository, then create the local environment file:

```bash
git clone https://github.com/nanosamurai/nanosamurai.git
cd nanosamurai
cp .env.example .env
```

Windows PowerShell:

```powershell
git clone https://github.com/nanosamurai/nanosamurai.git
Set-Location nanosamurai
Copy-Item .env.example .env
```

Set `HF_TOKEN` in `.env`. The token should have only the model-read permissions
needed for the selected models.

Confirm that Docker can access the intended NVIDIA GPU, then pull and start the
complete evaluator stack:

```bash
docker compose pull
docker compose up -d
docker compose ps --all
docker compose logs --tail=100 rtservice whisperx_worker recorder_worker finalizer_worker
```

Wait for model initialization to finish before treating an early timeout as a
failure. The speech containers request `gpus: all`; they will not start when
the NVIDIA runtime is unavailable.

Run the Tier 1 connectivity check described in
[Smoke tests and release rehearsal](smoke-tests.md), then continue with the
browser transcription below.

## Evaluate Qwen native streaming

The opt-in Qwen override keeps the default Faster-Whisper `rtservice` and adds
Qwen3-ASR as a second peer implementing the same `RealtimeASR` API. The BFF
fans one browser audio stream out to both tracks. Qwen is reachable only over
the internal Compose network and publishes no host port. Set
`QWEN_RTSERVICE_IMAGE` to an immutable image tag or digest, then start the stack:

```bash
docker compose -f docker-compose.yml -f docker-compose.qwen.yml pull
docker compose -f docker-compose.yml -f docker-compose.qwen.yml up -d
docker compose -f docker-compose.yml -f docker-compose.qwen.yml ps --all
```

For local xamurai development, build the Qwen and Faster realtime images in that
repository, set their image names only in your uncommitted `.env`, and use the
same command. The Qwen model is pinned by its service profile and downloads to
the separate `nanosamurai_qwen_hf_cache` volume on first start. The service
requires CUDA, supports one native stream in this validation profile, emits
cumulative replacement-safe hypotheses, and intentionally does not claim word
or segment timestamps. A Qwen failure ends only its track; Faster-Whisper may
continue.

The first two-second model chunk determines the earliest normal partial. Lower
`QWEN_STREAM_CHUNK_SECONDS` only as an experiment because it increases repeated
vLLM work. `QWEN_GPU_MEMORY_UTILIZATION` is bounded by the service and defaults
to `0.65`. No Hugging Face token is passed to the Qwen service for
the public model.

Validate both native partial delivery and request-EOF flushing through the BFF
with Tier 2's terminal-event mode:

```bash
python utilities/k8s_local_smoke_test/tier2_realtime_asr.py \
  --lang cs --stream-seconds 12 --asr-timeout 90 --require-final \
  --require-tracks faster-whisper,qwen
```

The smoke test reports event keys and latency only; it does not print the
transcript.

## Make the first browser transcription

1. Open <http://127.0.0.1:8000/live>.
2. Choose a language or leave language detection on its default.
3. Select **Microphone** as the input.
4. Open **Session settings**, select the desired realtime tracks, and choose the
   realtime, refined, and final outputs. With the Qwen override, select Faster,
   Qwen, or both; both are selected by default.
5. Choose **Record now**, grant microphone permission, and speak.
6. Compare simultaneous realtime tracks in their labelled side-by-side panels.
7. Stop the recording when finished.
8. Watch realtime hypotheses while recording. Refined events arrive
   asynchronously; the final transcript appears later in the recording detail
   after the recording and finalizer workers complete.

For deterministic validation, use the repository smoke-test audio and Tier 2-4
scripts instead of microphone input. See
[Transcription lifecycle](transcription-lifecycle.md) for the meaning of each
output.

## Add local observability

Start the evaluator stack with the observability override:

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d
```

Local endpoints:

- Grafana: <http://127.0.0.1:3001>
- Prometheus: <http://127.0.0.1:9090>
- Loki: <http://127.0.0.1:3100>
- Tempo: <http://127.0.0.1:3200>

The default Grafana evaluator credentials are `admin` / `admin`. They are
development-only credentials protected by the localhost bind and must not be
reused for a production deployment.

## Stop or reset the stack

Stop the services while preserving volumes:

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml down
```

To remove the evaluator data and model cache as well:

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml down -v
```

The `-v` form permanently deletes local transcripts, recordings, database
state, and cached models. See [Troubleshooting](troubleshooting.md) before
resetting a stack that contains anything you need.
