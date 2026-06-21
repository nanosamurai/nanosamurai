# nanosamurai (front-door / community edition)

This repository is the **front door** for the nanosamurai project.

## Purpose
- Provide a **Compose-first** “Community Edition” that is runnable end-to-end on a developer machine.
- Offer a clear, security-first evaluation path (docs + smoke tests) without exposing paid/private delivery IP.

## What must NOT be added here
- Production Kubernetes delivery IP (hardened Helm charts, env overlays, upgrade choreography).
- Infrastructure automation IP (Pulumi/Terraform foundations for AWS).
- Real customer credentials, tokens, or private endpoints.

Those belong in private repos like `nanodeploy` and `nanoplatform`.

## Naming
- Use **nanosamurai** for the overall solution.
- The voice services repo is **xamurai** (legacy name: drsynth).

## Security rules
- No secrets in git (tokens, API keys, private keys). Use `.env.example` and runtime env injection.
- Never bind services to 0.0.0.0 unless explicitly documented; prefer `127.0.0.1` for local dev.
- Default configs should be safe and not internet-exposed.

## Repo structure (recommended)
- `docker-compose.yml` (main entrypoint)
- `compose/` (compose fragments / profiles)
- `docs/` (how-to run, troubleshooting, architecture)
- `smoke-tests/` (scripts for quick verification)