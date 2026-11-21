"""Contract tests for ``mesh new <name>``, the beginner front door.

``mesh new`` scaffolds through ``engine.project_scaffold`` with the ``starter``
template. The project it makes must validate, boot headlessly, and contain a
walkable player plus something to talk to. ``mesh --help`` shows only the
getting-started commands; ``--help-all`` shows everything.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import mesh_cli
from engine.action_runtime.registry import validate_bound_actions
from engine.paths import reset_path_caches

pytestmark = [pytest.mark.fast]

_START_SCENE = "packs/core_regions/scenes/start.json"


def _run_new(name: str, dest: Path, extra_args: list[str] | None = None) -> int:
    return mesh_cli.main(["new", name, "--dest", str(dest), *(extra_args or [])])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert _run_new("my_game", tmp_path) == 0
    return tmp_path / "my_game"


def _scene(project: Path) -> dict:
    return json.loads((project / _START_SCENE).read_text(encoding="utf-8"))


def test_creates_scaffolded_project(project: Path) -> None:
    ast.parse((project / "main.py").read_text(encoding="utf-8"))
    cfg = json.loads((project / "config.json").read_text(encoding="utf-8"))
    assert cfg["start_scene"] == _START_SCENE
    assert cfg["title"] == "my_game"
    # The starter scene has no lights; lighting on renders a near-black screen.
    assert cfg["lighting_enabled"] is False
    assert (project / "packs/core_regions/worlds/main.json").is_file()
    assert (project / "assets/sprites/starter_hero.png").is_file()
    assert not (project / "assets/sprites/animated_player.png").exists(), "no template uses the legacy sheet"


def test_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    assert _run_new("beta", tmp_path) == 0
    assert _run_new("beta", tmp_path) != 0
    assert _run_new("beta", tmp_path, ["--force"]) == 0


def test_default_template_has_player_and_interactable(project: Path) -> None:
    entities = _scene(project)["entities"]
    # One player for the whole game: the room says where it starts, the "player" prefab what it is.
    players = [e for e in entities if e.get("prefab_id") == "player"]
    assert len(players) == 1
    prefabs = json.loads((project / "assets/prefabs.json").read_text(encoding="utf-8"))
    assert "PlayerController" in next(p for p in prefabs if p["id"] == "player")["entity"]["behaviours"]
    npc = next(e for e in entities if "Dialogue" in e.get("behaviours", []))
    nodes = npc["behaviour_config"]["Dialogue"]["dialogue"]["nodes"]
    assert nodes["root"]["text"]


def test_project_binds_every_required_action(project: Path) -> None:
    # Without explicit bindings the runtime only binds arrows/E/Esc (no WASD, no F4).
    cfg = json.loads((project / "config.json").read_text(encoding="utf-8"))
    unknown, missing = validate_bound_actions(cfg.get("input_bindings"))
    assert (unknown, missing) == ([], [])
    assert "W" in cfg["input_bindings"]["move_up"]


def test_project_passes_validate_all(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(project)
    reset_path_caches()
    # No --path: the bare command a beginner types must find the project's world.
    assert mesh_cli.main(["validate-all", "--strict", "--check-refs", "--check-reachability"]) == 0


def test_project_boots_headless_and_loads_start_scene(project: Path, tmp_path: Path) -> None:
    # Subprocess: the runtime-only smoke rejects editor modules this test process already imported.
    artifact = tmp_path / "smoke.json"
    env = {k: v for k, v in os.environ.items() if k != "MESH_REPO_ROOT"}
    # Run this checkout's engine: from the project folder Python may otherwise import another Mesh install.
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    cmd = [sys.executable, "-m", "mesh_cli", "play-runtime", "--headless-smoke", "--smoke-scene", _START_SCENE]
    cmd += ["--smoke-ticks", "3", "--smoke-artifact", str(artifact)]
    result = subprocess.run(cmd, cwd=project, env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["scene_loaded"] == "Starter Room"


def _help_text(capsys: pytest.CaptureFixture[str], flag: str) -> str:
    with pytest.raises(SystemExit) as exc:
        mesh_cli.main([flag])
    assert exc.value.code == 0
    return capsys.readouterr().out


def test_help_lists_only_getting_started(capsys: pytest.CaptureFixture[str]) -> None:
    out = _help_text(capsys, "--help")
    for command in ("new", "play", "edit", "mcp", "validate", "doctor"):
        assert f"\n  {command} " in out
    assert "--help-all" in out
    for hidden in ("new_project", "new-game", "validate-all", "replay-suite"):
        assert hidden not in out


def test_help_all_lists_every_command(capsys: pytest.CaptureFixture[str]) -> None:
    out = _help_text(capsys, "--help-all")
    for command in ("new", "new_project", "new-game", "validate-all", "replay-suite", "doctor"):
        assert command in out
