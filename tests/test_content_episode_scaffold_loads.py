"""#676: ``mesh content episode new`` appended cutscene entries carrying ``schema_version`` and ``commands`` (the second
cutscene runtime's script shape) to the project's ``cutscenes.json``. ``cutscene.schema.json`` allows ``id`` and
``steps`` only, so the game set the whole file aside (before #674 the project couldn't start at all), and every MCP
cutscene write to it was refused. The scaffold now writes the game's shape, checks the file as the game's loader does
before writing anything, and ``mesh episode`` still builds its runner from the entries' steps.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
import mesh_cli
from mesh_cli.content_scaffold import build_episode_scaffold_plan
from tests._game_window_live import dispose_game_window

pytestmark = pytest.mark.integration  # (project files on disk; a hidden window)

ARGS = ["content", "episode", "new", "--id", "ep02", "--title", "Signal in the Dust"]


def _project(root: Path) -> Path:
    """A project with the registries the scaffold appends to."""
    files: dict[str, Any] = {
        "config.json": {"title": "Game", "width": 320, "height": 200, "vsync": False, "main_menu_scene": None},
        "assets/data/events.json": {"events": []},
        "assets/data/quests.json": {"quests": []},
        "cutscenes.json": {"cutscenes": [{"id": "existing", "steps": [{"type": "wait", "duration": 1}]}]},
        "assets/prefabs.json": [{"id": "player", "display_name": "Player", "tags": ["player"], "entity": {"sprite": "assets/placeholder.png", "behaviours": [],
                                                             "behaviour_config": {}}}],
    }
    for rel, payload in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return root


def _files(root: Path) -> dict[str, bytes]:
    """The project's files, but Mesh's own ``.mesh/`` (the ownership lock a writer takes)."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and ".mesh" not in p.relative_to(root).parts}


def _game_window(root: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    from engine.config import EngineConfig
    from engine.game import GameWindow

    monkeypatch.chdir(root)  # (as `mesh play` / `mesh edit` run: in the project)
    cfg = EngineConfig(width=320, height=200, title="#676", vsync=False, start_scene="", world_file=None,
                       main_menu_scene=None, master_volume=0.0)
    return GameWindow(width=320, height=200, title=cfg.title, vsync=False, config=cfg)


@pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")
def test_a_scaffolded_episodes_cutscenes_load_in_the_game_and_in_mesh_episode(tmp_path: Path,
                                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.schema_validation import validate
    from mesh_cli.episode import _build_cutscene_runner, _build_window, _load_cutscene_script

    root = _project(tmp_path / "game")
    assert mesh_cli.main([*ARGS, "--out-dir", str(root)]) == 0
    plan = build_episode_scaffold_plan(episode_id="ep02", title="Signal in the Dust", out_dir=root, seed=123)
    payload = json.loads((root / "cutscenes.json").read_text(encoding="utf-8"))
    validate(payload, "cutscene.schema.json", "cutscenes.json")  # (raises with the offending pointer)

    window = _game_window(root, monkeypatch)
    try:
        assert window.cutscenes_error is None
        assert set(window.cutscene_controller.cutscenes) == {"existing", plan.cutscene_intro_id, plan.cutscene_outro_id}
    finally:
        dispose_game_window(window)

    # `mesh episode` (the second runtime) builds its commands from the steps; the intro still hands over to dialogue
    intro = _load_cutscene_script(plan.cutscene_intro_id, payload)
    assert intro is not None
    assert [c["type"] for c in intro["commands"]] == ["wait", "emit_event", "start_dialogue"]
    assert intro["commands"][1]["event_type"] == plan.event_intro_done
    for cutscene_id in (plan.cutscene_intro_id, plan.cutscene_outro_id):
        script = _load_cutscene_script(cutscene_id, payload)
        assert script is not None
        _build_cutscene_runner(_build_window(), script)  # (raises on load errors)


def test_a_cutscenes_file_the_game_cant_load_is_refused_and_nothing_is_written(
        tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _project(tmp_path / "game")
    (root / "cutscenes.json").write_text(json.dumps(
        {"cutscenes": [{"id": "existing", "steps": [{"type": "fade_to_black"}]}]}), encoding="utf-8")
    before = _files(root)
    assert mesh_cli.main([*ARGS, "--out-dir", str(root)]) == 2
    assert "refusing to write a cutscene file the game can't load" in capsys.readouterr().out
    assert _files(root) == before
