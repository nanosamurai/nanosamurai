# Voxtral realtime

Choose **Voxtral Mini 4B Realtime 2602** for live text in 13 languages, including
English, French and German. It runs locally without an API key or Hugging Face token.
It does not identify speakers, align individual words, or provide a refined or
full-recording transcript. Parakeet can still produce the latter two outputs.

## Add Voxtral to your local stack

Start with [Getting started](../getting-started.md). Voxtral needs an NVIDIA GPU
with BF16 support. Budget about 9 GB of disk for the weights in addition to the
container image. A 24 GB GPU is a starting point for evaluating Voxtral; leave
room for other models sharing it. Deselecting a track in the UI does not free its GPU memory.

From the repository root, finish any active recording and run:

```bash
docker compose -f docker-compose.yml -f docker-compose.voxtral.yml pull voxtral-rtservice
docker compose -f docker-compose.yml -f docker-compose.voxtral.yml up -d
docker compose -f docker-compose.yml -f docker-compose.voxtral.yml ps voxtral-rtservice
```

Keep any other overlays you already use in your file list (especially sign-in).
First startup downloads and verifies the weights, then warms the model; allow
several minutes. The model cache persists in a named volume. When the service
is healthy, open [the UI](http://127.0.0.1:8000/live) → **Session settings** →
**Realtime**. Select **voxtral** alone or select it alongside **nemotron** to
compare live output. Speak in a supported language and stop to see the last words.
Voxtral commits live text at the end of each 60-second interval and when you stop.

If GPU space is tight, try **Voxtral alone**. On an existing base stack, set
`SAMURAIBFF_GRPC_REALTIME_TRACKS=voxtral=voxtral-rtservice:50052` in `.env`,
and clear any realtime default other than `voxtral`. Finish active sessions, then run:

```bash
docker compose -f docker-compose.yml stop nemotron-rtservice parakeet-refinement parakeet-finalizer
docker compose -f docker-compose.yml -f docker-compose.voxtral.yml up -d voxtral-rtservice samuraibff
```

Turn off **Refined** and **Final** in Session settings while their workers are
stopped. A full `up -d` will start those workers again.
To remove Voxtral, stop `voxtral-rtservice` with the same file list, restore your
previous route/default in `.env`, and repeat `up -d` without its overlay.

## Settings

No additional variables are required. The [overlay](../../docker-compose.voxtral.yml)
pins the service image and registers `voxtral=voxtral-rtservice:50052` on the
private Compose network. If you combine multiple realtime overlays, set
`SAMURAIBFF_GRPC_REALTIME_TRACKS` to the complete list you want and apply the
Voxtral overlay after the other model overlays. Set `SAMURAIBFF_DEFAULT_REALTIME_TRACK=voxtral`
only if Voxtral should be preselected.

The local defaults admit two concurrent sessions and reserve 6144 MiB of GPU
decoder cache. Override `VOXTRAL_MAX_SESSIONS` and `VOXTRAL_KV_CACHE_MIB` in
`.env` to test another capacity; increasing the session limit does not add memory.
`VOXTRAL_GPU_MEMORY_UTILIZATION` (0.7) checks free GPU memory at startup; it
is not a VRAM cap. The bundled model size is fixed at 4B. See the
[Xamurai service guide](https://github.com/nanosamurai/xamurai/blob/master/docs/voxtral-realtime.md)
for supported languages, epoch boundaries and capacity qualification.
