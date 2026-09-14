"""Test-only inference replacement; buffering/publishing/commits are production code."""
import os
import time
from pathlib import Path

from whisperx_worker import whisperx_worker as worker


def infer(path, **_kwargs):
    """Return deterministic short segments or block/fail for fault injection."""
    gate = os.getenv("TEST_GATE")
    if gate and Path(gate).exists():
        Path(gate + ".entered").touch()
        while Path(gate).exists():
            time.sleep(0.1)
    failure = os.getenv("TEST_FAILURE")
    if failure and Path(failure).exists():
        raise RuntimeError("Test-only inference failure")
    pcm, sr = worker.sf.read(path)
    duration = len(pcm) / sr
    return "synthetic test only", [(0.0, min(duration, 0.5), "synthetic test only", "")]


worker._init_whisperx = lambda: None
worker.run_whisperx_diarized = infer
worker.main()
