# nanosamurai contributors guide (internal)

This file contains **contributor-only** guidance for maintaining this repository.
It is intentionally **not part of the public-facing documentation**.

## Repo intent
- Keep this repo focused on **local Docker Compose** setup, docs, and smoke tests.
- Favor a fast “clone → run” evaluation path.

## Security rules (non-negotiable)
- Never commit secrets (tokens, API keys, private keys).
- Prefer `127.0.0.1` binds by default; any LAN/WAN exposure must be explicit and documented.

## Structure
- `docker-compose.yml`
- `docs/`
- `smoke-tests/`