-- 004-create-api-credentials
--
-- M2M API credentials inventory.
--
-- We do NOT store secrets in Postgres.
-- Secrets live only in Keycloak and are shown to the user once on creation/rotation.
--
-- Each row corresponds to a Keycloak confidential client with service account enabled.

CREATE TABLE api_credentials (
    id                uuid PRIMARY KEY,
    tenant_id         uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name              text NOT NULL,

    -- Keycloak clientId (human-readable unique identifier used in OAuth2)
    keycloak_client_id text NOT NULL UNIQUE,

    -- Who created it (OIDC subject). This is audit metadata only.
    created_by_sub    text,

    revoked_at        timestamptz,
    last_used_at      timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_api_credentials_tenant ON api_credentials(tenant_id);
CREATE INDEX idx_api_credentials_tenant_revoked ON api_credentials(tenant_id, revoked_at);