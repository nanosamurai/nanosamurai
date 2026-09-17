"""Spike 2 Compose qualification; real Kafka/Postgres/BFF plus real WhisperX."""
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
import wave
from pathlib import Path
from urllib.parse import urlencode

from confluent_kafka import ConsumerGroupTopicPartitions
from websockets.sync.client import connect
from websockets.exceptions import InvalidStatus

sys.path.insert(0, '/probe/final')
import smoke as f

f.TOPICS['transcripts.refined'] = f.pb.RefinedEvent
GROUP = 'refinement.test-shadow.' + uuid.uuid4().hex
PROCESSES = []
TMP = Path(tempfile.mkdtemp(prefix='refinement-smoke-'))


def worker(label, track='test-shadow', group=GROUP, **extra):
    """Launch a real worker with only inference substituted, using no host ports."""
    env = dict(os.environ, REFINEMENT_TRACK_ID=track, KAFKA_GROUP_ID=group,
               KAFKA_CLIENT_ID=label, WHISPERX_MODEL='synthetic-test-only',
               WHISPERX_READY_QUEUE_MAX='1', **extra)
    log = (TMP / (label + '.log')).open('w')
    process = subprocess.Popen([sys.executable, '/probe/refinement/synthetic_refinement.py'],
                               env=env, stdout=log, stderr=subprocess.STDOUT)
    log.close()
    PROCESSES.append(process)
    return process


def members(group=GROUP):
    """Read consumer membership/partition assignments from the actual broker."""
    description = f.ADMIN.describe_consumer_groups([group])[group].result(10)
    return description.members if description.state.name == 'STABLE' else []


def rows(session):
    """Read only a newly created smoke session, with stable order for replay checks."""
    return f.DB.execute('SELECT track_id,model,full_text,segments,window_length,segment_start_s,segment_end_s '
                        "FROM session_transcripts WHERE session_id=%s AND type='refined' "
                        'ORDER BY track_id,segment_start_s', (session,)).fetchall()


def audio_socket(session, tracks=None, refined=True):
    """Open BFF ingress with independent refinement selection; final/realtime disabled."""
    params = dict(session_id=session, lang='cs', sample_rate=16000, realtime='false',
                  final='false', refined=str(refined).lower(), refinement_window_sec=10)
    if not refined:
        params['final'] = 'true'
    if tracks is not None:
        params['refinement_tracks'] = tracks
    return connect(f.BFF.replace('http', 'ws', 1) + '/ws/audio?' + urlencode(params), open_timeout=15)


def send(ws, pcm):
    """Send normal 200 ms BFF frames; keep inference tests shorter than real-time."""
    for start in range(0, len(pcm), 6400):
        ws.send(pcm[start:start + 6400])
        time.sleep(0.02)


def raw(session, seconds, seq=1, partition=0, tracks=b'test-shadow'):
    """Send retained audio for restart/interleaving tests, with existing message shape."""
    event = f.pb.AudioChunk(session_id=session, tenant_id=f.TENANT, seq=seq, sample_rate=16000,
                           pcm16_le=b'\0\0' * round(seconds * 16000), lang='cs')
    f.PRODUCER.produce('audio.raw', key=session.encode(), value=event.SerializeToString(),
                       partition=partition, headers=[('x-outputs', b'refined'),
                         ('x-refinement-window-sec', b'10'), ('x-refinement-tracks', tracks)])
    assert f.PRODUCER.flush(15) == 0


def observed(session):
    return f.EVENTS.get((session, 'transcripts.refined'), [])


def normal_session(speech):
    """Drain live events while checking the ordinary stack, including playback."""
    normal = f.new_session()
    params = urlencode(dict(session_id=normal, lang='cs', realtime='true', refined='true', final='true',
                            realtime_tracks='nemotron', refinement_window_sec=10))
    with connect(f.BFF.replace('http', 'ws', 1) + '/ws/events?' + urlencode({'session_id': normal})) as events:
        with connect(f.BFF.replace('http', 'ws', 1) + '/ws/audio?' + params, open_timeout=30) as ws:
            send(ws, speech[:12 * 32000])
        realtime = False
        until = time.monotonic() + 300
        while time.monotonic() < until:
            f.pump()
            try:
                event = json.loads(events.recv(timeout=.1))
                realtime |= event.get('type') == 'asr' and bool(event.get('text', '').strip())
            except TimeoutError:
                pass
            if realtime and len(f.rows(normal)) == 1 and len(rows(normal)) == 2:
                break
        else:
            raise AssertionError('Ordinary realtime/refined/final session did not complete')
    status, audio, _ = f.http(f'/api/recordings/{normal}/audio')
    assert status == 200 and audio[:4] == b'RIFF'
    assert f.http(f'/api/recordings/{normal}/audio', headers={'Range': 'bytes=0-43'})[0] == 206
    print('PASS ordinary session realtime output and shared recording playback', flush=True)


def parakeet(speech):
    """Real Parakeet and WhisperX windows through live BFF, Kafka, persistence and HTTP."""
    groups = ['refinement.parakeet', os.getenv('WHISPERX_REFINEMENT_GROUP', 'whisperx-async')]
    session = f.new_session()
    live = []
    with connect(f.BFF.replace('http', 'ws', 1) + '/ws/events?' + urlencode({'session_id': session})) as events:
        with audio_socket(session, 'parakeet,whisperx') as ws:
            send(ws, speech)
            # Keep ingress open: full windows must arrive before session completion.
            deadline = time.monotonic() + 900
            while time.monotonic() < deadline:
                f.pump()
                try:
                    event = json.loads(events.recv(timeout=.1))
                    if event.get('type') == 'refined':
                        live.append(event)
                except TimeoutError:
                    pass
                if len(rows(session)) == 6 and len({(e['track_id'], e['slice_index']) for e in live}) == 6:
                    break
            else:
                raise AssertionError('Both real refinement tracks must arrive live')
    assert {e['track_id'] for e in live} == {'parakeet', 'whisperx'}
    saved = rows(session)
    for track in ['parakeet', 'whisperx']:
        track_rows = [r for r in saved if r['track_id'] == track]
        assert [(r['segment_start_s'], r['segment_end_s']) for r in track_rows] == [(0, 10), (10, 20), (20, 23.125)]
        assert all(r['window_length'] == 10 and r['full_text'].strip() for r in track_rows)
        assert all(r['model'] == ('nvidia/parakeet-tdt-0.6b-v3' if track == 'parakeet' else 'medium') for r in track_rows)
        status, history, _ = f.http(f'/api/recordings/{session}?track_id={track}')
        assert status == 200 and len(history['transcripts']['refined']) == 3
        assert [(r['full_text'], r['segments']) for r in history['transcripts']['refined']] == [
            (r['full_text'], r['segments']) for r in track_rows]
        for row in track_rows:
            if track == 'parakeet':
                words = [w for segment in row['segments'] for w in segment.get('words', [])]
                assert words and any(s['speaker'].startswith('SPEAKER_') for s in row['segments'])
                assert all(row['segment_start_s'] <= w['start_s'] <= w['end_s'] <= row['segment_end_s']
                           for w in words)
                assert ''.join(row['full_text'].split()) == ''.join(w['text'].replace(' ', '') for w in words)
    assert any(e.get('speaker', '').startswith('SPEAKER_') for e in live if e['track_id'] == 'parakeet')
    assert all(e['window_start_s'] <= e['start_s'] <= e['end_s'] <= e['window_end_s'] + .1 for e in live)
    f.wait_for(lambda: len(observed(session)) == 6, 'both real tracks observed on Kafka')
    assert all(ev.refinement_model == ('nvidia/parakeet-tdt-0.6b-v3' if ev.track_id == 'parakeet' else 'medium')
               and msg.key() == session.encode() for ev, msg in observed(session))
    assert dict(f.EVENTS[(session, 'audio.raw')][0][1].headers())['x-refinement-tracks'] == b'parakeet,whisperx'
    print('PASS real live tracks, exact windows/tail, session-relative words and filtered history', flush=True)

    # Replaying the retained input exercises real inference plus persistence deduplication.
    audio = list(f.EVENTS[(session, 'audio.raw')])
    for group in groups:
        f.wait_for(lambda: f.committed(group, audio[-1][1]), 'original session audio committed', 900)
    for _, msg in audio:
        f.replay(msg)
    f.wait_for(lambda: len(observed(session)) >= 12, 'real refinement replayed', 900)
    f.wait_for(lambda: f.committed('samuraipersistor-refined', observed(session)[-1][1]), 'Persistor consumed replay')
    assert rows(session) == saved
    # Contradictory replay must also retain the first result.
    event, msg = observed(session)[0]
    event.text = 'Replay must not replace the first result'
    f.replay(msg, event.SerializeToString())
    f.wait_for(lambda: len(observed(session)) >= 13, 'conflicting replay observed')
    f.wait_for(lambda: f.committed('samuraipersistor-refined', observed(session)[-1][1]), 'conflicting replay consumed')
    assert rows(session) == saved

    for tracks, pcm, enabled in [('parakeet', speech[:12 * 32000], True),
                                  ('whisperx', speech[:12 * 32000], True),
                                  (None, bytes(32000), True),
                                  ('parakeet,whisperx', bytes(32000), True),
                                  ('parakeet', bytes(32000), False)]:
        selected = f.new_session()
        expected = set((tracks or 'whisperx').split(',')) if enabled else set()
        with audio_socket(selected, tracks, refined=enabled) as ws:
            send(ws, pcm)
        count = (2 if len(pcm) > 10 * 32000 else 1) * len(expected)
        f.wait_for(lambda: len(rows(selected)) == count, 'selected refinement completed', 900)
        f.wait_for(lambda: sum(len(ev.pcm16_le) for ev, _ in f.EVENTS.get((selected, 'audio.raw'), [])) == len(pcm),
                   'all selection audio observed')
        last = f.EVENTS[(selected, 'audio.raw')][-1][1]
        for group in groups:
            f.wait_for(lambda: f.committed(group, last), 'selected or skipped input committed', 900)
        selected_rows = rows(selected)
        assert len(selected_rows) == count and {r['track_id'] for r in selected_rows} == expected
        if not any(pcm):
            assert all(not r['full_text'].strip() and not r['segments'] for r in selected_rows)
    foreign, foreign_session = uuid.uuid4(), uuid.uuid4()
    f.DB.execute("INSERT INTO tenants(id,name) VALUES (%s,'Parakeet refinement smoke tenant')", (foreign,))
    f.DB.execute('INSERT INTO sessions(id,tenant_id,session_key) VALUES (%s,%s,%s)',
                 (foreign_session, foreign, str(foreign_session)))
    assert f.http(f'/api/recordings/{foreign_session}?track_id=parakeet')[0] == 404
    try:
        with audio_socket(str(foreign_session), 'parakeet'):
            raise AssertionError('Foreign tenant accepted audio')
    except InvalidStatus as error:
        assert error.response.status_code == 403
    print('PASS replay, selection, defaults, silence, disabled refinement and tenant denial', flush=True)
    print('PARAKEET REFINEMENT COMPOSE SMOKE PASSED', flush=True)


def main():
    f.CONSUMER.subscribe(list(f.TOPICS))
    f.wait_for(lambda: {p.topic for p in f.CONSUMER.assignment()} == set(f.TOPICS), 'Kafka observer ready', 40)
    f.wait_for(lambda: f.http('/ready')[0] == 200, 'BFF ready after rollout', 60)
    with wave.open('/probe/test_cs.wav', 'rb') as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
        fixture = wav.readframes(wav.getnframes())
    size = round(23.125 * 32000)
    speech = (fixture * (size // len(fixture) + 1))[:size]

    if '--parakeet' in sys.argv:
        parakeet(speech)
        return

    if '--normal-only' in sys.argv:
        normal_session(speech)
        return

    shadow = worker('shadow')
    skip_group = GROUP + '.unselected'
    worker('unselected', 'test-unselected', skip_group)
    f.wait_for(lambda: len(members()) == 1 and len(members(skip_group)) == 1, 'test workers assigned', 60)
    session = f.new_session()
    for invalid in ['', 'unknown', 'whisperx,whisperx']:
        try:
            with audio_socket(session, invalid):
                raise AssertionError('Invalid selection accepted')
        except InvalidStatus as error:
            assert error.response.status_code == 400
    assert f.DB.execute('SELECT started_at FROM sessions WHERE id=%s', (session,)).fetchone()['started_at'] is None
    print('PASS invalid selections rejected before audio', flush=True)
    live = []
    with connect(f.BFF.replace('http', 'ws', 1) + '/ws/events?' + urlencode({'session_id': session})) as events:
        with audio_socket(session, 'test-shadow,whisperx') as ws:
            send(ws, speech)
            f.wait_for(lambda: len(rows(session)) == 6, 'two tracks, adjacent windows and final tail while WS remains open')
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and {e['track_id'] for e in live} != {'whisperx', 'test-shadow'}:
                message = json.loads(events.recv(timeout=10))
                if message.get('type') == 'refined':
                    live.append(message)
    assert {e['track_id'] for e in live} == {'whisperx', 'test-shadow'}
    saved = rows(session)
    for track in ['whisperx', 'test-shadow']:
        track_rows = [r for r in saved if r['track_id'] == track]
        assert [(r['segment_start_s'], r['segment_end_s']) for r in track_rows] == [(0, 10), (10, 20), (20, 23.125)]
        assert all(r['window_length'] == 10 for r in track_rows)
        assert all(r['model'] == ('medium' if track == 'whisperx' else 'synthetic-test-only') for r in track_rows)
        assert any(r['full_text'].strip() for r in track_rows)
        for row in track_rows:
            assert all(row['segment_start_s'] <= s['start_s'] <= s['end_s'] <= row['segment_end_s'] + .1
                       for s in row['segments'])
        status, history, _ = f.http(f'/api/recordings/{session}?track_id={track}')
        assert status == 200 and len(history['transcripts']['refined']) == 3
        assert [r['full_text'] for r in history['transcripts']['refined']] == [r['full_text'] for r in track_rows]
    f.wait_for(lambda: len(observed(session)) >= 6, 'refined Kafka results observed')
    assert all(m.key() == session.encode() for _, m in observed(session))
    audio = f.EVENTS[(session, 'audio.raw')]
    assert dict(audio[0][1].headers())['x-refinement-tracks'] == b'test-shadow,whisperx'
    f.wait_for(lambda: f.committed(skip_group, audio[-1][1]), 'unselected worker advances without a result')
    f.wait_for(lambda: any(v.get('stream_controls', {}).get('refinement_tracks') == ['test-shadow', 'whisperx']
                          for v, _ in f.EVENTS.get((session, 'sessions.meta'), [])), 'selection in sessions.meta')
    with audio_socket(session, 'whisperx'):
        pass
    assert f.DB.execute('SELECT stream_controls FROM sessions WHERE id=%s', (session,)).fetchone()['stream_controls']['refinement_tracks'] == ['test-shadow', 'whisperx']
    for ev, msg in list(observed(session)):
        ev.text = 'Replay must not replace first text'
        f.replay(msg, ev.SerializeToString())
    f.wait_for(lambda: len(observed(session)) >= 12, 'output replays observed')
    f.wait_for(lambda: f.committed('samuraipersistor-refined', observed(session)[-1][1]), 'refined replays persisted')
    assert rows(session) == saved
    print('PASS live routing, history/filtering, selection snapshot and first-result replay', flush=True)

    # Omitted selections route only to WhisperX, including a short silent tail.
    default = f.new_session()
    with audio_socket(default) as ws:
        send(ws, b'\0\0' * 16000)
    f.wait_for(lambda: len(rows(default)) == 1, 'default track and silence')
    assert rows(default)[0]['track_id'] == 'whisperx'
    assert rows(default)[0]['segment_end_s'] == 1

    # Block a window in the first replica, add another replica, then kill the
    # first. Retained Kafka audio must reconstruct both interleaved sessions.
    shadow.terminate()
    shadow.wait(15)
    gate = TMP / 'gate'
    gate.touch()
    first = worker('first', TEST_GATE=str(gate))
    f.wait_for(lambda: any(m.client_id == 'first' and m.assignment.topic_partitions for m in members()),
               'restart joined its existing group', 90)
    partition = next(m for m in members() if m.client_id == 'first').assignment.topic_partitions[0].partition
    a, b, skipped = f.new_session(), f.new_session(), f.new_session()
    raw(a, 3, partition=partition)
    raw(b, 10, partition=partition)
    raw(skipped, 1, partition=partition, tracks=b'whisperx')
    raw(a, 10.125, seq=2, partition=partition)
    f.wait_for(lambda: Path(str(gate) + '.entered').exists(), 'inference blocked after audio buffered', 30)
    f.wait_for(lambda: len(f.EVENTS.get((a, 'audio.raw'), [])) == 2, 'interleaved audio retained')
    first_audio = f.EVENTS[(a, 'audio.raw')][0][1]
    assert not f.committed(GROUP, first_audio), 'Committed past unfinished audio'
    second = worker('second')
    f.wait_for(lambda: len(members()) == 2, 'same-track replicas rebalanced', 90)
    first.kill()
    first.wait(15)
    gate.unlink()
    f.wait_for(lambda: len(rows(a)) == 2 and len(rows(b)) == 1, 'reconstruct unfinished windows after owner loss', 120)
    assert [(r['segment_start_s'], r['segment_end_s']) for r in rows(a)] == [(0, 10), (10, 13.125)]
    assert [(r['segment_start_s'], r['segment_end_s']) for r in rows(b)] == [(0, 10)]
    f.wait_for(lambda: f.committed(GROUP, f.EVENTS[(a, 'audio.raw')][-1][1]), 'commit reconstructed tail')
    worker('third')
    f.wait_for(lambda: len(members()) == 2, 'two same-track replicas stable', 90)
    stable = f.new_session()
    raw(stable, 23.125, partition=partition)
    f.wait_for(lambda: len(rows(stable)) == 3 and len(observed(stable)) == 3, 'one producer per track partition')
    f.wait_for(lambda: f.committed(GROUP, f.EVENTS[(stable, 'audio.raw')][-1][1]),
               'bounded queue resumes and commits the short tail')

    # Fault one test-only track while the real peer continues.
    for p in PROCESSES:
        if p.poll() is None:
            p.terminate()
            p.wait(15)
    failure = TMP / 'failure'
    failed = worker('failed', TEST_FAILURE=str(failure))
    f.wait_for(lambda: len(members()) == 1, 'failure worker assigned', 90)
    failure.touch()
    isolated = f.new_session()
    with audio_socket(isolated, 'whisperx,test-shadow') as ws:
        send(ws, speech[:12 * 32000])
    f.wait_for(lambda: failed.poll() is not None, 'synthetic inference failure exits without committing')
    f.wait_for(lambda: len(rows(isolated)) == 2, 'real track succeeds during peer failure')
    assert {r['track_id'] for r in rows(isolated)} == {'whisperx'}
    failure.unlink()
    worker('recovered')
    f.wait_for(lambda: len(rows(isolated)) == 4, 'failed track replays after restart', 120)

    retry = f.new_session()
    function = 'lean_refinement_smoke_reject'
    f.DB.execute(f"CREATE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS "
                 "$$ BEGIN RAISE EXCEPTION 'Injected refinement DB fault'; END $$")
    try:
        f.DB.execute(f"CREATE TRIGGER {function} BEFORE INSERT ON session_transcripts "
                     f"FOR EACH ROW WHEN (NEW.session_id='{uuid.UUID(retry)}'::uuid) EXECUTE FUNCTION {function}()")
        raw(retry, 1)
        f.wait_for(lambda: observed(retry), 'DB fault receives a real refined event')
        time.sleep(2)
        assert not rows(retry)
        assert not f.committed('samuraipersistor-refined', observed(retry)[0][1])
    finally:
        f.DB.execute(f'DROP TRIGGER IF EXISTS {function} ON session_transcripts')
        f.DB.execute(f'DROP FUNCTION {function}()')
    f.wait_for(lambda: len(rows(retry)) == 1, 'database retry keeps the failed offset')
    forged = f.pb.RefinedEvent(session_id=retry, tenant_id=str(uuid.uuid4()), track_id='forged',
                              start_s=0, end_s=1, window_sec=10, text='must not persist')
    f.PRODUCER.produce('transcripts.refined', key=retry.encode(), value=forged.SerializeToString())
    assert f.PRODUCER.flush(10) == 0
    f.wait_for(lambda: any(ev.track_id == 'forged' for ev, _ in observed(retry)), 'foreign tenant event observed')
    f.wait_for(lambda: f.committed('samuraipersistor-refined', observed(retry)[-1][1]), 'tenant denial consumed')
    assert len(rows(retry)) == 1
    normal_session(speech)
    print('REFINEMENT TRACKS COMPOSE SMOKE PASSED', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        for log in TMP.glob('*.log'):
            print(log.name, '\n'.join(log.read_text().splitlines()[-8:]), flush=True)
        raise
    finally:
        for process in PROCESSES:
            if process.poll() is None:
                process.kill()
            process.wait(15)
        f.CONSUMER.close()
        f.DB.close()
