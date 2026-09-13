-- Migration 016 from the discarded local experiment required execution IDs
-- for any tagged transcript. The lean contract only requires track_id.
-- Preserve its columns, historical rows and applied migration ledger.
ALTER TABLE session_transcripts
    DROP CONSTRAINT IF EXISTS session_transcripts_final_track_check;
