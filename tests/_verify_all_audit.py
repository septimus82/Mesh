"""The one ``verify-all`` of this checkout that the audit tests share (#422).

Fourteen test modules each ran ``mesh verify-all --artifacts <tmp> --no-index`` on the real checkout, 16 times in one
pytest process, to read one report each (stamp, brush, macro and room audits, the encounter coverage matrix, headroom
and audit). The command, the checkout and the stand-ins were the same every time, so the reports were too, and each
run cost a whole verify-all (mypy gate, both exception scans, every audit). ``run_once`` is that run, once; the
``verify_all_audit_artifacts`` fixture in ``tests/conftest.py`` gives its reports folder to every test that asks.

What the run does not do is what none of those tests did either: the demo, the replay suite, ``validate-all`` and the
asset doctor are stood in for (they have their own tests and their own verify-all steps in CI), and under pytest
verify-all skips its fast tier. Everything else runs for real, as ``verify-all`` runs it anywhere.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_once(artifacts_dir: Path) -> Path:
    """Run verify-all in this checkout, its reports into ``artifacts_dir``; the folder, or an error if it failed.

    The working directory and the stand-ins last for the run only."""
    import engine.tooling.asset_doctor as asset_doctor
    import mesh_cli

    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(REPO_ROOT)
        patch.setattr(mesh_cli.verify_demo, "run_verify_demo", lambda *_a, **_k: 0)
        patch.setattr(mesh_cli.replay_suite, "run_replay_suite",
                      lambda _folder: {"failed": 0, "passed": 1, "total": 1, "results": []})
        patch.setattr(mesh_cli.validate_all, "main", lambda _argv: 0)
        patch.setattr(asset_doctor, "doctor_assets",
                      lambda **_kwargs: {"ok": True, "errors": [], "warnings": [], "fixes": []})
        code = mesh_cli.main(["verify-all", "--artifacts", str(artifacts_dir), "--no-index"])
    if code != 0:
        raise AssertionError(f"verify-all failed in this checkout (exit code {code}): see its output above; every test "
                             "that reads its reports fails with it")
    return artifacts_dir
