"""Fast-tier tests for the optional authoring_trace.json verify artifact.

Covers:
- Default-off: fetch returns None when env var not set.
- Enabled: fetch returns a valid snapshot dict.
- Schema fields present and deterministic.
- Artifact gating in verify-all.
"""
from __future__ import annotations

from typing import Any

import pytest

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# _fetch_authoring_trace_snapshot gating
# ---------------------------------------------------------------------------

def test_fetch_returns_none_when_env_var_not_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MESH_AUTHORING_TRACE_ARTIFACT", raising=False)
    from mesh_cli.verify import _fetch_authoring_trace_snapshot

    result = _fetch_authoring_trace_snapshot()
    assert result is None


def test_fetch_returns_snapshot_when_env_var_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESH_AUTHORING_TRACE_ARTIFACT", "1")
    from mesh_cli.verify import _fetch_authoring_trace_snapshot

    result = _fetch_authoring_trace_snapshot()
    assert result is not None
    assert isinstance(result, dict)
    assert result["schema_version"] == 1
    assert "enabled" in result
    assert "total_calls" in result
    assert "functions" in result
    assert isinstance(result["functions"], list)


def test_fetch_returns_empty_snapshot_when_import_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESH_AUTHORING_TRACE_ARTIFACT", "1")

    # Make SceneController import blow up
    import mesh_cli.verify as verify_mod

    original = verify_mod._fetch_authoring_trace_snapshot

    def _patched() -> dict[str, Any] | None:
        import builtins
        real_import = builtins.__import__

        def _fail_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if "scene_controller" in name:
                raise ImportError("simulated")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fail_import)
        try:
            return original()
        finally:
            monkeypatch.setattr(builtins, "__import__", real_import)

    result = _patched()
    assert result is not None
    assert result["schema_version"] == 1
    assert result["enabled"] is False
    assert result["total_calls"] == 0
    assert result["functions"] == []


# ---------------------------------------------------------------------------
# Snapshot schema
# ---------------------------------------------------------------------------

def test_snapshot_schema_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESH_AUTHORING_TRACE_ARTIFACT", "1")
    from mesh_cli.verify import _fetch_authoring_trace_snapshot

    result = _fetch_authoring_trace_snapshot()
    assert result is not None
    assert set(result.keys()) == {"schema_version", "enabled", "total_calls", "functions"}


def test_snapshot_functions_ordering_is_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MESH_AUTHORING_TRACE_ARTIFACT", "1")
    from mesh_cli.verify import _fetch_authoring_trace_snapshot

    # Call twice and verify identical output
    r1 = _fetch_authoring_trace_snapshot()
    r2 = _fetch_authoring_trace_snapshot()
    assert r1 == r2


# ---------------------------------------------------------------------------
# Artifact written key
# ---------------------------------------------------------------------------

def test_artifacts_written_includes_authoring_trace_key() -> None:
    """The artifacts_written dict in verify.py initializes authoring_trace to None."""
    from pathlib import Path

    import mesh_cli.verify as verify_mod

    src = Path(verify_mod.__file__).read_text(encoding="utf-8")
    assert '"authoring_trace": None' in src


def test_authoring_trace_not_written_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MESH_AUTHORING_TRACE_ARTIFACT", raising=False)
    from mesh_cli.verify import _fetch_authoring_trace_snapshot

    result = _fetch_authoring_trace_snapshot()
    assert result is None, "Artifact should not be written when env var is unset"
