# Track storage migrations

Apply migrations 017–019 before you start services that use final or refinement
track selection. Migration 019 requires PostgreSQL 15 or later.
Follow [Prepare the database](models/source-builds.md#prepare-the-database)
for the upgrade sequence. Keep the existing PostgreSQL major version and volumes.

| Migration | Change |
| --- | --- |
| 017 | Add nullable `track_id`; make recording URLs unique per session and final results unique per recording and track |
| 018 | Remove the obsolete `session_transcripts_final_track_check` constraint from an earlier local experiment |
| 019 | Make refined results unique per tenant, session, track, window length, and time bounds |

Historical rows with NULL track IDs, transcript text, and segment JSON remain
unchanged. Readers treat old untagged results as WhisperX. New untagged events
also use WhisperX. Migration 019 uses `NULLS NOT DISTINCT` so that tagged
replays without a window length still have one stored result.

## Before an upgrade

Back up Postgres and recording storage. Inspect the migration ledger.
Versions 014–016 were used by local experiments; do not reuse them or remove
applied ledger entries. Migration 018 removes only the obsolete constraint.
It does not remove old tables or columns. Such cleanup needs a separate review.

Migrations 017 and 019 lock the affected tables while they check duplicates
and create indexes. They abort on duplicate tagged results or recording URLs.
Inspect and resolve conflicts without deleting transcript history before you
retry. Do not edit an applied migration or reset volumes.

Check duplicate recording URLs before migration 017:

```sql
SELECT session_id, recording_url, count(*) FROM recordings
GROUP BY session_id, recording_url HAVING count(*) > 1;
```

If `session_transcripts.track_id` already exists, also check tagged results:

```sql
SELECT recording_id, track_id, count(*) FROM session_transcripts
WHERE type='final' AND track_id IS NOT NULL AND recording_id IS NOT NULL
GROUP BY recording_id, track_id HAVING count(*) > 1;

SELECT tenant_id, session_id, track_id, window_length,
       segment_start_s, segment_end_s, count(*) FROM session_transcripts
WHERE type='refined' AND track_id IS NOT NULL
GROUP BY tenant_id, session_id, track_id, window_length,
         segment_start_s, segment_end_s HAVING count(*) > 1;
```

These queries return groups and counts, not transcript text.

## Migration ownership

Nanosamurai and Nanodeploy own deployment migrations. Keep their Docker SQL
and Nanodeploy's chart copies of 017–019 identical. Compare the SQL and migration
runner configuration before promotion. Apply each migration in a transaction.
Do not use Persistor's historical Migratus files as the deployment ledger.

Use the [track migration probes](track-checks.md) to test SQL behavior in
separate schemas. These probes roll back; they do not upgrade the application
database. Past local test results do not validate a new image set or Helm deployment.
