<img src="docs/nanosamurai_logo_finished_shoulders.svg" width="100">

# [nanosamur.ai](https://nanosamur.ai)
guarding your sensitive conversations</sub>

<sub>Your voice. Your control.</sub>

## **Complete speech AI platform**

- open source
- production-grade, distributed architecture
- [model agnostic](#model-pipelines-in-the-supplied-stack)
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

## What nanosamur.ai includes
<img src="docs/main-art-large.png" width="35%" align="right">


- browser UI and SamuraiBFF API
- Windows-first Electron wrapper
- one or more independently selectable [**realtime transcription** models](#model-pipelines-in-the-supplied-stack)
- [**batch** and **semi-batch** processing](#model-pipelines-in-the-supplied-stack) with one or more models
- diarization (currently Pyannote or Sortformer), vad, alignment
- multi-tenancy support
- recording storage and full-session final transcripts
- PostgreSQL transcript persistence
- Python SDK and CLI source
- optional Grafana, Prometheus, Tempo, Loki, and Alloy stack
- public smoke tests and trace-context audit

The public code also includes agentic-workflow and webhook contracts.
Community Edition does not currently ship workflow execution or webhook delivery
services, but you are free to implement your own workflows / webhook services and plug them in.
<br clear="right">


## Architecture

```mermaid
flowchart LR
    subgraph Client
        Browser["Browser UI<br/>(ClojureScript)"]
        Electron["Electron app<br/>(Windows-first)"]
    end

    subgraph SamuraiBFF["SamuraiBFF<br/>(API and orchestration)"]
        HTTP[HTTP /api + /auth]
        WSAudio[ws/audio]
        WSEvents[ws/events]
    end

    subgraph Xamurai["Xamurai (Python services)"]
        RealtimeService["Realtime service<br/>[Faster-Whisper,<br/>Qwen3-ASR, Nemotron]"]
        RefinementService["Refinement service<br/>[WhisperX, Parakeet, Qwen3-ASR]"]
        RecorderWorker["recorder_worker<br/>(session WAV)"]
        FinalizerService["Finalizer service<br/>[WhisperX, Parakeet, Qwen3-ASR]"]
    end

    Browser -->|HTTP /api + /auth| HTTP
    Browser -->|"WS audio<br/>WebSocket /ws/audio<br/>PCM16LE mono 16kHz"| WSAudio
    Browser ---|"WS events<br/>WebSocket /ws/events<br/>JSON events"| WSEvents

    Electron -->|HTTP /api + /auth| HTTP
    Electron -->|"WS audio<br/>WebSocket /ws/audio<br/>PCM16LE mono 16kHz"| WSAudio
    Electron ---|"WS events<br/>WebSocket /ws/events<br/>JSON events"| WSEvents

    SamuraiBFF <-->|"gRPC streams per selected realtime track"| RealtimeService

    subgraph Kafka["Kafka"]
        KafkaBroker[(Kafka broker)]
    end

    subgraph Storage["Storage"]
        ObjectStore[("S3-compatible object storage<br/>(Ceph etc., LocalStack in the local setup)")]
        Postgres[(PostgreSQL)]
    end

    SamuraiBFF -->|"produce protobuf AudioChunk<br/>topic: audio.raw"| KafkaBroker
    SamuraiBFF -->|"produce compacted JSON<br/>topic: sessions.meta"| KafkaBroker

    KafkaBroker -->|"consume protobuf RefinedEvent<br/>topic: transcripts.refined"| SamuraiBFF
    KafkaBroker -->|"consume<br/>topic: audio.raw"| RefinementService
    RefinementService -->|"produce protobuf RefinedEvent<br/>topic: transcripts.refined"| KafkaBroker

    KafkaBroker -->|"consume<br/>topic: audio.raw"| RecorderWorker
    RecorderWorker -->|"produce protobuf RecordingFinished<br/>topic: recordings.finished"| KafkaBroker

    KafkaBroker -->|"consume<br/>topic: recordings.finished"| FinalizerService
    FinalizerService -->|"produce protobuf SessionTranscript<br/>topic: transcripts.final"| KafkaBroker

    RecorderWorker -->|"write session WAV"| ObjectStore
    FinalizerService -->|"read recording; optional speaker enrollments"| ObjectStore
    SamuraiBFF -->|"serve recordings; read/write speaker enrollments"| ObjectStore
    RealtimeService -->|"optional speaker enrollments"| ObjectStore
    RefinementService -->|"optional speaker enrollments"| ObjectStore

    KafkaBroker -->|"consume + persist<br/>topic: transcripts.refined"| Persistor["SamuraiPersistor<br/>(PostgreSQL writer)"]
    KafkaBroker -->|"consume + persist<br/>topic: transcripts.final"| Persistor
    Persistor -->|persist| Postgres
    SamuraiBFF -->|query| Postgres
```

Each speech-service box groups independently deployed, selectable tracks for
that stage; brackets list the supported model pipelines. Multiple selected
tracks produce separate labelled results. The [model matrix](#model-pipelines-in-the-supplied-stack)
below covers default and optional providers, model versions, alignment, and
diarization (pyannote or Sortformer). Speaker-enrollment access applies only to
pipelines that support it.

The stack consists of:

- [xamurai](https://github.com/nanosamurai/xamurai) contains the speech services:
  - `rtservice`, `qwen_rtservice` and `nemotron_rtservice`: realtime transcription.
  - `whisperx_worker`: one pipeline with refinement and finalizer entrypoints,
    built with `Dockerfile.refinement` and `Dockerfile.finalizer`.
  - `parakeet_worker`: Parakeet refinement and finalization with embedded Sortformer.
  - `qwen_worker`: batched vLLM refinement/finalization with pyannote speaker turns.
  - `nemo_speech_native`: native bindings and a shared Docker base for Nemotron and Parakeet.
  - `recorder_worker`: session audio storage.
  - `xamurai_serving.finalization`: the shared Kafka and recording loop for finalizers.
  - `xamurai_serving.refinement` and `refinement_runtime`: shared window buffering,
    publication and recovery for WhisperX, Parakeet and Qwen refinement.
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

## Supported Models

Realtime transcription gives you text while you speak. Refinement processes
short audio windows during the session. Final processing uses the complete
recording after you stop.

You can choose different models for each stage or use several models together.
Each model returns a separate result from the same audio.
This lets you compare live, refined, and final transcripts for your language and task.

The default stack uses Faster-Whisper for live text and WhisperX for refined
and final transcripts. You can add Qwen, Nemotron, or Parakeet when you need them.

### Model pipelines in the supplied stack

| Model family | Available output | Setup guide |
| --- | --- | --- |
| Whisper | Realtime, refined, and final; on by default | [Whisper](docs/models/whisper.md) |
| Qwen | Realtime, refined, and final | [Qwen](docs/models/qwen.md) |
| Nemotron | Realtime | [Nemotron](docs/models/nemotron.md) |
| Parakeet | Refined and final | [Parakeet](docs/models/parakeet.md) |

The [model guide](docs/models/README.md) explains how to add, select, or stop each model.
All model families have published container images. Each guide describes its setup.

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
[Getting started](docs/getting-started.md) for success checks,
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
- [Getting started](docs/getting-started.md)
- [Choose models](docs/models/README.md)
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
