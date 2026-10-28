-- 023-assign-guest-legacy-sessions
--
-- Give ownerless sessions of the guest tenant to the guest principal.
--
-- With authentication disabled (a single-user, local install) every request
-- runs as the guest principal. Sessions recorded before sessions had an owner
-- have user_id NULL, and 022 made ownerless sessions unreadable, so they
-- disappeared from such installs. The guest tenant has exactly one person,
-- so the guest is their only possible owner.
--
-- Scope: only rows in the tenant of the guest principal (issuer
-- urn:nanosamurai:guest). Ownerless sessions of real tenants are untouched;
-- operators resolve those explicitly (`samuraibff.tools.principals
-- legacy-report` / `assign-owner`). Without a guest principal this is a no-op.
-- Guest sessions stay private, and the guest principal is unreachable while
-- authentication is required, so no other identity gains access.

UPDATE sessions s
   SET user_id = g.id
  FROM app_users g
 WHERE g.issuer = 'urn:nanosamurai:guest'
   AND g.principal_type = 'human'
   AND s.tenant_id = g.tenant_id
   AND s.user_id IS NULL;

UPDATE session_transcripts t
   SET user_id = s.user_id
  FROM sessions s, app_users g
 WHERE g.issuer = 'urn:nanosamurai:guest'
   AND s.id = t.session_id
   AND s.tenant_id = g.tenant_id
   AND s.user_id = g.id
   AND t.user_id IS NULL;
