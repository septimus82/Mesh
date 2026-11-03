"""#461 R1: rivers in the real renderer, hidden windows (GL-gated: MESH_GL_SMOKE=1).

The starter village with a stream flowing north under its bridge and another flowing east south of its road, each in
a bed sculpted with the existing terrain op (tooling/r1_river_study.py builds it through project_ops, as Studio and
AI do). A river is drawn whole along its course (the bridge's deck hides it where it passes beneath: depth-tested);
its surface moves downstream at its flow, whichever way it runs, and stands still at flow 0; its pattern belongs to
the world, not the screen; its GPU objects are made once, not every frame, and freed with the room."""

from __future__ import annotations

import json
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
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
    pytest.mark.filterwarnings("ignore:.*style dict.*:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))


def test_a_river_is_drawn_whole_passes_under_the_bridge_and_flows_downstream(tmp_path: Path,
                                                                           record_testsuite_property: Any) -> None:
    import r1_river_study as study
    from hd2d_demo import SCENES, HiddenGame

    beds = HiddenGame(study.make_project(tmp_path, "beds", rivers=False), size=study.study.SIZE)
    try:  # the same village and beds without the rivers: what each pixel would be without them
        beds.load(f"{SCENES}/start.json")
        beds.step(3)
        plain = {rid: study.frame(beds, study.centre_of(points), 10.0)
                 for rid, points in (("north", study.NORTH), ("east", study.EAST))}
        study.frame_ms(beds, study.centre_of(study.NORTH), 10)  # (warm)
        cost = {"beds_only": study.frame_ms(beds, study.centre_of(study.NORTH))}
    finally:
        beds.close()
    game = HiddenGame(study.make_project(tmp_path, "flowing", flow=1.2), size=study.study.SIZE)
    try:
        game.load(f"{SCENES}/start.json")
        game.step(3)
        study.frame_ms(game, study.centre_of(study.NORTH), 10)
        cost["rivers"] = study.frame_ms(game, study.centre_of(study.NORTH))
        # every run's frame cost, in the lane's JUnit and summary: reporting only (no threshold), before any assert
        record_testsuite_property("measure.river_frame_ms", json.dumps(cost))
        for rid, points in (("north", study.NORTH), ("east", study.EAST)):
            target = study.centre_of(points)
            image = study.frame(game, target, 10.0)
            assert game.window.hd2d_renderer.stats()["rivers"] == 2 and game.window.hd2d_renderer.water_error is None
            shown: list[tuple[float, float, float]] = []
            hidden: list[tuple[float, float, float]] = []
            for p in study.course(game, rid):
                at = study.to_screen(game, p)
                if at is not None:
                    xy = (int(at[0]), int(at[1]))
                    (shown if image.getpixel(xy) != plain[rid].getpixel(xy) else hidden).append(p)
            assert len(shown) > 300, (rid, len(shown))
            if rid == "east":  # in the open: every texel of its course drawn
                assert not hidden, hidden[:5]
            else:  # it passes beneath the bridge (y 768 px): the deck stands in front of it there, and only there
                ys = sorted(p[1] * 32 for p in hidden)
                assert ys and 640 <= ys[0] and ys[-1] <= 1040, ys[:3] + ys[-3:]
                band = [p for p in shown + hidden if ys[0] <= p[1] * 32 <= ys[-1]]
                assert len(hidden) / len(band) > 0.9, "one stretch, behind the deck"
                assert sum(1 for p in shown if p[1] * 32 > ys[-1]) > 60, "and out the other side"
            moved, corr = study.drift(game, rid, target, 10.25)  # in a quarter second at 1.2 m/s: 0.3 m, 9.6 texels
            assert 8 <= moved <= 12 and corr > 0.3, (rid, moved, corr)
            # the pattern belongs to the world: half a metre's camera move leaves it where it was
            line = study.course(game, rid, 0.25)
            a = study.profile(game, study.frame(game, target, 10.0), line)
            b = study.profile(game, study.frame(game, (target[0] + 0.5, target[1], target[2]), 10.0), line)
            assert study.shift([(a, b)])[0] == 0, rid
    finally:
        game.close()


def test_still_water_stands_still_and_its_gpu_objects_are_made_once(tmp_path: Path) -> None:
    import r1_river_study as study
    from hd2d_demo import SCENES, HiddenGame, _gl_counts

    game = HiddenGame(study.make_project(tmp_path, "still", flow=0.0), size=study.study.SIZE)
    try:
        ctx = game.window.ctx
        game.load(f"{SCENES}/start.json")
        game.step(3)
        target = study.centre_of(study.NORTH)
        first = study.frame(game, target, 10.0)
        water = game.window.hd2d_renderer.water
        made = (water.river_program, *water.river_buffers)
        held = _gl_counts(ctx)
        for k in range(30):
            later = study.frame(game, target, 10.0 + k / 10)
        assert later.tobytes() == first.tobytes(), "flow 0: nothing on the river moves"
        assert (water.river_program, *water.river_buffers) == made and _gl_counts(ctx) == held, "made once"
        assert water.memory_bytes() >= sum(b.size for b in water.river_buffers) > 0
        game.load(f"{SCENES}/cottage.json")  # a room without rivers
        game.step(3)
        game.draw()
        assert all(getattr(getattr(o, "_glo", None), "value", 0) == 0 for o in made), "freed with the room"
        counts = []
        for _ in range(3):  # and room after room, nothing builds up
            for room in ("start", "cottage"):
                game.load(f"{SCENES}/{room}.json")
                game.step(3)
                game.draw()
            ctx.gc()
            counts.append({k: v for k, v in _gl_counts(ctx).items() if k != "buffer"})  # (arcade's own caches)
        assert counts[1:] == counts[:-1], counts
    finally:
        game.close()


def test_a_river_only_room_flows_on_the_game_s_own_ticks(tmp_path: Path) -> None:
    """No pond or puddle in the room: the river alone keeps the water's clock running, and the game's own update
    ticks (not a clock set by the test) carry its surface downstream, or leave it still at flow 0."""
    import r1_river_study as study
    from hd2d_demo import SCENES, HiddenGame

    for flow, name in ((1.2, "ticked"), (0.0, "ticked_still"), (None, "ticked_beds")):
        game = HiddenGame(study.make_project(tmp_path, name, flow=flow or 0.0, rivers=flow is not None),
                          size=study.study.SIZE)
        try:
            game.load(f"{SCENES}/start.json")
            assert not game.window.water_bodies, "a room without ponds or puddles"
            game.step(30)
            clock = game.window.water_time
            if flow is None:  # no water at all: the clock stays where loading left it
                assert clock == 0.0
                continue
            assert abs(clock - 0.5) < 1e-6, clock  # 30 ticks of 1/60 s
            for rid, points in (("north", study.NORTH), ("east", study.EAST)):
                moved, corr = study.drift(game, rid, study.centre_of(points), None)
                if flow:
                    assert 8 <= moved <= 12 and corr > 0.3, (rid, moved, corr)
                else:  # still: along the river nothing changed between the ticks
                    assert corr <= 0.0, (rid, moved, corr)
        finally:
            game.close()


def test_a_bend_that_widens_is_drawn_bank_to_bank_and_nowhere_else(tmp_path: Path) -> None:
    """Seen from straight above: every texel inside the banks (by more than 3 texels) is drawn, none outside them
    (by more than 3 texels), round a right-angle bend while the river widens from 1.25 m to 3 m."""
    import r1_river_study as study
    from hd2d_demo import SCENES, HiddenGame

    target = (300 / 32, 140 / 32, 0.0)
    frames, spots = {}, {}
    for name, river in (("plain", False), ("bend", True)):
        game = HiddenGame(study.make_bend_project(tmp_path, name, river=river), size=study.study.SIZE)
        try:
            game.load(f"{SCENES}/start.json")
            game.step(3)
            game.window.hd2d_renderer.camera.pitch = 89.0
            frames[name] = study.frame(game, target, 10.0)
            if river:
                inside, outside = study.bank_to_bank(game, "bend")
                spots = {k: [study.to_screen(game, p) for p in v] for k, v in (("inside", inside), ("outside", outside))}
        finally:
            game.close()

    def drawn(at: tuple[float, float]) -> bool:
        xy = (int(at[0]), int(at[1]))
        return bool(frames["bend"].getpixel(xy) != frames["plain"].getpixel(xy))

    inside = [at for at in spots["inside"] if at is not None]
    outside = [at for at in spots["outside"] if at is not None]
    assert len(inside) > 15000 and len(outside) > 50000, (len(inside), len(outside))
    assert len(inside) == len(spots["inside"]) and len(outside) == len(spots["outside"]), "all of it in the picture"
    holes = [at for at in inside if not drawn(at)]
    spill = [at for at in outside if drawn(at)]
    assert not holes, (len(holes), holes[:5])
    assert not spill, (len(spill), spill[:5])
