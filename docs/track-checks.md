# Check transcription tracks

These contributor tests check selection, storage, playback, and recovery.
They use real WhisperX inference and synthetic test workers. Synthetic output
checks integration; it does not measure another model's quality.
For model-specific checks, see [Check optional models](model-checks.md).

## Prepare the local stack

Run these tests from the `nanosamurai` repository root. Use a local test stack
with compatible [service images](models/source-builds.md), migrations 017–019,
and Nemotron realtime enabled. Keep Community Edition mode enabled. Do not run
the tests with external workflow or webhook consumers attached.

Set `XAMURAI_SOURCE`, `BFF_SOURCE`, and `PERSISTOR_SOURCE` to compatible source
checkouts. The test overlays build some services with local `lean-tracks` tags.
These tags identify test images; they do not require old feature branches.

Finish active sessions and back up the database and recordings. Keep the
existing project name, PostgreSQL major version, volumes, and consumer groups.
Keep `HF_TOKEN` in the ignored `.env` and all host ports on `127.0.0.1`.
Use blank default-track settings for these tests, then restore your defaults.

The PowerShell examples use this ordinary configuration:

```powershell
$baseFiles = @('-p', 'nanosamurai', '-f', 'docker-compose.yml',
  '-f', 'docker-compose.nemotron.yml')
```

Adjust it to match your stack. If you use `docker-compose.local-asr.yml`, add
it last to both `$baseFiles` and each `$testFiles` list below. Retain image and
consumer-group overrides, but remove overrides that hide the test track lists.
Infrastructure must already be running. Check [track migrations](final-track-migration.md)
before an upgrade. Run one test group at a time.

## Final tracks

```powershell
$testFiles = $baseFiles + @('-f', 'docker-compose.final-tracks-smoke.yml')
docker compose @testFiles build samuraibff samuraipersistor recorder_worker whisperx_finalizer final-tracks-smoke
docker compose @testFiles --profile validation run --rm --no-deps --entrypoint python final-tracks-smoke /probe/migration.py
docker compose @testFiles up -d --no-deps --no-build samuraibff samuraipersistor recorder_worker whisperx_finalizer test-shadow test-unselected
docker compose @testFiles --profile validation run --rm --no-deps final-tracks-smoke
docker compose @testFiles stop test-shadow test-unselected
docker compose @baseFiles up -d --no-deps --no-build samuraibff samuraipersistor recorder_worker whisperx_finalizer
```

The migration probe uses a separate schema and rolls back its changes. It does
not upgrade the application database. The main test checks separate results,
one shared recording, defaults, reconnects, replay, failed-worker recovery,
download retries, database retries, tenant isolation, and audio retention.
The unselected worker must skip the recording.

The probe creates test sessions and leaves them as evidence. It removes its
fault marker and database trigger in `finally`. If the process is killed,
inspect `/faults/fail` in the test volume and the `lean_smoke_reject_final`
trigger and function. Remove only test faults. Do not reset volumes or offsets.

## Refinement tracks

```powershell
$testFiles = $baseFiles + @('-f', 'docker-compose.refinement-tracks-smoke.yml')
docker compose @testFiles build samuraibff samuraipersistor whisperx_refinement
docker compose @testFiles --profile validation build refinement-tracks-smoke
docker compose @testFiles --profile validation run --rm --no-deps --entrypoint python refinement-tracks-smoke /probe/refinement/migration.py
docker compose @testFiles up -d --no-deps --no-build samuraibff samuraipersistor whisperx_refinement
docker compose @testFiles --profile validation run --rm --no-deps refinement-tracks-smoke
docker compose @baseFiles up -d --no-deps --no-build samuraibff samuraipersistor whisperx_refinement
```

The migration probe tests migration 019 in a separate schema and rolls back.
The main test checks live windows and a short tail, history, replay, concurrent
sessions, replicas, partition reassignment, worker restart, database retries,
and tenant isolation. It starts synthetic workers as child processes and stops
them on exit. If the probe is killed during fault injection, inspect the
`lean_refinement_smoke_reject` trigger and function before you rerun it.

## Browser selection and playback

The UI test requires the two `lean-tracks` worker images built above. Install
the browser test environment. If a local override uses different image tags,
select the same images for `ui-test-final` and `ui-test-refined`:

```powershell
python -m venv .tmp/track-ui-python
$smokePython = '.tmp/track-ui-python/Scripts/python.exe'
& $smokePython -m pip install -r smoke-tests/track-ui/requirements.txt
& $smokePython -m playwright install chromium
```

On Linux or macOS, use `.tmp/track-ui-python/bin/python`.
The browser URL defaults to `http://127.0.0.1:8000`. Use `BFF_URL` for another
loopback URL. The runner sends `tests/data/test_cs.wav` through microphone capture.

```powershell
$testFiles = $baseFiles + @('-f', 'docker-compose.track-ui-smoke.yml')
docker compose @testFiles build samuraibff
docker compose @testFiles --profile validation build track-ui-audit
docker compose @testFiles --profile validation up -d --no-deps --no-build samuraibff whisperx_refinement recorder_worker ui-test-final ui-test-refined
& $smokePython smoke-tests/track-ui/smoke.py
docker compose @testFiles --profile validation run --rm --no-deps track-ui-audit
```

This checks stage selection, fixed session settings, separate result tabs,
missing results, text-only output, reloads, and shared audio playback. The audit
checks stored controls, labels, separate rows, one recording, and tenant isolation.
`ui-unavailable` has no worker so that the UI must show a missing result.
Screenshots and session IDs stay in ignored `.tmp/track-ui/`.

To check saved labels, create `.tmp/track-ui/renamed-labels.yml`:

```yaml
services:
  samuraibff:
    environment:
      SAMURAIBFF_TRACK_LABELS: '{"final":{"ui-shadow":"Renamed test"},"refined":{"ui-shadow":"Renamed windows"}}'
```

```powershell
docker compose @testFiles -f .tmp/track-ui/renamed-labels.yml up -d --no-deps --no-build samuraibff
& $smokePython smoke-tests/track-ui/smoke.py --verify-labels
docker compose @testFiles --profile validation stop ui-test-final ui-test-refined
docker compose @baseFiles up -d --no-deps --no-build samuraibff whisperx_refinement recorder_worker
```

After each test group, restore ordinary image settings, track defaults, and
idle timeouts. Run the [ordinary smoke tests](smoke-tests.md) again. Do not use
`down -v` or reset consumer offsets to clean up a test.

## Realtime settings and speaker display

Use ordinary Compose settings with Faster-Whisper and Nemotron enabled. Use
images with [service-owned settings](realtime-settings.md) support. The speaker
check also requires `NEMOTRON_DIARIZATION=true`. These tests need no synthetic workers.

```powershell
$testFiles = $baseFiles + @('-f', 'docker-compose.realtime-settings-smoke.yml')
docker compose @testFiles --profile validation build realtime-settings-audit
& $smokePython smoke-tests/track-ui/settings.py
docker compose @testFiles --profile validation run --rm --no-deps realtime-settings-audit
& $smokePython smoke-tests/track-ui/realtime.py
```

The settings test checks defaults, numeric limits, fixed session settings,
Whisper partials, and Nemotron silence settings. The audit compares saved
settings across HTTP, Postgres, and Kafka. The speaker test checks the unknown
speaker label and its alignment with a turn that has a speaker label.
Evidence stays in `.tmp/realtime-settings/` and `.tmp/track-ui-realtime/`.
