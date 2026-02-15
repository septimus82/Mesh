from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]

_BASELINE_PATH = Path(__file__).resolve().parent / "baselines" / "unmarked_test_nodeids.txt"
_UPDATE_COMMAND = (
    "python -c \"import os, subprocess, sys; import tests.test_tier_marker_ratchet as t; "
    "os.environ['MESH_UPDATE_UNMARKED_BASELINE']='1'; "
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


def test_unmarked_test_nodeids_ratchet(unmarked_test_nodeids: list[str]) -> None:
    current = sorted(str(x) for x in unmarked_test_nodeids)
    if os.getenv("MESH_UPDATE_UNMARKED_BASELINE") == "1":
        _BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = "\n".join(current)
        if payload:
            payload += "\n"
        _BASELINE_PATH.write_text(payload, encoding="utf-8")

    allowed = set(_load_baseline())
    unexpected = sorted(nodeid for nodeid in current if nodeid not in allowed)
    assert not unexpected, (
        "New unmarked tests detected (sorted):\n"
        + "\n".join(unexpected)
        + "\n\n"
        + f"Update baseline intentionally with:\n{_UPDATE_COMMAND}"
    )
