-- Vendored from samuraipersistor/resources/migrations/002-transcript-records-append-only.up.sql
--
-- Evolve session_transcripts into an append-only "transcript records" table
-- that can store outputs from multiple worker/model/window configurations.

-- 1) Allow multiple transcript records per session.
-- Default constraint name for a UNIQUE column in Postgres is <table>_<column>_key
ALTER TABLE session_transcripts
    DROP CONSTRAINT session_transcripts_session_id_key;

-- 2) Add metadata columns to distinguish transcript sources/types.
ALTER TABLE session_transcripts ADD COLUMN source text;
ALTER TABLE session_transcripts ADD COLUMN type text;
ALTER TABLE session_transcripts ADD COLUMN model text;
ALTER TABLE session_transcripts ADD COLUMN window_length integer;
ALTER TABLE session_transcripts ADD COLUMN segment_start_s double precision;
ALTER TABLE session_transcripts ADD COLUMN segment_end_s double precision;
ALTER TABLE session_transcripts ADD COLUMN supersedes_seq bigint[];
ALTER TABLE session_transcripts ADD COLUMN event_created_at_ns bigint;

-- 3) Backfill existing rows (from finalizer_worker) and enforce NOT NULL.
UPDATE session_transcripts SET source = 'finalizer_worker' WHERE source IS NULL;
UPDATE session_transcripts SET type = 'final' WHERE type IS NULL;

ALTER TABLE session_transcripts ALTER COLUMN source SET NOT NULL;
ALTER TABLE session_transcripts ALTER COLUMN type SET NOT NULL;

-- 4) Indexes for typical querying patterns.
CREATE INDEX idx_session_transcripts_session_created_at
    ON session_transcripts (session_id, created_at DESC);

CREATE INDEX idx_session_transcripts_session_type_source_window
    ON session_transcripts (session_id, type, source, window_length, segment_start_s);

CREATE INDEX idx_session_transcripts_event_created_at_ns
    ON session_transcripts (event_created_at_ns);
