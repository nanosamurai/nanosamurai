-- Seed data for local development.
--
-- Required because the BFF unauthenticated/dev mode uses a hard-coded tenant id,
-- and the schema has FK constraints sessions.tenant_id -> tenants.id.

BEGIN;

-- The dev/guest tenant used by samuraibff when auth is disabled.
INSERT INTO tenants (id, name)
VALUES ('00000000-0000-0000-0000-000000000000', 'dev-tenant')
ON CONFLICT (id) DO NOTHING;

-- Optional guest user (can be useful if/when unauth mode starts mapping sessions.user_id).
INSERT INTO app_users (id, tenant_id, external_id, email, name, roles)
VALUES (
  '00000000-0000-0000-0000-000000000001',
  '00000000-0000-0000-0000-000000000000',
  'guest',
  'guest@example.local',
  'Guest',
  'dev'
)
ON CONFLICT (external_id) DO NOTHING;

COMMIT;
