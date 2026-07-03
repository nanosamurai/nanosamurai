# nanosamurai

Open-source **self-hosted** speech-to-text + workflow automation stack.

This repo is the **starting point**: documentation, local (Docker Compose) setup, and smoke tests.

> Status: WIP. The Compose stack is currently a minimal skeleton while we complete the OSS rollout.

## Quickstart (local)

Prerequisites:
- Docker Desktop (or Docker Engine)

1) Copy env file:

```bash
cp .env.example .env
```

2) Start the stack:

```bash
docker compose up -d
```

3) Run smoke tests:

```bash
./smoke-tests/smoke.sh
```

## What you get
- A Compose-driven local environment (no Kubernetes required)
- Smoke tests to validate that the stack is up
- Docs for running and troubleshooting

## Roadmap (short-term)
- Replace the placeholder service with the full local stack
- Add a realistic end-to-end smoke test (API call → transcription result)
- Add an optional observability profile (Tempo/Loki/Prometheus/Grafana)

## Repositories
The nanosamurai project is split into several repositories (services + SDK + this front door). Links will be added as the rollout progresses.

## Security
- Do not commit secrets (tokens, API keys, private keys). Use `.env` (or similar) locally.
- Local defaults should bind to `127.0.0.1` unless explicitly documented.