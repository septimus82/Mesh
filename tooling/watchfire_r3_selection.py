"""Watchfire R3: choosing what you edit in Mesh Studio's 3D view, where objects overlap.

A disposable copy of the M23B clearing (tooling/m23b_fire_study.py), opened in Mesh Studio in a hidden window and
worked with Studio's own mouse and keyboard events (nothing selected or moved by calling Studio directly):

- a lone campfire (no picture: the world draws its logs and flames);
- two campfires stacked on one spot (the trial's cold and burning watchfire);
- two signs placed with Objects > Sign, one just behind the other as the camera sees them.

The creator clicks each, clicks again where they overlap, drags what is selected, right-clicks the stack, clicks empty
ground, clicks an object with Terrain > Sculpt on, undoes and redoes, saves, and reopens. What Studio selected, its
inspector, its message and where every object stands are recorded; pictures beside ``report.json``.

    py -3.13 tooling/watchfire_r3_selection.py OUT
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

LONE = (9.6, 2.6)  # m: the clearing's campfire (m23b FIRE)
STACK = (14.0, 9.0)  # m: two campfires on one spot, in the open
HIDDEN = (6.0, 5.0)  # m: a campfire behind the cottage, hidden by it as the camera looks north
EMPTY = (16.0, 12.0)  # m: open ground
FRONT, BACK = (12.0, 6.0), (12.0, 6.6)  # m: two signs, the second just behind the first as the camera looks north


def make(out: Path) -> Path:
    import m23b_fire_study as study

    project: Path = study.make_project(out, "r3", fires=[(LONE, {}), (STACK, {}), (STACK, {"enabled": False}), (HIDDEN, {})])
    return project


def run(out: Path) -> dict[str, Any]:
    import m20c_material_study as m20c
    import m23b_fire_study as study
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops

    out.mkdir(parents=True, exist_ok=True)
    project = make(out)
    report: dict[str, Any] = {}
    d = StudioDriver(project)
    arcade = d.arcade

    def open_room(driver: Any) -> None:
        key = next(k for k, _l, path in driver.studio.project.rooms() if path.endswith("hills.json"))
        driver.button(driver.studio.project.label(key))
        driver.advance(3)

    def ground(driver: Any, x: float, y: float, up: float = 0.0) -> tuple[float, float]:
        z = driver.renderer.ground_height(x * study.PX, y * study.PX) / study.PX
        sx, sy = driver.screen((x, y, z + up))
        return float(sx), float(sy)

    def name_of(eid: Any) -> str | None:
        return (d.studio._entity(eid) or {}).get("name") if eid else None

    def seen(label: str, **extra: Any) -> dict[str, Any]:
        eid = d.studio.selected
        entity = d.studio._entity(eid) or {} if eid else {}
        row = {"selected": name_of(eid), "structure": d.studio.hd2d.structure, "message": d.studio.message,
               "inspector_name": getattr(d.studio._focusable.get("name"), "text", None),
               "inspector_burning": [t for t in d.labels() if t.startswith("Burning:")],
               "campfire_of_selected": ops.campfire_of(entity) if entity else None, **extra}
        report[label] = row
        return row

    def under_at(x: float, y: float) -> list[str]:  # (what is under the mouse; "n/a" on an engine without it)
        ids_under = getattr(d.studio.hd2d, "ids_under", None)
        return ids_under(x, y) if callable(ids_under) else ["n/a"]

    def where() -> dict[str, tuple[float, float]]:
        return {str(e.get("name")): (float(e.get("x", 0)), float(e.get("y", 0)))
                for e in ops.entities(d.studio.project.scene()) if e.get("name") != "Player"}

    try:
        open_room(d)
        # the two signs, placed as a creator places them (Objects > Sign, a click on the ground)
        for spot in (FRONT, BACK):
            m20c._look_at(d, spot[0], spot[1], 14.0)
            d.studio.set_left_tab("objects")
            d.advance()
            d.button("Sign")
            d.click(*ground(d, *spot))
            d.advance(2)
            d.key(arcade.key.ESCAPE)  # (done placing)
            d.advance()
        names = [str(e.get("name")) for e in ops.entities(d.studio.project.scene())]
        report["objects"] = names
        signs = [n for n in names if n.lower().startswith("sign")]
        report["signs"] = signs
        d.click(*ground(d, 2.0, 9.0))  # (nothing selected to start)
        d.advance()

        # 1. a lone campfire: click it (on its logs, a little above the ground)
        m20c._look_at(d, LONE[0], LONE[1] + 1.0, 12.0)
        lone_at = ground(d, *LONE, up=0.3)
        d.click(*lone_at)
        d.advance(2)
        seen("1_click_lone_campfire", under=[name_of(i) or i for i in under_at(*lone_at)])
        d.picture(out / "1_click_lone_campfire.png")
        # 1b. a campfire hidden behind the cottage: a click there selects the cottage (in front); turned with its
        # inspector (the fire stays put) and turned back; click again without moving: the fire behind it
        m20c._look_at(d, HIDDEN[0], HIDDEN[1] - 1.0, 12.0)
        hidden_at = ground(d, *HIDDEN, up=0.3)
        report["1b_under_hidden_fire"] = [name_of(i) or i for i in under_at(*hidden_at)]
        d.click(*hidden_at)
        d.advance(2)
        seen("1b_click_where_the_fire_is_hidden")
        d.picture(out / "1b_click_where_the_fire_is_hidden.png")
        sid = d.studio.hd2d.structure
        turned_from = (d.structure(sid) or {}).get("rotation") if sid else None
        fire_before = where().get("Campfire 4")
        if sid:
            d.button("Turn +90")
            d.advance(2)
        seen("1c_turn_the_selected_cottage", turned=(turned_from, (d.structure(sid) or {}).get("rotation") if sid else None),
             fire_unmoved=where().get("Campfire 4") == fire_before)
        d.key(arcade.key.Z, arcade.key.MOD_CTRL)  # (the cottage as it was)
        d.advance(2)
        report["1c_undo_turn"] = {"rotation": (d.structure(sid) or {}).get("rotation") if sid else None,
                                  "still_selected": d.studio.hd2d.structure}
        d.click(*hidden_at)
        d.advance(2)
        seen("1d_click_again_the_hidden_fire")
        d.picture(out / "1d_click_again_the_hidden_fire.png")

        # 2. the two signs: click where they overlap, then again, then again
        m20c._look_at(d, FRONT[0], FRONT[1] + 1.0, 10.0)
        at = ground(d, FRONT[0], FRONT[1], up=0.75)
        for k in range(3):
            d.click(*at)
            d.advance(2)
            seen(f"2_signs_click_{k + 1}", under=[name_of(i) or i for i in under_at(*at)])
            d.picture(out / f"2_signs_click_{k + 1}.png")
        # 3. what is selected now, dragged a metre east: only it moves
        before = where()
        selected_before = name_of(d.studio.selected)
        d.drag(at, ground(d, FRONT[0] + 1.0, FRONT[1], up=0.75))
        d.advance(2)
        after = where()
        seen("3_drag_selected", selected_before_drag=selected_before,
             moved=sorted(n for n in after if after[n] != before.get(n)))
        d.key(arcade.key.Z, arcade.key.MOD_CTRL)
        d.advance(2)
        report["3_undo"] = {"positions_restored": where() == before}
        d.key(arcade.key.Y, arcade.key.MOD_CTRL)
        d.advance(2)
        report["3_redo"] = {"positions_moved_again": where() == after}

        # 4. the stacked campfires: click, click again; the inspector each time; right-click keeps the choice
        m20c._look_at(d, STACK[0], STACK[1] + 1.0, 12.0)
        stack_at = ground(d, *STACK, up=0.3)
        for k in range(2):
            d.click(*stack_at)
            d.advance(2)
            seen(f"4_stack_click_{k + 1}", under=[name_of(i) or i for i in under_at(*stack_at)])
            d.picture(out / f"4_stack_click_{k + 1}.png")
        chosen = d.studio.selected
        d.click(*stack_at, button=arcade.MOUSE_BUTTON_RIGHT)
        d.advance(2)
        seen("4_stack_right_click", kept=d.studio.selected == chosen, menu=[t for t, _ in (d.studio.menu or (0, 0, []))[2]])
        d.key(arcade.key.ESCAPE)
        d.advance()

        # 5. empty ground deselects
        m20c._look_at(d, EMPTY[0], EMPTY[1] + 1.0, 12.0)
        report["5_under_empty"] = under_at(*ground(d, *EMPTY))
        d.click(*ground(d, *EMPTY))
        d.advance(2)
        seen("5_click_empty_ground")

        # 6. Terrain > Sculpt, Paint, Scatter on: a click on the lone campfire uses the brush, never selects (undone after)
        m20c._look_at(d, LONE[0], LONE[1] + 1.0, 12.0)
        d.studio.set_left_tab("terrain")
        d.advance()
        for tool in ("Sculpt", "Paint", "Scatter"):
            d.button(tool)
            d.advance()
            active = d.studio.hd2d.sculpt is not None
            d.click(*ground(d, *LONE, up=0.3))
            d.advance(2)
            seen(f"6_{tool.lower()}_click_on_campfire", brush_on=active)
            d.key(arcade.key.Z, arcade.key.MOD_CTRL)  # (the ground as it was)
            d.advance()
            d.button(tool)  # (off again)
            d.advance()

        # 7. save, close, reopen: where everything stands
        saved = where()
        d.key(arcade.key.S, arcade.key.MOD_CTRL)
        d.advance()
        report["7_saved"] = {"message": d.studio.message, "positions": saved}
    finally:
        d.close()
    d = StudioDriver(project)
    try:
        open_room(d)
        report["7_reopened"] = {"positions_match": where() == saved}
    finally:
        d.close()
    (out / "report.json").write_text(json.dumps(report, indent=1, default=str) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(run(Path(sys.argv[1])), indent=1, default=str))
