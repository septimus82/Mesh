from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _write(
        repo / "pyproject.toml",
        "\n".join(
            [
                "[project]",
                "name = \"mesh-engine\"",
                "version = \"1.2.3\"",
                "dependencies = [",
                "  \"arcade>=3,<4\",",
                "]",
                "",
            ]
        ),
    )
    _write(repo / "MANIFEST.in", "recursive-include examples *.json\n")
    return repo


def _cp(args: list[str], *, code: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=args, returncode=code, stdout=out, stderr=err)


def test_missing_git_is_graceful(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import mesh_cli.release_preflight as rp

    repo = _make_repo(tmp_path)
    monkeypatch.setattr(rp, "_repo_root_from_module", lambda: repo)

    def _fake_run_cmd(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["git", "--version"]:
            raise OSError("git unavailable")
        return _cp(args, code=0)

    monkeypatch.setattr(rp, "_run_cmd", _fake_run_cmd)

    rc = rp.main(["--tag", "v1.2.3", "--artifacts", str(repo / "artifacts")])
    out = capsys.readouterr().out
    assert rc == 0
    assert "(git unavailable)" in out


def test_tag_format_validation(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import mesh_cli.release_preflight as rp

    repo = _make_repo(tmp_path)
    monkeypatch.setattr(rp, "_repo_root_from_module", lambda: repo)
    monkeypatch.setattr(rp, "_run_cmd", lambda args, *, cwd=None: _cp(args, code=0))

    rc = rp.main(["--tag", "1.2.3", "--artifacts", str(repo / "artifacts")])
    out = capsys.readouterr().out
    assert rc == 2
    assert "tag format invalid: expected to start with 'v'" in out


def test_failure_aggregation_is_deterministic(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import mesh_cli.release_preflight as rp

    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    _write(
        repo / "pyproject.toml",
        "\n".join(
            [
                "[project]",
                "name = \"mesh-engine\"",
                "version = \"1.2.3\"",
                "dependencies = [",
                "  \"arcade>=2.6.17\",",
                "]",
                "",
            ]
        ),
    )
    _write(repo / "MANIFEST.in", "include README.md\n")
    monkeypatch.setattr(rp, "_repo_root_from_module", lambda: repo)

    def _fake_run_cmd(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        if args[0] == "git":
            return _cp(args, code=0)
        if args[2:4] == ["mesh_cli", "verify-all"]:
            return _cp(args, code=1)
        if args[2:4] == ["mesh_cli", "artifacts-validate"]:
            return _cp(args, code=2)
        return _cp(args, code=0)

    monkeypatch.setattr(rp, "_run_cmd", _fake_run_cmd)

    rc = rp.main(["--artifacts", str(repo / "artifacts")])
    out = capsys.readouterr().out
    assert rc == 2
    marker = "Release preflight failed:\n"
    assert marker in out
    issues_block = out.split(marker, 1)[1]
    issue_lines = [line.strip() for line in issues_block.splitlines() if line.strip().startswith("- ")]
    assert issue_lines == sorted(issue_lines)


def test_subprocess_invocation_args(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import mesh_cli.release_preflight as rp

    repo = _make_repo(tmp_path)
    monkeypatch.setattr(rp, "_repo_root_from_module", lambda: repo)
    calls: list[list[str]] = []

    def _fake_run_cmd(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        if args[:2] == ["git", "--version"]:
            return _cp(args, code=0)
        return _cp(args, code=0)

    monkeypatch.setattr(rp, "_run_cmd", _fake_run_cmd)
    target_artifacts = repo / "custom_artifacts"
    rc = rp.main(["--artifacts", str(target_artifacts)])
    assert rc == 0

    verify_cmd = [
        sys.executable,
        "-m",
        "mesh_cli",
        "verify-all",
        "--artifacts",
        target_artifacts.as_posix(),
        "--ci-bundle",
        "--release-notes-artifact",
    ]
    validate_cmd = [
        sys.executable,
        "-m",
        "mesh_cli",
        "artifacts-validate",
        "--artifacts",
        target_artifacts.as_posix(),
    ]
    assert verify_cmd in calls
    assert validate_cmd in calls


def test_exit_code_semantics(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import mesh_cli.release_preflight as rp

    repo = _make_repo(tmp_path)
    monkeypatch.setattr(rp, "_repo_root_from_module", lambda: repo)

    monkeypatch.setattr(rp, "_run_cmd", lambda args, *, cwd=None: _cp(args, code=0))
    assert rp.main(["--artifacts", str(repo / "artifacts_ok")]) == 0

    def _failing_run_cmd(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        if args[2:4] == ["mesh_cli", "verify-all"]:
            return _cp(args, code=1)
        return _cp(args, code=0)

    monkeypatch.setattr(rp, "_run_cmd", _failing_run_cmd)
    assert rp.main(["--artifacts", str(repo / "artifacts_fail")]) == 2
