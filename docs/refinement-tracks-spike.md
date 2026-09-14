# Refinement track spike

Spike 2 runs on `implement-lean-refinement-tracks`, branched from the unmerged
`implement-lean-final-tracks` in all five repositories. It adds refinement
identity/selection to the existing worker, Kafka topics and transcript table.
Browser selection and result tabs remain spike 3.

## Run on the original local stack

Use the original `nanosamurai` Compose project, database and volumes. Retain
existing localhost port, image and Nemotron overrides, and keep model credentials
in the ignored `.env`. `COMPOSE_BIND_IP` must be `127.0.0.1`. Do not enable this
spike against external workflow/webhook consumers.

From Nanosamurai, after inspecting the migration ledger and backing up Postgres:

```powershell
$files = @('-p', 'nanosamurai',
  '-f', 'docker-compose.yml', '-f', 'docker-compose.nemotron.yml',
  '-f', 'docker-compose.refinement-tracks-smoke.yml', '-f', 'docker-compose.local-asr.yml')
docker compose @files build samuraibff samuraipersistor whisperx_worker
docker compose @files --profile validation build refinement-tracks-smoke
docker compose @files --profile validation run --rm --no-deps --entrypoint python refinement-tracks-smoke /probe/refinement/migration.py
docker compose @files run --rm --no-deps db_migrate
docker compose @files up -d --no-deps --no-build samuraibff samuraipersistor whisperx_worker
docker compose @files --profile validation run --rm --no-deps refinement-tracks-smoke
```

The local override is machine-specific and ignored. Source paths use the same
`XAMURAI_SOURCE`, `BFF_SOURCE` and `PERSISTOR_SOURCE` overrides as spike 1.
The real worker retains the original `whisperx-async` consumer group; no offsets
are reset. The test probe launches synthetic workers as separate processes with
one group per track, including replicas sharing the same group. Only inference
is substituted. Those processes expose no ports and stop when the probe exits;
there is no Docker socket mounted into the probe or production synthetic mode.

After qualification, run ordinary `docker compose up -d --no-deps --no-build
samuraibff samuraipersistor whisperx_worker` with the original local Compose
configuration to remove the test-only BFF allowlist and restore the normal idle
timeout. Keep the source-built image overrides. Infrastructure is reused.

## Database and compatibility

Migration 019 adds a partial unique index on the existing refined row's
`tenant_id`, `session_id`, `track_id`, `window_length`, `segment_start_s` and
`segment_end_s`. It uses PostgreSQL 15+ `NULLS NOT DISTINCT` for legacy events
without window length. Existing NULL track rows remain unchanged. New untagged
events default to WhisperX; tagged replay keeps the first text, segments and
model. No transcript JSON shape changes, recording changes or new tables occur.

The SQL locks the table briefly and aborts on duplicate tagged windows. Inspect
and reconcile conflicts without deleting history before retrying. Never edit
an applied migration or reset volumes. Nanosamurai and Nanodeploy remain the
deployment migration owners; Persistor's historical Migratus files are not used.
Keep the Nanosamurai Docker SQL and Nanodeploy Docker/chart SQL byte-identical.
The duplication can drift, as can their different migration runners; compare
hashes and runner wiring when promoting these changes. Helm execution and cloud
deployment remain out of scope.

## Replay behavior and remaining gap

A worker buffers audio separately for each tenant/session and filters its track
on every input. All selected tracks publish directly to `transcripts.refined`.
Bounds are derived from cumulative audio sample counts, including short tails,
while model segments retain session-relative times. Kafka publication must be
acknowledged before work is considered complete. Persistor retries failed writes
before advancing, and verifies that event and session tenants match.

The worker retains the first Kafka offset of each active session until all its
windows and idle tail finish. On revocation, local buffers and queued work for
that assignment are discarded; a new owner reconstructs them from retained
audio. Skipped messages and interleaved sessions cannot commit past that audio.
This deliberately trades repeated inference and higher partition lag for a small
implementation without a separate checkpoint store. Audio retention must cover
the longest active-session recovery interval; expired input cannot be rebuilt.

Idle timeout is still the existing end-of-audio signal. Resuming a previously
idle-flushed/evicted session can restart its timing origin, especially across a
worker restart. A durable end/resume contract needs separate agreement. This
spike does not introduce that protocol. Use a new session after completion.

Live JSON retains track/window identity through the existing tenant-scoped BFF
reply route. Buffers and deduplication are scoped to the session and track; the
buffer limit applies per track. The API's existing `track_id` filter covers
refined and final history. UI labels/tabs and durable per-track status remain
future work; session status does not establish success for every track.

## Qualification

The repeatable smoke covers two full 10-second windows plus a 3.125-second tail
using repeated public audio fixture data. Real WhisperX runs alongside explicitly
synthetic inference, which proves plumbing rather than another model's quality.
It checks live WS output before closing audio ingress, history/filtering,
selection headers and metadata, frozen reconnects, defaults/silence, skip behavior,
first-result replay, interleaved sessions, replicas, rebalance/owner loss,
independent failure/restart, a session-scoped database fault, and tenant denial.
The injected trigger/function is removed in `finally`. If the probe is forcibly
killed during that test, inspect `lean_refinement_smoke_reject` before rerunning;
never remove unrelated triggers or data.

Validation on 2026-09-14:

- BFF full suite: 129 tests / 973 assertions, zero failures/errors. Changed
  files pass clj-kondo; the source UI also compiled in the Docker build.
- Persistor full suite: 15 tests / 84 assertions, zero failures/errors. Its
  real Postgres test includes concurrent replay and preserved word timestamps.
- Xamurai lightweight regression suite plus refinement publication checks:
  72 passed, including failure to acknowledge a Kafka publication.
- Migration 019: isolated-schema tests passed on the real Compose Postgres;
  duplicate preflight, NULL history, separate windows/tracks/tenants, NULL
  window-length replay and repeated application were checked and rolled back.
- Rebuilt and deployed `samuraibff:lean-tracks`, `samuraipersistor:lean-tracks`
  and `xamurai-whisperx-worker:lean-tracks`; all three running image IDs match.
- Full Compose smoke passed, including real WhisperX medium, exact adjacent
  windows/tail, live output, history/filtering, interleaved replay, owner loss,
  same-track replicas, a one-job queue, independent failure/restart, DB retry,
  tenant rejection, realtime output and WAV/range playback.
- After restoring the ordinary local Compose settings and normal idle timeout,
  `refinement-tracks-smoke --normal-only` passed realtime/refined/final and
  playback again. That mode starts no synthetic workers. The probe now drains
  live events while awaiting final persistence; an earlier probe held them in
  its client queue and logged a close-time keepalive warning after assertions.
- Before migration: 182 transcripts, 63 recording records, no duplicate tagged
  refined windows, and versions 017/018 already applied. A custom-format dump
  was taken, then the regular runner applied 019 without changing prior entries.
  All 245 pre-existing transcript/recording row hashes match after qualification.
- No injected `lean_refinement_smoke_reject` function or trigger remains. No
  synthetic workers remain running. All published host ports bind to 127.0.0.1.

The backup, row hashes and test logs are retained in Nanodeploy's ignored
`.tmp/refinement-spike/` directory. No volumes were reset or historical rows
rewritten. The migration SQL hashes match across all three deployment copies.
The old LocalStack historical-audio limitation recorded in spike 1 is unchanged;
this qualification tests playback of new recordings.
