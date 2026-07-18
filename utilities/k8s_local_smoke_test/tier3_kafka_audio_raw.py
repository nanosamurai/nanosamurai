"""Tier 3 (optional) smoke test: verify BFF publishes AudioChunk to Kafka.

PASS criteria:
- Create session
- Stream some audio over /ws/audio
- Consume Kafka topic audio.raw and observe an AudioChunk with matching session_id

Requires:
  pip install -r utilities/k8s_local_smoke_test/requirements.kafka.txt

Notes:
- This does not depend on whisperx/recorder/finalizer.
- It validates Kafka connectivity + advertised listeners + BFF publisher.
"""

from __future__ import annotations

import pathlib
import sys

# Allow running this file directly (without `python -m ...`).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import argparse
import queue
import time
import urllib.parse

from confluent_kafka import Consumer

from proto_gen import stream_pb2
from utilities.k8s_local_smoke_test import _lib


def _make_consumer(bootstrap: str, group_id: str) -> Consumer:
    return Consumer(
        {
            "bootstrap.servers": bootstrap,
            "group.id": group_id,
            "auto.offset.reset": "latest",
            "enable.auto.commit": False,
            # Windows: prefer IPv4. Otherwise confluent-kafka may try ::1 first and fail
            # even when 127.0.0.1 works.
            "broker.address.family": "v4",
        }
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=_lib.DEFAULT_BASE_URL)
    ap.add_argument("--wav", default="tests/data/test_cs.wav")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--stream-seconds", type=float, default=2.0)
    ap.add_argument("--kafka-bootstrap", required=True, help="Kafka bootstrap as seen from your machine")
    ap.add_argument("--timeout", type=float, default=20.0)
    ap.add_argument("--topic", default="audio.raw")
    args = ap.parse_args()

    base_url = args.base_url.rstrip("/")
    ws_base = _lib.http_to_ws(base_url)

    session_id = _lib.create_session(base_url)
    print(f"[tier3] session_id={session_id}")

    pcm = _lib.read_wav_as_pcm16le(args.wav, target_sr=16000)

    # Start consuming before we stream audio (to avoid missing messages)
    consumer = _make_consumer(args.kafka_bootstrap, group_id=f"tier3-{int(time.time())}")
    consumer.subscribe([args.topic])

    # Kafka subscription assignment is async; poll until partitions are assigned.
    # Otherwise a short audio stream can complete before the consumer is ready,
    # and with auto.offset.reset=latest we'd miss the messages.
    t0 = time.time()
    while time.time() - t0 < 5.0:
        consumer.poll(0.1)
        if consumer.assignment():
            break

    events_q: queue.Queue[str] = queue.Queue()
    events_url = f"{ws_base}/ws/events?session_id={urllib.parse.quote(session_id)}"
    audio_url = (
        f"{ws_base}/ws/audio?session_id={urllib.parse.quote(session_id)}"
        f"&lang={urllib.parse.quote(args.lang)}&sample_rate={pcm.sample_rate}"
    )

    events_app = _lib.start_events_ws(events_url, events_q)
    time.sleep(0.5)
    audio_ws = _lib.connect_audio_ws(audio_url)

    try:
        _lib.stream_audio(audio_ws, pcm, frame_ms=20, max_seconds=args.stream_seconds)

        deadline = time.time() + args.timeout
        while time.time() < deadline:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                continue

            chunk = stream_pb2.AudioChunk()
            chunk.ParseFromString(msg.value())
            if chunk.session_id == session_id:
                hdrs = msg.headers() or []
                # Extract traceparent if present (W3C Trace Context).
                tp = None
                for (k, v) in hdrs:
                    if (k or "").lower() == "traceparent" and v:
                        try:
                            tp = v.decode("utf-8")
                        except Exception:
                            tp = str(v)
                        break

                print(f"[tier3] PASS: observed AudioChunk in Kafka topic={args.topic} session_id={session_id}")
                if tp:
                    print(f"[tier3] traceparent={tp}")
                else:
                    # Keep this compact; just show header keys.
                    keys = [str(k) for (k, _v) in hdrs]
                    print(f"[tier3] WARN: no traceparent header found. headers={keys}")
                return 0

        print("[tier3] FAIL: did not observe matching AudioChunk on audio.raw")
        return 1

    finally:
        try:
            audio_ws.close()
        except Exception:
            pass
        try:
            events_app.close()
        except Exception:
            pass
        try:
            consumer.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
