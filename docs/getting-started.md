# Getting started

This guide starts a local stack and takes you to your first transcript.
The stack uses development credentials and binds ports to `127.0.0.1`.
Keep it local. See [Deployment and security](deployment-and-security.md) before you plan a shared deployment.

## What you will run

The default stack starts three speech services:

| Stage | Model | What you get |
| --- | --- | --- |
| Realtime | Faster-Whisper | Text while you speak |
| Refined | WhisperX | Speaker-labelled text from short audio windows |
| Final | WhisperX | A transcript of the complete recording after you stop |

The browser UI, API, database, recording service, and storage start with them.
All three output stages and recording storage are enabled by default.
See [model sizes and variants](models/whisper.md#model-sizes-and-variants) for the current Whisper settings and size choices.

Qwen, Nemotron, and Parakeet are off by default.
To use another model, follow [Choose models](models/README.md).
Each family has its own setup guide:
[Whisper](models/whisper.md), [Qwen](models/qwen.md),
[Nemotron](models/nemotron.md), and [Parakeet](models/parakeet.md).

## Before you start

You need:

- Git.
- Docker Desktop or Docker Engine with Docker Compose v2.
- An NVIDIA GPU that Docker can access.
- Disk space for container images and model downloads.
- A Hugging Face account and a token with the required model-read permissions.

Accept the access conditions for
[pyannote speaker diarization](https://huggingface.co/pyannote/speaker-diarization-3.1)
and [pyannote segmentation](https://huggingface.co/pyannote/segmentation-3.0).
Create the token with the same account.

The default stack requires GPU access. It has no automatic CPU fallback.
The release rehearsal used an RTX 5090 Laptop GPU with 24 GB of GPU memory.
This is a tested configuration, not a minimum requirement.
More running model services need more RAM and GPU memory.

## 1. Get the stack

Run:

```bash
git clone https://github.com/nanosamurai/nanosamurai.git
cd nanosamurai
```

Create your local settings file.

Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Open `.env` in an editor. Set `HF_TOKEN` to your Hugging Face token.
Keep `COMPOSE_BIND_IP=127.0.0.1`. Do not commit `.env`.

## 2. Start the default models

Run these commands from the repository root:

```bash
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d
docker compose -f docker-compose.yml ps --all
```

The first startup can take several minutes while services download and load models.
Check their progress:

```bash
docker compose -f docker-compose.yml logs --tail=100 rtservice whisperx_refinement whisperx_finalizer
```

The setup jobs `kafka_init`, `db_migrate`, and `db_seed` should finish with exit code 0.
The other services should stay running.
Wait for model initialization to finish before you send audio.
If a service exits or repeatedly restarts, see [Troubleshooting](troubleshooting.md).

## 3. Make a transcript

1. Open [the local browser UI](http://127.0.0.1:8000/live).
2. Select **Microphone**.
3. Select the language, or keep automatic language detection.
4. Open **Session settings**.
5. Keep realtime, refined, final, and recording output enabled for this first session.
6. Select **Record now**.
7. Allow microphone access when the browser asks.
8. Speak, then select **Stop**.
9. Open the saved session after the final transcript is ready.

Realtime text appears first. Refined text appears after each processing window.
The final transcript appears after the recording and final processing finish.
First-use alignment downloads can add a delay.

For a repeatable check with supplied audio, use [Smoke tests](smoke-tests.md).
See [Transcription lifecycle](transcription-lifecycle.md) for the differences between outputs.

## 4. Choose what runs next

To disable an output for one session, turn it off in **Session settings** before you start audio.
This prevents processing for that stage. It does not stop its container.

You can also [set a default track for each stage](models/README.md#set-default-tracks).
A default applies when the stage is enabled and the session has no explicit model choice.
This requires a newer BFF image; the linked guide includes the setup steps.

To add or replace a model, use its guide:

- [Whisper](models/whisper.md): use the defaults or change the WhisperX model size.
- [Qwen](models/qwen.md): add realtime text, refined output, or final transcripts.
- [Nemotron](models/nemotron.md): add a realtime service with optional speaker labels.
- [Parakeet](models/parakeet.md): add refined and final workers with word timing.

The guides show how to stop the default model services and replace their track settings.
For file order, combined models, and memory use, see [Choose models](models/README.md).

## Add monitoring

The optional monitoring stack shows logs, metrics, and traces:

```bash
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d
```

Open [Grafana](http://127.0.0.1:3001) with the local credentials `admin` / `admin`.
If you use model overlays, include them in this command too.
See [Operations and observability](operations-and-observability.md) for more details.

## Stop and restart

For the default stack:

```bash
docker compose -f docker-compose.yml down
```

Use the same file list that started the stack, including any model or monitoring overlays.
The command retains saved data and model caches.
Repeat your `up -d` command to restart.

Do not add `-v` unless you intend to delete the stack's named volumes.
That option deletes local transcripts, recordings, database state, and model caches.
