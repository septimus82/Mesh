"""#461 R4: a stream flowing into a pond in the real renderer and the real game, hidden windows (GL-gated:
MESH_GL_SMOKE=1).

Studio (the R4 study village: a carved stream joined to a natural pond with a grassy bank, its source rounded):
- one water surface: in the pond, the frame with the stream is the frame without it (no second layer), where with
  its mouth off the stream lies over the pond (the negative control);
- the pond's bank isn't drawn over the stream where it enters; the stream's round source leaves its square
  corners dry;
- what is drawn is what ``RiverIndex`` (collision, wading, scatter) says is water, around the mouth and the source;
- Into the pond and Ends are one undo step each; drawing frames allocates no river buffers.
Play: the player wades down the stream and on into the pond (no barrier at the shore). Export: the bundle's room
joins the same way."""

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
P = 32.0


def test_studio_draws_one_water_surface_where_the_stream_enters_the_pond(tmp_path: Path) -> None:
    import r4_river_mouth_study as study
    from hd2d_studio_demo import StudioDriver

    from engine.hd2d.river import RiverIndex, join, ponds_of, ribbon
    from engine.water import LIFT_M, inside

    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    d = StudioDriver(study.make_project(tmp_path, "studio", carved=True))
    try:
        k, studio = d.arcade.key, d.studio
        d.button("Terrain")
        d.button("River")
        d.button("Select 'brook'")
        assert any("Flows into the pond" in t for t in d.texts()), d.texts()
        view = studio.hd2d
        view.camera.target, view.camera.distance, view.camera.pitch = (19.0, 36.5, 0.0), 14.0, 89.0
        d.advance(2)
        renderer = d.renderer
        rivers = renderer.settings.rivers
        (brook,) = rivers
        ponds = ponds_of(studio.project.scene()["entities"])
        mouth = join(brook, ponds)
        pond = mouth.pond
        rib = ribbon(brook)
        vx, vy, vw, _vh = view.viewport()
        scale = d.window.get_framebuffer_size()[0] / d.window.width

        def frame(shown: tuple) -> bytes:  # (drawn now, no time passing: nothing sways or flows between frames)
            renderer.settings = dataclasses.replace(renderer.settings, rivers=shown)
            try:
                return bytes(renderer.draw(camera=view.camera, viewport=view.viewport(), read=True))
            finally:
                renderer.settings = dataclasses.replace(renderer.settings, rivers=rivers)

        def at(p: tuple[float, float]) -> int:
            z = brook.points[-1][3] / P + LIFT_M
            s = d.screen((p[0], p[1], z))
            i = ((int(s[1] * scale) - vy) * vw + int(s[0] * scale) - vx) * 3
            assert 0 <= int(s[0] * scale) - vx < vw and 0 <= i < len(joined_size), ("off the picture", p)
            return i

        joined_size = frame(rivers)
        allocations = renderer.water.river_allocations
        for _ in range(5):
            frame(rivers)
        assert renderer.water.river_allocations == allocations, "drawing again makes no river buffers"
        joined, alone = frame(rivers), frame(())
        free = frame((dataclasses.replace(brook, mouth="none"),))

        def in_pond(p: tuple[float, float], margin_px: float) -> bool:
            return inside(pond.water, pond.centre, (p[0] * P, p[1] * P), margin_px)

        # its course in the pond past the opening (within MOUTH_BLEND of the shore the pond's own edge opens there)
        tail = [c for c in rib.centre if in_pond(c, 12.0)
                and (c[0] - mouth.at[0]) * mouth.tangent[0] + (c[1] - mouth.at[1]) * mouth.tangent[1] > 1.6]
        assert len(tail) >= 4, len(tail)
        same = sum(joined[at(c):at(c) + 3] == alone[at(c):at(c) + 3] for c in tail) / len(tail)
        doubled = sum(free[at(c):at(c) + 3] != alone[at(c):at(c) + 3] for c in tail) / len(tail)
        assert same > 0.95, ("in the pond: the pond's water alone, no second layer", same)
        assert doubled > 0.5, ("with its mouth off it lies over the pond (the control)", doubled)

        # the pond's bank, just outside its shore, where the stream comes in: not drawn there (the pond's opening
        # alone, the stream's own water left out of the frame: the ground shows, where the pond alone draws its bank)
        (tx, ty), h = mouth.tangent, mouth.half
        lip = [(mouth.at[0] - tx * out + -ty * a * h, mouth.at[1] - ty * out + tx * a * h)
               for a in (-0.6, -0.45, -0.3, -0.15, 0.0, 0.15, 0.3, 0.45, 0.6) for out in (0.03, 0.05)]
        lip = [p for p in lip if not in_pond(p, 0.0)]  # (its earth lip, at the water's edge: drawn all along it)
        frame(rivers)  # (its mouth set)
        geometry, renderer.water.river_geometry = renderer.water.river_geometry, None  # (its pass left out)
        try:
            opening = bytes(renderer.draw(camera=view.camera, viewport=view.viewport(), read=True))
        finally:
            renderer.water.river_geometry = geometry
        assert renderer.water.mouths, "(the mouth still set: only the stream's water left out)"
        bare = sum(opening[at(p):at(p) + 3] != alone[at(p):at(p) + 3] for p in lip) / max(1, len(lip))
        assert len(lip) >= 9 and bare >= 0.7, ("no bank over the stream", len(lip), bare)

        # the round source: the middle of its end is water, its square end's corners aren't
        (sx, sy), (ux, uy), h0 = rib.centre[0], rib.tangent[0], rib.half[0]
        corner = (sx + ux * 0.1 - uy * 0.85 * h0, sy + uy * 0.1 + ux * 0.85 * h0)
        middle = (sx + ux * 0.5, sy + uy * 0.5)
        view.camera.target = (sx, sy, 0.0)
        d.advance(1)
        joined, alone = frame(rivers), frame(())
        assert joined[at(corner):at(corner) + 3] == alone[at(corner):at(corner) + 3], "a square corner: dry"
        assert joined[at(middle):at(middle) + 3] != alone[at(middle):at(middle) + 3], "its end's middle: water"

        # drawn = water (RiverIndex), around the source and the mouth: away from every edge by 3 px
        index = RiverIndex(rivers, ponds)

        def water(p: tuple[float, float]) -> bool | None:
            near = [index.level_at(p[0] + dx / P, p[1] + dy / P) is not None for dx in (-3, 0, 3) for dy in (-3, 0, 3)]
            return near[4] if all(n == near[4] for n in near) else None  # (None: an edge)

        checked = 0
        for (cx, cy) in ((sx, sy), mouth.at):
            view.camera.target = (cx, cy, 0.0)
            d.advance(1)
            joined, alone = frame(rivers), frame(())
            for i in range(-12, 13):
                for j in range(-12, 13):
                    p = (cx + i * 0.2, cy + j * 0.2)
                    expect = water(p)
                    if expect is None or in_pond(p, -6.0):
                        continue
                    drawn = joined[at(p):at(p) + 3] != alone[at(p):at(p) + 3]
                    assert drawn == expect, (p, drawn, expect)
                    checked += 1
        assert checked > 400, checked

        # the panel's controls: one undo step each
        undo0 = len(studio.project._undo)
        d.button("Into the pond: on")
        assert studio.project.scene()["settings"]["hd2d"]["rivers"][0].get("mouth") is None
        assert len(studio.project._undo) == undo0 + 1
        d.key(k.Z, k.MOD_CTRL)
        assert studio.project.scene()["settings"]["hd2d"]["rivers"][0]["mouth"] == "auto"
        d.button("Ends: Round at source")
        assert studio.project.scene()["settings"]["hd2d"]["rivers"][0].get("ends") == "round_end"
        d.key(k.Z, k.MOD_CTRL)
        assert studio.project.scene()["settings"]["hd2d"]["rivers"][0]["ends"] == "round_source"
        d.key(k.Y, k.MOD_CTRL)
        assert studio.project.scene()["settings"]["hd2d"]["rivers"][0]["ends"] == "round_end"
    finally:
        d.close()


def test_the_player_wades_down_the_stream_and_on_into_the_pond(tmp_path: Path) -> None:
    import r3_river_bed_study as walker
    import r4_river_mouth_study as study
    from hd2d_demo import SCENES, HiddenGame

    from engine.hd2d.river import join, ponds_of

    project = study.make_project(tmp_path, "play", carved=True)
    scene = study.scene_of(project)
    game = HiddenGame(project, size=(1280, 720))
    try:
        game.load(f"{SCENES}/start.json")
        game.step(3)
        world = game.window.hd2d_world
        (brook,) = game.window.hd2d_renderer.settings.rivers
        mouth = join(brook, ponds_of(scene["entities"]))
        x, y = 611.0, 1000.0  # in the stream, 4 m short of the pond
        bed = min(h for h, _s in world.heights_at(x / P, y / P))
        start = (x, y, bed)
        down = game.arcade.key.S
        probe = walker.walk(game, start, down, 4)
        if probe["y"] < y:  # (which key walks south, the stream's way)
            down = game.arcade.key.W
        went = walker.walk(game, start, down, 160)
        assert went["y"] > mouth.at[1] * P + 32, ("on past the shore into the pond", went, mouth.at)
        assert went["wading_steps"] >= 2, ("its steps ripple the stream", went)
        player = game.player()
        assert world.water_at(player.center_x / P, player.bottom / P, went["z"]) is None, "the pond's water, not the stream's"
        assert getattr(game.window.water_bodies[0].entity, "mesh_entity_data", None) is not None
    finally:
        game.close()


def test_the_join_survives_save_export_and_reload(tmp_path: Path) -> None:
    import r4_river_mouth_study as study

    from engine.hd2d.river import RiverIndex, mouths, parse_rivers, ponds_of
    from engine.tooling.export_bundle import build_bundle

    project = study.make_project(tmp_path, "export", carved=True)
    code, _manifest = build_bundle(project, tmp_path / "bundle", deterministic=True)
    assert code == 0
    rel = f"{study.SCENES}/start.json"
    exported = next(p for p in (tmp_path / "bundle").rglob("start.json") if p.as_posix().endswith(rel))
    source = json.loads((project / rel).read_text(encoding="utf-8"))
    copied = json.loads(exported.read_text(encoding="utf-8"))
    assert copied["settings"]["hd2d"] == source["settings"]["hd2d"] and copied["entities"] == source["entities"]
    answers = []
    for s in (source, copied):
        rivers, ponds = parse_rivers(s["settings"]["hd2d"]["rivers"]), ponds_of(s["entities"])
        joined, problems = mouths(rivers, ponds)
        index = RiverIndex(rivers, ponds)
        answers.append((sorted(joined), problems, [index.level_at(19.0, y / 4) for y in range(130, 150)]))
    assert answers[0] == answers[1] and answers[0][0] == ["brook"], answers
