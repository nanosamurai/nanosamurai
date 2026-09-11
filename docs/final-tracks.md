# Evaluate independent final tracks

This opt-in spike processes a completed recording through one real WhisperX
composite: VAD, medium ASR, alignment, and pyannote diarization. It also runs a
successful synthetic secondary track with two replicas and an intentionally
failing synthetic track. The test profiles demonstrate isolation and replay;
they are not additional speech models.

The long-lived outcome topic is `transcripts.final-tracks`, with schema version
inside the protobuf envelope. Every track group consumes `recordings.finished`
and filters the frozen session selection. Recorder emits one immutable source;
it does not route a copy to a topic per track. Only the successful primary also
publishes the existing body on `transcripts.final`.

## Run the isolated evaluation

Use the matching `implement-final-tracks` service branches. Build from each
service checkout (or pass equivalent paths from a common parent directory):

```sh
docker build -t samuraibff:final-tracks ../samuraibff
docker build -t samuraipersistor:final-tracks ../samuraipersistor
docker build -t xamurai-finalizer-worker:final-tracks -f ../xamurai/finalizer_worker/Dockerfile ../xamurai
```

Docker with NVIDIA GPU support and access to the gated pyannote models is
required. Supply `HF_TOKEN` through your environment; never put it in a committed
file. Model identifiers, immutable revisions and weight checksums are defined
by `whisperx-medium-final-r1` in Xamurai. English and Czech alignment are pinned;
other alignment languages report a degradation. The profile disables enrollment.

From this repository:

```sh
docker compose -f docker-compose.final-tracks.yml config --quiet
docker compose -f docker-compose.final-tracks.yml up -d
python -m venv .venv-final-tracks
# Activate the virtual environment for your shell.
python -m pip install -r smoke-tests/requirements-final-tracks.txt
python smoke-tests/final_tracks.py --wav /path/to/consented-16khz-mono.wav --database-fault --process-exit-fault
```

Use a consented Czech speech fixture for this strict smoke: it requires actual
word timings and speaker labels. The checked-in `xamurai/tests/data/test_cs.wav`
was used for qualification. Inputs must be PCM16 mono 16 kHz and at most 600
seconds. Three sessions are processed when the process-exit fault is enabled.
An optional `--report /local/path/report.json` records identities and provenance
without transcript text or audio.

The standalone file creates project `nanosamurai-final-tracks`, two-partition
topics and migration 014. It does not extend the standard quickstart. Test ports
bind only to `127.0.0.1`: BFF 18000, Kafka 19094, PostgreSQL 15434, S3 14566.
Its guest authentication and fixed database/S3 credentials are local fixture
settings. Do not expose or deploy this file publicly. The model cache is a
separate named volume; it is not part of recording cleanup.

The smoke checks independent success/failure, two replicas handling different
partitions, one recording/three outcome/one primary row per session, identical
replay bytes, no-retention rejection, and range playback through the existing
recording API. `--database-fault` stops and restarts only this project's database
and checks its consumer offsets. `--process-exit-fault` stops the synthetic
workers, exits a one-shot process immediately after its S3 manifest is durable,
then restarts the workers and verifies the recovered bytes. Both restore the
affected services in `finally`.

Stop the evaluation with:

```sh
docker compose -f docker-compose.final-tracks.yml down
```

Do not use `down -v` when reusing a model-cache volume. The default fixture S3
objects disappear with LocalStack; the isolated PostgreSQL volume remains.
Remove that specific project's fixture volume separately when it is no longer
needed. Never run the fault smoke against an existing product deployment.

## Boundaries

Feature flags default off in the services. The BFF freezes an operator-owned
plan in `sessions.stream_controls.asr_plan` and mirrors the complete snapshot
to compacted `sessions.meta`. Audio/source events carry the plan in headers and
typed fields; metadata lag or a newer snapshot cannot retarget emitted work.

Sources and transcripts use immutable S3 keys. The first conditional outcome
manifest wins; retries republish its exact event bytes. Computation before that
manifest can repeat. Kafka output acknowledgements precede source commits;
Persistor uses stable identities and validates the frozen tenant/session plan.
Delivery is at least once, with no exactly-once inference guarantee.

Only retained recordings are accepted. Track workers never delete shared audio.
Shared source/derived-artifact cleanup, deletion during active processing,
recording-assembly crash recovery, live refinement and a second real model are
later work. Keep this evaluation limited to isolated fixtures until those
lifecycle requirements are implemented. No new track picker, query API,
scheduler, inference RPC, KServe, KEDA or production Helm enablement is included.

See [qualification evidence](final-tracks-qualification.md) for measured results
and the remaining test limitation.
