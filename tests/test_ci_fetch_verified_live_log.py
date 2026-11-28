"""Windows CI's Mesa download (#481): each line reaches the job log while the downloader runs, not when it exits.
The runner's stdout is a pipe, which buffers; Extended 42580284863 showed five attempts with one timestamp."""

from __future__ import annotations

import queue
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

ROOT = Path(__file__).resolve().parents[1]
URL = "https://github.com/pal1000/mesa-dist-win/releases/download/26.0.3/mesa3d-26.0.3-release-msvc.7z"


def test_each_attempt_and_retry_wait_reaches_a_piped_log_at_once(tmp_path: Path) -> None:
    release = tmp_path / "release"
    code = textwrap.dedent(f"""
        import pathlib, time, urllib.error
        from email.message import Message
        from tooling.ci_fetch_verified import fetch

        def opener(url, timeout):
            raise urllib.error.HTTPError(url, 504, "Gateway Time-out", Message(), None)

        def sleep(seconds):  # the retry wait, held until the test has read what was logged so far
            while not pathlib.Path({str(release)!r}).exists():
                time.sleep(0.05)

        fetch({URL!r}, "0" * 64, pathlib.Path({str(tmp_path / "mesa.7z")!r}), opener=opener, sleep=sleep, delays=(10,))
    """)
    # Not "python -u": the downloader must flush by itself (the setup action adds -u as well).
    proc = subprocess.Popen([sys.executable, "-c", code], cwd=ROOT, stdout=subprocess.PIPE, text=True)
    lines: queue.Queue[str] = queue.Queue()

    def pump() -> None:
        for line in proc.stdout or []:
            lines.put(line.rstrip("\n"))

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    try:
        during = [lines.get(timeout=60), lines.get(timeout=60)]
        assert proc.poll() is None  # read while it waits to retry, not after it exited
    finally:
        release.touch()
        proc.wait(timeout=60)
    assert during == [f"attempt 1/2: GET {URL}", "attempt 1/2 failed: HTTP 504 Gateway Time-out; retrying in 10 s"]
    assert lines.get(timeout=10) == f"attempt 2/2: GET {URL}"
    assert lines.get(timeout=10) == "::error::mesa.7z: all 2 attempts failed; last: HTTP 504 Gateway Time-out"
    reader.join(timeout=10)
    if proc.stdout:
        proc.stdout.close()
