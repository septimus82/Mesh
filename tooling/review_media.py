"""Animated review media: the WebP clips the studies write for a person to look at, which nothing asserts on.

Encoding them is slow (#422 GPU lane), so automated tests leave them off: tests/conftest.py sets MESH_REVIEW_MEDIA=0
unless it is set already. A study run by hand writes them, as before; ``MESH_REVIEW_MEDIA=1`` writes them in a test
run too. The frames themselves are still drawn and read back either way: only the encoding is skipped.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def wanted() -> bool:
    return os.environ.get("MESH_REVIEW_MEDIA", "1") != "0"


def save_clip(frames: list[Any], path: Path, **options: Any) -> None:
    """``frames`` as an animated picture at ``path`` (PIL ``save`` options: duration, quality, ...), if wanted."""
    if frames and wanted():
        frames[0].save(path, save_all=True, append_images=frames[1:], loop=0, **options)
