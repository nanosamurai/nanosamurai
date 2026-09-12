-- Forward-only correction. 014/015 may already be applied. Never rewrite them.
-- The old index remains migration input while retained refinement drafts wait.
ALTER TABLE session_transcripts ADD COLUMN plan_id uuid;
ALTER TABLE session_transcripts ADD COLUMN track_id text;
ALTER TABLE session_transcripts ADD COLUMN profile_id text;
ALTER TABLE session_transcripts ADD COLUMN status text NOT NULL DEFAULT 'succeeded';
ALTER TABLE session_transcripts ADD COLUMN is_primary boolean NOT NULL DEFAULT true;
ALTER TABLE session_transcripts ADD COLUMN error_code text;
ALTER TABLE session_transcripts ADD COLUMN capabilities jsonb NOT NULL DEFAULT '{}';
ALTER TABLE session_transcripts ADD COLUMN degradations jsonb NOT NULL DEFAULT '[]';
ALTER TABLE session_transcripts ADD CONSTRAINT session_transcripts_status_check
  CHECK (status IN ('succeeded', 'failed'));
ALTER TABLE session_transcripts ADD CONSTRAINT session_transcripts_final_track_check
  CHECK (track_id IS NULL OR (result_id IS NOT NULL AND plan_id IS NOT NULL
    AND profile_id IS NOT NULL AND recording_id IS NOT NULL AND type = 'final'));
CREATE UNIQUE INDEX session_transcripts_final_track_uidx
  ON session_transcripts (tenant_id, session_id, recording_id, plan_id, track_id)
  WHERE track_id IS NOT NULL;

-- Preserve primary content that the old compatibility consumer already stored.
UPDATE session_transcripts st SET
  plan_id = old.plan_id, track_id = old.track_id, profile_id = old.profile_id,
  status = old.status, is_primary = old.is_primary, error_code = old.error_code,
  capabilities = old.capabilities, degradations = old.degradations
FROM transcript_track_results old
WHERE st.result_id = old.result_id AND st.tenant_id = old.tenant_id
  AND st.session_id = old.session_id AND old.stage = 'final';
