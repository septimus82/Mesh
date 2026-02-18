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
    _write(
        repo / "pyproject.toml",
        "\n".join(
            [
                "[project]",
                "name = \"mesh-engine\"",
                "version = \"0.4.0\"",
                "dependencies = [",
                "  \"arcade>=3,<4\",",
                "]",
                "",
            ]
        ),
    )
    _write(
        repo / "engine" / "public_api" / "version.py",
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "PUBLIC_API_VERSION = \"1.0\"",
                "PUBLIC_API_SEMVER = \"1.0.0\"",
                "",
                "__all__ = [\"PUBLIC_API_VERSION\", \"PUBLIC_API_SEMVER\"]",
                "",
            ]
        ),
    )
    return repo


def _cp(args: list[str], *, code: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=args, returncode=code, stdout=out, stderr=err)


def test_version_bump_dry_run_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import mesh_cli.version_bump as vb

    repo = _make_repo(tmp_path)
    monkeypatch.setattr(vb, "_repo_root_from_module", lambda: repo)

    def _fail_run_cmd(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        raise AssertionError(f"unexpected subprocess call: {args}")

    monkeypatch.setattr(vb, "_run_cmd", _fail_run_cmd)
    before_pyproject = (repo / "pyproject.toml").read_text(encoding="utf-8")
    before_public = (repo / "engine" / "public_api" / "version.py").read_text(encoding="utf-8")

    rc = vb.main(["--to", "0.4.1", "--public-api", "1.0.1", "--dry-run"])
    out = capsys.readouterr().out
    assert rc == 0
    assert (repo / "pyproject.toml").read_text(encoding="utf-8") == before_pyproject
    assert (repo / "engine" / "public_api" / "version.py").read_text(encoding="utf-8") == before_public
    assert f"--- {(repo / 'pyproject.toml').as_posix()}" in out
    assert f"--- {(repo / 'engine' / 'public_api' / 'version.py').as_posix()}" in out


def test_version_bump_normal_run_updates_files_and_runs_post_checks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import mesh_cli.version_bump as vb

    repo = _make_repo(tmp_path)
    monkeypatch.setattr(vb, "_repo_root_from_module", lambda: repo)
    calls: list[list[str]] = []

    def _fake_run_cmd(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        calls.append(list(args))
        return _cp(args, code=0)

    monkeypatch.setattr(vb, "_run_cmd", _fake_run_cmd)
    rc = vb.main(["--to", "0.4.1", "--public-api", "1.0.1"])
    assert rc == 0

    pyproject = (repo / "pyproject.toml").read_text(encoding="utf-8")
    public_api = (repo / "engine" / "public_api" / "version.py").read_text(encoding="utf-8")
    assert 'version = "0.4.1"' in pyproject
    assert 'PUBLIC_API_SEMVER = "1.0.1"' in public_api
    assert 'PUBLIC_API_VERSION = "1.0"' in public_api

    assert [sys.executable, "-m", "mesh_cli", "release-preflight", "--no-verify-all"] in calls
    assert [sys.executable, "-m", "compileall", "-q", "engine", "mesh_cli", "tooling", "tests"] in calls


def test_version_bump_invalid_version_strings_fail(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import mesh_cli.version_bump as vb

    repo = _make_repo(tmp_path)
    monkeypatch.setattr(vb, "_repo_root_from_module", lambda: repo)
    monkeypatch.setattr(vb, "_run_cmd", lambda args, *, cwd=None: _cp(args, code=0))

    before_pyproject = (repo / "pyproject.toml").read_text(encoding="utf-8")
    assert vb.main(["--to", "bad.version"]) == 2
    assert vb.main(["--to", "0.4.1", "--public-api", "nope"]) == 2
    assert (repo / "pyproject.toml").read_text(encoding="utf-8") == before_pyproject


def test_version_bump_dry_run_output_is_deterministic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import mesh_cli.version_bump as vb

    repo = _make_repo(tmp_path)
    monkeypatch.setattr(vb, "_repo_root_from_module", lambda: repo)
    monkeypatch.setattr(vb, "_run_cmd", lambda args, *, cwd=None: _cp(args, code=0))

    rc1 = vb.main(["--to", "0.4.9", "--public-api", "1.2.3", "--dry-run"])
    out1 = capsys.readouterr().out
    rc2 = vb.main(["--to", "0.4.9", "--public-api", "1.2.3", "--dry-run"])
    out2 = capsys.readouterr().out

    assert rc1 == 0
    assert rc2 == 0
    assert out1 == out2
