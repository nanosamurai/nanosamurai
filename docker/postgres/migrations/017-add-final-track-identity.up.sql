-- Keep this migration identical in both deployment repositories.
-- Versions 014-016 were used by local track experiments; never reuse them.
-- Run in one transaction. Preserve old NULL tracks and all transcript history.
LOCK TABLE recordings, session_transcripts IN SHARE ROW EXCLUSIVE MODE;

ALTER TABLE session_transcripts ADD COLUMN IF NOT EXISTS track_id text;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM recordings GROUP BY session_id, recording_url HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'Duplicate recordings: inspect (session_id, recording_url) and reconcile references without deleting transcript history before migration 017';
    END IF;
    IF EXISTS (SELECT 1 FROM session_transcripts
               WHERE type = 'final' AND track_id IS NOT NULL AND recording_id IS NOT NULL
               GROUP BY recording_id, track_id HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'Duplicate tagged final transcripts: preserve history and resolve (recording_id, track_id) conflicts before migration 017';
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS recordings_session_url_unique
    ON recordings (session_id, recording_url);

CREATE UNIQUE INDEX IF NOT EXISTS session_transcripts_recording_final_track_unique
    ON session_transcripts (recording_id, track_id)
    WHERE type = 'final' AND track_id IS NOT NULL;
