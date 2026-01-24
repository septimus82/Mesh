from __future__ import annotations

from engine.console_runtime.models import ParsedCommand


def parse_command_line(command: str) -> ParsedCommand | None:
    raw = str(command or "").strip()
    if not raw:
        return None
    parts = raw.split()
    if not parts:
        return None
    cmd = parts[0].lower()
    return ParsedCommand(raw=raw, cmd=cmd, args=parts[1:])
