"""Qualify the isolated final-track Compose spike using a consented local WAV.

Run from the repository root. Reports identities and timings, never audio/text.
The optional database fault stops only this Compose project's postgres service.
"""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
import wave
import zlib

import boto3
from confluent_kafka import Consumer, Producer, TopicPartition
import psycopg
import requests
import websocket

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from proto_gen import stream_pb2 as pb

BROKER = "127.0.0.1:19094"
BASE = "http://127.0.0.1:18000"
DB = "postgresql://nanosamurai:nanosamurai@127.0.0.1:15434/nanosamurai"
TOPICS = {"recordings.finished": pb.RecordingFinished,
          "transcripts.final-tracks": pb.FinalTrackResult,
          "transcripts.final": pb.SessionTranscript}


def eventually(check, seconds=60):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.2)
    raise AssertionError("Timed out waiting for qualification condition")


def create_session():
    response = requests.post(BASE + "/api/sessions", json={}, timeout=10)
    response.raise_for_status()
    return response.json()["session_id"]


def audio_url(session_id, retain=True):
    return (BASE.replace("http:", "ws:") + "/ws/audio?session_id=" + session_id
            + "&lang=cs&sample_rate=16000&realtime=false&refined=false&final=true"
            + "&store_recording=" + str(retain).lower())


def stream(session_id, pcm):
    ws = websocket.create_connection(audio_url(session_id), timeout=20)
    try:
        for index in range(0, len(pcm), 640):
            ws.send_binary(pcm[index:index + 640])
            time.sleep(0.002)
    finally:
        ws.close()


def counts(session_id):
    with psycopg.connect(DB, connect_timeout=5) as conn:
        return tuple(conn.execute(
            "SELECT (SELECT count(*) FROM recordings WHERE session_id=%s),"
            "(SELECT count(*) FROM transcript_track_results WHERE session_id=%s),"
            "(SELECT count(*) FROM session_transcripts WHERE session_id=%s)",
            (session_id,) * 3).fetchone())


def offsets():
    client = Consumer({"bootstrap.servers": BROKER,
                       "group.id": "samuraipersistor-final-tracks",
                       "enable.auto.commit": False})
    try:
        return [p.offset for p in client.committed(
            [TopicPartition("transcripts.final-tracks", n) for n in range(2)], timeout=10)]
    finally:
        client.close()


def compose(*args):
    subprocess.run(["docker", "compose", "-f", "docker-compose.final-tracks.yml", *args],
                   cwd=Path(__file__).resolve().parents[1], check=True,
                   stdout=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wav", type=Path, required=True)
    parser.add_argument("--database-fault", action="store_true")
    parser.add_argument("--process-exit-fault", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    with wave.open(str(args.wav), "rb") as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 16000)
        assert 0 < wav.getnframes() <= 600 * 16000
        pcm = wav.readframes(wav.getnframes())
    consumer = Consumer({"bootstrap.servers": BROKER, "group.id": "final-track-audit." + str(uuid.uuid4()),
                         "enable.auto.commit": False, "auto.offset.reset": "earliest"})
    consumer.subscribe(list(TOPICS))
    producer = Producer({"bootstrap.servers": BROKER, "enable.idempotence": True})
    s3 = boto3.client("s3", endpoint_url="http://127.0.0.1:14566", region_name="us-east-1",
                      aws_access_key_id="test", aws_secret_access_key="test")
    sessions = []
    records = {topic: [] for topic in TOPICS}

    def collect():
        message = consumer.poll(0.2)
        if message is not None:
            assert not message.error(), str(message.error())
            event = TOPICS[message.topic()].FromString(message.value())
            if event.session_id in sessions:
                records[message.topic()].append((event, message))

    def wait_for_results(count):
        def ready():
            collect()
            return (len(records["transcripts.final-tracks"]) >= count * 3
                    and len(records["transcripts.final"]) >= count)
        eventually(ready, 600)

    def replay():
        for _, message in records["recordings.finished"][:2]:
            producer.produce("recordings.finished", key=message.key(), value=message.value(),
                             headers=message.headers(), partition=message.partition())
        assert producer.flush(30) == 0

    try:
        rejected_session = create_session()
        try:
            rejected = websocket.create_connection(audio_url(rejected_session, retain=False), timeout=10)
        except websocket.WebSocketBadStatusException as error:
            assert error.status_code == 400
        else:
            rejected.close()
            raise AssertionError("No-retention plan was accepted")
        first = create_session()
        sessions.append(first)
        for _ in range(40):
            other = create_session()
            if zlib.crc32(first.encode()) % 2 != zlib.crc32(other.encode()) % 2:
                sessions.append(other)
                break
        assert len(sessions) == 2
        for session_id in sessions:
            stream(session_id, pcm)
        wait_for_results(2)
        assert {m.partition() for _, m in records["recordings.finished"]} == {0, 1}
        summaries = []
        shadow_instances = set()
        for session_id in sessions:
            events = [e for e, _ in records["transcripts.final-tracks"] if e.session_id == session_id]
            assert len(events) == 3
            assert {e.track_id: e.status for e in events} == {
                "whisperx": "succeeded", "shadow": "succeeded", "failure": "failed"}
            assert len({e.source.artifact_id for e in events}) == 1
            for event in events:
                provenance = json.loads(event.provenance_json)
                if event.track_id == "whisperx":
                    assert event.primary and event.word_timestamps and event.speaker_labels
                    assert not event.degradations
                else:
                    assert not event.primary
                if event.track_id == "shadow":
                    shadow_instances.add(provenance["worker_instance"])
                if event.status == "succeeded":
                    key = event.result_uri.removeprefix("s3://recordings/")
                    body = s3.get_object(Bucket="recordings", Key=key)["Body"]
                    try:
                        data = body.read(1000001)
                    finally:
                        body.close()
                    assert hashlib.sha256(data).hexdigest() == event.result_sha256
                    assert json.loads(data)["provenance"] == provenance
                summaries.append({"session_id": session_id, "track_id": event.track_id,
                                  "result_id": event.result_id, "status": event.status,
                                  "provenance": provenance})
        assert len(shadow_instances) == 2, "Two source partitions must reach two shadow replicas"
        eventually(lambda: all(counts(s) == (1, 3, 1) for s in sessions))
        for session_id in sessions:
            response = requests.get(BASE + f"/api/recordings/{session_id}/audio",
                                    headers={"Range": "bytes=0-43"}, timeout=15)
            assert response.status_code == 206 and response.content[:4] == b"RIFF"
        accepted = {e.result_id: m.value() for e, m in records["transcripts.final-tracks"]}
        replay()
        wait_for_results(4)
        assert all(accepted[e.result_id] == m.value() for e, m in records["transcripts.final-tracks"])
        eventually(lambda: all(counts(s) == (1, 3, 1) for s in sessions))
        if args.database_fault:
            time.sleep(2)
            before = offsets()
            compose("stop", "postgres")
            try:
                replay()
                wait_for_results(6)
                time.sleep(3)
                assert offsets() == before, "Database outage advanced canonical offsets"
            finally:
                compose("start", "postgres")
            eventually(lambda: all(a > b for a, b in zip(offsets(), before)), 120)
            assert all(counts(s) == (1, 3, 1) for s in sessions)
        if args.process_exit_fault:
            compose("stop", "shadow")
            try:
                crash_session = create_session()
                sessions.append(crash_session)
                stream(crash_session, pcm)

                def source_ready():
                    collect()
                    return any(e.session_id == crash_session for e, _ in records["recordings.finished"])

                eventually(source_ready, 60)
                _, message = next(pair for pair in records["recordings.finished"]
                                  if pair[0].session_id == crash_session)
                payload = json.dumps({"value": base64.b64encode(message.value()).decode(),
                                      "headers": [(k, base64.b64encode(v).decode())
                                                  for k, v in message.headers()]}).encode()
                script = """
import base64, hashlib, json, os, sys
from proto_gen import stream_pb2 as pb
from drsynth_common.final_track_artifacts import S3Artifacts
from finalizer_worker.track_processing import process_recording
from finalizer_worker.test_track import TestTrack
data = json.load(sys.stdin)
event = pb.RecordingFinished.FromString(base64.b64decode(data['value']))
headers = [(k, base64.b64decode(v)) for k, v in data['headers']]
accepted = process_recording(event, headers, track_id='shadow', profile_id='test-final-r1',
                             provider=TestTrack(), store=S3Artifacts.from_env())
print(hashlib.sha256(accepted[1]).hexdigest(), flush=True)
os._exit(17)
"""
                crash = subprocess.run(
                    ["docker", "compose", "-f", "docker-compose.final-tracks.yml", "run", "--rm",
                     "--no-deps", "-T", "shadow", "python", "-c", script], input=payload,
                    cwd=Path(__file__).resolve().parents[1], stdout=subprocess.PIPE, check=False)
                assert crash.returncode == 17, "Expected exit immediately after durable manifest creation"
                accepted_digest = crash.stdout.decode().strip()
                assert len(accepted_digest) == 64
            finally:
                compose("start", "shadow")

            def crash_recovered():
                collect()
                return any(e.session_id == crash_session and e.track_id == "shadow"
                           for e, _ in records["transcripts.final-tracks"])

            eventually(crash_recovered, 120)
            recovered = next(m for e, m in records["transcripts.final-tracks"]
                             if e.session_id == crash_session and e.track_id == "shadow")
            assert hashlib.sha256(recovered.value()).hexdigest() == accepted_digest
            eventually(lambda: counts(crash_session) == (1, 3, 1), 120)
        report = {"passed": True, "source_partitions": [0, 1], "shadow_replicas_observed": 2,
                  "rows_per_session": {"recordings": 1, "track_results": 3, "primary_transcripts": 1},
                  "immutable_replay": True, "retention_rejection": True,
                  "primary_recording_playback": True,
                  "database_retry": args.database_fault,
                  "manifest_process_exit_recovery": args.process_exit_fault, "results": summaries}
        if args.report:
            args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if k != "results"}), flush=True)
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
