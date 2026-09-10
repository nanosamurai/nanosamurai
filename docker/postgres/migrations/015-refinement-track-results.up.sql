-- Window outcomes use the existing index, without one recording row per window.
ALTER TABLE transcript_track_results ALTER COLUMN recording_id DROP NOT NULL;
ALTER TABLE transcript_track_results ADD COLUMN source jsonb;
ALTER TABLE transcript_track_results DROP CONSTRAINT transcript_track_results_stage_check;
ALTER TABLE transcript_track_results DROP CONSTRAINT transcript_track_results_unit_id_check;
ALTER TABLE transcript_track_results ADD CONSTRAINT transcript_track_results_stage_unit_check
    CHECK ((stage = 'final' AND unit_id = 'recording' AND recording_id IS NOT NULL)
        OR (stage = 'refined' AND unit_id ~ '^fixed-[0-9]+:[0-9]+:[0-9]+$'
            AND recording_id IS NULL AND source IS NOT NULL));
