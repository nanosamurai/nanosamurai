"""Exercise real refinement tracks in the regular loopback-only Compose stack.

Uses a consented mono PCM16/16kHz speech fixture. Reports metadata, never text.
Replays only source windows created by this invocation. Optional recovery check
restarts only the regular local stack's refinement window producer.
"""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import threading
import time
from urllib.parse import urlparse
import uuid
import wave

import boto3
from confluent_kafka import Consumer, Producer
import psycopg
import requests
import websocket

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from proto_gen import stream_pb2 as pb


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wav", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--database", default="postgresql://nanosamurai:nanosamurai@127.0.0.1:5432/nanosamurai")
    parser.add_argument("--test-tracks", action="store_true")
    parser.add_argument("--restart-window-producer", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    assert all(urlparse(url).hostname in ("127.0.0.1", "localhost") for url in (args.base_url, args.database))
    with wave.open(str(args.wav), "rb") as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 16000)
        assert 11 * 16000 < wav.getnframes() <= 600 * 16000
        pcm = wav.readframes(wav.getnframes())
    response = requests.post(args.base_url + "/api/sessions", json={}, timeout=10)
    response.raise_for_status()
    session = response.json()["session_id"]
    topics = {"audio.refinement-windows": pb.RefinementWindow,
              "transcripts.refined-tracks": pb.FinalTrackResult,
              "transcripts.refined": pb.RefinedEvent,
              "transcripts.final-tracks": pb.FinalTrackResult}
    consumer = Consumer({"bootstrap.servers": "127.0.0.1:9092", "group.id": "refinement-smoke." + str(uuid.uuid4()),
                         "enable.auto.commit": False, "auto.offset.reset": "earliest"})
    consumer.subscribe(list(topics))
    records = {topic: [] for topic in topics}
    events, stop = [], threading.Event()
    wsbase = args.base_url.replace("http:", "ws:")
    event_ws = websocket.create_connection(wsbase + "/ws/events?session_id=" + session, timeout=1)

    def receive_events():
        while not stop.is_set():
            try:
                raw = event_ws.recv()
                if not raw:
                    return
                event = json.loads(raw)
                if event.get("type") == "refined":
                    events.append(event)
            except websocket.WebSocketTimeoutException:
                pass
            except websocket.WebSocketConnectionClosedException:
                return

    thread = threading.Thread(target=receive_events, daemon=True)
    thread.start()

    def collect():
        message = consumer.poll(0.2)
        if message is not None:
            assert not message.error(), "Kafka audit failed"
            event = topics[message.topic()].FromString(message.value())
            owner = event.recording.session_id if message.topic() == "audio.refinement-windows" else event.session_id
            if owner == session:
                records[message.topic()].append((event, message))

    def wait_until(check, timeout=180):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            collect()
            if check():
                return
        raise AssertionError("Refinement qualification timed out: " + str({k: len(v) for k, v in records.items()}))

    def outcome_ids():
        return {e.result_id for e, _ in records["transcripts.refined-tracks"]}

    def counts():
        with psycopg.connect(args.database, connect_timeout=5) as conn:
            return tuple(conn.execute(
                "SELECT (SELECT count(*) FROM transcript_track_results WHERE session_id=%s AND stage='refined'),"
                "(SELECT count(*) FROM session_transcripts WHERE session_id=%s AND type='refined'),"
                "(SELECT count(*) FROM recordings WHERE session_id=%s)", (session,) * 3).fetchone())

    started = time.monotonic()
    audio = None
    try:
        audio = websocket.create_connection(
            wsbase + "/ws/audio?session_id=" + session
            + "&lang=cs&sample_rate=16000&realtime=false&refined=true&final=true"
              "&store_recording=true&refinement_window_sec=10", timeout=20)
        split = 11 * 32000
        for index in range(0, split, 6400):
            audio.send_binary(pcm[index:index + 6400])
            time.sleep(0.02)
        # A nonterminal real result must arrive with audio still open.
        wait_until(lambda: any(e.primary and e.status == "succeeded" for e, _ in records["transcripts.refined-tracks"]), 120)
        live_seconds = time.monotonic() - started
        if args.restart_window_producer:
            assert args.base_url == "http://127.0.0.1:8000", "Recovery check requires the regular local stack"
            container = "nanosamurai-refinement_windows-1"
            inspected = subprocess.run(["docker", "inspect", "--format", "{{json .Config.Labels}}", container],
                                       check=True, capture_output=True, text=True, timeout=15)
            labels = json.loads(inspected.stdout)
            assert labels["com.docker.compose.project"] == "nanosamurai"
            assert labels["com.docker.compose.service"] == "refinement_windows"
            subprocess.run(["docker", "restart", container], check=True, capture_output=True, timeout=30)
        for index in range(split, len(pcm), 6400):
            audio.send_binary(pcm[index:index + 6400])
            time.sleep(0.02)
        audio.close()
        audio = None
        windows_expected = (len(pcm) // 2 + 159999) // 160000
        tracks_expected = 3 if args.test_tracks else 1
        wait_until(lambda: len(outcome_ids()) == windows_expected * tracks_expected
                   and len(records["transcripts.refined"]) >= windows_expected
                   and len(records["transcripts.final-tracks"]) >= 1)
        wait_until(lambda: counts() == (windows_expected * tracks_expected, windows_expected, 1))
        assert events, "No primary refined WebSocket events"
        outcomes = {e.result_id: e for e, _ in records["transcripts.refined-tracks"]}
        unique_windows = {e.recording.source.artifact_id: (e, m.value())
                          for e, m in records["audio.refinement-windows"]}
        assert all(unique_windows[e.recording.source.artifact_id][1] == m.value()
                   for e, m in records["audio.refinement-windows"])
        windows = sorted((e for e, _ in unique_windows.values()), key=lambda e: e.start_sample)
        assert len(windows) == windows_expected
        if args.restart_window_producer:
            assert len(records["audio.refinement-windows"]) > windows_expected, "Open source was not replayed"
        assert windows[0].start_sample == 0 and windows[-1].end_sample == len(pcm) // 2
        assert windows[-1].flush_reason == "eof"
        assert all(a.end_sample == b.start_sample for a, b in zip(windows, windows[1:]))
        primary = [e for e in outcomes.values() if e.primary]
        assert all(e.status == "succeeded" for e in primary)
        assert any(e.word_timestamps and e.speaker_labels for e in primary)
        assert all(e.source == e.refinement_window.recording.source for e in outcomes.values())
        response = requests.get(args.base_url + f"/api/recordings/{session}/audio",
                                headers={"Range": "bytes=0-43"}, timeout=15)
        assert response.status_code == 206 and response.content[:4] == b"RIFF"
        response = requests.get(args.base_url + f"/api/recordings/{session}", timeout=15)
        response.raise_for_status()
        assert response.json()["transcripts"]["refined"], "No primary refinement in recordings API"
        if args.test_tracks:
            assert Counter(e.status for e in outcomes.values()) == {"succeeded": windows_expected * 2, "failed": windows_expected}
        assert len({e.run_id for e in outcomes.values()}) == tracks_expected
        for event, _ in records["transcripts.refined"]:
            assert all(event.start_s <= s.start_s <= s.end_s <= event.end_s + 0.01 for s in event.segments)

        s3 = boto3.client("s3", endpoint_url="http://127.0.0.1:4566", region_name="us-east-1",
                          aws_access_key_id="test", aws_secret_access_key="test")
        for event in primary:
            location = urlparse(event.result_uri)
            body = s3.get_object(Bucket=location.netloc, Key=location.path.lstrip("/"))["Body"]
            try:
                content = body.read(1000001)
            finally:
                body.close()
            assert hashlib.sha256(content).hexdigest() == event.result_sha256
            transcript = json.loads(content)
            assert transcript["full_text"]
        before = {e.result_id: m.value() for e, m in records["transcripts.refined-tracks"]}
        old_count = len(records["transcripts.refined-tracks"])
        producer = Producer({"bootstrap.servers": "127.0.0.1:9092", "enable.idempotence": True})
        for _, message in records["audio.refinement-windows"]:
            producer.produce(message.topic(), key=message.key(), value=message.value(),
                             headers=message.headers(), partition=message.partition())
        assert producer.flush(30) == 0
        wait_until(lambda: len(records["transcripts.refined-tracks"]) >= old_count * 2)
        assert all(before[e.result_id] == m.value() for e, m in records["transcripts.refined-tracks"])
        wait_until(lambda: counts() == (windows_expected * tracks_expected, windows_expected, 1))
        result = dict(session_id=session, windows=windows_expected, tracks=tracks_expected,
                      outcomes=len(outcomes), primary_rows=windows_expected, recordings=1,
                      live_result_seconds=round(live_seconds, 3), total_seconds=round(time.monotonic() - started, 3),
                      websocket_refined_events=len(events), exact_replay=True,
                      primary_api=True, range_playback=True,
                      window_producer_restart=args.restart_window_producer,
                      source_partition=records["audio.refinement-windows"][0][1].partition(),
                      worker_instances={e.track_id: json.loads(e.provenance_json)["worker_instance"]
                                        for e in outcomes.values()},
                      statuses=dict(Counter(e.status for e in outcomes.values())),
                      degradations=sorted({d for e in primary for d in e.degradations}))
        if args.report:
            args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result))
    finally:
        if audio is not None:
            audio.close()
        stop.set()
        event_ws.close()
        thread.join(2)
        consumer.close()


if __name__ == "__main__":
    main()
