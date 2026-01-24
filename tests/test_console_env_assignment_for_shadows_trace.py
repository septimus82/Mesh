from __future__ import annotations


def test_console_allows_mesh_shadows_trace_assignment(monkeypatch) -> None:
    from engine.console_runtime.commands import dispatch_command

    class _Console:
        def __init__(self) -> None:
            self.lines: list[str] = []

        def log(self, message: str) -> None:
            self.lines.append(message)

    monkeypatch.delenv("MESH_SHADOWS_TRACE", raising=False)
    console = _Console()
    ok = dispatch_command(console, "mesh_shadows_trace=1", [])
    assert ok is True
    import os

    assert os.environ.get("MESH_SHADOWS_TRACE") == "1"
    assert console.lines == ["[Lighting] MESH_SHADOWS_TRACE=1"]

