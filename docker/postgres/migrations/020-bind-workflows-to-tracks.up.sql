-- Bind each transcript workflow to one explicit source track.
ALTER TABLE workflows ADD COLUMN IF NOT EXISTS trigger_track_id text;

-- Existing definitions were created for the single WhisperX transcript lane.
UPDATE workflows SET trigger_track_id = 'whisperx'
WHERE trigger_type IN ('transcript.refined.segment', 'transcript.final.ready')
  AND trigger_track_id IS NULL;

ALTER TABLE workflows ADD CONSTRAINT workflows_trigger_track_check CHECK (
    (trigger_type = 'recording.finished' AND trigger_track_id IS NULL)
    OR (trigger_type IN ('transcript.refined.segment', 'transcript.final.ready')
        AND trigger_track_id IS NOT NULL AND trigger_track_id ~ '^\S+$')
);
