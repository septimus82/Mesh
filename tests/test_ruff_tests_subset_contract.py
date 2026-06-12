from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]

_REPO_ROOT = Path(__file__).resolve().parent.parent
_RUFF_RULES = "F401,F821,F841,B006,B007,B011,B018,E722"
_RUFF_TARGETS = [
    "tests/test_verify_step_budget_guard.py",
    "tests/test_verify_pipeline_inner_fallback_contract.py",
    "tests/test_verify_demo_command.py",
    "tests/test_verify_demo_failure_diagnostics.py",
    "tests/test_pipeline_lighting_no_silent_pass_contract.py",
    "tests/test_verify_summary_artifact_contract.py",
    "tests/test_verify_all_artifact_index.py",
    "tests/test_verify_all_report_json_artifact.py",
    "tests/test_verify_step_durations_artifact.py",
    "tests/test_verify_all_artifacts_json_valid.py",
    "tests/test_verify_all_ci_bundle_flag.py",
    "tests/test_verify_all_report_flag.py",
    "tests/test_verify_report_command.py",
    "tests/test_verify_required_metrics_contract.py",
    "tests/test_verify_budget_metrics_contract.py",
    "tests/test_verify_authoring_trace_artifact.py",
    "tests/test_verify_release_notes_artifacts.py",
    "tests/test_verify_pytest_fast_budget_diagnostic.py",
    "tests/test_verify_exception_budget_guard.py",
    "tests/test_verify_authoring_trace_budget_guard.py",
    "tests/test_verify_local_command_contract.py",
    "tests/test_verify_all_steps_are_canonical.py",
    "tests/test_cli_verify_demo_parser.py",
]


def test_ruff_bugcatching_subset_contract() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            *_RUFF_TARGETS,
            "--select",
            _RUFF_RULES,
            "--output-format",
            "concise",
        ],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        "Ruff bug-catching test subset regression.\n"
        f"rules={_RUFF_RULES}\n"
        f"targets={', '.join(_RUFF_TARGETS)}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
