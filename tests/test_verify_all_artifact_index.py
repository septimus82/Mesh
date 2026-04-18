"""Fast-tier tests for the ``verify-all --artifact-index`` flag.

These tests exercise ``_build_artifact_index_payload`` directly and
verify the file-writing + ``artifacts_written`` registration logic.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _make_minimal_artifacts(d: Path) -> None:
    """Write the minimum viable set of artifacts."""
    _write(
        d / "verify_all_summary.json",
        {
            "ok": True,
            "steps": [{"name": "verify-demo", "ok": True, "code": 0, "error": "", "artifact": None}],
            "pytest_fast": {"ok": True, "total": 1.0, "top10": 0.5},
            "artifacts": {"dir": d.as_posix(), "written": {"verify_all_summary": d.as_posix() + "/verify_all_summary.json"}},
        },
    )
    _write(d / "exception_budget.json", {"schema_version": 1, "ok": True, "current_count": 5, "baseline_count": 5, "files_scanned": [], "per_file_counts": {}})
    _write(d / "verify_step_durations.json", {"schema_version": 1, "total_ms": 100, "steps": [{"name": "verify-demo", "ms": 100, "ok": True}]})
    _write(
        d / "verify_step_budget_check.json",
        {
            "schema_version": 2,
            "ok": True,
            "tolerance_ms": 50,
            "candidates_used": [],
            "checked_steps": [],
            "offenders": [],
        },
    )
    _write(d / "swallowed_exceptions.json", {"schema_version": 1, "ok": True, "total": 0, "distinct": 0, "per_site": []})
    _write(d / "shadow_backend.json", {"schema_version": 1, "selected": "none", "reason": "uninitialized", "fallbacks": []})


def _make_artifacts_written(d: Path) -> dict[str, str | None]:
    """Build a minimal artifacts_written map matching _make_minimal_artifacts."""
    prefix = d.as_posix()
    return {
        "verify_all_summary": f"{prefix}/verify_all_summary.json",
        "exception_budget": f"{prefix}/exception_budget.json",
        "verify_step_durations": f"{prefix}/verify_step_durations.json",
        "verify_step_budget_check": f"{prefix}/verify_step_budget_check.json",
        "swallowed_exceptions": f"{prefix}/swallowed_exceptions.json",
        "shadow_backend": f"{prefix}/shadow_backend.json",
        "authoring_trace": None,
        "authoring_trace_budget_check": None,
        "verify_report": None,
        "artifact_index": None,
    }


def _identity_normalize(v, *, repo_root=None):
    if v is None:
        return None
    return str(v).replace("\\", "/")


# ---------------------------------------------------------------------------
# _build_artifact_index_payload unit tests
# ---------------------------------------------------------------------------


def test_index_schema_version(tmp_path: Path) -> None:
    from mesh_cli.verify import _build_artifact_index_payload

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _build_artifact_index_payload(
        overall_ok=True,
        artifacts_dir=artifacts,
        artifacts_written=_make_artifacts_written(artifacts),
        normalize=_identity_normalize,
        repo_root=tmp_path,
    )
    assert payload["schema_version"] == 1
    assert payload["bundle_schema_version"] == 1


def test_index_has_required_keys(tmp_path: Path) -> None:
    from mesh_cli.verify import _build_artifact_index_payload

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _build_artifact_index_payload(
        overall_ok=True,
        artifacts_dir=artifacts,
        artifacts_written=_make_artifacts_written(artifacts),
        normalize=_identity_normalize,
        repo_root=tmp_path,
    )
    required = {
        "schema_version",
        "bundle_schema_version",
        "ok",
        "verify_all",
        "written",
        "schemas",
        "readable",
        "generated_files",
    }
    assert set(payload.keys()) == required


def test_index_ok_reflects_overall(tmp_path: Path) -> None:
    from mesh_cli.verify import _build_artifact_index_payload

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    for ok_val in (True, False):
        payload = _build_artifact_index_payload(
            overall_ok=ok_val,
            artifacts_dir=artifacts,
            artifacts_written=_make_artifacts_written(artifacts),
            normalize=_identity_normalize,
            repo_root=tmp_path,
        )
        assert payload["ok"] is ok_val


def test_index_verify_all_points_to_summary(tmp_path: Path) -> None:
    from mesh_cli.verify import _build_artifact_index_payload

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)
    written = _make_artifacts_written(artifacts)

    payload = _build_artifact_index_payload(
        overall_ok=True,
        artifacts_dir=artifacts,
        artifacts_written=written,
        normalize=_identity_normalize,
        repo_root=tmp_path,
    )
    assert payload["verify_all"] == written["verify_all_summary"]


def test_index_written_mirrors_input(tmp_path: Path) -> None:
    from mesh_cli.verify import _build_artifact_index_payload

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)
    written = _make_artifacts_written(artifacts)

    payload = _build_artifact_index_payload(
        overall_ok=True,
        artifacts_dir=artifacts,
        artifacts_written=written,
        normalize=_identity_normalize,
        repo_root=tmp_path,
    )
    assert set(payload["written"].keys()) == set(written.keys())
    for key, val in written.items():
        assert payload["written"][key] == val


def test_index_schemas_from_valid_artifacts(tmp_path: Path) -> None:
    """schemas includes schema_version for readable artifacts that have it."""
    from mesh_cli.verify import _build_artifact_index_payload

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _build_artifact_index_payload(
        overall_ok=True,
        artifacts_dir=artifacts,
        artifacts_written=_make_artifacts_written(artifacts),
        normalize=_identity_normalize,
        repo_root=tmp_path,
    )
    schemas = payload["schemas"]
    assert schemas["exception_budget"] == 1
    assert schemas["verify_step_durations"] == 1
    assert schemas["verify_step_budget_check"] == 2
    assert schemas["shadow_backend"] == 1
    assert schemas["swallowed_exceptions"] == 1
    # verify_all_summary has no schema_version field — should be absent
    assert "verify_all_summary" not in schemas


def test_index_schemas_omits_unreadable(tmp_path: Path) -> None:
    """schemas omits keys for null/missing artifacts."""
    from mesh_cli.verify import _build_artifact_index_payload

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _build_artifact_index_payload(
        overall_ok=True,
        artifacts_dir=artifacts,
        artifacts_written=_make_artifacts_written(artifacts),
        normalize=_identity_normalize,
        repo_root=tmp_path,
    )
    assert "authoring_trace" not in payload["schemas"]
    assert "authoring_trace_budget_check" not in payload["schemas"]
    assert "verify_report" not in payload["schemas"]


def test_index_readable_reflects_state(tmp_path: Path) -> None:
    """readable[key] is True for valid files, False for null/missing."""
    from mesh_cli.verify import _build_artifact_index_payload

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _build_artifact_index_payload(
        overall_ok=True,
        artifacts_dir=artifacts,
        artifacts_written=_make_artifacts_written(artifacts),
        normalize=_identity_normalize,
        repo_root=tmp_path,
    )
    readable = payload["readable"]
    # All keys in written should be in readable
    assert set(readable.keys()) == set(_make_artifacts_written(artifacts).keys())
    # Valid files
    assert readable["exception_budget"] is True
    assert readable["shadow_backend"] is True
    # Null paths
    assert readable["authoring_trace"] is False
    assert readable["authoring_trace_budget_check"] is False


def test_index_readable_corrupt_file(tmp_path: Path) -> None:
    """A corrupt JSON file is readable=False."""
    from mesh_cli.verify import _build_artifact_index_payload

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)
    # Corrupt one file
    (artifacts / "exception_budget.json").write_text("NOT JSON{{{", encoding="utf-8")

    payload = _build_artifact_index_payload(
        overall_ok=True,
        artifacts_dir=artifacts,
        artifacts_written=_make_artifacts_written(artifacts),
        normalize=_identity_normalize,
        repo_root=tmp_path,
    )
    assert payload["readable"]["exception_budget"] is False
    assert "exception_budget" not in payload["schemas"]


def test_index_generated_files_sorted_unique(tmp_path: Path) -> None:
    from mesh_cli.verify import _build_artifact_index_payload

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _build_artifact_index_payload(
        overall_ok=True,
        artifacts_dir=artifacts,
        artifacts_written=_make_artifacts_written(artifacts),
        normalize=_identity_normalize,
        repo_root=tmp_path,
    )
    gen = payload["generated_files"]
    assert isinstance(gen, list)
    assert gen == sorted(gen)
    assert len(gen) == len(set(gen))
    # None values should not appear
    for v in gen:
        assert v is not None


def test_index_deterministic(tmp_path: Path) -> None:
    """Two runs produce identical JSON bytes."""
    from mesh_cli.verify import _build_artifact_index_payload

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)
    written = _make_artifacts_written(artifacts)

    def _build():
        return json.dumps(
            _build_artifact_index_payload(
                overall_ok=True,
                artifacts_dir=artifacts,
                artifacts_written=written,
                normalize=_identity_normalize,
                repo_root=tmp_path,
            ),
            indent=2,
            sort_keys=True,
        )

    assert _build() == _build()


# ---------------------------------------------------------------------------
# Integration: _handle_verify_all with monkeypatched payload builder
# ---------------------------------------------------------------------------


def _make_payload(*, ok: bool = True, artifacts_dir: str = "artifacts") -> dict:
    return {
        "ok": ok,
        "steps": [{"name": "verify-demo", "ok": ok, "code": 0 if ok else 1, "error": "" if ok else "failed", "artifact": None}],
        "pytest_fast": {"ok": True, "total": 1.0, "top10": 0.5},
        "artifacts": {
            "dir": artifacts_dir,
            "written": {
                "verify_all_summary": f"{artifacts_dir}/verify_all_summary.json",
                "artifact_index": None,
            },
        },
    }


def test_flag_not_set_no_index_written(tmp_path: Path, monkeypatch, capsys) -> None:
    """Without --artifact-index, index.json is not written."""
    import argparse

    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    args = argparse.Namespace(
        command="verify-all",
        artifacts=str(artifacts),
        report=False,
        report_json=False,
        report_json_artifact=False,
        artifact_index=False,
        pytest_args=[],
        out_dir=None,
        no_index=False,
    )
    verify_mod._handle_verify_all(args)
    capsys.readouterr()

    assert not (artifacts / "index.json").exists()


def test_flag_preserves_exit_code(tmp_path: Path, monkeypatch, capsys) -> None:
    """--artifact-index preserves failing exit code."""
    import argparse

    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(ok=False, artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 2))

    args = argparse.Namespace(
        command="verify-all",
        artifacts=str(artifacts),
        report=False,
        report_json=False,
        report_json_artifact=False,
        artifact_index=True,
        pytest_args=[],
        out_dir=None,
        no_index=False,
    )
    code = verify_mod._handle_verify_all(args)
    capsys.readouterr()

    assert code == 2


def test_artifacts_written_has_index_key_none_by_default(tmp_path: Path, monkeypatch, capsys) -> None:
    """artifact_index appears in stdout payload as None when flag not set."""
    import argparse

    import mesh_cli.verify as verify_mod

    artifacts = tmp_path / "artifacts"
    _make_minimal_artifacts(artifacts)

    payload = _make_payload(artifacts_dir=artifacts.as_posix())
    monkeypatch.setattr(verify_mod, "_build_verify_all_payload", lambda _args: (payload, 0))

    args = argparse.Namespace(
        command="verify-all",
        artifacts=str(artifacts),
        report=False,
        report_json=False,
        report_json_artifact=False,
        artifact_index=False,
        pytest_args=[],
        out_dir=None,
        no_index=False,
    )
    verify_mod._handle_verify_all(args)
    out = capsys.readouterr().out
    out_payload = json.loads(out.strip())

    assert "artifact_index" in out_payload["artifacts"]["written"]
    assert out_payload["artifacts"]["written"]["artifact_index"] is None
