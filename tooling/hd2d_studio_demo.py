"""Mesh Studio's 3D view, proven (Milestone 16 Stage 5A), in a hidden window.

    py -3.13 tooling/hd2d_studio_demo.py check FLOORS_PROJECT OUT_DIR   # a project from hd2d_floors_demo.py build

Opens the lit HD-2D crossing in Mesh Studio and works it the way a person would, only through input events sent to
the window (mouse press / drag / release, key presses, clicks on Mesh Studio's own buttons), never by editing JSON:
see the 3D room; pick the structure and a character; drag the structure and turn it; undo and redo; save, close
and reopen; play-test with F4 and walk around the moved structure with the arrow keys; stop; place a second copy
of the model from the project's .glb list; undo and redo that. It checks the structure's transform is the same for
what is drawn, what collides and the floors' names, that Edit / Play / Edit leaves no extra GPU objects, and
measures the view: drawing, picking and committing an edit. Pictures and ``studio_check.json`` go to OUT_DIR.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
from hd2d_demo import SCENES, HiddenGame  # noqa: E402
from hd2d_floors_demo import _feet, hold_key  # noqa: E402

PX = 32.0
WORLD = "packs/core_regions/worlds/main.json"


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")


class StudioDriver:
    """Mesh Studio in a hidden window, worked through the window's own input events."""

    def __init__(self, project: Path) -> None:
        from engine.studio import open_studio

        self.game = HiddenGame(project, size=(1280, 720))
        self.game.load(f"{SCENES}/start.json")
        studio = open_studio(self.game.window, project, WORLD, f"{SCENES}/start.json")
        assert studio is not None, "a Studio project"
        self.studio = studio
        self.arcade = self.game.arcade
        self.frame()

    @property
    def renderer(self) -> Any:
        renderer = self.studio.hd2d.renderer
        assert renderer is not None, "the room is HD-2D"
        return renderer

    @property
    def window(self) -> Any:
        return self.game.window

    def frame(self, n: int = 1) -> Any:
        image = None
        for _ in range(n):
            self.window.dispatch_event("on_update", 1 / 60)
            self.window.dispatch_event("on_draw")
        image = self.arcade.get_image(0, 0, *self.window.get_framebuffer_size())
        return image

    def picture(self, path: Path) -> None:
        self.frame().convert("RGB").save(path)

    # ------------------------------------------------------------------ input, as the OS would send it
    def key(self, symbol: int, modifiers: int = 0) -> None:
        self.window.dispatch_event("on_key_press", symbol, modifiers)
        self.window.dispatch_event("on_key_release", symbol, modifiers)
        self.frame()

    def click(self, x: float, y: float, button: int | None = None) -> None:
        button = self.arcade.MOUSE_BUTTON_LEFT if button is None else button
        self.window.dispatch_event("on_mouse_motion", x, y, 0, 0)
        self.window.dispatch_event("on_mouse_press", x, y, button, 0)
        self.window.dispatch_event("on_mouse_release", x, y, button, 0)
        self.frame()

    def drag(self, start: tuple[float, float], end: tuple[float, float], steps: int = 12,
             button: int | None = None) -> None:
        button = self.arcade.MOUSE_BUTTON_LEFT if button is None else button
        self.window.dispatch_event("on_mouse_motion", *start, 0, 0)
        self.window.dispatch_event("on_mouse_press", *start, button, 0)
        last = start
        for i in range(1, steps + 1):
            p = (start[0] + (end[0] - start[0]) * i / steps, start[1] + (end[1] - start[1]) * i / steps)
            self.window.dispatch_event("on_mouse_drag", p[0], p[1], p[0] - last[0], p[1] - last[1], button, 0)
            last = p
            self.frame()
        self.window.dispatch_event("on_mouse_release", *end, button, 0)
        self.frame()

    def button(self, text: str, *, prefix: bool = False) -> None:
        """Click Mesh Studio's button with this text (or, with ``prefix``, starting with it), where it is on screen."""
        for widget in self.studio.ui.walk_widgets():
            label = getattr(widget, "text", None)
            if label == text or (prefix and isinstance(label, str) and label.startswith(text)):
                r = widget.rect
                self.click(r.left + r.width / 2, r.bottom + r.height / 2)
                return
        raise AssertionError(f"no button '{text}' on screen")

    def type_into(self, key: str, text: str) -> None:
        """Click Mesh Studio's text field ``key``, select what is in it (Ctrl+A), type ``text`` and press Enter, as a
        person types (key and text events into the window)."""
        k = self.arcade.key
        field = self.studio._focusable[key]
        r = field.rect
        self.click(r.left + r.width / 2, r.bottom + r.height / 2)
        self.window.dispatch_event("on_key_press", k.A, k.MOD_CTRL)
        self.window.dispatch_event("on_key_release", k.A, k.MOD_CTRL)
        self.window.dispatch_event("on_text", text)
        self.key(k.ENTER)

    def labels(self) -> list[str]:
        """Every text Mesh Studio shows (labels and buttons), top to bottom."""
        return [w.text for w in self.studio.ui.walk_widgets() if isinstance(getattr(w, "text", None), str) and w.text]

    def has_button(self, text: str) -> bool:
        return any(getattr(w, "text", None) == text for w in self.studio.ui.walk_widgets())

    def screen(self, p: tuple[float, float, float]) -> tuple[float, float]:
        """Where a world point (m) is on the window, in the 3D view."""
        view = self.studio.hd2d
        left, right, bottom, top = view._rect()
        vp = view.camera.view_projection((right - left) / (top - bottom))
        c = [sum(vp[r][k] * (p[k] if k < 3 else 1.0) for k in range(4)) for r in range(4)]
        return left + (c[0] / c[3] * 0.5 + 0.5) * (right - left), bottom + (c[1] / c[3] * 0.5 + 0.5) * (top - bottom)

    def structure(self, sid: str) -> dict[str, Any] | None:
        from engine import project_ops as ops

        found = ops.find_structure(self.studio.project.scene(), sid)
        return dict(found) if found else None

    def gl_counts(self) -> dict[str, int]:
        ctx = self.window.ctx
        ctx.gc()
        return {k: getattr(ctx.stats, k)[0] - getattr(ctx.stats, k)[1] for k in ("texture", "framebuffer", "program")}

    def close(self) -> None:
        self.game.close()


def ops_structures(studio: Any) -> list[dict[str, Any]]:
    from engine import project_ops as ops

    return ops.structures(studio.project.scene())


def check(project: Path, out: Path) -> dict[str, Any]:
    out.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"steps": []}

    def step(name: str, **facts: Any) -> None:
        report["steps"].append({"step": name, **facts})

    d = StudioDriver(project)
    k = d.arcade.key
    ctrl = k.MOD_CTRL
    try:
        studio, view = d.studio, d.studio.hd2d
        # 1-2. the HD-2D room opens in the 3D view, lit as in Play
        renderer = d.renderer
        step("open", active=view.active, structures=[st.id for st in view.structures()],
             lamps=len(renderer.lighting.lamps), shadows=renderer.lighting.enabled,
             left_panel_3d=d.has_button("Turn left"), models_button=d.has_button("Models..."))
        d.picture(out / "01_studio_3d_view.png")
        gl_edit = d.gl_counts()
        original = d.structure("crossing")

        # 3. pick: a character in front of the bridge, then the structure
        player = d.game.player()
        z = player.mesh_entity_data.get("elevation", 0.0) / PX
        d.click(*d.screen((player.center_x / PX, player.bottom / PX, z + 0.75)))
        picked_character = studio.selected
        d.click(*d.screen((10.0, 12.0, 2.0)))  # the west platform's top
        step("pick", character=picked_character, character_is_entity=bool(picked_character),
             structure=view.structure, inspector=d.has_button("Turn +90"))
        d.picture(out / "02_structure_selected.png")

        # 4. move it (drag, snapped) and turn it (the inspector's button)
        grab = d.screen((10.0, 12.0, 2.0))
        on_ground = view.ground_px(*grab, 0.0)
        assert on_ground is not None
        target = d.screen(((on_ground[0] + 64) / PX, (on_ground[1] + 32) / PX, 0.0))  # +2 m east, +1 m north
        d.drag(grab, target)
        moved = d.structure("crossing")
        d.button("Turn +90")
        turned = d.structure("crossing")
        step("move_and_turn", before=original, after_drag=moved, after_turn=turned)
        d.picture(out / "03_moved_and_turned.png")

        # 5-6. undo twice, redo twice (keyboard)
        d.key(k.Z, ctrl)
        after_undo1 = d.structure("crossing")
        d.key(k.Z, ctrl)
        after_undo2 = d.structure("crossing")
        d.key(k.Y, ctrl)
        d.key(k.Y, ctrl)
        after_redo = d.structure("crossing")
        step("undo_redo", undo1=after_undo1, undo2=after_undo2, redo2=after_redo)

        # 7. save
        d.key(k.S, ctrl)
        step("save", dirty_after=studio.project.is_dirty)
    finally:
        d.close()

    # 8. reopen: the structure is where it was put
    d = StudioDriver(project)
    try:
        studio, view = d.studio, d.studio.hd2d
        reopened = d.structure("crossing")
        renderer = d.renderer
        st = view.find("crossing")
        assert st is not None
        from engine.hd2d.picking import Picker, placement
        from engine.hd2d.renderer import _placement

        # the same transform for what is drawn (renderer), what is picked (picking) and what collides (world)
        drawn = _placement(st.x / PX, st.y / PX, st.elevation / PX, st.rotation, st.scale)
        picked = placement(st)
        world = d.window.hd2d_world
        # the west platform's centre in the model (-6, 0) is now, turned 90 degrees about the origin: (0, -6) + origin
        cx, cy = st.x / PX + 0.0, st.y / PX - 6.0
        stood = world.stand(cx, cy, 2.0, 0.3, 0.19)
        down = Picker().pick((cx, cy, 10.0), (0.0, 0.0, -1.0), [st], renderer.models)
        step("reopen", structure=reopened, same_matrix=all(abs(drawn[r][c] - picked[r][c]) < 1e-9 for r in range(4) for c in range(4)),
             floor_at_moved_platform=stood, drawn_top_at_moved_platform=None if down is None else round(down.point[2], 3),
             floors=sorted({s.floor for s in world.surfaces}))
        d.picture(out / "04_reopened.png")

        # 9-11. Play (F4), walk around the moved structure with the arrow keys, Stop (F4)
        edit_objects = d.renderer.gl_objects()
        d.key(k.F4)
        play_renderer = d.window.hd2d_renderer
        player = d.game.player()
        start = _feet(player)
        walk = []

        def note(label: str) -> None:
            fx, fy = _feet(player)
            z = player.mesh_entity_data.get("elevation", 0.0) / PX
            walk.append({"after": label, "feet_m": [round(fx, 2), round(fy, 2)], "elevation_m": round(z, 2),
                         "standable": d.window.hd2d_world.stand(fx, fy, z, 0.3, 0.19) is not None})

        blocked = not hold_key(d.game, player, k.UP, 1, 12.0, 300)
        note("up: into the moved platform's side")
        hold_key(d.game, player, k.RIGHT, 0, 27.0, 600)
        note("right: past its east end")
        hold_key(d.game, player, k.UP, 1, 13.0, 600)
        note("up: along its east side")
        hold_key(d.game, player, k.LEFT, 0, 24.0, 300)
        note("left: towards it again")
        d.picture(out / "05_play_walking_around.png")
        step("play", mode=studio.mode, hd2d=play_renderer is not None, start_feet=[round(v, 2) for v in start],
             blocked_by_moved_structure=blocked, walk=walk)
        d.key(k.F4)
        back = d.frame()
        back.convert("RGB").save(out / "06_back_in_edit.png")
        gl_back = d.gl_counts()
        still_alive = [type(o).__name__ for o in edit_objects if getattr(o, "_glo", None) not in (None, 0)
                       and getattr(getattr(o, "_glo", None), "value", 1) not in (None, 0)]
        report["edit_renderer_objects"] = {"held_before_play": len(edit_objects), "still_alive_after_stop": still_alive}
        d.key(k.F4)  # a second round: what a first Play sets up once is there now; nothing may grow
        d.frame(5)
        d.key(k.F4)
        gl_back2 = d.gl_counts()
        step("stop", mode=studio.mode, active=view.active, gl_objects_after_edit_play_edit=gl_back,
             gl_objects_after_second_round=gl_back2)

        # placing a second copy from the project's models
        d.button("Models...")
        listed = [m for m in view.models_in_project()]
        d.button("Stone Crossing", prefix=True)  # the model browser: choose it...
        d.button("Place in scene")  # ... and place a copy
        spot = d.screen((7.0, 20.0, 0.0))
        d.window.dispatch_event("on_mouse_motion", spot[0], spot[1], 0, 0)
        d.picture(out / "07_placing_preview.png")
        preview_shown = d.renderer.preview is not None
        d.click(*spot)
        new_id = view.structure
        placed = d.structure(new_id) if new_id else None
        world = d.window.hd2d_world
        new_floors = sorted({s.floor for s in world.surfaces if new_id and s.floor.startswith(new_id + "/")})
        d.picture(out / "08_second_copy.png")
        d.key(k.Z, ctrl)
        after_undo = d.structure(new_id) if new_id else None
        d.key(k.Y, ctrl)
        after_redo2 = d.structure(new_id) if new_id else None
        step("place_second_copy", models_listed=listed, preview_shown=preview_shown, new_id=new_id, placed=placed,
             collision_floors=new_floors, after_undo=after_undo, after_redo=after_redo2)

        # an AI proposes structure changes through the review workflow (what the MCP tools send); the person accepts
        proposal = studio.ai.stage_proposal_payload({"title": "Line up the copy", "source": "a test AI", "changes": [
            {"op": "set_structure", "structure_id": new_id, "x": 288, "rotation": 180},
            {"op": "place_structure", "model": "assets/models/stone_crossing.glb", "x": 800, "y": 160}]})
        summary = list(getattr(proposal, "summary", []))
        refused = studio.ai.stage_proposal_payload({"changes": [
            {"op": "place_structure", "model": "assets/models/missing.glb", "x": 100, "y": 100}]})
        studio.open_ai()
        d.frame()
        d.button("Accept")
        accepted = {"copy": d.structure(new_id or ""), "third": [dict(s) for s in ops_structures(studio)][-1],
                    "selected_structure": view.structure, "warning": studio.message if not studio.message_ok else None,
                    "newly_buried": list(view.newly_buried)}
        step("ai_proposal", summary=summary, accepted=accepted,
             missing_model_refused=refused if isinstance(refused, dict) else {"ok": True})
        d.picture(out / "09_after_ai_proposal.png")

        # the view's costs
        for _ in range(60):
            d.frame()
        t = time.perf_counter()
        for _ in range(20):
            d.click(*d.screen((cx, cy, 2.0)))  # the moved platform's top
        click_ms = (time.perf_counter() - t) * 1000 / 20
        player = d.game.player()
        z = player.mesh_entity_data.get("elevation", 0.0) / PX
        at = d.screen((player.center_x / PX, player.bottom / PX, z + 0.75))
        t = time.perf_counter()
        for _ in range(20):
            d.click(*at)  # an object: Mesh Studio's ordinary selection (inspector rebuilt) for comparison
        object_click_ms = (time.perf_counter() - t) * 1000 / 20
        d.click(*d.screen((cx, cy, 2.0)))
        report["structure_selected_for_edits"] = view.structure
        for _ in range(3):
            d.button("Raise 0.5 m")  # an edit committed: op, one undo step, the room reloaded, drawn
        for _ in range(3):
            d.key(k.Z, ctrl)
        t = time.perf_counter()
        d.frame()
        frame_ms = (time.perf_counter() - t) * 1000
        times = view.timings
        report["performance"] = {
            "draw_ms_median": round(statistics.median(times["draw_ms"]), 3),
            "draw_ms_p95": round(sorted(times["draw_ms"])[int(len(times["draw_ms"]) * 0.95)], 3),
            "pick_ms_median": round(statistics.median(times["pick_ms"]), 3),
            "structure_click_with_redraw_ms": round(click_ms, 2),
            "object_click_with_redraw_ms": round(object_click_ms, 2),
            "studio_frame_ms": round(frame_ms, 2),
            "edit_commit_ms_median": round(statistics.median(times["edit_ms"]), 1) if times["edit_ms"] else None,
            "renderer": d.renderer.stats()}
        report["gl_objects"] = {"edit_first_open": gl_edit, "edit_after_play_and_stop": gl_back,
                                "edit_after_second_play_and_stop": gl_back2}
    finally:
        d.close()
    _write(out / "studio_check.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["check"])
    parser.add_argument("project", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.project.resolve(), args.out.resolve()), indent=1, default=str))
