from __future__ import annotations

import types

from engine.console_controller import ConsoleController
from engine.console_runtime.commands import dispatch_keys, parse_command_line


def test_parse_is_deterministic() -> None:
    parsed = parse_command_line("  XP   get   ")
    assert parsed is not None
    assert parsed.raw == "XP   get"
    assert parsed.cmd == "xp"
    assert parsed.args == ["get"]


def test_unknown_command_error_is_deterministic() -> None:
    controller = ConsoleController(types.SimpleNamespace())
    controller.execute_command("  does_not_exist   123 ")
    assert controller.lines[-2] == "does_not_exist   123"
    assert controller.lines[-1] == "Unknown command: does_not_exist"


def test_dispatch_table_key_order_is_stable() -> None:
    keys = list(dispatch_keys())
    assert keys == sorted(keys)

