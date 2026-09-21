# Developer smoke-test runbook

This runbook explains how developers can run smoke tests after a code or image change.
Use it to check that users can record speech, receive transcripts, and play saved audio.
For installation, use [Getting started](getting-started.md).

## Prepare

Run commands from the repository root against a local Community Edition test stack with your changed images.
Wait for model startup. Keep ports on `127.0.0.1`. Use repository audio, not customer recordings.
Tests create sessions and saved results. Run GPU tests one at a time; they do not measure model accuracy or capacity.
Keep existing volumes and consumer offsets. For image builds and upgrades, see [source setup](models/source-builds.md).

```bash
python -m venv .venv-smoke
. .venv-smoke/bin/activate
python -m pip install -r utilities/k8s_local_smoke_test/requirements.txt -r utilities/k8s_local_smoke_test/requirements.kafka.txt
```

On Windows, use `.venv-smoke/Scripts/Activate.ps1` instead of the activation command above.

## Check the running stack

The [test scripts](../utilities/k8s_local_smoke_test/) check the API, live text, audio delivery, and completed recording or transcript events in that order:

```bash
python utilities/k8s_local_smoke_test/tier1_bff_connectivity.py
python utilities/k8s_local_smoke_test/tier2_realtime_asr.py --lang cs --require-final
python utilities/k8s_local_smoke_test/tier3_kafka_audio_raw.py --lang cs --kafka-bootstrap 127.0.0.1:9092
python utilities/k8s_local_smoke_test/tier4_async_pipeline.py --lang cs --kafka-bootstrap 127.0.0.1:9092 --signal recording-finished --timeout 180
```

Repeat the last command with `--signal refined`, then `--signal final`.
Allow more time for first-use model loading. Each command must exit successfully.
Use `--help` for options. Check only the stages enabled in your test stack.
After a UI or playback change, also record a session in the browser, open its saved results, and play the audio.

## Check optional models

Start the models with their [setup guides](models/README.md). Keep the same Compose file list and image overrides for tests.
Parakeet and Qwen worker comparisons require WhisperX in both stages and blank default-track settings.
Set `XAMURAI_SOURCE` to the compatible source checkout; Qwen worker tests use its English audio fixture.

| Model | Test source | Compose overlay | Test service / profile |
| --- | --- | --- | --- |
| Nemotron | [Replica and audio probe](https://github.com/nanosamurai/xamurai/blob/master/nemotron_rtservice/src/nemotron_rtservice/probe.py) | `docker-compose.nemotron.yml` | `nemotron-probe` / `nemotron-validation` |
| Parakeet | [Final results](../smoke-tests/final-tracks/parakeet.py), [live refinement](../smoke-tests/refinement-tracks/smoke.py) | `docker-compose.parakeet.yml` | `parakeet-smoke`, `parakeet-refinement-smoke` / `validation` |
| Qwen workers | [Refined/final results and recording completion](../smoke-tests/final-tracks/qwen.py) | `docker-compose.qwen-workers.yml` | `qwen-smoke` / `validation` |

Build and run the test service. For example, with Qwen workers already running:

```bash
docker compose -f docker-compose.yml -f docker-compose.qwen-workers.yml --profile validation build qwen-smoke
docker compose -f docker-compose.yml -f docker-compose.qwen-workers.yml --profile validation run --rm --no-deps qwen-smoke
```

Use the overlay, service, and profile from the table for the other tests. Run each Parakeet test separately.
Worker tests check separate model results, playback, replay, and tenant isolation. Nemotron checks replica connections and realtime audio.
For custom WhisperX consumer groups, set `WHISPERX_REFINEMENT_GROUP` and `WHISPERX_FINALIZER_GROUP` on the probes, not the workers.
Nemotron uses the service image, so skip the build step. Keep the configured replica count; use the probe's `--help` for speaker checks.

For Qwen realtime, run Tier 2 with `--realtime-tracks qwen --require-tracks qwen --realtime-only --require-final --require-speakerless-finals`.
Keep `--lang cs` for the Czech fixture. For supported English audio, use `--wav <path> --lang en --require-speaker-labels` instead of `--require-speakerless-finals`.

## Tests for worker recovery and browser changes

These tests use special fixtures and change the test stack configuration. Use them when you change model selection, worker retries, or the UI.
Inspect the linked test and overlay before running it; they are not checks for an ordinary installation.

| Change to verify | Test source | Fixture configuration |
| --- | --- | --- |
| One final worker fails while another completes; retries preserve results | [Final worker tests](../smoke-tests/final-tracks/smoke.py) | [Final test overlay](../docker-compose.final-tracks-smoke.yml) |
| Refined results survive worker restart or partition reassignment | [Refinement tests](../smoke-tests/refinement-tracks/smoke.py) | [Refinement test overlay](../docker-compose.refinement-tracks-smoke.yml) |
| Model choices, result tabs, and playback work in the browser | [Browser tests](../smoke-tests/track-ui/smoke.py) | [Browser test overlay](../docker-compose.track-ui-smoke.yml) |
| Realtime settings reach the services and remain fixed during a session | [Settings test](../smoke-tests/track-ui/settings.py) | [Settings audit overlay](../docker-compose.realtime-settings-smoke.yml) |

The worker tests inject failures. If interrupted, check for the test marker `/faults/fail` and database faults named `lean_smoke_reject_final` or `lean_refinement_smoke_reject`.
Remove only test faults. Stop synthetic workers and restore ordinary service settings after testing.
Browser tests need [Python dependencies](../smoke-tests/track-ui/requirements.txt) and `python -m playwright install chromium`.
They write evidence to ignored `.tmp/` directories. For API settings, use the [BFF WebSocket contract](https://github.com/nanosamurai/samuraibff/blob/master/docs/ws-contract.md).

## Before a release

Repeat startup without deleting volumes and check that migrations and seed jobs succeed.
Repeat the relevant tests with observability enabled if you changed tracing or metrics.
Record the tested image versions, results, and skipped checks. Do not claim final transcription passed if you tested only live text.
