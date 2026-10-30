# Getting started

This guide starts a local stack and takes you to your first transcript.
The stack uses development credentials and binds ports to `127.0.0.1`.
Keep it local. See [Deployment and security](deployment-and-security.md) before you plan a shared deployment.

## What you will run

The default stack starts three speech services:

| Stage | Model | What you get |
| --- | --- | --- |
| Realtime | Nemotron 3.5 ASR | Text while you speak |
| Refined | Parakeet TDT v3 | Speaker-labelled text from short audio windows |
| Final | Parakeet TDT v3 | A transcript of the complete recording after you stop |

These NVIDIA models are fast and accurate in English. They need no Hugging Face token.
The browser UI, API, database, recording service, and storage start with them.
All three output stages and recording storage are enabled by default.

Whisper and Qwen are optional overlays. They cover more languages and need a Hugging Face token.
To use another model, follow [Choose models](models/README.md).
Each family has its own setup guide:
[Nemotron](models/nemotron.md), [Parakeet](models/parakeet.md),
[Whisper](models/whisper.md), and [Qwen](models/qwen.md).
If you used an earlier version with Whisper as the default, see
[Upgrade from the Whisper default](models/README.md#upgrade-from-the-whisper-default).

## Before you start

You need:

- Git.
- Docker Desktop or Docker Engine with Docker Compose v2.
- An NVIDIA GPU that Docker can access.
- Disk space for container images and model downloads.

The default models download from Hugging Face on first start without a token.
Their licenses are on the model cards:
[Nemotron 3.5 ASR](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b) (OpenMDW-1.1),
[Parakeet TDT v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) and
[Sortformer](https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2) (CC BY 4.0).

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

Keep `COMPOSE_BIND_IP=127.0.0.1` in `.env`. Do not commit `.env`.
The default models need no other settings. `HF_TOKEN` is needed only for Whisper or Qwen.

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
docker compose -f docker-compose.yml logs --tail=100 nemotron-rtservice parakeet-refinement parakeet-finalizer
```

The setup jobs `kafka_init`, `db_migrate`, and `db_seed` should finish with exit code 0.
The other services should stay running.
Wait for model initialization to finish before you send audio.
If a service exits or repeatedly restarts, see [Troubleshooting](troubleshooting.md).

## 3. Make a transcript

1. Open [the local browser UI](http://127.0.0.1:8000/live).
2. Select **Microphone**.
3. Select English, or keep automatic language detection.
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

To add or replace a model, use its guide:

- [Nemotron](models/nemotron.md): change the chunk size, add replicas, or add speaker labels.
- [Parakeet](models/parakeet.md): compare or replace the refined and final model.
- [Whisper](models/whisper.md): add Faster-Whisper and WhisperX, or use them instead of the defaults.
- [Qwen](models/qwen.md): add realtime text, refined output, or final transcripts.

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
