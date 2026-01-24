from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


SAVE_FORMAT_VERSION = 1


def migrate_save_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Migrate a persisted save payload to the current save format.

    Versioning policy:
    - Missing `save_format_version` is treated as v0.
    - Versions newer than this engine are rejected (raises ValueError).
    """
    if not isinstance(payload, dict):
        raise ValueError("Save payload must be a JSON object")

    raw_version = payload.get("save_format_version")
    if raw_version is None:
        version = 0
    else:
        try:
            version = int(raw_version)
        except (TypeError, ValueError):
            version = 0

    if version > SAVE_FORMAT_VERSION:
        raise ValueError(
            f"Unsupported save_format_version {version} (engine supports up to {SAVE_FORMAT_VERSION})"
        )

    # v0 -> v1: add save_format_version (no semantic changes).
    if version < 1:
        payload["save_format_version"] = 1
        version = 1

    # Ensure the field is present for current version too.
    payload["save_format_version"] = int(payload.get("save_format_version", SAVE_FORMAT_VERSION) or SAVE_FORMAT_VERSION)
    return payload


def dumps_json_deterministic(
    payload: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = True,
    trailing_newline: bool = True,
) -> str:
    text = json.dumps(payload, indent=indent, sort_keys=sort_keys)
    if trailing_newline:
        return text + "\n"
    return text


def write_text_atomic(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write text to `path` atomically (temp + replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with open(tmp_path, "w", encoding=encoding, newline="\n") as handle:
        handle.write(text)
    os.replace(tmp_path, path)


def write_json_atomic(
    path: Path,
    payload: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = True,
    trailing_newline: bool = True,
    encoding: str = "utf-8",
) -> None:
    text = dumps_json_deterministic(
        payload,
        indent=indent,
        sort_keys=sort_keys,
        trailing_newline=trailing_newline,
    )
    write_text_atomic(path, text, encoding=encoding)


def read_json(path: Path, *, encoding: str = "utf-8") -> Any:
    with open(path, "r", encoding=encoding) as handle:
        return json.load(handle)
