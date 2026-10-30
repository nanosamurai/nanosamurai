# Choose models

Each model produces a separate transcript, called a **track**.
You can select different tracks for each stage:

- **Realtime**: text appears while you speak.
- **Refined**: the worker processes short audio windows during the session.
- **Final**: the worker processes the complete recording after you stop.

## What starts by default

The base `docker-compose.yml` runs NVIDIA Nemotron for realtime text and NVIDIA
Parakeet for refined and final transcripts. They are fast and accurate in English,
need no Hugging Face token, and use less GPU memory than the Whisper services.
The other families are optional overlays. You choose which setup runs.

| Model family | Realtime | Refined | Final | Installation |
| --- | --- | --- | --- | --- |
| [Nemotron](nemotron.md) | Nemotron 3.5 ASR | — | — | On by default |
| [Parakeet](parakeet.md) | — | Parakeet TDT v3 | Parakeet TDT v3 | On by default |
| [Whisper](whisper.md) | Faster-Whisper | WhisperX | WhisperX | Optional overlay |
| [Qwen](qwen.md) | Qwen3-ASR | Qwen3-ASR | Qwen3-ASR | Optional overlays |

The base stack also starts the browser UI, API, database, message broker,
recording service, and storage.

All families have images in [GHCR](https://github.com/orgs/nanosamurai/packages?repo_name=xamurai).
The base file, the Whisper overlay, and the Qwen realtime overlay select published images.
The Qwen worker overlay defaults to local image names. Its guide shows a local build.
See [image choices](source-builds.md#published-images-and-compose-defaults) for the published-image settings.

## Choose a setup

| Setup | Compose files |
| --- | --- |
| Default: Nemotron and Parakeet | `docker-compose.yml` |
| Whisper next to the defaults, for example to compare results | `docker-compose.yml` and `docker-compose.whisper.yml` |
| Whisper only | The Whisper files and [the replacement example](whisper.md#use-whisper-instead-of-nemotron-and-parakeet) |
| Qwen next to the defaults | `docker-compose.yml` and [one or both Qwen overlays](qwen.md) |

Nemotron and Parakeet also list other languages, including German.
This stack tests them with English. Whisper covers more languages and can match enrolled speaker names.
Compare the models with your own audio before you choose one for another language.

## Model sizes and variants

A model family can include several sizes or variants.
Each guide lists the available choices and the settings supported by this stack:
[Whisper](whisper.md#model-sizes-and-variants), [Qwen](qwen.md#model-sizes-and-variants),
[Nemotron](nemotron.md#model-sizes-and-variants), and [Parakeet](parakeet.md#model-sizes-and-variants).

Model size and computation precision are separate choices.
For example, `0.6B` describes the parameter count. Q8 and INT8 describe 8-bit representation.
The services download their selected model weights when needed.
They do not select a model size from available GPU memory.

## Select models for a session

1. Open **Session settings** before you start audio.
2. Select the models for each stage.
3. Disable any stage that you do not need.
4. If you select multiple final models, keep recording storage enabled.
5. Start the session.

Session selection does not stop containers or release their model memory.
Each running model process needs its own RAM and GPU memory.

## Set default tracks

A default track is the initial model choice for a stage.
It applies when that stage is enabled and the session has no explicit track selection.
An explicit selection takes priority, including a choice of multiple tracks.
A default does not enable a disabled stage or change a session after audio starts.

Set one track ID per stage in `.env`. Leave a value blank to use the behavior below:

| Stage | Setting | Choice when blank |
| --- | --- | --- |
| Realtime | `SAMURAIBFF_DEFAULT_REALTIME_TRACK` | All configured realtime tracks |
| Refined | `SAMURAIBFF_DEFAULT_REFINEMENT_TRACK` | First configured refined track |
| Final | `SAMURAIBFF_DEFAULT_FINAL_TRACK` | First configured final track |

Thus, the Whisper and Qwen realtime overlays select two realtime models when no default is set.
The Whisper and Qwen worker overlays list Parakeet first, so it remains the initial refined and final choice.

For example, after you [add Whisper](whisper.md#add-whisper), set these values in `.env`:

```dotenv
SAMURAIBFF_DEFAULT_REALTIME_TRACK=faster-whisper
SAMURAIBFF_DEFAULT_REFINEMENT_TRACK=whisperx
SAMURAIBFF_DEFAULT_FINAL_TRACK=whisperx
```

This selects Whisper for every stage.
Nemotron and Parakeet remain available in **Session settings**, and their containers continue to run.

Finish active sessions. Repeat your startup command to apply the settings.
For this example:

```bash
docker compose -f docker-compose.yml -f docker-compose.whisper.yml up -d
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

For example, this file list starts the base stack with the Whisper models:

```bash
docker compose -f docker-compose.yml -f docker-compose.whisper.yml up -d
```

You can append `-f docker-compose.observability.yml` before `up` to add monitoring.
Explicit `-f` options replace the file list in `COMPOSE_FILE`.
If you already use local overlays, include those files too.
Keep the same Compose project name to retain access to your existing volumes.

## Stop or replace a model

Finish active sessions before you change the running models.
To turn a model off for one session, clear its selection in **Session settings**.
To release its memory, stop its container as well.

For example, stop both Parakeet workers when you only need realtime text:

```bash
docker compose -f docker-compose.yml stop parakeet-refinement parakeet-finalizer
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
      SAMURAIBFF_GRPC_REALTIME_TRACKS: nemotron=nemotron-rtservice:50052,faster-whisper=rtservice:50052,qwen=qwen-rtservice:50052
      SAMURAIBFF_REFINEMENT_TRACKS: parakeet,whisperx,qwen
      SAMURAIBFF_FINAL_TRACKS: parakeet,whisperx,qwen
      SAMURAIBFF_TRACK_LABELS: '{"refined":{"parakeet":"Parakeet TDT v3","whisperx":"WhisperX","qwen":"Qwen3-ASR"},"final":{"parakeet":"Parakeet TDT v3","whisperx":"WhisperX","qwen":"Qwen3-ASR"}}'
```

Include the Whisper overlay and both Qwen overlays before this local file.
Build the Qwen worker images before startup. Register only tracks whose services you run.
With blank default settings, Parakeet stays selected because it is first in each worker track list.
Do not combine this example with settings that set those services to zero replicas.

Check the configuration without printing token values:

```bash
docker compose -f docker-compose.yml -f docker-compose.whisper.yml -f docker-compose.qwen.yml -f docker-compose.qwen-workers.yml -f docker-compose.local-asr.yml config --quiet
```

Start fewer model processes if your machine cannot hold them all in memory.

## Upgrade from the Whisper default

Earlier versions of this repository started Whisper by default, and
`docker-compose.nemotron.yml` and `docker-compose.parakeet.yml` added the other models.
Those files are now `docker-compose.nemotron-smoke.yml` and `docker-compose.parakeet-smoke.yml`.
They hold only test services, because the models start with the base file.
Nemotron also starts one replica instead of two.

Finish active sessions. Choose one of these before your next `up -d`:

- To keep Whisper, add `-f docker-compose.whisper.yml` after `docker-compose.yml` in every command.
  Its services, track IDs, and model cache volume stay the same.
- To stop Whisper, stop its containers with the Whisper file list first:

  ```bash
  docker compose -f docker-compose.yml -f docker-compose.whisper.yml stop rtservice whisperx_refinement whisperx_finalizer
  ```

  Then start the base stack. Saved Whisper transcripts stay available.

Remove `docker-compose.nemotron.yml` and `docker-compose.parakeet.yml` from your file list.
Also remove local settings that only repeat their old track lists.
The Nemotron and Parakeet model caches use the same volumes as before.
Clear any default track setting that names a model you no longer run.
