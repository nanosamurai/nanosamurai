# Nemotron

Nemotron 3.5 ASR provides realtime transcription. It runs by default in the
`nemotron-rtservice` service. It does not provide refined or final transcripts;
[Parakeet](parakeet.md) provides those by default.

## Model sizes and variants

The official [Nemotron 3.5 ASR streaming release](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b)
provides a **0.6B** model. It does not list a larger size for this release.

The current adapter selects `nvidia/nemotron-3.5-asr-streaming-0.6b` in Q8 format.
Q8 uses 8-bit weights; the model still has 0.6 billion parameters.
The adapter fixes the model file, revision, and checksum.
It has no model-size setting and does not select a size from available GPU memory.
Another model would require an adapter update and validation.

The model needs no Hugging Face token. The first startup downloads and verifies it.
Its license is OpenMDW-1.1; see the model card.

## Chunk size and accuracy

Nemotron transcribes the stream in chunks. A larger chunk gives the model more
context: text appears in larger steps, but it is more accurate.
`NEMOTRON_RNNT_RIGHT_CONTEXT` sets the chunk in 80 ms encoder frames:

| Value | Chunk | Result |
| --- | --- | --- |
| `-1` (default) | 1.12 s, the largest the model supports | Most accurate |
| `6` | 560 ms | Faster text, slightly less accurate |
| `1` | 160 ms | Fastest text, least accurate |

The [model card](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b)
lists the error rates for each chunk size. The service log shows the chunk size
at startup, for example `step=1120ms`.
Set the value in `.env` and repeat your `up -d` command.

## Streams and replicas

One Nemotron container runs by default. It accepts one active stream.
To serve two streams at the same time, set this in `.env` and repeat your `up -d` command:

```dotenv
NEMOTRON_RTSERVICE_REPLICAS=2
```

Each replica loads its own model copy into GPU memory.
When every replica is busy, Nemotron rejects a new realtime stream before it reads audio.
See [Troubleshooting](../troubleshooting.md) for the related log messages.

## Languages

Nemotron uses the session language when you select one, or detects it.
The model card lists 40 locales, including German. This stack is tested with English.
Check the results with your own audio before you use it for another language.

## Use Faster-Whisper instead of Nemotron

Add the [Whisper overlay](whisper.md#add-whisper), then add this to your ignored
`docker-compose.local-asr.yml`:

```yaml
services:
  nemotron-rtservice:
    deploy:
      replicas: 0
  samuraibff:
    environment:
      SAMURAIBFF_GRPC_REALTIME_TRACKS: faster-whisper=rtservice:50052
```

Apply the change:

```bash
docker compose -f docker-compose.yml -f docker-compose.whisper.yml -f docker-compose.local-asr.yml up -d
```

This stops Nemotron. Faster-Whisper becomes the only realtime choice.
Keep at least one realtime service available for the API readiness check.
To restore Nemotron, remove these settings and repeat the command.

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

Repeat your `up -d` command to apply the change.
Set `NEMOTRON_DIARIZATION=false` and `NEMOTRON_ENROLL_BACKEND=disabled` to turn both features off.

Nemotron and its speaker models do not need a Hugging Face token.
Sortformer supports up to four speakers per continuous stream.
Enrolled-name matching needs local calibration with separate test audio.
Nemotron does not provide word timing.

For verification, see [developer smoke tests](../smoke-tests.md#check-the-models).
For speaker limits, see [Xamurai's Nemotron guide](https://github.com/nanosamurai/xamurai/blob/master/docs/nemotron-sortformer.md).
