-- Vendored from samuraibff/resources/migrations/0006_sessions_webhook_overrides.up.sql
--
-- Migration: store session-scoped webhook override request (immutable snapshot for audit)

ALTER TABLE sessions
  ADD COLUMN IF NOT EXISTS webhook_overrides jsonb;