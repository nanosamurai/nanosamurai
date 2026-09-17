"""Test-only inference replacement; buffering/publishing/commits are production code."""
import os
import time
from pathlib import Path

from xamurai_serving import refinement as worker


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
    return "synthetic test only", [dict(start_s=0.0, end_s=min(duration, 0.5),
                                       text="synthetic test only", speaker="")]


worker.main(infer, model="synthetic-test-only")
