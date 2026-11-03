"""#461 R2: the River tool's gestures, headless (engine.studio_river.RiverTool on a real Studio project, the 3D view
stood in for: a pointer at screen (x, y) meets the ground at (x, y) px). What it saves goes through R1's checked ops,
one undo step a finished gesture; what it shows before then is never saved; a refused point, drag or value changes
nothing. The real window is tests/test_river_tool_gpu.py."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from engine import project_ops as ops
from engine.hd2d.settings import parse_hd2d
from engine.studio_river import RiverTool

pytestmark = pytest.mark.fast


class _Studio:
    def __init__(self, project: Any) -> None:
        self.project, self.message, self.ok, self.rebuilt = project, "", True, 0

    def _say(self, text: str, ok: bool = True) -> None:
        self.message, self.ok = text, ok

    def _rebuild(self) -> None:
        self.rebuilt += 1

    def _refresh_top_bar(self) -> None:
        pass


@pytest.fixture()
def tool(tmp_path: Path) -> RiverTool:
    from engine.project_scaffold import create_project
    from engine.studio_project import Project

    root = tmp_path / "game"
    create_project(root, "Game", template_id="hd2d_rpg")
    project = Project(root, json.loads((root / "config.json").read_text(encoding="utf-8"))["world_file"])
    studio = _Studio(project)
    raw = project.scene()["settings"]["hd2d"]
    view = SimpleNamespace(studio=studio, renderer=SimpleNamespace(settings=parse_hd2d(raw)),
                           sculpt=None, sculpt_at=None, cancel_stroke=lambda: False,
                           ground_hit=lambda x, y: (x / 32, y / 32, 0.0))
    t = RiverTool(cast(Any, view))
    t.__dict__["_to_screen"] = lambda p: (p[0] * 32, p[1] * 32)  # (a post's screen place: its ground px)
    t.on = True
    return t


def _steps(t: RiverTool) -> int:
    return len(t.studio.project._undo)


def _draw(t: RiverTool, points: list[tuple[float, float]]) -> None:
    for x, y in points:
        t.press(x, y)


COURSE = [(160.0, 100.0), (320.0, 110.0), (480.0, 100.0), (640.0, 120.0)]


def test_drawing_shows_a_provisional_river_and_saves_it_once_finished(tool: RiverTool) -> None:
    undo0 = _steps(tool)
    _draw(tool, COURSE)
    assert tool.draft is not None and len(tool.draft) == 4
    assert ops.rivers(tool.studio.project.scene()) == [] and _steps(tool) == undo0, "nothing saved while drawn"
    assert [r.id for r in tool.renderer.settings.rivers] == ["river"], "but shown"
    pts = tool.draft
    assert pts[0][2] == 64.0 and pts[0][3] == pytest.approx(8.0), "2 m wide, 0.25 m over the ground clicked"
    tool.finish()
    assert _steps(tool) == undo0 + 1 and tool.selected == "river" and tool.draft is None
    (saved,) = ops.rivers(tool.studio.project.scene())
    assert saved == {"id": "river", "points": pts}, "a plain river: 1 m/s, stored without its default flow"


def test_a_refused_point_is_not_added_and_one_point_is_no_river(tool: RiverTool) -> None:
    tool.press(*COURSE[0])
    tool.finish()
    assert "at least two points" in tool.studio.message and tool.draft is not None and len(tool.draft) == 1
    tool.press(*COURSE[1])
    tool.press(170.0, 112.0)  # straight back over the first: the course would fold
    assert len(tool.draft) == 2 and not tool.studio.ok and "refused" in tool.studio.message, tool.studio.message
    tool.press(480.0, 10.0)  # its banks would reach off the room's ground (y 0)
    assert len(tool.draft) == 2 and "off the room's ground" in (tool.error or ""), tool.error
    tool.cancel()
    assert tool.draft is None and tool.renderer.settings.rivers == () and ops.rivers(tool.studio.project.scene()) == []


def test_a_point_never_stands_above_the_one_before(tool: RiverTool) -> None:
    tool.view.ground_hit = lambda x, y: (x / 32, y / 32, 0.0 if x < 400 else 1.0)  # rising ground downstream
    _draw(tool, COURSE)
    levels = [p[3] for p in tool.draft or []]
    assert levels == sorted(levels, reverse=True) and levels[-1] == levels[0], levels


def test_a_drag_saves_once_when_let_go_and_a_refused_drag_saves_nothing(tool: RiverTool) -> None:
    _draw(tool, COURSE)
    tool.finish()
    undo0, before = _steps(tool), ops.rivers(tool.studio.project.scene())[0]["points"]
    tool.press(320.0, 110.0)  # the second point's post
    assert tool.gesture is not None and tool.point == 1
    for x in (330.0, 340.0, 350.0):
        tool.drag_to(x, 140.0)
        tool.tick()
    assert _steps(tool) == undo0, "nothing saved while dragging"
    assert tool.renderer.settings.rivers[0].points[1][:2] == (350.0, 140.0), "shown where it is dragged"
    tool.release()
    after = ops.rivers(tool.studio.project.scene())[0]["points"]
    assert _steps(tool) == undo0 + 1 and after[1] == [350.0, 140.0, *before[1][2:]], after[1]
    # dragged where the checks refuse it: the last valid course stays shown, and nothing is saved
    tool.press(350.0, 140.0)
    tool.drag_to(330.0, 160.0)
    tool.tick()
    tool.drag_to(150.0, 105.0)  # onto the first point
    tool.tick()
    assert tool.gesture is not None and tool.gesture["bad"]
    assert tool.renderer.settings.rivers[0].points[1][:2] == (330.0, 160.0), "the last valid one, shown"
    tool.release()
    assert ops.rivers(tool.studio.project.scene())[0]["points"] == after and _steps(tool) == undo0 + 1
    assert "Refused" in tool.studio.message and [list(p) for p in tool.renderer.settings.rivers[0].points] == after


def test_esc_and_a_reload_drop_an_unfinished_gesture(tool: RiverTool) -> None:
    _draw(tool, COURSE)
    tool.finish()
    saved = ops.rivers(tool.studio.project.scene())
    tool.press(320.0, 110.0)
    tool.drag_to(340.0, 150.0)
    tool.tick()
    assert tool.cancel() and tool.gesture is None
    assert ops.rivers(tool.studio.project.scene()) == saved
    assert [list(p) for p in tool.renderer.settings.rivers[0].points] == saved[0]["points"], "the saved one shown"
    tool.selected = None
    _draw(tool, [(160.0, 400.0), (320.0, 400.0)])
    tool.room_loaded()
    assert tool.draft is None and ops.rivers(tool.studio.project.scene()) == saved


def test_insert_remove_width_level_flow_reverse_and_remove_the_river(tool: RiverTool) -> None:
    _draw(tool, COURSE)
    tool.finish()
    undo0 = _steps(tool)

    def points() -> list[list[float]]:
        return ops.rivers(tool.studio.project.scene())[0]["points"]

    tool.point = 1
    tool.insert_point()
    assert len(points()) == 5 and tool.point == 2 and _steps(tool) == undo0 + 1
    new = points()[2]
    assert 320 < new[0] < 480, "halfway along the course"
    tool.remove_point()
    assert len(points()) == 4 and _steps(tool) == undo0 + 2
    tool.point = 2
    tool.set_point(width_m=3.0)
    assert points()[2][2] == 96.0
    tool.set_point(level_m=1.0)  # above the point upstream (0.25 m): uphill, refused
    assert points()[2][3] == pytest.approx(8.0) and "uphill" in (tool.error or "") and _steps(tool) == undo0 + 3
    tool.set_point(level_m=-0.1)  # (now the next point, still at 0.25 m, would be uphill of it: refused too)
    assert points()[2][3] == pytest.approx(8.0) and "uphill" in (tool.error or "")
    tool.point = 3
    tool.set_point(level_m=-0.1)  # the mouth lower: fine
    assert points()[3][3] == pytest.approx(-3.2)
    tool.set_look(flow=2.5)
    assert ops.rivers(tool.studio.project.scene())[0]["flow"] == 2.5
    levels = [p[3] for p in points()]
    tool.reverse()
    turned = points()
    assert [p[3] for p in turned] == levels, "the water still falls from the first point"
    assert turned[0][:2] == [640.0, 120.0], "the old mouth is its source now"
    for _ in range(3):  # (4 points: the third is refused)
        tool.point = 0
        tool.remove_point()
    assert len(points()) == 2 and "at least two" in tool.studio.message
    tool.remove_river()
    assert ops.rivers(tool.studio.project.scene()) == [] and tool.selected is None
    assert tool.renderer.settings.rivers == ()
