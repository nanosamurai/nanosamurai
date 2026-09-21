# Parakeet

Parakeet TDT 0.6B v3 provides refined and final transcripts.
It is off by default. The optional overlay builds two services from source:

- `parakeet-refinement` processes audio windows during the session.
- `parakeet-finalizer` processes the complete recording after you stop.

Both use the Q8 model with Sortformer speaker labels and native word timing.
Parakeet does not provide realtime transcription in this stack.

## Add Parakeet

Complete [Prepare source-built models](source-builds.md) first.
From the repository root:

```bash
docker compose -f docker-compose.yml -f docker-compose.parakeet.yml build parakeet-finalizer parakeet-refinement
docker compose -f docker-compose.yml -f docker-compose.parakeet.yml up -d --no-build --pull never
docker compose -f docker-compose.yml -f docker-compose.parakeet.yml logs --tail=100 parakeet-refinement parakeet-finalizer
```

The first startup downloads the models. Parakeet and Sortformer need no model token.
The default Whisper services still need `HF_TOKEN`.
The Parakeet workers share a disk cache, but each loads separate weights into memory.

Open **Session settings**. Select Parakeet in **Refined**, **Final**, or both.
With no defaults set, WhisperX remains selected until you change the selection.
To make Parakeet the initial choice, set the [refined and final defaults](README.md#set-default-tracks) to `parakeet`.
To compare both models, select both in the same stage.
Keep recording storage enabled when you select both final models.

## Use Parakeet instead of WhisperX

Add this to your ignored `docker-compose.local-asr.yml`:

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
      SAMURAIBFF_REFINEMENT_TRACKS: parakeet
      SAMURAIBFF_FINAL_TRACKS: parakeet
      SAMURAIBFF_TRACK_LABELS: '{"refined":{"parakeet":"Parakeet TDT v3"},"final":{"parakeet":"Parakeet TDT v3"}}'
```

Apply the change:

```bash
docker compose -f docker-compose.yml -f docker-compose.parakeet.yml -f docker-compose.local-asr.yml up -d --no-build --pull never
```

This stops both WhisperX workers and offers only Parakeet for those stages.
Faster-Whisper continues to provide realtime output.
To keep one WhisperX stage, omit its zero-replica setting and retain `whisperx,parakeet` in that stage's track list.

## Remove Parakeet

Stop `parakeet-refinement` and `parakeet-finalizer` with the file list that started them.
Remove the Parakeet overlay and its local replacement settings.
Clear any default track settings that name `parakeet`.
Start the remaining stack to restore WhisperX.
The model cache and saved transcripts remain available.

## Limits and checks

Parakeet supports up to four anonymous speakers per window or final recording.
It does not match enrolled names. Speaker labels restart in each refinement window.
Equal labels in different windows do not prove that the speaker is the same.

Use [model checks](../model-checks.md#parakeet) to verify both stages.
See the [Xamurai pipeline guide](https://github.com/nanosamurai/xamurai/blob/master/docs/parakeet-refinement.md)
for worker settings and timing details.
