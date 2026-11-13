"""#461 R3: a river's bed and its water underfoot in the real renderer and the real game, hidden windows (GL-gated:
MESH_GL_SMOKE=1).

Studio: a stream whose water lies under the ground is unseen; its River panel's Carve the bed lowers the ground
under it and the water shows along its course (measured: the frame with the river against the frame without);
undo puts the ground back exactly, redo carves it again; Clear plants takes away the scatter standing in its water,
one undo step. Play (the template village, carved: deep but for a ford): the player wades across the ford (its
steps ripple the water), stops at the deep stretch's edge, and walks across the bridge's deck over the deep water.
Walking uses the window's own key events."""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
    pytest.mark.filterwarnings("ignore:.*style dict.*:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


def test_studio_carves_a_stream_s_bed_so_its_water_shows_undo_and_clear_its_plants(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import r3_river_bed_study as study
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops
    from engine.hd2d.river import ribbon
    from engine.hd2d.scatter import parse_scatter
    from engine.water import LIFT_M

    monkeypatch.setenv("MESH_STUDIO_NO_AI_BRIDGE", "1")
    d = StudioDriver(study.make_project(tmp_path, "studio"))
    try:
        k, studio = d.arcade.key, d.studio
        d.button("Terrain")
        d.button("River")
        d.button("Select 'brook'")
        studio.hd2d.camera.target = (20.0, 17.0, 0.0)
        d.advance(2)

        def shown_along() -> float:
            """The share of the course's water texels (south of the bridge: open) that the river changes."""
            renderer = d.renderer
            rivers = renderer.settings.rivers
            rib = ribbon(rivers[0])
            points = [(c[0], c[1], z + LIFT_M) for c, z in zip(rib.centre, rib.level) if c[1] * 32 < 700]
            at = [d.screen(p) for p in points]

            view = studio.hd2d
            vx, vy, vw, _vh = view.viewport()
            scale = d.window.get_framebuffer_size()[0] / d.window.width

            def frame(with_rivers: bool) -> bytes:  # (drawn now, no time passing: the meadow's sway the same)
                renderer.settings = dataclasses.replace(renderer.settings, rivers=rivers if with_rivers else ())
                try:
                    return bytes(renderer.draw(camera=view.camera, viewport=view.viewport(), read=True))
                finally:
                    renderer.settings = dataclasses.replace(renderer.settings, rivers=rivers)

            a, b = frame(True), frame(False)
            spots = [((int(s[1] * scale) - vy) * vw + int(s[0] * scale) - vx) * 3 for s in at]
            return sum(1 for i in spots if a[i:i + 3] != b[i:i + 3]) / len(spots)

        assert shown_along() < 0.05, "its water under the ground: unseen"
        heights_before = list(d.renderer.terrain.heights) if d.renderer.terrain is not None else None
        undo0 = len(studio.project._undo)
        d.button("Carve the bed")
        assert "bed carved" in studio.message, studio.message
        assert len(studio.project._undo) == undo0 + 1
        assert shown_along() > 0.95, "carved: its water shows all along its course"
        d.key(k.Z, k.MOD_CTRL)
        after_undo = list(d.renderer.terrain.heights) if d.renderer.terrain is not None else None
        assert after_undo == heights_before, "undone: the ground exactly as it was"
        assert shown_along() < 0.05
        d.key(k.Y, k.MOD_CTRL)
        assert shown_along() > 0.95, "redone"

        def wet() -> int:
            from engine.hd2d.river import RiverIndex
            from engine.hd2d.scatter import ASSETS, submerged

            scene = studio.project.scene()
            water = RiverIndex(tuple(d.renderer.settings.rivers))
            terrain = d.renderer.terrain
            rows = parse_scatter(scene["settings"]["hd2d"].get("scatter") or {})
            return sum(1 for name, rs in rows.items() for x, y, _t, _s in rs
                       if (w := water.level_at(x / 32, y / 32)) and submerged(ASSETS[name], terrain.height(x, y),
                                                                              w[0] * 32))

        total = sum(len(v) for v in parse_scatter(studio.project.scene()["settings"]["hd2d"]["scatter"]).values())
        assert wet() > 0
        d.button("Clear plants")
        assert wet() == 0 and len(studio.project._undo) == undo0 + 2
        left = sum(len(v) for v in parse_scatter(studio.project.scene()["settings"]["hd2d"]["scatter"]).values())
        assert 0 < left < total, "only what stood in its water"
        assert ops.rivers(studio.project.scene())[0]["points"] == [list(p) for p in study.COURSE]
        d.key(k.Z, k.MOD_CTRL)
        assert wet() > 0, "undone: the plants back"
    finally:
        d.close()


def test_the_player_wades_the_ford_stops_at_deep_water_and_crosses_the_bridge(tmp_path: Path) -> None:
    import r3_river_bed_study as study
    from hd2d_demo import SCENES, HiddenGame

    from engine.hd2d.river import ribbon
    from engine.hd2d.world import DEEP

    game = HiddenGame(study.make_project(tmp_path, "play", carved=True), size=(1280, 720))
    try:
        game.load(f"{SCENES}/start.json")
        game.step(3)
        world = game.window.hd2d_world
        assert world is not None and world.rivers, "a room with a river walks by its water"
        left = game.arcade.key.A

        ford = study.walk(game, (study.EAST_BANK_X, study.FORD_Y, 0.0), left, 150)
        assert ford["x"] < study.WEST_BANK_X + 16, ("across the ford", ford)
        assert 0.0 < ford["deepest"] <= DEEP and ford["lowest"] < -0.2, ("waded: in the water", ford)
        assert ford["wading_steps"] >= 3, ("its steps ripple the water", ford)

        deep = study.walk(game, (study.EAST_BANK_X, study.DEEP_Y, 0.0), left, 150)
        rib = ribbon(game.window.hd2d_renderer.settings.rivers[0])
        middle = min(rib.centre, key=lambda c: abs(c[1] * 32 - study.DEEP_Y))[0] * 32
        assert deep["x"] > middle, ("stopped before the deep middle", deep, middle)
        assert deep["deepest"] <= DEEP, ("never stood in deep water", deep)

        # put in the deep middle (a river carved under it, a start point there): it wades out, never deeper than
        # where it was put, so out the shallower way (towards the bank on the side the bed rises from where it stands)
        bed = min(h for h, _s in world.heights_at(middle / 32, study.DEEP_Y / 32))

        def deepest_at(x_px: float) -> float:
            floor = min(h for h, _s in world.heights_at(x_px / 32, study.DEEP_Y / 32))
            return world.deepest(x_px / 32, study.DEEP_Y / 32, floor, 0.3, 0.19)

        east = deepest_at(middle + 2) < deepest_at(middle - 2)  # (the way the bed rises from where it stands)
        key, bank = (game.arcade.key.D, study.EAST_BANK_X) if east else (left, study.WEST_BANK_X)
        out = study.walk(game, (middle, study.DEEP_Y, bed), key, 150)
        reached = out["x"] > bank - 16 if east else out["x"] < bank + 16
        assert reached and out["deepest"] <= 0.8 + 0.02, ("waded out onto the bank", out, bank)

        # re-review of c96e3e8: tiny steps (a slow stick, a slow NPC, a fast frame) never ratchet into deep water
        player = game.player()
        player.center_x = study.EAST_BANK_X
        player.center_y = study.DEEP_Y + (player.center_y - player.bottom)
        player.mesh_entity_data["elevation"] = 0.0
        solids = getattr(game.window.scene_controller, "solid_sprites", None)
        for _ in range(1200):  # 0.25 px a step, 300 px west: across the river if nothing stopped it
            world.move(player, (-0.25, 0.0), solids)
        assert player.center_x > middle, ("tiny steps stopped at the deep water", player.center_x, middle)
        from engine.hd2d.world import DEEP_SLACK, elevation_of
        from engine.physics_runtime import _sprite_to_aabb  # (its feet box, as the world moves it by)

        box = _sprite_to_aabb(player)
        depth = world.deepest(box.x / 32, box.y / 32, elevation_of(player), box.w / 64, box.h / 64)
        assert depth <= DEEP + DEEP_SLACK + 1e-9, depth

        # re-review of afc674c: a cap set in shallower deep water, then moved deeper by a teleport (a transfer, an
        # event): it can still wade out
        for x in range(int(middle) + 4, int(study.EAST_BANK_X), 2):
            box_bed = min(h for h, _s in world.heights_at(x / 32, study.DEEP_Y / 32))
            if world.deepest(x / 32, study.DEEP_Y / 32, box_bed, 0.3, 0.19) < 0.65:
                break
        study.walk(game, (float(x), study.DEEP_Y, box_bed), game.arcade.key.D, 2)  # (a step there: its cap set)
        assert getattr(game.player(), "mesh_hd2d_deep_cap", None) is not None
        game.player().center_x = middle  # teleported into the deep middle, its old cap kept
        game.player().mesh_entity_data["elevation"] = bed * 32
        game.player().center_y = study.DEEP_Y + (game.player().center_y - game.player().bottom)
        solids = getattr(game.window.scene_controller, "solid_sprites", None)
        for _ in range(400):  # (the shallower way out, as above)
            world.move(game.player(), (1.0 if east else -1.0, 0.0), solids)
        x_out = game.player().center_x
        assert x_out > bank - 16 if east else x_out < bank + 16, ("waded out after a teleport", x_out, bank)

        bridge = study.walk(game, study.DECK, left, 150)
        assert bridge["x"] < 600.0 and abs(bridge["z"] - study.DECK[2]) < 0.05, ("across on the deck", bridge)
        assert bridge["deepest"] == 0.0, "dry on the deck"
    finally:
        game.close()


def test_the_bed_survives_save_export_and_reload(tmp_path: Path) -> None:
    """The carved room as exported (the bundle's own copy of the scene) builds the same ground and the same water
    underfoot as the project."""
    import r3_river_bed_study as study

    from engine.hd2d.settings import parse_hd2d
    from engine.hd2d.world import World
    from engine.tooling.export_bundle import build_bundle

    project = study.make_project(tmp_path, "export", carved=True)
    code, _manifest = build_bundle(project, tmp_path / "bundle", deterministic=True)
    assert code == 0
    rel = f"{study.SCENES}/start.json"
    exported = next(p for p in (tmp_path / "bundle").rglob("start.json") if p.as_posix().endswith(rel))
    source = json.loads((project / rel).read_text(encoding="utf-8"))
    copied = json.loads(exported.read_text(encoding="utf-8"))
    assert copied["settings"]["hd2d"] == source["settings"]["hd2d"]
    # (ground and water: the structures' models aren't read here)
    worlds = [World(dataclasses.replace(parse_hd2d(s["settings"]["hd2d"]), structures=()), {})
              for s in (source, copied)]
    for x, y in ((20.4, 18.75), (20.2, 31.25), (22.0, 31.25), (25.0, 25.0)):
        answers = []
        for w in worlds:
            z = min(h for h, _s in w.heights_at(x, y))
            answers.append((round(z, 4), w.water_at(x, y, z), w.stand(x, y, z, 0.3, 0.19)))
        assert answers[0] == answers[1], answers
