# Whisper

Whisper is the default model family. No extra Compose file is required.

| Stage | Service | Track ID | Model |
| --- | --- | --- | --- |
| Realtime | `rtservice` | `faster-whisper` | `Systran/faster-whisper-medium` |
| Refined | `whisperx_refinement` | `whisperx` | WhisperX `medium` |
| Final | `whisperx_finalizer` | `whisperx` | WhisperX `medium` |

All three services use pyannote for speaker labels. The finalizer also adds
word timing where alignment succeeds. Refinement uses segment timing by default.

## Start

Complete the [getting-started prerequisites](../getting-started.md#before-you-start).
Set `HF_TOKEN` in `.env`, then run:

```bash
docker compose -f docker-compose.yml pull
docker compose -f docker-compose.yml up -d
docker compose -f docker-compose.yml logs --tail=100 rtservice whisperx_refinement whisperx_finalizer
```

Wait for model initialization before you start a session.
Realtime, refined, and final output are enabled by default.

## Turn off a stage

Disable the stage in **Session settings** before you start audio.
To release worker memory too, follow [Stop or replace a model](README.md#stop-or-replace-a-model).

To replace Whisper with another family, use the [Qwen](qwen.md),
[Nemotron](nemotron.md), or [Parakeet](parakeet.md) guide.
Keep at least one realtime service available for the API readiness check.

## Change the WhisperX model size

The realtime Faster-Whisper service uses a fixed `medium` model profile.
It does not accept a different model name from the browser.
WhisperX workers support `WHISPERX_MODEL`.

To use `large-v3` for refined and final output, add this to
`docker-compose.local-asr.yml`:

```yaml
services:
  whisperx_refinement:
    environment:
      WHISPERX_MODEL: large-v3
  whisperx_finalizer:
    environment:
      WHISPERX_MODEL: large-v3
```

Apply the change:

```bash
docker compose -f docker-compose.yml -f docker-compose.local-asr.yml up -d
```

The new model downloads on first use. Each worker loads its own copy into memory.
Check available GPU memory before you change model size.
Remove these two settings to return to `medium`, then repeat the command.

For service settings, see the [Xamurai documentation](https://github.com/nanosamurai/xamurai/tree/master/docs).
