"""The Mesh launcher's checks, the beginner templates, and keeping games out of the engine folder."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine import project_ops as ops
from engine import projects
from engine.launcher import ENGINE_ROOT, check_existing_project, check_new_project, studio_command
from engine.project_scaffold import create_project
from engine.project_templates import list_templates
from engine.studio_project import Project

pytestmark = pytest.mark.fast


def test_new_project_checks_explain_every_refusal(tmp_path) -> None:
    assert check_new_project("", str(tmp_path))[1] == "Give your game a name."
    assert "can't contain" in check_new_project("a/b", str(tmp_path))[1]
    assert "Windows doesn't allow" in check_new_project("CON", str(tmp_path))[1]
    assert "Choose where" in check_new_project("Game", "")[1]
    assert "full folder path" in check_new_project("Game", "relative/dir")[1]
    assert "outside the Mesh engine folder" in check_new_project("Game", str(ENGINE_ROOT))[1]
    (tmp_path / "Taken").mkdir()
    (tmp_path / "Taken" / "notes.txt").write_text("mine", encoding="utf-8")
    assert "already a folder" in check_new_project("Taken", str(tmp_path))[1]
    create_project(tmp_path / "Existing", "Existing", template_id="blank")
    assert "already a Mesh project" in check_new_project("Existing", str(tmp_path))[1]
    target, problem = check_new_project("Mitt spel – Åäö", str(tmp_path / "with space"))
    assert problem == "" and target == tmp_path / "with space" / "Mitt spel – Åäö"
    assert not (tmp_path / "with space").exists(), "checking never creates anything"


def test_existing_project_checks(tmp_path) -> None:
    assert "isn't there any more" in check_existing_project(str(tmp_path / "gone"))[1]
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    assert "is a file" in check_existing_project(str(tmp_path / "file.txt"))[1]
    assert "no config.json" in check_existing_project(str(tmp_path))[1]
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "config.json").write_text("{not json", encoding="utf-8")
    assert "can't be read" in check_existing_project(str(tmp_path / "broken"))[1]
    create_project(tmp_path / "Good Game", "Good Game", template_id="blank")
    assert check_existing_project(f'"{tmp_path / "Good Game"}"') == ((tmp_path / "Good Game").resolve(), "")


def test_studio_runs_in_its_own_process_with_the_engine_importable(tmp_path) -> None:
    command, env = studio_command(tmp_path)
    assert command[1:] == ["-m", "mesh_cli", "edit", str(tmp_path)]
    assert env["PYTHONPATH"].split(";" if sys.platform == "win32" else ":")[0] == str(ENGINE_ROOT)


def test_the_launcher_offers_blank_and_adventure_with_pictures() -> None:
    offered = list_templates(launcher_only=True)
    assert [t.id for t in offered] == ["blank", "adventure"]
    for template in offered:
        assert (ENGINE_ROOT / template.preview).is_file(), f"run tooling/make_template_previews.py ({template.id})"
    assert {"starter", "lighting_playground", "demo_slice", "monster"} <= {t.id for t in list_templates()}


def _open(root: Path) -> Project:
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    project = Project.open(root, config["world_file"])
    assert project is not None
    return project


def test_blank_is_an_empty_editable_map_with_no_monster_or_demo_content(tmp_path) -> None:
    root = tmp_path / "blank"
    create_project(root, "Blank", template_id="blank")
    project = _open(root)
    assert [label for _, label, _ in project.rooms()] == ["Start"]
    scene = project.scene()
    assert [e["tag"] for e in ops.entities(scene)] == ["player"]
    info = ops.map_info(scene)
    assert set(info["layers"][ops.GROUND]) == {ops.STARTER_GRASS} and not any(info["layers"][ops.WALLS])
    files = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    assert not [f for f in files if "monster" in f or "sproutling" in f or "shelltide" in f or "quest" in f], files
    prefabs = {p["id"]: p for p in json.loads((root / "assets/prefabs.json").read_text(encoding="utf-8"))}
    assert list(prefabs) == ["player", "person", "sign"]
    # Mesh's own starter art, not the coloured "no picture" placeholder: a player and a person you can tell apart.
    assert prefabs["player"]["entity"]["sprite"] == "assets/sprites/starter_hero.png"
    assert prefabs["person"]["entity"]["sprite"] == "assets/sprites/starter_villager.png"
    assert {"assets/sprites/starter_hero.png", "assets/sprites/starter_villager.png", "assets/sprites/starter_sign.png"} <= files
    assert ops.animation_clips(prefabs["player"]["entity"]).keys() >= {"walk_up", "walk_down", "walk_left", "walk_right"}
    assert prefabs["person"]["entity"]["behaviour_config"]["Dialogue"]["once"] is False  # they answer every time


def test_adventure_has_two_linked_rooms_a_talking_npc_and_walls(tmp_path) -> None:
    root = tmp_path / "adventure"
    create_project(root, "Adventure", template_id="adventure")
    project = _open(root)
    assert [label for _, label, _ in project.rooms()] == ["Village", "House"]
    village, house = project.scene("start"), project.scene("house")
    for scene, other in ((village, "house"), (house, "start")):
        assert ops.scene_errors(scene) == []
        door = next(e for e in ops.entities(scene) if e.get("tag") == "door")
        assert door["behaviour_config"]["SceneTransition"]["target_scene"] == other
    guide = next(e for e in ops.entities(village) if e.get("name") == "Guide")
    assert "save" in ops.dialogue_text(guide)
    walls = ops.map_info(village)["layers"][ops.WALLS]
    assert sum(1 for gid in walls if gid) > 30, "the house, pond, fence and trees block the way"
    player = next(e for e in ops.entities(village) if e.get("tag") == "player")
    col, row = ops.cell_at(ops.map_info(village), player["x"], player["y"])
    assert walls[row * 24 + col] == 0, "the player doesn't start inside a wall"


@pytest.mark.parametrize("template_id", ["blank", "adventure", "starter"])
def test_generated_project_code_is_lint_clean(tmp_path, template_id) -> None:
    root = tmp_path / "game"
    create_project(root, 'My "Game"', template_id=template_id)
    result = subprocess.run([sys.executable, "-m", "ruff", "check", "--config", str(ENGINE_ROOT / "pyproject.toml"),
                             "--output-format=concise", str(root)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    compile((root / "main.py").read_text(encoding="utf-8"), "main.py", "exec")


def test_recent_projects_live_in_the_user_folder_not_the_engine(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("MESH_PROJECTS_PATH", raising=False)
    monkeypatch.setenv("MESH_USER_DIR", str(tmp_path / "user"))
    projects.add_recent_project(str(tmp_path))
    assert (tmp_path / "user" / "projects.json").is_file()
    assert projects.get_recent_projects() == [str(tmp_path.resolve())]
    assert ENGINE_ROOT not in projects.default_projects_dir().parents


def test_ruff_gate_skips_untracked_game_projects_only(tmp_path) -> None:
    from tooling.ruff_gate import untracked_game_projects

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "game").mkdir()
    (tmp_path / "game" / "config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "game" / "main.py").write_text("import os\n", encoding="utf-8")
    (tmp_path / "newtool").mkdir()
    (tmp_path / "newtool" / "tool.py").write_text("import os\n", encoding="utf-8")
    assert untracked_game_projects(tmp_path) == ["game"]


def test_mesh_new_inside_the_engine_goes_to_the_projects_folder(tmp_path, monkeypatch) -> None:
    from mesh_cli.blank_project import create_blank_project, default_dest

    monkeypatch.setenv("MESH_USER_DIR", str(tmp_path))
    monkeypatch.chdir(ENGINE_ROOT)
    assert default_dest(".") == projects.default_projects_dir()
    assert default_dest(str(tmp_path)) == tmp_path.resolve()
    assert create_blank_project("nope", ENGINE_ROOT) == 1
    assert not (ENGINE_ROOT / "nope").exists()


def test_a_new_log_keeps_the_last_runs_log(tmp_path) -> None:
    from engine.launcher import fresh_log  # noqa: PLC0415

    log = tmp_path / "logs" / "studio.log"
    assert fresh_log(log) == log and log.parent.is_dir()
    log.write_text("Traceback: the crash", encoding="utf-8")
    fresh_log(log)
    assert not log.exists()
    assert (tmp_path / "logs" / "studio.previous.log").read_text(encoding="utf-8") == "Traceback: the crash"


def test_a_studio_crash_names_its_log_when_started_from_the_launcher(monkeypatch, tmp_path) -> None:
    import engine.launcher  # noqa: PLC0415
    import engine.optional_arcade  # noqa: PLC0415
    from engine.game import GameWindow  # noqa: PLC0415

    def boom() -> None:
        raise RuntimeError("draw failed")

    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(engine.optional_arcade.arcade, "run", boom)
    monkeypatch.setattr(engine.launcher, "show_crash", lambda what, log: shown.append((what, str(log))))
    monkeypatch.setenv("MESH_CRASH_LOG", str(tmp_path / "studio.log"))
    with pytest.raises(SystemExit):
        GameWindow.run(None)  # type: ignore[arg-type]
    assert shown == [("Mesh Studio", str(tmp_path / "studio.log"))]

    monkeypatch.delenv("MESH_CRASH_LOG")  # from a console: an ordinary traceback, no message box
    with pytest.raises(RuntimeError):
        GameWindow.run(None)  # type: ignore[arg-type]
    assert len(shown) == 1
