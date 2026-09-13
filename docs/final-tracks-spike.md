# Final track spike

This opt-in local Compose overlay uses one real WhisperX track and a second,
explicitly synthetic test track. It does not establish a second model's quality.
The extra unselected worker proves that selection is enforced by each consumer.
The normal Compose image pins and realtime/refinement settings are unchanged.

## Run

Check out `implement-lean-final-tracks` in Xamurai, SamuraiBFF and
SamuraiPersistor. The overlay accepts `XAMURAI_SOURCE`, `BFF_SOURCE` and
`PERSISTOR_SOURCE` for source locations. Supply your existing `HF_TOKEN` through
the ignored `.env`; do not copy credentials into build arguments or images.
Keep `COMPOSE_BIND_IP=127.0.0.1`.

For an existing local stack, retain its Compose project name, infrastructure
images, volume mappings and any localhost port overrides. Do not recreate a
Postgres 16 volume with the base Compose PostgreSQL 18 image. Inspect its
migration ledger first; see [the migration notes](final-track-migration.md).
Stop any obsolete experimental worker containers consuming these same topics.
Do not enable this spike against external webhook/workflow consumers.

Run these commands from the Nanosamurai checkout, using its original
`nanosamurai` project. They keep its existing Nemotron and local image overrides; keep the local
override last so the existing final consumer group is preserved. Infrastructure
must already be running. No separate Compose project or database is needed.

```powershell
$smokeFiles = @('-p', 'nanosamurai',
  '-f', 'docker-compose.yml', '-f', 'docker-compose.nemotron.yml',
  '-f', 'docker-compose.final-tracks-smoke.yml', '-f', 'docker-compose.local-asr.yml')
docker compose @smokeFiles build samuraibff samuraipersistor finalizer_worker final-tracks-smoke
docker compose @smokeFiles --profile validation run --rm --no-deps --entrypoint python final-tracks-smoke /probe/migration.py
docker compose @smokeFiles run --rm --no-deps db_migrate
docker compose @smokeFiles up -d --no-deps --no-build samuraibff samuraipersistor recorder_worker finalizer_worker test-shadow test-unselected
docker compose @smokeFiles --profile validation run --rm --no-deps final-tracks-smoke
```

The generic smoke overlay can reuse the finalizer image for the recorder. This
checkout's local override selects its separately built recorder image instead.
The synthetic workers run the production finalizer
loop with only inference replaced by the mounted test function. No production
worker has a synthetic inference mode. Test services expose no host ports.

The smoke prints assertion names rather than transcript content. It checks:

- two separate rows and one shared recording, model labels, ordered selection
  headers and `sessions.meta`;
- invalid selections and unsafe retention rejected before audio; omitted
  selection, reconnect selection, silence and unselected worker offset advancement;
- BFF text/segments, track filtering, shared WAV bytes and range playback;
- input/output replay idempotency and preservation of the first result;
- a failing synthetic worker while WhisperX completes, then restart/replay;
- an unavailable S3 recording that is restored after a failed download, proving
  the worker retries without committing away that result;
- a temporary DB fault scoped to one newly created smoke session, removal of
  that fault in `finally`, and successful retry without advancing the failed offset;
- tenant denial for history, audio playback and audio ingestion;
- retained multi-track source audio, single-track source deletion, and absence
  of a local transcript JSON sidecar beside a WAV.

The smoke uses the repository's published audio fixture and creates new test
sessions. It leaves those sessions as evidence. Its synthetic failure marker
and session-specific DB trigger are removed in `finally`. If the test process
is forcibly killed during fault injection, inspect `/faults/fail` and the named
`lean_smoke_reject_final` trigger before restarting it. Never remove unrelated
data or reset volumes to recover a failed test.

## Boundaries and evidence

Selection settings and saved-result tabs in the browser belong to spike 3.
The API supports all final rows and preserves nested stream controls now; the existing UI still chooses one final
result. There is no durable per-track failure/status contract yet, so session
`finished` is not evidence that every selected track succeeded.

The migration copies must remain identical across the two deployment repos.
Migration 018 retires only the discarded local experiment's execution-ID check.
Removing other experimental schema is separate local maintenance, described
below. A normal master schema has no such check or experimental metadata.

Validation on 2026-09-13:

- BFF: full suite, 127 tests / 955 assertions, zero failures or errors.
- Persistor: full suite, 14 tests / 73 assertions, zero failures or errors.
- Xamurai: existing lightweight suite plus final selection coverage, 71 passed.
- SQL: duplicate preflight, legacy NULL rows, uniqueness, repeat application and
  experimental-check compatibility passed inside a rolled-back isolated schema.
- Rebuilt `samuraibff:lean-tracks`, `samuraipersistor:lean-tracks` and
  `xamurai-finalizer-worker:lean-tracks`; local Compose ran those images.
- Full Compose smoke passed every assertion above, including real WhisperX
  `medium` inference, alignment, playback, failure/restart, source-download and
  DB recovery.
- Final cleanup check found no fault marker, DB trigger or fault function.
  Every published local stack port was bound to `127.0.0.1`.

## Original nanosamurai stack

The deployment target is the existing Compose project `nanosamurai`, with
`nanosamurai-postgres-1` (Postgres 18), `nanosamurai-broker-1` and
`nanosamurai-localstack-1`. The earlier experimental
`nanosamurai-final-tracks-postgres` project is stopped and is not selected by
`.env`. The original infrastructure containers and their data volumes are reused.

The original database contained 117 transcripts, 51 recordings and migration
ledger entries 001-015. After full and experimental-table-only `pg_dump -Fc`
backups, the normal runner applied 017 and 018. Approved local cleanup archived
the 126 obsolete final/refined result-metadata rows in those backups, removed
`transcript_track_results`, and removed eight experimental columns:
`sessions.asr_meta_snapshot`, the five `recordings.source_*` metadata columns,
and `session_transcripts.result_id` / `result_event_sha256`. The cleanup used no
`CASCADE` and checked that row counts still matched the backup. All 117 original
transcripts and 51 recording records passed content-hash comparisons afterward.
`track_id` remains, and applied ledger entries 014/015 were preserved.

Only ignored local configuration selects source-built images: `.env` names
project `nanosamurai` and the existing base, Nemotron and `docker-compose.local-asr.yml`
files. BFF, Persistor, realtime, ordinary refinement, recorder and finalizer use
their `:lean-tracks` images. Existing Nemotron settings are retained. BFF is at
`http://127.0.0.1:8000`; its internal reply address is `http://samuraibff:8000`.
The finalizer continues the last active original WhisperX input group,
`final-track.whisperx.whisperx-medium-final-r1`, rather than replaying a retired
group's stale backlog. Other original consumer groups are retained. No offsets
are reset, topics deleted, or new application stack created.

Synthetic workers are used only during the smoke. After validation, stop them
and use ordinary `docker compose up -d --no-deps --no-build` for the application
services; the default configuration does not include the test overlay.

The full final-track smoke passed on this original stack. After removing the
test overlay from the running application configuration and stopping its two
synthetic workers, a normal realtime/refined/final audio session also passed.
All 117 original transcript hashes and 51 recording-record hashes still matched
after both tests. Each of the six updated service containers was checked against
its local image ID. The original refinement consumer caught up without resetting
offsets, and no injected DB failure trigger/function remained.

The original LocalStack recordings bucket was empty when its existing container
started, before the new smoke. The 51 historical DB references are preserved,
but their old audio is unavailable in that bucket. This is a storage-recovery
limitation; the new-recording smoke checks new audio and playback separately.
The backup, cleanup SQL and validation logs for the original stack are in the
ignored `.tmp/original-stack-upgrade/` directory.
