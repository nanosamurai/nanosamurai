# Service-owned realtime settings spike

Each realtime service defines its own small settings map in `GetCapabilities`.
The BFF exposes it through `/api/me.realtime_track_capabilities[].session_settings`.
Each attribute has `display_name`, `type`, `default`, and numeric `min`/`max`;
the UI renders booleans, integers, and decimals rounded to two places.

Whisper exposes `window_sec`, `overlap_sec`, `emit_every_sec`, `partial_enable`.
Nemotron exposes `endpointing_silence_ms`, defaulting to the service's
`NEMOTRON_ENDPOINTING_SILENCE_MS`. Qwen currently advertises an empty map.

The UI submits defaults plus edits in one URL-encoded `realtime_settings` JSON
query parameter, keyed by selected track ID. Audio admission freezes this in
`sessions.stream_controls.realtime_settings` and `sessions.meta.stream_controls`.
The BFF sends only each track's submap in `x-rt-settings` gRPC metadata. Nemotron
sets native per-stream recognition options; it does not reconfigure the shared model.
No new database schema, topic, settings registry or dependency is introduced.
The flat Whisper query/header settings path is removed.

Unknown fields are ignored by services. The spike relies on UI bounds and existing
engine guards; full SDK validation is a separate follow-up. SDK callers should
resolve advertised defaults before admission if they need a complete saved snapshot.

## Validate the source-built spike locally

From this repo, build the three changed images:

```powershell
docker build -t samuraibff:session-settings ../../IdeaProjects/samuraibff
docker build -t xamurai-rtservice:session-settings -f ../xamurai/rtservice/Dockerfile ../xamurai
docker build -t xamurai-nemotron-rtservice:session-settings -f ../xamurai/nemotron_rtservice/Dockerfile ../xamurai
```

Set those tags in the ignored `docker-compose.local-asr.yml` for `samuraibff`,
`rtservice`, and `nemotron-rtservice` (also `nemotron-probe`). Retain existing local
CE flags, enrollment configuration, worker images and credentials. Public default
image pins do not yet contain this spike. Use the original project and volumes:

```powershell
$files = @('-p', 'nanosamurai', '-f', 'docker-compose.yml',
  '-f', 'docker-compose.nemotron.yml', '-f', 'docker-compose.local-asr.yml',
  '-f', 'docker-compose.realtime-settings-smoke.yml')
docker compose @files up -d --no-build samuraibff rtservice nemotron-rtservice `
  samuraipersistor whisperx_worker recorder_worker finalizer_worker
docker compose @files --profile validation build realtime-settings-audit
python -m venv .tmp/track-ui-python
$smokePython = '.tmp/track-ui-python/Scripts/python.exe'
& $smokePython -m pip install -r smoke-tests/track-ui/requirements.txt
& $smokePython -m playwright install chromium
& $smokePython smoke-tests/track-ui/settings.py
docker compose @files --profile validation run --rm --no-deps realtime-settings-audit
```

The browser runner uses Python Playwright; no npm install or system Node.js is
needed. On Linux/macOS use `.tmp/track-ui-python/bin/python` for the same commands.
The Python runner and auditor were requalified on 2026-09-16. An independent
Python event subscriber waits for both tracks to finish draining before the
next session; the UI's shorter event-close timeout cannot guarantee that.

The browser streams `tests/data/test_cs.wav` through real microphone capture into
both ASR services. It checks deployment defaults, integer bounds, decimal rounding,
locked settings, per-track admission JSON, and Whisper partials disabled/enabled
in successive sessions with Nemotron silence set to 800/3000 ms. The existing
auditor checks the submitted values against Postgres, HTTP and compacted Kafka
metadata, including foreign-tenant denial. No synthetic workers are started.
Evidence stays in ignored `.tmp/realtime-settings`; all published ports use loopback.

Validation on 2026-09-16 passed with source-built images, the original volumes and
real inference. Both tracks produced finals; Whisper emitted zero partials when
disabled and three when enabled. The observed first Nemotron final ended at about
5.8 s with 800 ms silence and 20 s with 3000 ms. These are fixture observations,
not fixed latency guarantees. Postgres and Kafka retained each session's distinct
settings. Service CI: 115 tests; BFF: 130 tests / 981 assertions; Electron: 8 tests;
browser release build: zero warnings.
The existing Tier 1 connectivity and Tier 2 realtime smoke also pass with omitted
settings, confirming service defaults still work for direct clients.
