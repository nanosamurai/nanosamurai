"""Verify browser-created sessions through real Postgres, Kafka and HTTP boundaries."""
import json
import os
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import psycopg
from confluent_kafka import Consumer

sessions = json.loads(Path('/probe/evidence/sessions.json').read_text())
expected = {}
with psycopg.connect('', autocommit=True) as db:
    for item in sessions:
        sid = item['id']
        controls, = db.execute('SELECT stream_controls FROM sessions WHERE id=%s', (sid,)).fetchone()
        if 'realtime_settings' in item:
            assert controls['realtime_settings'] == item['realtime_settings']
        expected[sid] = controls
        rows = db.execute('SELECT type,track_id,recording_id FROM session_transcripts WHERE session_id=%s', (sid,)).fetchall()
        assert all(controls[stage] for stage, _, _ in rows), item['label']
        if controls['final']:
            recordings = db.execute('SELECT count(*) FROM recordings WHERE session_id=%s', (sid,)).fetchone()[0]
            assert recordings == 1, (item['label'], recordings)
            assert len({recording for stage, _, recording in rows if stage == 'final'}) == 1
        with urlopen(os.environ['BFF_URL'] + '/api/recordings/' + sid) as response:
            detail = json.load(response)
        assert detail['session']['stream_controls'] == controls
    foreign = uuid.uuid4()
    foreign_session = uuid.uuid4()
    with db.transaction():
        db.execute("INSERT INTO tenants(id,name) VALUES (%s,'UI smoke tenant')", (foreign,))
        db.execute('INSERT INTO sessions(id,tenant_id,session_key) VALUES (%s,%s,%s)',
                   (foreign_session, foreign, str(foreign_session)))
    try:
        for suffix in ['', '/audio']:
            try:
                urlopen(os.environ['BFF_URL'] + '/api/recordings/' + str(foreign_session) + suffix)
                raise AssertionError('Foreign session was exposed')
            except HTTPError as error:
                assert error.code == 404
    finally:
        db.execute('DELETE FROM sessions WHERE id=%s AND tenant_id=%s', (foreign_session, foreign))
        db.execute('DELETE FROM tenants WHERE id=%s', (foreign,))
print('PASS saved controls, selected outputs and tenant denial', flush=True)

consumer = Consumer({'bootstrap.servers': os.environ['KAFKA_BOOTSTRAP'],
                     'group.id': 'ui-audit-' + uuid.uuid4().hex,
                     'auto.offset.reset': 'earliest', 'enable.auto.commit': False})
try:
    consumer.subscribe(['sessions.meta'])
    deadline = time.monotonic() + 60
    while expected and time.monotonic() < deadline:
        message = consumer.poll(1)
        if message is None or message.value() is None:
            continue
        assert not message.error(), message.error()
        event = json.loads(message.value())
        sid = event.get('session_id')
        if sid in expected and 'stream_controls' in event:
            assert event['stream_controls'] == expected.pop(sid)
    assert not expected, 'Missing sessions.meta selections/labels'
finally:
    consumer.close()
print('PASS selected labels and controls copied to the existing sessions.meta topic', flush=True)
