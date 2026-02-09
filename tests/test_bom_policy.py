"""Policy test: no JSON files under content directories may contain a UTF-8 BOM.

Scans assets/, scenes/, worlds/, and locales/ for .json files that start with
the UTF-8 BOM byte sequence (EF BB BF).  Reports all offending paths in
deterministic sorted order so CI output is stable.
"""
from __future__ import annotations

from pathlib import Path

import pytest

# Directories that contain content JSON files shipped with the game.
_CONTENT_DIRS = ["assets", "scenes", "worlds", "locales"]

# Root of the repository (tests/ is one level below).
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _find_bom_json_files() -> list[str]:
    """Return sorted list of repo-relative paths with a leading BOM."""
    hits: list[str] = []
    for dirname in _CONTENT_DIRS:
        content_dir = _REPO_ROOT / dirname
        if not content_dir.is_dir():
            continue
        for json_file in sorted(content_dir.rglob("*.json")):
            try:
                raw = json_file.read_bytes()[:3]
            except OSError:
                continue
            if raw == b"\xef\xbb\xbf":
                hits.append(str(json_file.relative_to(_REPO_ROOT)))
    hits.sort()
    return hits


class TestNoBomInContentJson:
    def test_no_json_files_have_bom(self) -> None:
        """All JSON files under content directories must be BOM-free."""
        offending = _find_bom_json_files()
        if offending:
            file_list = "\n  ".join(offending)
            pytest.fail(
                f"UTF-8 BOM detected in {len(offending)} JSON file(s). "
                f"Remove the BOM (e.g. re-save as UTF-8 without BOM):\n  {file_list}"
            )
