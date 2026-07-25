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

SamuraiBFF also publishes the session audio to Kafka topic `audio.raw`. The
WhisperX refinement worker buffers configurable windows and produces
`RefinedEvent` messages on `transcripts.refined`.

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
store. The evaluator stack uses LocalStack S3.

After the recorder publishes `recordings.finished`, the finalizer worker
processes the completed recording and publishes `SessionTranscript` on
`transcripts.final`. SamuraiPersistor stores that full-session result, and
SamuraiBFF serves it through the recording-detail API and UI.

Finalization can take substantially longer during the first run because model
and alignment initialization are cold. A stopped recording can therefore be
visible before its final transcript is available.

## Speaker labels and word timing

The realtime and asynchronous workers can assign speaker labels through
diarization. Final transcript segments may also include word-level
`start_s`/`end_s` timing. The browser uses final word timing for synchronized
playback and best-effort seeking.

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
