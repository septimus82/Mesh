from __future__ import annotations

import contextlib
import io
from typing import Iterator

from engine.log_utils import (
    configure_logging as _configure_logging,
    get_logger as _get_logger,
    is_json_mode as _is_json_mode,
)


def configure_logging(*, level: str = "INFO", json_mode: bool = False) -> None:
    _configure_logging(level=level, json_mode=json_mode)


def get_logger(name: str):
    return _get_logger(name)


@contextlib.contextmanager
def suppress_stdout() -> Iterator[io.StringIO]:
    """Temporarily redirect stdout to an in-memory buffer, restoring it on exit."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield buf


def is_json_mode() -> bool:
    return _is_json_mode()

