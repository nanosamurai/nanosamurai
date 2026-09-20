# Check optional models

These checks are for operators and contributors. Start with the [model guides](models/README.md).
Use the same Compose files and image overrides that started your stack.
Keep all published ports on `127.0.0.1`.

The tests create sessions from repository audio and print assertions without transcript text.
They check service integration, not recognition accuracy or maximum capacity.
Run GPU tests one at a time. Do not reset volumes or consumer offsets.

## Qwen realtime

Install the [smoke-test environment](smoke-tests.md#install-the-test-environment), then run:

```bash
python utilities/k8s_local_smoke_test/tier2_realtime_asr.py --lang cs --stream-seconds 12 --asr-timeout 90 --require-final --require-tracks faster-whisper,qwen
```

If Faster-Whisper is disabled, use `--realtime-tracks qwen --require-tracks qwen --realtime-only` instead of the two-track requirement.
Use `--require-speakerless-finals` for the Czech fixture.
For approved English audio, use `--wav <path> --lang en --require-speaker-labels` instead.
See [Smoke tests](smoke-tests.md) for multiple-speaker and epoch checks.

## Nemotron

After all configured replicas are healthy, run the internal probe:

```bash
docker compose -f docker-compose.yml -f docker-compose.nemotron.yml --profile nemotron-validation run --rm --no-deps nemotron-probe
```

With two replicas, success includes `replica_check=ok distinct_instances=2` and `audio_check=ok`.
If you changed the replica count, keep `NEMOTRON_RTSERVICE_REPLICAS` set for the probe too.
For enabled speaker processing, append `--replicas 2 --wav /fixtures/test_cs.wav --require-speakers --concurrent-audio`.
Use your actual replica count. Enrolled-name checks need `--tenant-id` and `--require-enrolled` with suitable test audio.
Use separate enrollment and test recordings to assess matching quality.

## Parakeet

Run these checks with both WhisperX and Parakeet enabled in both stages:

```bash
docker compose -f docker-compose.yml -f docker-compose.parakeet.yml --profile validation build parakeet-smoke parakeet-refinement-smoke
docker compose -f docker-compose.yml -f docker-compose.parakeet.yml --profile validation run --rm --no-deps parakeet-refinement-smoke
docker compose -f docker-compose.yml -f docker-compose.parakeet.yml --profile validation run --rm --no-deps parakeet-smoke
```

Include your local overlay if it selects the required images or infrastructure.
Temporarily remove replacement settings that disable WhisperX before these comparison tests.
If your WhisperX consumer groups differ from the base file, set
`WHISPERX_REFINEMENT_GROUP` and `WHISPERX_FINALIZER_GROUP` for the probes.
Do not change the workers' existing groups for a test.

The tests cover live windows, final results, word timing, speaker labels,
WAV playback, replay, model selection, and tenant isolation.

## Qwen workers

After the [source-built stack](models/source-builds.md) and Qwen workers are running:

```bash
docker compose -f docker-compose.yml -f docker-compose.qwen-workers.yml --profile validation build qwen-smoke
docker compose -f docker-compose.yml -f docker-compose.qwen-workers.yml --profile validation run --rm --no-deps qwen-smoke
```

Keep WhisperX in both configured track lists for default-selection checks.
The probe uses Xamurai's synthetic English fixture through `XAMURAI_SOURCE`.
It checks refined and final output, word timing, playback, replay, selection,
tenant isolation, and recording completion after normal or interrupted Stop.
Updated BFF and recorder images are required for the ordered-Stop assertions.

For shared worker recovery tests, see [final-track tests](final-tracks-spike.md)
and [refinement-track tests](refinement-tracks-spike.md).
