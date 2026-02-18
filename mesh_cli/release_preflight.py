from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

from mesh_cli.version_info import get_tool_version


def _repo_root_from_module() -> Path:
    return Path(__file__).resolve().parent.parent


def _run_cmd(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
    )


def _safe_read_toml(path: Path) -> dict[str, Any] | None:
    if not path.exists() or not path.is_file():
        return None
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _read_package_version_from_pyproject(repo_root: Path) -> str:
    payload = _safe_read_toml(repo_root / "pyproject.toml")
    if not isinstance(payload, dict):
        return "?"
    project = payload.get("project")
    if not isinstance(project, dict):
        return "?"
    version = project.get("version")
    return str(version).strip() if isinstance(version, str) and version.strip() else "?"


def _arcade_runtime_range_ok(repo_root: Path) -> bool:
    payload = _safe_read_toml(repo_root / "pyproject.toml")
    if not isinstance(payload, dict):
        return False
    project = payload.get("project")
    if not isinstance(project, dict):
        return False
    dependencies = project.get("dependencies")
    if not isinstance(dependencies, list):
        return False
    for dep in dependencies:
        if not isinstance(dep, str):
            continue
        text = dep.strip().lower()
        if not text.startswith("arcade"):
            continue
        has_lower_3 = re.search(r">\s*=\s*3(\D|$)", text) is not None
        has_upper_4 = re.search(r"<\s*4(\D|$)", text) is not None
        if has_lower_3 and has_upper_4:
            return True
    return False


def _manifest_includes_examples_json(repo_root: Path) -> bool:
    manifest_path = repo_root / "MANIFEST.in"
    if not manifest_path.exists() or not manifest_path.is_file():
        return False
    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return False
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        lowered = line.lower()
        if "examples" in lowered and ".json" in lowered:
            return True
    return False


def _git_available(repo_root: Path) -> bool:
    try:
        result = _run_cmd(["git", "--version"], cwd=repo_root)
    except OSError:
        return False
    return result.returncode == 0


def _git_tag_exists_local(repo_root: Path, tag: str) -> bool:
    try:
        result = _run_cmd(["git", "tag", "--list", tag], cwd=repo_root)
    except OSError:
        return False
    if result.returncode != 0:
        return False
    return bool((result.stdout or "").strip())


def _git_tag_exists_remote(repo_root: Path, tag: str) -> bool:
    try:
        result = _run_cmd(["git", "ls-remote", "--tags", "origin", f"refs/tags/{tag}"], cwd=repo_root)
    except OSError:
        return False
    if result.returncode != 0:
        return False
    return bool((result.stdout or "").strip())


def _make_temp_artifacts_dir(repo_root: Path) -> Path:
    base = repo_root / "artifacts"
    base.mkdir(parents=True, exist_ok=True)
    pid = os.getpid()
    candidate = base / f"artifacts_preflight_{pid}"
    suffix = 0
    while candidate.exists():
        suffix += 1
        candidate = base / f"artifacts_preflight_{pid}_{suffix}"
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def _normalize_artifacts_dir(repo_root: Path, raw: str | None) -> Path:
    if raw is None or not str(raw).strip():
        return _make_temp_artifacts_dir(repo_root)
    path = Path(str(raw).strip())
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _tag_issues(repo_root: Path, tag: str | None) -> tuple[list[str], str | None]:
    if tag is None:
        return [], None

    issues: list[str] = []
    if not tag.startswith("v"):
        issues.append("tag format invalid: expected to start with 'v'")
        return issues, None

    if not _git_available(repo_root):
        return issues, "(git unavailable)"

    if _git_tag_exists_local(repo_root, tag):
        issues.append(f"tag already exists locally: {tag}")
    if _git_tag_exists_remote(repo_root, tag):
        issues.append(f"tag already exists on origin: {tag}")
    return issues, None


def _run_preflight_checks(
    repo_root: Path,
    artifacts_dir: Path,
    *,
    issues: list[str],
    run_verify_all: bool,
) -> None:
    if not run_verify_all:
        return

    verify_args = [
        sys.executable,
        "-m",
        "mesh_cli",
        "verify-all",
        "--artifacts",
        artifacts_dir.as_posix(),
        "--ci-bundle",
        "--release-notes-artifact",
    ]
    validate_args = [
        sys.executable,
        "-m",
        "mesh_cli",
        "artifacts-validate",
        "--artifacts",
        artifacts_dir.as_posix(),
    ]

    verify_result = _run_cmd(verify_args, cwd=repo_root)
    if verify_result.returncode != 0:
        issues.append(f"verify-all failed (code={int(verify_result.returncode)})")

    validate_result = _run_cmd(validate_args, cwd=repo_root)
    if validate_result.returncode != 0:
        issues.append(f"artifacts-validate failed (code={int(validate_result.returncode)})")


def _handle_release_preflight(args: argparse.Namespace) -> int:
    repo_root = _repo_root_from_module()
    package_version = _read_package_version_from_pyproject(repo_root)
    try:
        from engine.public_api import PUBLIC_API_SEMVER  # noqa: PLC0415
    except Exception:
        PUBLIC_API_SEMVER = "?"

    tag_raw = str(getattr(args, "tag", "") or "").strip()
    tag = tag_raw if tag_raw else None
    keep_temp = bool(getattr(args, "keep_temp", False))
    no_verify_all = bool(getattr(args, "no_verify_all", False))
    artifacts_raw = str(getattr(args, "artifacts", "") or "").strip() or None
    artifacts_dir = _normalize_artifacts_dir(repo_root, artifacts_raw)
    auto_temp = artifacts_raw is None

    issues: list[str] = []

    if not _manifest_includes_examples_json(repo_root):
        issues.append("MANIFEST.in missing examples JSON include")
    if not _arcade_runtime_range_ok(repo_root):
        issues.append("pyproject.toml missing arcade runtime range >=3,<4")

    tag_issues, git_note = _tag_issues(repo_root, tag)
    issues.extend(tag_issues)

    _run_preflight_checks(
        repo_root,
        artifacts_dir,
        issues=issues,
        run_verify_all=not no_verify_all,
    )

    print(f"- package version: {package_version}")
    print(f"- public api semver: {PUBLIC_API_SEMVER}")
    print(f"- artifacts: {artifacts_dir.as_posix()}")
    if tag is not None:
        print(f"- tag: {tag}")
        if git_note is not None:
            print(git_note)

    if issues:
        print("Release preflight failed:")
        for issue in sorted(set(issues)):
            print(f"- {issue}")
        return 2

    print("Release preflight ok.")
    if auto_temp and not keep_temp:
        shutil.rmtree(artifacts_dir, ignore_errors=True)
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "release-preflight",
        help="Run local release-critical preflight checks",
    )
    parser.add_argument("--tag", default="", help="Optional release tag candidate (example: v0.4.1)")
    parser.add_argument("--keep-temp", action="store_true", help="Keep auto-created artifacts directory")
    parser.add_argument("--artifacts", default="", help="Optional artifacts directory override")
    parser.add_argument("--no-verify-all", action="store_true", help="Skip verify-all/artifacts-validate subprocess checks")
    parser.set_defaults(func=_handle_release_preflight)


def handle(args: argparse.Namespace) -> int:
    return _handle_release_preflight(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mesh release-preflight")
    parser.add_argument("--tag", default="")
    parser.add_argument("--keep-temp", action="store_true")
    parser.add_argument("--artifacts", default="")
    parser.add_argument("--no-verify-all", action="store_true")
    args = parser.parse_args(argv)
    return _handle_release_preflight(args)
