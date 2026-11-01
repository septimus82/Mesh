"""Milestone 16 Stage 6A's acceptance workflow for the HD-2D RPG template candidate, in a hidden window.

    py -3.13 tooling/hd2d_starter_demo.py check OUT_DIR

Creates a project from the developer-only ``hd2d_rpg`` template (timed) in OUT_DIR/project, then works it only through
Mesh Studio's and the game's own window events (clicks, drags, typing, key presses; no JSON, no Blender):

1. open it in Mesh Studio; 2. select the shop and drag it 1 m east; 3. choose Person and click the west plateau in
3D (a click into the fence first is refused); undo and redo it; edit what they say; 4. change a lamp's colour and
height in Lighting;
5. an AI proposes a sign on the east plateau; the person accepts; 6. save, close and reopen; 7. Play: climb the west
stairs, talk to the new person, cross the bridge, talk to the Elder, go down the east stairs, walk under the bridge,
read the sign, walk into the cottage's door (the second room), quick-save, move, quick-load; 8. Stop and edit again.

Pictures, ``starter_check.json`` and timings (project creation, Studio and game frames, the model browser with the
kit, importing a model, GPU objects across Edit / Play / room change / Stop) go to OUT_DIR.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import tracemalloc
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))
from hd2d_floors_demo import _feet, hold_key  # noqa: E402
from hd2d_studio_demo import StudioDriver  # noqa: E402

PX = 32.0
WEST_PLATEAU_SPOT = (10.0, 24.0)  # m, 2 m up: where the new person is placed
NEW_LINE = "Welcome to the west hill!"  # what the new person is given to say in Mesh Studio


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, default=str) + "\n", encoding="utf-8")


def check(out: Path, project: Path | None = None) -> dict[str, Any]:
    """The workflow; ``project``: an HD-2D RPG project already made (as ``mesh new --template hd2d_rpg`` makes it),
    else one is made (timed) in OUT/project."""
    from engine.project_scaffold import create_project

    out.mkdir(parents=True, exist_ok=True)
    created_ms = None
    if project is None:
        project = out / "project"
        t = time.perf_counter()
        create_project(project, "Mesh Village", "hd2d_rpg")
        created_ms = round((time.perf_counter() - t) * 1000)
    report: dict[str, Any] = {"steps": [], "timings": {"create_project_ms": created_ms}}

    def step(name: str, **facts: Any) -> None:
        report["steps"].append({"step": name, **facts})

    d = StudioDriver(project)
    try:
        studio, view = d.studio, d.studio.hd2d
        k = d.arcade.key
        ctrl = k.MOD_CTRL
        d.advance(30)
        d.picture(out / "01_studio_opened.png")
        gl_open = d.gl_counts()
        step("open", room=studio.project.current, hd2d=view.active, structures=len(view.structures()),
             error=getattr(d.window, "hd2d_error", None))

        # select the shop and drag it 1 m east
        d.click(*d.screen((28.0, 12.0, 3.0)))  # its roof
        picked = view.structure
        d.drag(d.screen((28.0, 12.0, 0.0)), d.screen((29.0, 12.0, 0.0)))
        shop = d.structure("shop")
        d.picture(out / "02_shop_moved.png")
        step("move_building", picked=picked, shop=shop)

        # select a crate (click its top) and turn it a quarter
        d.click(*d.screen((24.5, 9.0, 1.0)))
        crate_picked = view.structure
        d.button("Turn +90")
        crate = d.structure("crate_1")
        d.picture(out / "02b_crate_turned.png")
        d.button("See-through in play", prefix=True)  # the cutaway, then undone
        see_through = (d.structure("crate_1") or {}).get("cutaway")
        d.key(k.Z, ctrl)
        see_through_undone = (d.structure("crate_1") or {}).get("cutaway")
        step("turn_structure", picked=crate_picked, crate=crate, see_through=see_through,
             see_through_undone=see_through_undone)

        # choose Person, click into the fence (refused), then on the west plateau (2 m up)
        d.key(k.ESCAPE)
        d.button("Person")
        fence = d.screen((7.0, 16.0, 0.0))
        d.window.dispatch_event("on_mouse_motion", *fence, 0, 0)
        d.click(*fence)
        refused = studio.message
        spot = d.screen((*WEST_PLATEAU_SPOT, 2.0))
        d.window.dispatch_event("on_mouse_motion", *spot, 0, 0)
        d.advance()
        marker = view.object_marker
        d.picture(out / "03_placing_person_on_plateau.png")
        d.click(*spot)
        placed_message = studio.message
        new_id = studio.selected
        person = dict(next(e for e in studio.project.scene()["entities"] if e.get("id") == new_id)) if new_id else None
        world = d.window.hd2d_world
        feet = (person["x"] / PX, (person["y"] - 18.0) / PX, person.get("elevation", 0) / PX) if person else None
        stands = world.stand(*feet, 0.3, 0.19) if feet else None
        d.picture(out / "04_person_placed.png")
        d.key(k.Z, ctrl)
        after_undo = any(e.get("id") == new_id for e in studio.project.scene()["entities"])
        d.key(k.Y, ctrl)
        after_redo = any(e.get("id") == new_id for e in studio.project.scene()["entities"])
        step("place_person", refused_message=refused, marker=marker, message=placed_message, entity=person,
             stands_on=stands, gone_after_undo=not after_undo, back_after_redo=after_redo)

        # edit what the new person says, in the Dialogue tab (selecting them by clicking them, if need be)
        if studio.selected != new_id:
            d.click(*d.screen((*WEST_PLATEAU_SPOT, 2.8)))
        selected = studio.selected
        d.button("Dialogue")
        d.type_into("says", NEW_LINE)
        person = dict(next(e for e in studio.project.scene()["entities"] if e.get("id") == new_id)) if new_id else None
        from engine import project_ops as ops  # noqa: PLC0415

        step("edit_person", selected=selected, says=ops.dialogue_text(person) if person else None)

        # a lamp: colour and height, in Lighting
        d.button("Lighting")
        d.button("Light 2", prefix=True)
        d.button("Cold")
        d.button("> More settings")
        d.type_into("light_height", "3")
        lamp = dict(studio.project.scene()["lights"][1])
        d.picture(out / "05_lamp_changed.png")
        d.button("Done")
        step("modify_light", lamp=lamp, renderer_lamps=d.renderer.stats()["lamps"])

        # browse the model catalogue (the starter kit) and place a lamp post beside the path
        d.key(k.ESCAPE)
        d.button("Models...")
        kit_listed = [t for t in d.labels() if t.startswith(("Lamp post", "Cottage", "Bridge"))]
        d.button("Lamp post", prefix=True)
        d.button("Place in scene")
        spot = d.screen((22.0, 11.0, 0.0))  # open grass east of the path, clear of the walk below
        left, right, bottom, top = view._rect()
        assert left < spot[0] < right and bottom < spot[1] < top, f"the lamp post's spot is off the 3D view ({spot})"
        d.window.dispatch_event("on_mouse_motion", *spot, 0, 0)
        d.advance()
        d.click(*spot)
        post_id = view.structure
        post = d.structure(post_id) if post_id else None
        d.picture(out / "05b_lamp_post_placed.png")
        d.key(k.ESCAPE)
        step("place_model", listed=kit_listed, placed=post_id, structure=post)

        # an AI proposes a sign on the east plateau; the person accepts in the review panel
        proposal = studio.ai.stage_proposal_payload({"title": "A sign for the hill", "source": "a test AI", "changes": [
            {"op": "place_prefab", "prefab": "sign", "x": 31.0 * PX, "y": 24.5 * PX + 12.0, "elevation": 64}]})
        studio.open_ai()
        d.advance()
        d.picture(out / "06_ai_proposal.png")
        d.button("Accept")
        ai_sign = next((e for e in studio.project.scene()["entities"] if e.get("tag") == "sign"
                        and abs(float(e.get("x", 0)) - 31.0 * PX) < 1), None)
        step("ai_proposal", summary=list(getattr(proposal, "summary", [])),
             sign=None if ai_sign is None else {k_: ai_sign.get(k_) for k_ in ("id", "x", "y", "elevation")})

        d.key(k.S, ctrl)
        saved = studio.message
    finally:
        d.close()

    # reopen, and play
    d = StudioDriver(project)
    try:
        studio, view = d.studio, d.studio.hd2d
        k = d.arcade.key
        d.advance(10)
        reopened = {"shop": d.structure("shop"), "person": next((dict(e) for e in studio.project.scene()["entities"]
                                                                 if e.get("id") == new_id), None),
                    "lamp": dict(studio.project.scene()["lights"][1]), "crate": d.structure("crate_1"),
                    "post": d.structure(post_id) if post_id else None}
        step("save_reopen", saved_message=saved, same=reopened["shop"] == shop and reopened["person"] == person
             and reopened["lamp"] == lamp and reopened["crate"] == crate and reopened["post"] == post)
        studio_frames = []
        for _ in range(40):
            t = time.perf_counter()
            d.frame()  # (timed: the frame as it was measured, read-back included)
            studio_frames.append((time.perf_counter() - t) * 1000)
        gl_edit = d.gl_counts()
        tracemalloc.start()

        d.key(k.F4)
        game, player = d.game, d.game.player()
        walk: list[dict[str, Any]] = []

        def note(label: str, **extra: Any) -> None:
            fx, fy = _feet(player)
            walk.append({"after": label, "feet_m": [round(fx, 2), round(fy, 2)],
                         "elevation_m": round(player.mesh_entity_data.get("elevation", 0.0) / PX, 2),
                         "floor": getattr(player, "mesh_hd2d_floor", None), "room": d.window.scene_controller.current_scene_path,
                         **extra})

        def press(key: int) -> None:  # held for a few frames, as a person's key press is
            d.window.dispatch_event("on_key_press", key, 0)
            d.advance(3)
            d.window.dispatch_event("on_key_release", key, 0)
            d.advance(3)

        def talk(label: str) -> None:
            prompt = None
            try:
                from engine.interaction import get_interact_prompt

                prompt = get_interact_prompt(d.window)
            except Exception:  # noqa: BLE001  # REASON: the prompt is a note in the report, not part of the test
                pass
            press(k.E)
            opened = d.window.is_dialogue_active()
            box = getattr(d.window.ui_controller, "dialogue_box", None)
            speaker = box._speaker_text.text if opened and box is not None else None
            first_line = box._body_text.text.splitlines()[0] if opened and box is not None and box._body_text.text else None
            if opened:
                d.picture(out / f"talk_{label.split()[-1].lower()}.png")
            for _ in range(8):
                if not d.window.is_dialogue_active():
                    break
                press(k.E)
            note(label, prompt=prompt, dialogue_opened=opened, speaker=speaker, first_line=first_line,
                 dialogue_closed=not d.window.is_dialogue_active())

        game_frames = []
        for _ in range(30):
            t = time.perf_counter()
            d.frame()  # (timed: the frame as it was measured, read-back included)
            game_frames.append((time.perf_counter() - t) * 1000)
        note("start")
        hold_key(game, player, k.LEFT, 0, 15.0, 600)
        hold_key(game, player, k.UP, 1, 24.0, 900)
        note("up the west stairs onto the plateau")
        d.picture(out / "07_play_on_the_west_plateau.png")
        hold_key(game, player, k.LEFT, 0, WEST_PLATEAU_SPOT[0] + 1.1, 400)
        talk("talked to the new person")
        hold_key(game, player, k.RIGHT, 0, 26.8, 900)
        note("across the bridge onto the east plateau")
        d.picture(out / "08_play_across_the_bridge.png")
        talk("talked to the Elder")
        hold_key(game, player, k.UP, 1, 25.2, 300)  # behind the Elder: the east landing is entered from the north
        hold_key(game, player, k.RIGHT, 0, 30.0, 400)
        hold_key(game, player, k.DOWN, 1, 14.5, 900)
        note("down the east stairs")
        hold_key(game, player, k.LEFT, 0, 20.0, 900)
        hold_key(game, player, k.UP, 1, 24.0, 900)
        note("under the bridge")
        d.picture(out / "09_play_under_the_bridge.png")
        hold_key(game, player, k.DOWN, 1, 8.5, 900)
        hold_key(game, player, k.RIGHT, 0, 20.6, 200)
        talk("read the sign")
        hold_key(game, player, k.LEFT, 0, 10.0, 900)
        d.picture(out / "10_play_at_the_cottage.png")
        hold_key(game, player, k.UP, 1, 10.5, 300)
        for _ in range(30):
            d.advance()
        player = game.player()
        note("through the cottage door")
        d.picture(out / "11_play_inside_the_cottage.png")
        d.key(k.F5)  # quick save
        saved_at = _feet(player)
        hold_key(game, player, k.RIGHT, 0, saved_at[0] + 1.5, 200)
        moved_to = _feet(player)
        d.key(k.F9)  # quick load
        for _ in range(20):
            d.advance()
        player = game.player()
        note("quick-saved, moved, quick-loaded", saved_at=[round(v, 2) for v in saved_at],
             moved_to=[round(v, 2) for v in moved_to])
        gl_play = d.gl_counts()
        mem_play = tracemalloc.get_traced_memory()[1] // 1024
        d.key(k.F4)
        d.advance(10)
        d.picture(out / "12_back_in_edit.png")
        gl_back = d.gl_counts()
        d.key(k.F4)  # a second Play / Stop: nothing may grow
        d.advance(20)
        d.key(k.F4)
        d.advance(10)
        gl_back2 = d.gl_counts()
        tracemalloc.stop()
        step("play", walk=walk, mode_after_stop=studio.mode)

        # the model browser with the kit, and importing one more model through Studio
        t = time.perf_counter()
        d.button("Models...")
        d.frame()  # (timed: the frame as it was measured, read-back included)
        open_ms = (time.perf_counter() - t) * 1000
        d.picture(out / "13_model_browser_with_kit.png")
        listed = [t_ for t_ in d.labels() if t_.startswith(("Cottage", "Shop", "Staircase", "Bridge", "Platform"))]
        d.button("Import 3D model...")
        t = time.perf_counter()
        d.type_into("model_path", str(REPO / "tooling" / "hd2d_assets" / "cottage_v2.glb"))
        check_ms = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        d.button("Import")
        import_ms = (time.perf_counter() - t) * 1000
        step("model_browser", listed=listed, imported=studio.message)
        report["timings"].update({
            "studio_frame_ms_median": round(statistics.median(studio_frames), 2),
            "game_frame_ms_median": round(statistics.median(game_frames), 2),
            "browser_open_ms": round(open_ms, 1), "import_check_ms": round(check_ms, 1),
            "import_ms": round(import_ms, 1), "renderer": d.renderer.stats()})
        report["gl"] = {"opened": gl_open, "edit_after_reopen": gl_edit, "play_after_room_change_and_load": gl_play,
                        "edit_after_stop": gl_back, "edit_after_second_play_stop": gl_back2,
                        "python_peak_during_play_kb": mem_play}
    finally:
        d.close()
    _write(out / "starter_check.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["check"])
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    os.environ.setdefault("MESH_STUDIO_NO_AI_BRIDGE", "1")
    print(json.dumps(check(args.out), indent=2, default=str))
