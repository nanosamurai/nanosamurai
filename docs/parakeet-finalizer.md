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

From this repository, with existing infrastructure running:

```powershell
$files = @('-p', 'nanosamurai', '-f', 'docker-compose.yml',
  '-f', 'docker-compose.nemotron.yml', '-f', 'docker-compose.local-asr.yml',
  '-f', 'docker-compose.parakeet.yml')
docker compose @files build parakeet-finalizer
docker build -t xamurai-finalizer-worker:parakeet-spike -f ../xamurai/finalizer_worker/Dockerfile ../xamurai
```

Set the existing `finalizer_worker.image` in the ignored local override to
`xamurai-finalizer-worker:parakeet-spike`; preserve its existing consumer group.
The rebuild verifies the shared finalizer loop with WhisperX as well. Update the
ignored `.env`'s `COMPOSE_FILE` to append `docker-compose.parakeet.yml` if this
track should stay available during ordinary local startup.

```powershell
docker compose @files up -d --no-deps --no-build samuraibff samuraipersistor recorder_worker finalizer_worker parakeet-finalizer
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
Czech fixture. It checks two real results sharing one recording, model identity,
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

## Local validation on 2026-09-16

The complete Parakeet Compose smoke passed on the original project and volumes,
using source-built Parakeet and WhisperX finalizer images. The fixture is 20
seconds long; the silence case is one second. Both results persisted, playback
and word timings matched the API, repeated inference preserved the first rows,
and every selection/skip and tenant-denial assertion passed.

Existing Tier 1 connectivity and Tier 2 real Nemotron FINAL smokes passed too.
Both finalizers and the existing realtime/refinement services were running with
zero restarts at the final check. No temporary Parakeet recording downloads
remained, and all six configured published ports were bound to loopback.

The ignored local override selects `xamurai-finalizer-worker:parakeet-spike` and
preserves the original WhisperX group. The ignored `.env` appends the Parakeet
overlay; ordinary local startup now advertises the additional final track.
The new Parakeet image is `xamurai-parakeet-finalizer:local`. Public base image
pins are unchanged; build the source images as above to reproduce this spike.
