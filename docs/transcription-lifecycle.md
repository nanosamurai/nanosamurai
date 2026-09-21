# Transcription lifecycle

Nanosamurai produces three complementary transcript layers from one audio
session. They trade immediacy for additional context and processing:

| Layer | Delivery | Intended use |
| --- | --- | --- |
| Realtime | Streamed while audio is arriving | Live captions and immediate feedback |
| Asynchronous refinement | Streamed and persisted after configurable audio windows | Speaker-aware corrections with more context |
| Final transcript | Persisted after the completed recording is processed | Canonical full-session result and playback |

These layers are separate outputs. A realtime event marked `final=true` commits
one realtime window; it is not the same artifact as the full-session final
transcript.

## Realtime transcription

SamuraiBFF sends PCM audio to Xamurai's realtime service over bidirectional
gRPC. The service emits:

- replaceable `PARTIAL` hypotheses while a window is active
- a realtime `FINAL` event when that window is committed

SamuraiBFF forwards the events to connected clients over `/ws/events`. The
browser UI shows them on the realtime tab while recording.

Smaller windows and more frequent partial emissions make the UI feel more
responsive but increase decode work and can provide less linguistic context.
Larger windows generally improve stability at the cost of latency. The
authoritative tuning reference is Xamurai's
[rtservice performance guide](https://github.com/nanosamurai/xamurai/blob/master/docs/rtservice-performance.md).

## Asynchronous refinement

SamuraiBFF also publishes the session audio to Kafka topic `audio.raw`. Selected
WhisperX, Parakeet, or Qwen workers use the shared refinement runtime to buffer
configurable windows and publish track-labelled `RefinedEvent` messages on
`transcripts.refined`. Optional overlays enable Parakeet and Qwen; WhisperX
is the base stack default. See [Default tracks](models/README.md#set-default-tracks)
for how the deployment resolves omitted selections.

A refined event may contain several speaker turns. SamuraiBFF fans those turns
out to browser events, and SamuraiPersistor stores the underlying transcript
record in PostgreSQL. Refined results can arrive while the session is still
active, but they intentionally lag realtime output.

The refinement-window control trades latency and compute for context. The
public wire behavior is described by:

- [SamuraiBFF transcript semantics](https://github.com/nanosamurai/samuraibff/blob/master/docs/features-transcripts.md)
- [Xamurai stream output selection](https://github.com/nanosamurai/xamurai/blob/master/docs/stream-output-selection.md)

## Recording and final transcript

When recording is enabled, the recorder worker consumes the same `audio.raw`
stream and writes the completed session audio to the configured recording
store. The evaluator stack supplies LocalStack as its S3-compatible
implementation; LocalStack is not required by the application architecture.
See [Replaceable object storage](architecture.md#replaceable-object-storage) for
the consumers and configuration that must move together when selecting another
provider.

After the recorder publishes `recordings.finished`, each selected finalizer
processes the completed recording and publishes its own `SessionTranscript` on
`transcripts.final`. WhisperX, Parakeet, and Qwen reuse the shared finalization runtime.
SamuraiPersistor stores each full-session track, and SamuraiBFF serves the
separate results through the recording-detail API and UI. Final tracks are
selected independently of refinement tracks. An omitted selection uses the
configured default, or the first configured final track when no default is set.
Multiple final tracks currently require `store_recording=true`.

With the ordered-audio-end BFF and recorder builds, Stop closes the audio socket
normally. The BFF drains accepted frames, then sends an empty `AudioChunk` with
`x-audio-end=true` on the same Kafka session key/partition. The recorder finalizes
on that marker, removing the usual 30-second idle wait. Interrupted streams and
older BFFs still use `RECORDER_IDLE_SECONDS` (default 30). Refinement retains its
idle-tail behavior. The finish API updates session status but cannot establish
that audio has drained; it does not trigger recording completion.

Finalization can take substantially longer during the first run because model
and alignment initialization are cold. A stopped recording can therefore be
visible before its final transcript is available.

## Track results and recovery

The browser shows separate results for each selected stage and track. Saved
results use the labels recorded when the session started. A later deployment
label change does not rename those saved tabs. Text-only results do not acquire
speaker labels or timestamps that the model did not supply.

A missing result does not show whether its worker is still processing or has
failed. Session status does not prove that every selected track completed.
Realtime text is held in the browser and is not stored as transcript history.

Refinement workers retain the first Kafka offset for each active session until
all its windows and idle tail are published. After partition reassignment, a
worker rebuilds its buffers from retained audio. This can repeat inference and
increase partition lag. Keep Kafka audio long enough to cover the longest
active session and its recovery time. Expired audio cannot be rebuilt.

Persistor keeps the first stored result for each final recording/track or
refined track/window. Retries do not replace it. After an idle flush or worker
restart, resumed audio can lose its original refinement time origin. Start a
new session after audio completion.

## Speaker labels and word timing

The realtime and asynchronous workers can assign speaker labels through
diarization. WhisperX refinement emits segment timing without word alignment;
its finalizer adds word timing where alignment succeeds. Parakeet emits native
word timing in both stages. Live refinement events carry segment text and
speaker labels; Kafka and saved HTTP transcripts also retain available words.
The browser uses final word timing for synchronized playback and best-effort
seeking.

Parakeet supports up to four anonymous speakers per refinement window or final
recording, with no enrolled-speaker matching. Speaker labels restart in each
refinement window, so matching labels across windows do not establish identity.
See [Parakeet](models/parakeet.md) for timing and selection details.

Detailed component behavior remains with the owning services:

- [Xamurai diarization](https://github.com/nanosamurai/xamurai/blob/master/docs/whisperx-worker-diarization.md)
- [Xamurai word-level timing](https://github.com/nanosamurai/xamurai/blob/master/docs/word-level-timing.md)
- [SamuraiBFF recording playback](https://github.com/nanosamurai/samuraibff/blob/master/docs/features-recordings-playback-karaoke.md)

## Select outputs per stream

Clients can enable or disable these outputs when opening `/ws/audio`:

| Control | Default | Effect |
| --- | --- | --- |
| `realtime` | `true` | Produce live realtime events |
| `refined` | `true` | Publish audio for asynchronous refinement |
| `final` | `true` | Produce a full-session final transcript |
| `store_recording` | `true` | Retain completed audio for playback/download |

Examples:

```text
# Realtime only
realtime=true&refined=false&final=false

# Keep final text without retaining playback audio
final=true&store_recording=false
```

Disabling an output prevents unnecessary downstream processing for that lane.
`store_recording=false` controls long-term retention; the finalizer still needs
temporary access to completed audio when `final=true`.

## Persistence and visibility

- Realtime hypotheses are live events and are not the canonical stored
  transcript.
- Refined and final transcript records are persisted in PostgreSQL.
- Recorded audio is served through SamuraiBFF's authenticated, tenant-scoped
  playback endpoint when authentication is enabled.
- Internal `file://` and `s3://` recording locations are not exposed to browser
  clients.

See [Architecture and Community Edition boundary](architecture.md) for component
ownership and [APIs and extension points](apis-and-extension-points.md) for the
client-facing interfaces.
