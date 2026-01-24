import json
from pathlib import Path
from unittest.mock import MagicMock

from engine.config import EngineConfig
from engine.tooling.check import run_check


class _StubContentIndex:
    def __init__(self) -> None:
        self.packs = []

    def build(self) -> None:
        return


def test_mesh_check_fails_when_required_binding_missing(tmp_path: Path, monkeypatch, capsys) -> None:
    world_path = tmp_path / "world.json"
    world_path.write_text(json.dumps({"scenes": {}, "links": []}), encoding="utf-8")

    cfg = EngineConfig()
    cfg.input_bindings = {
        "move_up": ["W"],
        "move_down": ["S"],
        "move_left": ["A"],
        "move_right": ["D"],
        "interact": ["E"],
        "attack": ["SPACE"],
        "show_quests": ["Q"],
        "show_inventory": ["TAB"],
        "show_character": ["C"],
        # missing toggle_editor / toggle_help
    }

    monkeypatch.setattr("engine.tooling.check.get_content_index", lambda refresh=True: _StubContentIndex())  # noqa: ARG005
    monkeypatch.setattr("engine.tooling.check.validate_pack_dependencies", lambda packs: [])  # noqa: ARG005
    monkeypatch.setattr("engine.tooling.check.load_config", lambda path="config.json": cfg)  # noqa: ARG005
    monkeypatch.setattr("engine.tooling.check.subprocess.run", lambda *a, **k: MagicMock(returncode=0))

    assert run_check(str(world_path)) is False
    out = capsys.readouterr().out
    assert "Wiring FAILED" in out
    assert "Unbound required action(s)" in out
    assert "[CHECK] Next:" in out
    assert f"mesh doctor --world {world_path}" in out
    assert "mesh explain --last" in out


def test_mesh_check_fails_when_binding_unknown_action(tmp_path: Path, monkeypatch, capsys) -> None:
    world_path = tmp_path / "world.json"
    world_path.write_text(json.dumps({"scenes": {}, "links": []}), encoding="utf-8")

    cfg = EngineConfig()
    cfg.input_bindings = {
        "move_up": ["W"],
        "move_down": ["S"],
        "move_left": ["A"],
        "move_right": ["D"],
        "interact": ["E"],
        "attack": ["SPACE"],
        "show_quests": ["Q"],
        "show_inventory": ["TAB"],
        "show_character": ["C"],
        "toggle_editor": ["F2"],
        "toggle_help": ["H"],
        "definitely_not_real": ["F10"],
    }

    monkeypatch.setattr("engine.tooling.check.get_content_index", lambda refresh=True: _StubContentIndex())  # noqa: ARG005
    monkeypatch.setattr("engine.tooling.check.validate_pack_dependencies", lambda packs: [])  # noqa: ARG005
    monkeypatch.setattr("engine.tooling.check.load_config", lambda path="config.json": cfg)  # noqa: ARG005
    monkeypatch.setattr("engine.tooling.check.subprocess.run", lambda *a, **k: MagicMock(returncode=0))

    assert run_check(str(world_path)) is False
    out = capsys.readouterr().out
    assert "Wiring FAILED" in out
    assert "Unknown bound action(s)" in out
    assert "[CHECK] Next:" in out
    assert f"mesh doctor --world {world_path}" in out
    assert "mesh explain --last" in out
