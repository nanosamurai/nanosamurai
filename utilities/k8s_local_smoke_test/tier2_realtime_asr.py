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

import requests

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
        "--require-final-count",
        type=int,
        default=1,
        help="number of final events required per selected required track",
    )
    ap.add_argument(
        "--require-speaker-labels",
        action="store_true",
        help="count only final events carrying a non-empty speaker label",
    )
    ap.add_argument(
        "--require-distinct-speakers",
        type=int,
        default=0,
        help="number of distinct non-empty speaker labels required per selected track",
    )
    ap.add_argument(
        "--require-speaker-epochs",
        type=int,
        default=0,
        help="number of distinct EPOCH_* speaker-label scopes required per selected track",
    )
    ap.add_argument(
        "--require-speakerless-finals",
        action="store_true",
        help="count only final events with no speaker label",
    )
    ap.add_argument(
        "--require-tracks",
        default="",
        help="comma-separated track IDs that must each emit a matching ASR event",
    )
    ap.add_argument(
        "--realtime-tracks",
        default="",
        help="comma-separated realtime track selection passed to /ws/audio",
    )
    ap.add_argument(
        "--realtime-only",
        action="store_true",
        help="disable refined/final Kafka work for a provider-only smoke",
    )
    args = ap.parse_args()
    if args.require_final_count < 1:
        ap.error("--require-final-count must be at least 1")
    if args.require_final_count > 1 and not args.require_final:
        ap.error("--require-final-count greater than 1 requires --require-final")
    if args.require_speaker_labels and not args.require_final:
        ap.error("--require-speaker-labels requires --require-final")
    if args.require_distinct_speakers < 0:
        ap.error("--require-distinct-speakers cannot be negative")
    if args.require_distinct_speakers and not args.require_speaker_labels:
        ap.error("--require-distinct-speakers requires --require-speaker-labels")
    if args.require_speaker_epochs < 0:
        ap.error("--require-speaker-epochs cannot be negative")
    if args.require_speaker_epochs and not args.require_speaker_labels:
        ap.error("--require-speaker-epochs requires --require-speaker-labels")
    if args.require_speakerless_finals and not args.require_final:
        ap.error("--require-speakerless-finals requires --require-final")
    if args.require_speaker_labels and args.require_speakerless_finals:
        ap.error("speaker-labelled and speakerless final requirements are mutually exclusive")
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
    audio_query = {
        "session_id": session_id,
        "lang": args.lang,
        "sample_rate": pcm.sample_rate,
    }
    if args.realtime_tracks:
        audio_query["realtime_tracks"] = args.realtime_tracks
    if args.realtime_only:
        audio_query.update({"refined": "false", "final": "false"})
    audio_url = f"{ws_base}/ws/audio?{urllib.parse.urlencode(audio_query)}"

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

        event_kind = (
            f"{args.require_final_count} final asr events"
            if args.require_final and args.require_final_count > 1
            else "final asr event" if args.require_final else "asr event"
        )
        expected = (
            f"{event_kind} from tracks {sorted(required_tracks)}"
            if required_tracks
            else event_kind
        )
        print(f"[tier2] waiting for {expected}...")

        deadline = time.monotonic() + args.asr_timeout
        first_event_elapsed = None
        matched_tracks: set[str] = set()
        final_counts: dict[str, int] = {}
        distinct_speakers: dict[str, set[str]] = {}
        speaker_epochs: dict[str, set[str]] = {}
        matching_event_count = 0
        matching_speakers: set[str] = set()
        matching_epochs: set[str] = set()
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
            if args.require_speaker_labels:
                terminal_match = terminal_match and bool(
                    str(candidate.get("speaker") or "").strip()
                )
            if args.require_speakerless_finals:
                terminal_match = terminal_match and not bool(
                    str(candidate.get("speaker") or "").strip()
                )
            candidate_track = candidate.get("track")
            speaker_label = str(candidate.get("speaker") or "").strip()
            speaker_epoch = speaker_label.partition("/")[0]
            if not speaker_epoch.startswith("EPOCH_"):
                speaker_epoch = ""
            if required_tracks and terminal_match and candidate_track in required_tracks:
                final_counts[candidate_track] = final_counts.get(candidate_track, 0) + 1
                distinct_speakers.setdefault(candidate_track, set()).add(speaker_label)
                distinct_speakers[candidate_track].discard("")
                speaker_epochs.setdefault(candidate_track, set()).add(speaker_epoch)
                speaker_epochs[candidate_track].discard("")
                if (
                    final_counts[candidate_track] >= args.require_final_count
                    and len(distinct_speakers[candidate_track])
                    >= args.require_distinct_speakers
                    and len(speaker_epochs[candidate_track]) >= args.require_speaker_epochs
                ):
                    matched_tracks.add(candidate_track)
                print(
                    f"[tier2] matched track={candidate_track} final={bool(candidate.get('final'))} "
                    f"count={final_counts[candidate_track]} "
                    f"distinct_speakers={len(distinct_speakers[candidate_track])} "
                    f"speaker_epochs={len(speaker_epochs[candidate_track])}"
                )
            elif not required_tracks and terminal_match:
                matching_event_count += 1
                matching_speakers.add(speaker_label)
                matching_speakers.discard("")
                matching_epochs.add(speaker_epoch)
                matching_epochs.discard("")
            if required_tracks and matched_tracks == required_tracks:
                ev = candidate
                break
            if (
                not required_tracks
                and matching_event_count >= args.require_final_count
                and len(matching_speakers) >= args.require_distinct_speakers
                and len(matching_epochs) >= args.require_speaker_epochs
            ):
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
        try:
            response = requests.post(
                f"{base_url}/api/sessions/{urllib.parse.quote(session_id)}/finish",
                timeout=10,
            )
            response.raise_for_status()
            print(f"[tier2] finished session_id={session_id}")
        except requests.RequestException as exc:
            print(f"[tier2] WARN: could not finish test session_id={session_id}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
