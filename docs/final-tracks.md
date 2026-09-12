# Qualify final-track Postgres storage locally

Use the `correct-final-track-storage` service branches with this Compose slice.
The regular quickstart overlay is `docker-compose.final-tracks.override.yml`;
enable it only after the migration/drain checks in the service contract.
For isolated qualification:

```sh
docker build -t samuraibff:postgres-final-tracks ../samuraibff
docker build -t samuraipersistor:postgres-final-tracks ../samuraipersistor
docker build -t xamurai-finalizer-worker:postgres-final-tracks -f ../xamurai/finalizer_worker/Dockerfile ../xamurai
docker compose -f docker-compose.final-tracks.yml up -d
python -m pip install -r smoke-tests/requirements-final-tracks.txt
python smoke-tests/final_tracks.py --wav /path/to/consented-czech.wav --database-fault --process-exit-fault
```

The real WhisperX profile uses the pinned medium/VAD/alignment/diarization
pipeline. Supply `HF_TOKEN` through the intended environment for gated model
downloads, or use `HF_HUB_OFFLINE=1` with an already populated model cache;
cached ASR can run without a token, while full diarization may still require it. `FINAL_TRACK_HF_CACHE` chooses the
cache volume. The synthetic secondary/failure profiles exercise isolation;
they do not qualify another speech model.

`FINAL_TRACK_COMPOSE_PROJECT` can select a fresh project without touching
retained datasets. Ports bind to `127.0.0.1`: BFF 18000, Kafka 19094,
Postgres 15434 and S3 14566. The selected input is retained mono PCM16/16 kHz,
at most ten minutes. The existing consented `xamurai/tests/data/test_cs.wav`
is suitable. Never run fault injection against a product deployment.

The smoke checks real speech and silence, independent failed/secondary results,
one reused recording and three stored transcript/outcome rows per session,
stable accepted content across reinference, primary playback, database outage,
worker restart/replay, process exits after DB commit and after primary publication, and primary-only
API reads with object storage paused. It asserts that S3 contains audio WAVs
only. Faulted services are restored in `finally`. Reports contain verification
status and synthetic session IDs, never transcript text or audio.

Stop with `docker compose -f docker-compose.final-tracks.yml down`; preserve
volumes. LocalStack fixture objects are ephemeral unless separately configured
for persistence. Keep source data/backups needed for later replay. The smoke
pauses S3 for read verification so it does not reset its in-memory data.

Postgres is authoritative for final transcripts; Persistor publishes the legacy
primary after accepting the result. See the companion services' `docs/final-tracks.md`
for the reduced schema, migration 016, retry limits and rollback procedure.
Historical S3-based qualification is retained in `final-tracks-qualification.md`
and does not qualify this correction. Refinement and catalog/UI rebases remain
on hold until the corrected final slice is reviewed and merged.
