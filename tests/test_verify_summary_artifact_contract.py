from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mesh_cli.verify import (
    _build_verify_summary_payload,
    _build_verify_summary_text,
    _write_verify_summary_artifacts,
)

pytestmark = [pytest.mark.fast]

def test_verify_summary_payload_schema_and_deterministic_order(tmp_path: Path) -> None:
    steps: list[dict[str, Any]] = [
        {"name": "verify-demo", "ok": True, "code": 0, "error": "", "artifact": None},
        {"name": "mypy-gate", "ok": False, "code": 2, "error": "skipped: previous step failed", "artifact": None},
        {"name": "player-package-gate", "ok": True, "code": 0, "error": "", "artifact": "artifacts/player_pkg/package_check.json"},
    ]
    artifacts_written: dict[str, str | None] = {
        "player_package_manifest": "artifacts/player_pkg/manifest.json",
        "player_package_check": "artifacts/player_pkg/package_check.json",
        "player_package_runtime_smoke": "artifacts/player_pkg/runtime_smoke.json",
        "player_package_runtime_diagnostics_snapshot": "artifacts/player_pkg/runtime_diagnostics_snapshot.json",
        "web_smoke": "artifacts/web_smoke.json",
        "perf_compare": "artifacts/perf_compare.json",
        "swallow_scan": "artifacts/swallow_scan.json",
        "runtime_smoke": "artifacts/runtime_smoke.json",
        "runtime_diagnostics_snapshot": "artifacts/runtime_diagnostics_snapshot.json",
        "verify_report": "artifacts/verify_report.json",
        "swallowed_exceptions": "artifacts/swallowed_exceptions.json",
        "shadow_backend": "artifacts/shadow_backend.json",
    }

    payload = _build_verify_summary_payload(
        overall_ok=False,
        steps=steps,
        artifacts_written=artifacts_written,
    )

    assert list(payload.keys()) == ["schema_version", "ok", "steps", "key_artifacts", "diagnostics"]
    assert payload["schema_version"] == 1
    assert payload["ok"] is False

    step_rows = payload["steps"]
    assert isinstance(step_rows, list)
    assert [row["name"] for row in step_rows] == ["verify-demo", "mypy-gate", "player-package-gate"]
    assert [row["skipped"] for row in step_rows] == [False, True, False]
    assert step_rows[2]["artifact"] == "artifacts/player_pkg/package_check.json"

    key_artifacts = payload["key_artifacts"]
    assert isinstance(key_artifacts, dict)
    assert list(key_artifacts.keys()) == [
        "player_pkg_manifest",
        "player_pkg_check",
        "player_pkg_runtime_smoke",
        "player_pkg_runtime_diagnostics_snapshot",
        "web_smoke",
        "perf_compare",
        "swallow_scan",
        "runtime_smoke",
        "runtime_diagnostics_snapshot",
    ]
    assert key_artifacts["player_pkg_manifest"] == "artifacts/player_pkg/manifest.json"
    assert key_artifacts["web_smoke"] == "artifacts/web_smoke.json"
    assert key_artifacts["runtime_smoke"] == "artifacts/runtime_smoke.json"

    diagnostics = payload["diagnostics"]
    assert isinstance(diagnostics, dict)
    assert list(diagnostics.keys()) == ["verify_report", "swallowed_exceptions", "shadow_backend"]


def test_verify_summary_text_and_files_are_greppable(tmp_path: Path) -> None:
    payload: dict[str, object] = {
        "schema_version": 1,
        "ok": True,
        "steps": [{"name": "verify-demo", "ok": True, "skipped": False}],
        "key_artifacts": {
            "player_pkg_manifest": "artifacts/player_pkg/manifest.json",
            "player_pkg_check": "artifacts/player_pkg/package_check.json",
            "player_pkg_runtime_smoke": "artifacts/player_pkg/runtime_smoke.json",
            "player_pkg_runtime_diagnostics_snapshot": "artifacts/player_pkg/runtime_diagnostics_snapshot.json",
            "web_smoke": None,
            "perf_compare": "artifacts/perf_compare.json",
            "swallow_scan": "artifacts/swallow_scan.json",
            "runtime_smoke": None,
            "runtime_diagnostics_snapshot": "artifacts/runtime_diagnostics_snapshot.json",
        },
        "diagnostics": {
            "verify_report": "artifacts/verify_report.json",
            "swallowed_exceptions": "artifacts/swallowed_exceptions.json",
            "shadow_backend": "artifacts/shadow_backend.json",
        },
    }

    text = _build_verify_summary_text(payload)
    assert "VERIFY_SUMMARY_OK: true" in text
    assert "VERIFY_STEP: verify-demo ok=true skipped=false artifact=-" in text
    assert "VERIFY_ARTIFACT: perf_compare artifacts/perf_compare.json" in text
    assert "VERIFY_ARTIFACT: runtime_diagnostics_snapshot artifacts/runtime_diagnostics_snapshot.json" in text
    assert "VERIFY_DIAGNOSTIC: verify_report artifacts/verify_report.json" in text

    _write_verify_summary_artifacts(tmp_path, payload)
    summary_json = tmp_path / "verify_summary.json"
    summary_txt = tmp_path / "verify_summary.txt"
    assert summary_json.is_file()
    assert summary_txt.is_file()
    loaded = json.loads(summary_json.read_text(encoding="utf-8"))
    assert loaded == payload
    assert summary_txt.read_text(encoding="utf-8").startswith("VERIFY_SUMMARY_OK: true\n")
