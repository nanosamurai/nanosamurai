-- Vendored from samuraibff/resources/migrations/0005_webhooks_tables.up.sql
--
-- Migration: add webhook configuration tables (tenant-scoped)

CREATE TABLE webhooks (
    id            uuid PRIMARY KEY,
    tenant_id     uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

    name          text NOT NULL,
    url           text NOT NULL,
    enabled       boolean NOT NULL DEFAULT true,

    -- Supported values: none | hmac | oauth | api_key
    auth_type     text NOT NULL,

    -- Secret references (write-only secrets live outside Postgres)
    hmac_secret_ref         text,
    oauth_client_secret_ref text,
    api_key_ref             text,

    -- Non-secret auth config
    oauth_token_url   text,
    oauth_client_id   text,
    oauth_scopes      text,
    api_key_header_name text,
    api_key_prefix      text,

    -- Optional static headers (non-secret; never allowed to override system headers)
    static_headers jsonb,

    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_webhooks_tenant ON webhooks(tenant_id);
CREATE UNIQUE INDEX idx_webhooks_tenant_name ON webhooks(tenant_id, name);

CREATE TABLE webhook_subscriptions (
    tenant_id  uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    webhook_id uuid NOT NULL REFERENCES webhooks(id) ON DELETE CASCADE,
    event_type text NOT NULL,

    created_at timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (tenant_id, webhook_id, event_type)
);

CREATE INDEX idx_webhook_subscriptions_tenant_event_type
  ON webhook_subscriptions(tenant_id, event_type);

-- Per-tenant defaults: which webhook endpoints apply to newly created sessions.
CREATE TABLE tenant_webhook_defaults (
    tenant_id   uuid PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    webhook_ids uuid[] NOT NULL DEFAULT '{}'::uuid[],
    updated_at  timestamptz NOT NULL DEFAULT now()
);