from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from mesh_cli.version_info import get_version_file_path, read_tool_version

BumpKind = Literal["patch", "minor", "major"]
_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


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

