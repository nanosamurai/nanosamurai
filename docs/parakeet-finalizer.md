# Parakeet final track spike

This opt-in overlay adds a real Parakeet TDT 0.6B v3 finalizer with embedded
Sortformer v2. Choose `parakeet`, `whisperx`, or both in the Final settings tab.
Both consume one retained source recording and produce separate saved transcript
tabs with word timing. Parakeet supports up to four anonymous speakers; enrolled
names are not part of this spike. No migration or BFF/Persistor code change is
required beyond the already implemented lean track support.

## Build and run locally

Use the existing `nanosamurai` project and its volumes. The source checkout
defaults to `../xamurai`; override `XAMURAI_SOURCE` if needed. Retain the local
BFF, Persistor, recording and realtime image overrides from previous spikes.
Keep `COMPOSE_BIND_IP=127.0.0.1`. Never start the old synthetic workers as part
of this real-model overlay.

From this repository, with existing infrastructure running. If upgrading an old
local stack, stop its `nanosamurai-whisperx_worker-1` and
`nanosamurai-finalizer_worker-1` containers before starting the renamed services.
Keep the existing consumer groups and cache volumes.

```powershell
$files = @('-p', 'nanosamurai', '-f', 'docker-compose.yml',
  '-f', 'docker-compose.nemotron.yml', '-f', 'docker-compose.local-asr.yml',
  '-f', 'docker-compose.parakeet.yml')
docker compose @files build whisperx_refinement whisperx_finalizer parakeet-finalizer
```

Set the existing `whisperx_finalizer.image` in the ignored local override to
`xamurai-finalizer-worker:module-refactor`; preserve its existing consumer group.
The rebuild includes the WhisperX pipeline and both entrypoints. Update the
ignored `.env`'s `COMPOSE_FILE` to append `docker-compose.parakeet.yml` if this
track should stay available during ordinary local startup.

```powershell
docker compose @files up -d --no-deps --no-build samuraibff samuraipersistor recorder_worker whisperx_refinement whisperx_finalizer parakeet-finalizer
$env:WHISPERX_FINALIZER_GROUP = 'final-track.whisperx.whisperx-medium-final-r1'
docker compose @files --profile validation build parakeet-smoke
docker compose @files --profile validation run --rm --no-deps parakeet-smoke
```

Use the actual existing WhisperX group for `WHISPERX_FINALIZER_GROUP`; the
overlay defaults to the base Compose group's `finalizer-worker`. This changes
only the probe's offset checks, not worker offsets or group names.

No model token is required by Parakeet/Sortformer. The separate model-cache
volume contains immutable, hash-verified artifacts. WhisperX still uses its
existing HF credentials and cache. Model downloads and the first initialization
can take several minutes. All inference endpoints remain internal to Compose.

## Smoke coverage

The probe reuses the existing final-track HTTP/Kafka/DB helpers and published
Czech fixture. It checks two WhisperX refinement windows, two real final results
sharing one recording, model identity,
speaker labels and word timings, filtered HTTP results, exact WAV playback and
range requests, retained multi-track audio, replay idempotency, silence,
Parakeet-only and WhisperX-only selection with committed skips, and foreign
tenant denial. It creates new evidence sessions and never prints transcripts.
No offsets are reset, volumes replaced, or historical transcripts rewritten.

Native model tests live in Xamurai's
`tests/test_parakeet_finalizer_integration.py`; they also check empty/stereo
inputs and repeated requests with independent speaker state. General worker
failure/restart coverage remains in the existing final-track smoke.

The Xamurai [pipeline documentation](https://github.com/nanosamurai/xamurai/blob/master/docs/parakeet-finalizer.md)
records model/runtime pins and limitations. Short-fixture smoke is functional
qualification, not a claim about recognition accuracy or maximum recording length.
