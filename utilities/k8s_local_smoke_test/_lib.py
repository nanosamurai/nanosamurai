"""Shared helpers for local k8s smoke tests.

These helpers are intentionally dependency-light so that Tier 1/2 can run with
`requirements.txt` only.

Tier 3/4 (Kafka verification) add `confluent-kafka` + protobuf parsing.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import urllib.parse
import wave
from dataclasses import dataclass
from typing import Optional

import numpy as np
import requests
import websocket  # websocket-client

DEFAULT_BASE_URL = os.environ.get("BFF_BASE_URL", "http://localhost:8000")


@dataclass(frozen=True)
class WavPcm16:
    sample_rate: int
    pcm16le: bytes


def read_wav_as_pcm16le(path: str, target_sr: int = 16000) -> WavPcm16:
    """Read a WAV file and return raw PCM16LE bytes.

    Strict by design: expects PCM16, resamples linearly if SR differs.
    """

    with wave.open(path, "rb") as wf:
        nch = wf.getnchannels()
        sr = wf.getframerate()
        sampwidth = wf.getsampwidth()
        nframes = wf.getnframes()
        comptype = wf.getcomptype()

        if comptype != "NONE":
            raise ValueError(f"Unsupported WAV compression: {comptype}")
        if sampwidth != 2:
            raise ValueError(f"Expected 16-bit PCM WAV (sampwidth=2), got sampwidth={sampwidth}")

        raw = wf.readframes(nframes)

    audio_i16 = np.frombuffer(raw, dtype="<i2")
    if nch > 1:
        audio_i16 = audio_i16.reshape(-1, nch).mean(axis=1).astype(np.int16)

    if sr != target_sr:
        x = audio_i16.astype(np.float32)
        duration = x.shape[0] / sr
        t_old = np.linspace(0.0, duration, num=x.shape[0], endpoint=False)
        n_new = int(round(duration * target_sr))
        t_new = np.linspace(0.0, duration, num=n_new, endpoint=False)
        x_new = np.interp(t_new, t_old, x).astype(np.int16)
        audio_i16 = x_new
        sr = target_sr

    return WavPcm16(sample_rate=sr, pcm16le=audio_i16.astype("<i2").tobytes())


def create_session(base_url: str, timeout_s: float = 10.0) -> str:
    # Explicit JSON avoids occasional 400s due to missing content-type/body
    # when running through certain proxies / environments.
    # Compose bring-up can restart the BFF; make this resilient to brief windows
    # where the TCP connection is accepted but the server closes the socket.
    deadline = time.time() + float(timeout_s)
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            r = requests.post(
                f"{base_url}/api/sessions",
                headers={"content-type": "application/json"},
                data="{}",
                timeout=min(5.0, max(1.0, deadline - time.time())),
            )

            # Retry on typical "starting up" statuses.
            if r.status_code in (502, 503, 504):
                time.sleep(0.5)
                continue

            r.raise_for_status()
            data = r.json()
            session_id = data.get("session_id")
            if not session_id:
                raise RuntimeError(f"No session_id in response: {data}")
            return str(session_id)

        except requests.exceptions.RequestException as e:
            last_err = e
            time.sleep(0.5)
            continue

    if last_err:
        raise last_err
    raise TimeoutError(f"Timed out creating session via {base_url}/api/sessions")


def http_to_ws(base_url: str) -> str:
    u = urllib.parse.urlparse(base_url)
    if u.scheme == "http":
        scheme = "ws"
    elif u.scheme == "https":
        scheme = "wss"
    else:
        raise ValueError(f"Unsupported base URL scheme: {u.scheme}")
    return urllib.parse.urlunparse((scheme, u.netloc, "", "", "", ""))


def start_events_ws(ws_url: str, out_q: queue.Queue[str]) -> websocket.WebSocketApp:
    def on_message(_ws, message):
        if isinstance(message, bytes):
            try:
                message = message.decode("utf-8", errors="replace")
            except Exception:
                message = repr(message)
        out_q.put(str(message))

    def on_error(_ws, err):
        out_q.put(f"__error__:{err!r}")

    app = websocket.WebSocketApp(ws_url, on_message=on_message, on_error=on_error)
    t = threading.Thread(target=app.run_forever, kwargs={"ping_interval": 10, "ping_timeout": 5}, daemon=True)
    t.start()
    return app


def connect_audio_ws(ws_url: str) -> websocket.WebSocket:
    return websocket.create_connection(ws_url, timeout=10)


def slice_pcm16le(pcm: WavPcm16, start_sec: float, max_seconds: float) -> WavPcm16:
    """Return a sub-slice of PCM bytes (time-based)."""

    start_b = int(max(0.0, start_sec) * pcm.sample_rate) * 2
    max_b = int(max_seconds * pcm.sample_rate) * 2
    return WavPcm16(sample_rate=pcm.sample_rate, pcm16le=pcm.pcm16le[start_b : start_b + max_b])


def find_non_silent_start_sec(pcm: WavPcm16, window_sec: float = 0.5, rms_threshold_i16: float = 200.0) -> float:
    """Heuristic: find first window whose RMS exceeds a threshold.

    This helps Tier 2 be reliable if the WAV starts with silence.
    """

    arr = np.frombuffer(pcm.pcm16le, dtype="<i2").astype(np.float32)
    w = int(window_sec * pcm.sample_rate)
    if w <= 0:
        return 0.0

    n = arr.shape[0]
    for i in range(0, n, w):
        seg = arr[i : i + w]
        if seg.size == 0:
            break
        rms = float(np.sqrt(np.mean(seg * seg)))
        if rms >= rms_threshold_i16:
            return i / pcm.sample_rate

    return 0.0


def stream_audio(ws: websocket.WebSocket, pcm: WavPcm16, frame_ms: int = 20, max_seconds: float = 3.0) -> None:
    sr = pcm.sample_rate
    samples_per_frame = int(sr * (frame_ms / 1000.0))
    frame_bytes = samples_per_frame * 2

    total_bytes = min(len(pcm.pcm16le), int(max_seconds * sr) * 2)
    sent = 0
    while sent < total_bytes:
        chunk = pcm.pcm16le[sent : sent + frame_bytes]
        if not chunk:
            break
        ws.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)
        sent += len(chunk)
        time.sleep(frame_ms / 1000.0)


def wait_for_json_event(out_q: queue.Queue[str], timeout_s: float) -> Optional[dict]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        remaining = max(0.1, deadline - time.time())
        try:
            msg = out_q.get(timeout=remaining)
        except queue.Empty:
            continue

        if msg.startswith("__error__:"):
            continue

        try:
            return json.loads(msg)
        except Exception:
            continue

    return None


def wait_for_json_event_type(out_q: queue.Queue[str], event_type: str, timeout_s: float) -> Optional[dict]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        remaining = max(0.1, deadline - time.time())
        try:
            msg = out_q.get(timeout=remaining)
        except queue.Empty:
            continue

        if msg.startswith("__error__:"):
            continue

        try:
            ev = json.loads(msg)
        except Exception:
            continue

        if ev.get("type") == event_type:
            return ev

    return None
