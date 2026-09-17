"""Test-only second track: replace inference, exercise the production worker loop."""
import os
import wave
from pathlib import Path

from xamurai_serving import finalization as worker


def transcribe(path, **_kwargs):
    """Return text-only test output, silence, or an explicitly injected failure."""
    failure = os.environ.get("TEST_FAILURE_FILE")
    if failure and Path(failure).exists():
        raise RuntimeError("Injected test-only finalizer failure")
    with wave.open(path, "rb") as wav:
        silence = not any(wav.readframes(wav.getnframes()))
    return ("" if silence else "Synthetic test-only transcript"), []


worker.main(transcribe, model=os.getenv("WHISPERX_MODEL", "synthetic-test-only"))
