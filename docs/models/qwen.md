# Qwen

Qwen3-ASR 0.6B can provide realtime, refined, and final transcripts.
Each stage runs in a separate service. All Qwen services are off by default.
They need an NVIDIA GPU and `HF_TOKEN` access to pyannote models.

## Add realtime transcription

This path uses a published image. Complete [Getting started](../getting-started.md) first,
or use these commands for the first startup after you create `.env`:

```bash
docker compose -f docker-compose.yml -f docker-compose.qwen.yml pull
docker compose -f docker-compose.yml -f docker-compose.qwen.yml up -d
docker compose -f docker-compose.yml -f docker-compose.qwen.yml logs --tail=100 qwen-rtservice
```

The overlay adds `qwen-rtservice` and keeps the default Whisper services running.
Faster-Whisper and Qwen are both selected by default for realtime output.
In **Session settings**, select either model or both before you start audio.

If you already use source-built base images, pull only `qwen-rtservice` with this file list.
Then use `up -d --no-build --pull never` to preserve your local images.

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

Complete [Prepare source-built models](source-builds.md) first.
From the repository root, build the workers:

```bash
docker compose -f docker-compose.yml -f docker-compose.qwen-workers.yml build qwen-finalizer qwen-refinement
docker compose -f docker-compose.yml -f docker-compose.qwen-workers.yml up -d --no-build --pull never
docker compose -f docker-compose.yml -f docker-compose.qwen-workers.yml logs --tail=100 qwen-refinement qwen-finalizer
```

The overlay adds Qwen to the **Refined** and **Final** model lists.
WhisperX remains selected by default. Select Qwen in each stage that you need.
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

## Remove Qwen

With the file list that started Qwen, stop `qwen-rtservice`, `qwen-refinement`,
and `qwen-finalizer` as applicable. Remove their overlays from your file list.
Remove any Qwen replacement settings from your local file, then start the base stack.
This restores the Whisper defaults and retains model caches and saved data.

## Checks and settings

Use the [model checks](../model-checks.md) to validate realtime or worker output.
The realtime cache allocation defaults to 512 MiB; each worker defaults to 1024 MiB.
The shared `QWEN_KV_CACHE_MIB` override affects every Qwen service that uses it.
These values cover the vLLM cache, not total GPU memory.
See Xamurai's [Qwen worker guide](https://github.com/nanosamurai/xamurai/blob/master/docs/qwen-workers.md)
for limits and tuning.
