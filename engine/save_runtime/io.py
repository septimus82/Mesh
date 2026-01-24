from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.persistence_io import migrate_save_payload, read_json, write_json_atomic
from engine.save_runtime.errors import single_line_error


def write_json_pretty_atomic(path: Path, payload: Any) -> None:
    write_json_atomic(path, payload, indent=2, sort_keys=True, trailing_newline=True)


def load_snapshot_payload(path: Path) -> tuple[bool, dict[str, Any] | str]:
    if not path.exists():
        return False, ""

    try:
        data = read_json(path)
    except ValueError as exc:
        return False, f"[Mesh][Snapshot] ERROR: {single_line_error(str(exc))}"
    except Exception:
        return False, ""

    if not isinstance(data, dict):
        return False, ""

    try:
        return True, migrate_save_payload(data)
    except ValueError as exc:
        return False, f"[Mesh][Snapshot] ERROR: {single_line_error(str(exc))}"


def load_slot_payload(path: Path) -> tuple[bool, dict[str, Any] | str]:
    if not path.exists():
        return False, f"[Mesh][Save] Save file '{path}' not found"

    try:
        data = read_json(path)
    except Exception as exc:  # noqa: BLE001
        message = single_line_error(str(exc))
        return False, f"[Mesh][Save] ERROR: Failed to load game: {message or type(exc).__name__}"

    if not isinstance(data, dict):
        return False, "[Mesh][Save] ERROR: Save payload must be an object"

    try:
        return True, migrate_save_payload(data)
    except ValueError as exc:
        return False, f"[Mesh][Save] ERROR: {single_line_error(str(exc))}"


def write_snapshot_atomic(path: Path, payload: dict[str, Any]) -> None:
    write_json_pretty_atomic(path, payload)
