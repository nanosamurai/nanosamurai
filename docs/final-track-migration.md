# Final track migration

Migration `017-add-final-track-identity.up.sql` adds nullable
`session_transcripts.track_id` and uniqueness on recordings' `(session_id,
recording_url)` and tagged final transcripts' `(recording_id, track_id)`.
Transcript text and segment JSON keep their existing shape. Old NULL tracks
remain history and are read as WhisperX. New untagged events use WhisperX.

Nanodeploy and Nanosamurai own the migration. Keep Nanodeploy's Docker and
chart SQL copies byte-identical to Nanosamurai's Docker SQL. Persistor's
historical Migratus files are not the deployment migration ledger. This
duplication can drift; compare hashes whenever promoting the service changes.
No Helm templates, image pins or cloud deployment are changed by this spike.

Apply the migration transactionally before starting the changed services.
The SQL takes short table locks to inspect duplicates and build the indexes.
It aborts on duplicate recording URLs or tagged final results, without deleting
or rewriting history. Operators must inspect and reconcile such references
before retrying; do not reset volumes or edit an applied migration.

Preflight queries (counts/groups only; no transcript text):

```sql
SELECT session_id, recording_url, count(*) FROM recordings
GROUP BY session_id, recording_url HAVING count(*) > 1;
SELECT recording_id, track_id, count(*) FROM session_transcripts
WHERE type='final' AND track_id IS NOT NULL AND recording_id IS NOT NULL
GROUP BY recording_id, track_id HAVING count(*) > 1;
```

The retained local spike database was inspected on 2026-09-13: 49 transcript
rows (48 tagged), zero duplicate recording groups and zero duplicate tagged
final groups. Its ledger already contained experimental versions 014 and 016,
so versions 014-016 are deliberately not reused. Extra experimental schema,
existing rows and applied ledger entries remain intact. This is preflight
evidence; execution results belong in the spike smoke report.

The first live write exposed `session_transcripts_final_track_check` from the
old experiment: it required `result_id`, `plan_id` and `profile_id` on every
non-NULL track. Forward migration 018 retires that obsolete check, leaving
foreign keys, uniqueness indexes, old columns and history intact. It is a
no-op on clean master schemas. Migration 017 remains unchanged after application.