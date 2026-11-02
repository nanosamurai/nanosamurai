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

## Database is empty after an upgrade or `down`

PostgreSQL 18 keeps its data in `/var/lib/postgresql/18/docker`. Older versions
of `docker-compose.yml` mounted the named volume `nanosamurai_pgdata` one level
too deep, at `/var/lib/postgresql/data`. The database then lived in an anonymous
volume. It survived `restart`, `stop` and `start`, and `up -d`, but
`docker compose down` followed by `up` started with an empty database. The old
data stays on disk in a dangling volume.

The current file mounts the named volume at `/var/lib/postgresql`. Existing
installs must copy their database into it once.

### Move the database before you upgrade

Run this with the old files still checked out, and with the same file list
that started the stack (here only `docker-compose.yml`).

Bash (in Git Bash on Windows, run `export MSYS_NO_PATHCONV=1` first):

```bash
docker compose -f docker-compose.yml stop
pg=$(docker compose -f docker-compose.yml ps -a -q postgres)
old=$(docker inspect "$pg" --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql"}}{{.Name}}{{end}}{{end}}')
new="$(docker inspect "$pg" --format '{{index .Config.Labels "com.docker.compose.project"}}')_nanosamurai_pgdata"
echo "copy $old -> $new"
docker run --rm -v "$old":/from:ro -v "$new":/to alpine:3.20 sh -c 'test ! -e /to/18 && cp -a /from/18 /to/'
```

PowerShell:

```powershell
docker compose -f docker-compose.yml stop
$pg = docker compose -f docker-compose.yml ps -a -q postgres
$info = docker inspect $pg | ConvertFrom-Json
$old = ($info.Mounts | Where-Object Destination -eq '/var/lib/postgresql').Name
$new = $info.Config.Labels.'com.docker.compose.project' + '_nanosamurai_pgdata'
"copy $old -> $new"
docker run --rm -v "${old}:/from:ro" -v "${new}:/to" alpine:3.20 sh -c 'test ! -e /to/18 && cp -a /from/18 /to/'
```

If `old` is empty, the stack already uses the named volume and needs no copy.
If the copy command fails, the named volume already holds a database; do not
overwrite it, and check which one has your data first.

Then update the files and repeat your `up -d` command. The old anonymous volume
is no longer used. Remove it with `docker volume rm` once you have checked your
sessions.

### Recover a database after `down`

If you already ran `down` and `up`, or started the new version without the
copy, the previous database is in a dangling volume. List the candidates:

```bash
for v in $(docker volume ls -q -f dangling=true); do
  docker run --rm -v "$v":/v:ro alpine:3.20 sh -c "test -f /v/18/docker/PG_VERSION && echo $v \$(du -sh /v | cut -f1)"
done
```

Pick the volume with your data; `docker volume inspect` shows when each one
was created. Stop the stack, keep the current database aside, and copy the old
one in:

```bash
docker compose -f docker-compose.yml stop
docker run --rm -v <old volume>:/from:ro -v nanosamurai_nanosamurai_pgdata:/to alpine:3.20 \
  sh -c 'mv /to/18 /to/18.before-restore && cp -a /from/18 /to/'
```

Replace `nanosamurai_nanosamurai_pgdata` if your Compose project has another
name. Repeat your `up -d` command; `db_migrate` applies any newer migrations.

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
