-- Vendored from samuraibff/resources/migrations/0009_sessions_workflow_overrides.up.sql
--
-- Migration: store session-scoped workflow override request (immutable snapshot for audit)

ALTER TABLE sessions
  ADD COLUMN IF NOT EXISTS workflow_overrides jsonb;
