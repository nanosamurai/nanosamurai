# Lean track selection UI spike

Spike 3 uses `implement-lean-track-selection-ui` in SamuraiBFF, Nanosamurai and
Nanodeploy, based on unmerged `implement-lean-refinement-tracks`. Xamurai and
Persistor retain their spike 2 code. The UI uses the existing API, Kafka and
Postgres paths. No new migration is needed; inspect that 017–019 are applied.

## Run against the original stack

Use the existing `nanosamurai` project, source-built spike 2 images, database
and volumes. Keep localhost ports, Nemotron settings and credentials in the
ignored local configuration. Never reset volumes or consumer offsets. Keep
these track spikes away from unmigrated workflow/webhook consumers.

From Nanosamurai in PowerShell:

```powershell
$files = @('-p', 'nanosamurai',
  '-f', 'docker-compose.yml', '-f', 'docker-compose.nemotron.yml',
  '-f', 'docker-compose.track-ui-smoke.yml', '-f', 'docker-compose.local-asr.yml')
docker compose @files build samuraibff
docker compose @files --profile validation build track-ui-audit
docker compose @files --profile validation up -d --no-deps --no-build `
  samuraibff whisperx_worker recorder_worker ui-test-final ui-test-refined

npm install --prefix .tmp/track-ui-tools --no-save playwright@1.62.1
node .tmp/track-ui-tools/node_modules/playwright/cli.js install chromium
$env:PLAYWRIGHT_MODULE = (Resolve-Path .tmp/track-ui-tools/node_modules/playwright).Path
node smoke-tests/track-ui/smoke.cjs
docker compose @files --profile validation run --rm --no-deps track-ui-audit
```

The browser sends `tests/data/test_cs.wav` through real microphone capture.
Default BFF URL is `http://127.0.0.1:8000`; `BFF_URL` can select another loopback
URL. Screenshots and newly created session IDs stay in ignored `.tmp/track-ui/`.
An existing Playwright installation can also supply `PLAYWRIGHT_MODULE`.

The synthetic workers expose no ports and replace only inference in the real
worker loops. Their `ui-shadow` ID avoids obsolete fixture messages addressed
to earlier spikes' `test-shadow`. `ui-unavailable` has no worker, testing
honest missing-result display. No consumer offsets are reset. No test worker
mounts the Docker socket.

For historical-label validation, write this ignored override:

```yaml
# .tmp/track-ui/renamed-labels.yml
services:
  samuraibff:
    environment:
      SAMURAIBFF_TRACK_LABELS: '{"final":{"ui-shadow":"Renamed test"},"refined":{"ui-shadow":"Renamed windows"}}'
```

Then recreate only BFF and check the previously saved session:

```powershell
docker compose @files -f .tmp/track-ui/renamed-labels.yml up -d --no-deps --no-build samuraibff
node smoke-tests/track-ui/smoke.cjs --verify-labels
```

After qualification, stop the test workers and restore ordinary configuration:

```powershell
docker compose @files --profile validation stop ui-test-final ui-test-refined
docker compose -p nanosamurai -f docker-compose.yml -f docker-compose.nemotron.yml `
  -f docker-compose.local-asr.yml up -d --no-deps --no-build `
  samuraibff whisperx_worker recorder_worker
```

This keeps the rebuilt BFF image and original volumes while removing the test
allowlist, labels and short idle timeouts. The mirror in Nanodeploy uses the
same smoke sources; the qualification target remains Nanosamurai Compose.

## Qualification on 2026-09-14

The original Postgres 18 stack passed:

- Browser tests for multiple/default/alternative-only selections, each stage
  alone, disabled stages, restoring choices, frozen settings, and New session
  preferences. Maximum realtime inference input and its configurable window
  are presented separately.
- Both live refinement tracks before recording stopped; real WhisperX aligned
  final output and a test-only text-only final. Synthetic output demonstrates
  integration, not another model's quality.
- Flat saved tabs, missing-result display, nested controls, direct links,
  reloads, shared audio range playback and word seeking. Text-only output adds
  no timestamps or speakers. Narrow-screen screenshots were also inspected.
- The audit checks one recording per final-enabled session, independent rows,
  tenant denial and the existing `sessions.meta` label snapshot.
- Deployment label renaming preserves historical tab labels.
- BFF release build and lint; 129 backend tests / 982 assertions and all eight
  Electron tests, with no failures or errors.

After removing test overrides and stopping both synthetic workers, the ordinary
Nemotron realtime / WhisperX refined / WhisperX final session and shared audio
playback smoke passed. The final BFF image was verified against its running
container, and the saved tabs/reload check passed on that image with only the
default async tracks configured. All published ports remained on loopback.

No migrations were applied. Per-track durable failure/completion remains a
later contract; missing results are unavailable, and session status does not
prove track completion. Realtime text remains a browser cache. Historical
audio already missing from LocalStack is not restored. Start a new session
after completion; the existing idle-tail resume limitation remains.

## Migration ownership and security

Nanosamurai and Nanodeploy remain migration owners. Their Docker SQL copies
match byte-for-byte; 017–019 also match Nanodeploy's chart copies. Some older
chart SQL differs only in comments/whitespace. Duplication and different
migration runners can drift: compare SQL and runner wiring before promotion,
and never rewrite applied SQL just to make historical hashes match.

No new table, topic, protobuf, result envelope, stored transcript artifact or
worker-discovery service. Labels render as text; tenant checks remain intact.
All host ports stay on loopback. Helm execution and cloud deployment are out
of scope.
