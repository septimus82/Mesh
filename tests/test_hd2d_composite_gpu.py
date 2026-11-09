"""M17-L4-1: the HD-2D final composite in real frames (hidden windows; tooling/hd2d_composite_study.py): off, every
room is drawn exactly as before and nothing is made; the identity composite gives the very same bytes, with the depth
of field too; picture sizes, room changes and release leave nothing behind; Mesh Studio's offset canvas, its lines and
the game's camera path agree. GL-gated: MESH_GL_SMOKE=1."""

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
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
ROOMS = ("village", "lakeside", "fixtures", "cottage", "emissive")
TRACKED = ("texture", "framebuffer", "program")  # (buffers: see test_room_changes_free_the_composite_with_the_renderer)


@pytest.fixture(scope="module")
def report(tmp_path_factory: pytest.TempPathFactory) -> dict:
    import hd2d_composite_study

    out = tmp_path_factory.mktemp("composite")
    os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")
    os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
    try:
        found: dict = hd2d_composite_study.study(out)
    finally:
        os.environ.pop("MESH_RUNTIME_SETTINGS_PATH", None)
        os.environ.pop("MESH_STUDIO_NO_AI_BRIDGE", None)
    keep = REPO / "artifacts" / "hd2d_composite"
    keep.mkdir(parents=True, exist_ok=True)
    (keep / f"report_{sys.platform}.json.log").write_text(json.dumps(found, indent=1, default=str), encoding="utf-8")
    return found


@pytest.mark.parametrize("name", ROOMS)
def test_off_every_room_is_the_blit_and_nothing_is_made(report: dict, name: str) -> None:
    off = report["rooms"][name]["off"]
    assert off["stage"] == "blit" and not off["composite_made"], off
    assert off["blit_is_the_world"] and off["repeat_same"], off


@pytest.mark.parametrize("name", ROOMS)
def test_the_identity_composite_is_the_very_same_picture(report: dict, name: str) -> None:
    r = report["rooms"][name]
    off, ident = r["off"], r["identity"]
    assert ident["stage"] == "composite" and ident["same_as_off"] and ident["repeat_same"], r
    assert ident["draw_calls"] == off["draw_calls"], r  # (the world's draws: the composite takes the blit's place)
    added = {k: ident["live"][k] - off["live"][k] for k in off["live"]}
    assert added == {"texture": 0, "framebuffer": 0, "program": 1, "buffer": 0, "geometry": 0}, added
    assert ident["world_read_unchanged"] and r["off_again_same"], r  # draw(read=True): the world before it, as ever
    assert r["rgba"]["identity_same"], r["rgba"]  # (alpha kept: the world's own, not forced opaque)


@pytest.mark.parametrize("name", ROOMS)
def test_the_depth_of_field_is_unchanged_with_the_identity_after_it(report: dict, name: str) -> None:
    r = report["rooms"][name]
    dof, forced = r["dof"], r["dof_forced"]
    if report["software_renderer"]:  # (as before: bypassed, the picture as off; the identity alone after nothing)
        assert dof["status"] == "unavailable" and dof["stage"] == "blit" and not dof["changed_the_picture"], dof
        assert dof["identity_stage"] == "composite" and dof["identity_same"], dof
    else:
        assert dof["status"] == "on" and dof["stage"] == "dof" and dof["changed_the_picture"], dof
        assert dof["identity_stage"] == "dof+composite" and dof["identity_same"], dof
    assert dof["world_read_unchanged"] and r["off_after_dof_same"], r
    # forced on, whatever the driver (the chained path itself): the DoF picture, one chain target
    assert forced["stage"] == "dof" and forced["identity_stage"] == "dof+composite", forced
    assert forced["changed_the_picture"] and forced["identity_same"] and forced["chain_allocations"] == 1, forced


def test_the_identity_returns_every_byte_alpha_included_in_any_viewport(report: dict) -> None:
    tx = report["texels"]
    assert tx["same_size"]["same"] and tx["offset_viewport"]["same"], tx  # (random RGBA, odd size, offset viewport)
    assert tx["same_size"]["alphas"] == 256, tx


def test_picture_sizes_remake_the_chain_target_and_nothing_piles_up(report: dict) -> None:
    sizes = report["sizes"]
    for key, v in sizes.items():
        w, h = (int(n) for n in key.split(":")[1].split("x"))
        assert v["identity_same"] and v["dof_identity_same"] and v["bytes"] == w * h * 3, (key, v)
        assert v["world_fbo"] == [w, h] and v["chain"] == [w, h], (key, v)
    assert [v["chain_allocations"] for v in sizes.values()] == [1, 2, 3], sizes  # remade on each new size
    assert len({tuple(v["live"][k] for k in TRACKED) for v in sizes.values()}) == 1, sizes  # the old one freed


def test_room_changes_free_the_composite_with_the_renderer(report: dict) -> None:
    visits = report["room_changes"]
    for name in ("village", "cottage"):
        seen = [tuple(v["live"][k] for k in TRACKED) for v in visits if v["room"] == name]
        assert len(set(seen)) == 1, visits
    # (GL buffers grow by the same counts on every room change with or without the composite, at 0fa2f25 too: not
    # the renderer's, and not this pass's, which makes none; the textures, framebuffers and programs are checked)


def test_release_deletes_the_composite_s_objects(report: dict) -> None:
    rel = report["release"]
    assert rel["composite_objects"] == 3 and rel["listed_in_gl_objects"] and rel["composite_after"] is None, rel
    assert rel["freed"]["program"] >= 1 and rel["freed"]["framebuffer"] >= 2 and rel["freed"]["texture"] >= 2, rel


def test_studio_s_offset_canvas_is_the_same_picture_as_at_the_origin(report: dict) -> None:
    st = report["studio"]
    x, y, w, h = st["viewport"]
    assert x > 0 and w > 0 and h > 0, st  # (offset: Studio's left panel)
    assert st["canvas_identity_same"] and st["canvas_equals_origin"], st
    assert st["canvas_identity_equals_origin_identity"] and st["read_final_in_canvas"], st


def test_studio_s_lines_are_drawn_after_the_composite(report: dict) -> None:
    lines = report["studio"]["lines"]
    assert report["studio"]["lines_after_calls"] == [True], report["studio"]  # off: into the world; identity: after
    assert lines["pixels"] > 1000 and lines["outside_lines_same"], lines
    # drawn after the picture (premultiplied over it, as with the depth of field) rather than into the world: the
    # same lines, a faint one over a pale world rounding either way by a level
    assert lines["line_pixels_same_share"] >= 0.98 and lines["line_pixels_max_delta"] <= 1, lines


def test_the_game_s_camera_path_draws_studio_s_view_the_same(report: dict) -> None:
    gp = report["studio"]["game_path"]
    assert gp["same_as_studio_same_shadow_fit"] and gp["game_repeat_same"] and gp["studio_without_cutaway_same"], gp


def test_studio_s_window_resized_keeps_the_same_picture(report: dict) -> None:
    rs = report["studio"]["resized"]
    assert rs["identity_same"] and rs["world_fbo"] == rs["viewport"][2:], rs
