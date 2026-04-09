"""CLI command: ``mesh_cli artifacts-validate``

Validates the artifact bundle produced by ``verify-all --ci-bundle`` by
checking that ``index.json`` is present, every referenced artifact file
exists, parses as JSON, and declared schema versions match.

Headless-safe — no engine or arcade imports.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_INDEX_REQUIRED_KEYS = frozenset(
    ["ok", "verify_all", "written", "readable", "generated_files"]
)


def _safe_read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Read a JSON file.  Returns ``(data, None)`` on success or ``(None, err)``."""
    if not path.exists() or not path.is_file():
        return None, f"file not found: {path.as_posix()}"
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        return None, f"unreadable JSON: {path.as_posix()}: {type(exc).__name__}"
    if not isinstance(data, dict):
        return None, f"unreadable JSON: {path.as_posix()}: expected object"
    return data, None


def _normalize_written_path(value: str) -> str:
    """Strip a leading ``artifacts/`` prefix so the basename can be joined
    with the actual artifacts directory.

    >>> _normalize_written_path("artifacts/exception_budget.json")
    'exception_budget.json'
    >>> _normalize_written_path("exception_budget.json")
    'exception_budget.json'
    """
    parts = value.replace("\\", "/").split("/")
    # If the first component looks like the artifacts dir name, drop it.
    if len(parts) > 1:
        return "/".join(parts[1:])
    return parts[0]


def _strip_artifacts_dir_name_prefix(path_value: str, artifacts_dir_name: str) -> str:
    """Strip a leading ``<artifacts_dir_name>/`` path prefix when present."""
    normalized = path_value.replace("\\", "/").lstrip("/")
    normalized_dir_name = artifacts_dir_name.strip().replace("\\", "/").strip("/")
    prefix = f"{normalized_dir_name}/"
    if prefix and normalized.startswith(prefix):
        return normalized[len(prefix) :]
    return normalized


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------


def validate_artifacts(artifacts_dir: Path) -> tuple[bool, list[str]]:
    """Validate the artifact bundle under *artifacts_dir*.

    Returns ``(ok, issues)`` where *issues* is a sorted list of
    human-readable single-line strings.
    """
    issues: list[str] = []

    # 1) index.json existence + parse
    index_path = artifacts_dir / "index.json"
    index, err = _safe_read_json(index_path)
    if index is None:
        issues.append(f"missing_index: {index_path.as_posix()}: {err}")
        return False, issues

    # 1b) schema_version / bundle_schema_version
    sv = index.get("schema_version")
    if sv != 1:
        issues.append(
            f"schema_mismatch: index.json: schema_version expected 1 got {sv!r}"
        )
    bsv = index.get("bundle_schema_version")
    if bsv != 1:
        issues.append(
            f"schema_mismatch: index.json: bundle_schema_version expected 1 got {bsv!r}"
        )

    # 1c) required keys
    for key in sorted(_INDEX_REQUIRED_KEYS):
        if key not in index:
            issues.append(f"missing_key: index.json: {key}")

    # 2) Written path existence
    written: dict[str, str | None] = index.get("written", {})
    if not isinstance(written, dict):
        issues.append("unreadable_json: index.json: 'written' is not an object")
        return False, sorted(issues)

    schemas: dict[str, int] = index.get("schemas", {})
    if not isinstance(schemas, dict):
        schemas = {}

    for key in sorted(written.keys()):
        value = written[key]
        if value is None:
            continue
        basename = _normalize_written_path(str(value))
        basename = _strip_artifacts_dir_name_prefix(basename, artifacts_dir.name)
        full_path = artifacts_dir / basename
        if not full_path.exists() or not full_path.is_file():
            issues.append(f"missing_file: {key}: {full_path.as_posix()}")
            continue

        # Non-JSON artifacts (e.g. release_notes.md) are existence-only checks.
        if full_path.suffix.lower() != ".json":
            continue

        # 3) JSON parse + schema checks
        data, parse_err = _safe_read_json(full_path)
        if data is None:
            issues.append(f"unreadable_json: {key}: {parse_err}")
            continue

        expected_sv = schemas.get(key)
        if isinstance(expected_sv, int):
            actual_sv = data.get("schema_version")
            if actual_sv is None:
                issues.append(
                    f"missing_schema_version: {key}: expected {expected_sv}"
                )
            elif actual_sv != expected_sv:
                issues.append(
                    f"schema_mismatch: {key}: expected {expected_sv} got {actual_sv}"
                )

    return len(issues) == 0, sorted(issues)


# ---------------------------------------------------------------------------
# CLI entry points
# ---------------------------------------------------------------------------


def _handle_artifacts_validate(args: argparse.Namespace) -> int:
    raw = str(getattr(args, "artifacts", "") or "").strip() or "artifacts"
    artifacts_dir = Path(raw)
    if not artifacts_dir.is_absolute():
        artifacts_dir = Path.cwd() / artifacts_dir

    ok, issues = validate_artifacts(artifacts_dir)

    if ok:
        print("artifacts-validate: ok")
        return 0

    print(f"artifacts-validate: FAILED ({len(issues)} issues)")
    for issue in issues:
        print(f"  - {issue}")
    return 2


def register(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "artifacts-validate",
        help="Validate verify-all artifact bundle index",
    )
    parser.add_argument(
        "--artifacts",
        default="artifacts",
        help="Artifact directory containing verify outputs (default: artifacts)",
    )
    parser.set_defaults(func=_handle_artifacts_validate)


def handle(args: argparse.Namespace) -> int:
    return _handle_artifacts_validate(args)
