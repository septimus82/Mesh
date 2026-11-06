"""#460 Phase B: the HD-2D depth of field drawn by the real renderer (hidden window, the HD-2D template): off, disabled
and strength 0 are the original blit pixel for pixel; the depth texture is read with comparison off and the world's
depth test is unchanged by it; two surfaces on one screen row at different depths blur differently; the followed
character, the sharp band and the HUD's text stay as they were; walking, room changes and resizes allocate nothing;
software rendering bypasses it, says so and draws exactly off. The pass itself is drawn even on a software
rasteriser here (``allow_software``, a small window), so CI's Mesa lanes test the shader too; the bypass is checked
for real there. GL-gated: MESH_GL_SMOKE=1."""

from __future__ import annotations

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
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
SIZE = (640, 360)


@pytest.fixture(scope="module")
def report(tmp_path_factory: pytest.TempPathFactory, record_testsuite_property) -> dict:
    import dof_study

    from engine.hd2d.dof import parse_dof
    from engine.project_scaffold import create_project

    out = tmp_path_factory.mktemp("dof")
    project = out / "template"
    create_project(project, "DoF Template", template_id="hd2d_rpg")
    # bounded, stronger than Subtle so a small window's blur (radius scales with height) is measurable: 2 px at 360
    dof = parse_dof({"enabled": True, "max_blur": 4.0, "near_falloff": 4.0, "far_falloff": 4.0})
    found = dof_study.run(project, out / "lab", size=SIZE, frames=6, walk=8, loops=20, dof=dof, allow_software=True,
                          resizes=((480, 270), (800, 450)))
    keep = REPO / "artifacts" / "dof_phase_b"
    keep.mkdir(parents=True, exist_ok=True)
    (keep / f"report_{sys.platform}.json.log").write_text(json.dumps(found, indent=1, default=str), encoding="utf-8")
    record_testsuite_property("measure.dof_phase_b", json.dumps({
        "gl": found["gl"], "size": found["size"], "software_renderer": found["software_renderer"],
        "timing": {k: v["timing"] for k, v in found["views"].items()}}))
    return found


def test_off_disabled_and_strength_zero_are_the_original_blit(report: dict) -> None:
    checks = report["checks"]
    assert checks["zero_strength_identical_to_off"] and checks["disabled_identical_to_off"]
    assert checks["zero_strength_drawn"] is False  # (the original blit itself, not the pass at no blur)
    assert checks["still_frames_identical"]


def test_two_surfaces_on_one_screen_row_at_different_depths_blur_differently(report: dict) -> None:
    pairs = [ex for v in report["views"].values() for ex in v.get("same_row", {}).get("examples", [])]
    assert pairs, {k: v.get("same_row") for k, v in report["views"].items()}
    best = min(pairs, key=lambda ex: ex["far_kept"])
    assert best["sharp_kept"] == 1.0 and best["far_kept"] < 0.85 and best["far_coc_px"] >= 1.0, best


def test_the_followed_character_and_the_sharp_band_stay_sharp(report: dict) -> None:
    for name, view in report["views"].items():
        assert view["status"][0] == "on", (name, view["status"])
        assert view["player"]["pixels"] > 0, name
        assert view["player"]["changed_share"] == 0.0, (name, view["player"])
        assert view["sharp_band"]["changed_share"] <= 0.02, (name, view["sharp_band"])  # (only a nearer thing's spill)
        assert view["blurred_share"] > 0.0, name
    for walk in report["checks"]["walking"].values():
        assert walk["player_changed_share_max"] == 0.0, walk


def test_the_hud_is_drawn_after_it(report: dict) -> None:
    hud = report["checks"]["hud"]
    assert hud["glyph_pixels"] > 50, hud
    # (its text unchanged; a glyph's anti-aliased edge over a blurred background may move a level or two)
    assert hud["glyph_max_delta"] <= 3 and hud["glyph_pixels_changed"] <= hud["glyph_pixels"] * 0.25, hud


def test_nothing_is_allocated_per_frame_across_rooms_or_resizes(report: dict) -> None:
    gl = report["checks"]["gl_objects"]
    assert gl["off_before"] == gl["off_after"] and gl["on_before"] == gl["on_after"], gl
    rooms = report["checks"]["room_changes"]
    assert [r["drawn"] for r in rooms] == [True, False, True, False, True], rooms  # outdoor on, the interior off
    for visits in (rooms[0::2], rooms[1::2]):  # each room as it was on the first visit (geometry wrappers are
        first = visits[0]["objects"]  # freed lazily: their count may fall, never grow)
        for later in visits[1:]:
            now = later["objects"]
            assert {k: now[k] for k in ("texture", "framebuffer", "program", "buffer")} == \
                {k: first[k] for k in ("texture", "framebuffer", "program", "buffer")}, rooms
            assert now["geometry"] <= first["geometry"], rooms
    sizes = report["checks"]["resizes"]
    textures = {v["objects"]["texture"] for v in sizes.values()}
    assert len(textures) == 1, sizes
    for key, v in sizes.items():
        w, h = (int(n) for n in key.split("x"))
        assert v["fbo"] == [w, h] and v["radius_px"] == pytest.approx(4.0 * h / 720.0), (key, v)


def test_software_rendering_bypasses_it_says_so_and_draws_exactly_off(report: dict) -> None:
    sw = report["checks"]["software_bypass"]
    assert sw["status"][0] == "unavailable" and "software rendering" in sw["status"][1], sw
    assert sw["identical_to_off"] and not sw["drawn"], sw
    if report["software_renderer"]:  # (a real software rasteriser, CI's Mesa: the room's load said so too)
        assert sw["real"]
        said = [r["load_message"] for r in report["checks"]["room_changes"] if r["scene"].endswith("start.json")]
        assert said and all(m and "software rendering" in m for m in said), said


def test_the_depth_texture_is_read_with_comparison_off_and_depth_testing_is_unchanged(
        tmp_path_factory: pytest.TempPathFactory) -> None:
    import numpy as np
    from dof_study import Study

    from engine.project_scaffold import create_project

    out = tmp_path_factory.mktemp("dof_compare")
    project = out / "template"
    create_project(project, "DoF Compare", template_id="hd2d_rpg")
    study = Study(project, out, (480, 270))
    try:
        study.game.load("packs/core_regions/scenes/start.json")
        study.game.step(60)
        study.set_dof(None)
        off = study.frame()
        depth = study.hd._fbo_parts[1]
        assert depth.compare_func is None  # (arcade turns it on; the depth of field reads depth as depth)
        depth.compare_func = "<="  # (as before Phase B): what the world's depth test draws is the same
        again = study.frame()
        assert np.array_equal(off, again)
    finally:
        study.close()


def test_a_driver_refusing_the_pass_falls_back_to_the_blit_and_says_so(
        tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    import numpy as np
    from dof_study import Study

    import engine.hd2d.renderer as renderer_module
    import engine.optional_arcade as optional_arcade
    from engine.hd2d.dof import SUBTLE
    from engine.project_scaffold import create_project

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise optional_arcade.arcade.gl.ShaderException("refused for the test")

    out = tmp_path_factory.mktemp("dof_refused")
    project = out / "template"
    create_project(project, "DoF Refused", template_id="hd2d_rpg")
    study = Study(project, out, (480, 270))
    try:
        study.game.load("packs/core_regions/scenes/start.json")
        study.game.step(60)
        study.set_dof(None)
        off = study.frame()
        monkeypatch.setattr(renderer_module, "DofPass", refuse)
        study.set_dof(SUBTLE)
        study.hd.dof_unavailable = None  # (only the driver's refusal is the reason here, software or not)
        refused = study.frame()
        assert np.array_equal(off, refused) and study.hd.last_dof is None
        status, why = study.hd.dof_status()
        assert status == "unavailable" and "refused" in (why or ""), (status, why)
        assert np.array_equal(off, study.frame())  # (and it doesn't try again every frame)
    finally:
        study.close()
