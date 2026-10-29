-- 022-add-access-control
--
-- Application principals, fixed roles, recording audiences, integration
-- ownership and a payload-free access audit trail.
--
-- The OIDC identity provider stays authoritative for identity and credentials.
-- These tables are authoritative for membership, role, suspension and session
-- visibility.
--
-- Compatibility:
-- - Existing app_users rows were created explicitly by operators. They keep
--   access as active human members. No row becomes an Admin automatically.
-- - Existing sessions keep their audience: everyone in their tenant, as every
--   signed-in person read every session of the tenant before. Recorded owners
--   stay. The BFF never stored who recorded a session with sign-in, so those
--   sessions have no owner; the tenant's Admins manage them and can assign one.
--   New sessions start private to their owner.
-- - Existing workflows, webhooks and API credentials become Admin-managed:
--   published definitions without a human owner.
-- - The local guest principal (auth disabled only) becomes the guest tenant Admin.

ALTER TABLE app_users
    ALTER COLUMN email DROP NOT NULL,
    ADD COLUMN IF NOT EXISTS issuer text,
    ADD COLUMN IF NOT EXISTS principal_type text NOT NULL DEFAULT 'human',
    ADD COLUMN IF NOT EXISTS role text,
    ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS client_id text,
    ADD COLUMN IF NOT EXISTS setup_state text,
    ADD COLUMN IF NOT EXISTS setup_email_sent_at timestamptz,
    ADD COLUMN IF NOT EXISTS identity_sync_state text NOT NULL DEFAULT 'synced',
    ADD COLUMN IF NOT EXISTS provisioning_operation_id uuid,
    ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS last_seen_at timestamptz;

UPDATE app_users SET role = 'member' WHERE role IS NULL AND principal_type = 'human';

UPDATE app_users
   SET role = 'admin',
       issuer = 'urn:nanosamurai:guest'
 WHERE id = '00000000-0000-0000-0000-000000000001'
   AND tenant_id = '00000000-0000-0000-0000-000000000000'
   AND external_id = 'guest';

ALTER TABLE app_users
    ADD CONSTRAINT app_users_principal_type_check
        CHECK (principal_type IN ('human', 'service')),
    ADD CONSTRAINT app_users_role_check
        CHECK ((principal_type = 'human' AND role IN ('member', 'builder', 'admin'))
            OR (principal_type = 'service' AND role IS NULL)),
    ADD CONSTRAINT app_users_status_check
        CHECK (status IN ('pending', 'active', 'suspended')),
    ADD CONSTRAINT app_users_setup_state_check
        CHECK (setup_state IS NULL OR setup_state IN ('email_pending', 'email_sent', 'email_failed', 'complete')),
    ADD CONSTRAINT app_users_identity_sync_state_check
        CHECK (identity_sync_state IN ('synced', 'disable_pending', 'enable_pending')),
    ADD CONSTRAINT app_users_service_client_check
        CHECK (principal_type = 'human' OR client_id IS NOT NULL),
    ADD CONSTRAINT app_users_id_tenant_uniq UNIQUE (id, tenant_id);

CREATE UNIQUE INDEX IF NOT EXISTS app_users_issuer_subject_uniq
    ON app_users(issuer, external_id) WHERE issuer IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS app_users_provisioning_operation_uniq
    ON app_users(provisioning_operation_id) WHERE provisioning_operation_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_app_users_tenant_directory
    ON app_users(tenant_id, principal_type, status, name);

-- Sessions: immutable owner plus one constrained audience.
-- Rows present now (recorded before access control) get 'tenant'; then the
-- default becomes 'private' for every new session.
ALTER TABLE sessions
    ADD COLUMN IF NOT EXISTS visibility text NOT NULL DEFAULT 'tenant',
    ADD COLUMN IF NOT EXISTS access_revision bigint NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS admission_snapshot jsonb;
ALTER TABLE sessions ALTER COLUMN visibility SET DEFAULT 'private';

ALTER TABLE sessions
    ADD CONSTRAINT sessions_visibility_check
        CHECK (visibility IN ('private', 'selected', 'tenant')),
    ADD CONSTRAINT sessions_id_tenant_uniq UNIQUE (id, tenant_id),
    ADD CONSTRAINT sessions_owner_same_tenant_fk
        FOREIGN KEY (user_id, tenant_id) REFERENCES app_users(id, tenant_id) NOT VALID;

CREATE INDEX IF NOT EXISTS idx_sessions_tenant_owner_created
    ON sessions(tenant_id, user_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_tenant_visibility_created
    ON sessions(tenant_id, visibility, created_at DESC, id DESC);

-- Read-only grants for the Selected people audience.
CREATE TABLE IF NOT EXISTS session_access_grants (
    session_id   uuid NOT NULL,
    tenant_id    uuid NOT NULL,
    user_id      uuid NOT NULL,
    granted_by   uuid,
    created_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, user_id),
    FOREIGN KEY (session_id, tenant_id) REFERENCES sessions(id, tenant_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id, tenant_id) REFERENCES app_users(id, tenant_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_session_access_grants_recipient
    ON session_access_grants(tenant_id, user_id, session_id);

-- Integration ownership: personal definitions belong to one human owner.
ALTER TABLE workflows
    ADD COLUMN IF NOT EXISTS owner_user_id uuid,
    ADD COLUMN IF NOT EXISTS availability text NOT NULL DEFAULT 'published';

ALTER TABLE workflows
    ADD CONSTRAINT workflows_availability_check
        CHECK (availability IN ('personal', 'published')),
    ADD CONSTRAINT workflows_personal_owner_check
        CHECK (availability = 'published' OR owner_user_id IS NOT NULL),
    ADD CONSTRAINT workflows_owner_same_tenant_fk
        FOREIGN KEY (owner_user_id, tenant_id) REFERENCES app_users(id, tenant_id);

ALTER TABLE webhooks
    ADD COLUMN IF NOT EXISTS owner_user_id uuid,
    ADD COLUMN IF NOT EXISTS availability text NOT NULL DEFAULT 'published';

ALTER TABLE webhooks
    ADD CONSTRAINT webhooks_availability_check
        CHECK (availability IN ('personal', 'published')),
    ADD CONSTRAINT webhooks_personal_owner_check
        CHECK (availability = 'published' OR owner_user_id IS NOT NULL),
    ADD CONSTRAINT webhooks_owner_same_tenant_fk
        FOREIGN KEY (owner_user_id, tenant_id) REFERENCES app_users(id, tenant_id);

CREATE INDEX IF NOT EXISTS idx_workflows_tenant_owner ON workflows(tenant_id, owner_user_id);
CREATE INDEX IF NOT EXISTS idx_webhooks_tenant_owner ON webhooks(tenant_id, owner_user_id);

-- Credential management: a human manager and the bound service principal.
ALTER TABLE api_credentials
    ADD COLUMN IF NOT EXISTS manager_user_id uuid,
    ADD COLUMN IF NOT EXISTS service_user_id uuid,
    ADD COLUMN IF NOT EXISTS identity_sync_state text NOT NULL DEFAULT 'synced';

ALTER TABLE api_credentials
    ADD CONSTRAINT api_credentials_manager_same_tenant_fk
        FOREIGN KEY (manager_user_id, tenant_id) REFERENCES app_users(id, tenant_id),
    ADD CONSTRAINT api_credentials_service_same_tenant_fk
        FOREIGN KEY (service_user_id, tenant_id) REFERENCES app_users(id, tenant_id),
    ADD CONSTRAINT api_credentials_identity_sync_state_check
        CHECK (identity_sync_state IN ('synced', 'disable_pending'));

CREATE INDEX IF NOT EXISTS idx_api_credentials_tenant_manager
    ON api_credentials(tenant_id, manager_user_id);

-- Payload-free audit trail for membership, role, credential and sharing decisions.
CREATE TABLE IF NOT EXISTS access_audit_events (
    id             uuid PRIMARY KEY,
    tenant_id      uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    actor_user_id  uuid,
    actor_kind     text NOT NULL,
    action         text NOT NULL,
    target_type    text NOT NULL,
    target_id      text,
    outcome        text NOT NULL,
    details        jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT access_audit_events_actor_kind_check
        CHECK (actor_kind IN ('user', 'service', 'operator', 'system')),
    CONSTRAINT access_audit_events_outcome_check
        CHECK (outcome IN ('succeeded', 'denied', 'failed', 'pending'))
);

CREATE INDEX IF NOT EXISTS idx_access_audit_events_tenant_created
    ON access_audit_events(tenant_id, created_at DESC);
