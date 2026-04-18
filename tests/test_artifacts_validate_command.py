"""Fast-tier tests for ``mesh_cli artifacts-validate``."""

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


def _make_minimal_bundle(d: Path) -> None:
    """Write a minimal valid artifact bundle with index.json."""
    _write(
        d / "verify_all_summary.json",
        {
            "ok": True,
            "steps": [],
            "artifacts": {"dir": "artifacts", "written": {}},
        },
    )
    _write(
        d / "exception_budget.json",
        {"schema_version": 1, "ok": True, "current_count": 0, "baseline_count": 0},
    )
    written = {
        "verify_all_summary": "artifacts/verify_all_summary.json",
        "exception_budget": "artifacts/exception_budget.json",
        "authoring_trace": None,
        "artifact_index": "artifacts/index.json",
    }
    schemas = {"exception_budget": 1}
    readable = {
        "verify_all_summary": True,
        "exception_budget": True,
        "authoring_trace": False,
        "artifact_index": True,
    }
    generated = sorted(v for v in written.values() if v is not None)
    _write(
        d / "index.json",
        {
            "schema_version": 1,
            "bundle_schema_version": 1,
            "ok": True,
            "verify_all": "artifacts/verify_all_summary.json",
            "written": written,
            "schemas": schemas,
            "readable": readable,
            "generated_files": generated,
        },
    )


# ---------------------------------------------------------------------------
# validate_artifacts unit tests
# ---------------------------------------------------------------------------


def test_success_case(tmp_path: Path) -> None:
    """Valid bundle -> ok, no issues."""
    from mesh_cli.artifacts_validate import validate_artifacts

    d = tmp_path / "artifacts"
    _make_minimal_bundle(d)

    ok, issues = validate_artifacts(d)
    assert ok is True
    assert issues == []


def test_missing_index(tmp_path: Path) -> None:
    """Missing index.json -> FAILED with missing_index."""
    from mesh_cli.artifacts_validate import validate_artifacts

    d = tmp_path / "artifacts"
    d.mkdir()

    ok, issues = validate_artifacts(d)
    assert ok is False
    assert len(issues) == 1
    assert "missing_index" in issues[0]


def test_corrupt_index(tmp_path: Path) -> None:
    """Corrupt index.json -> FAILED with missing_index (parse error)."""
    from mesh_cli.artifacts_validate import validate_artifacts

    d = tmp_path / "artifacts"
    d.mkdir()
    (d / "index.json").write_text("NOT JSON{{{", encoding="utf-8")

    ok, issues = validate_artifacts(d)
    assert ok is False
    assert any("missing_index" in i for i in issues)


def test_missing_referenced_file(tmp_path: Path) -> None:
    """A non-null written path pointing to nonexistent file -> missing_file."""
    from mesh_cli.artifacts_validate import validate_artifacts

    d = tmp_path / "artifacts"
    _make_minimal_bundle(d)
    # Remove a referenced file
    (d / "exception_budget.json").unlink()

    ok, issues = validate_artifacts(d)
    assert ok is False
    assert any("missing_file" in i and "exception_budget" in i for i in issues)


def test_corrupt_artifact_json(tmp_path: Path) -> None:
    """A referenced file with corrupt JSON -> unreadable_json."""
    from mesh_cli.artifacts_validate import validate_artifacts

    d = tmp_path / "artifacts"
    _make_minimal_bundle(d)
    (d / "exception_budget.json").write_text("BROKEN{", encoding="utf-8")

    ok, issues = validate_artifacts(d)
    assert ok is False
    assert any("unreadable_json" in i and "exception_budget" in i for i in issues)


def test_schema_mismatch(tmp_path: Path) -> None:
    """Schema version in file differs from index's declared version -> schema_mismatch."""
    from mesh_cli.artifacts_validate import validate_artifacts

    d = tmp_path / "artifacts"
    _make_minimal_bundle(d)
    # Write exception_budget with schema_version=99 (index says 1)
    _write(d / "exception_budget.json", {"schema_version": 99, "ok": True})

    ok, issues = validate_artifacts(d)
    assert ok is False
    assert any("schema_mismatch" in i and "exception_budget" in i for i in issues)
    assert any("expected 1 got 99" in i for i in issues)


def test_missing_schema_version(tmp_path: Path) -> None:
    """File lacks schema_version but index declares one -> missing_schema_version."""
    from mesh_cli.artifacts_validate import validate_artifacts

    d = tmp_path / "artifacts"
    _make_minimal_bundle(d)
    # Write exception_budget without schema_version (index expects 1)
    _write(d / "exception_budget.json", {"ok": True})

    ok, issues = validate_artifacts(d)
    assert ok is False
    assert any("missing_schema_version" in i and "exception_budget" in i for i in issues)


def test_determinism(tmp_path: Path) -> None:
    """Two runs produce identical issues lists."""
    from mesh_cli.artifacts_validate import validate_artifacts

    d = tmp_path / "artifacts"
    _make_minimal_bundle(d)
    # Introduce a few errors for non-trivial output
    (d / "exception_budget.json").write_text("BAD", encoding="utf-8")

    _, issues1 = validate_artifacts(d)
    _, issues2 = validate_artifacts(d)
    assert issues1 == issues2


def test_path_normalization_strips_prefix(tmp_path: Path) -> None:
    """Written values like 'artifacts/foo.json' resolve inside the dir."""
    from mesh_cli.artifacts_validate import _normalize_written_path

    assert _normalize_written_path("artifacts/foo.json") == "foo.json"
    assert _normalize_written_path("foo.json") == "foo.json"
    assert _normalize_written_path("artifacts/sub/bar.json") == "sub/bar.json"


def test_validate_artifacts_accepts_index_paths_prefixed_with_artifacts_dir_name(tmp_path: Path) -> None:
    """Paths like artifacts/<bundle_dir>/file.json still resolve against artifacts dir."""
    from mesh_cli.artifacts_validate import validate_artifacts

    d = tmp_path / "artifacts_preflight_1"
    _make_minimal_bundle(d)
    index_path = d / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    written = index.get("written", {})
    generated = index.get("generated_files", [])
    assert isinstance(written, dict)
    assert isinstance(generated, list)

    bundle_name = d.name
    for key, value in list(written.items()):
        if isinstance(value, str):
            written[key] = f"artifacts/{bundle_name}/" + value.replace("\\", "/").split("/")[-1]
    index["generated_files"] = sorted(
        f"artifacts/{bundle_name}/" + str(v).replace("\\", "/").split("/")[-1]
        for v in generated
        if isinstance(v, str)
    )
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, issues = validate_artifacts(d)
    assert ok is True
    assert issues == []


def test_null_written_values_skipped(tmp_path: Path) -> None:
    """Null written values do not trigger missing_file checks."""
    from mesh_cli.artifacts_validate import validate_artifacts

    d = tmp_path / "artifacts"
    _make_minimal_bundle(d)

    ok, issues = validate_artifacts(d)
    assert ok is True
    # authoring_trace is null in our fixture — should not appear in issues
    assert not any("authoring_trace" in i for i in issues)


# ---------------------------------------------------------------------------
# CLI handler tests
# ---------------------------------------------------------------------------


def test_cli_success_exit_0(tmp_path: Path, capsys) -> None:
    """Handler returns 0 and prints 'ok' for valid bundle."""
    import argparse

    from mesh_cli.artifacts_validate import _handle_artifacts_validate

    d = tmp_path / "artifacts"
    _make_minimal_bundle(d)

    args = argparse.Namespace(artifacts=str(d))
    code = _handle_artifacts_validate(args)
    out = capsys.readouterr().out

    assert code == 0
    assert "artifacts-validate: ok" in out


def test_cli_failure_exit_2(tmp_path: Path, capsys) -> None:
    """Handler returns 2 and prints FAILED for invalid bundle."""
    import argparse

    from mesh_cli.artifacts_validate import _handle_artifacts_validate

    d = tmp_path / "empty"
    d.mkdir()

    args = argparse.Namespace(artifacts=str(d))
    code = _handle_artifacts_validate(args)
    out = capsys.readouterr().out

    assert code == 2
    assert "FAILED" in out
    assert "missing_index" in out


def test_cli_reports_all_issues(tmp_path: Path, capsys) -> None:
    """Handler reports multiple issues, not just the first."""
    import argparse

    from mesh_cli.artifacts_validate import _handle_artifacts_validate

    d = tmp_path / "artifacts"
    _make_minimal_bundle(d)
    (d / "exception_budget.json").unlink()
    (d / "verify_all_summary.json").write_text("BROKEN", encoding="utf-8")

    args = argparse.Namespace(artifacts=str(d))
    code = _handle_artifacts_validate(args)
    out = capsys.readouterr().out

    assert code == 2
    # Should have both missing_file and unreadable_json
    lines = out.strip().split("\n")
    bullet_lines = [line for line in lines if line.strip().startswith("- ")]
    assert len(bullet_lines) >= 2


def test_non_json_written_artifact_is_existence_only(tmp_path: Path) -> None:
    """Markdown artifacts should not be parsed as JSON."""
    from mesh_cli.artifacts_validate import validate_artifacts

    d = tmp_path / "artifacts"
    _make_minimal_bundle(d)
    (d / "release_notes.md").write_text("# notes\n", encoding="utf-8")
    index_path = d / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    written = index.get("written", {})
    assert isinstance(written, dict)
    written["release_notes_md"] = "artifacts/release_notes.md"
    index_path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ok, issues = validate_artifacts(d)
    assert ok is True
    assert issues == []
