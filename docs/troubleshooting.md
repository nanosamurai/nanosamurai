# Troubleshooting

## GHCR reports unauthorized or denied

Ordinary users should be able to pull released images anonymously. Confirm the
package visibility in the GitHub organization. Maintainers testing a package
before publication may run `docker login ghcr.io` with a token limited to
`read:packages`; do not place the token in `.env` or shell history.

## A localhost port is already in use

Use `docker compose ps --all` to find the affected service and stop the
conflicting local process. Keep `COMPOSE_BIND_IP=127.0.0.1`; changing it to
`0.0.0.0` is not a safe workaround.

## Speech containers cannot access a GPU

First confirm that an NVIDIA CUDA test container can run with `--gpus all`.
The base stack can still be evaluated with Tier 1, but the supplied speech
profile requires a working NVIDIA container runtime.

## Hugging Face model startup fails

Check that `HF_TOKEN` is present in `.env`, has only the required model-read
permissions, and has accepted any applicable gated-model terms. Inspect the
specific container with `docker compose logs --tail=200 <service>`.

## A speech test times out during first start

Model downloads and cold initialization can take several minutes. Follow the
service logs and retry only after initialization has completed. Increasing a
test timeout does not fix a worker that has crashed or lost Kafka membership.

## Database migration fails on a reused volume

Inspect `docker compose logs db_migrate`. Applied versions are recorded in
`nanosamurai_schema_migrations`; do not edit that table manually. If the data is
disposable, `docker compose down -v` provides a clean reset but permanently
deletes local database, recording, and model-cache volumes.

## Collecting diagnostics

Useful, non-sensitive diagnostics are `docker compose ps --all`, the failing
service's recent logs, Docker/Compose versions, operating system, and GPU model.
Remove tokens, transcript text, recording URIs, tenant identifiers, and customer
data before opening a public issue.
