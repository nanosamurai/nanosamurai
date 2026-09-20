# Getting started

This guide takes a clean machine from an empty checkout to a first browser
transcription. The supplied Docker Compose configuration is an evaluator stack:
it binds published ports to localhost, uses development credentials, and is not
a production deployment manifest.

## Choose an evaluation path

| Path | What starts | GPU required |
| --- | --- | --- |
| Default stack | UI/API, infrastructure, persistence, realtime transcription, refinement, recording, and finalization | Yes |
| Dual realtime override | Default stack with Faster-Whisper and Qwen3-ASR 0.6B/vLLM evaluated as peer realtime tracks | Yes |
| Nemotron replica validation | Pinned Nemotron/NeMo-Speech.cpp service behind one DNS name, two replicas by default | Yes |
| Observability override | Default stack plus Grafana, Prometheus, Tempo, Loki, Alloy, and OpenTelemetry Collector | No additional GPU |

The default stack is the complete end-to-end speech product. It does not
silently fall back to a UI/API-only deployment when GPU access is unavailable.

## Prerequisites

- Git
- Docker Desktop or Docker Engine
- Docker Compose v2
- Enough disk space for the service images and selected speech models
- For speech processing, an NVIDIA GPU available to Docker through the NVIDIA
  container runtime
- A least-privilege Hugging Face token with access to the required gated
  pyannote models

There is not yet a published minimum GPU-memory guarantee. The July 2026 release
rehearsal passed on an NVIDIA GeForce RTX 5090 Laptop GPU with 24 GB of GPU
memory. Treat that as a tested configuration, not a minimum requirement.
Model downloads and first initialization can take several minutes.

## Start the default stack

Clone the public front-door repository, then create the local environment file:

```bash
git clone https://github.com/nanosamurai/nanosamurai.git
cd nanosamurai
cp .env.example .env
```

Windows PowerShell:

```powershell
git clone https://github.com/nanosamurai/nanosamurai.git
Set-Location nanosamurai
Copy-Item .env.example .env
```

Set `HF_TOKEN` in `.env`. The token should have only the model-read permissions
needed for the selected models.

Optional defaults in `.env`: `SAMURAIBFF_DEFAULT_REALTIME_TRACK`,
`SAMURAIBFF_DEFAULT_REFINEMENT_TRACK` and `SAMURAIBFF_DEFAULT_FINAL_TRACK`.
Each names one configured track, used only when that output is enabled and no
track is selected. Blank values preserve current defaults; explicit selections
take precedence. Requires a BFF image with default-track support.

Confirm that Docker can access the intended NVIDIA GPU, then pull and start the
complete evaluator stack:

```bash
docker compose pull
docker compose up -d
docker compose ps --all
docker compose logs --tail=100 rtservice whisperx_refinement recorder_worker whisperx_finalizer
```

Wait for model initialization to finish before treating an early timeout as a
failure. The speech containers request `gpus: all`; they will not start when
the NVIDIA runtime is unavailable.

Run the Tier 1 connectivity check described in
[Smoke tests and release rehearsal](smoke-tests.md), then continue with the
browser transcription below.

## Evaluate Qwen native streaming

The opt-in Qwen override keeps the default Faster-Whisper `rtservice` and adds
Qwen3-ASR as a second peer implementing the same `RealtimeASR` API. The BFF
fans one browser audio stream out to both tracks. Qwen is reachable only over
the internal Compose network and publishes no host port. Its checked-in Compose
default is pinned to the validated immutable Xamurai release, so start the stack
without selecting an image manually:

```bash
docker compose -f docker-compose.yml -f docker-compose.qwen.yml pull
docker compose -f docker-compose.yml -f docker-compose.qwen.yml up -d
docker compose -f docker-compose.yml -f docker-compose.qwen.yml ps --all
```

For local Xamurai development, build the Qwen and Faster realtime images in that
repository and set `QWEN_RTSERVICE_IMAGE` and `RTSERVICE_IMAGE` only in your
uncommitted `.env`. Image environment variables are optional development,
release-evaluation, and rollback overrides; the checked-in Compose pins are the
normal evaluator path. The Qwen model is pinned by its service profile and
downloads to the separate `nanosamurai_qwen_hf_cache` volume on first start. The service
requires CUDA, supports one native stream in this validation profile, emits
bounded partials, and forced-aligns and pyannote-diarizes completed epochs for
the aligner's advertised languages. It advertises segment timestamps and
speaker labels for those languages but intentionally does not claim word
timestamps. Unsupported languages or failed enrichment preserve a coarse
speakerless final. Its public stream has no duration cutoff; the service
finalizes and reopens native Qwen state every 60 seconds by default, carrying a
bounded transcript-context tail without replaying audio. Anonymous Qwen speaker
labels are epoch-scoped and do not claim cross-epoch identity. A Qwen failure
ends only its track; Faster-Whisper may continue.

The first two-second model chunk determines the earliest normal partial. Lower
`QWEN_STREAM_CHUNK_SECONDS` only as an experiment because it increases repeated
vLLM work. `QWEN_MAX_MODEL_LEN=4096` is aligned with the default 60-second
epoch and `QWEN_KV_CACHE_MIB=512` sets an explicit cache allocation instead of
reserving a percentage of all VRAM. The service rejects context/cache settings
that cannot hold the configured epoch. Model and vLLM/Torch compilation caches
persist in the separate Qwen volume across container recreation. Compose passes
the configured least-privilege `HF_TOKEN` only to the opt-in Qwen service so it
can read the fixed gated pyannote pipeline; the Qwen ASR and aligner models are
public and pinned by immutable revision and weight digest.

Validate both native partial delivery and request-EOF flushing through the BFF
with Tier 2's terminal-event mode:

```bash
python utilities/k8s_local_smoke_test/tier2_realtime_asr.py \
  --lang cs --stream-seconds 12 --asr-timeout 90 --require-final \
  --require-tracks faster-whisper,qwen
```

The smoke test reports event keys and latency only; it does not print the
transcript. It explicitly marks its temporary session finished during cleanup,
including after a failed ASR assertion.

To exercise Qwen alone without triggering Kafka refinement/finalization work,
use `--realtime-tracks qwen --require-tracks qwen --realtime-only`. This is the
preferred provider-development smoke when the other GPU models are already
running. With a short test epoch, add `--require-final --require-final-count 2`
to prove the public stream stays open across an internal epoch final and still
flushes the last epoch at EOF.

For an approved English speech fixture, require the enriched path explicitly:

```bash
python utilities/k8s_local_smoke_test/tier2_realtime_asr.py \
  --wav <consented-english-speech.wav> --lang en --stream-seconds 12 \
  --asr-timeout 180 --realtime-tracks qwen --require-tracks qwen \
  --realtime-only --require-final --require-speaker-labels
```

For a consented multi-speaker fixture, add `--require-distinct-speakers 2`.
For a fixture longer than the configured epoch, add
`--require-speaker-epochs 2`; this asserts that labelled finals arrive from two
separate bounded Qwen states rather than merely counting multiple turns inside
one epoch.

Do not use the repository's Czech fixture for that assertion: Czech transcription
is supported, but the pinned forced aligner does not advertise Czech, so the
expected result is the documented coarse speakerless fallback. Assert that path
with `--require-final --require-speakerless-finals`.

## Validate Nemotron replicas

Nemotron is an experimental source-build recipe, separate from the released
quickstart. No published Nemotron image pin is selected; the base stack and
Qwen override retain their existing release pins. Local image overrides and
enrollment calibration belong in an ignored `.env` or explicitly selected
`docker-compose.local-asr.yml` and must not be committed.

The opt-in Nemotron override is the focused Phase 2b validation path. It runs
the fixed `nvidia/nemotron-3.5-asr-streaming-0.6b` Q8 profile through the pinned
NeMo-Speech.cpp C ABI. Each container owns one recognizer and admits one stream
by default; every accepted stream owns independent native cache state. Compose
starts two containers behind the stable `nemotron-rtservice` DNS name. The
service and probe publish no host ports.

Build the image from the adjacent Xamurai checkout:

```powershell
Set-Location ../xamurai
docker buildx bake --load nemotron-rtservice
Set-Location ../nanosamurai
```

Start only the two provider replicas while developing:

```powershell
docker compose -f docker-compose.yml -f docker-compose.nemotron.yml `
  up -d --no-deps nemotron-rtservice
docker compose -f docker-compose.yml -f docker-compose.nemotron.yml `
  ps nemotron-rtservice
```

Cold start includes downloading and hashing the pinned 742 MB GGUF artifact in
each process before readiness; the shared cache volume avoids duplicate network
downloads. Wait until both containers are healthy, then run the internal probe:

```powershell
docker compose --profile nemotron-validation `
  -f docker-compose.yml -f docker-compose.nemotron.yml `
  run --rm --no-deps nemotron-probe
```

Success prints `replica_check=ok distinct_instances=2` and
`audio_check=ok`. The probe holds two admission handshakes concurrently to
prove DNS round-robin reached two process identities, then streams the checked-in
Czech fixture and requires a non-empty final. It reports only counts and status,
never transcript text.

For the browser/full-stack path, the existing pinned SamuraiBFF image predates
the required realtime replica routing. Build a compatible BFF source revision
that includes that routing and set `SAMURAIBFF_IMAGE` only in the ignored
`.env` or an explicitly selected local override. Keep the published default pin
unchanged. The BFF registers `nemotron-rtservice:50052`, resolves all task
addresses, uses gRPC `round_robin`, and retries only a pre-admission
`REPLICA_FULL` response.

`NEMOTRON_RTSERVICE_REPLICAS` controls process replicas and
`NEMOTRON_RT_SERVING_MAX_SESSIONS` controls bounded streams per process. Keep
the default one stream per replica for the routing proof. Values above one
enable NeMo-Speech.cpp microbatching inside that process and require a separate
latency and memory qualification. `NEMOTRON_RNNT_RIGHT_CONTEXT=1` selects the
roughly 160 ms trained right-context mode. The service accepts only PCM16 mono
at 16 kHz and a fixed allowlisted language code; clients cannot choose model
paths or revisions.

Remove the validation containers without deleting the model cache:

```powershell
docker compose -f docker-compose.yml -f docker-compose.nemotron.yml down
```

### Add optional Sortformer and enrolled names

Build a Xamurai revision that includes optional Sortformer and enrolled-speaker
matching. In the ignored `.env`, set
`NEMOTRON_DIARIZATION=true`. Add `NEMOTRON_ENROLL_BACKEND=s3_manifest` to match
the existing tenant enrollment WAV samples in LocalStack. Neither speaker
model is loaded in the default ASR-only mode; anonymous diarization also works
with enrollment disabled. No Hugging Face token is needed for these models.

```powershell
docker compose -f docker-compose.yml -f docker-compose.nemotron.yml `
  up -d --no-deps localstack
docker compose -f docker-compose.yml -f docker-compose.nemotron.yml `
  up -d --no-deps --scale nemotron-rtservice=2 nemotron-rtservice
docker compose --profile nemotron-validation `
  -f docker-compose.yml -f docker-compose.nemotron.yml `
  run --rm --no-deps nemotron-probe --replicas 2 --wav /fixtures/test_cs.wav `
  --require-speakers --concurrent-audio
```

For a consented fixture whose speaker has been enrolled under the guest tenant,
also pass `--tenant-id 00000000-0000-0000-0000-000000000000 --require-enrolled`.
The probe uses only container DNS and prints counts, not names or transcripts.
Use held-out audio to assess matching quality; reusing enrollment audio is only
a wiring check.

Sortformer supports up to four speakers in one continuous stream. The S3
gallery can contain more people: each detected speaker is matched against the
tenant's usable gallery, capped at 256 records for resource safety. Unknown,
short or ambiguous matches stay anonymous. Expected meetings with more than
four speakers should use the existing pyannote-based service. The default
cosine threshold (`NEMOTRON_ENROLL_SIM_THRESHOLD=0.65`) and runner-up margin
(`NEMOTRON_ENROLL_MATCH_MARGIN=0.1`) require local quality calibration.

Speaker processing uses the same two replicas and admission mechanism; there
is no additional service, scheduler or Kubernetes dependency. Details and
model attribution live in Xamurai's `docs/nemotron-sortformer.md`.

The 2026-09-08 local GPU qualification passed with two Sortformer/enrollment
replicas, concurrent real fixture audio, tenant-isolated held-out enrollment
matching, and speaker-labelled finals through the localhost BFF WebSocket.
The same image also passed with speaker processing disabled. This verifies the
integration on an RTX 5090 Laptop GPU with the single-speaker fixture; it does
not establish accuracy for multi-speaker meetings or capacity on other GPUs.

## Make the first browser transcription

1. Open <http://127.0.0.1:8000/live>.
2. Choose a language or leave language detection on its default.
3. Select **Microphone** as the input.
4. Open **Session settings**, select the desired realtime tracks, and choose the
   realtime, refined, and final outputs. With the Qwen override, select Faster,
   Qwen, or both; both are selected unless a realtime default is configured.
5. Choose **Record now**, grant microphone permission, and speak.
6. Compare simultaneous realtime tracks in their labelled side-by-side panels.
7. Stop the recording when finished.
8. Watch realtime hypotheses while recording. Refined events arrive
   asynchronously; the final transcript appears later in the recording detail
   after the recording and finalizer workers complete.

For deterministic validation, use the repository smoke-test audio and Tier 2-4
scripts instead of microphone input. See
[Transcription lifecycle](transcription-lifecycle.md) for the meaning of each
output.

## Add local observability

Start the evaluator stack with the observability override:

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d
```

Local endpoints:

- Grafana: <http://127.0.0.1:3001>
- Prometheus: <http://127.0.0.1:9090>
- Loki: <http://127.0.0.1:3100>
- Tempo: <http://127.0.0.1:3200>

The default Grafana evaluator credentials are `admin` / `admin`. They are
development-only credentials protected by the localhost bind and must not be
reused for a production deployment.

## Stop or reset the stack

Stop the services while preserving volumes:

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml down
```

To remove the evaluator data and model cache as well:

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml down -v
```

The `-v` form permanently deletes local transcripts, recordings, database
state, and cached models. See [Troubleshooting](troubleshooting.md) before
resetting a stack that contains anything you need.
