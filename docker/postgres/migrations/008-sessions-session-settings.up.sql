-- Vendored from samuraibff/resources/migrations/0007_sessions_session_settings.up.sql
--
-- Migration: store session-scoped settings snapshot (webhook-agnostic)

ALTER TABLE sessions
  ADD COLUMN IF NOT EXISTS session_settings jsonb;
