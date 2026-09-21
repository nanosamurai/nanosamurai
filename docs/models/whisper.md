# Whisper

Whisper is the default model family. No extra Compose file is required.

| Stage | Service | Track ID | Pipeline |
| --- | --- | --- | --- |
| Realtime | `rtservice` | `faster-whisper` | Faster-Whisper |
| Refined | `whisperx_refinement` | `whisperx` | WhisperX |
| Final | `whisperx_finalizer` | `whisperx` | WhisperX |

All three services use pyannote for speaker labels. The finalizer also adds
word timing where alignment succeeds. Refinement uses segment timing by default.

## Model sizes and variants

Faster-Whisper and WhisperX run models from the Whisper family.
Whisper sizes include `tiny`, `base`, `small`, `medium`, and `large`.
The large models have several versions, including `large-v2` and `large-v3`.
The smaller sizes also have English-only variants with an `.en` suffix.
See the [Whisper model card](https://huggingface.co/openai/whisper-large-v3#model-details).
The backend also supports variants such as `large-v3-turbo`; see its [model names](https://github.com/SYSTRAN/faster-whisper/blob/v1.2.0/faster_whisper/utils.py).

The WhisperX workers use `medium` by default.
Set `WHISPERX_MODEL` on each worker to select another size or version.
Refined and final workers can use different sizes. See [Change the WhisperX model size](#change-the-whisperx-model-size).
The workers download the selected weights when needed. They do not select a size from available GPU memory.

The realtime adapter currently selects `Systran/faster-whisper-medium`.
It has no environment setting for another Whisper size. Changing that selection requires a service code update.
This is a limit of the current adapter.

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

This setting changes the WhisperX model weights. The service image and track IDs stay the same.
It does not change the realtime model.

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

Use `small` instead of `large-v3` in the example if you need a smaller model.
Finish active sessions, then apply the change:

```bash
docker compose -f docker-compose.yml -f docker-compose.local-asr.yml up -d
```

Include any other overlays from your existing file list.
The new model downloads on first use. Each worker loads its own copy into memory.
Check available GPU memory before you change model size.
WhisperX also accepts `WHISPERX_COMPUTE_TYPE`, for example `int8`, to change computation precision.
That setting does not select a smaller model. See [WhisperX memory guidance](https://github.com/m-bain/whisperX).
Remove both `WHISPERX_MODEL` overrides to return to `medium`, then repeat the command.

For service settings, see the [Xamurai documentation](https://github.com/nanosamurai/xamurai/tree/master/docs).
