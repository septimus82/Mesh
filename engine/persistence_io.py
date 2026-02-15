from __future__ import annotations

from pathlib import Path
from typing import Any

from . import json_io


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
    _ = (indent, sort_keys)
    text = json_io.dumps_stable(payload)
    if trailing_newline:
        return text + "\n"
    return text


def write_text_atomic(
    path: Path | str,
    text: str,
    *,
    encoding: str = "utf-8",
    durable: bool = False,
) -> None:
    """Write text to `path` atomically (temp + replace)."""
    json_io.write_text_atomic(path, text, encoding=encoding, durable=durable)


def write_json_atomic(
    path: Path | str,
    payload: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = True,
    trailing_newline: bool = True,
    encoding: str = "utf-8",
    durable: bool = False,
) -> None:
    _ = (indent, sort_keys, encoding)
    text = dumps_json_deterministic(payload, trailing_newline=trailing_newline)
    json_io.write_text_atomic(path, text, encoding="utf-8", durable=durable)


def read_json(path: Path | str, *, encoding: str = "utf-8") -> Any:
    _ = encoding
    return json_io.read_json(path)
