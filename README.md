# nanosamurai (Community Edition)

This repository is the **front door** for the nanosamurai project.

Goal: a **Compose-first** evaluation path with security-first defaults.

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

## What this repo is / isn’t

- ✅ Compose-based runnable Community Edition
- ✅ docs + smoke tests
- ❌ no Helm charts / Kubernetes delivery IP
- ❌ no cloud infra automation (Pulumi/Terraform)

For Kubernetes deployment, see the private repos `nanodeploy` and `nanoplatform`.