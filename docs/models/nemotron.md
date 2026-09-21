# Nemotron

Nemotron 3.5 ASR 0.6B provides realtime transcription. It is off by default.
The optional overlay runs the Q8 model service.
It does not provide refined or full-recording final transcripts.

## Add Nemotron

The commands below use local builds. Complete [Prepare source-built models](source-builds.md) for this path.
GHCR images are also available; see [image choices](source-builds.md#published-images-and-compose-defaults).
The pinned base API image predates the required replica routing.

From the repository root:

```bash
docker compose -f docker-compose.yml -f docker-compose.nemotron.yml build nemotron-rtservice
docker compose -f docker-compose.yml -f docker-compose.nemotron.yml up -d --no-build --pull never
docker compose -f docker-compose.yml -f docker-compose.nemotron.yml ps --all
docker compose -f docker-compose.yml -f docker-compose.nemotron.yml logs --tail=100 nemotron-rtservice
```

The overlay starts two Nemotron containers by default. Each accepts one active stream.
Set `NEMOTRON_RTSERVICE_REPLICAS=1` in `.env` if you only need one stream.
Each replica needs separate model memory. The first startup downloads and verifies the model.

Faster-Whisper stays available. With no realtime default set, both realtime tracks are selected.
In **Session settings**, select Nemotron, Faster-Whisper, or both.
To make Nemotron the initial choice, [set the realtime default](README.md#set-default-tracks) to `nemotron`.
WhisperX still provides refined and final transcripts.

## Use Nemotron instead of Faster-Whisper

Add this to your ignored `docker-compose.local-asr.yml`:

```yaml
services:
  rtservice:
    deploy:
      replicas: 0
  samuraibff:
    environment:
      SAMURAIBFF_GRPC_REALTIME_TRACKS: nemotron=nemotron-rtservice:50052
```

Apply the change:

```bash
docker compose -f docker-compose.yml -f docker-compose.nemotron.yml -f docker-compose.local-asr.yml up -d --no-build --pull never
```

This stops Faster-Whisper. Nemotron becomes the only realtime choice.

## Add speaker labels

Speaker processing is off by default. To enable anonymous Sortformer labels,
set this in `.env`:

```dotenv
NEMOTRON_DIARIZATION=true
```

To match existing enrolled speakers, also set:

```dotenv
NEMOTRON_ENROLL_BACKEND=s3_manifest
```

Repeat your `up -d --no-build --pull never` command to apply the change.
Set `NEMOTRON_DIARIZATION=false` and `NEMOTRON_ENROLL_BACKEND=disabled` to turn both features off.

Nemotron and its speaker models do not need a Hugging Face token.
The default Whisper services still need one.
Sortformer supports up to four speakers per continuous stream.
Enrolled-name matching needs local calibration with separate test audio.
Nemotron does not provide word timing.

## Remove Nemotron

Stop `nemotron-rtservice` with the file list that started it.
Remove the Nemotron overlay and its local replacement settings.
Clear the realtime default if it names `nemotron`.
Start the remaining stack to restore Faster-Whisper.
The model cache remains available for later use.

For verification, see [model checks](../model-checks.md#nemotron).
For speaker limits, see [Xamurai's Nemotron guide](https://github.com/nanosamurai/xamurai/blob/master/docs/nemotron-sortformer.md).
