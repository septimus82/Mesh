"""#642: an MCP cutscene edit is checked before it is written, and a bad cutscenes.json never stops a project opening.

Before: ``apply_ops`` wrote any cutscene step (``{"type": "fade_to_black"}``, no such step) and reported success, its
validation pass didn't look at cutscenes.json, and ``GameWindow.__init__`` then raised SchemaValidationError: neither
the game nor Mesh Studio (which builds the GameWindow first) could open the project. Now the cutscene operations
refuse a document ``cutscene.schema.json`` rejects (the file stays byte-identical), validation reports a bad file, and
the window sets a bad file aside with a log line and a notice (a toast; Mesh Studio's status line).
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from engine.mcp_server import tools
from engine.project_scaffold import create_project
from tests._game_window_live import dispose_game_window

pytestmark = pytest.mark.integration  # (F13-A: project files, the ownership lock, hidden windows)

GOOD = {"cutscenes": [{"id": "intro", "steps": [{"type": "wait", "duration": 1}]}]}
BROKEN = {  # by hand: no such step type
    "schema": json.dumps({"cutscenes": [{"id": "intro", "steps": [{"type": "fade_to_black"}]}]}),
    "json": '{"cutscenes": [',
}
REFUSED_OPS = {
    "unknown step type (the issue's op)": {"type": "add_cutscene", "id": "outro", "steps": [{"type": "fade_to_black"}]},
    "missing required field": {"type": "add_cutscene", "id": "outro", "steps": [{"type": "wait"}]},
    "update with an unknown field": {"type": "update_cutscene", "id": "intro",
                                     "steps": [{"type": "wait", "duration": 1, "seconds": 2}]},
    "insert an unknown step": {"type": "insert_cutscene_step", "id": "intro", "step": {"type": "fade_to_black"}},
    "patch a step out of shape": {"type": "update_cutscene_step", "id": "intro", "index": 0,
                                  "patch": {"duration": "long"}},
}


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "game"
    create_project(path, "Game", template_id="blank")
    return path


def _cutscenes(root: Path) -> Path:
    return root / "cutscenes.json"


@pytest.mark.parametrize("op", list(REFUSED_OPS))
def test_apply_ops_refuses_a_cutscene_the_game_cant_load_and_writes_nothing(root: Path, op: str) -> None:
    _cutscenes(root).write_text(json.dumps(GOOD), encoding="utf-8")
    before = _cutscenes(root).read_bytes()
    result = tools.apply_ops([REFUSED_OPS[op]], root=str(root))
    assert result["ok"] is False
    message = result["results"][0]["message"]
    assert message.startswith("Refused, nothing written: Schema validation failed for 'cutscenes.json'"), message
    assert "list_op_types" in message
    if "unknown step" in op:  # (#676: the type is named, not a field of some other step shape)
        assert "unknown step type 'fade_to_black'" in message and "is a required property" not in message, message
    assert _cutscenes(root).read_bytes() == before


def test_apply_ops_refuses_the_issues_op_on_a_new_project_and_creates_no_file(root: Path) -> None:
    existed = _cutscenes(root).read_bytes() if _cutscenes(root).exists() else None
    result = tools.apply_ops([REFUSED_OPS["unknown step type (the issue's op)"]], root=str(root))
    assert result["ok"] is False and "/cutscenes/0/steps/0" in result["results"][0]["message"]
    assert (_cutscenes(root).read_bytes() if _cutscenes(root).exists() else None) == existed


def test_apply_ops_writes_valid_cutscene_steps(root: Path) -> None:
    result = tools.apply_ops([
        {"type": "add_cutscene", "id": "intro", "steps": [
            {"type": "start_dialogue", "lines": [{"speaker": "Keeper", "text": "Welcome."}]},
            {"type": "wait_dialogue_end"},
            {"type": "move_entity", "entity": "Keeper", "x": 64, "y": 32, "duration": 1.5},
        ]},
        {"type": "insert_cutscene_step", "id": "intro", "index": 0, "step": {"type": "wait", "duration": 0.5}},
        {"type": "update_cutscene_step", "id": "intro", "index": 0, "patch": {"duration": 2}},
        {"type": "add_cutscene", "id": "outro", "steps": [{"type": "set_flag", "flag": "seen_outro"}]},
    ], root=str(root))
    assert result["ok"] is True, result
    assert result["validation"]["ok"] is True, result["validation"]
    written = json.loads(_cutscenes(root).read_text(encoding="utf-8"))["cutscenes"]
    assert [c["id"] for c in written] == ["intro", "outro"]
    assert written[0]["steps"][0] == {"type": "wait", "duration": 2}


@pytest.mark.parametrize("broken", list(BROKEN))
def test_validation_reports_a_bad_cutscenes_file(root: Path, broken: str) -> None:
    _cutscenes(root).write_text(BROKEN[broken], encoding="utf-8")
    report = tools.validate_scene(root=str(root))
    assert report["ok"] is False
    assert any("cutscenes.json" in error for error in report["data"]["errors"]), report
    after_op = tools.apply_ops([{"type": "delete_cutscene", "id": "nothing"}], root=str(root))["validation"]
    assert after_op["ok"] is False and after_op["data"]["errors"] == report["data"]["errors"]


def test_the_catalogue_gives_every_cutscene_step_the_schema_allows() -> None:
    """The step format an AI is given (``list_op_types``) names every step type and field of cutscene.schema.json,
    marks the required ones as required, and nothing else."""
    schema = json.loads((Path(tools.__file__).parents[1] / "schemas" / "cutscene.schema.json").read_text(encoding="utf-8"))
    defs = schema["$defs"]
    text = tools.CUTSCENE_STEP_FORMAT
    step_types = []
    for ref in defs["cutsceneStep"]["oneOf"]:
        step = defs[ref["$ref"].rsplit("/", 1)[1]]
        step_type = step["properties"]["type"]["const"]
        step_types.append(step_type)
        segment = re.search(rf"\b{step_type} \{{([^}}]*)\}}", text)
        assert segment is not None, step_type
        fields = segment.group(1)
        assert set(re.findall(r"[a-z_]+", fields)) == set(step["properties"]) - {"type"}, step_type
        for required in set(step["required"]) - {"type"}:
            assert re.search(rf"\b{required}\b(?!\?)", fields), (step_type, required)
    assert set(re.findall(r"(?:^|; |: )([a-z_]+) \{", text)) == set(step_types)
    rows = {row["type"]: row for row in tools.list_op_types()}
    for op in ("add_cutscene", "update_cutscene", "insert_cutscene_step", "update_cutscene_step"):
        assert rows[op]["step_format"] == text


# ------------------------------------------------------------------ a hand-broken file: the project still opens
def _game_window(root: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    from engine.config import EngineConfig
    from engine.game import GameWindow

    monkeypatch.chdir(root)  # (as `mesh play` / `mesh edit` run: in the project)
    cfg = EngineConfig(width=320, height=200, title="#642", vsync=False, start_scene="", world_file=None,
                       main_menu_scene=None, master_volume=0.0)
    return GameWindow(width=320, height=200, title=cfg.title, vsync=False, config=cfg)


@pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")
@pytest.mark.parametrize("broken", list(BROKEN))
def test_a_bad_cutscenes_file_lets_the_game_start_and_says_so(root: Path, broken: str,
                                                               monkeypatch: pytest.MonkeyPatch) -> None:
    _cutscenes(root).write_text(BROKEN[broken], encoding="utf-8")
    records: list[logging.LogRecord] = []
    handler = logging.Handler(logging.ERROR)
    handler.emit = records.append  # type: ignore[method-assign]
    logging.getLogger("engine.game").addHandler(handler)  # (the engine's loggers don't reach caplog)
    try:
        window = _game_window(root, monkeypatch)
    finally:
        logging.getLogger("engine.game").removeHandler(handler)
    try:
        said = window.cutscenes_error
        assert said and said.startswith("cutscenes.json is set aside")
        if broken == "schema":
            assert "/cutscenes/0/steps/0" in said
        assert any(said in record.getMessage() for record in records)  # the log
        assert said in window.player_hud.active_toasts()  # on screen
        assert window.cutscene_controller.cutscenes == {}
    finally:
        dispose_game_window(window)


@pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")
def test_a_good_cutscenes_file_loads_without_a_notice(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _cutscenes(root).write_text(json.dumps(GOOD), encoding="utf-8")
    window = _game_window(root, monkeypatch)
    try:
        assert window.cutscenes_error is None and set(window.cutscene_controller.cutscenes) == {"intro"}
        assert not any("cutscenes.json" in toast for toast in window.player_hud.active_toasts())
    finally:
        dispose_game_window(window)


@pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                    reason="Mesh Studio needs a real GL context (set MESH_GL_SMOKE=1)")
@pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function")
@pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning")
def test_mesh_edit_opens_mesh_studio_on_a_bad_cutscenes_file_and_says_so(root: Path,
                                                                         monkeypatch: pytest.MonkeyPatch) -> None:
    from engine import game_launch

    _cutscenes(root).write_text(BROKEN["schema"], encoding="utf-8")
    monkeypatch.delenv("MESH_LEGACY_EDITOR", raising=False)
    monkeypatch.setenv("MESH_STUDIO_NO_AI_BRIDGE", "1")
    seen: dict[str, Any] = {}

    def opened(window: Any) -> None:  # (the window loop, as `mesh edit` runs it: one frame, then closed)
        window._allow_dispatch_event = True
        window.dispatch_event("on_update", 1 / 60)
        studio = window.studio
        seen.update(error=window.cutscenes_error, said=set(studio._weather_said), message=studio.message)
        dispose_game_window(window)

    monkeypatch.setattr(game_launch.GameWindow, "run", opened)
    assert game_launch.launch_editor(project_root=root) == 0
    assert seen["error"] and "/cutscenes/0/steps/0" in seen["error"]
    assert seen["error"] in seen["said"]  # (Studio's status line, as it says a room's set-aside weather)
