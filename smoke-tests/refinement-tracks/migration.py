"""Exercise migration 019 in an isolated, rolled-back schema on real Postgres."""
import uuid
from pathlib import Path

import psycopg
from psycopg import sql

with psycopg.connect("") as db:
    schema = "refinement_migration_" + uuid.uuid4().hex
    db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    db.execute(sql.SQL("SET LOCAL search_path TO {}").format(sql.Identifier(schema)))
    db.execute("CREATE TABLE session_transcripts (id int, tenant_id int, session_id int, "
               "track_id text, type text, window_length int, segment_start_s float8, "
               "segment_end_s float8, full_text text, segments jsonb)")
    db.execute("INSERT INTO session_transcripts VALUES "
               "(1,1,1,NULL,'refined',10,0,10,'history','[]'),"
               "(2,1,1,NULL,'refined',10,0,10,'history','[]'),"
               "(3,1,1,'whisperx','refined',10,10,20,'first','[]'),"
               "(4,1,1,'whisperx','refined',10,10,20,'duplicate','[]')")
    migration = Path("/migrations/019-add-refinement-track-identity.up.sql").read_text()
    try:
        with db.transaction():
            db.execute(migration)
        raise AssertionError("Duplicate tagged windows must block migration")
    except psycopg.errors.RaiseException:
        pass
    assert db.execute("SELECT count(*) FROM session_transcripts").fetchone()[0] == 4
    db.execute("UPDATE session_transcripts SET track_id='test-shadow' WHERE id=4")
    db.execute(migration)
    db.execute(migration)
    db.execute("INSERT INTO session_transcripts VALUES (5,1,1,'whisperx','refined',10,10,20,'replay','[]') "
               "ON CONFLICT (tenant_id,session_id,track_id,window_length,segment_start_s,segment_end_s) "
               "WHERE type='refined' AND track_id IS NOT NULL DO NOTHING")
    db.execute("INSERT INTO session_transcripts VALUES "
               "(6,1,1,'whisperx','refined',10,20,23.125,'tail','[]'),"
               "(7,2,2,'whisperx','refined',10,10,20,'other tenant','[]'),"
               "(8,1,1,'whisperx','refined',NULL,0,0,'legacy event','[]')")
    db.execute("INSERT INTO session_transcripts VALUES "
               "(9,1,1,'whisperx','refined',NULL,0,0,'legacy replay','[]') ON CONFLICT DO NOTHING")
    assert db.execute("SELECT count(*) FROM session_transcripts").fetchone()[0] == 7
    assert db.execute("SELECT count(*) FROM session_transcripts WHERE track_id IS NULL").fetchone()[0] == 2
    assert db.execute("SELECT full_text FROM session_transcripts WHERE id=3").fetchone()[0] == "first"
    db.rollback()
print("PASS migration duplicate preflight, NULL history, window uniqueness and repeat application (rolled back)")
