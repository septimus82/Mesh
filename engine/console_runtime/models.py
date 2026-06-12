from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    raw: str
    cmd: str
    args: list[str]
