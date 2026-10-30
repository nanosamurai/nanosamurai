-- Match the tenant-scoped Sessions page ordering and cover draft counts.
-- Built inside the migration transaction; it blocks writes to sessions while it builds.
CREATE INDEX IF NOT EXISTS idx_sessions_tenant_created_at_id
    ON sessions (tenant_id, created_at DESC, id DESC) INCLUDE (status);
