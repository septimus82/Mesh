"""Contract tests for ``mesh new <name>`` command.

Tests cover:
- Creates expected directory structure and files
- Refuses to overwrite without --force; succeeds with --force
- Generated main.py is syntactically valid Python
- Generated config.json has required EngineConfig fields and correct start_scene
- Generated starter_room.json has a player entity with sprite_sheet and animations
- Generated starter_room.json has an NPC entity with Dialogue behaviour
- CLI dispatch integration (via mesh_cli.main)
- Name substitution in config and README
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

import mesh_cli

pytestmark = [pytest.mark.fast]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_new(name: str, dest: Path, extra_args: list[str] | None = None) -> int:
    """Run ``mesh new <name>`` via the CLI dispatcher."""
    args = ["new", name, "--dest", str(dest)]
    if extra_args:
        args.extend(extra_args)
    return mesh_cli.main(args)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDirectoryStructure:
    def test_creates_project_directory(self, tmp_path: Path) -> None:
        rc = _run_new("alpha", tmp_path)
        assert rc == 0
        assert (tmp_path / "alpha").is_dir()

    def test_creates_main_py(self, tmp_path: Path) -> None:
        _run_new("alpha", tmp_path)
        assert (tmp_path / "alpha" / "main.py").is_file()

    def test_creates_config_json(self, tmp_path: Path) -> None:
        _run_new("alpha", tmp_path)
        assert (tmp_path / "alpha" / "config.json").is_file()

    def test_creates_starter_room_scene(self, tmp_path: Path) -> None:
        _run_new("alpha", tmp_path)
        assert (tmp_path / "alpha" / "scenes" / "starter_room.json").is_file()

    def test_creates_readme(self, tmp_path: Path) -> None:
        _run_new("alpha", tmp_path)
        assert (tmp_path / "alpha" / "README.md").is_file()

    def test_creates_assets_dir(self, tmp_path: Path) -> None:
        _run_new("alpha", tmp_path)
        assert (tmp_path / "alpha" / "assets" / "sprites").is_dir()

    def test_creates_sprite_file(self, tmp_path: Path) -> None:
        _run_new("alpha", tmp_path)
        # Either the real sprite was copied or a placeholder was written — either way, file exists
        assert (tmp_path / "alpha" / "assets" / "sprites" / "animated_player.png").is_file()


class TestOverwriteGuard:
    def test_refuses_to_overwrite_existing_directory(self, tmp_path: Path) -> None:
        _run_new("beta", tmp_path)
        rc = _run_new("beta", tmp_path)
        assert rc != 0

    def test_force_flag_allows_overwrite(self, tmp_path: Path) -> None:
        _run_new("beta", tmp_path)
        rc = _run_new("beta", tmp_path, ["--force"])
        assert rc == 0
        assert (tmp_path / "beta" / "main.py").is_file()


class TestMainPy:
    def test_main_py_is_valid_python(self, tmp_path: Path) -> None:
        _run_new("gamma", tmp_path)
        source = (tmp_path / "gamma" / "main.py").read_text(encoding="utf-8")
        # Must parse without SyntaxError
        ast.parse(source)

    def test_main_py_imports_engine(self, tmp_path: Path) -> None:
        _run_new("gamma", tmp_path)
        source = (tmp_path / "gamma" / "main.py").read_text(encoding="utf-8")
        assert "from engine.config import load_config" in source
        assert "from engine.game import GameWindow" in source


class TestConfigJson:
    def test_config_json_is_valid_json(self, tmp_path: Path) -> None:
        _run_new("delta", tmp_path)
        text = (tmp_path / "delta" / "config.json").read_text(encoding="utf-8")
        cfg = json.loads(text)
        assert isinstance(cfg, dict)

    def test_config_start_scene_points_to_starter_room(self, tmp_path: Path) -> None:
        _run_new("delta", tmp_path)
        cfg = json.loads((tmp_path / "delta" / "config.json").read_text(encoding="utf-8"))
        assert cfg["start_scene"] == "scenes/starter_room.json"

    def test_config_has_required_engine_fields(self, tmp_path: Path) -> None:
        _run_new("delta", tmp_path)
        cfg = json.loads((tmp_path / "delta" / "config.json").read_text(encoding="utf-8"))
        for field in ("start_scene", "width", "height", "title"):
            assert field in cfg, f"config.json missing field '{field}'"

    def test_config_title_contains_project_name(self, tmp_path: Path) -> None:
        _run_new("MyProject", tmp_path)
        cfg = json.loads((tmp_path / "MyProject" / "config.json").read_text(encoding="utf-8"))
        assert "MyProject" in cfg["title"]


class TestStarterRoom:
    def _load_scene(self, tmp_path: Path, name: str = "epsilon") -> dict:
        _run_new(name, tmp_path)
        return json.loads(
            (tmp_path / name / "scenes" / "starter_room.json").read_text(encoding="utf-8")
        )

    def test_scene_is_valid_json(self, tmp_path: Path) -> None:
        scene = self._load_scene(tmp_path)
        assert isinstance(scene, dict)

    def test_scene_has_name(self, tmp_path: Path) -> None:
        scene = self._load_scene(tmp_path)
        assert "name" in scene

    def test_scene_has_player_entity(self, tmp_path: Path) -> None:
        scene = self._load_scene(tmp_path)
        players = [e for e in scene["entities"] if e.get("tag") == "player"]
        assert len(players) == 1

    def test_player_has_sprite_sheet(self, tmp_path: Path) -> None:
        scene = self._load_scene(tmp_path)
        player = next(e for e in scene["entities"] if e.get("tag") == "player")
        assert "sprite_sheet" in player
        ss = player["sprite_sheet"]
        assert "columns" in ss and "rows" in ss
        assert "frame_width" in ss and "frame_height" in ss

    def test_player_has_animations(self, tmp_path: Path) -> None:
        scene = self._load_scene(tmp_path)
        player = next(e for e in scene["entities"] if e.get("tag") == "player")
        assert "animations" in player
        assert "idle" in player["animations"]

    def test_npc_entity_present(self, tmp_path: Path) -> None:
        scene = self._load_scene(tmp_path)
        npcs = [e for e in scene["entities"] if "Dialogue" in e.get("behaviours", [])]
        assert len(npcs) >= 1

    def test_npc_has_dialogue_config(self, tmp_path: Path) -> None:
        scene = self._load_scene(tmp_path)
        npc = next(e for e in scene["entities"] if "Dialogue" in e.get("behaviours", []))
        dialogue = npc["behaviour_config"]["Dialogue"]["dialogue"]
        assert "speaker" in dialogue
        assert "start" in dialogue
        assert "nodes" in dialogue

    def test_scene_has_layers(self, tmp_path: Path) -> None:
        scene = self._load_scene(tmp_path)
        assert "layers" in scene
        layer_names = [layer["name"] for layer in scene["layers"]]
        assert "entities" in layer_names


class TestNameSubstitution:
    def test_readme_contains_project_name(self, tmp_path: Path) -> None:
        _run_new("CoolGame", tmp_path)
        readme = (tmp_path / "CoolGame" / "README.md").read_text(encoding="utf-8")
        assert "CoolGame" in readme

    def test_main_py_does_not_contain_literal_placeholder(self, tmp_path: Path) -> None:
        _run_new("TestGame", tmp_path)
        source = (tmp_path / "TestGame" / "main.py").read_text(encoding="utf-8")
        assert "{name}" not in source


class TestCLIDispatch:
    def test_new_command_registered_in_parser(self) -> None:
        parser = mesh_cli.create_parser()
        subparsers_action = next(
            a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction"
        )
        assert "new" in subparsers_action.choices

    def test_new_command_end_to_end_via_main(self, tmp_path: Path) -> None:
        rc = mesh_cli.main(["new", "e2e_test", "--dest", str(tmp_path)])
        assert rc == 0
        assert (tmp_path / "e2e_test" / "main.py").is_file()
        assert (tmp_path / "e2e_test" / "config.json").is_file()
        assert (tmp_path / "e2e_test" / "scenes" / "starter_room.json").is_file()
