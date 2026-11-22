"""HD-2D online M1-A-3, the required gpu case: the collision world the game window plays on (``window.hd2d_world``,
built by engine.hd2d.runtime.configure_scene beside the real renderer, its sculpted heights the renderer's) has the
same ``collision_digest`` as the World the net authority builds from the same files.

Two rooms from the floors demo's crossing (tooling/hd2d_floors_demo.py build), edited with Studio's own operations:

- A: a scatter boulder, sculpted ground and a pond. The authority refuses the room (water that limits walking), so it
  is compared with the World from the authority's own ``build_world`` call, the one SceneRoom makes before that refusal;
- B: the boulder and the sculpted ground, no pond: compared with a fully loaded SceneRoom.

Hidden windows only, audio at master 0. GL-gated: set MESH_GL_SMOKE=1."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from engine import optional_arcade
from engine.physics_model import entity_aabb
from mesh_net.scene_room import Body

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
]

REPO = Path(__file__).resolve().parents[1]
SCENE = "packs/core_regions/scenes/start.json"


def room_files(tmp: Path, pond: bool) -> dict[str, bytes]:
    """The crossing with a boulder and sculpted ground (away from the player and the crossing), and a pond if asked."""
    from engine import project_ops as ops

    sys.path.insert(0, str(REPO / "tooling"))
    try:
        import hd2d_floors_demo
    finally:
        sys.path.remove(str(REPO / "tooling"))
    built = hd2d_floors_demo.build(tmp / "proj")
    files = {p.relative_to(built).as_posix(): p.read_bytes() for p in built.rglob("*") if p.is_file()}
    config = json.loads(files["config.json"])
    files["config.json"] = json.dumps({**config, "master_volume": 0.0}).encode()  # (never heard)
    scene = json.loads(files[SCENE])
    scene = ops.sculpt_terrain(scene, "raise", 160, 600, 96, 24)
    scene = ops.sculpt_terrain(scene, "lower", 900, 200, 80, 12)
    scene = ops.set_scatter(scene, {"boulder": [[800, 96, 30, 110]]})
    if pond:
        scene["entities"].append({"id": "pond", "x": 860.0, "y": 640.0, "behaviours": ["WaterSurface"]})
        scene = ops.set_water(scene, "pond", preset="natural_pond", width=160, height=96, walkable=False)
    assert scene["settings"]["hd2d"]["ground"]["terrain"], "sculpted"
    return {**files, SCENE: json.dumps(scene).encode()}


def authority(files: dict[str, bytes]) -> tuple[Any, Any]:
    """(the SceneRoom or the reason it refused, the World its build_world call returned)."""
    import engine.hd2d.world as world_module
    from mesh_net.scene_room import SceneRoom, Unsupported, disposable_project

    built: list[Any] = []
    original = world_module.build_world

    def spy(*args: Any, **kwargs: Any) -> Any:
        built.append(original(*args, **kwargs))
        return built[-1]

    with pytest.MonkeyPatch.context() as patch, disposable_project(files, scaffold=False) as root:
        patch.setattr(world_module, "build_world", spy)  # (scene_room.hd2d_world imports it when it runs)
        try:
            room: Any = SceneRoom(root / SCENE, root)
        except Unsupported as exc:
            room = exc
    assert len(built) == 1
    return room, built[0][0]


def window_digest(files: dict[str, bytes], tmp: Path) -> tuple[str, Any]:
    """The game, in a hidden window, loads the room: its window's collision world's digest, and its player's movement
    box (engine.physics_model.entity_aabb) where it starts."""
    project = tmp / "game"
    for rel, data in files.items():
        (project / rel).parent.mkdir(parents=True, exist_ok=True)
        (project / rel).write_bytes(data)
    with pytest.MonkeyPatch.context() as env:  # (this run's own user locations, then as they were)
        for name, rel in (("MESH_USER_DIR", "user"), ("MESH_RUNTIME_SETTINGS_PATH", "user/settings.json"),
                          ("MESH_PROJECTS_DIR", "projects"), ("MESH_PROJECTS_PATH", "user/projects.json"),
                          ("MESH_SAVE_DIR", "saves")):
            env.setenv(name, str(tmp / rel))
        env.syspath_prepend(str(REPO / "tooling"))
        from hd2d_demo import HiddenGame

        game = HiddenGame(project)
        try:
            game.load(SCENE)
            game.step(2)
            w = game.window
            assert w.hd2d_error is None and w.hd2d_renderer is not None and w.hd2d_renderer.terrain is not None
            assert w.hd2d_world.terrain is w.hd2d_renderer.terrain, "walked on what is drawn"
            assert [x for x in w.hd2d_world.walls if x.name == "scatter:boulder"], "the boulder blocks"
            return w.hd2d_world.collision_digest(), entity_aabb(game.player())
        finally:
            game.close()


def test_the_pond_room_the_authority_refuses_has_the_windows_collision_world(tmp_path: Path) -> None:
    files = room_files(tmp_path / "files", pond=True)
    refused, world = authority(files)
    assert "rivers or ponds" in str(refused), "SceneRoom refuses it (owner D4)"
    assert world is not None and world.ponds, "built with its pond, then refused"
    assert window_digest(files, tmp_path)[0] == world.collision_digest()


def test_the_room_without_the_pond_loads_with_the_windows_collision_world(tmp_path: Path) -> None:
    files = room_files(tmp_path / "files", pond=False)
    room, world = authority(files)
    assert not isinstance(room, Exception), room
    assert room.world is world and room.digest == world.collision_digest()
    digest, feet = window_digest(files, tmp_path)
    assert digest == room.digest
    (x, y), (w, h) = room.spawn, room._template_size()
    assert feet == entity_aabb(Body(x, y, w, h, room.template)), "the same body moves in both"
    assert digest != authority(room_files(tmp_path / "pond", pond=True))[1].collision_digest(), "the pond is in it"
