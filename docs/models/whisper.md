# Whisper

Whisper is an optional model family. `docker-compose.whisper.yml` adds three services:

| Stage | Service | Track ID | Pipeline |
| --- | --- | --- | --- |
| Realtime | `rtservice` | `faster-whisper` | Faster-Whisper |
| Refined | `whisperx_refinement` | `whisperx` | WhisperX |
| Final | `whisperx_finalizer` | `whisperx` | WhisperX |

All three services use pyannote for speaker labels and can match enrolled speaker names.
The finalizer also adds word timing where alignment succeeds. Refinement uses segment timing by default.
Whisper covers more languages than the default models.

## Add Whisper

Complete the [getting-started prerequisites](../getting-started.md#before-you-start).
Accept the access conditions for
[pyannote speaker diarization](https://huggingface.co/pyannote/speaker-diarization-3.1)
and [pyannote segmentation](https://huggingface.co/pyannote/segmentation-3.0).
Create a Hugging Face token with the same account. Give it only model-read access.
Set `HF_TOKEN` in `.env`, then run:

```bash
docker compose -f docker-compose.yml -f docker-compose.whisper.yml pull
docker compose -f docker-compose.yml -f docker-compose.whisper.yml up -d
docker compose -f docker-compose.yml -f docker-compose.whisper.yml logs --tail=100 rtservice whisperx_refinement whisperx_finalizer
```

Wait for model initialization before you start a session.
The overlay adds the Whisper tracks next to Nemotron and Parakeet.
With no defaults set, both realtime models are selected, and Parakeet stays the initial refined and final choice.
In **Session settings**, select the models for each stage.
To start with Whisper, [set the default tracks](README.md#set-default-tracks).
Use the same file list for later commands.

## Use Whisper instead of Nemotron and Parakeet

Add this to your ignored `docker-compose.local-asr.yml`:

```yaml
services:
  nemotron-rtservice:
    deploy:
      replicas: 0
  parakeet-refinement:
    deploy:
      replicas: 0
  parakeet-finalizer:
    deploy:
      replicas: 0
  samuraibff:
    environment:
      SAMURAIBFF_GRPC_REALTIME_TRACKS: faster-whisper=rtservice:50052
      SAMURAIBFF_REFINEMENT_TRACKS: whisperx
      SAMURAIBFF_FINAL_TRACKS: whisperx
      SAMURAIBFF_TRACK_LABELS: '{"refined":{"whisperx":"WhisperX"},"final":{"whisperx":"WhisperX"}}'
```

Finish active sessions, then apply the change:

```bash
docker compose -f docker-compose.yml -f docker-compose.whisper.yml -f docker-compose.local-asr.yml up -d
```

This stops Nemotron and Parakeet and offers only Whisper.
To keep one default model, omit its zero-replica setting and keep its track ID in that stage's list.
Clear any default track setting that names a stopped model.

## Turn off a stage

Disable the stage in **Session settings** before you start audio.
To release worker memory too, follow [Stop or replace a model](README.md#stop-or-replace-a-model).

## Shared WhisperX track

Xamurai's optional `whisperx-shared` track runs refinement and finalization in one
process and loads Whisper ASR once, reducing GPU memory use compared with separate workers.
It can batch compatible ASR requests and align different preloaded languages in
parallel while ASR continues. Both stages share capacity and must scale together;
keep the separate `whisperx` workers when independent scaling matters.

This requires an Xamurai build with the combined worker and explicit worker/BFF
track configuration. The supplied Whisper overlay still uses separate workers.
See the [shared-worker guide](https://github.com/nanosamurai/xamurai/blob/f742f8e333df5ee5fd78d7da4378f30e02daedb5/docs/whisperx-shared.md) for setup and limits.

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
docker compose -f docker-compose.yml -f docker-compose.whisper.yml -f docker-compose.local-asr.yml up -d
```

Include any other overlays from your existing file list.
The new model downloads on first use. Each worker loads its own copy into memory.
Check available GPU memory before you change model size.
WhisperX also accepts `WHISPERX_COMPUTE_TYPE`, for example `int8`, to change computation precision.
That setting does not select a smaller model. See [WhisperX memory guidance](https://github.com/m-bain/whisperX).
Remove both `WHISPERX_MODEL` overrides to return to `medium`, then repeat the command.

## Monitoring

With [monitoring](../operations-and-observability.md), add `docker-compose.whisper-observability.yml`
after `docker-compose.observability.yml` to trace the Whisper services too.

## Remove Whisper

Stop `rtservice`, `whisperx_refinement`, and `whisperx_finalizer` with the file list that started them.
Remove the Whisper overlays and any local settings that name Whisper tracks.
Clear any default track setting that names `faster-whisper` or `whisperx`.
Start the remaining stack. Saved transcripts and the model cache stay available.

For service settings, see the [Xamurai documentation](https://github.com/nanosamurai/xamurai/tree/master/docs).
