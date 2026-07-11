-- Vendored from samuraibff/resources/migrations/0008_workflows_tables.up.sql
--
-- Migration: add workflow configuration tables (tenant-scoped)

CREATE TABLE IF NOT EXISTS workflows (
    id            uuid PRIMARY KEY,
    tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    name          text NOT NULL,
    enabled       boolean NOT NULL DEFAULT true,

    -- Trigger source event type, e.g. transcript.refined.segment
    trigger_type  text NOT NULL,

    -- Prompt content (v1: plain text, no templating)
    prompt_text   text NOT NULL,

    -- Provider config (v1: bedrock only)
    provider_type      text NOT NULL,
    provider_model_id  text NOT NULL,
    provider_params    jsonb,

    -- Incremental trigger debounce
    incremental_enabled           boolean NOT NULL DEFAULT false,
    incremental_min_interval_sec  integer,

    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workflows_tenant ON workflows(tenant_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_workflows_tenant_name ON workflows(tenant_id, name);

-- Per-tenant defaults: which workflows apply by default to newly created sessions.
CREATE TABLE IF NOT EXISTS workflow_defaults (
    tenant_id     uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    workflow_ids  uuid[] NOT NULL DEFAULT '{}'::uuid[],
    updated_at    timestamptz NOT NULL DEFAULT now()
);
