-- Seed data for local development.
--
-- Required because the BFF unauthenticated/dev mode uses a hard-coded tenant id,
-- and the schema has FK constraints sessions.tenant_id -> tenants.id.

BEGIN;

-- The dev/guest tenant used by samuraibff when auth is disabled.
INSERT INTO tenants (id, name)
VALUES ('00000000-0000-0000-0000-000000000000', 'dev-tenant')
ON CONFLICT (id) DO NOTHING;

-- Guest principal used only while authentication is disabled. It owns local
-- evaluator sessions and is the Admin of the guest tenant. The issuer is not an
-- OIDC issuer, so a signed-in token can never resolve to this principal.
-- Migration 022 gives an existing guest row the same role and issuer.
INSERT INTO app_users (id, tenant_id, external_id, issuer, principal_type, role, status, email, name)
VALUES (
  '00000000-0000-0000-0000-000000000001',
  '00000000-0000-0000-0000-000000000000',
  'guest',
  'urn:nanosamurai:guest',
  'human',
  'admin',
  'active',
  'guest@example.local',
  'Guest'
)
ON CONFLICT (external_id) DO NOTHING;

COMMIT;
