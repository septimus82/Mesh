from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]

_FORBIDDEN_PREFIXES = (
    "engine.editor",
    "engine.scene_runtime",
    "engine.scene_controller",
)

# Keep explicit in case a narrow compatibility exception is needed later.
_ALLOWLIST: set[str] = set()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _discover_ui_overlay_modules() -> list[str]:
    base = _repo_root() / "engine" / "ui_overlays"
    modules: list[str] = []
    for path in sorted(base.glob("*.py")):
        if path.name == "__init__.py":
            continue
        modules.append(f"engine.ui_overlays.{path.stem}")
    return modules


def _capture_import_issues(target_modules: list[str]) -> dict[str, object]:
    script = (
        "import importlib, json, sys\n"
        "targets = json.loads(sys.argv[1])\n"
        "forbidden = tuple(json.loads(sys.argv[2]))\n"
        "allowlist = set(json.loads(sys.argv[3]))\n"
        "issues = []\n"
        "for target in targets:\n"
        "    before = set(sys.modules)\n"
        "    importlib.import_module(target)\n"
        "    after = set(sys.modules)\n"
        "    new_modules = sorted(after - before)\n"
        "    offenders = []\n"
        "    for name in new_modules:\n"
        "        is_forbidden = any(name == p or name.startswith(p + '.') for p in forbidden)\n"
        "        if is_forbidden and name not in allowlist:\n"
        "            offenders.append(name)\n"
        "    if offenders:\n"
        "        issues.append({'target': target, 'offenders': offenders})\n"
        "print(json.dumps({'targets': targets, 'issues': issues}, sort_keys=True))\n"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            json.dumps(target_modules, sort_keys=True),
            json.dumps(list(_FORBIDDEN_PREFIXES), sort_keys=True),
            json.dumps(sorted(_ALLOWLIST), sort_keys=True),
        ],
        capture_output=True,
        text=True,
        cwd=str(_repo_root()),
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"import probe failed: rc={result.returncode}\n"
            f"stdout={result.stdout}\n"
            f"stderr={result.stderr}"
        )
    payload = json.loads(result.stdout.strip() or "{}")
    assert isinstance(payload, dict)
    return payload


def test_ui_overlays_import_policy_contract() -> None:
    targets = _discover_ui_overlay_modules()
    assert targets
    assert "engine.ui_overlays.providers" in targets
    assert "engine.ui_overlays.command_palette" in targets

    payload = _capture_import_issues(targets)
    issues = payload.get("issues")
    assert isinstance(issues, list)
    assert issues == []
