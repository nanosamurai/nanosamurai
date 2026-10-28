-- 024-add-personal-and-organization-api-keys
--
-- Two kinds of machine credentials. The identity provider is unchanged: every
-- credential is still one confidential client (client_credentials grant) with
-- its own service-account principal in app_users. These columns decide, in Postgres,
-- what a request made with the credential may do.
--
-- - personal: requests act as the credential's manager (its owner). Sessions
--   belong to that person and are marked with the credential. read_scope
--   limits reads to sessions created with this credential ('credential') or
--   allows everything the owner can read ('owner').
-- - organization: requests act as the credential's service principal, which
--   owns its sessions. New sessions get default_visibility. The manager (or
--   any Admin when there is none) manages those sessions.
--
-- Compatibility: existing credentials become organization credentials whose
-- sessions are visible to everyone in the organization, as before access
-- control. Sessions already owned by their service principals get that
-- audience and the credential marker.

ALTER TABLE api_credentials
    ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'organization',
    ADD COLUMN IF NOT EXISTS read_scope text NOT NULL DEFAULT 'credential',
    ADD COLUMN IF NOT EXISTS default_visibility text NOT NULL DEFAULT 'private';

UPDATE api_credentials SET default_visibility = 'tenant';

ALTER TABLE api_credentials
    ADD CONSTRAINT api_credentials_kind_check
        CHECK (kind IN ('personal', 'organization')),
    ADD CONSTRAINT api_credentials_read_scope_check
        CHECK (read_scope IN ('credential', 'owner')),
    ADD CONSTRAINT api_credentials_default_visibility_check
        CHECK (default_visibility IN ('private', 'tenant')),
    ADD CONSTRAINT api_credentials_personal_owner_check
        CHECK (kind = 'organization' OR manager_user_id IS NOT NULL),
    ADD CONSTRAINT api_credentials_id_tenant_uniq UNIQUE (id, tenant_id);

CREATE INDEX IF NOT EXISTS idx_api_credentials_tenant_service
    ON api_credentials(tenant_id, service_user_id);

ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS created_via_credential_id uuid;

ALTER TABLE sessions
    ADD CONSTRAINT sessions_credential_same_tenant_fk
        FOREIGN KEY (created_via_credential_id, tenant_id)
        REFERENCES api_credentials(id, tenant_id);

CREATE INDEX IF NOT EXISTS idx_sessions_tenant_credential
    ON sessions(tenant_id, created_via_credential_id)
    WHERE created_via_credential_id IS NOT NULL;

UPDATE sessions s
   SET visibility = 'tenant',
       created_via_credential_id = c.id,
       access_revision = s.access_revision + 1
  FROM api_credentials c
 WHERE c.service_user_id = s.user_id
   AND c.tenant_id = s.tenant_id
   AND s.created_via_credential_id IS NULL;
