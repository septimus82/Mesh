"""F13-B (#422): CI's release bundle reuses the verify-all its verify step ran, only on proof; otherwise it runs one.

The bundle's release check ran a whole second verify-all on the same checkout (about 3 minutes of Windows CI per run).
Now ``mesh release bundle --reuse-verify-all artifacts`` takes the reports of the verify-all that wrote
``verify_all_evidence.json`` there, if that run passed every step on this exact clean commit with the same versions and
``MESH_*`` environment and its reports are unchanged; anything else is refused with the reason, recorded, and the
release check runs verify-all itself. The rest of the release check (asset audit, export build, debug bundle) always
runs. Here "now" (commit, clean tree, versions, environment) is a fixed record, so no test depends on this checkout.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

import mesh_cli.release as release
from mesh_cli import verify_reuse
from mesh_cli.release_check_pipeline import _write_deterministic_verify_all_summary
from mesh_cli.verify_steps import STEP_ORDER

pytestmark = pytest.mark.fast
NOW = {"git_commit": "c" * 40, "git_dirty": False, "tool_version": "1.0.0", "python": "3.11.9", "platform": "win32",
       "env": {"MESH_CI_SEED": "123"}}
REPORTS = {"verify_all_summary.json": None, "verify_summary.txt": "verify-all: OK\n",
           "verify_step_durations.json": '{"steps": []}\n', "reports/doctor_assets.json": '{"ok": true}\n'}


@pytest.fixture
def now(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The checkout and runtime as ``verify_reuse.state`` reports them; a test changes it to make "now" differ."""
    current: dict[str, Any] = json.loads(json.dumps(NOW))
    monkeypatch.setattr(verify_reuse, "state", lambda _root: json.loads(json.dumps(current)))
    return current


def _summary() -> dict[str, Any]:
    return {"ok": True, "steps": [{"name": n, "ok": True, "code": 0, "error": "", "artifact": None} for n in STEP_ORDER],
            "pytest_fast": {"wall_seconds": 93.2, "slowest10_seconds": 4.1, "slowest_entries_seconds": 9.9},
            "artifacts": {"dir": "artifacts", "written": {}}}


def _write_reports(folder: Path, summary: dict[str, Any]) -> None:
    """What a verify-all leaves in its folder (a stand-in of the same shape)."""
    for rel, text in REPORTS.items():
        path = folder / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n" if text is None else text, encoding="utf-8")


def _ci_verify_all(source: Path, **evidence: Any) -> Path:
    """CI's verify-all (--ci-bundle --release-notes-artifact --reuse-evidence) in ``source``: its reports, CI's extras,
    then its evidence; ``evidence`` overrides what it records (exit_code, ok, steps, selection...)."""
    summary = _summary()
    _write_reports(source, summary)
    for extra in verify_reuse.NOT_COPIED:
        (source / extra).write_text("{}\n", encoding="utf-8")
    args = argparse.Namespace(ci_bundle=True, release_notes_artifact=True, pytest_args=[], skip_web_smoke=False)
    verify_reuse.write_evidence(source, repo_root=source.parent, before=json.loads(json.dumps(NOW)),
                                exit_code=evidence.pop("exit_code", 0), payload=summary, args=args)
    if evidence:
        path = source / verify_reuse.EVIDENCE
        path.write_text(json.dumps({**json.loads(path.read_text(encoding="utf-8")), **evidence}), encoding="utf-8")
    return source


def _evidence(source: Path) -> dict[str, Any]:
    found: dict[str, Any] = json.loads((source / verify_reuse.EVIDENCE).read_text(encoding="utf-8"))
    return found


def _rewrite_evidence(source: Path, change: Callable[[dict[str, Any]], None]) -> None:
    data = _evidence(source)
    change(data)
    (source / verify_reuse.EVIDENCE).write_text(json.dumps(data), encoding="utf-8")


# --------------------------------------------------------------------- the decision

def test_a_passing_run_on_this_clean_commit_is_reused_with_a_record(tmp_path: Path, now: dict[str, Any]) -> None:
    source = _ci_verify_all(tmp_path / "artifacts")
    release_dir = tmp_path / "release"
    release_dir.mkdir()
    outputs = verify_reuse.reuse(source, release_dir, repo_root=tmp_path, deterministic=True)
    assert outputs is not None and outputs["verify_all_ok"] is True and outputs["verify_all_reused_from"] == "artifacts"
    copied = sorted(p.relative_to(release_dir).as_posix() for p in release_dir.rglob("*") if p.is_file())
    assert copied == sorted([*REPORTS, verify_reuse.RECORD]), "the reports, not CI's extras or the evidence"
    for rel in ("verify_summary.txt", "reports/doctor_assets.json"):
        assert (release_dir / rel).read_bytes() == (source / rel).read_bytes()
    summary = json.loads((release_dir / "verify_all_summary.json").read_text(encoding="utf-8"))
    assert summary["pytest_fast"]["wall_seconds"] == 0.0, "normalized as the release check's own deterministic summary"
    record = json.loads((release_dir / verify_reuse.RECORD).read_text(encoding="utf-8"))
    assert record["reused"] is True and record["commit"] == NOW["git_commit"] and record["files_copied"] == len(REPORTS)
    assert record["not_copied"] == sorted(verify_reuse.NOT_COPIED) and "every file's SHA-256" in record["checked"]


def _refuse(case: str, source: Path, now: dict[str, Any]) -> None:
    """Make the recorded run, its reports or "now" not good enough, as ``case`` says."""
    if case == "no evidence":
        (source / verify_reuse.EVIDENCE).unlink()
    elif case == "unreadable evidence":
        (source / verify_reuse.EVIDENCE).write_text("{", encoding="utf-8")
    elif case == "unknown format":
        _rewrite_evidence(source, lambda e: e.update(schema=2))
    elif case == "failed":
        _rewrite_evidence(source, lambda e: e.update(exit_code=1, ok=False))
    elif case == "a step failed":
        _rewrite_evidence(source, lambda e: e["steps"][3].update(code=1, error="boom"))
    elif case == "a step skipped":
        _rewrite_evidence(source, lambda e: e["steps"][-1].update(code=2, error="skipped: previous step failed"))
    elif case == "steps missing":
        _rewrite_evidence(source, lambda e: e["steps"].pop())
    elif case == "pytest arguments":
        _rewrite_evidence(source, lambda e: e["selection"].update(pytest_args=["-k", "smoke"]))
    elif case == "web smoke skipped":
        _rewrite_evidence(source, lambda e: e["selection"].update(skip_web_smoke=True))
    elif case == "another commit now":
        now["git_commit"] = "d" * 40
    elif case == "commit moved during the run":
        _rewrite_evidence(source, lambda e: e["after"].update(git_commit="d" * 40))
    elif case == "dirty before":
        _rewrite_evidence(source, lambda e: e["before"].update(git_dirty=True))
    elif case == "dirty now":
        now["git_dirty"] = True
    elif case == "unknown git state":
        now["git_commit"] = None
    elif case == "another tool version":
        now["tool_version"] = "1.0.1"
    elif case == "another python":
        now["python"] = "3.12.1"
    elif case == "another environment":
        now["env"]["MESH_GL_SOFTWARE"] = "1"
    elif case == "weaker budgets then":
        now["env"]["MESH_VERIFY_BUDGET_ENFORCE"] = "1"
    elif case == "report changed":
        (source / "reports/doctor_assets.json").write_text('{"ok": false}\n', encoding="utf-8")
    elif case == "report missing":
        (source / "verify_summary.txt").unlink()
    elif case == "path outside":
        _rewrite_evidence(source, lambda e: e["files"].update({"../elsewhere.json": "0" * 64}))
    elif case == "summary disagrees":
        summary = _summary() | {"ok": False}
        (source / "verify_all_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                                                        encoding="utf-8")
        _rewrite_evidence(source, lambda e: e["files"].update(
            {"verify_all_summary.json": verify_reuse._sha256(source / "verify_all_summary.json")}))
    else:
        raise AssertionError(case)


REFUSALS = {
    "no evidence": "no verify_all_evidence.json", "unreadable evidence": "can't be read",
    "unknown format": "unknown format", "failed": "didn't pass", "a step failed": "didn't pass or didn't run",
    "a step skipped": "didn't pass or didn't run", "steps missing": "complete list",
    "pytest arguments": "narrowed selection", "web smoke skipped": "narrowed selection",
    "another commit now": "this is dddd", "commit moved during the run": "this is cccc", "dirty before": "clean",
    "dirty now": "clean", "unknown git state": "this is None", "another tool version": "tool_version differs",
    "another python": "python differs", "another environment": "MESH_GL_SOFTWARE",
    "weaker budgets then": "weaker", "report changed": "doctor_assets.json is missing or changed",
    "report missing": "verify_summary.txt is missing or changed", "path outside": "outside its folder",
    "summary disagrees": "same passing run",
}


@pytest.mark.parametrize("case", sorted(REFUSALS))
def test_anything_short_of_proof_is_refused_with_the_reason_and_nothing_copied(tmp_path: Path, now: dict[str, Any],
                                                                               case: str) -> None:
    source = _ci_verify_all(tmp_path / "artifacts")
    _refuse(case, source, now)
    evidence, why = verify_reuse.check(source, tmp_path)
    assert evidence is None and REFUSALS[case] in why, why
    release_dir = tmp_path / "release"
    release_dir.mkdir()
    assert verify_reuse.reuse(source, release_dir, repo_root=tmp_path, deterministic=True) is None
    assert [p.name for p in release_dir.iterdir()] == [verify_reuse.RECORD], "only the record of why"
    record = json.loads((release_dir / verify_reuse.RECORD).read_text(encoding="utf-8"))
    assert record == {"reused": False, "source": "artifacts", "reason": why}


def test_a_report_changing_while_it_is_copied_is_refused_and_the_copies_removed(
        tmp_path: Path, now: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    source = _ci_verify_all(tmp_path / "artifacts")
    real_copy = verify_reuse.shutil.copyfile

    def copy_then_tamper(src: Any, dst: Any) -> Any:
        result = real_copy(src, dst)
        if Path(dst).name == "verify_summary.txt":
            Path(dst).write_text("tampered\n", encoding="utf-8")
        return result

    monkeypatch.setattr(verify_reuse.shutil, "copyfile", copy_then_tamper)
    release_dir = tmp_path / "release"
    release_dir.mkdir()
    assert verify_reuse.reuse(source, release_dir, repo_root=tmp_path, deterministic=True) is None
    assert [p.name for p in release_dir.iterdir()] == [verify_reuse.RECORD]
    assert "changed while it was being copied" in json.loads((release_dir / verify_reuse.RECORD).read_text())["reason"]


def test_the_evidence_records_what_ran_and_never_decides(tmp_path: Path, now: dict[str, Any]) -> None:
    """A failed run's evidence says so (exit code, steps); it isn't turned into a pass anywhere."""
    source = tmp_path / "artifacts"
    summary = _summary() | {"ok": False}
    summary["steps"][2] = {**summary["steps"][2], "ok": False, "code": 1, "error": "boom"}
    _write_reports(source, summary)
    verify_reuse.write_evidence(source, repo_root=tmp_path, before=json.loads(json.dumps(NOW)), exit_code=1,
                                payload=summary, args=argparse.Namespace())
    evidence = _evidence(source)
    assert evidence["exit_code"] == 1 and evidence["ok"] is False and evidence["steps"][2]["code"] == 1
    assert set(evidence["files"]) == set(REPORTS) and verify_reuse.EVIDENCE not in evidence["files"]
    assert "didn't pass" in verify_reuse.check(source, tmp_path)[1]


# --------------------------------------------------------------------- the release check

@pytest.fixture
def steps(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """The release check's four steps replaced by recorders (the real ones run verify-all, an export, a debug
    bundle); verify-all writes the same reports as CI's, deterministically, as the real ``_run_verify_all``."""
    calls: dict[str, list[str]] = {"verify-all": [], "asset-audit": [], "export-build": [], "debug-bundle": []}

    def verify_all(repo_root: Path, artifacts_dir: Path, *, deterministic: bool = False) -> tuple[int, dict[str, Any]]:
        calls["verify-all"].append(str(artifacts_dir))
        _write_reports(artifacts_dir, _summary())
        _write_deterministic_verify_all_summary(artifacts_dir, _summary())
        return 0, {"verify_all_ok": True, "verify_all_summary": (artifacts_dir / "verify_all_summary.json").as_posix()}

    def recorder(name: str) -> Callable[..., tuple[int, dict[str, Any]]]:
        def run(_repo_root: Path, out: Path, **_kw: Any) -> tuple[int, dict[str, Any]]:
            calls[name].append(str(out))
            return 0, {}
        return run

    monkeypatch.setattr(release, "_run_verify_all", verify_all)
    monkeypatch.setattr(release, "_run_assets_audit", recorder("asset-audit"))
    monkeypatch.setattr(release, "_run_export_build", recorder("export-build"))
    monkeypatch.setattr(release, "_run_debug_bundle", recorder("debug-bundle"))
    return calls


def _release_check(release_dir: Path, reuse_from: Path | None) -> int:
    return release._handle_check(argparse.Namespace(
        command="release", release_command="check", repo_root=".", artifacts=str(release_dir), report=None,
        summary=None, deterministic=True, quiet=True, reuse_verify_all=str(reuse_from) if reuse_from else None))


def test_the_release_check_reuses_verify_all_and_still_runs_its_other_steps(tmp_path: Path, now: dict[str, Any],
                                                                            steps: dict[str, list[str]]) -> None:
    source = _ci_verify_all(tmp_path / "artifacts")
    assert _release_check(tmp_path / "release", source) == 0
    assert steps["verify-all"] == [], "not run a second time"
    assert all(len(steps[name]) == 1 for name in ("asset-audit", "export-build", "debug-bundle"))
    report = json.loads((tmp_path / "release/release_report.json").read_text(encoding="utf-8"))
    verify_step = next(s for s in report["steps"] if s["name"] == "verify-all")
    assert verify_step["ok"] and verify_step["outputs"]["verify_all_reused_from"] == "artifacts"


def test_refused_evidence_means_the_release_check_runs_verify_all_itself(tmp_path: Path, now: dict[str, Any],
                                                                         steps: dict[str, list[str]]) -> None:
    source = _ci_verify_all(tmp_path / "artifacts", exit_code=1, ok=False)
    assert _release_check(tmp_path / "release", source) == 0
    assert steps["verify-all"] == [str(tmp_path / "release")], "run here, as before"
    record = json.loads((tmp_path / "release" / verify_reuse.RECORD).read_text(encoding="utf-8"))
    assert record["reused"] is False and "didn't pass" in record["reason"]


@pytest.mark.parametrize("failing", ["asset-audit", "export-build", "debug-bundle"])
def test_a_failing_audit_export_or_debug_step_still_fails_a_reusing_release_check(
        tmp_path: Path, now: dict[str, Any], steps: dict[str, list[str]], monkeypatch: pytest.MonkeyPatch,
        failing: str) -> None:
    name = {"asset-audit": "_run_assets_audit", "export-build": "_run_export_build",
            "debug-bundle": "_run_debug_bundle"}[failing]
    monkeypatch.setattr(release, name, lambda *_a, **_k: (1, {}))
    assert _release_check(tmp_path / "release", _ci_verify_all(tmp_path / "artifacts")) != 0
    report = json.loads((tmp_path / "release/release_report.json").read_text(encoding="utf-8"))
    assert report["summary"]["failed_step"] == failing and steps["verify-all"] == []


def test_reused_and_rerun_release_reports_differ_only_where_documented(tmp_path: Path, now: dict[str, Any],
                                                                       steps: dict[str, list[str]]) -> None:
    """The same reports either way, byte for byte, apart from the reuse record and the release report's note of
    where verify-all came from; CI's extras (index, report, overlay perf, release notes) aren't copied."""
    rerun_dir, reused_dir = tmp_path / "a" / "release", tmp_path / "b" / "release"
    assert _release_check(rerun_dir, None) == 0
    assert _release_check(reused_dir, _ci_verify_all(tmp_path / "artifacts")) == 0
    rerun = {p.relative_to(rerun_dir).as_posix(): p.read_bytes() for p in rerun_dir.rglob("*") if p.is_file()}
    reused = {p.relative_to(reused_dir).as_posix(): p.read_bytes() for p in reused_dir.rglob("*") if p.is_file()}
    assert set(reused) == set(rerun) | {verify_reuse.RECORD}
    assert sorted(rel for rel in rerun if rerun[rel] != reused[rel]) == ["release_report.json"]
    rerun_report, reused_report = (json.loads(d["release_report.json"]) for d in (rerun, reused))
    reused_step = next(s for s in reused_report["steps"] if s["name"] == "verify-all")
    assert reused_step["outputs"].pop("verify_all_reused_from") == "artifacts"
    assert reused_report == rerun_report, "the only difference: where verify-all's reports came from"


# --------------------------------------------------------------------- verify-all writes the evidence

@pytest.mark.parametrize("asked", [False, True])
def test_verify_all_writes_its_evidence_only_when_asked_and_last(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                 capsys: pytest.CaptureFixture[str], asked: bool) -> None:
    import mesh_cli.verify as verify

    order: list[str] = []
    def state(_root: Path) -> dict[str, Any]:
        order.append("state")
        current: dict[str, Any] = json.loads(json.dumps(NOW))
        return current

    monkeypatch.setattr(verify_reuse, "state", state)

    def build(args: argparse.Namespace) -> tuple[dict[str, Any], int]:
        order.append("verify-all")
        _write_reports(Path(args.artifacts), _summary())
        return _summary(), 0

    monkeypatch.setattr(verify, "_build_verify_all_payload", build)
    artifacts = tmp_path / "artifacts"
    code = verify._handle_verify_all(argparse.Namespace(artifacts=str(artifacts), reuse_evidence=asked, pytest_args=[],
                                                        skip_web_smoke=False, ci_bundle=False))
    capsys.readouterr()
    assert code == 0 and (artifacts / verify_reuse.EVIDENCE).is_file() is asked
    if asked:
        assert order == ["state", "verify-all", "state"], "the checkout recorded before the run and after it"
        evidence = _evidence(artifacts)
        assert evidence["exit_code"] == 0 and set(evidence["files"]) == set(REPORTS) and evidence["before"] == NOW
    else:
        assert order == ["verify-all"]
