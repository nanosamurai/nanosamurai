# Smoke tests and release rehearsal

For the unmerged lean track UI spike, see [the browser/Compose runbook](track-selection-ui.md).

The tests are cumulative: each higher tier requires the services exercised by
the lower tiers.

| Tier | What it verifies |
| --- | --- |
| 1 | BFF HTTP connectivity |
| 2 | WebSocket and realtime ASR |
| 3 | Session audio reaches Kafka |
| 4 | Recording, refined, or final async signal |

Tier 2 accepts the first realtime partial by default. Pass `--require-final`
when validating a native-streaming provider to prove that closing the audio
WebSocket flushes a terminal event through BFF. Pass
`--require-tracks faster-whisper,qwen` with the Qwen override to require a
matching event from both peer services.
Pass `--require-speaker-labels` together with `--require-final` when a selected
provider/language must prove its aligned-and-diarized path. The assertion counts
only final events with a non-empty speaker label and never prints transcript
content.
Add `--require-distinct-speakers 2` for a multi-speaker fixture, or
`--require-speaker-epochs 2` for a fixture that must prove labelled finals on
both sides of a Qwen epoch rollover. Both options require
`--require-speaker-labels`.
Use `--require-speakerless-finals` instead for an unsupported alignment language
such as Czech; the two speaker assertions are mutually exclusive.

## Install the test environment

```bash
python -m venv .venv-smoke
. .venv-smoke/bin/activate
python -m pip install -r utilities/k8s_local_smoke_test/requirements.txt
python -m pip install -r utilities/k8s_local_smoke_test/requirements.kafka.txt
```

On Windows PowerShell, use `py -m venv .venv-smoke` and invoke
`.\.venv-smoke\Scripts\python` for the remaining commands.

## Release rehearsal

1. Copy `.env.example` to `.env` and set a least-privilege `HF_TOKEN`.
2. Run `docker compose config --quiet`.
3. Run `docker compose pull` and then `docker compose up -d`.
4. Wait for the speech services and their models to finish starting.
5. Run Tier 1, Tier 2, Tier 3, Tier 4 `recording-finished`, and Tier 4
   `refined`.
6. Run strict Tier 4 `final` when validating the full finalizer contract.
7. Repeat `docker compose up -d` without deleting volumes and verify the
   migration and seed jobs complete successfully.
8. Start the observability override and repeat Tier 3/4 while checking Tempo,
   Prometheus, Loki, and Grafana.

Use `smoke-tests/smoke.sh` or `smoke-tests/smoke.ps1` to orchestrate the tiers.
Tier 4 `final` remains opt-in because model and alignment cold starts can be
long. A release note must state clearly if that signal is not validated.

The test audio is synthetic repository data. Never add customer recordings,
transcripts, tokens, or identifying metadata to test fixtures or public issues.

## Native Nemotron VAD

Build the adjacent Xamurai checkout and recreate the provider using the rebuilt
image (include any existing local overrides in the same order as the running
stack). An explicit image override must also point to the new tag:

```powershell
Set-Location ../xamurai
docker buildx bake --load nemotron-rtservice
Set-Location ../nanosamurai
docker compose -f docker-compose.yml -f docker-compose.nemotron.yml `
  up -d --no-deps nemotron-rtservice
```

The image runs Silero v6.2.0 natively with masking disabled; ASR receives all
audio. `NEMOTRON_ENDPOINTING_SILENCE_MS` defaults to 2000 ms and the per-session
setting still overrides it. After 90 seconds, the silence interval shortens to
700 ms (unless already shorter); 120 seconds is the emergency limit. See
[instance configuration](realtime-settings.md) for the three environment variables.
Wait for health, then run the internal probe as described in
[getting started](getting-started.md#validate-nemotron-replicas).

To verify a silence endpoint through BFF before EOF, send eight seconds of the
synthetic fixture followed by five seconds of silence. `--silence-seconds`
keeps the audio socket open while waiting for a final, so success cannot rely
on closing the stream. The total input is below the emergency endpoint:

```powershell
.\.venv-smoke\Scripts\python utilities/k8s_local_smoke_test/tier2_realtime_asr.py `
  --base-url http://127.0.0.1:8000 --lang cs --stream-seconds 8 `
  --silence-seconds 5 --require-final --realtime-only `
  --realtime-tracks nemotron --require-tracks nemotron
```

With `NEMOTRON_DIARIZATION=true`, use `--stream-seconds 20` and add
`--require-speaker-labels` for the complete fixture (25 seconds including
silence, still below the hard endpoint).
Also run ordinary Tier 2 with `--require-final --realtime-only
--realtime-tracks faster-whisper,nemotron --require-tracks faster-whisper,nemotron`
to cover EOF and both realtime tracks. Xamurai's
`tests/test_nemotron_vad_integration.py` separately checks leading silence,
repeated utterances and 800/2000/3000 ms native endpoint timing with and without
Sortformer, plus the 90/120-second duration policy and a shorter configured
override; its `docs/nemotron-vad.md` includes the container command.

The 2026-09-17 local GPU run passed the native tests, two concurrent replicas,
Tier 1, Tier 2 finals from both realtime tracks, the eight-second silence smoke,
and the full-fixture speaker-labelled silence smoke with the rebuilt
`xamurai-nemotron-rtservice:native-vad` image. Local image overrides stay ignored.
Short 8/12-second excerpts can return a speakerless final because native word
metadata does not fully match the final text; requiring speaker labels on those
excerpts failed. The existing fallback preserves the text. This boundary-quality
limitation is documented in Xamurai's VAD guide and remains outside this spike.

The duration-policy follow-up rebuilt and ran
`xamurai-nemotron-rtservice:duration-endpointing` in the same local Compose stack.
Tier 1, EOF finals from both realtime tracks, and the 20-second speaker-labelled
silence smoke passed. A separate
99-second BFF stream used eleven repetitions of fixture seconds 3–11 followed
by one second of silence, with a 3000 ms session timeout. It produced no finals
through 90 seconds, then a final at audio position 92.18 seconds before EOF.
The native GPU suite also passed the emergency-limit test (120.66 seconds),
shorter configured limits, and resetting the policy after an endpoint.
