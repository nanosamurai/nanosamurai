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

Refined and final model selection requires the [source-built stack](source-builds.md).
The base published images predate this feature. Realtime selection works with
the published base and Qwen realtime images.

Session selection does not stop containers or release their model memory.
Each running model process needs its own RAM and GPU memory.

## Set default tracks

A default track is the initial model choice for a stage.
It applies when that stage is enabled and the session has no explicit track selection.
An explicit selection takes priority, including a choice of multiple tracks.
A default does not enable a disabled stage or change a session after audio starts.

These settings require a BFF image with default-track support.
The pinned base image predates this feature. Complete the [source-build setup](source-builds.md) before you use them.

Set one track ID per stage in `.env`. Leave a value blank to use the behavior below:

| Stage | Setting | Choice when blank |
| --- | --- | --- |
| Realtime | `SAMURAIBFF_DEFAULT_REALTIME_TRACK` | All configured realtime tracks |
| Refined | `SAMURAIBFF_DEFAULT_REFINEMENT_TRACK` | First configured refined track |
| Final | `SAMURAIBFF_DEFAULT_FINAL_TRACK` | First configured final track |

Thus, the Qwen realtime overlay selects both Faster-Whisper and Qwen when no default is set.
The Parakeet and Qwen worker overlays list WhisperX first, so it remains the initial choice.

For example, after you add [Qwen realtime](qwen.md#add-realtime-transcription), set these values in `.env`:

```dotenv
SAMURAIBFF_DEFAULT_REALTIME_TRACK=qwen
SAMURAIBFF_DEFAULT_REFINEMENT_TRACK=whisperx
SAMURAIBFF_DEFAULT_FINAL_TRACK=whisperx
```

This selects Qwen for realtime text and WhisperX for refined and final output.
Faster-Whisper remains available in **Session settings**, and its container continues to run.

Finish active sessions. Repeat your startup command to apply the settings.
For this example:

```bash
docker compose -f docker-compose.yml -f docker-compose.qwen.yml up -d --no-build --pull never
```

Include any other overlays from your existing file list.
Compose recreates BFF when its settings change. A `restart` command does not apply changes from `.env`.
Reload the UI before you create a new session.
Check **Session settings**; any explicit choices already in the browser take priority.

Each default must be in that stage's configured track list:
`SAMURAIBFF_GRPC_REALTIME_TRACKS`, `SAMURAIBFF_REFINEMENT_TRACKS`, or `SAMURAIBFF_FINAL_TRACKS`.
For realtime, use the ID before `=`, such as `qwen`, without the service address.
An unknown ID prevents BFF startup. Before you remove a track, clear or change its default.

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
If a replacement removes your default track, [change or clear that default](#set-default-tracks).
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
With blank default settings, WhisperX stays selected because it is first in each worker track list.
Do not combine this example with settings that set those services to zero replicas.

Check the configuration without printing token values:

```bash
docker compose -f docker-compose.yml -f docker-compose.qwen.yml -f docker-compose.nemotron.yml -f docker-compose.parakeet.yml -f docker-compose.qwen-workers.yml -f docker-compose.local-asr.yml config --quiet
```

Start fewer model processes if your machine cannot hold them all in memory.
