"""verify-all runs once where once is enough (#422).

Two places could repeat a whole ``verify-all`` for nothing, and each is pinned here:

* **The audit tests.** Fourteen modules ran ``verify-all`` on this checkout 16 times in one pytest process to read
  one report each. They now share one run (``tests/_verify_all_audit.py``, the ``verify_all_audit_artifacts``
  fixture). Pinned: the shared run is one complete command with its stand-ins and working directory undone; a failed
  run fails every test that shares it; and no test function runs verify-all on this checkout itself.
* **The workflows.** Each job that promises a verify-all runs it once, and what follows it in the same job reuses it
  (the release bundle: H2/F13-B; the baseline update: ``--no-verify-all``). Pinned as a map of every workflow.

Headless stand-ins and text checks only: no verify-all runs here.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

import tests._verify_all_audit as shared

pytestmark = pytest.mark.fast

REPO_ROOT = Path(__file__).resolve().parents[1]
TESTS = REPO_ROOT / "tests"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
FIXTURE = "verify_all_audit_artifacts"
# The modules whose tests read the shared run's reports (16 tests): each used to run its own verify-all.
AUDIT_MODULES = (
    "test_brush_audit_ordering_stable", "test_encounter_audit_compact_golden", "test_encounter_coverage_matrix_artifact",
    "test_encounter_headroom_artifact", "test_encounter_headroom_golden", "test_room_audit_ordering_stable",
    "test_stamp_audit_ordering_stable", "test_verify_all_brush_audit_artifact",
    "test_verify_all_encounter_audit_nonempty", "test_verify_all_macro_audit_artifact",
    "test_verify_all_macro_audit_includes_new_objective_macro_case",
    "test_verify_all_room_audit_artifact_json_valid_and_sorted",
    "test_verify_all_room_audit_includes_micro_dungeon_cases", "test_verify_all_stamp_audit_artifact",
)
# The only functions that may run verify-all on this checkout, and why.
OWN_RUN_ALLOWED = {
    "tests/_verify_all_audit.py::run_once": "the one run the audit tests share",
    "tests/test_mesh_cli_headless_imports.py::test_mesh_cli_verify_all_runs_headless_without_arcade":
        "a different condition: a fresh interpreter in which arcade cannot be imported",
}


# --------------------------------------------------------------------------- #
# The shared run
# --------------------------------------------------------------------------- #

def _stand_ins() -> dict[str, Any]:
    import engine.tooling.asset_doctor as asset_doctor
    import mesh_cli

    return {"demo": mesh_cli.verify_demo.run_verify_demo, "replays": mesh_cli.replay_suite.run_replay_suite,
            "validate": mesh_cli.validate_all.main, "doctor": asset_doctor.doctor_assets}


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[dict[str, Any]]:
    """``mesh_cli.main`` replaced by a recorder (``result``: an exit code, or an exception to raise), starting from a
    folder that is not the checkout."""
    import mesh_cli

    monkeypatch.chdir(tmp_path)

    seen: dict[str, Any] = {"calls": [], "result": 0}
    before = _stand_ins()

    def main(argv: list[str]) -> int:
        seen["calls"].append({"argv": list(argv), "cwd": Path.cwd(),
                              "stood_in": sorted(k for k, v in _stand_ins().items() if v is not before[k])})
        if isinstance(seen["result"], BaseException):
            raise seen["result"]
        return int(seen["result"])

    monkeypatch.setattr(mesh_cli, "main", main)
    yield seen


def test_the_shared_run_is_one_whole_verify_all_of_this_checkout(recorded: dict[str, Any], tmp_path: Path) -> None:
    start, before = Path.cwd(), _stand_ins()
    out = tmp_path / "artifacts"

    assert shared.run_once(out) == out

    assert len(recorded["calls"]) == 1, "one run"
    call = recorded["calls"][0]
    # the whole command, as the audit tests ran it: no step selection, no skip flags
    assert call["argv"] == ["verify-all", "--artifacts", str(out), "--no-index"]
    assert call["cwd"] == REPO_ROOT, "in this checkout"
    assert call["stood_in"] == ["demo", "doctor", "replays", "validate"], "the stand-ins the audit tests always used"
    # for the run only
    assert Path.cwd() == start and all(_stand_ins()[k] is v for k, v in before.items())


@pytest.mark.parametrize("result", [1, 2, RuntimeError("the pipeline broke")], ids=["exit 1", "exit 2", "raises"])
def test_a_failed_verify_all_fails_whoever_shares_it(recorded: dict[str, Any], tmp_path: Path, result: Any) -> None:
    start, before = Path.cwd(), _stand_ins()
    recorded["result"] = result

    with pytest.raises((AssertionError, RuntimeError)) as failure:
        shared.run_once(tmp_path / "artifacts")

    if isinstance(result, int):
        assert f"exit code {result}" in str(failure.value)
    else:
        assert failure.value is result
    assert Path.cwd() == start and all(_stand_ins()[k] is v for k, v in before.items())


def test_the_fixture_is_that_run_once_a_session(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch,
                                                tmp_path_factory: pytest.TempPathFactory) -> None:
    definitions = request.session._fixturemanager.getfixturedefs(FIXTURE, request.node)
    assert definitions and len(definitions) == 1, "defined once, in tests/conftest.py"
    definition = definitions[0]
    assert definition.scope == "session", "one run for every test of the session, not one a test or a module"

    runs: list[Path] = []
    monkeypatch.setattr(shared, "run_once", lambda out: runs.append(out) or out)
    function = getattr(definition.func, "__wrapped__", definition.func)
    folder = function(tmp_path_factory)

    assert runs == [folder] and folder.name == "artifacts"
    assert not folder.is_relative_to(REPO_ROOT), "the reports go to pytest's temporary folder, never into the checkout"


# --------------------------------------------------------------------------- #
# No test runs verify-all on this checkout itself
# --------------------------------------------------------------------------- #

def _mentions_file(node: ast.AST) -> bool:
    return any(isinstance(n, ast.Name) and n.id == "__file__" for n in ast.walk(node))


def _is_verify_all_run(call: ast.Call) -> bool:
    """A call given a list or tuple whose first item is "verify-all" (``main([...])``, a handler, a subprocess), or a
    code string that runs it (``main(['verify-all', ...])`` in a fresh interpreter)."""
    for arg in [*call.args, *(k.value for k in call.keywords)]:
        for node in ast.walk(arg):
            if isinstance(node, (ast.List, ast.Tuple)) and node.elts:
                items = [e.value for e in node.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                if "verify-all" in items and "--help" not in items:  # (its help text is not a run)
                    return True
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and re.search(
                    r"main\(\s*\[\s*['\"]verify-all['\"]", node.value):
                return True
    return False


def _own_runs(source: str) -> list[str]:
    """Functions that run verify-all and also work in this checkout: they change directory to, or pass as ``cwd``, a
    path made from ``__file__`` (in the function or at module level). A test that builds its own project folder under
    ``tmp_path`` and runs verify-all there is not one of these."""
    tree = ast.parse(source)
    module_paths = {t.id for node in tree.body if isinstance(node, ast.Assign) and _mentions_file(node.value)
                    for t in node.targets if isinstance(t, ast.Name)}
    found = []
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        paths = set(module_paths)
        for node in ast.walk(function):
            if isinstance(node, ast.Assign) and _mentions_file(node.value):
                paths |= {t.id for t in node.targets if isinstance(t, ast.Name)}
        runs = here = False
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            runs = runs or _is_verify_all_run(node)
            target = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            places = list(node.args) if target == "chdir" else [k.value for k in node.keywords if k.arg == "cwd"]
            for place in places:
                if _mentions_file(place) or any(isinstance(n, ast.Name) and n.id in paths for n in ast.walk(place)):
                    here = True
        if runs and here:
            found.append(function.name)
    return found


OLD_AUDIT_TEST = '''
def test_x(monkeypatch, tmp_path):
    import mesh_cli
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)
    assert mesh_cli.main(["verify-all", "--artifacts", str(tmp_path), "--no-index"]) == 0
'''
OWN = {
    "the audit tests' old shape": OLD_AUDIT_TEST,
    "os.chdir": 'def test_x():\n    root = Path(__file__).parent.parent\n    os.chdir(root)\n    main(["verify-all"])\n',
    "a module-level root": 'ROOT = Path(__file__).resolve().parents[1]\ndef test_x(monkeypatch):\n'
                           '    monkeypatch.chdir(ROOT)\n    mesh_cli.main(["verify-all", "--artifacts", "a"])\n',
    "a subprocess in the checkout": 'def test_x():\n    root = Path(__file__).parents[1]\n'
                                    '    subprocess.run([sys.executable, "-m", "mesh_cli", "verify-all"], cwd=root)\n',
    "a code string in the checkout": 'def test_x():\n    run("from mesh_cli.main import main\\n'
                                     'raise SystemExit(main([\'verify-all\']))", cwd=Path(__file__).parents[1])\n',
    "the handler": 'def test_x(monkeypatch):\n    monkeypatch.chdir(Path(__file__).parents[1])\n'
                   '    handle(argparse.Namespace(command="x"), ["verify-all", "--no-index"])\n',
}
NOT_OWN = {
    "its own project folder": 'def test_x(monkeypatch, tmp_path):\n    repo = tmp_path / "repo"\n'
                              '    monkeypatch.chdir(repo / "sub")\n    assert mesh_cli.main(["verify-all"]) == 0\n',
    "the shared reports": 'def test_x(verify_all_audit_artifacts):\n    root = Path(__file__).parents[1]\n'
                          '    assert (verify_all_audit_artifacts / "stamp_audit.json").exists()\n',
    "only its help text": 'def test_x():\n    root = Path(__file__).parents[1]\n'
                          '    subprocess.run([sys.executable, "-m", "mesh_cli", "verify-all", "--help"], cwd=root)\n',
    "another command in the checkout": 'def test_x(monkeypatch):\n    monkeypatch.chdir(Path(__file__).parents[1])\n'
                                       '    mesh_cli.main(["validate-all"])\n',
    "a stand-in argument list": 'def test_x():\n    root = Path(__file__).parents[1]\n'
                                '    args = argparse.Namespace(command="verify-all", artifacts="a")\n',
}


@pytest.mark.parametrize("source", OWN.values(), ids=OWN.keys())
def test_the_check_sees_a_test_running_verify_all_on_this_checkout(source: str) -> None:
    assert _own_runs(source) == ["test_x"]


@pytest.mark.parametrize("source", NOT_OWN.values(), ids=NOT_OWN.keys())
def test_the_check_leaves_other_tests_alone(source: str) -> None:
    assert _own_runs(source) == []


def test_no_test_runs_its_own_verify_all_of_this_checkout() -> None:
    """A new audit test asks for ``verify_all_audit_artifacts``; it doesn't run verify-all again. (The check reads the
    shape of the code: a run hidden behind a helper in another module is not seen.)"""
    found = set()
    for path in sorted(TESTS.rglob("*.py")):
        source = path.read_text(encoding="utf-8-sig")
        if "verify-all" not in source or path == Path(__file__):
            continue
        found |= {f"{path.relative_to(REPO_ROOT).as_posix()}::{name}" for name in _own_runs(source)}
    assert found == set(OWN_RUN_ALLOWED), (
        "verify-all run on this checkout by a test of its own (use the verify_all_audit_artifacts fixture), or an "
        f"allowed run gone: {sorted(found ^ set(OWN_RUN_ALLOWED))}")


def test_every_audit_test_reads_the_shared_run() -> None:
    users = 0
    for module in AUDIT_MODULES:
        tree = ast.parse((TESTS / f"{module}.py").read_text(encoding="utf-8-sig"))
        tests = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
        assert tests, module
        for test in tests:
            assert FIXTURE in [a.arg for a in test.args.args], f"{module}::{test.name} doesn't use the shared run"
            users += 1
    assert users == 16


# --------------------------------------------------------------------------- #
# The workflows: one verify-all a job, reused by what follows it
# --------------------------------------------------------------------------- #

def _jobs(workflow: str) -> dict[str, str]:
    """Each job's text, by its key (a line indented two spaces under ``jobs:``)."""
    text = (WORKFLOWS / workflow).read_text(encoding="utf-8")
    body = text[text.index("\njobs:\n") + len("\njobs:\n"):]
    parts = re.split(r"(?m)^  ([A-Za-z0-9_-]+):[ \t]*$", body)
    return {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}


def _steps(job: str) -> dict[str, str]:
    """The job's steps, by name."""
    found = {}
    for step in re.split(r"(?m)^      - ", job)[1:]:
        name = re.match(r"name: (.*)", step)
        found[name.group(1).strip() if name else f"(unnamed {len(found)})"] = step
    return found


def _steps_running(job: str, command: str) -> dict[str, list[str]]:
    """The job's steps with a line that runs ``command`` (comments apart): step name -> those lines."""
    found = {}
    for name, step in _steps(job).items():
        lines = [line.strip() for line in step.splitlines()
                 if command in line and not line.strip().startswith("#") and "name:" not in line]
        if lines:
            found[name] = lines
    return found


# Every job of every workflow that runs verify-all itself: the steps that do. Windows and Linux are one step each,
# of which a runner executes its own. Any other job, and any other step, runs none.
VERIFY_ALL_STEPS = {
    "ci.yml": {"verify": ["Run verify-all (Windows)", "Run verify-all (Linux)"]},
    "extended.yml": {},
    "release_draft.yml": {},  # (its release-preflight runs one itself, on the commit being released)
    "update_ci_baseline.yml": {"update-baseline": ["Generate verify artifacts"]},
    "update_weekly_trends.yml": {"update-weekly-trends": ["Generate verify artifacts"]},
    "weekly_health.yml": {"health": ["Verify-all + CI bundle"]},
}


def test_every_workflow_is_in_the_map() -> None:
    assert sorted(p.name for p in WORKFLOWS.glob("*.yml")) == sorted(VERIFY_ALL_STEPS)


@pytest.mark.parametrize("workflow", sorted(VERIFY_ALL_STEPS))
def test_each_job_runs_verify_all_at_most_once(workflow: str) -> None:
    expected = VERIFY_ALL_STEPS[workflow]
    actual = {}
    for key, job in _jobs(workflow).items():
        steps = _steps_running(job, "mesh_cli verify-all")
        if steps:
            assert all(len(lines) == 1 for lines in steps.values()), (key, steps)
            actual[key] = list(steps)
    assert actual == expected


def test_ci_s_verify_job_runs_one_verify_all_per_runner_and_the_bundle_reuses_it() -> None:
    job = _jobs("ci.yml")["verify"]
    steps = _steps(job)
    # a runner executes its own system's step of each pair, never both
    for system, only in (("Windows", "if: runner.os == 'Windows'"), ("Linux", "if: runner.os != 'Windows'")):
        run = steps[f"Run verify-all ({system})"]
        assert only in run
        assert "mesh_cli verify-all --artifacts artifacts --ci-bundle --release-notes-artifact --reuse-evidence" in run
        bundle = steps[f"Build release bundle (seeded, {system})"]
        assert only in bundle
        # the bundle's release check takes this job's verify-all, on evidence, instead of running another (F13-B)
        assert "mesh_cli release bundle" in bundle and "--reuse-verify-all artifacts" in bundle
        assert job.index(f"Run verify-all ({system})") < job.index(f"Build release bundle (seeded, {system})")
    # nothing else in the job starts a verification of its own
    assert _steps_running(job, "mesh_cli release check") == {} and _steps_running(job, "tooling.pytest_fast") == {}
    assert _steps_running(job, "mesh_cli ship-check") == {} and _steps_running(job, "release-preflight") == {}
    # and no other job of the workflow builds the bundle
    for key, other_job in _jobs("ci.yml").items():
        if key != "verify":
            assert _steps_running(other_job, "mesh_cli release bundle") == {}, key


def test_the_baseline_update_takes_its_job_s_verify_all() -> None:
    job = _jobs("update_ci_baseline.yml")["update-baseline"]
    update = _steps_running(job, "mesh_cli baseline-update")
    assert len(update) == 1
    (line,) = next(iter(update.values()))
    assert "--artifacts artifacts" in line and "--no-verify-all" in line
    assert job.index("mesh_cli verify-all") < job.index("mesh_cli baseline-update")
