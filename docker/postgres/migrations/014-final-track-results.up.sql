-- Additive, opt-in final-track outcome index. Apply before enabling any writer.
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS asr_meta_snapshot jsonb;
ALTER TABLE recordings ADD COLUMN IF NOT EXISTS source_artifact_id uuid;
ALTER TABLE recordings ADD COLUMN IF NOT EXISTS source_sha256 text;
ALTER TABLE recordings ADD COLUMN IF NOT EXISTS source_size_bytes bigint;
ALTER TABLE recordings ADD COLUMN IF NOT EXISTS source_sample_count bigint;
ALTER TABLE recordings ADD COLUMN IF NOT EXISTS source_version_id text;
CREATE UNIQUE INDEX IF NOT EXISTS recordings_session_source_uidx
    ON recordings (session_id, source_artifact_id);

ALTER TABLE session_transcripts ADD COLUMN IF NOT EXISTS result_id uuid;
ALTER TABLE session_transcripts ADD COLUMN IF NOT EXISTS result_event_sha256 text;
CREATE UNIQUE INDEX IF NOT EXISTS session_transcripts_result_uidx
    ON session_transcripts (result_id);

CREATE TABLE IF NOT EXISTS transcript_track_results (
    result_id uuid PRIMARY KEY,
    tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    session_id uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    recording_id uuid NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    plan_id uuid NOT NULL,
    track_id text NOT NULL,
    profile_id text NOT NULL,
    run_id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    stage text NOT NULL CHECK (stage = 'final'),
    unit_id text NOT NULL CHECK (unit_id = 'recording'),
    revision integer NOT NULL CHECK (revision = 1),
    status text NOT NULL CHECK (status IN ('succeeded', 'failed')),
    is_primary boolean NOT NULL,
    result_uri text,
    result_sha256 text,
    error_code text,
    capabilities jsonb NOT NULL,
    degradations jsonb NOT NULL,
    provenance jsonb NOT NULL,
    event_sha256 text NOT NULL,
    event_created_at_ns bigint NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (tenant_id, session_id, run_id, unit_id, revision)
);
CREATE INDEX IF NOT EXISTS transcript_track_results_session_idx
    ON transcript_track_results (tenant_id, session_id, track_id);
