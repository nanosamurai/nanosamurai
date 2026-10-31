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
The default stack requires a working NVIDIA container runtime. Individual
non-speech services can be started explicitly for infrastructure diagnostics,
but that is not a functional speech evaluation.

## Hugging Face model startup fails

The default Nemotron and Parakeet models need no token. They download pinned
files and stop if a checksum does not match; retry after a network failure.
The Whisper and Qwen overlays need `HF_TOKEN`. Check that it is present in
`.env`, has only the required model-read permissions, and belongs to the account
that accepted the pyannote terms. Inspect the specific container with
`docker compose logs --tail=200 <service>`.

## A speech test times out during first start

Model downloads and cold initialization can take several minutes. Follow the
service logs and retry only after initialization has completed. Increasing a
test timeout does not fix a worker that has crashed or lost Kafka membership.

## Realtime recording fails during admission

The API reserves a realtime slot before it accepts audio. Each realtime ASR
container accepts one session by default. If the `/ws/audio` handshake returns
HTTP 500, run `docker compose logs --tail=200 samuraibff`:

- `Timed out waiting for realtime admission`: a `NEMOTRON_RTSERVICE_IMAGE`,
  `RTSERVICE_IMAGE`, or `QWEN_RTSERVICE_IMAGE` override in `.env` selects an
  older image without admission support. Remove the override or select the
  default pin.
- `Realtime replica full`: another recording uses the same container. Wait
  until it finishes and retry, or add a Nemotron replica with
  `NEMOTRON_RTSERVICE_REPLICAS=2`.

## Database migration fails on a reused volume

Inspect `docker compose logs db_migrate`. Applied versions are recorded in
`nanosamurai_schema_migrations`; do not edit that table manually. If the data is
disposable, `docker compose down -v` provides a clean reset but permanently
deletes local database, recording, and model-cache volumes.

## Sessions or recordings disappeared after a restart

Earlier versions kept the database in an anonymous volume and recordings only in
LocalStack memory. Your sessions are usually still in an older anonymous volume.
Do not run `docker volume prune` yet. Follow
[Recover a database after a restart](upgrade-local-storage.md#recover-a-database-after-a-restart).
Recordings stored before LocalStack restarted cannot be recovered.

## Postgres keeps restarting after an upgrade

If `docker compose logs postgres` says that there appears to be PostgreSQL data
in `/var/lib/postgresql`, the `nanosamurai_pgdata` volume holds PostgreSQL 17
or older files. Follow
[A named volume has PostgreSQL 17 or older data](upgrade-local-storage.md#a-named-volume-has-postgresql-17-or-older-data).

## A service cannot reach S3

Check `docker compose ps --all s3 s3_init`. `s3` should be healthy and `s3_init`
should have exited with code 0. Overlays from earlier versions may still point
at `http://localstack:4566`; change them to `http://s3:7070`.

## Collecting diagnostics

Useful, non-sensitive diagnostics are `docker compose ps --all`, the failing
service's recent logs, Docker/Compose versions, operating system, and GPU model.
Remove tokens, transcript text, recording URIs, tenant identifiers, and customer
data before opening a public issue.
