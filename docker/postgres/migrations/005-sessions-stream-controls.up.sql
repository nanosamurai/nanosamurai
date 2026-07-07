-- 005-sessions-stream-controls
--
-- Motivation:
-- - BFF / SDKs can pass per-stream settings via /ws/audio query params.
-- - We store a snapshot of these controls per session for debugging and playback metadata.

ALTER TABLE sessions
  ADD COLUMN IF NOT EXISTS stream_controls jsonb;
