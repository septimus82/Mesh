from __future__ import annotations

import pytest

from mesh_cli.release_contract import validate_release_report_v1


def test_release_contract_report_schema_v1_rejects_bad_types() -> None:
    bad_report = {
        "schema_version": 1,
        "repo_root": "/repo",
        "artifacts_dir": None,
        "steps": [
            {
                "name": "pack-validate",
                "ok": True,
                "exit_code": "0",
                "log_path": None,
            }
        ],
        "summary": {"ok": False, "failed_step": "pack-validate"},
        "counts": {"presets_validated": None, "content_files_checked": None, "errors": None},
    }

    with pytest.raises(ValueError, match="exit_code must be int"):
        validate_release_report_v1(bad_report)
