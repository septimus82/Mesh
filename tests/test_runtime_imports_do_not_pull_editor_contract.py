from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tests.subprocess_tools import run_checked


pytestmark = [pytest.mark.fast]


def test_runtime_only_entry_import_and_scene_bootstrap_do_not_pull_editor_modules() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    script = """
import json
import sys

from engine.runtime_only import is_forbidden_editor_import

before = set(sys.modules)
from engine.runtime_only.entry import run_runtime_scene
rc = int(run_runtime_scene(quiet=True))
after = set(sys.modules)

offenders = sorted(
    name
    for name in (after - before)
    if is_forbidden_editor_import(name)
)
print(json.dumps({"rc": rc, "offenders": offenders}, sort_keys=True))
"""
    result = run_checked([sys.executable, "-c", script], cwd=str(repo_root))
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads((result.stdout or "").strip().splitlines()[-1])
    assert payload["rc"] == 0
    assert payload["offenders"] == []
