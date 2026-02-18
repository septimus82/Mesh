from __future__ import annotations

import argparse
import difflib
import re
import subprocess
import sys
from pathlib import Path
from typing import Literal

from mesh_cli.version_info import get_version_file_path, read_tool_version

BumpKind = Literal["patch", "minor", "major"]
_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_PROJECT_SECTION_RE = re.compile(r"^\s*\[project\]\s*$")
_SECTION_RE = re.compile(r"^\s*\[[^\]]+\]\s*$")
_VERSION_LINE_RE = re.compile(r'^(\s*version\s*=\s*")([^"]+)(".*)$')
_PUBLIC_API_SEMVER_RE = re.compile(r'^(PUBLIC_API_SEMVER\s*=\s*")([^"]+)(".*)$', re.MULTILINE)
_PUBLIC_API_VERSION_RE = re.compile(r'^(PUBLIC_API_VERSION\s*=\s*")([^"]+)(".*)$', re.MULTILINE)


def parse_semver(s: str) -> tuple[int, int, int]:
    text = str(s or "").strip()
    match = _SEMVER_RE.fullmatch(text)
    if match is None:
        raise ValueError(f"Invalid semantic version '{s}'. Expected X.Y.Z with numeric components.")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def bump_semver(version: str, kind: BumpKind) -> str:
    major, minor, patch = parse_semver(version)
    if kind == "patch":
        return f"{major}.{minor}.{patch + 1}"
    if kind == "minor":
        return f"{major}.{minor + 1}.0"
    if kind == "major":
        return f"{major + 1}.0.0"
    raise ValueError(f"Unsupported bump kind '{kind}'. Expected patch, minor, or major.")


def apply_version_update(path: Path, old_v: str, new_v: str) -> None:
    try:
        original = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read version file '{path.as_posix()}': {exc}") from exc

    old_literal = f'"{old_v}"'
    occurrences = original.count(old_literal)
    if occurrences == 0:
        raise ValueError(
            f"Cannot update version: literal {old_literal} not found in '{path.as_posix()}'."
        )
    if occurrences > 1:
        raise ValueError(
            f"Cannot update version: literal {old_literal} appears {occurrences} times in '{path.as_posix()}'."
        )

    updated = original.replace(old_literal, f'"{new_v}"', 1)
    try:
        path.write_text(updated, encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot write version file '{path.as_posix()}': {exc}") from exc


def version_display_path(path: Path) -> str:
    canonical = get_version_file_path().resolve()
    try:
        if path.resolve() == canonical:
            return "engine/version.py"
    except OSError:
        pass
    return path.as_posix()


def bump_version_file(*, kind: BumpKind, path: Path | None = None, dry_run: bool = False) -> dict[str, str]:
    version_path = path or get_version_file_path()
    old_version = read_tool_version(version_path)
    parse_semver(old_version)  # validates current format
    new_version = bump_semver(old_version, kind)
    if not dry_run:
        apply_version_update(version_path, old_version, new_version)
    return {
        "old": old_version,
        "new": new_version,
        "file": version_display_path(version_path),
    }


def _repo_root_from_module() -> Path:
    return Path(__file__).resolve().parent.parent


def _run_cmd(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
    )


def _update_pyproject_project_version_text(text: str, new_version: str) -> tuple[str, str]:
    lines = text.splitlines(keepends=True)
    in_project = False
    found_index = -1
    old_version = ""

    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if _PROJECT_SECTION_RE.match(stripped):
            in_project = True
            continue
        if _SECTION_RE.match(stripped):
            in_project = False
            continue
        if not in_project:
            continue
        match = _VERSION_LINE_RE.match(raw)
        if match is None:
            continue
        if found_index != -1:
            raise ValueError("Found multiple [project].version lines in pyproject.toml")
        found_index = i
        old_version = match.group(2)
        lines[i] = f'{match.group(1)}{new_version}{match.group(3)}\n' if not raw.endswith("\n") else f"{match.group(1)}{new_version}{match.group(3)}\n"

    if found_index == -1:
        raise ValueError("Could not find [project].version in pyproject.toml")
    return "".join(lines), old_version


def _replace_single_match(pattern: re.Pattern[str], text: str, new_value: str, label: str) -> tuple[str, str]:
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one {label} assignment, found {len(matches)}")
    match = matches[0]
    old_value = match.group(2)
    replacement = f"{match.group(1)}{new_value}{match.group(3)}"
    updated = text[: match.start()] + replacement + text[match.end() :]
    return updated, old_value


def _update_public_api_version_text(text: str, new_semver: str) -> tuple[str, str, str, str]:
    updated_text, old_semver = _replace_single_match(
        _PUBLIC_API_SEMVER_RE,
        text,
        new_semver,
        "PUBLIC_API_SEMVER",
    )
    major, minor, _patch = parse_semver(new_semver)
    new_public_api_version = f"{major}.{minor}"
    updated_text, old_public_api_version = _replace_single_match(
        _PUBLIC_API_VERSION_RE,
        updated_text,
        new_public_api_version,
        "PUBLIC_API_VERSION",
    )
    return updated_text, old_semver, old_public_api_version, new_public_api_version


def _unified_diff(path: Path, before: str, after: str) -> str:
    diff = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=path.as_posix(),
        tofile=path.as_posix(),
        lineterm="",
    )
    return "".join(diff)


def _print_changed_line(path: Path, label: str, old: str, new: str) -> None:
    print(f"{path.as_posix()}: {label} {old} -> {new}")


def _handle_version_bump(args: argparse.Namespace) -> int:
    target_version = str(getattr(args, "to", "") or "").strip()
    public_api_semver_raw = str(getattr(args, "public_api", "") or "").strip()
    public_api_semver = public_api_semver_raw if public_api_semver_raw else None
    dry_run = bool(getattr(args, "dry_run", False))

    try:
        parse_semver(target_version)
        if public_api_semver is not None:
            parse_semver(public_api_semver)
    except ValueError as exc:
        print(f"[Mesh][VersionBump] ERROR: {exc}")
        return 2

    repo_root = _repo_root_from_module()
    pyproject_path = repo_root / "pyproject.toml"
    public_api_path = repo_root / "engine" / "public_api" / "version.py"

    try:
        pyproject_before = pyproject_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[Mesh][VersionBump] ERROR: cannot read {pyproject_path.as_posix()}: {exc}")
        return 2

    try:
        pyproject_after, old_pkg_version = _update_pyproject_project_version_text(pyproject_before, target_version)
    except ValueError as exc:
        print(f"[Mesh][VersionBump] ERROR: {exc}")
        return 2

    public_before: str | None = None
    public_after: str | None = None
    old_public_semver = ""
    old_public_version = ""
    new_public_version = ""
    if public_api_semver is not None:
        try:
            public_before = public_api_path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"[Mesh][VersionBump] ERROR: cannot read {public_api_path.as_posix()}: {exc}")
            return 2
        try:
            public_after, old_public_semver, old_public_version, new_public_version = _update_public_api_version_text(
                public_before, public_api_semver
            )
        except ValueError as exc:
            print(f"[Mesh][VersionBump] ERROR: {exc}")
            return 2

    if dry_run:
        print(_unified_diff(pyproject_path, pyproject_before, pyproject_after))
        if public_before is not None and public_after is not None:
            print(_unified_diff(public_api_path, public_before, public_after))
        return 0

    try:
        pyproject_path.write_text(pyproject_after, encoding="utf-8")
    except OSError as exc:
        print(f"[Mesh][VersionBump] ERROR: cannot write {pyproject_path.as_posix()}: {exc}")
        return 2
    _print_changed_line(pyproject_path, "[project].version", old_pkg_version, target_version)

    if public_before is not None and public_after is not None and public_api_semver is not None:
        try:
            public_api_path.write_text(public_after, encoding="utf-8")
        except OSError as exc:
            print(f"[Mesh][VersionBump] ERROR: cannot write {public_api_path.as_posix()}: {exc}")
            return 2
        _print_changed_line(public_api_path, "PUBLIC_API_SEMVER", old_public_semver, public_api_semver)
        _print_changed_line(public_api_path, "PUBLIC_API_VERSION", old_public_version, new_public_version)

    preflight = _run_cmd(
        [
            sys.executable,
            "-m",
            "mesh_cli",
            "release-preflight",
            "--no-verify-all",
        ],
        cwd=repo_root,
    )
    if preflight.returncode != 0:
        print(f"[Mesh][VersionBump] ERROR: release-preflight failed (code={int(preflight.returncode)})")
        if preflight.stdout:
            print(preflight.stdout.strip())
        if preflight.stderr:
            print(preflight.stderr.strip())
        return 2

    compile_result = _run_cmd(
        [
            sys.executable,
            "-m",
            "compileall",
            "-q",
            "engine",
            "mesh_cli",
            "tooling",
            "tests",
        ],
        cwd=repo_root,
    )
    if compile_result.returncode != 0:
        print(f"[Mesh][VersionBump] WARNING: compileall failed (code={int(compile_result.returncode)})")
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "version-bump",
        help="Bump package/public API versions with guardrails",
    )
    parser.add_argument("--to", required=True, help="Target package version (X.Y.Z)")
    parser.add_argument("--public-api", default="", help="Optional PUBLIC_API_SEMVER target (X.Y.Z)")
    parser.add_argument("--dry-run", action="store_true", help="Show unified diffs without writing files")
    parser.set_defaults(func=_handle_version_bump)


def handle(args: argparse.Namespace) -> int:
    return _handle_version_bump(args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mesh version-bump")
    parser.add_argument("--to", required=True)
    parser.add_argument("--public-api", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return _handle_version_bump(args)
