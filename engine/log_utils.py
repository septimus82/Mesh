from __future__ import annotations

import logging
import re
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from engine.singletons import get_registry

_CONFIGURED = False
_LEVEL = logging.INFO
_JSON_MODE = False
_DETERMINISTIC = False
_HANDLER: logging.Handler | None = None
_BOUND_LOGGERS: set[str] = set()
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


class _DynamicStderrHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            sys.stderr.write(msg + "\n")
        except Exception:
            self.handleError(record)


def _formatter_for_mode() -> logging.Formatter:
    # Keep deterministic-friendly formatting as the default baseline.
    # In non-deterministic mode we intentionally avoid timestamps/PIDs too,
    # because many CLI contracts assert stable textual outputs.
    if _DETERMINISTIC:
        return logging.Formatter("%(levelname)s:%(name)s:%(message)s")
    return logging.Formatter("%(levelname)s:%(name)s:%(message)s")


def configure_logging(*, level: str = "INFO", json_mode: bool = False) -> None:
    global _CONFIGURED, _HANDLER, _LEVEL, _JSON_MODE
    _LEVEL = getattr(logging, str(level).upper(), logging.INFO)
    _JSON_MODE = bool(json_mode)

    if _HANDLER is None:
        _HANDLER = _DynamicStderrHandler()
    _HANDLER.setFormatter(_formatter_for_mode())

    for name in list(_BOUND_LOGGERS):
        logger = logging.getLogger(name)
        logger.setLevel(_LEVEL)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    if not _CONFIGURED:
        configure_logging()
    logger = logging.getLogger(str(name))
    if name not in _BOUND_LOGGERS:
        if _HANDLER is not None:
            logger.addHandler(_HANDLER)
        logger.setLevel(_LEVEL)
        logger.propagate = False
        _BOUND_LOGGERS.add(name)
    return logger


def set_deterministic_logging(enabled: bool) -> None:
    global _DETERMINISTIC
    _DETERMINISTIC = bool(enabled)
    if _HANDLER is not None:
        _HANDLER.setFormatter(_formatter_for_mode())


def is_json_mode() -> bool:
    return bool(_JSON_MODE)


def normalize_path(path: str | Path | PurePosixPath) -> str:
    raw = str(path).replace("\\", "/")
    if not raw:
        return "."

    # Strip Windows drive prefix deterministically.
    if _DRIVE_RE.match(raw):
        raw = raw[2:]

    pp = PurePosixPath(raw)
    norm = pp.as_posix()

    cwd = Path.cwd().as_posix().replace("\\", "/")
    cwd = cwd[2:] if _DRIVE_RE.match(cwd) else cwd
    if norm.startswith(cwd + "/"):
        norm = norm[len(cwd) + 1 :]
    elif norm == cwd:
        norm = "."

    norm = norm.lstrip("/")
    return norm or "."


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (Path, PurePosixPath)):
        return normalize_path(value)
    if isinstance(value, str):
        return value
    return repr(value)


def format_kv(data: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in sorted(str(k) for k in data.keys()):
        parts.append(f"{key}={_format_value(data[key])}")
    return " ".join(parts)


def _update_log_once_state(key: str) -> tuple[int, bool]:
    registry = get_registry()
    count = registry.log_once_counts.get(key, 0) + 1
    registry.log_once_counts[key] = count
    first = key not in registry.log_once_seen
    if first:
        registry.log_once_seen.add(key)
    return count, first


def log_once(
    key: str,
    message: str,
    *,
    logger: logging.Logger | None = None,
    level: int = logging.INFO,
) -> bool:
    _, first = _update_log_once_state(str(key))
    if first:
        target = logger if logger is not None else get_logger("engine.log_once")
        target.log(level, "%s", message)
    return first


def get_log_once_count(key: str) -> int:
    return int(get_registry().log_once_counts.get(str(key), 0))


def reset_log_once_state() -> None:
    registry = get_registry()
    registry.log_once_seen.clear()
    registry.log_once_counts.clear()

