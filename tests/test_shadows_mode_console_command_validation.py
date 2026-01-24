from __future__ import annotations

from engine.console_runtime.commands import _dispatch_table


def test_shadows_mode_direct_sets_mode() -> None:
    class _Lighting:
        shadows_mode = "none"

        def set_shadows_mode(self, mode: str) -> str:
            if mode not in {"none", "hard", "direct"}:
                raise ValueError("invalid")
            self.shadows_mode = mode
            return self.shadows_mode

    class _Window:
        lighting = _Lighting()

    class _Console:
        def __init__(self) -> None:
            self.window = _Window()
            self.lines: list[str] = []

        def log(self, message: str) -> None:
            self.lines.append(message)

    dispatch = _dispatch_table()
    console = _Console()
    ok = dispatch["shadows_mode"](console, ["direct"])
    assert ok is True
    assert console.window.lighting.shadows_mode == "direct"


def test_shadows_mode_invalid_does_not_change_current_mode() -> None:
    class _Lighting:
        shadows_mode = "hard"

        def set_shadows_mode(self, mode: str) -> str:
            if mode not in {"none", "hard", "direct"}:
                raise ValueError("invalid")
            self.shadows_mode = mode
            return self.shadows_mode

    class _Window:
        lighting = _Lighting()

    class _Console:
        def __init__(self) -> None:
            self.window = _Window()
            self.lines: list[str] = []

        def log(self, message: str) -> None:
            self.lines.append(message)

    dispatch = _dispatch_table()
    console = _Console()
    ok = dispatch["shadows_mode"](console, ["potato"])
    assert ok is True
    assert console.window.lighting.shadows_mode == "hard"
    assert console.lines == ["Invalid shadows_mode: potato. Allowed: none, hard, direct"]

