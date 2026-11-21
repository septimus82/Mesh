"""M17-L3 E2, in real frames (hidden windows; tooling/hd2d_lamp_glow_demo.py): a lamp lights its own lamp head and
nothing else. Each of the investigation's four rooms is drawn as E2 draws it and with the lamp-head association off
(E1's frame): only pixels inside the lamp heads differ, and a room with no head (the cottage's ceiling lamp; the
village with every lamp off) is byte-identical, drawn with the same draws. The glow follows its lamp's colour and
intensity, goes with the lamp, and Mesh Studio keeps it through an edit, undo / redo, saving and reopening.
GL-gated: set MESH_GL_SMOKE=1."""

from __future__ import annotations

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
import hd2d_lamp_glow_demo as demo  # noqa: E402

HEADS = {"village": 2, "lakeside": 4, "fixtures": 2, "cottage": 0}
# heads in view from each room's camera (Lakeside lamp 4's lantern is inside the cottage's corner, hidden by its walls;
# its other posts and #459's lamp B stand outside the picture)
SEEN = {"village": [0, 1], "lakeside": [0], "fixtures": [0], "cottage": []}


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    # (the AI bridge off for its Studio session only, then as it was: absent stays absent, a value comes back)
    with pytest.MonkeyPatch.context() as env:
        env.setenv("MESH_STUDIO_NO_AI_BRIDGE", "1")
        return demo.check(tmp_path_factory.mktemp("glow") / "d")


@pytest.mark.parametrize("room", demo.ROOMS)
def test_only_the_lamp_heads_change_in_each_investigation_room(run: dict, room: str) -> None:
    r = run[room]
    assert r["lamp_head_draws"] == HEADS[room] and len(r["per_head"]) == HEADS[room]
    assert r["outside_heads"] == 0, r  # (Lakeside lamp 4's cottage, #459's panel: unchanged)
    seen = [i for i, h in enumerate(r["per_head"]) if h["changed"]]
    assert seen == SEEN[room], r["per_head"]
    assert all(r["per_head"][i]["changed"] > 20 and r["per_head"][i]["luma"][1] > r["per_head"][i]["luma"][0] + 25
               for i in seen), r["per_head"]


def test_no_head_means_the_e1_frame_with_the_e1_draws(run: dict) -> None:
    for label in ("cottage", "variant_off"):
        r = run[label]
        assert r["changed"] == 0 and r["lamp_head_draws"] == 0, (label, r)
        assert r["static_draws"] == r["static_draws_e1"] and r["buffer_bytes"] == r["buffer_bytes_e1"]


def test_each_head_is_one_more_draw_and_no_more_memory(run: dict) -> None:
    for room in ("village", "lakeside", "fixtures"):
        r = run[room]
        # the heads leave their material's batch: one draw each, less the batch they all left (every lamp post lit)
        assert r["static_draws"] - r["static_draws_e1"] == r["lamp_head_draws"] - 1, (room, r)
        assert r["buffer_bytes"] == r["buffer_bytes_e1"]


def test_the_glow_follows_its_lamps_colour(run: dict) -> None:
    warm, blue = run["village"]["per_head"], run["variant_blue_east"]["per_head"]
    assert abs(blue[0]["luma"][1] - warm[0]["luma"][1]) < 3  # (the west head: as it was, but for the east light on it)
    w, b = warm[1]["rgb"], blue[1]["rgb"]
    assert b[2] > w[2] + 40 and b[0] < w[0], (w, b)  # (the east lamp's blue light: a bluer, less red head)


def test_the_glow_follows_its_lamps_intensity_and_goes_with_it(run: dict) -> None:
    west = {label: run[label]["per_head"][0] for label in ("variant_dim_west", "village", "variant_bright_west",
                                                           "variant_zero_west")}
    lumas = [west[k]["luma"][1] for k in ("variant_dim_west", "village", "variant_bright_west")]
    assert lumas[0] < lumas[1] < lumas[2], lumas  # (0.5, 1.6, 3)
    assert west["variant_zero_west"]["changed"] == 0  # (intensity 0: no glow)
    for label in ("variant_zero_west", "variant_west_off"):  # (only the east head is drawn on its own, glowing)
        r = run[label]
        east = r["per_head"][-1]
        assert r["lamp_head_draws"] == 1 and r["outside_heads"] == 0, label
        assert abs(east["luma"][1] - run["village"]["per_head"][1]["luma"][1]) < 3, (label, east)


def test_it_is_a_lit_lantern_not_a_white_box(run: dict) -> None:
    """The kit lantern's glass in the template lamp's amber light: warm and bright, its colour kept (the blue channel
    well below the red), never washed to white."""
    for head in run["village"]["per_head"]:
        r, g, b = head["rgb"]
        assert r > 110 and b < 0.7 * r and min(r, g, b) < 200, head
        dark, bright = head["luma_p10_p90"]
        assert bright > 2.5 * dark, head  # (its pixel art kept: the glass glows, the iron frame stays dark)


def test_studio_keeps_it_through_edits_undo_saving_and_reopening(run: dict) -> None:
    assert run["studio"] == {"heads_in_edit_view": 2, "heads_after_edit": 1, "saved": True, "heads_after_undo": 2,
                             "heads_after_redo": 1, "heads_after_reopen": 1}
