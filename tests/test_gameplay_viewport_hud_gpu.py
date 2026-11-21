"""#422 H8, in the real renderer and game loop (hidden windows; GL-gated: MESH_GL_SMOKE=1): what a player of the
2D (adventure) and HD-2D (hd2d_rpg) starter games sees around the room and in the controls-hint toast.

Measured from the frames, not from layout numbers (tooling/h8_visual_evidence.py): a toast is the pixels that change
when it is taken away and its border the sky-blue lines among them, so text running past the border, or a border
running past the window, fails whatever the font or renderer.
"""

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
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
HINT = "Q: Quest Log  Tab: Inventory  I: Inspector  C: Character  H: Help"
OLD_DEFAULT = [102, 102, 153]  # arcade.color.DARK_BLUE_GRAY, the purple around every small 2D room before H8
ONE_LINE = 40  # px: a one-line toast's box, its outline included, is 36 tall


@pytest.fixture(scope="module")
def projects(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    from engine.project_scaffold import create_project

    root = tmp_path_factory.mktemp("h8")
    for game in ("adventure", "hd2d_rpg"):
        create_project(root / game, game, game)
    return {game: root / game for game in ("adventure", "hd2d_rpg")}


def _frame(projects: dict[str, Path], game: str, size: tuple[int, int], out: Path, **options: Any) -> dict[str, Any]:
    import h8_visual_evidence as evidence

    return evidence.capture(projects[game], size, out, f"{game}_{size[0]}x{size[1]}", **options)


def _contained(facts: dict[str, Any]) -> None:
    assert facts["toast"], facts
    left, top, right, bottom = facts["border"]
    width, height = facts["window"]
    assert facts["changed_outside_border"] == 0, f"the toast drew outside its border: {facts}"
    assert 0 <= left and right < width and 0 <= top and bottom < height, f"the box leaves the window: {facts}"


@pytest.mark.parametrize("game", ["adventure", "hd2d_rpg"])
@pytest.mark.parametrize("size", [(1280, 720), (1920, 1080), (560, 420)])
def test_the_controls_hint_stays_inside_its_box(projects: dict[str, Path], tmp_path: Path, game: str,
                                                size: tuple[int, int]) -> None:
    facts = _frame(projects, game, size, tmp_path)
    assert facts["toasts"] == [HINT]
    _contained(facts)
    box_height = facts["border"][3] - facts["border"][1]
    if size[0] >= 1280:  # (room for it on one line)
        assert facts["layouts"] == [[HINT]] and box_height < ONE_LINE
    else:  # (it wraps: two lines, and the box is two lines tall)
        assert len(facts["layouts"][0]) == 2 and box_height > ONE_LINE


def test_the_hint_wraps_again_when_the_window_shrinks(projects: dict[str, Path], tmp_path: Path) -> None:
    facts = _frame(projects, "hd2d_rpg", (1280, 720), tmp_path, resize=(560, 420))
    assert facts["window"] == [560, 420], "the window took the new size"
    _contained(facts)
    assert facts["border"][3] - facts["border"][1] > ONE_LINE


def test_a_larger_text_scale_stays_inside(projects: dict[str, Path], tmp_path: Path) -> None:
    plain = _frame(projects, "adventure", (1280, 720), tmp_path)
    scaled = _frame(projects, "adventure", (1280, 720), tmp_path, text_scale=1.5)
    _contained(scaled)
    assert scaled["border"][3] - scaled["border"][1] > plain["border"][3] - plain["border"][1], "larger text, taller box"


def test_a_short_toast_keeps_its_box(projects: dict[str, Path], tmp_path: Path) -> None:
    facts = _frame(projects, "adventure", (1280, 720), tmp_path, toast="Game saved")
    _contained(facts)
    left, top, right, bottom = facts["border"]
    assert abs((right - left) - 181) <= 1 and abs((bottom - top) - 35) <= 1, f"180 x 34 as before H8: {facts}"


def test_a_room_smaller_than_the_window_is_framed_in_black(projects: dict[str, Path], tmp_path: Path) -> None:
    for room in (None, "packs/core_regions/scenes/house.json"):
        facts = _frame(projects, "adventure", (1280, 720), tmp_path, room=room)
        assert facts["corners"] == [[0, 0, 0]] * 4, facts["corners"]


def test_a_room_s_own_background_colour_is_kept(projects: dict[str, Path], tmp_path: Path) -> None:
    import shutil

    project = tmp_path / "own_colour"
    shutil.copytree(projects["adventure"], project)
    scene = project / "packs/core_regions/scenes/house.json"
    data = json.loads(scene.read_text(encoding="utf-8"))
    data.setdefault("settings", {})["background_color"] = "dark_slate_gray"
    scene.write_text(json.dumps(data), encoding="utf-8")
    facts = _frame({"adventure": project}, "adventure", (1280, 720), tmp_path, room="packs/core_regions/scenes/house.json")
    from arcade import color

    assert facts["corners"] == [list(color.DARK_SLATE_GRAY[:3])] * 4, facts["corners"]


def test_hd2d_rooms_keep_their_own_sky(projects: dict[str, Path], tmp_path: Path) -> None:
    facts = _frame(projects, "hd2d_rpg", (1920, 1080), tmp_path, room="packs/core_regions/scenes/cottage.json")
    assert facts["corners"][0] != [0, 0, 0] and facts["corners"][0] != OLD_DEFAULT
    assert len({tuple(c) for c in facts["corners"]}) == 1, "one sky colour round the room"
