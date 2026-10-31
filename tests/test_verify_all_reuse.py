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

from mesh_cli import verify_reuse
from mesh_cli.verify_steps import STEP_ORDER

pytestmark = pytest.mark.fast
NOW = {"git_commit": "c" * 40, "git_dirty": False, "tool_version": "1.0.0", "python": "3.11.9", "platform": "win32",
       "env": {"MESH_CI_SEED": "123"}}
PACKAGE_FILES = ("config.json", "scenes/runtime_smoke_scene.json")  # (what its manifest lists, nested ones included)
NESTED = "player_pkg/scenes/runtime_smoke_scene.json"
SCRATCH_FILE = "verify_demo_pytest/pid4242-run0001/basetemp/test_scaffold0/config.json"
# What a verify-all leaves in its folder (a stand-in of the same shape): every named report, the player package as its
# manifest lists it, verify-demo's pytest scratch. None is the summary, written from the run's payload.
REPORTS: dict[str, str | None] = {
    **{rel: '{"ok": true}\n' for rel in verify_reuse.RELEASE_REPORTS},
    "verify_all_summary.json": None,
    "verify_summary.txt": "verify-all: OK\n",
    "player_pkg/manifest.json": json.dumps({"included_files": list(PACKAGE_FILES)}) + "\n",
    **{f"player_pkg/{rel}": "{}\n" for rel in PACKAGE_FILES},
    SCRATCH_FILE: "{}\n",
    "verify_demo_pytest/pid4242-run0001/cache/README.md": "pytest cache\n",
}


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
    """CI's verify-all (--ci-bundle --release-notes-artifact --reuse-evidence) in ``source``: the folder as it was
    (``snapshot``), its reports, CI's extras, then its evidence; ``evidence`` overrides what it records."""
    files_before = verify_reuse.snapshot(source)
    summary = _summary()
    _write_reports(source, summary)
    for extra in verify_reuse.NOT_COPIED:
        (source / extra).write_text("{}\n", encoding="utf-8")
    args = argparse.Namespace(ci_bundle=True, release_notes_artifact=True, pytest_args=[], skip_web_smoke=False)
    verify_reuse.write_evidence(source, repo_root=source.parent, before=json.loads(json.dumps(NOW)),
                                files_before=files_before, exit_code=evidence.pop("exit_code", 0), payload=summary,
                                args=args)
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
    for rel in ("verify_summary.txt", NESTED, SCRATCH_FILE):  # (named, nested package and dynamic scratch reports)
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
        _rewrite_evidence(source, lambda e: e.update(schema=1))  # (1 listed every file in the folder)
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
        (source / "doctor_assets.json").write_text('{"ok": false}\n', encoding="utf-8")
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
    verify_reuse.write_evidence(source, repo_root=tmp_path, before=json.loads(json.dumps(NOW)), files_before={}, exit_code=1,
                                payload=summary, args=argparse.Namespace())
    evidence = _evidence(source)
    assert evidence["exit_code"] == 1 and evidence["ok"] is False and evidence["steps"][2]["code"] == 1
    assert set(evidence["files"]) == set(REPORTS) and verify_reuse.EVIDENCE not in evidence["files"]
    assert "didn't pass" in verify_reuse.check(source, tmp_path)[1]


# --------------------------------------------------------------------- only what the run produced (review of 80e657f)

UNRELATED = {"old_release_notes.json": b'{"from": "an earlier run"}\n', "previous_bundle.zip": b"PK\x03\x04 old archive",
             "deep/nested/unexpected.txt": b"left here by something else\n"}


def _with_unrelated_files(source: Path) -> None:
    """``source`` already holding files before verify-all runs: unrelated ones, and a stale summary it will rewrite."""
    for rel, data in UNRELATED.items():
        (source / rel).parent.mkdir(parents=True, exist_ok=True)
        (source / rel).write_bytes(data)
    (source / "verify_all_summary.json").write_text('{"ok": false, "stale": true}\n', encoding="utf-8")


def test_files_already_in_the_folder_are_never_copied_only_what_the_run_produced(tmp_path: Path,
                                                                                  now: dict[str, Any]) -> None:
    source = tmp_path / "artifacts"
    _with_unrelated_files(source)
    _ci_verify_all(source)
    evidence = _evidence(source)
    assert sorted(evidence["untouched"]) == sorted(UNRELATED), "listed apart, never as the run's"
    assert not set(UNRELATED) & set(evidence["files"])
    assert set(REPORTS) <= set(evidence["files"]), "nested reports and the rewritten summary are the run's"
    release_dir = tmp_path / "release"
    release_dir.mkdir()
    assert verify_reuse.reuse(source, release_dir, repo_root=tmp_path, deterministic=True) is not None
    copied = sorted(p.relative_to(release_dir).as_posix() for p in release_dir.rglob("*") if p.is_file())
    assert copied == sorted([*REPORTS, verify_reuse.RECORD]), copied
    assert json.loads((release_dir / "verify_all_summary.json").read_text(encoding="utf-8"))["ok"] is True
    record = json.loads((release_dir / verify_reuse.RECORD).read_text(encoding="utf-8"))
    assert record["untouched_not_copied"] == len(UNRELATED)


def _fake_run_also_writing(source: Path, during: dict[str, bytes], *, without: tuple[str, ...] = ()) -> None:
    """CI's verify-all in ``source`` during which ``during`` appear too (something else writing there), and which
    doesn't produce ``without``: its evidence lists what changed during the run, as the real one would."""
    files_before = verify_reuse.snapshot(source)
    _write_reports(source, _summary())
    for rel in without:
        (source / rel).unlink()
    for rel, data in during.items():
        (source / rel).parent.mkdir(parents=True, exist_ok=True)
        (source / rel).write_bytes(data)
    verify_reuse.write_evidence(source, repo_root=source.parent, before=json.loads(json.dumps(NOW)),
                                files_before=files_before, exit_code=0, payload=_summary(),
                                args=argparse.Namespace(pytest_args=[], skip_web_smoke=False))


@pytest.mark.parametrize("stray", ["notes_from_another_tool.json", "player_pkg/not_in_its_manifest.dll",
                                   "verify_demo_pytest/left_here.txt", "web_build/extra.js", "deep/nested/new.txt"])
def test_an_unrelated_file_created_during_verification_refuses_the_reuse(tmp_path: Path, now: dict[str, Any],
                                                                        stray: str) -> None:
    """It changed during the run, so it's in the evidence with its hash; it still isn't a verification output (not a
    named report, not in the package's manifest, not verify-demo's scratch): reuse is refused and nothing copied."""
    source = tmp_path / "artifacts"
    _fake_run_also_writing(source, {stray: b"not a verification output\n"})
    assert stray in _evidence(source)["files"], "recorded as produced: changed during the run"
    evidence, why = verify_reuse.check(source, tmp_path)
    assert evidence is None and "aren't verification outputs" in why and stray in why, why
    release_dir = tmp_path / "release"
    release_dir.mkdir()
    assert verify_reuse.reuse(source, release_dir, repo_root=tmp_path, deterministic=True) is None
    assert [p.name for p in release_dir.iterdir()] == [verify_reuse.RECORD]


def test_schema_2_evidence_listing_an_unrelated_file_with_its_true_hash_cannot_package_it(tmp_path: Path,
                                                                                         now: dict[str, Any]) -> None:
    """Valid, current-format evidence naming a file that was only lying in the folder, with its correct SHA-256: the
    hash proves it's unchanged, not that verification produced it. Refused."""
    source = tmp_path / "artifacts"
    _with_unrelated_files(source)
    _ci_verify_all(source)
    _rewrite_evidence(source, lambda e: e["files"].update(
        {rel: verify_reuse._sha256(source / rel) for rel in UNRELATED}))
    assert _evidence(source)["schema"] == verify_reuse.SCHEMA == 2
    evidence, why = verify_reuse.check(source, tmp_path)
    assert evidence is None and "aren't verification outputs" in why, why
    release_dir = tmp_path / "release"
    release_dir.mkdir()
    assert verify_reuse.reuse(source, release_dir, repo_root=tmp_path, deterministic=True) is None
    assert not any((release_dir / rel).exists() for rel in UNRELATED)


@pytest.mark.parametrize("not_produced", ["doctor_assets.json", "web_build/index.html", NESTED,
                                          "player_pkg/package_check.json"])
def test_an_incomplete_report_set_refuses_the_reuse(tmp_path: Path, now: dict[str, Any], not_produced: str) -> None:
    """A named report, a web build file, a file the package's manifest lists, or the package's own record that the run
    didn't produce: the reuse would make a release missing it, so it's refused and verify-all runs."""
    source = tmp_path / "artifacts"
    _fake_run_also_writing(source, {}, without=(not_produced,))
    evidence, why = verify_reuse.check(source, tmp_path)
    assert evidence is None and "weren't produced" in why and not_produced in why, why


def test_the_package_is_known_only_from_its_own_readable_manifest(tmp_path: Path, now: dict[str, Any]) -> None:
    source = tmp_path / "artifacts"
    _fake_run_also_writing(source, {"player_pkg/manifest.json": b'{"included_files": ["../outside.json"]}\n'})
    assert "outside the package" in verify_reuse.check(source, tmp_path)[1]
    source = tmp_path / "again"
    _fake_run_also_writing(source, {"player_pkg/manifest.json": b"{"})
    assert "player_pkg/manifest.json can't be read" in verify_reuse.check(source, tmp_path)[1]


# --------------------------------------------------------------------- an interrupted copy (review of 80e657f)

def _failing_copy(monkeypatch: pytest.MonkeyPatch, *, at: str) -> None:
    """Copying ``at`` writes part of it, then fails (a full disk, a lost handle)."""
    real_copy = verify_reuse.shutil.copyfile

    def copy(src: Any, dst: Any) -> Any:
        if Path(dst).as_posix().endswith(at):
            Path(dst).write_bytes(Path(src).read_bytes()[:3])
            raise OSError(28, "No space left on device")
        return real_copy(src, dst)

    monkeypatch.setattr(verify_reuse.shutil, "copyfile", copy)


def test_an_interrupted_copy_is_undone_partial_file_and_folders_included(tmp_path: Path, now: dict[str, Any],
                                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    source = _ci_verify_all(tmp_path / "artifacts")
    _failing_copy(monkeypatch, at=NESTED)
    release_dir = tmp_path / "release"
    release_dir.mkdir()
    (release_dir / "already_here.txt").write_text("the release check's own\n", encoding="utf-8")
    assert verify_reuse.reuse(source, release_dir, repo_root=tmp_path, deterministic=True) is None
    assert sorted(p.name for p in release_dir.iterdir()) == ["already_here.txt", verify_reuse.RECORD]
    reason = json.loads((release_dir / verify_reuse.RECORD).read_text(encoding="utf-8"))["reason"]
    assert f"{NESTED} couldn't be copied" in reason and "No space left" in reason


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
