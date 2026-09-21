# Prepare source-built models

This guide builds the service images locally.
The Nemotron, Parakeet, and Qwen worker guides use this path with their current Compose defaults.
Published images are also available for these services.

The optional worker overlays need newer API, UI, recorder, and persistence code
than the pinned base images contain. Upgrade the related services together.
The Compose image pins do not change when source code merges.

## Published images and Compose defaults

All model families have published images in [GHCR](https://github.com/orgs/nanosamurai/packages?repo_name=xamurai).
The base stack and Qwen realtime overlay select published image tags by default.
The other model overlays include build settings and default to `:local` images.
They also accept these image overrides in `.env`:

| Compose overlay | Image setting | Package under `ghcr.io/nanosamurai/` |
| --- | --- | --- |
| [`docker-compose.nemotron.yml`](../../docker-compose.nemotron.yml) | `NEMOTRON_RTSERVICE_IMAGE` | `xamurai-nemotron-rtservice` |
| [`docker-compose.parakeet.yml`](../../docker-compose.parakeet.yml) | `PARAKEET_FINALIZER_IMAGE` | `xamurai-parakeet-finalizer` |
| Same Parakeet overlay | `PARAKEET_REFINEMENT_IMAGE` | `xamurai-parakeet-refinement` |
| [`docker-compose.qwen-workers.yml`](../../docker-compose.qwen-workers.yml) | `QWEN_FINALIZER_IMAGE` | `xamurai-qwen-finalizer` |
| Same Qwen worker overlay | `QWEN_REFINEMENT_IMAGE` | `xamurai-qwen-refinement` |

Set each override to the full image reference with a published `sha-<commit>` tag.
Keep BFF, Persistor, and the base workers compatible with the selected model images.
A model image override does not update those services or the database.
The following steps show the local-build path.

## Get the source

Install Docker Buildx with support for Bake and additional build contexts.
Run these commands from the `nanosamurai` repository root:

```bash
git clone https://github.com/nanosamurai/xamurai.git ../xamurai
git clone https://github.com/nanosamurai/samuraibff.git ../samuraibff
git clone https://github.com/nanosamurai/samuraipersistor.git ../samuraipersistor
```

If a checkout already exists, use it instead. Do not overwrite local changes.
Use compatible `master` revisions that include track selection and ordered audio completion.
For default track settings, use a BFF revision that also includes default-track support.
Record the source commit IDs when you validate a deployment.
If your directories differ, adjust the build paths below.
Set `XAMURAI_SOURCE` in `.env` to the Xamurai path used by the model overlays.

## Build the base services

From the `nanosamurai` directory:

```bash
docker build -t samuraibff:local ../samuraibff
docker build -t samuraipersistor:local ../samuraipersistor
cd ../xamurai
docker buildx bake --load rtservice whisperx-worker recorder-worker finalizer-worker
cd ../nanosamurai
```

Bake uses the `local` tag by default. If you set `TAG`, use that tag below.
Set these image overrides in the ignored `.env`:

```dotenv
SAMURAIBFF_IMAGE=samuraibff:local
SAMURAIPERSISTOR_IMAGE=samuraipersistor:local
RTSERVICE_IMAGE=xamurai-rtservice:local
WHISPERX_WORKER_IMAGE=xamurai-whisperx-worker:local
RECORDER_WORKER_IMAGE=xamurai-recorder-worker:local
FINALIZER_WORKER_IMAGE=xamurai-finalizer-worker:local
COMPOSE_BIND_IP=127.0.0.1
```

Keep `HF_TOKEN` in `.env`. Do not pass it as a build argument.
If a local overlay sets `image` directly, update that setting too.
It takes precedence over the base file's image variable.

## Prepare the database

For a new installation, pull the infrastructure images:

```bash
docker compose -f docker-compose.yml pull broker kafka_init localstack postgres db_migrate db_seed
```

The normal startup command runs migrations automatically.
For an existing installation, finish active sessions first.
Back up the database and recording storage before an upgrade.
Keep the existing project name, PostgreSQL major version, volumes, and worker consumer groups.

Stop the application services with your existing Compose file list.
Keep Postgres, Kafka, and LocalStack running.
Stop any optional model workers too.
Then run the normal migration service with that same file list:

```bash
docker compose -f docker-compose.yml stop samuraibff samuraipersistor rtservice whisperx_refinement recorder_worker whisperx_finalizer
docker compose -f docker-compose.yml run --rm db_migrate
```

Include your existing overlays in these commands if they change infrastructure settings.
Do not replace an existing PostgreSQL image with the base image during an upgrade.
[Migrations 017–019](../../docker/postgres/migrations/) provide track storage; 019 requires PostgreSQL 15 or later.
They stop on duplicate recording or tagged transcript rows. Resolve conflicts without deleting transcript history before retrying.
Preserve the migration ledger. Do not edit applied SQL, reuse versions 014–016, delete volumes, or reset consumer offsets.

Older installations can have containers named `whisperx_worker` and `finalizer_worker`.
Stop those containers before you start the renamed services.
Do not run old and new workers against the same topics.

## Add your model

Continue with [Nemotron](nemotron.md), [Parakeet](parakeet.md), or [Qwen workers](qwen.md#add-refined-and-final-transcription).
Build the optional images, then use that guide's full-stack startup command.
Use `up -d --no-build --pull never` after local builds to keep the selected local images.
Check `ps --all` and the model logs before you send audio.

Source builds do not establish a minimum GPU requirement.
Each model service loads separate weights, even when services share a cache.
