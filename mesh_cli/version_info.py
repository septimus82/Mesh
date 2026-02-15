from __future__ import annotations

import re
from pathlib import Path


_VERSION_RE = re.compile(r'^ENGINE_VERSION\s*=\s*"([^"]+)"\s*$', re.MULTILINE)


def get_version_file_path() -> Path:
    """Return the canonical version source file."""
    return Path(__file__).resolve().parents[1] / "engine" / "version.py"


def read_tool_version(path: Path | None = None) -> str:
    """Read the version directly from the canonical file (cache-safe)."""
    version_path = path or get_version_file_path()
    try:
        text = version_path.read_text(encoding="utf-8")
    except OSError:
        return "unknown"
    matches = _VERSION_RE.findall(text)
    if len(matches) != 1:
        return "unknown"
    return str(matches[0]).strip() or "unknown"


def get_tool_version() -> str:
    """Return the canonical Mesh tool version string."""
    return read_tool_version()
