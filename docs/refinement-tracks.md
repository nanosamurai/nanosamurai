# Evaluate refinement tracks in the local stack

Use matching `implement-refinement-tracks` branches, stacked on
`implement-final-tracks`. Build the normal service Dockerfiles as
`samuraibff:refinement-tracks`, `samuraipersistor:refinement-tracks` and
`xamurai-finalizer-worker:refinement-tracks`. The last image supplies the existing
finalizer, the refinement track processor and a model-free window producer.

Append `-f docker-compose.refinement-tracks.yml` after the regular Compose files
and any local realtime overrides. Keep the same project name and `.env` when
updating an existing stack; all published ports must bind to `127.0.0.1`.
For a standard checkout:

```sh
docker compose -f docker-compose.yml -f docker-compose.refinement-tracks.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.refinement-tracks.yml up -d broker postgres localstack kafka_init db_migrate
docker compose -f docker-compose.yml -f docker-compose.refinement-tracks.yml --profile speech up -d
python -m pip install -r smoke-tests/requirements-final-tracks.txt
python smoke-tests/refinement_tracks.py --wav tests/data/test_cs.wav --report /local/path/refinement-report.json
```

Migration 015 extends the existing outcome index; window outcomes do not create
recording rows. Topic initialization adds `audio.refinement-windows` and
`transcripts.refined-tracks`, each with two partitions. Neither is compacted.
Existing session metadata remains on compacted `sessions.meta` with its current
key. Both final and refinement stage flags are enabled by this overlay.

The default refinement profile is the pinned `whisperx-medium-refined-r1`
composite (VAD, ASR, alignment and diarization). NVIDIA support, cached model
weights and `HF_TOKEN` supplied outside committed files are required. This
profile shares final tracks' model pins and disables enrollment. The primary
projection preserves existing WebSocket and recordings API behavior.

The smoke sends a consented Czech mono PCM16/16 kHz fixture, waits for a live
10-second result before closing audio, checks adjacent windows and ordered EOF,
real words/speakers, canonical SQL and primary rows, then republishes only its
own source-window events and verifies exact outcome replay. Reports contain
counts/identities/timings, never transcript text or audio. `--test-tracks` expects
an operator-selected synthetic success and failure alongside the real primary;
test profiles require explicit BFF and worker gates and are not speech models.
Append `-f docker-compose.refinement-tracks.test.yml` for those two synthetic
tracks (the successful one has two replicas), then pass `--test-tracks` to the
smoke. Optional `--restart-window-producer` restarts only
`nanosamurai-refinement_windows-1` while the smoke session is open and requires
exact reconstruction of its first window. Run that fault check only when this
local stack has no other active recordings; the producer serves all sessions.
After qualification, stop the synthetic services and recreate the BFF using
only the normal refinement overlay to restore the single real primary catalog.

The worker contract is bounded to ten-minute retained sessions and 32 open
sessions per window producer. Raw Kafka retention must cover that duration plus
recovery time. Open sessions pin their initial raw offsets; restart reconstructs
windows from Kafka and immutable S3 manifests. Idle closure defaults to 30
seconds and cannot reopen a generation. Keep speech input flowing during model
cold start. Shared source/derived-artifact cleanup and deletion during processing
remain lifecycle qualification work; use local consented fixtures. No production
Helm enablement or workflow consumer migration is included. The next stacked
[track selection spike](track-selection.md) adds the browser choices and read API.

## Local qualification — 2026-09-10

The regular stack passed real WhisperX with two adjacent windows, word timings,
speaker labels and no degradations. The first result arrived while audio was
open. Synthetic success/failure remained independent, with six canonical rows,
two primary rows and one recording per three-track session. Both secondary
replicas processed selected sessions on different source partitions. Restarting
the open window producer reconstructed the accepted window exactly; source
republication preserved canonical bytes and SQL counts. Primary WebSocket/API,
Range playback and concurrent finalization passed.

First live results after worker startup took 22.190–27.130 seconds; warm checks
took 2.038–2.661 seconds. The final real-only image check finished in 75.554
seconds, including recorder idle and finalization. These are burst-fed fixture
checks, not benchmarks. Full BFF/Persistor suites passed (131/18 tests), with
140 Python unit tests passing; real model coverage ran in Linux containers.
Published ports remained loopback-only and public-tree scans passed. Synthetic
services were stopped after qualification and the real primary was restored.
