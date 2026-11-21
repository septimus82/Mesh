from pathlib import Path
from unittest.mock import MagicMock

import pytest

import engine.tooling_runtime.verify_demo as runtime_verify_demo
from engine.tooling.verify_demo import build_verify_demo_pytest_cmd, run_verify_demo

pytestmark = [pytest.mark.fast]


def test_verify_demo_builds_deterministic_pytest_cmd(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)

    captured = {}

    def _fake_run(cmd, capture_output=False, text=False, cwd=None):  # noqa: ARG001
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return MagicMock(returncode=0)

    monkeypatch.setattr("engine.tooling.verify_demo.subprocess.run", _fake_run)

    rc = run_verify_demo()
    assert rc == 0
    assert captured["cmd"] == build_verify_demo_pytest_cmd()


def test_verify_demo_appends_pytest_passthrough_args(monkeypatch) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)

    captured = {}

    def _fake_run(cmd, capture_output=False, text=False, cwd=None):  # noqa: ARG001
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return MagicMock(returncode=0)

    monkeypatch.setattr("engine.tooling.verify_demo.subprocess.run", _fake_run)

    extra = ["--maxfail=1"]
    rc = run_verify_demo(extra)
    assert rc == 0
    assert captured["cmd"] == build_verify_demo_pytest_cmd() + extra


def test_verify_demo_uses_artifacts_scoped_pytest_scratch_when_log_path_provided(monkeypatch, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)
    # (the artifacts-scoped branch, explicitly: whether this machine's tmp_path is short enough must not decide which
    # branch runs; the too-long branch has its own tests below, the same on every machine)
    monkeypatch.setattr(runtime_verify_demo, "MAX_BASETEMP_CHARS", 10_000)

    captured = {}

    def _fake_run(cmd, capture_output=False, text=False, cwd=None):  # noqa: ARG001
        captured["cmd"] = list(cmd)
        captured["cwd"] = cwd
        return MagicMock(returncode=0)

    monkeypatch.setattr("engine.tooling.verify_demo.subprocess.run", _fake_run)

    artifacts_dir = tmp_path / "artifacts"
    log_path = artifacts_dir / "verify_demo.log"
    rc = run_verify_demo(capture_output=True, quiet=True, log_path=log_path)

    assert rc == 0
    cmd = captured["cmd"]
    assert cmd[: len(build_verify_demo_pytest_cmd())] == build_verify_demo_pytest_cmd()
    assert cmd[len(build_verify_demo_pytest_cmd())] == "--basetemp"
    basetemp = Path(cmd[len(build_verify_demo_pytest_cmd()) + 1])
    assert basetemp.parent.parent == artifacts_dir / "verify_demo_pytest"
    assert basetemp.name == "basetemp"
    assert cmd[len(build_verify_demo_pytest_cmd()) + 2 :] == [
        "-o",
        f"cache_dir={(basetemp.parent / 'cache').as_posix()}",
    ]
    assert captured["cwd"] == str(root)
    assert not (artifacts_dir / "verify_demo_failure.json").exists()


def test_verify_demo_run_paths_are_distinct_across_back_to_back_runs(monkeypatch, tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)
    # (the artifacts-scoped branch, explicitly: whether this machine's tmp_path is short enough must not decide which
    # branch runs; the too-long branch has its own tests below, the same on every machine)
    monkeypatch.setattr(runtime_verify_demo, "MAX_BASETEMP_CHARS", 10_000)

    captured: list[list[str]] = []

    def _fake_run(cmd, capture_output=False, text=False, cwd=None):  # noqa: ARG001
        captured.append(list(cmd))
        return MagicMock(returncode=0)

    monkeypatch.setattr("engine.tooling.verify_demo.subprocess.run", _fake_run)

    scratch_dir = tmp_path / "artifacts" / "verify_demo_pytest"
    assert run_verify_demo(capture_output=True, quiet=True, scratch_dir=scratch_dir) == 0
    assert run_verify_demo(capture_output=True, quiet=True, scratch_dir=scratch_dir) == 0

    first_basetemp = Path(captured[0][len(build_verify_demo_pytest_cmd()) + 1])
    second_basetemp = Path(captured[1][len(build_verify_demo_pytest_cmd()) + 1])
    assert first_basetemp != second_basetemp
    assert first_basetemp.parent.parent == scratch_dir
    assert second_basetemp.parent.parent == scratch_dir
    assert not (tmp_path / "artifacts" / "verify_demo_failure.json").exists()


def test_verify_demo_success_does_not_require_or_create_shared_tests_temp_dirs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runtime_verify_demo, "iter_missing_paths", lambda _paths: [])

    def _fake_run(cmd, capture_output=False, text=False, cwd=None):  # noqa: ARG001
        return MagicMock(returncode=0)

    monkeypatch.setattr("engine.tooling.verify_demo.subprocess.run", _fake_run)

    shared_dirs = [
        tmp_path / "tests" / "temp_trend",
        tmp_path / "tests" / "temp_audit_auto",
    ]
    for shared_dir in shared_dirs:
        assert not shared_dir.exists()

    scratch_dir = tmp_path / "artifacts" / "verify_demo_pytest"
    assert run_verify_demo(capture_output=True, quiet=True, scratch_dir=scratch_dir) == 0
    assert run_verify_demo(capture_output=True, quiet=True, scratch_dir=scratch_dir) == 0

    for shared_dir in shared_dirs:
        assert not shared_dir.exists()


def test_verify_demo_strict_guard_rejects_selection_changing_flags(monkeypatch, capsys) -> None:
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)

    # Should fail before attempting to spawn pytest.
    monkeypatch.setattr(
        "engine.tooling.verify_demo.subprocess.run",
        lambda *a, **k: MagicMock(returncode=0),
    )

    rc = run_verify_demo(["-k", "smoke"])
    assert rc != 0
    _ = capsys.readouterr()


def _too_long(monkeypatch) -> None:
    """Every artifacts-scoped basetemp counts as too long (#394's branch, on any machine)."""
    monkeypatch.setattr(runtime_verify_demo, "MAX_BASETEMP_CHARS", 0)


def test_verify_demo_too_long_basetemp_gets_a_short_folder_unique_to_each_run(monkeypatch, tmp_path: Path) -> None:
    """#394: nested in the release bundle's work folder, the demo tests' project trees went past Windows' 260
    characters. Such a run gets its own new short folder in the temp folder (two runs never share one), named in its
    run root while it runs, and removed when it passes."""
    import tempfile

    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)
    _too_long(monkeypatch)
    seen: list[dict[str, object]] = []

    def _fake_run(cmd, capture_output=False, text=False, cwd=None):  # noqa: ARG001
        n = len(build_verify_demo_pytest_cmd())
        basetemp = Path(cmd[n + 1])
        cache_dir = Path(cmd[n + 3].split("=", 1)[1])
        pointer = cache_dir.parent / runtime_verify_demo.BASETEMP_POINTER
        seen.append({"basetemp": basetemp, "run_root": cache_dir.parent, "folder_exists": basetemp.parent.is_dir(),
                     "pointer": pointer.read_text(encoding="utf-8").strip() if pointer.exists() else None})
        return MagicMock(returncode=0)

    monkeypatch.setattr("engine.tooling.verify_demo.subprocess.run", _fake_run)
    scratch_dir = tmp_path / "artifacts" / "verify_demo_pytest"
    assert run_verify_demo(capture_output=True, quiet=True, scratch_dir=scratch_dir) == 0
    assert run_verify_demo(capture_output=True, quiet=True, scratch_dir=scratch_dir) == 0

    first, second = seen
    temp = Path(tempfile.gettempdir()).resolve()
    for run in (first, second):
        basetemp = Path(str(run["basetemp"]))
        assert basetemp.name == "basetemp" and basetemp.parent.parent.resolve() == temp  # (short: <temp>/mvd-*/basetemp)
        assert len(str(basetemp)) <= len(str(Path(tempfile.gettempdir()))) + 30
        assert run["folder_exists"] and run["pointer"] == str(basetemp)  # (made for the run, named in its run root)
        assert Path(str(run["run_root"])).parent == scratch_dir  # (the run's root and cache stay beside the artifacts)
        assert not basetemp.parent.exists()  # (removed: the run passed)
        assert not (Path(str(run["run_root"])) / runtime_verify_demo.BASETEMP_POINTER).exists()
    assert first["basetemp"] != second["basetemp"] and Path(str(first["basetemp"])).parent != Path(str(second["basetemp"])).parent
    assert first["run_root"] != second["run_root"]


def test_verify_demo_failed_run_keeps_its_short_basetemp_and_reports_it_redacted(monkeypatch, tmp_path: Path) -> None:
    """A failed run keeps its short folder for inspection; the failure report names it, and shows the inherited
    environment by name with only known-safe values (a CI job's environment can hold tokens)."""
    import json
    import shutil

    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)
    _too_long(monkeypatch)
    monkeypatch.setenv("MESH_FAKE_API_TOKEN", "s3cret-value")
    monkeypatch.setenv("PYTHON_FAKE_PASSWORD", "hunter2-value")
    monkeypatch.setenv("MESH_CI_SEED", "123")
    for name in ("PYTHONPATH", "PYTHONHOME", "PYTEST_ADDOPTS", "MESH_REPO_ROOT"):  # (paths and free-form options)
        monkeypatch.setenv(name, f"C:/Users/someone-private/{name}-value")
    monkeypatch.setattr("engine.tooling.verify_demo.subprocess.run",
                        lambda *a, **k: MagicMock(returncode=1, stdout="1 failed", stderr=""))
    artifacts_dir = tmp_path / "artifacts"
    assert run_verify_demo(capture_output=True, quiet=True, log_path=artifacts_dir / "verify_demo.log") == 1

    failure_path = artifacts_dir / "verify_demo_failure.json"
    text = failure_path.read_text(encoding="utf-8")
    report = json.loads(text)
    basetemp = Path(report["basetemp"])
    try:
        assert basetemp.parent.is_dir() and artifacts_dir not in basetemp.parents  # (kept, in the temp folder)
        assert (Path(report["run_root"]) / runtime_verify_demo.BASETEMP_POINTER).read_text(encoding="utf-8").strip()             == str(basetemp)
        env = report["environment"]
        assert env["MESH_FAKE_API_TOKEN"] == "<redacted>" and env["PYTHON_FAKE_PASSWORD"] == "<redacted>"
        assert env["MESH_CI_SEED"] == "123"
        assert "s3cret-value" not in text and "hunter2-value" not in text
        for name in ("PYTHONPATH", "PYTHONHOME", "PYTEST_ADDOPTS", "MESH_REPO_ROOT"):
            assert env[name] == "<redacted>"
        assert "someone-private" not in json.dumps(env)
    finally:
        shutil.rmtree(basetemp.parent, ignore_errors=True)
