# Choose models

Each model produces a separate transcript, called a **track**.
You can select different tracks for each stage:

- **Realtime**: text appears while you speak.
- **Refined**: the worker processes short audio windows during the session.
- **Final**: the worker processes the complete recording after you stop.

## What starts by default

| Model family | Realtime | Refined | Final | Installation |
| --- | --- | --- | --- | --- |
| [Whisper](whisper.md) | Faster-Whisper medium | WhisperX medium | WhisperX medium | On by default; published images |
| [Qwen](qwen.md) | Qwen3-ASR 0.6B | Qwen3-ASR 0.6B | Qwen3-ASR 0.6B | Optional; published realtime image, source builds for workers |
| [Nemotron](nemotron.md) | Nemotron 3.5 ASR 0.6B | — | — | Optional; source build |
| [Parakeet](parakeet.md) | — | Parakeet TDT 0.6B v3 | Parakeet TDT 0.6B v3 | Optional; source build |

The base stack also starts the browser UI, API, database, message broker,
recording service, and storage. Qwen, Nemotron, and Parakeet are off by default.

## Select models for a session

1. Open **Session settings** before you start audio.
2. Select the models for each stage.
3. Disable any stage that you do not need.
4. If you select multiple final models, keep recording storage enabled.
5. Start the session.

The Qwen realtime overlay selects both realtime tracks by default.
The Parakeet and Qwen worker overlays keep WhisperX as the default refined and
final track. Select the additional tracks in each stage to use them.

Refined and final model selection requires the [source-built stack](source-builds.md).
The base published images predate this feature. Realtime selection works with
the published base and Qwen realtime images.

Session selection does not stop containers or release their model memory.
Each running model process needs its own RAM and GPU memory.

## Keep your Compose file list

An **overlay** is an extra Compose file that adds or changes services.
Run commands from the repository root. Put `docker-compose.yml` first.
Use the same file list for `up`, `ps`, `logs`, `stop`, and `down`.

For example, this file list starts the base stack with Qwen realtime:

```bash
docker compose -f docker-compose.yml -f docker-compose.qwen.yml up -d
```

You can append `-f docker-compose.observability.yml` before `up` to add monitoring.
Explicit `-f` options replace the file list in `COMPOSE_FILE`.
If you already use local overlays, include those files too.
Keep the same Compose project name to retain access to your existing volumes.

## Stop or replace a model

Finish active sessions before you change the running models.
To turn a model off for one session, clear its selection in **Session settings**.
To release its memory, stop its container as well.

For example, stop both WhisperX workers when you only need realtime text:

```bash
docker compose -f docker-compose.yml stop whisperx_refinement whisperx_finalizer
```

Disable **Refined** and **Final** before the next session.
The models can still appear in the UI while their workers are stopped.
An ordinary `up -d` starts them again.

For a permanent local choice, use the replacement example in the model guide.
These examples use `deploy.replicas: 0` and change the API's available tracks.
Add the example to `docker-compose.local-asr.yml`, which Git ignores.
If that file exists, merge the settings into it. Do not replace its other settings.
Include it last in every Compose command.

To remove an optional model, stop its services with the old file list first.
Then remove its overlay and any related local track settings.
Start the remaining stack with the new file list.
Removing a file from the command alone does not stop its existing containers.
Do not delete volumes to change models.

## Combine model families

Realtime and worker overlays control different stages. You can combine them.
However, two overlays for the same stage replace the same track list;
Compose does not join comma-separated values. See [Compose merge rules](https://docs.docker.com/reference/compose-file/merge/).

For example, add these settings to your last local overlay to offer all families:

```yaml
services:
  samuraibff:
    environment:
      SAMURAIBFF_GRPC_REALTIME_TRACKS: faster-whisper=rtservice:50052,qwen=qwen-rtservice:50052,nemotron=nemotron-rtservice:50052
      SAMURAIBFF_REFINEMENT_TRACKS: whisperx,parakeet,qwen
      SAMURAIBFF_FINAL_TRACKS: whisperx,parakeet,qwen
      SAMURAIBFF_TRACK_LABELS: '{"refined":{"whisperx":"WhisperX","parakeet":"Parakeet TDT v3","qwen":"Qwen3-ASR"},"final":{"whisperx":"WhisperX","parakeet":"Parakeet TDT v3","qwen":"Qwen3-ASR"}}'
```

Include all four model overlays before this local file.
Build their images before startup. Register only tracks whose services you run.
Keep WhisperX first to retain the default refined and final selection.
Do not combine this example with settings that set those services to zero replicas.

Check the configuration without printing token values:

```bash
docker compose -f docker-compose.yml -f docker-compose.qwen.yml -f docker-compose.nemotron.yml -f docker-compose.parakeet.yml -f docker-compose.qwen-workers.yml -f docker-compose.local-asr.yml config --quiet
```

Start fewer model processes if your machine cannot hold them all in memory.
