"""Qualify the isolated final-track Compose spike using a consented local WAV.

Run from the repository root. Reports identities and timings, never audio/text.
The optional database fault stops only this Compose project's postgres service.
"""

import argparse
import base64
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
import wave

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
            "(SELECT count(*) FROM session_transcripts WHERE session_id=%s AND track_id IS NOT NULL),"
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


def stored(session_id):
    from psycopg.rows import dict_row
    with psycopg.connect(DB, row_factory=dict_row) as conn:
        return conn.execute("SELECT result_id,track_id,profile_id,status,is_primary,full_text,segments,"
                            "recording_id,event_created_at_ns FROM session_transcripts "
                            "WHERE session_id=%s ORDER BY track_id", (session_id,)).fetchall()


def crash_after_acceptance(message, after_publish):
    """Use the real Persistor code in a one-shot process; the input stays uncommitted."""
    program = """
(require '[jsonista.core :as json] '[next.jdbc :as jdbc]
         '[samuraipersistor.final-track-consumer :as consumer]
         '[samuraipersistor.kafka.common :as kafka])
(import '(java.util Base64) '(org.apache.kafka.clients.consumer ConsumerRecord))
(let [input (json/read-value (slurp *in*) (json/object-mapper {:decode-key-fn keyword}))
      value (.decode (Base64/getDecoder) (:value input))
      key (.getBytes (:key input) "UTF-8")
      record (ConsumerRecord. "transcripts.final-tracks" 0 0 key value)
      config {:bootstrap-servers "broker:29092" :final-source-bucket "recordings"
              :topics {:final "transcripts.final"}}
      ds (jdbc/get-datasource {:jdbcUrl "jdbc:postgresql://postgres:5432/nanosamurai"
                              :user "nanosamurai" :password "nanosamurai"})
      producer (kafka/->producer config)
      publish consumer/publish-primary!]
  (with-redefs [consumer/publish-primary!
                (fn [& args]
                  (when (:after-publish input) (apply publish args))
                  (System/exit 17))]
    (consumer/persist-record! ds config false record producer)))
"""
    data = json.dumps({"value": base64.b64encode(message.value()).decode(),
                       "key": message.key().decode(), "after-publish": after_publish}).encode()
    result = subprocess.run(["docker", "compose", "-f", "docker-compose.final-tracks.yml",
                             "run", "--rm", "--no-deps", "-T", "--entrypoint", "java",
                             "samuraipersistor", "-cp", "/app/samuraipersistor.jar",
                             "clojure.main", "-e", program], input=data,
                            cwd=Path(__file__).resolve().parents[1],
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert result.returncode == 17, "Fault process did not reach the post-commit boundary"


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
                         "enable.auto.commit": False, "auto.offset.reset": "earliest",
                         "max.partition.fetch.bytes": 1048576})
    consumer.subscribe(list(TOPICS))
    producer = Producer({"bootstrap.servers": BROKER, "enable.idempotence": True, "message.max.bytes": 1048576})
    s3 = boto3.client("s3", endpoint_url="http://127.0.0.1:14566", region_name="us-east-1",
                      aws_access_key_id="test", aws_secret_access_key="test")
    sessions, records = [], {topic: [] for topic in TOPICS}

    def collect():
        message = consumer.poll(0.2)
        if message is not None:
            assert not message.error(), str(message.error())
            event = TOPICS[message.topic()].FromString(message.value())
            if event.session_id in sessions:
                records[message.topic()].append((event, message))

    def wait_for(topic, count):
        def ready():
            collect()
            return len(records[topic]) >= count
        eventually(ready, 600)

    def new_session(audio):
        session_id = create_session()
        sessions.append(session_id)
        stream(session_id, audio)
        return session_id

    def replay_sources():
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
        speech = new_session(pcm)
        silence = new_session(bytes(3 * 32000))
        wait_for("transcripts.final-tracks", 6)
        wait_for("transcripts.final", 2)
        eventually(lambda: all(counts(s) == (1, 3, 3) for s in sessions))
        snapshots = {s: stored(s) for s in sessions}
        for session_id in sessions:
            events = [e for e, _ in records["transcripts.final-tracks"] if e.session_id == session_id]
            assert {e.track_id: e.status for e in events} == {
                "whisperx": "succeeded", "shadow": "succeeded", "failure": "failed"}
            assert all(e.schema_version == 2 for e in events)
            assert len({row["recording_id"] for row in snapshots[session_id]}) == 1
            for event in events:
                row = next(row for row in snapshots[session_id] if str(row["result_id"]) == event.result_id)
                assert row["full_text"] == event.full_text and row["status"] == event.status
                assert row["is_primary"] == (event.track_id == "whisperx")
            primary = next(e for e in events if e.track_id == "whisperx")
            legacy = next(e for e, _ in records["transcripts.final"] if e.session_id == session_id)
            assert primary.full_text == legacy.full_text and primary.segments == legacy.segments
            if session_id == silence:
                assert not primary.full_text and not primary.segments
            else:
                assert primary.full_text and primary.word_timestamps
                assert primary.speaker_labels == any(segment.speaker for segment in primary.segments)
                if not primary.speaker_labels:
                    assert "diarization_unavailable_or_unassigned" in primary.degradations
            response = requests.get(BASE + f"/api/recordings/{session_id}/audio",
                                    headers={"Range": "bytes=0-43"}, timeout=15)
            assert response.status_code == 206 and response.content[:4] == b"RIFF"
        replay_sources()
        wait_for("transcripts.final-tracks", 12)
        wait_for("transcripts.final", 4)
        assert all(stored(s) == snapshots[s] for s in sessions)
        if args.database_fault:
            time.sleep(2)
            compose("restart", "whisperx")
            before = offsets()
            compose("stop", "postgres")
            try:
                replay_sources()
                wait_for("transcripts.final-tracks", 18)
                time.sleep(3)
                assert offsets() == before, "Database outage advanced canonical offsets"
            finally:
                compose("start", "postgres")
            eventually(lambda: offsets() != before, 120)
            wait_for("transcripts.final", 6)
            assert all(stored(s) == snapshots[s] for s in sessions)
        if args.process_exit_fault:
            for after_publish in (False, True):
                compose("stop", "samuraipersistor")
                before = offsets()
                count = len(records["transcripts.final-tracks"])
                try:
                    session_id = new_session(pcm)
                    wait_for("transcripts.final-tracks", count + 3)
                    event, message = next((e, m) for e, m in records["transcripts.final-tracks"]
                                          if e.session_id == session_id and e.track_id == "whisperx")
                    crash_after_acceptance(message, after_publish)
                    assert offsets() == before
                    accepted = stored(session_id)
                    assert len(accepted) == 1 and accepted[0]["full_text"] == event.full_text
                finally:
                    compose("start", "samuraipersistor")
                eventually(lambda: counts(session_id) == (1, 3, 3), 120)
                assert next(r for r in stored(session_id) if r["is_primary"]) == accepted[0]
        objects = [obj["Key"] for page in s3.get_paginator("list_objects_v2").paginate(Bucket="recordings")
                   for obj in page.get("Contents", [])]
        assert objects and all(key.startswith("recordings/") and key.endswith(".wav") for key in objects)
        compose("pause", "localstack")
        try:
            for session_id in sessions:
                response = requests.get(BASE + f"/api/recordings/{session_id}", timeout=15)
                response.raise_for_status()
                final = response.json()["transcripts"]["final"]
                assert len(final) == 1
                assert final[0]["full_text"] == next(r["full_text"] for r in stored(session_id) if r["is_primary"])
        finally:
            compose("unpause", "localstack")
        report = {"passed": True, "sessions": sessions, "rows_per_session": [1, 3, 3],
                  "speech_and_silence": True, "stable_accepted_replay": True,
                  "no_transcript_objects": True, "postgres_reads_without_s3": True,
                  "primary_recording_playback": True, "retention_rejection": True,
                  "database_retry": args.database_fault,
                  "worker_restart_replay": args.database_fault,
                  "real_speaker_labels": next(e.speaker_labels for e, _ in records["transcripts.final-tracks"]
                                                if e.session_id == speech and e.track_id == "whisperx"),
                  "post_commit_and_post_publication_crash_recovery": args.process_exit_fault}
        if args.report:
            args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report), flush=True)
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
