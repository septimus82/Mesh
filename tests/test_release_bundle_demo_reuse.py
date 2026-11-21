"""H2-F13: a release bundle runs ``release check`` (a whole verify-all) once, not twice.

The bundle's pipeline is release-check, then demo-run; the demo pipeline's own first step is the same release check
(same checkout, same arguments, same process). The bundle's demo now takes the reports of the bundle's release check
(copied to demo/release/) instead of running it again; ``mesh demo pipeline`` on its own still runs it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.fast


@pytest.fixture()
def checks(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """``release check`` replaced by a recorder that writes a report, like the real one, into its artifacts folder."""
    import mesh_cli.demo as demo
    import mesh_cli.release as release

    calls: list[str] = []

    def fake_check(args: Any) -> int:
        calls.append(str(args.artifacts))
        out = Path(args.artifacts)
        (out / "verify_all_summary.json").write_text(json.dumps({"ok": True, "run": len(calls)}) + "\n", encoding="utf-8")
        (out / "nested").mkdir(exist_ok=True)
        (out / "nested" / "asset_audit.json").write_text("{}\n", encoding="utf-8")
        return 0

    def demo_step_after(out_dir: Path, _seed: int, _campaign: str) -> tuple[int, dict[str, Any]]:  # (cheap stand-in)
        return (0 if (out_dir / "release" / "verify_all_summary.json").is_file() else 1), {}

    monkeypatch.setattr(release, "_handle_check", fake_check)
    monkeypatch.setattr(demo, "PIPELINE", [("release-check", demo._step_release_check), ("new-game", demo_step_after)])
    return calls


def test_the_bundle_runs_release_check_once_and_the_demo_gets_its_reports(tmp_path: Path, checks: list[str]) -> None:
    from mesh_cli import release_bundle

    assert release_bundle._step_release_check(tmp_path, 123, "demo")[0] == 0
    code, outputs = release_bundle._step_demo_run(tmp_path, 123, "demo")
    assert code == 0 and outputs == {"dir": "demo/"}
    assert len(checks) == 1, "release check ran once, for the bundle"
    for rel in ("verify_all_summary.json", "nested/asset_audit.json"):
        assert (tmp_path / "demo/release" / rel).read_bytes() == (tmp_path / "release" / rel).read_bytes()
    report = json.loads((tmp_path / "demo/demo_report.json").read_text(encoding="utf-8"))
    steps = {s["name"]: s for s in report["steps"]}
    assert steps["release-check"]["ok"] and steps["release-check"]["outputs"]["reused_from"] == "release/"
    assert steps["new-game"]["ok"], "the demo's later steps still run, and see the release reports"


def test_the_demo_pipeline_on_its_own_still_runs_its_release_check(tmp_path: Path, checks: list[str]) -> None:
    from mesh_cli.demo import run_demo

    code, _report = run_demo(out_dir=tmp_path / "demo", seed=123, campaign="demo", quiet=True)
    assert code == 0 and len(checks) == 1 and checks[0].endswith("release")


def test_links_in_the_release_reports_are_not_copied_as_folders(tmp_path: Path, checks: list[str]) -> None:
    """pytest leaves "<name>current" links to its temp folders; the bundle's file scan skips them, so the demo copy
    does too (copied as folders they duplicated their files in the zip: 25 files in CI run 40963872558)."""
    import os

    from mesh_cli import release_bundle

    release_bundle._step_release_check(tmp_path, 123, "demo")
    try:
        os.symlink(tmp_path / "release" / "nested", tmp_path / "release" / "nestedcurrent", target_is_directory=True)
    except OSError:
        pytest.skip("this system can't make directory links (Windows without the privilege)")
    release_bundle._step_demo_run(tmp_path, 123, "demo")
    copied = sorted(p.relative_to(tmp_path / "demo/release").as_posix() for p in (tmp_path / "demo/release").rglob("*"))
    assert copied == ["nested", "nested/asset_audit.json", "verify_all_summary.json"]
