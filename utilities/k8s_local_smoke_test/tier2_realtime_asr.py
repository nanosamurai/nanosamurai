"""Tier 2 smoke test: realtime audio -> rtservice -> ASR events.

PASS criteria:
- Tier 1 passes (session + WS events)
- Send audio to /ws/audio
- Receive at least one JSON event with type=asr on /ws/events

This proves audio flowed through BFF -> rtservice gRPC and ASR produced output.
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

from utilities.k8s_local_smoke_test import _lib


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=_lib.DEFAULT_BASE_URL)
    ap.add_argument("--wav", default="tests/data/test_cs.wav")
    ap.add_argument("--lang", default="en")
    # rtservice window defaults to ~10s in current deployments; stream a bit more
    # to reliably trigger at least one ASR event even when FINAL emission is window-based.
    ap.add_argument("--stream-seconds", type=float, default=12.0)
    ap.add_argument("--asr-timeout", type=float, default=45.0)
    args = ap.parse_args()

    base_url = args.base_url.rstrip("/")
    ws_base = _lib.http_to_ws(base_url)

    print(f"[tier2] base_url={base_url}")

    session_id = _lib.create_session(base_url)
    print(f"[tier2] created session_id={session_id}")

    pcm_full = _lib.read_wav_as_pcm16le(args.wav, target_sr=16000)
    start_sec = _lib.find_non_silent_start_sec(pcm_full)
    pcm = _lib.slice_pcm16le(pcm_full, start_sec=start_sec, max_seconds=args.stream_seconds)
    print(
        f"[tier2] loaded wav={args.wav} sr={pcm.sample_rate} bytes={len(pcm_full.pcm16le)} "
        f"(streaming from ~{start_sec:.2f}s)"
    )

    q: queue.Queue[str] = queue.Queue()
    events_url = f"{ws_base}/ws/events?session_id={urllib.parse.quote(session_id)}"
    audio_url = (
        f"{ws_base}/ws/audio?session_id={urllib.parse.quote(session_id)}"
        f"&lang={urllib.parse.quote(args.lang)}&sample_rate={pcm.sample_rate}"
    )

    print(f"[tier2] connecting events ws: {events_url}")
    events_app = _lib.start_events_ws(events_url, q)
    time.sleep(0.5)

    print(f"[tier2] connecting audio ws: {audio_url}")
    audio_ws = _lib.connect_audio_ws(audio_url)

    try:
        print(f"[tier2] streaming {args.stream_seconds:.1f}s audio")
        _lib.stream_audio(audio_ws, pcm, frame_ms=20, max_seconds=args.stream_seconds)

        # Help servers flush buffered audio / finalize a window.
        try:
            audio_ws.close()
        except Exception:
            pass

        print("[tier2] waiting for asr event...")

        ev = _lib.wait_for_json_event_type(q, event_type="asr", timeout_s=args.asr_timeout)
        if not ev:
            print(
                "[tier2] FAIL: did not receive type=asr event. "
                "Likely causes: rtservice still warming up, too little audio streamed, or WS rejected."
            )
            return 1

        print(f"[tier2] PASS: got asr event keys={list(ev.keys())}")
        return 0

    finally:
        try:
            audio_ws.close()
        except Exception:
            pass
        try:
            events_app.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
