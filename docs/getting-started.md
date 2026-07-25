# Evaluator getting started

This guide takes a clean machine from an empty checkout to a first browser
transcription. The supplied Docker Compose configuration is an evaluator stack:
it binds published ports to localhost, uses development credentials, and is not
a production deployment manifest.

## Choose an evaluation path

| Path | What starts | GPU required |
| --- | --- | --- |
| Base stack | UI/API, Kafka, PostgreSQL, LocalStack, migrations, and persistence | No |
| Speech profile | Base stack plus realtime, refinement, recording, and finalization workers | Yes |
| Observability override | Optional Grafana, Prometheus, Tempo, Loki, Alloy, and OpenTelemetry Collector | No additional GPU |

The base stack is useful for checking service startup and the HTTP surface, but
it cannot transcribe audio. Use the speech profile for an end-to-end evaluation.

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

## Start the base stack

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

Pull the pinned images and start the base services:

```bash
docker compose pull
docker compose up -d
docker compose ps --all
```

Open <http://127.0.0.1:8000>. Run the Tier 1 connectivity check described in
[Smoke tests and release rehearsal](smoke-tests.md) before starting the GPU
workers.

## Start speech processing

Set `HF_TOKEN` in `.env`. The token should have only the model-read permissions
needed for the selected models.

Confirm that Docker can access the intended NVIDIA GPU, then start the speech
profile:

```bash
docker compose --profile speech up -d
docker compose ps --all
docker compose logs --tail=100 rtservice whisperx_worker recorder_worker finalizer_worker
```

Wait for model initialization to finish before treating an early timeout as a
failure. The speech containers request `gpus: all`; they will not start when the
NVIDIA runtime is unavailable.

## Make the first browser transcription

1. Open <http://127.0.0.1:8000/live>.
2. Choose a language or leave language detection on its default.
3. Select **Microphone** as the input.
4. Select the desired realtime, refined, and final outputs.
5. Choose **Record now**, grant microphone permission, and speak.
6. Stop the recording when finished.
7. Watch realtime hypotheses while recording. Refined events arrive
   asynchronously; the final transcript appears later in the recording detail
   after the recording and finalizer workers complete.

For deterministic validation, use the repository smoke-test audio and Tier 2-4
scripts instead of microphone input.

## Add local observability

Start the evaluator stack with the observability override:

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml --profile speech up -d
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
docker compose -f docker-compose.yml -f docker-compose.observability.yml --profile speech down
```

To remove the evaluator data and model cache as well:

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml --profile speech down -v
```

The `-v` form permanently deletes local transcripts, recordings, database
state, and cached models. See [Troubleshooting](troubleshooting.md) before
resetting a stack that contains anything you need.
