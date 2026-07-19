"""Tier 4 (optional) smoke test: verify a selected async pipeline signal via Kafka.

PASS criteria:
- Observe the selected downstream signal for the session_id.

Signals:
- recording-finished: recordings.finished (RecordingFinished)  [default; quick]
- refined:           transcripts.refined (RefinedEvent)
- final:             transcripts.final (SessionTranscript)     [strict; validates finalizer]

Requires:
  pip install -r utilities/k8s_local_smoke_test/requirements.kafka.txt

Notes on time:
- recorder emits only after session idle (no audio) for RECORDER_IDLE_SECONDS.
- whisperx refined emits per slice (default 60s)
- final transcript depends on full-session processing and can be slow on CPU.

Use `--signal final` when you specifically want the test to FAIL if finalizer is broken.
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
    ap.add_argument("--kafka-bootstrap", required=True)
    ap.add_argument("--timeout", type=float, default=90.0)

    ap.add_argument(
        "--expect-speaker",
        default="",
        help=(
            "Optional strict check: require that at least one emitted transcript segment "
            "contains this exact speaker label (e.g. 'Miro (cz)'). "
            "Useful to catch cases where the speaker field exists but is always empty."
        ),
    )

    ap.add_argument(
        "--expect-speaker-alias",
        action="append",
        default=[],
        help=(
            "Optional additional accepted speaker label(s). Can be provided multiple times. "
            "Useful when local dev data uses e.g. 'Miro (cz)' but tests expect 'Miro-cz'."
        ),
    )

    ap.add_argument(
        "--signal",
        choices=["recording-finished", "refined", "final"],
        default="recording-finished",
        help=(
            "Which Kafka signal to validate for the session_id. "
            "Use 'final' to fail when finalizer is down or crashing."
        ),
    )

    # Backwards-compat (soft): old flags still override --signal when provided.
    ap.add_argument("--check-recording-finished", action="store_true", default=False)
    ap.add_argument("--check-refined", action="store_true", default=False)
    ap.add_argument("--check-final", action="store_true", default=False)

    args = ap.parse_args()

    if args.check_final:
        args.signal = "final"
    elif args.check_refined:
        args.signal = "refined"
    elif args.check_recording_finished:
        args.signal = "recording-finished"

    base_url = args.base_url.rstrip("/")
    ws_base = _lib.http_to_ws(base_url)

    session_id = _lib.create_session(base_url)
    print(f"[tier4] session_id={session_id}")
    trace_id = session_id.replace("-", "")
    if len(trace_id) == 32:
        print(f"[tier4] trace_id={trace_id} (Tempo TraceID lookup)")

    pcm = _lib.read_wav_as_pcm16le(args.wav, target_sr=16000)

    # Make Tier4 more reliable: many test WAVs start with silence. If we stream only
    # the first N seconds and that segment is silent, downstream VAD/ASR may emit
    # no refined/final events and the test flakes.
    non_silent_start = _lib.find_non_silent_start_sec(pcm)
    if non_silent_start > 0.0:
        pcm = _lib.slice_pcm16le(pcm, start_sec=non_silent_start, max_seconds=max(3.0, float(args.stream_seconds)))

    if args.signal == "recording-finished":
        topics = ["recordings.finished"]
    elif args.signal == "refined":
        topics = ["transcripts.refined"]
    elif args.signal == "final":
        topics = ["transcripts.final"]
    else:
        raise SystemExit(f"Unsupported --signal: {args.signal}")

    consumer = _make_consumer(args.kafka_bootstrap, group_id=f"tier4-{int(time.time())}")
    consumer.subscribe(topics)

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
        observed_speakers: dict[str, int] = {}

        print(f"[tier4] streaming {args.stream_seconds:.1f}s audio")
        _lib.stream_audio(audio_ws, pcm, frame_ms=20, max_seconds=args.stream_seconds)
        print("[tier4] waiting for async pipeline events (stop sending audio to allow idle)...")

        deadline = time.time() + args.timeout
        while time.time() < deadline:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                continue

            topic = msg.topic()
            payload = msg.value()

            if topic == "recordings.finished":
                ev = stream_pb2.RecordingFinished()
                ev.ParseFromString(payload)
                if ev.session_id == session_id:
                    print(
                        f"[tier4] PASS(signal=recording-finished): got RecordingFinished "
                        f"for session={session_id} url={ev.recording_url}"
                    )
                    return 0

            if topic == "transcripts.refined":
                ev = stream_pb2.RefinedEvent()
                ev.ParseFromString(payload)
                if ev.session_id == session_id:
                    for seg in ev.segments:
                        spk = seg.speaker or ""
                        observed_speakers[spk] = observed_speakers.get(spk, 0) + 1

                    if args.expect_speaker:
                        accepted = [args.expect_speaker] + list(args.expect_speaker_alias or [])
                        if not any((seg.speaker in accepted) for seg in ev.segments):
                            # not good enough yet; keep waiting for a matching label
                            continue
                        speakers = sorted({s.speaker for s in ev.segments if s.speaker})
                        print(
                            f"[tier4] PASS(signal=refined): got RefinedEvent "
                            f"for session={session_id} speakers={speakers[:5]} segments={len(ev.segments)} "
                            f"text_len={len(ev.text)}"
                        )
                        return 0

                    print(
                        f"[tier4] PASS(signal=refined): got RefinedEvent "
                        f"for session={session_id} segments={len(ev.segments)} "
                        f"text_len={len(ev.text)}"
                    )
                    return 0

            if topic == "transcripts.final":
                ev = stream_pb2.SessionTranscript()
                ev.ParseFromString(payload)
                if ev.session_id == session_id:
                    # track observed speaker labels for debug (including empty)
                    for s in ev.segments:
                        spk = s.speaker or ""
                        observed_speakers[spk] = observed_speakers.get(spk, 0) + 1

                    if args.expect_speaker:
                        speakers = {s.speaker for s in ev.segments if s.speaker}
                        accepted = {args.expect_speaker, *list(args.expect_speaker_alias or [])}
                        if not (accepted & speakers):
                            # keep waiting; final transcript for this session may be emitted multiple times
                            # (at-least-once semantics) or refined may arrive first.
                            continue
                        print(
                            f"[tier4] PASS(signal=final): got SessionTranscript "
                            f"for session={session_id} segments={len(ev.segments)} speakers={sorted(speakers)}"
                        )
                        return 0

                    print(
                        f"[tier4] PASS(signal=final): got SessionTranscript "
                        f"for session={session_id} segments={len(ev.segments)}"
                    )
                    return 0

        if args.expect_speaker:
            if observed_speakers:
                # sort by frequency desc for compact debug output
                observed = sorted(observed_speakers.items(), key=lambda kv: (-kv[1], kv[0]))
                observed_str = ", ".join([f"{k!r}:{v}" for (k, v) in observed[:10]])
                more = "" if len(observed) <= 10 else f" (+{len(observed) - 10} more)"
                print(f"[tier4] observed speakers (top): {observed_str}{more}")
            else:
                print("[tier4] observed speakers: <none>")

            print(
                f"[tier4] FAIL(signal={args.signal}): did not observe expected event with speaker="
                f"{args.expect_speaker!r} within {args.timeout:.0f}s"
            )
        else:
            print(
                f"[tier4] FAIL(signal={args.signal}): did not observe expected event within {args.timeout:.0f}s"
            )
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
