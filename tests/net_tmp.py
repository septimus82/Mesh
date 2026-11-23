"""A private temp folder for a test's server subprocess. mesh_net.server hosts its room from a ``mesh-room-*`` folder
(scene_room.disposable_project) that its own exit removes; a process the test kills outright cannot, so the test
points the child's temp folder (TMP/TEMP/TMPDIR) here and removes it itself, passing or failing."""
from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def private_temp() -> Iterator[tuple[dict[str, str], str]]:
    """(environment for the child, the folder its temp files land in); the folder is removed on exit."""
    base = tempfile.mkdtemp(prefix="mesh-net-test-")
    try:
        yield {**os.environ, "TMP": base, "TEMP": base, "TMPDIR": base}, base
    finally:
        shutil.rmtree(base, ignore_errors=True)
