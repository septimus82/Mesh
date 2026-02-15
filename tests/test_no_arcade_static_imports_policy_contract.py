from __future__ import annotations

from pathlib import Path

import pytest

import tests.test_no_arcade_static_imports_policy as policy

pytestmark = [pytest.mark.fast]


def test_import_safety_guard_scoped_and_fast() -> None:
    marker_names = {m.name for m in policy.pytestmark}
    assert marker_names == {"fast"}
    assert policy.SCAN_DIRS == ["engine", "mesh_cli", "tooling"]


def test_import_safety_guard_scans_sorted_files() -> None:
    source = Path(policy.__file__).read_text(encoding="utf-8")
    assert "for rel_path in sorted(files_to_scan):" in source

