"""HD-2D follow camera: the player never leaves the picture at a room's edges (camera bounds give way to it).

Rooms made by Studio's own "new HD-2D room" (Project.add_hd2d_room: the HD-2D template's recipe), saved, played in a
hidden game window with real key events: the player walks into every edge and corner. Every frame, the player's
billboard (feet and head, as the renderer draws it) projected through the game camera is inside the picture; settled
at each edge and corner it is inside with a margin, and the renderer draws its pixels. A 24 x 24 m outdoor room
(whose picture of the floor is as large as the room, so the camera can't move: before the fix the player walked
off its sides and top), a 40 x 30 m one (the camera moves; at the north edge the player's head left the top) and a
16 x 12 m indoor one. Hidden windows only. GL-gated: set MESH_GL_SMOKE=1."""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
ROOMS = {"outdoor_24x24": (24, 24, True), "outdoor_40x30": (40, 30, True), "indoor_16x12": (16, 12, False)}
SETTLED_MARGIN = 0.9  # NDC: settled, the player is at least 5% of the picture inside each edge
EDGE_M = 1.5  # the walk reached an edge: the player's feet within this of the room's side


@pytest.fixture(scope="module")
def project(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, str]]:
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    root = tmp_path_factory.mktemp("hd2dcam") / "Edges"
    create_project(root, "Edges", template_id="hd2d_rpg")
    studio = Project.open(root, "packs/core_regions/worlds/main.json")
    assert studio is not None
    keys = {name: studio.add_hd2d_room(name.replace("_", " ").title(), w, d, outdoor=outdoor)[0]
            for name, (w, d, outdoor) in ROOMS.items()}
    studio.save()
    return root, {name: studio.path(key) for name, key in keys.items()}


def _body_ndc(hd: Any, sprite: Any) -> tuple[float, float, float, float]:
    """The player's billboard (an upright quad at its feet, stretched by 1 / cos(pitch), facing the camera) through
    the game camera: min x, min y, max x, max y in normalised device coordinates."""
    cam = hd.camera
    vp = cam.view_projection(hd._aspect)
    half = abs(sprite.width) / 32 / 2
    h = abs(sprite.height) / 32 / max(0.5, math.cos(math.radians(cam.pitch)))
    x, y, z = sprite.center_x / 32, sprite.bottom / 32, hd.elevation_of(sprite) / 32
    rx, ry, _ = cam.right()
    xs, ys = [], []
    for sx in (-1.0, 1.0):
        for top in (0.0, h):
            p = (x + sx * rx * half, y + sx * ry * half, z + top, 1.0)
            c = [sum(vp[i][j] * p[j] for j in range(4)) for i in range(4)]
            assert c[3] > 0, "the player is in front of the camera"
            xs.append(c[0] / c[3])
            ys.append(c[1] / c[3])
    return min(xs), min(ys), max(xs), max(ys)


def _walk_room(root: Path, scene: str) -> dict[str, Any]:
    from hd2d_demo import HiddenGame

    game = HiddenGame(root, size=(1280, 720))
    game.window.audio.set_muted(True)
    keys = game.arcade.key
    out: dict[str, Any] = {"worst_frame": 0.0, "spots": {}}
    try:
        game.load(scene)
        game.step(60)
        hd, player = game.window.hd2d_renderer, game.player()
        assert hd is not None and hd.settings.camera.bounds is not None
        out["bounds_m"] = [v / 32 for v in hd.settings.camera.bounds]
        game.draw()
        out["centre_px"] = hd.visible_pixels(player)

        def walk(key: int, until: Any = None) -> None:
            """Hold ``key`` until ``until()`` or the player stops; every frame, the player in the picture."""
            game.window.dispatch_event("on_key_press", key, 0)
            last, still = None, 0
            for _ in range(2000):
                game.step(1)
                x0, y0, x1, y1 = _body_ndc(hd, player)
                out["worst_frame"] = max(out["worst_frame"], -x0, x1, -y0, y1)
                pos = (round(player.center_x, 2), round(player.center_y, 2))
                still = still + 1 if pos == last else 0
                last = pos
                if (until is not None and until()) or still >= 10:
                    break
            game.window.dispatch_event("on_key_release", key, 0)
            game.step(2)

        def spot(name: str) -> None:
            game.step(90)  # the smooth follow settles
            game.draw()
            out["spots"][name] = {"feet_m": (player.center_x / 32, player.bottom / 32), "ndc": _body_ndc(hd, player),
                                  "visible_px": hd.visible_pixels(player)}

        x0, y0, x1, y1 = out["bounds_m"]
        mid_x, mid_y = (x0 + x1) / 2 * 32, (y0 + y1) / 2 * 32
        walk(keys.UP)
        spot("north")
        walk(keys.LEFT)
        spot("northwest")
        walk(keys.DOWN, lambda: player.bottom < mid_y)
        spot("west")
        walk(keys.DOWN)
        spot("southwest")
        walk(keys.RIGHT, lambda: player.center_x > mid_x)
        spot("south")
        walk(keys.RIGHT)
        spot("southeast")
        walk(keys.UP, lambda: player.bottom > mid_y)
        spot("east")
        walk(keys.UP)
        spot("northeast")
    finally:
        game.close()
    return out


@pytest.mark.parametrize("room", list(ROOMS))
def test_the_player_stays_in_the_picture_at_every_edge_and_corner(project: tuple[Path, dict[str, str]],
                                                                  room: str) -> None:
    root, scenes = project
    run = _walk_room(root, scenes[room])
    x0, y0, x1, y1 = run["bounds_m"]
    reach = {"north": (None, y1), "south": (None, y0), "east": (x1, None), "west": (x0, None)}
    assert len(run["spots"]) == 8
    for name, s in run["spots"].items():  # the walk reached every edge and corner
        fx, fy = s["feet_m"]
        for side, (ex, ey) in reach.items():
            if side in name:
                assert abs((fx if ex is not None else fy) - (ex if ex is not None else ey)) < EDGE_M, (name, s)
    assert run["worst_frame"] <= 1.0, f"every frame, walking: the player in the picture ({run['worst_frame']})"
    for name, s in run["spots"].items():  # settled: in view with a margin, and drawn whole
        nx0, ny0, nx1, ny1 = s["ndc"]
        assert max(-nx0, nx1, -ny0, ny1) <= SETTLED_MARGIN + 1e-3, (name, s)
        assert s["visible_px"] > run["centre_px"] * 0.4, (name, s, run["centre_px"])
