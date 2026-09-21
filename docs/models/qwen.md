# Qwen

Qwen3-ASR can provide realtime, refined, and final transcripts.
Each stage runs in a separate service. All Qwen services are off by default.
They need an NVIDIA GPU and `HF_TOKEN` access to pyannote models.

## Model sizes and variants

Qwen publishes **0.6B** and **1.7B** ASR models.
Both support realtime and offline transcription through the same upstream APIs.
See the [Qwen3-ASR model card](https://huggingface.co/Qwen/Qwen3-ASR-1.7B).

The current realtime service and workers select `Qwen/Qwen3-ASR-0.6B`.
Their adapter fixes the model ID, revision, and checksum.
There is no environment setting to select 1.7B or choose a size from available GPU memory.
Using 1.7B requires an adapter update and validation before deployment.

`Qwen3-ForcedAligner-0.6B` is a separate model for timing information.
Upstream supports this aligner with either ASR size.
`QWEN_KV_CACHE_MIB` controls cache memory; it does not change the ASR model size.

## Add realtime transcription

This path uses a published image. Complete [Getting started](../getting-started.md) first,
or use these commands for the first startup after you create `.env`:

```bash
docker compose -f docker-compose.yml -f docker-compose.qwen.yml pull
docker compose -f docker-compose.yml -f docker-compose.qwen.yml up -d
docker compose -f docker-compose.yml -f docker-compose.qwen.yml logs --tail=100 qwen-rtservice
```

The overlay adds `qwen-rtservice` and keeps the default Whisper services running.
With no realtime default set, Faster-Whisper and Qwen are both selected.
In **Session settings**, select either model or both before you start audio.
To make Qwen the initial choice, [set the realtime default](README.md#set-default-tracks) to `qwen`.

If you already use source-built base images, pull only `qwen-rtservice` with this file list.
Then use `up -d --no-build --pull never` to preserve your local images.

```bash
docker compose -f docker-compose.yml -f docker-compose.qwen.yml pull qwen-rtservice
```

Qwen processes a continuous stream in bounded intervals, called epochs.
The default epoch is 60 seconds. Speaker labels apply only within each epoch.
For languages supported by its forced aligner, Qwen adds segment timing and speaker labels.
Other languages, including Czech, get text without speaker labels.
Realtime output does not provide word timing.

### Use Qwen instead of Faster-Whisper

Add this to your ignored `docker-compose.local-asr.yml`:

```yaml
services:
  rtservice:
    deploy:
      replicas: 0
  samuraibff:
    environment:
      SAMURAIBFF_GRPC_REALTIME_TRACKS: qwen=qwen-rtservice:50052
```

Apply it with the Qwen overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.qwen.yml -f docker-compose.local-asr.yml up -d
```

This stops Faster-Whisper and offers only Qwen for realtime output.
WhisperX still provides refined and final output.
Keep this file list for later commands.

## Add refined and final transcription

The commands below use local builds. Complete [Prepare source-built models](source-builds.md) for this path.
GHCR worker images are also available; see [image choices](source-builds.md#published-images-and-compose-defaults).
From the repository root, build the workers:

```bash
docker compose -f docker-compose.yml -f docker-compose.qwen-workers.yml build qwen-finalizer qwen-refinement
docker compose -f docker-compose.yml -f docker-compose.qwen-workers.yml up -d --no-build --pull never
docker compose -f docker-compose.yml -f docker-compose.qwen-workers.yml logs --tail=100 qwen-refinement qwen-finalizer
```

The overlay adds Qwen to the **Refined** and **Final** model lists.
With no defaults set, WhisperX remains selected. Select Qwen in each stage that you need.
To make Qwen the initial choice, set the [refined and final defaults](README.md#set-default-tracks) to `qwen`.
Qwen realtime is independent; add its overlay if you also want that stage.

Qwen workers add speaker labels and word timing where alignment succeeds.
They do not match enrolled speaker names. Labels restart for each refinement window or final recording.
Final playback highlights words that have timing data.

### Use Qwen instead of WhisperX

Add these settings to your local overlay:

```yaml
services:
  whisperx_refinement:
    deploy:
      replicas: 0
  whisperx_finalizer:
    deploy:
      replicas: 0
  samuraibff:
    environment:
      SAMURAIBFF_REFINEMENT_TRACKS: qwen
      SAMURAIBFF_FINAL_TRACKS: qwen
      SAMURAIBFF_TRACK_LABELS: '{"refined":{"qwen":"Qwen3-ASR"},"final":{"qwen":"Qwen3-ASR"}}'
```

Apply it after the worker overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.qwen-workers.yml -f docker-compose.local-asr.yml up -d --no-build --pull never
```

This stops the WhisperX workers. Qwen becomes the only refined and final choice.
Faster-Whisper still runs unless you also apply the realtime replacement above.
For all-Qwen processing, combine both YAML examples under one `services` map
and include both Qwen overlays before the local file.

```bash
docker compose -f docker-compose.yml -f docker-compose.qwen.yml -f docker-compose.qwen-workers.yml -f docker-compose.local-asr.yml up -d --no-build --pull never
```

## Remove Qwen

With the file list that started Qwen, stop `qwen-rtservice`, `qwen-refinement`,
and `qwen-finalizer` as applicable. Remove their overlays from your file list.
Clear any default track settings that name `qwen`.
Remove any Qwen replacement settings from your local file, then start the base stack.
This restores the Whisper defaults and retains model caches and saved data.

## Checks and settings

Use the [model checks](../model-checks.md) to validate realtime or worker output.
The realtime cache allocation defaults to 512 MiB; each worker defaults to 1024 MiB.
The shared `QWEN_KV_CACHE_MIB` override affects every Qwen service that uses it.
These values cover the vLLM cache, not total GPU memory.
See Xamurai's [Qwen worker guide](https://github.com/nanosamurai/xamurai/blob/master/docs/qwen-workers.md)
for limits and tuning.
