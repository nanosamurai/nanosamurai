"""Tier 2 smoke test: realtime audio -> configured ASR tracks -> events.

PASS criteria:
- Tier 1 passes (session + WS events)
- Send audio to /ws/audio
- Receive at least one JSON event with type=asr on /ws/events

This proves audio flowed through BFF -> realtime gRPC service(s) and ASR produced output.
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
    ap.add_argument(
        "--require-final",
        action="store_true",
        help="wait for a terminal ASR event instead of accepting the first partial",
    )
    ap.add_argument(
        "--require-tracks",
        default="",
        help="comma-separated track IDs that must each emit a matching ASR event",
    )
    args = ap.parse_args()
    required_tracks = {track.strip() for track in args.require_tracks.split(",") if track.strip()}

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
        stream_started = time.monotonic()
        _lib.stream_audio(audio_ws, pcm, frame_ms=20, max_seconds=args.stream_seconds)

        # Help servers flush buffered audio / finalize a window.
        try:
            audio_ws.close()
        except Exception:
            pass

        event_kind = "final asr event" if args.require_final else "asr event"
        expected = (
            f"{event_kind} from tracks {sorted(required_tracks)}"
            if required_tracks
            else event_kind
        )
        print(f"[tier2] waiting for {expected}...")

        deadline = time.monotonic() + args.asr_timeout
        first_event_elapsed = None
        matched_tracks: set[str] = set()
        ev = None
        while time.monotonic() < deadline:
            candidate = _lib.wait_for_json_event_type(
                q,
                event_type="asr",
                timeout_s=max(0.1, deadline - time.monotonic()),
            )
            if not candidate:
                break
            if first_event_elapsed is None:
                first_event_elapsed = time.monotonic() - stream_started
                print(
                    "[tier2] first asr event "
                    f"elapsed={first_event_elapsed:.2f}s final={bool(candidate.get('final'))}"
                )
            terminal_match = not args.require_final or candidate.get("final") is True
            candidate_track = candidate.get("track")
            if required_tracks and terminal_match and candidate_track in required_tracks:
                matched_tracks.add(candidate_track)
                print(f"[tier2] matched track={candidate_track} final={bool(candidate.get('final'))}")
            if required_tracks and matched_tracks == required_tracks:
                ev = candidate
                break
            if not required_tracks and terminal_match:
                ev = candidate
                break

        if not ev:
            print(
                f"[tier2] FAIL: did not receive {expected}; "
                f"missing_tracks={sorted(required_tracks - matched_tracks)}. "
                "Likely causes: rtservice still warming up, too little audio streamed, or WS rejected."
            )
            return 1

        elapsed = time.monotonic() - stream_started
        print(
            f"[tier2] PASS: got asr event elapsed={elapsed:.2f}s "
            f"final={bool(ev.get('final'))} tracks={sorted(matched_tracks)} keys={list(ev.keys())}"
        )
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
