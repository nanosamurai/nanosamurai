"""Local Compose integration smoke. Prints assertions, never transcript content."""
import io
import json
import os
import time
import uuid
import wave
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import boto3
import psycopg
from confluent_kafka import Consumer, Producer, ConsumerGroupTopicPartitions
from confluent_kafka.admin import AdminClient
from psycopg.rows import dict_row
from websockets.sync.client import connect
from websockets.exceptions import InvalidStatus

from proto_gen import stream_pb2 as pb

BFF = os.getenv("BFF_URL", "http://samuraibff:8000")
BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "broker:29092")
TENANT = "00000000-0000-0000-0000-000000000000"
PERSISTOR_GROUP = os.getenv("PERSISTOR_GROUP", "samuraipersistor-final")
DB = psycopg.connect("", autocommit=True, row_factory=dict_row)
PRODUCER = Producer({"bootstrap.servers": BOOTSTRAP})
CONSUMER = Consumer({"bootstrap.servers": BOOTSTRAP, "group.id": f"lean-smoke-{uuid.uuid4()}",
                     "enable.auto.commit": False, "auto.offset.reset": "latest"})
ADMIN = AdminClient({"bootstrap.servers": BOOTSTRAP})
S3 = boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT"], region_name="us-east-1",
                  aws_access_key_id="test", aws_secret_access_key="test")
EVENTS = {}
TOPICS = {"audio.raw": pb.AudioChunk, "recordings.finished": pb.RecordingFinished,
          "transcripts.final": pb.SessionTranscript, "sessions.meta": None}


def http(path, data=None, headers=None):
    """Return HTTP status/body/headers; leave expected denials available to assertions."""
    req = Request(BFF + path, data=json.dumps(data).encode() if data is not None else None,
                  headers={"Content-Type": "application/json", **(headers or {})})
    try:
        response = urlopen(req, timeout=15)
    except HTTPError as error:
        response = error
    with response:
        body = response.read()
        if "application/json" in response.headers.get("Content-Type", ""):
            body = json.loads(body)
        return response.status, body, response.headers


def pump():
    """Capture Kafka messages for assertions while waiting for asynchronous work."""
    msg = CONSUMER.poll(0.25)
    if msg is None:
        return
    assert not msg.error(), msg.error()
    if msg.topic() == "sessions.meta":
        value = json.loads(msg.value())
        session = value["session_id"]
    else:
        value = TOPICS[msg.topic()].FromString(msg.value())
        session = value.session_id
    EVENTS.setdefault((session, msg.topic()), []).append((value, msg))


def wait_for(check, label, timeout=300):
    """Poll Kafka and the real stack until an assertion is ready, with a hard deadline."""
    until = time.monotonic() + timeout
    while time.monotonic() < until:
        pump()
        try:
            value = check()
        except URLError:
            value = False
        if value:
            print("PASS", label, flush=True)
            return value
    raise AssertionError("Timed out: " + label)


def rows(session):
    """Read only this smoke session's final rows."""
    return DB.execute("SELECT track_id,model,full_text,segments,recording_id FROM session_transcripts "
                      "WHERE session_id=%s AND type='final' ORDER BY track_id", (session,)).fetchall()


def new_session():
    status, body, _ = http("/api/sessions", {})
    assert status in (200, 201), (status, body)
    return body["session_id"]


def stream(session, pcm, tracks=None, retained=True):
    params = {"session_id": session, "sample_rate": 16000, "lang": "cs", "realtime": "false",
              "refined": "false", "final": "true", "store_recording": str(retained).lower()}
    if tracks is not None:
        params["final_tracks"] = tracks
    with connect(BFF.replace("http", "ws", 1) + "/ws/audio?" + urlencode(params), open_timeout=15) as ws:
        for start in range(0, len(pcm), 6400):
            ws.send(pcm[start:start + 6400])
            time.sleep(0.02)


def replay(msg, value=None):
    PRODUCER.produce(msg.topic(), key=msg.key(), value=value or msg.value(), headers=msg.headers())
    assert PRODUCER.flush(15) == 0


def committed(group, msg):
    result = ADMIN.list_consumer_group_offsets([ConsumerGroupTopicPartitions(group)])[group].result(10)
    return any(p.topic == msg.topic() and p.partition == msg.partition() and p.offset > msg.offset()
               for p in result.topic_partitions)


def main():
    CONSUMER.subscribe(list(TOPICS))
    wait_for(lambda: {p.topic for p in CONSUMER.assignment()} == set(TOPICS), "Kafka observation ready", 30)
    wait_for(lambda: http("/health")[0] == 200, "BFF HTTP ready", 60)
    with wave.open("/probe/test_cs.wav", "rb") as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (16000, 1, 2)
        speech = wav.readframes(12 * 16000)

    session = new_session()
    for tracks, retained in [("whisperx,test-shadow", False), ("unknown", True), ("", True)]:
        try:
            stream(session, speech, tracks, retained)
            raise AssertionError("Invalid controls were accepted")
        except InvalidStatus as error:
            assert error.response.status_code == 400
    assert DB.execute("SELECT started_at FROM sessions WHERE id=%s", (session,)).fetchone()["started_at"] is None
    print("PASS invalid selections and non-retained multi-track rejected before audio")

    stream(session, speech, "test-shadow,whisperx")
    wait_for(lambda: len(rows(session)) == 2, "two independent final rows")
    saved = rows(session)
    assert len({r["recording_id"] for r in saved}) == 1
    assert DB.execute("SELECT count(*) AS n FROM recordings WHERE session_id=%s", (session,)).fetchone()["n"] == 1
    real = next(r for r in saved if r["track_id"] == "whisperx")
    assert real["full_text"].strip() and real["segments"] and real["model"] == "medium"
    assert next(r for r in saved if r["track_id"] == "test-shadow")["model"] == "synthetic-test-only"
    wait_for(lambda: EVENTS.get((session, "recordings.finished")), "recording completion observed")
    rf, finished = EVENTS[(session, "recordings.finished")][-1]
    assert finished.key() == session.encode()
    assert dict(finished.headers())["x-final-tracks"] == b"test-shadow,whisperx"
    assert "traceparent" in dict(finished.headers())
    wait_for(lambda: any(v.get("stream_controls", {}).get("final_tracks") == ["test-shadow", "whisperx"]
                         for v, _ in EVENTS.get((session, "sessions.meta"), [])), "selection copied to sessions.meta")
    wait_for(lambda: committed("finalizer.test-unselected", finished), "unselected worker committed skip")
    assert all(r["track_id"] != "test-unselected" for r in saved)
    status, detail, _ = http(f"/api/recordings/{session}")
    assert status == 200 and len(detail["transcripts"]["final"]) == 2
    for row in saved:
        status, filtered, _ = http(f"/api/recordings/{session}?track_id={row['track_id']}")
        result = filtered["transcripts"]["final"]
        assert status == 200 and len(result) == 1
        assert (result[0]["full_text"], result[0]["segments"]) == (row["full_text"], row["segments"])
    status, audio, _ = http(f"/api/recordings/{session}/audio")
    assert status == 200 and audio[:4] == b"RIFF"
    with wave.open(io.BytesIO(audio), "rb") as wav:
        assert wav.readframes(wav.getnframes()) == speech
    assert http(f"/api/recordings/{session}/audio", headers={"Range": "bytes=0-43"})[0] == 206
    print("PASS BFF track text/segments and shared audio/range playback")

    wait_for(lambda: len(EVENTS.get((session, "transcripts.final"), [])) >= 2, "final events observed")
    for event, msg in list(EVENTS[(session, "transcripts.final")]):
        event.full_text = "Replay must not overwrite the first result"
        replay(msg, event.SerializeToString())
    replay(finished)
    wait_for(lambda: len(EVENTS.get((session, "transcripts.final"), [])) >= 6, "input/output replays delivered")
    last_output = EVENTS[(session, "transcripts.final")][-1][1]
    wait_for(lambda: committed(PERSISTOR_GROUP, last_output), "Persistor consumed replays")
    assert rows(session) == saved
    print("PASS replay idempotency and first-result preservation")

    # Reconnect with a different valid selection; the stored snapshot is authoritative.
    stream(session, b"", "whisperx")
    status, detail, _ = http(f"/api/recordings/{session}")
    assert detail["session"]["stream_controls"]["final_tracks"] == ["test-shadow", "whisperx"]
    print("PASS reconnect preserves the original ordered selection")

    silence = new_session()
    stream(silence, bytes(32000), "whisperx,test-shadow")
    wait_for(lambda: len(rows(silence)) == 2, "silence yields both terminal rows")
    assert all(not r["full_text"].strip() and not r["segments"] for r in rows(silence))

    default = new_session()
    stream(default, speech)
    wait_for(lambda: len(rows(default)) == 1, "omitted selection uses WhisperX")
    assert rows(default)[0]["track_id"] == "whisperx"

    # Only the synthetic worker fails. Its production loop exits without committing.
    failed = new_session()
    Path("/faults/fail").write_text("test-only")
    try:
        stream(failed, speech, "whisperx,test-shadow")
        wait_for(lambda: any(r["track_id"] == "whisperx" for r in rows(failed)), "real track survives peer failure")
        assert len(rows(failed)) == 1
    finally:
        Path("/faults/fail").unlink(missing_ok=True)
    wait_for(lambda: len(rows(failed)) == 2, "worker restart replays the unfinished input")

    unavailable = new_session()
    source_key = f"{TENANT}/{unavailable}/temporarily-unavailable.wav"
    source_event = pb.RecordingFinished(session_id=unavailable, tenant_id=TENANT,
                                       recording_url=f"s3://{os.environ['RECORDINGS_BUCKET']}/{source_key}",
                                       sample_rate=16000, duration_s=len(speech) / 32000, lang="cs")
    PRODUCER.produce("recordings.finished", key=unavailable.encode(),
                     value=source_event.SerializeToString(), headers=[("x-final-tracks", b"test-shadow")])
    assert PRODUCER.flush(15) == 0
    wait_for(lambda: EVENTS.get((unavailable, "recordings.finished")), "unavailable source event observed")
    for _ in range(20):
        pump()
    assert not rows(unavailable)
    assert not committed("finalizer.test-shadow", EVENTS[(unavailable, "recordings.finished")][-1][1])
    S3.put_object(Bucket=os.environ["RECORDINGS_BUCKET"], Key=source_key, Body=audio, ContentType="audio/wav")
    wait_for(lambda: len(rows(unavailable)) == 1, "source download failure replays after recovery")

    retry = new_session()
    DB.execute("CREATE FUNCTION lean_smoke_reject_final() RETURNS trigger LANGUAGE plpgsql AS "
               "$$ BEGIN RAISE EXCEPTION 'Injected smoke DB failure'; END $$")
    DB.execute("CREATE TRIGGER lean_smoke_reject_final BEFORE INSERT ON session_transcripts "
               f"FOR EACH ROW WHEN (NEW.session_id='{uuid.UUID(retry)}'::uuid) "
               "EXECUTE FUNCTION lean_smoke_reject_final()")
    try:
        stream(retry, speech, "test-shadow")
        wait_for(lambda: EVENTS.get((retry, "transcripts.final")), "final delivered during DB fault")
        for _ in range(16):
            pump()
        assert not rows(retry)
        assert not committed(PERSISTOR_GROUP, EVENTS[(retry, "transcripts.final")][-1][1])
    finally:
        DB.execute("DROP TRIGGER lean_smoke_reject_final ON session_transcripts")
        DB.execute("DROP FUNCTION lean_smoke_reject_final()")
    wait_for(lambda: len(rows(retry)) == 1, "database retry stores the same event without restart")

    foreign = uuid.uuid4()
    foreign_session = uuid.uuid4()
    DB.execute("INSERT INTO tenants(id,name) VALUES (%s,'Lean smoke foreign tenant')", (foreign,))
    DB.execute("INSERT INTO sessions(id,tenant_id,session_key) VALUES (%s,%s,%s)",
               (foreign_session, foreign, str(foreign_session)))
    assert http(f"/api/recordings/{foreign_session}")[0] == 404
    assert http(f"/api/recordings/{foreign_session}/audio")[0] == 404
    try:
        stream(str(foreign_session), speech, "test-shadow")
        raise AssertionError("Foreign session accepted audio")
    except InvalidStatus as error:
        assert error.response.status_code == 403
    print("PASS tenant denial for history, playback and audio input")

    ephemeral = new_session()
    stream(ephemeral, speech, "test-shadow", retained=False)
    wait_for(lambda: len(rows(ephemeral)) == 1, "single non-retained track finishes")
    wait_for(lambda: EVENTS.get((ephemeral, "recordings.finished")), "ephemeral recording observed")
    ephemeral_rf = EVENTS[(ephemeral, "recordings.finished")][-1][0]
    bucket, key = ephemeral_rf.recording_url.removeprefix("s3://").split("/", 1)

    def deleted():
        try:
            S3.head_object(Bucket=bucket, Key=key)
            return False
        except S3.exceptions.ClientError as error:
            assert error.response["ResponseMetadata"]["HTTPStatusCode"] == 404
            return True

    wait_for(deleted, "single-track source deletion preserved")
    bucket, key = rf.recording_url.removeprefix("s3://").split("/", 1)
    assert S3.head_object(Bucket=bucket, Key=key)["ContentLength"] > len(speech)
    assert not any(obj["Key"].endswith(".json") for obj in
                   S3.list_objects_v2(Bucket=bucket, Prefix=key.rsplit("/", 1)[0]).get("Contents", []))
    print("PASS multi-track source retained; no transcript sidecar")
    local_session = new_session()
    local_wav = Path(f"/faults/{local_session}.wav")
    with wave.open(str(local_wav), "wb") as wav:
        wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        wav.writeframes(speech)
    try:
        local_event = pb.RecordingFinished(session_id=local_session, tenant_id=TENANT,
                                          recording_url=f"file://{local_wav}", sample_rate=16000,
                                          duration_s=len(speech) / 32000, lang="cs")
        PRODUCER.produce("recordings.finished", key=local_session.encode(),
                         value=local_event.SerializeToString(), headers=[("x-final-tracks", b"test-shadow")])
        assert PRODUCER.flush(15) == 0
        wait_for(lambda: len(rows(local_session)) == 1, "local WAV finalization completes")
        assert local_wav.exists() and not local_wav.with_suffix(".json").exists()
        print("PASS no local transcript JSON sidecar")
    finally:
        local_wav.unlink(missing_ok=True)
    print("FINAL TRACKS COMPOSE SMOKE PASSED")


if __name__ == "__main__":
    try:
        main()
    finally:
        CONSUMER.close()
        DB.close()
