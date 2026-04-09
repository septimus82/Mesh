from __future__ import annotations

from typing import Any, TypeVar, cast

T = TypeVar("T")


def as_any(value: T) -> Any:
    return cast(Any, value)
