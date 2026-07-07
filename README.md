# nanosamurai

Open-source **self-hosted** speech-to-text and workflow automation stack.

This is the public front-door repo for running the Community Edition locally
with Docker Compose. Service images are pulled from `ghcr.io/nanosamurai/*`
and pinned by SHA by default.

## Quickstart

Prerequisites:

- Docker Desktop or Docker Engine
- GHCR access if the packages are still private

```bash
cp .env.example .env
docker compose up -d
```

Open the UI at http://127.0.0.1:8000.

Run the basic smoke test:

```bash
python -m venv .venv-smoke
. .venv-smoke/bin/activate
python -m pip install -r utilities/k8s_local_smoke_test/requirements.txt
python utilities/k8s_local_smoke_test/tier1_bff_connectivity.py --base-url http://127.0.0.1:8000
```

Windows PowerShell:

```powershell
py -m venv .venv-smoke
.\.venv-smoke\Scripts\python -m pip install -r utilities\k8s_local_smoke_test\requirements.txt
.\.venv-smoke\Scripts\python utilities\k8s_local_smoke_test\tier1_bff_connectivity.py --base-url http://127.0.0.1:8000
```

## Speech Services

Speech services need `HF_TOKEN` for model downloads. The token should have only
the minimum model-read permissions required by HuggingFace/pyannote.

Set `HF_TOKEN` in `.env`, then start the speech profile:

```bash
docker compose --profile speech up -d
```

Run the realtime ASR smoke test after `rtservice` finishes cold-starting:

```bash
python utilities/k8s_local_smoke_test/tier2_realtime_asr.py --base-url http://127.0.0.1:8000 --wav tests/data/test_cs.wav --lang cs
```

The speech containers request `gpus: all`. If Docker GPU support is not
available, remove or override those entries for CPU-only testing.

## Observability

The observability stack is optional and separated into an override file:

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml --profile speech up -d
```

Local endpoints:

- Grafana: http://127.0.0.1:3001 (`admin` / `admin`)
- Prometheus: http://127.0.0.1:9090
- Loki: http://127.0.0.1:3100
- Tempo: http://127.0.0.1:3200

The override downloads the OpenTelemetry Java agent into a Docker volume on
first start. Use the base Compose file alone for an offline/no-observability
run.

## Security

- Published ports bind to `127.0.0.1` by default through `COMPOSE_BIND_IP`.
- Do not set `COMPOSE_BIND_IP=0.0.0.0` unless you intentionally want LAN
  exposure and have firewall controls in place.
- Do not commit `.env`, tokens, recordings, transcripts, or customer data.
- LocalStack credentials in Compose are test-only values.

## Image Tags

The current default is immutable SHA tags. Future release options include:

- semantic version tags for stable releases
- `edge` tags for latest successful `master`
- signed release tags with provenance once the public release process is ready
