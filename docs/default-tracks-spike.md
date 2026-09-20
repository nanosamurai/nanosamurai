# Default transcription tracks

The lean spike adds three optional BFF environment variables, passed through
the base Compose file from `.env` or the shell:

| Variable | Applies when omitted by the client |
| --- | --- |
| `SAMURAIBFF_DEFAULT_REALTIME_TRACK` | `realtime_tracks` |
| `SAMURAIBFF_DEFAULT_REFINEMENT_TRACK` | `refinement_tracks` |
| `SAMURAIBFF_DEFAULT_FINAL_TRACK` | `final_tracks` |

Each is a single ID in its stage's configured allowlist. Invalid defaults stop
BFF startup. Blank/unset preserves existing behavior: all realtime tracks and
the first configured refinement/final track (normally WhisperX). Explicit
selections take precedence; disabling a stage still disables it. The UI reads
the same defaults from `/api/me`. Choices are saved when audio starts and stay
fixed on reconnect. Historical untagged results still mean WhisperX.

Use a source-built BFF containing this spike; existing published image pins
are unchanged. No worker, database migration, protobuf or Kafka-topic change
is required. Defaults choose among deployed workers; they do not start models
or automatically fail over to another model.

## Local Compose smoke

Reuse the existing compatible stack, database, volumes and model caches.
Prerequisites are healthy Faster-Whisper/Nemotron realtime services, Qwen
refinement/finalization, recorder, Persistor and the normal infrastructure.
Follow the existing Qwen-worker and Nemotron setup guides if needed. Do not
start duplicate workers or reset offsets. All published ports must use loopback.

The smoke overlay selects non-first IDs: Nemotron realtime and Qwen for both
batch stages. In PowerShell, with the sibling BFF and Xamurai source checkouts:

```powershell
$files = @('-p', 'nanosamurai', '-f', 'docker-compose.yml',
  '-f', 'docker-compose.nemotron.yml', '-f', 'docker-compose.local-asr.yml',
  '-f', 'docker-compose.qwen-workers.yml', '-f', 'docker-compose.default-tracks-smoke.yml')
docker compose @files build samuraibff
docker compose @files up -d --no-deps --no-build samuraibff
python -m venv .tmp/track-ui-python
.tmp/track-ui-python/Scripts/python.exe -m pip install -r smoke-tests/track-ui/requirements.txt
.tmp/track-ui-python/Scripts/python.exe -m playwright install chromium
.tmp/track-ui-python/Scripts/python.exe smoke-tests/track-ui/defaults.py
```

`docker-compose.local-asr.yml` is the existing ignored, machine-local image
override; omit it if compatible images are selected another way. Set
`BFF_SOURCE`/`XAMURAI_SOURCE` when sibling paths differ. Wait for `/ready` to
return 200 before starting the browser runner.

The runner uses Xamurai's synthetic English fixture and real browser capture,
ASR and persistence. It checks all stages together, each stage alone, an explicit
realtime override, preselected checkboxes, absence of track query parameters,
one realtime result panel, actual transcript track IDs, disabled stages and
saved controls. It prints assertions rather than transcript text and leaves
fixture sessions plus `.tmp/default-tracks/sessions.json` as evidence.
Expected final line: `DEFAULT TRACKS COMPOSE SMOKE PASSED`.

Remove the smoke overlay and recreate only BFF to restore ordinary settings.
To retain the spike, select its BFF image and your desired defaults in the
existing local override or environment. No infrastructure or worker restart
is needed to change these BFF settings.

## Qualification on 2026-09-20

The existing local Compose stack passed `DEFAULT TRACKS COMPOSE SMOKE PASSED`
with the source-built `samuraibff:default-tracks` image and real Nemotron,
Faster-Whisper and Qwen workers. All five browser scenarios passed, including
non-first defaults with no track query parameters and a Faster-Whisper override.
Refined/final results contained real text and the expected Qwen track identity;
disabled stages produced no results. No browser errors occurred.

BFF validation passed 131 tests / 1,012 assertions, including WebSocket defaults
and overrides, Kafka headers, PostgreSQL snapshots across reconnects, invalid
configuration, and unchanged legacy fallback. The release UI/image build,
changed-file lint and eight Electron tests passed. No schema, volumes, worker
configuration or permissions changed; all published ports remained on loopback.
Fixture sessions are retained as evidence; transcript content is not copied
into logs or documentation.
