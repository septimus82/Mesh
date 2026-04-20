from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


def _coerce_path(path: str | Path) -> Path:
    if isinstance(path, Path):
        return path
    if isinstance(path, str):
        return Path(path)
    raise TypeError(
        f"json_io._coerce_path: expected str or Path, got {type(path).__name__}"
    )


def _strip_bom(text: str, *, source: str = "") -> str:
    """Strip a leading UTF-8 BOM (U+FEFF) if present.

    Returns the cleaned text.  Emits a deterministic warning when a BOM is
    stripped so the root cause is visible in logs without breaking callers.
    """
    if text.startswith("\ufeff"):
        label = source or "<string>"
        _log.warning("Stripped UTF-8 BOM from JSON source: %s", label)
        return text[1:]
    return text


def dumps_stable(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
        separators=(",", ": "),
    )


def _fsync_parent_directory(path: Path) -> None:
    """Best-effort fsync of the parent directory after os.replace()."""
    dir_path = path.parent
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= int(getattr(os, "O_DIRECTORY"))
    try:
        dir_fd = os.open(str(dir_path), flags)
    except OSError:
        return
    try:
        os.fsync(dir_fd)
    except OSError:
        pass
    finally:
        os.close(dir_fd)


def write_text_atomic(
    path: str | Path,
    text: str,
    *,
    encoding: str = "utf-8",
    durable: bool = False,
) -> None:
    target = _coerce_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    try:
        with tmp_path.open("w", encoding=encoding, newline="\n") as handle:
            handle.write(text)
            if durable:
                handle.flush()
                os.fsync(handle.fileno())
        os.replace(tmp_path, target)
        if durable:
            _fsync_parent_directory(target)
    finally:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass


def write_json_atomic(
    path: str | Path,
    payload: Any,
    *,
    trailing_newline: bool = True,
    durable: bool = False,
) -> None:
    text = dumps_stable(payload)
    if trailing_newline and not text.endswith("\n"):
        text += "\n"
    write_text_atomic(path, text, encoding="utf-8", durable=durable)


def read_json(path: str | Path) -> Any:
    target = _coerce_path(path)
    text = target.read_text(encoding="utf-8")
    text = _strip_bom(text, source=str(target))
    return json.loads(text)


def loads_safe(text: str, *, source: str = "") -> Any:
    """Parse a JSON string, stripping a leading BOM if present."""
    return json.loads(_strip_bom(text, source=source))
