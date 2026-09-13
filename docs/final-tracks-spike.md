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

The following commands assume the existing base infrastructure is running:

```bash
docker compose -f docker-compose.yml -f docker-compose.final-tracks-smoke.yml \
  build samuraibff samuraipersistor finalizer_worker final-tracks-smoke

docker compose -f docker-compose.yml -f docker-compose.final-tracks-smoke.yml \
  --profile validation run --rm --no-deps --entrypoint python \
  final-tracks-smoke /probe/migration.py

docker compose -f docker-compose.yml -f docker-compose.final-tracks-smoke.yml \
  run --rm --no-deps db_migrate

docker compose -f docker-compose.yml -f docker-compose.final-tracks-smoke.yml \
  up -d --no-deps --no-build samuraibff samuraipersistor recorder_worker \
  finalizer_worker test-shadow test-unselected

docker compose -f docker-compose.yml -f docker-compose.final-tracks-smoke.yml \
  --profile validation run --rm --no-deps final-tracks-smoke
```

The recorder reuses the source-built finalizer image, which already includes
the production recorder code. The synthetic workers run the production finalizer
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
Migration 018 retires only the discarded local experiment's execution-ID check;
the old columns and history remain. A normal master schema has no such check.

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

The retained database has the obsolete experimental constraint described above.
Automatic approval review rejected removing it without explicit confirmation.
Migration 017 is applied there; 018 is pending approval. Its 49 historical
transcript rows and the old constraint remain intact.

To complete validation without changing that constraint, this run used a new
`nanosamurai_lean_validation` database on the same local Postgres service, seeded
from master migrations 001-013 plus 017/018 (018 is a no-op on a clean schema).
BFF, Persistor and the probe used that database; Persistor used separate
`samuraipersistor-final-validation` and `samuraipersistor-refined-validation`
consumer groups. The probe's `PERSISTOR_GROUP` matched the final group. Existing
Kafka topics, infrastructure volumes, source audio and retained DB were preserved.
The local application remains pointed at the validation database. Upgrading the
retained database and returning the application to it is the remaining operator
step after approval; do not interpret the fresh-database pass as a retained-data
upgrade pass.
