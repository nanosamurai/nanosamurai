# Qwen finalization and refinement

The optional `docker-compose.qwen-workers.yml` adds `qwen` to the Final and
Refinement settings independently. Both services use Qwen3-ASR-0.6B through
vLLM batching and pyannote speaker diarization. WhisperX remains the default.
Qwen realtime is a separate overlay and is not needed for these workers.

Use a compatible Xamurai checkout (`XAMURAI_SOURCE`, default `../xamurai`),
BFF/Persistor images with the existing lean-track support, and the already
applied track migrations described in [the refinement setup](refinement-tracks-spike.md).
This addition changes no protocol or database schema. Keep existing local image
overrides, project name, volumes and consumer groups. `HF_TOKEN` needs read
access to the pinned pyannote models; keep it in the ignored `.env`.

From an existing local stack:

```powershell
$env:COMPOSE_BIND_IP = '127.0.0.1'
docker build -t samuraibff:audio-end ../../IdeaProjects/samuraibff
docker build -t xamurai-recorder-worker:audio-end -f ../xamurai/recorder_worker/Dockerfile ../xamurai
$files = @('-p', 'nanosamurai', '-f', 'docker-compose.yml',
  '-f', 'docker-compose.nemotron.yml', '-f', 'docker-compose.local-asr.yml',
  '-f', 'docker-compose.qwen-workers.yml')
docker compose @files build qwen-finalizer qwen-refinement
docker compose @files up -d --no-deps --no-build recorder_worker samuraibff qwen-finalizer qwen-refinement
docker compose @files --profile validation build qwen-smoke
docker compose @files --profile validation run --rm --no-deps qwen-smoke
```

The Nemotron/local files above preserve this development stack's existing
source-built images; omit them on installations configured through their own
compatible image overrides. Start Kafka, Postgres, LocalStack, recorder,
Persistor and a configured realtime service before the probe. BFF readiness
still checks realtime gRPC even when a test selects only asynchronous stages.
Stop obsolete pre-rename workers and synthetic smoke workers before testing.

The overlay enables WhisperX and Qwen; to combine it with Parakeet, explicitly
include all desired IDs and labels in the BFF allowlists in the final override.
Keep worker groups `finalizer.qwen` and `refinement.qwen` distinct. The model
cache is shared with Qwen realtime; loaded weights are separate per process.
Allow several minutes for cold initialization and budget CPU RAM as well as GPU
memory. Run GPU integration suites separately from the full model stack on a
16 GiB Docker VM.

## Results and limits

Pyannote diarizes each input, then Qwen transcribes batches of speaker turns,
splitting turns into at most 30-second crops. The pinned Qwen forced aligner
adds word timestamps in the session timeline, preserving transcript punctuation.
The existing Final Transcript player highlights those words and supports
click-to-seek. Refinement results also store word timings; its UI is unchanged.
Old saved rows are not rewritten, so record a new session to obtain highlighting.
Unsupported languages or unusable crop alignments retain speaker segments without
word timing; other aligned segments still support highlighting.
There are no enrolled names. Overlapping voices are not separated; each sample is assigned
once. Speaker labels are recording-local for finalization and window-local for
refinement. Equal labels across windows do not establish identity.

`QWEN_BATCH_SIZE` defaults to 4 and `QWEN_KV_CACHE_MIB` to 1024. These bound the
vLLM batch and cache allocation. Refinement retains the shared window, idle-tail,
queue and replay behavior. See the
[Xamurai pipeline guide](https://github.com/nanosamurai/xamurai/blob/master/docs/qwen-workers.md)
for all settings. Short-fixture tests establish functionality, not ASR accuracy,
multi-speaker quality or maximum recording capacity.

The smoke uses real models and Xamurai's synthetic English fixture. It checks live
windows and an idle tail, finalization, model/track metadata, timed words/speakers,
exact word-text preservation and session-relative timing across refinement windows,
filtered saved results, exact WAV/range playback, replay deduplication, silence,
independent stage selection, committed skips/defaults, and foreign-tenant denial.
It prints assertions rather than transcripts and leaves new fixture sessions as
evidence. It does not reset offsets, replace volumes or change database objects.

The local override uses source-built `samuraibff:audio-end` and
`xamurai-recorder-worker:audio-end`. The probe closes audio immediately after
sending the fixture and requires `recordings.finished` within 10 seconds of
Stop, with the empty `x-audio-end=true` marker after every chunk on the same
session key/partition. It also checks an audio-only connection, abnormal TCP
closure with the unchanged 30-second fallback, and duplicate/empty Stop without
additional recordings. Refinement still produces its idle tail normally.

Validated on 2026-09-19 in the existing `nanosamurai` Compose project with rebuilt
`xamurai-qwen-finalizer:local` and `xamurai-qwen-refinement:local` images:

- The real Compose probe completed with `QWEN COMPOSE SMOKE PASSED`, including
  word timing and text preservation across final and refined results.
- Xamurai's two real GPU integration tests passed, including observed multi-crop
  vLLM and forced-aligner calls; 28 realtime/shared-worker regression checks also passed.
- A browser check rendered all 55 persisted final words. Clicking two words
  sought playback to 1.465 and 12.108 seconds and activated their highlights.
- Both running workers matched the rebuilt image IDs, ran as UID 10002 with no
  host ports, and had zero restarts or OOM kills. BFF `/ready` returned 200.
- Every published stack port was bound to `127.0.0.1`; the implementation commits
  passed Gitleaks. No protobuf, data-model or database-schema changes were made.

Workers run unprivileged, publish no host port and reuse immutable model pins
and digest checks. HF credentials are runtime-only and telemetry is disabled.
Refinement has no storage credentials. The stack's development credentials and
disabled authentication remain suitable only for localhost evaluation.
