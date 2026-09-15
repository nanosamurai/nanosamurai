"""Exercise migrations 017/018 in a rolled-back schema, preserving the database."""
from pathlib import Path
import re
import uuid

import psycopg
from psycopg import sql

with psycopg.connect("") as db:
    schema = "lean_migration_" + uuid.uuid4().hex
    db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    db.execute("SELECT set_config('search_path', %s, false)", (schema,))

    def execute(statement):
        """Qualify all fixture tables and refuse to execute outside the test schema."""
        assert db.execute("SELECT current_schema()").fetchone()[0] == schema
        statement = re.sub(r"\b(recordings|session_transcripts)\b", lambda m: schema + "." + m[0], statement)
        return db.execute(statement)

    execute("CREATE TABLE recordings(id int PRIMARY KEY, session_id int, recording_url text)")
    execute("CREATE TABLE session_transcripts(id int PRIMARY KEY, recording_id int REFERENCES recordings(id), "
            "type text, full_text text, segments jsonb)")
    execute("INSERT INTO recordings VALUES (1,1,'file://test.wav'),(2,1,'file://test.wav')")
    execute("INSERT INTO session_transcripts VALUES (1,1,'final','history one','[]'),(2,2,'final','history two','[]')")
    migration = Path("/migrations/017-add-final-track-identity.up.sql").read_text()
    try:
        with db.transaction():
            assert db.execute("SELECT current_schema()").fetchone()[0] == schema
            db.execute(migration)
        raise AssertionError("Duplicate recordings must stop migration")
    except psycopg.errors.RaiseException as error:
        assert "Duplicate recordings" in str(error)
    assert execute("SELECT count(*) FROM session_transcripts").fetchone()[0] == 2
    execute("UPDATE recordings SET recording_url='file://different.wav' WHERE id=2")
    assert db.execute("SELECT current_schema()").fetchone()[0] == schema
    db.execute(migration)
    db.execute(migration)
    assert execute("SELECT count(*) FROM session_transcripts WHERE track_id IS NULL").fetchone()[0] == 2
    execute("ALTER TABLE session_transcripts ADD COLUMN result_id uuid, ADD COLUMN plan_id uuid, "
            "ADD COLUMN profile_id text, ADD CONSTRAINT session_transcripts_final_track_check "
            "CHECK (track_id IS NULL OR (result_id IS NOT NULL AND plan_id IS NOT NULL "
            "AND profile_id IS NOT NULL AND recording_id IS NOT NULL AND type='final'))")
    assert db.execute("SELECT current_schema()").fetchone()[0] == schema
    db.execute(Path("/migrations/018-retire-experimental-final-track-check.up.sql").read_text())
    execute("INSERT INTO session_transcripts (id,recording_id,type,full_text,segments,track_id) "
            "VALUES (3,1,'final','first','[]','whisperx')")
    execute("INSERT INTO session_transcripts (id,recording_id,type,full_text,segments,track_id) "
            "VALUES (4,1,'final','second','[]','test-shadow')")
    execute("INSERT INTO session_transcripts (id,recording_id,type,full_text,segments,track_id) "
            "VALUES (5,1,'final','replay','[]','whisperx') "
            "ON CONFLICT (recording_id,track_id) WHERE type='final' AND track_id IS NOT NULL DO NOTHING")
    assert execute("SELECT full_text FROM session_transcripts WHERE track_id='whisperx'").fetchone()[0] == "first"
    assert execute("SELECT count(*) FROM session_transcripts").fetchone()[0] == 4
    db.rollback()
print("PASS migration duplicate guard, historical NULL rows, indexes and repeat application (rolled back)")
