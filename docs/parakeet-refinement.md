# Parakeet semi-batch refinement

The existing Parakeet overlay now offers `parakeet` in both **Refinement** and
**Final** settings. Select either model or both independently at each stage.
`parakeet-refinement` consumes the original `audio.raw` stream, emits one refined
event per window, and uses the same Parakeet/Sortformer pipeline as finalization.
Both model processes share the immutable artifact cache, but load their own
weights. WhisperX remains the default when no refinement track is selected.

Parakeet returns word timing and up to four anonymous speakers per window.
Speaker labels restart with each window: matching labels across windows do not
establish speaker identity. There is no enrolled-speaker mapping for this track.
Window and word times use session coordinates; idle input flushes a short tail.
Live events keep the existing per-segment text/speaker format. Kafka and saved
HTTP transcripts also retain the timed words.
Start a new session after completion; the existing idle/resume limitation remains.

## Build and run

Use the original `nanosamurai` Compose project, volumes and ignored local image
overrides from [the finalizer setup](parakeet-finalizer.md). The BFF and Persistor
must already support lean tracks and migration 019; this feature adds no schema
or service contract changes. Keep `COMPOSE_BIND_IP=127.0.0.1`.

```powershell
$files = @('-p', 'nanosamurai', '-f', 'docker-compose.yml',
  '-f', 'docker-compose.nemotron.yml', '-f', 'docker-compose.local-asr.yml',
  '-f', 'docker-compose.parakeet.yml')
docker compose @files build whisperx_refinement whisperx_finalizer parakeet-finalizer parakeet-refinement
docker compose @files up -d --no-deps --no-build samuraibff whisperx_refinement whisperx_finalizer parakeet-finalizer parakeet-refinement
docker compose @files --profile validation build parakeet-refinement-smoke parakeet-smoke
docker compose @files --profile validation run --rm --no-deps parakeet-refinement-smoke
```

Rebuilding/recreating WhisperX is required because refinement buffering and
publication now live in Xamurai's shared package. Keep the existing WhisperX
consumer groups and local image tags. Stop obsolete `whisperx_worker` and
`finalizer_worker` containers from the earlier naming scheme, and old synthetic
spike workers, before qualification; do not reset offsets or delete volumes.
The overlay's new group is `refinement.parakeet` and has no host port or S3
credentials. The image override is `PARAKEET_REFINEMENT_IMAGE`.

The worker defaults to 60-second windows (the UI/API's existing window setting
overrides this), a 30-second idle timeout, and a queue of 256 windows. Operators
can set `REFINEMENT_SLICE_SECONDS`, `REFINEMENT_IDLE_SECONDS` and
`REFINEMENT_READY_QUEUE_MAX`; old `WHISPERX_*` names remain fallbacks. Avoid
shortening the idle timeout below expected pauses in incoming audio. See the
[Xamurai contract](https://github.com/nanosamurai/xamurai/blob/master/docs/parakeet-refinement.md).

## Qualification

The new probe reuses the existing refinement smoke helpers and real stack. It
starts no synthetic workers. It checks two 10-second windows and a 3.125-second
tail for both real models, live WebSocket delivery while ingress remains open,
persisted model identity, session-relative Parakeet words/speakers, HTTP filtering,
real input replay and conflicting-result deduplication, each model alone,
omitted selection, silence, disabled refinement, committed skips and tenant denial.
Assertions are printed without transcript contents; new fixture sessions remain
as evidence. It does not reset offsets or rewrite existing transcripts.

Run the finalizer regression separately. Set `WHISPERX_FINALIZER_GROUP` to the
existing local finalizer's group if it differs from `finalizer-worker`:

```powershell
docker compose @files --profile validation run --rm --no-deps parakeet-smoke
docker compose @files --profile validation run --rm --no-deps --entrypoint python parakeet-refinement-smoke /probe/refinement/smoke.py --normal-only
```

The existing synthetic [recovery smoke](refinement-tracks-spike.md) still tests
the shared runtime's owner loss, replicas, failure/restart and database retry.
Its image now builds from the selected `whisperx_refinement` service through
an explicit build context; rebuild it after changing Xamurai.

No model pins, hashes, native runtime or license attribution change. The new
worker runs unprivileged, removes temporary windows after inference, and
requires no model token. The existing local stack has development credentials
and must remain localhost-only. GPU/memory capacity and cross-window speaker
matching are not established by these short-fixture tests.
