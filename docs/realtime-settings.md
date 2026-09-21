# Realtime settings

Open **Session settings** before you start audio. Select a realtime track,
then change the settings shown for that service. The available settings depend
on the deployed service image. Settings stay fixed after audio starts,
including across reconnects. Start a new session to use different values.

| Service | Settings |
| --- | --- |
| Faster-Whisper | `window_sec`, `overlap_sec`, `emit_every_sec`, `partial_enable` |
| Nemotron | `endpointing_silence_ms` |
| Qwen | No per-session settings are currently advertised |

Nemotron uses `NEMOTRON_ENDPOINTING_SILENCE_MS` as its deployment default.
Its silence setting applies to each stream; it does not reload the shared model.
See [Choose models](models/README.md) to change services or default tracks.

## API clients

Read `/api/me.realtime_track_capabilities[].session_settings` for the current
defaults, types, and numeric limits. The definitions come from each service's
`GetCapabilities` response. Send selected values in the URL-encoded
`realtime_settings` JSON query parameter on `/ws/audio`, keyed by track ID.

For example, this JSON disables Faster-Whisper partials and sets Nemotron's
silence limit to 800 ms:

```json
{"faster-whisper":{"partial_enable":false},"nemotron":{"endpointing_silence_ms":800}}
```

Select both tracks before you use this example. BFF saves the settings with
the session controls and sends each service only its own values through
`x-rt-settings` gRPC metadata. Reconnects use the saved settings.

Omitted settings use service defaults. Unknown fields are ignored. Clients
must use the advertised types and limits; do not assume that all SDK input is
validated. To save a complete settings snapshot, resolve the advertised
defaults before audio admission, as the browser does.

Use compatible BFF and realtime service images that support this contract.
See the [service image guide](models/source-builds.md), the
[BFF WebSocket contract](https://github.com/nanosamurai/samuraibff/blob/master/docs/ws-contract.md#wsaudio),
and [realtime regression checks](track-checks.md#realtime-settings-and-speaker-display).
