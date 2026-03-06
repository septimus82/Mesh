from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]

_TESTS_DIR = Path(__file__).resolve().parent
_BASELINE_PATH = _TESTS_DIR / "baselines" / "fast_marking_contract_allowlist.txt"
_FILE_PATTERN = re.compile(r"test_.*(contract|invariants).*\.py$")
_UPDATE_COMMAND = (
    "python -c \"import os, subprocess, sys; import tests.test_fast_marking_policy_contract as t; "
    "os.environ['MESH_UPDATE_FAST_MARKING_BASELINE']='1'; "
    "raise SystemExit(subprocess.call([sys.executable, '-m', 'pytest', '-q', t.__file__]))\""
)


def _load_baseline() -> list[str]:
    if not _BASELINE_PATH.exists():
        return []
    rows: list[str] = []
    for line in _BASELINE_PATH.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        rows.append(text)
    return sorted(rows)


def _iter_contract_like_test_paths() -> list[Path]:
    return sorted(
        path
        for path in _TESTS_DIR.rglob("test_*.py")
        if _FILE_PATTERN.search(path.name)
    )


def _has_fast_marker(source: str) -> bool:
    if "@pytest.mark.fast" in source:
        return True
    return bool(
        re.search(
            r"^\s*pytestmark\s*=.*pytest\.mark\.fast",
            source,
            flags=re.MULTILINE,
        )
    )


def test_contract_and_invariants_modules_require_fast_markers() -> None:
    missing_markers: list[str] = []
    for path in _iter_contract_like_test_paths():
        text = path.read_text(encoding="utf-8")
        if _has_fast_marker(text):
            continue
        missing_markers.append(path.relative_to(_TESTS_DIR.parent).as_posix())
    current = sorted(missing_markers)

    if os.getenv("MESH_UPDATE_FAST_MARKING_BASELINE") == "1":
        _BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = "\n".join(current)
        if payload:
            payload += "\n"
        _BASELINE_PATH.write_text(payload, encoding="utf-8")

    allowed = set(_load_baseline())
    unexpected = sorted(path for path in current if path not in allowed)
    stale = sorted(path for path in allowed if path not in set(current))
    assert not unexpected and not stale, (
        "Contract/invariants fast-marking baseline drift detected.\n"
        + (
            "New unmarked files:\n" + "\n".join(unexpected) + "\n\n"
            if unexpected
            else ""
        )
        + (
            "Baseline entries no longer needed:\n" + "\n".join(stale) + "\n\n"
            if stale
            else ""
        )
        + f"Update baseline intentionally with:\n{_UPDATE_COMMAND}"
    )
