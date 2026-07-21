#!/bin/sh

set -eu

psql_cmd() {
  psql -h postgres -U drsynth -d nanosamurai -v ON_ERROR_STOP=1 "$@"
}

psql_cmd -c "
  CREATE TABLE IF NOT EXISTS nanosamurai_schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
  )
"

is_applied() {
  [ "$(psql_cmd -tAc "SELECT count(*) FROM nanosamurai_schema_migrations WHERE version = '$1'")" = "1" ]
}

mark_applied() {
  psql_cmd -c "INSERT INTO nanosamurai_schema_migrations(version) VALUES ('$1') ON CONFLICT DO NOTHING"
}

table_exists() {
  [ "$(psql_cmd -tAc "SELECT to_regclass('public.$1') IS NOT NULL")" = "t" ]
}

column_exists() {
  [ "$(psql_cmd -tAc "SELECT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema = 'public' AND table_name = '$1' AND column_name = '$2')")" = "t" ]
}

# Adopt volumes created by the original Compose runner. That runner applied
# migrations 001-009 as one bootstrap unit whenever the tenants table did not
# yet exist, so an existing tenants table is a reliable local-volume marker.
if table_exists tenants && ! is_applied 001; then
  for version in 001 002 003 004 005 006 007 008 009; do
    mark_applied "$version"
  done
fi

# Adopt later migrations that may have been applied before the migration
# ledger was introduced. Check their primary schema object rather than
# blindly rerunning ALTER TABLE statements and named constraints.
table_exists workflows && mark_applied 010
column_exists sessions workflow_overrides && mark_applied 011
table_exists workflow_results_history && mark_applied 012
table_exists workflow_outcomes && mark_applied 013

apply_migration() {
  version="$1"
  file="$2"

  if is_applied "$version"; then
    printf 'Migration %s already applied\n' "$version"
    return
  fi

  printf 'Applying migration %s\n' "$version"
  psql_cmd --single-transaction \
    -f "/migrations/$file" \
    -c "INSERT INTO nanosamurai_schema_migrations(version) VALUES ('$version')"
}

apply_migration 001 001-create-core-schema.up.sql
apply_migration 002 002-transcript-records-append-only.up.sql
apply_migration 003 003-sessions-started-at-nullable.up.sql
apply_migration 004 004-create-api-credentials.up.sql
apply_migration 005 005-sessions-stream-controls.up.sql
apply_migration 006 006-webhooks-tables.up.sql
apply_migration 007 007-sessions-webhook-overrides.up.sql
apply_migration 008 008-sessions-session-settings.up.sql
apply_migration 009 009-webhook-delivery-outcomes.up.sql
apply_migration 010 010-workflows-tables.up.sql
apply_migration 011 011-sessions-workflow-overrides.up.sql
apply_migration 012 012-workflow-results.up.sql
apply_migration 013 013-workflow-outcomes.up.sql
