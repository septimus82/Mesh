"""A private temp folder for a test's server subprocess. mesh_net.server hosts its room from a ``mesh-room-*`` folder
(scene_room.disposable_project) that its own exit removes; a process the test kills outright cannot, so the test
points the child's temp folder (TMP/TEMP/TMPDIR) here and removes it itself, passing or failing."""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def private_temp() -> Iterator[tuple[dict[str, str], str]]:
    """(environment for the child, the folder its temp files land in); the folder is removed on exit."""
    base = tempfile.mkdtemp(prefix="mesh-net-test-")
    try:
        yield {**os.environ, "TMP": base, "TEMP": base, "TMPDIR": base}, base
    finally:
        for _ in range(20):  # (a just-killed child's handles can take a moment to go)
            shutil.rmtree(base, ignore_errors=True)
            if not os.path.exists(base):
                break
            time.sleep(0.25)
        else:
            if sys.exc_info()[0] is None:  # (a failure in the test itself still wins)
                raise RuntimeError(f"the private temp folder could not be removed: {os.path.basename(base)}")
