-- Keep the deployment migration copies identical. Apply transactionally.
-- Historical NULL tracks remain untouched, including duplicate legacy windows.
LOCK TABLE session_transcripts IN SHARE ROW EXCLUSIVE MODE;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM session_transcripts
               WHERE type = 'refined' AND track_id IS NOT NULL
               GROUP BY tenant_id, session_id, track_id, window_length,
                        segment_start_s, segment_end_s HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'Duplicate tagged refined windows: preserve history and reconcile tenant/session/track/window/bounds conflicts before migration 019';
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS session_transcripts_refined_track_window_unique
    ON session_transcripts
        (tenant_id, session_id, track_id, window_length, segment_start_s, segment_end_s)
    NULLS NOT DISTINCT
    WHERE type = 'refined' AND track_id IS NOT NULL;
