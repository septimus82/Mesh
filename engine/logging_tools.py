from __future__ import annotations

import contextlib
import io
import logging
import sys
from typing import Iterator


_CONFIGURED = False
_JSON_MODE = False
_LEVEL = logging.INFO
_HANDLER: logging.Handler | None = None
_BOUND_LOGGERS: set[str] = set()


class _DynamicStderrHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            sys.stderr.write(msg + "\n")
        except Exception:
            self.handleError(record)


def configure_logging(*, level: str = "INFO", json_mode: bool = False) -> None:
    """Configure lightweight loggers once.

    This intentionally does *not* mutate the root logger (pytest and other
    tooling may install handlers that must not be touched).
    """
    global _CONFIGURED, _HANDLER, _LEVEL, _JSON_MODE

    _LEVEL = getattr(logging, str(level).upper(), logging.INFO)
    _JSON_MODE = bool(json_mode)

    if _HANDLER is None:
        _HANDLER = _DynamicStderrHandler()
        _HANDLER.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))

    # Update already-created loggers to the latest level (if any exist).
    for name in list(_BOUND_LOGGERS):
        logger = logging.getLogger(name)
        logger.setLevel(_LEVEL)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    logger = logging.getLogger(name)
    if name not in _BOUND_LOGGERS:
        if _HANDLER is not None:
            logger.addHandler(_HANDLER)
        logger.setLevel(_LEVEL)
        logger.propagate = False
        _BOUND_LOGGERS.add(name)
    return logger


@contextlib.contextmanager
def suppress_stdout() -> Iterator[io.StringIO]:
    """Temporarily redirect stdout to an in-memory buffer, restoring it on exit."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield buf


def is_json_mode() -> bool:
    return bool(_JSON_MODE)
