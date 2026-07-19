"""Kafka traceparent audit utility (local dev).

Goal
----
When end-to-end traces are missing a service (often `samuraipersistor`), the
first question is:

    "Did we actually propagate the W3C `traceparent` header across Kafka hops?"

This script consumes from one or more topics and prints, for messages matching
the given session_id, whether a `traceparent` header exists and what it is.

This is intentionally *debug-only* and optimized for Windows usage.

Usage
-----

    py -3 utilities/k8s_local_smoke_test/kafka_traceparent_audit.py \
      --kafka-bootstrap 127.0.0.1:9092 \
      --session-id 019caa2d-5c10-7623-912c-8bd580cbc277 \
      --topics audio.raw transcripts.refined recordings.finished transcripts.final \
      --timeout 120

Notes
-----
- We do *not* attempt to create a deterministic trace id here. We only inspect
  headers actually present on Kafka messages.
- This script only matches session_id by parsing protobuf payloads.
"""

from __future__ import annotations

import pathlib
import sys

# Allow running this file directly (without `python -m ...`).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import argparse
import time
from typing import Optional

from confluent_kafka import Consumer

from proto_gen import stream_pb2


def _make_consumer(bootstrap: str, group_id: str) -> Consumer:
    return Consumer(
        {
            "bootstrap.servers": bootstrap,
            "group.id": group_id,
            "auto.offset.reset": "latest",
            "enable.auto.commit": False,
            # Windows: prefer IPv4. Otherwise confluent-kafka may try ::1 first and fail.
            "broker.address.family": "v4",
        }
    )


def _header_value(headers: Optional[list[tuple[str, Optional[bytes]]]], key: str) -> Optional[str]:
    if not headers:
        return None
    key_l = key.lower()
    for k, v in headers:
        if (k or "").lower() != key_l:
            continue
        if v is None:
            return None
        try:
            return v.decode("utf-8")
        except Exception:
            return "<non-utf8>"
    return None


def _session_id_from_payload(topic: str, payload: bytes) -> str:
    """Parse known message types and return session_id or empty string."""

    if topic == "audio.raw":
        msg = stream_pb2.AudioChunk()
        msg.ParseFromString(payload)
        return msg.session_id or ""
    if topic == "transcripts.refined":
        msg = stream_pb2.RefinedEvent()
        msg.ParseFromString(payload)
        return msg.session_id or ""
    if topic == "recordings.finished":
        msg = stream_pb2.RecordingFinished()
        msg.ParseFromString(payload)
        return msg.session_id or ""
    if topic == "transcripts.final":
        msg = stream_pb2.SessionTranscript()
        msg.ParseFromString(payload)
        return msg.session_id or ""

    return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kafka-bootstrap", required=True)
    ap.add_argument("--session-id", required=True)
    ap.add_argument(
        "--offset-reset",
        choices=["latest", "earliest"],
        default="latest",
        help=(
            "Where to start consuming if there is no committed offset for the group. "
            "Use 'earliest' to debug already-produced messages (slower)."
        ),
    )
    ap.add_argument(
        "--topics",
        nargs="+",
        default=["audio.raw", "transcripts.refined", "recordings.finished", "transcripts.final"],
    )
    ap.add_argument("--timeout", type=float, default=60.0)

    args = ap.parse_args()

    session_id = str(args.session_id).strip()
    topics: list[str] = [str(t).strip() for t in (args.topics or []) if str(t).strip()]
    if not topics:
        raise SystemExit("No topics provided")

    c = _make_consumer(args.kafka_bootstrap, group_id=f"traceparent-audit-{int(time.time())}")
    # Apply offset reset policy (Consumer config is mutable via set() only at init, so rebuild).
    # Simplest: close and re-create with desired setting.
    try:
        c.close()
    except Exception:
        pass
    c = Consumer(
        {
            "bootstrap.servers": args.kafka_bootstrap,
            "group.id": f"traceparent-audit-{int(time.time())}",
            "auto.offset.reset": args.offset_reset,
            "enable.auto.commit": False,
            "broker.address.family": "v4",
        }
    )
    c.subscribe(topics)

    print(f"[audit] session_id={session_id}")
    print(f"[audit] topics={topics}")
    print("[audit] waiting for messages...")

    deadline = time.time() + float(args.timeout)
    matched = 0
    try:
        while time.time() < deadline:
            msg = c.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                continue

            topic = msg.topic() or ""
            try:
                sid = _session_id_from_payload(topic, msg.value())
            except Exception:
                # Unknown payload; ignore.
                continue

            if sid != session_id:
                continue

            matched += 1
            tp = _header_value(msg.headers() or [], "traceparent")
            print(
                f"[audit] MATCH topic={topic} partition={msg.partition()} offset={msg.offset()} "
                f"traceparent={tp!r}"
            )

        if matched == 0:
            print(f"[audit] NO MATCHES within {args.timeout:.0f}s")
            return 2

        print(f"[audit] done (matched={matched})")
        return 0
    finally:
        try:
            c.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
