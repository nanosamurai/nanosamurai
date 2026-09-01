<img src="docs/nanosamurai_logo_finished_shoulders.svg" width="100">

# [nanosamur.ai](https://nanosamur.ai)
guarding your sensitive conversations</sub>

<sub>Your voice. Your control.</sub>

## **Complete speech AI platform**
- open source
- production-grade, distributed architecture
- multitenancy support

nanosamur.ai guards sensitive conversations in infrastructure you control. 

It is a model-agnostic orchestration platform that supports different models for
realtime, refined, and batch processing and provides a unified stack for robust
speech processing, agentic workflows, and webhooks.

Batteries included: we have a browser UI, a windows Electron app, API,
SDK, recording storage, persistence, and optional local observability.

This is the public front-door repository for running Community Edition locally
with Docker Compose. Service images are pulled from `ghcr.io/nanosamurai/*` and
pinned by source SHA.

## Demo - See it in action

<a href="https://nanosamur.ai/#demo">
  <img src="docs/demo-poster.jpg" alt="nanosamur.ai final transcript and workflow results" width="100%">
</a>

[Watch nanosamur.ai](https://nanosamur.ai/#demo) turn a live conversation into speaker-aware transcripts, workflow results, a searchable final record, and a fully traced session. 

## What Community Edition includes
<img src="docs/main-art-large.png" width="35%" align="right">


- browser UI and SamuraiBFF API
- Windows-first Electron wrapper
- one or more independently selectable realtime transcription models
- parallel, track-labelled realtime results from the same audio stream
- asynchronous speaker-aware refinement
- multi-tenancy support
- recording storage and full-session final transcripts
- PostgreSQL transcript persistence
- Python SDK and CLI source
- optional Grafana, Prometheus, Tempo, Loki, and Alloy stack
- public smoke tests and trace-context audit

The public code also includes agentic-workflow and webhook contracts.
Community Edition does not ship workflow execution or webhook delivery
services, but you are free to implement your own workflows / webhook services and plug them in.
<br clear="right">

## Multiple realtime models, one audio stream

nanosamur.ai can run multiple realtime speech models as peer providers behind
one API. SamuraiBFF accepts the audio once, fans it out to the models selected
for that session, and returns each result as a separate labelled track. The
models do not silently overwrite or blend one another.

This provides practical business and operational benefits:

- compare accuracy and latency on exactly the same conversation;
- introduce or evaluate a new model without replacing the established path;
- choose the best available provider set for a language, workload, or cost and
  latency target; and
- keep a slow or unavailable provider from blocking healthy realtime tracks.

```mermaid
flowchart LR
    Client["Browser, Electron, or SDK"] -->|"one audio stream"| BFF["SamuraiBFF\nsession track selection and fan-out"]
    BFF -->|"selected track"| Faster["Faster realtime\nFaster-Whisper + pyannote"]
    BFF -->|"selected track"| Qwen["Qwen realtime\nQwen3-ASR + ForcedAligner + pyannote"]
    Faster -->|"labelled ASR events"| Results["Independent realtime results"]
    Qwen -->|"labelled ASR events"| Results
    Results --> Client
    BFF -->|"publish audio once"| Async["Kafka refinement, recording, and finalization"]
```

The supplied base Compose stack starts the Faster-Whisper track. Add Qwen as a
second peer with the checked-in override:

```bash
docker compose -f docker-compose.yml -f docker-compose.qwen.yml pull
docker compose -f docker-compose.yml -f docker-compose.qwen.yml up -d
```

Both tracks are then available in the session settings, where an operator can
run Faster-Whisper, Qwen, or both. Concurrent models consume GPU memory and
compute independently, so capacity should be validated on the target hardware.
See [Evaluator getting started](docs/getting-started.md#evaluate-qwen-native-streaming)
for readiness checks and the tested profile.

### Model pipelines in the supplied stack

| Xamurai service | Stage | Default model pipeline | Result |
| --- | --- | --- | --- |
| `rtservice` | Realtime | `Systran/faster-whisper-medium` with `pyannote/speaker-diarization-3.1`; optional Silero VAD and enrolled-speaker mapping | Replaceable partials and timed, speaker-labelled finals |
| `qwen-rtservice` | Realtime | `Qwen/Qwen3-ASR-0.6B`, `Qwen/Qwen3-ForcedAligner-0.6B`, and `pyannote/speaker-diarization-3.1` | Native-streaming partials and aligned, speaker-labelled epoch finals where alignment is supported; speakerless fallback otherwise |
| `whisperx_worker` | Asynchronous refinement | WhisperX `medium` by default, language-specific alignment, and pyannote diarization | Refined speaker-aware transcript windows |
| `finalizer_worker` | Completed recording | The shared WhisperX alignment and pyannote pipeline | Canonical full-session transcript |
| `recorder_worker` | Recording | No inference model | Session WAV and recording-completion event |

These are the profiles supplied by the project, not model IDs accepted from an
untrusted client. Xamurai owns the detailed service contract and implementation;
see its [realtime provider guide](https://github.com/nanosamurai/xamurai/blob/master/docs/modular-asr-providers.md).

## Architecture

```mermaid
flowchart LR
    subgraph Client
        Browser["Browser UI\n(ClojureScript)"]
        Electron["Electron app\n(Windows-first)"]
    end

    subgraph SamuraiBFF["SamuraiBFF\n(API and orchestration)"]
        HTTP[HTTP /api + /auth]
        WSAudio[ws/audio]
        WSEvents[ws/events]
    end

    subgraph Xamurai["Xamurai (Python services)"]
        RTService["rtservice\n(Faster-Whisper + pyannote)"]
        QwenRT["qwen-rtservice\n(Qwen3-ASR + ForcedAligner + pyannote)"]
        WhisperXWorker["whisperx_worker\n(WhisperX + pyannote refinement)"]
        RecorderWorker["recorder_worker\n(session WAV)"]
        FinalizerWorker["finalizer_worker\n(WhisperX + pyannote final transcript)"]
    end

    Browser -->|HTTP /api + /auth| HTTP
    Browser -->|"WS audio\nWebSocket /ws/audio\nPCM16LE mono 16kHz"| WSAudio
    Browser ---|"WS events\nWebSocket /ws/events\nJSON events"| WSEvents

    Electron -->|HTTP /api + /auth| HTTP
    Electron -->|"WS audio\nWebSocket /ws/audio\nPCM16LE mono 16kHz"| WSAudio
    Electron ---|"WS events\nWebSocket /ws/events\nJSON events"| WSEvents

    SamuraiBFF -->|"configured gRPC track\nfaster-whisper"| RTService
    SamuraiBFF -->|"configured gRPC track\nqwen"| QwenRT

    subgraph Kafka["Kafka"]
        KafkaBroker[(Kafka broker)]
    end

    subgraph Storage["Storage"]
        ObjectStore[("S3-compatible object storage\n(Ceph etc., LocalStack in the local setup)")]
        Postgres[(PostgreSQL)]
    end

    SamuraiBFF -->|"produce protobuf AudioChunk\ntopic: audio.raw"| KafkaBroker
    SamuraiBFF -->|"produce compacted JSON\ntopic: sessions.meta"| KafkaBroker

    KafkaBroker -->|"consume protobuf RefinedEvent\ntopic: transcripts.refined"| SamuraiBFF
    KafkaBroker -->|"consume\ntopic: audio.raw"| WhisperXWorker
    WhisperXWorker -->|"produce protobuf RefinedEvent\ntopic: transcripts.refined"| KafkaBroker

    KafkaBroker -->|"consume\ntopic: audio.raw"| RecorderWorker
    RecorderWorker -->|"produce protobuf RecordingFinished\ntopic: recordings.finished"| KafkaBroker

    KafkaBroker -->|"consume\ntopic: recordings.finished"| FinalizerWorker
    FinalizerWorker -->|"produce protobuf SessionTranscript\ntopic: transcripts.final"| KafkaBroker

    RecorderWorker -->|"write session WAV"| ObjectStore
    FinalizerWorker -->|"read recording and speaker enrollments"| ObjectStore
    SamuraiBFF -->|"serve recordings; read/write speaker enrollments"| ObjectStore
    RTService -->|"read speaker enrollments"| ObjectStore
    WhisperXWorker -->|"read speaker enrollments"| ObjectStore

    KafkaBroker -->|"consume + persist\ntopic: transcripts.refined"| Persistor["SamuraiPersistor\n(PostgreSQL writer)"]
    KafkaBroker -->|"consume + persist\ntopic: transcripts.final"| Persistor
    Persistor -->|persist| Postgres
    SamuraiBFF -->|query| Postgres
```

The stack consists of:

- [xamurai](https://github.com/nanosamurai/xamurai) — this is a monorepo with all speech-to-text (STT) services, namely:
  - real time STT (rtservice)
  - semi-realtime STT (whisperx_worker)
  - batch STT (finalizer_worker)
  - recording service (recorder_worker)
- [samuraibff](https://github.com/nanosamurai/samuraibff) — HTTP/WebSocket API,
  browser UI, authentication, and orchestration
- [samuraipersistor](https://github.com/nanosamurai/samuraipersistor) —
  Kafka-to-PostgreSQL transcript persistence
- [nanosamurai-sdk](https://github.com/nanosamurai/nanosamurai-sdk) — Python
  SDK and CLI

Kafka carries audio and transcript events. PostgreSQL stores session and
transcript data. The evaluator uses LocalStack for S3-compatible recording and
speaker-enrollment storage; deployments can configure another S3-compatible
provider, such as AWS S3, Ceph RADOS Gateway, or MinIO.

See the [architecture guide](docs/architecture.md) for the request flow and
Community Edition boundary, including the object-storage replacement boundary.
API consumers should start with
[APIs and extension points](docs/apis-and-extension-points.md) for the generated
OpenAPI contract, Swagger UI, and BFF-owned protocol documentation.

## Quickstart

Prerequisites:

- Docker Desktop or Docker Engine
- Docker Compose v2
- free disk space for the selected images and speech models
- an NVIDIA container runtime and suitable GPU
- a least-privilege `HF_TOKEN` for required gated models

Create the local environment file:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Set `HF_TOKEN` in `.env`, then start the complete evaluator stack:

```bash
docker compose pull
docker compose up -d
docker compose ps --all
```

Open <http://127.0.0.1:8000/live>, select **Microphone**, and choose
**Record now**. Realtime results appear first; refined and final results arrive
asynchronously.

Model downloads and cold initialization can take several minutes. The speech
services request `gpus: all`; the default stack requires an NVIDIA GPU available
to Docker.

See
[Evaluator getting started](docs/getting-started.md) for success checks,
Windows/Linux instructions, the tested hardware disclosure, observability, and
safe reset commands.

## Optional observability

<img src="docs/tempo.png"/>

Start the local observability services with:

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d
```

The stack provisions Grafana with Prometheus, Loki, and Tempo data sources.
Prometheus also scrapes NVIDIA GPU utilization, framebuffer memory, temperature,
and power metrics from the bundled DCGM exporter.
Kafka carries W3C trace context so asynchronous session work can be correlated
across SamuraiBFF, the Python workers, SamuraiPersistor, Kafka, and PostgreSQL.

See [Operations and observability](docs/operations-and-observability.md) for
endpoints, available signals, trace behavior, and current limitations.

## Documentation

- [Documentation index](docs/README.md)
- [Evaluator getting started](docs/getting-started.md)
- [Transcription lifecycle](docs/transcription-lifecycle.md)
- [APIs and extension points](docs/apis-and-extension-points.md)
- [Architecture and Community Edition boundary](docs/architecture.md)
- [Authentication and bring-your-own Keycloak](docs/authentication.md)
- [Operations and observability](docs/operations-and-observability.md)
- [Deployment and security boundaries](docs/deployment-and-security.md)
- [Smoke tests and release rehearsal](docs/smoke-tests.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Image release policy](docs/image-release-policy.md)

Detailed API, WebSocket, SDK, speech-service, and persistence contracts remain
in their owning component repositories.

## Deployment boundary

Docker Compose is the supported public evaluation path. The containerized
services can be adapted to Kubernetes, but this repository does not supply
production Kubernetes manifests or charts.

Speech processing can run without a cloud speech API after container images,
models, and other dependencies have been staged. The normal quickstart
downloads those artifacts and is not a turnkey air-gap installation procedure.
See [Deployment and security boundaries](docs/deployment-and-security.md).

## Security

- All published host ports bind to `127.0.0.1` by default through
  `COMPOSE_BIND_IP`.
- The evaluator uses fixed development credentials and disables authentication
  for quick local access.
- Authenticated deployments must supply and operate their own Keycloak. See
  [Authentication and bring-your-own Keycloak](docs/authentication.md) for the
  required client, claims, tenant provisioning, and configuration.
- Do not expose this configuration to a LAN or public interface unless you intentionally want to do that.
- Never commit `.env`, tokens, recordings, transcripts, enrollment samples, or
  customer data.

The Compose credentials are intentionally fixed development values and are
safe only because services bind to localhost. This Compose stack is not a
production deployment manifest.

Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).
Contribution guidance is in [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) and
[NOTICE](NOTICE).
