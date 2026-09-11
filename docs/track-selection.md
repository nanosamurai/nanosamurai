# Evaluate track selection and tabbed results

This local spike adds deployment-owned choices, independent refined/final
selections and per-track playback in the browser. It builds on
[refinement tracks](refinement-tracks.md) without changing their worker or
Persistor contract. Production enablement and a second real speech model remain
separate work.

## Start the updated local stack

Use `implement-track-selection-ui` in SamuraiBFF and this repo. Both branches
start from `implement-refinement-tracks`. Use the existing matching
`implement-refinement-tracks` Xamurai and Persistor images; build them first if
they are not already present. From a directory with sibling service checkouts:

```sh
docker build -t samuraibff:track-ui ../samuraibff
# Only needed when the previous spike images are absent:
docker build -t samuraipersistor:refinement-tracks ../samuraipersistor
docker build -t xamurai-finalizer-worker:refinement-tracks -f ../xamurai/finalizer_worker/Dockerfile ../xamurai
```

Keep your usual project name and `.env`, and preserve any realtime overrides.
Append the refinement overlay, then `docker-compose.track-ui.yml`, in that order.
The normal catalog selects only the real WhisperX primary. Example for the
standard stack, with `COMPOSE_BIND_IP=127.0.0.1`:

```sh
docker compose -f docker-compose.yml -f docker-compose.refinement-tracks.yml -f docker-compose.track-ui.yml config --format json | python smoke-tests/check_track_catalog.py
docker compose -f docker-compose.yml -f docker-compose.refinement-tracks.yml -f docker-compose.track-ui.yml up -d broker postgres localstack kafka_init db_migrate
docker compose -f docker-compose.yml -f docker-compose.refinement-tracks.yml -f docker-compose.track-ui.yml --profile speech up -d
```

This uses the regular local volumes and ports. Migrations 014/015 and the two
canonical outcome topics must already be initialized. WhisperX needs NVIDIA
support, the pinned cached models and `HF_TOKEN` supplied outside committed
files. No new ports or cloud services are required.

## Optional comparison/failure fixtures

Append `-f docker-compose.track-ui.test.yml` last. It adds **Test text only** and
**Test failure** to each stage, both unselected by default, and four CPU-only
synthetic workers. Both BFF and workers explicitly enable the test profiles.
These fixtures are not additional speech models.

```sh
docker compose -f docker-compose.yml -f docker-compose.refinement-tracks.yml -f docker-compose.track-ui.yml -f docker-compose.track-ui.test.yml config --format json | python smoke-tests/check_track_catalog.py
docker compose -f docker-compose.yml -f docker-compose.refinement-tracks.yml -f docker-compose.track-ui.yml -f docker-compose.track-ui.test.yml up -d --no-deps samuraibff finalizer_worker refinement_shadow refinement_failure final_shadow final_failure
```

That `--no-deps` command assumes the already-running, migrated speech stack.
The configuration validator checks loopback ports, unique IDs, required primary,
test gates and matching worker stage/track/profile identities. It checks
configuration agreement, not worker health. BFF startup additionally validates
allowed profiles, display names, defaults and optional tenant restrictions.

## Manual browser check

Open [Record](http://127.0.0.1:8000/live), then **Session settings**.

1. Enable **Refined** and **Final**, keep recording storage enabled, and set a
   ten-second refinement window. Each stage has its own optional track choices;
   the primary remains selected. New sessions normally select only WhisperX.
2. Select both test tracks in each stage. Choose a language supported by the
   profile and record a short consented sample. Settings lock after start.
3. Open **Refined real-time** during recording. Switch between the three tabs:
   real transcript, text-only fixture, and an independently failed fixture.
4. Stop. Wait for recording storage/finalization, then open **Final transcript**.
   Each selected track has its own full-width tab and status.
5. In WhisperX tabs, play or click a word. Highlighting uses that track's actual
   timing; refinement words in the second window use absolute recording time.
   The text-only tab offers ordinary playback and explains missing word timings.
6. Open the saved session from **Sessions**, reload, and switch tabs again.
   The frozen choices/labels remain available even after changing the current
   catalog. Switching views does not change execution or primary output.
7. Use **New session** to change choices. Try primary-only, refinement-only and
   final-only. Refinement-only stores windows; Final additionally stores the
   full recording needed for playback.

## Repeatable Chromium smoke

The test drives actual Chromium microphone capture using the consented repository
fixture `tests/data/test_cs.wav`, selects Czech, and operates the browser controls.
It requires the running test overlay above, Node.js and Playwright Chromium:

```sh
npm ci --prefix smoke-tests
npm exec --prefix smoke-tests -- playwright install chromium
npm --prefix smoke-tests run test:tracks
python -m pip install -r smoke-tests/requirements-final-tracks.txt
python smoke-tests/audit_track_ui.py
```

Set `HEADED=true` to see the browser. `TRACK_UI_BASE_URL` may override the BFF
address, but must remain loopback. A run creates four retained local fixture
sessions; it does not delete existing sessions or restart services. Allow several
minutes for recorder idle closure, model startup and finalization. Keep this
fixture run separate from recordings whose content you need to preserve.

Checks cover independent choices, primary/defaults, locked controls, a real live
window, per-track success/failure, text-only playback, actual word highlighting
across refinement windows, direct links/reload, primary-only and stage-only
sessions, and browser runtime errors. Ignored `test-results/track-ui/report.json`
records the four session identities for the read-only SQL/S3 audit, which checks
that unselected tracks created neither canonical outcomes nor result artifacts.
The report contains IDs/check names. Screenshots and Chromium's optional
`debug.log` are ignored local diagnostics and must not be committed; screenshots
can contain fixture text. Worker timing validation may reject difficult/short
trailing audio with `invalid_provider_timing`; the UI preserves that failure
independently instead of inventing timings.

To verify catalog changes, save the multiple-track session ID from the report,
restore the normal catalog with the command below, then run:

```sh
TRACK_UI_REOPEN_SESSION=<session-id> npm --prefix smoke-tests run test:tracks
```

PowerShell uses `$env:TRACK_UI_REOPEN_SESSION='<session-id>'` before the npm
command. The reopen mode checks the original test-track labels and readable
outputs despite their absence from the current catalog. The BFF suite separately
checks tenant denial, invalid selections, frozen reconnects, digest/size bounds
and actual Postgres/S3/HTTP integration.

## Restore the normal catalog

After qualification, stop the four synthetic workers and recreate BFF/finalizer
without the test overlay. Keep any normal realtime overrides in these commands:

```sh
docker compose -f docker-compose.yml -f docker-compose.refinement-tracks.yml -f docker-compose.track-ui.yml -f docker-compose.track-ui.test.yml stop refinement_shadow refinement_failure final_shadow final_failure
docker compose -f docker-compose.yml -f docker-compose.refinement-tracks.yml -f docker-compose.track-ui.yml up -d --no-deps samuraibff finalizer_worker
```

Historical fixture results remain readable. Use only consented local recordings:
the prior spike's shared source/derived-artifact cleanup and deletion-during-work
limitations still apply. Guest auth and fixture infrastructure credentials are
appropriate only for this loopback stack. This spike adds no remote enablement,
named policies, discovery service, SDK expansion or workflow migration.

## Local qualification — 2026-09-11

Chromium 151.0.7922.34 passed the microphone/UI flow with real WhisperX, two
refinement windows, final results, actual audio/word highlighting, text-only
and failed test tracks, New session, reload, invalid-ID rejection, primary-only
and stage-only sessions. No browser runtime errors occurred. The SQL/S3 audit
found only selected tracks: 6 refined/3 final outcomes for the comparison
session, 2/1 for primary-only, 2/0 for refinement-only and 0/1 for final-only.
Full recording counts were respectively 1, 1, 0 and 1.

After removing the test catalog and stopping its workers, Chromium reopened
the original comparison session with its original labels and readable results.
The final stack advertises only WhisperX to new sessions. Both Compose catalogs,
five validator tests, syntax checks and the public-tree secret scan passed.
The BFF full suite passed 142 tests / 1,066 assertions and its normal container
UI build reported zero warnings. The test used existing local volumes/model
caches, not a fresh-clone or production rollout.
