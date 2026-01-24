from __future__ import annotations

import json

from engine.console_runtime.commands import _dispatch_table


def test_console_prefab_source_command(monkeypatch) -> None:
    class _Manager:
        def __init__(self) -> None:
            self.prefab_sources = {"p_tree": "packs/beta/data/prefabs.json"}
            self.prefab_source_chain = {
                "p_tree": [
                    "assets/prefabs.json",
                    "packs/alpha/data/prefabs.json",
                    "packs/beta/data/prefabs.json",
                ]
            }

        def load(self) -> None:
            return

    monkeypatch.setattr("engine.prefabs.get_prefab_manager", lambda: _Manager())

    class _Console:
        def __init__(self) -> None:
            self.lines: list[str] = []

        def log(self, message: str) -> None:
            self.lines.append(message)

    dispatch = _dispatch_table()
    console = _Console()
    ok = dispatch["prefab_source"](console, ["p_tree"])
    assert ok is True
    assert console.lines == ["[Prefab] id=p_tree source=packs/beta/data/prefabs.json"]


def test_console_prefab_source_chain_command(monkeypatch) -> None:
    class _Manager:
        def __init__(self) -> None:
            self.prefab_source_chain = {
                "p_tree": [
                    "assets/prefabs.json",
                    "packs/alpha/data/prefabs.json",
                    "packs/beta/data/prefabs.json",
                ]
            }

        def load(self) -> None:
            return

    monkeypatch.setattr("engine.prefabs.get_prefab_manager", lambda: _Manager())

    class _Console:
        def __init__(self) -> None:
            self.lines: list[str] = []

        def log(self, message: str) -> None:
            self.lines.append(message)

    dispatch = _dispatch_table()
    console = _Console()
    ok = dispatch["prefab_source_chain"](console, ["p_tree"])
    assert ok is True
    assert (
        console.lines
        == [
            "[Prefab] id=p_tree chain=assets/prefabs.json -> packs/alpha/data/prefabs.json -> packs/beta/data/prefabs.json"
        ]
    )


def test_console_prefab_source_json_output(monkeypatch) -> None:
    class _Manager:
        def __init__(self) -> None:
            self.prefab_sources = {"p_tree": "packs/beta/data/prefabs.json"}

        def load(self) -> None:
            return

    monkeypatch.setattr("engine.prefabs.get_prefab_manager", lambda: _Manager())

    class _Console:
        def __init__(self) -> None:
            self.lines: list[str] = []

        def log(self, message: str) -> None:
            self.lines.append(message)

    dispatch = _dispatch_table()
    console = _Console()
    ok = dispatch["prefab_source"](console, ["p_tree", "--json"])
    assert ok is True
    expected = json.dumps(
        {
            "cmd": "prefab_source",
            "prefab_id": "p_tree",
            "source": "packs/beta/data/prefabs.json",
            "ok": True,
        },
        separators=(",", ":"),
    )
    assert console.lines == [expected]


def test_console_prefab_source_chain_json_output(monkeypatch) -> None:
    class _Manager:
        def __init__(self) -> None:
            self.prefab_source_chain = {
                "p_tree": [
                    "assets/prefabs.json",
                    "packs/alpha/data/prefabs.json",
                    "packs/beta/data/prefabs.json",
                ]
            }

        def load(self) -> None:
            return

    monkeypatch.setattr("engine.prefabs.get_prefab_manager", lambda: _Manager())

    class _Console:
        def __init__(self) -> None:
            self.lines: list[str] = []

        def log(self, message: str) -> None:
            self.lines.append(message)

    dispatch = _dispatch_table()
    console = _Console()
    ok = dispatch["prefab_source_chain"](console, ["p_tree", "--json"])
    assert ok is True
    expected = json.dumps(
        {
            "cmd": "prefab_source_chain",
            "prefab_id": "p_tree",
            "chain": [
                "assets/prefabs.json",
                "packs/alpha/data/prefabs.json",
                "packs/beta/data/prefabs.json",
            ],
            "ok": True,
        },
        separators=(",", ":"),
    )
    assert console.lines == [expected]
