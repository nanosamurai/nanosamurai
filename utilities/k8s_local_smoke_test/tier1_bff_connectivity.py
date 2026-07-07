"""Tier 1 smoke test: BFF connectivity + WS events.

PASS criteria:
- POST /api/sessions returns a session_id
- /ws/events yields at least one JSON event (typically type=status)

This is intentionally cheap and should pass even if rtservice is still warming up.
"""

from __future__ import annotations

import pathlib
import sys

# Allow running this file directly (without `python -m ...`).
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import argparse
import queue
import urllib.parse

from utilities.k8s_local_smoke_test import _lib


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=_lib.DEFAULT_BASE_URL)
    ap.add_argument("--events-timeout", type=float, default=10.0)
    args = ap.parse_args()

    base_url = args.base_url.rstrip("/")
    ws_base = _lib.http_to_ws(base_url)

    print(f"[tier1] base_url={base_url}")

    session_id = _lib.create_session(base_url)
    print(f"[tier1] created session_id={session_id}")

    q: queue.Queue[str] = queue.Queue()
    events_url = f"{ws_base}/ws/events?session_id={urllib.parse.quote(session_id)}"
    print(f"[tier1] connecting events ws: {events_url}")
    app = _lib.start_events_ws(events_url, q)

    try:
        ev = _lib.wait_for_json_event(q, timeout_s=args.events_timeout)
        if not ev:
            print("[tier1] FAIL: did not receive any JSON event")
            return 1

        print(f"[tier1] PASS: received event type={ev.get('type')} keys={list(ev.keys())}")
        return 0
    finally:
        try:
            app.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
