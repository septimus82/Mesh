"""M17-L3 C3: in Mesh Studio (hidden window, worked through window input events), every control the lighting panel
shows in an HD-2D room does what it says to what the renderer draws, and none is there that doesn't.

- A sweep clicks each button the panel shows (a lamp chosen, its More settings open) and types into each box: every
  edit changes what the renderer gets (its settings, lamps and shadow slots), and Ctrl+Z restores it. A click that
  edits nothing is only a choice already made (the highlighted one), or moves around the panel. The one edit that
  draws nothing new: "Casts shadows" on a lamp past the two shadow maps, which changes only who gets the next free
  map (C2), its note saying it shines through walls.
- A lamp's brightness, in real frames: brighter, dimmer and 0 (as dark as switched off) for a lamp with a shadow map
  and one past the two maps; a switched-off lamp's brightness changes nothing drawn (its row says "off").
- Shadows on/off is the room's HD-2D shadows: off draws none (the panel says so), Ctrl+Z / Ctrl+Y.
- The 2D settings HD-2D doesn't use are named and kept: their values survive editing, saving and reopening.
- Placing a light switches on no 2D lighting; a 2D room in the same project still shows the 2D panel.
Set MESH_GL_SMOKE=1."""

from __future__ import annotations

import copy
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
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
SCENE = "packs/core_regions/scenes/start.json"
KEPT_2D = {"lighting_enabled": False, "lighting_ambient_color": [30, 30, 40, 255], "lighting_shadow_quality": "high"}
NAVIGATION = ("Done", "+ Add light", "> More settings", "v More settings")  # (and each "Light N: ..." row: choosing)


def _drawn(d: Any) -> tuple[Any, ...]:
    """What the renderer draws the room's lighting from."""
    r = d.renderer
    s, lighting = r.settings, r.lighting
    return (s.shadows, s.shadow_softness, s.shadow_strength, s.lights, s.ambient_color, lighting.enabled, lighting.pcf,
            tuple(lighting.lamp_slots))


def _view(d: Any) -> Any:
    """The 3D view in a real frame, its motion at the same moment every time."""
    d.window.motion_time = 0.0
    d.window.water_time = 0.0
    image = d.frame().convert("RGB")
    left, right, bottom, top = d.studio._map_rect()
    return image.crop((int(left), int(image.height - top), int(right), int(image.height - bottom)))


def _brightness(image: Any) -> float:
    from PIL import ImageStat

    return float(ImageStat.Stat(image.convert("L")).mean[0])


def _panel_widgets(d: Any) -> list[Any]:
    right = d.window.width - d.studio._panel_widths()[1]
    return [w for w in d.studio.ui.walk_widgets() if w.rect.left >= right - 1]


def _panel_survey(d: Any) -> tuple[list[str], set[str]]:
    """Every button text and text box the right panel shows, scrolled through as a person would."""
    from engine.studio_ui import IconButton

    buttons: list[str] = []
    boxes: set[str] = set()

    def look() -> bool:
        shown = _panel_widgets(d)
        buttons.extend(w.text for w in shown if isinstance(w, IconButton) and w.text not in buttons)
        boxes.update(k for k, f in d.studio._focusable.items() if getattr(f, "parent", None) is not None and f in shown)
        return False

    d._scroll_both(look)
    return buttons, boxes


def _button_widget(d: Any, text: str) -> Any:
    from engine.studio_ui import IconButton

    return next((w for w in d.studio.ui.walk_widgets() if isinstance(w, IconButton) and w.text == text), None)


def _choose(d: Any, index: int) -> None:
    if d.studio.light != index:
        d.button(f"Light {index + 1}:", prefix=True)


def _sweep(d: Any, index: int) -> dict[str, Any]:
    """Click every button and type into every box of the panel, with light ``index`` chosen; undo each edit."""
    from engine.hd2d import settings as S
    from engine.studio import S_ACTIVE

    studio, k = d.studio, d.arcade.key
    buttons, boxes = _panel_survey(d)
    out: dict[str, Any] = {"buttons": buttons, "boxes": sorted(boxes), "edits": {}, "no_edit": {}}
    for text in buttons:
        if text in NAVIGATION or text.startswith("Light "):
            continue
        _choose(d, index)
        if studio.expanded != "light_more":
            d.button("> More settings")
        scene, drawn = copy.deepcopy(studio.project.scene()), _drawn(d)
        allocation = S.scene_shadow_allocation(scene)
        d.button(text)
        if studio.project.scene() == scene:
            widget = _button_widget(d, text)
            out["no_edit"][text] = bool(widget is not None and (widget.style == S_ACTIVE or widget.disabled))
            continue
        changed = _drawn(d) != drawn
        moved = S.scene_shadow_allocation(studio.project.scene()) != allocation
        d.key(k.Z, k.MOD_CTRL)
        out["edits"][text] = {"drawn_changed": changed, "undone": studio.project.scene() == scene
                              and _drawn(d) == drawn, "allocation_changed": moved}
    light = studio.project.scene()["lights"][index]
    values = {"light_x": f"{light['x'] + 32:g}", "light_y": f"{light['y'] + 32:g}", "light_radius": "300",
              "light_height": "3", "light_intensity": "3", "light_rgb": "200, 120, 40", "shadow_strength_room": "0.5"}
    out["box_values"] = sorted(values)
    for key, value in values.items():
        _choose(d, index)
        if studio.expanded != "light_more":
            d.button("> More settings")
        scene, drawn = copy.deepcopy(studio.project.scene()), _drawn(d)
        d.type_into(key, value)
        changed = _drawn(d) != drawn and studio.project.scene() != scene
        d.key(k.Z, k.MOD_CTRL)
        out["edits"][f"box:{key}"] = {"drawn_changed": changed, "undone": studio.project.scene() == scene
                                      and _drawn(d) == drawn}
    return out


def _texts_have(texts: list[str], phrase: str) -> bool:
    return any(phrase in t for t in texts)


@pytest.fixture(scope="module")
def run(tmp_path_factory: pytest.TempPathFactory) -> dict:
    # (the AI bridge off for the session only, then as it was: absent stays absent, a value comes back, also when the
    # session fails part way)
    with pytest.MonkeyPatch.context() as env:
        env.setenv("MESH_STUDIO_NO_AI_BRIDGE", "1")
        return _lighting_session(tmp_path_factory)


def _lighting_session(tmp_path_factory: pytest.TempPathFactory) -> dict:
    from hd2d_studio_demo import StudioDriver

    from engine import project_ops as ops
    from engine.project_scaffold import create_project

    project = tmp_path_factory.mktemp("c3") / "Lighting controls"
    create_project(project, "Lighting controls", "hd2d_rpg")
    path = project / SCENE
    scene = json.loads(path.read_text(encoding="utf-8"))  # sky colour, two lamp posts' lamps (both shadow maps)
    scene = ops.set_hd2d_sun(scene, preset="night")
    for x, y in ((400.0, 800.0), (880.0, 800.0), (960.0, 1000.0)):
        scene, index = ops.add_light(scene, x, y, color="Warm", radius=200)
    scene = ops.set_light(scene, 4, flicker="torch")  # Light 5: past the maps, a 2D torch flicker
    scene = ops.set_light(scene, 5, shadows=False, enabled=False)  # Light 6: switched off
    scene["settings"].update(copy.deepcopy(KEPT_2D))
    path.write_bytes(json.dumps(scene, indent=2).encode("utf-8"))
    out: dict[str, Any] = {"project": project}
    d = StudioDriver(project)
    try:
        studio, k = d.studio, d.arcade.key
        origin = studio.project.current
        d.button("Lighting")
        out["panel"] = {"texts": d.texts(), "survey": _panel_survey(d)[0]}
        _choose(d, 1)
        d.button("> More settings")
        d._scroll_panels(lambda: _texts_have(d.texts(), "Flicker: none"))
        out["light2"] = d.texts()
        _choose(d, 4)
        d._scroll_panels(lambda: _texts_have(d.texts(), "Flicker: none"))
        out["light5"] = d.texts()

        _choose(d, 3)
        out["light4_note"] = d._scroll_panels(lambda: _texts_have(d.texts(), "lights earlier in the list have them"))

        # The sweep: a lamp with a shadow map, then one past the two maps.
        out["sweep_light2"] = _sweep(d, 1)
        out["sweep_light4"] = _sweep(d, 3)

        # Brightness, in real frames.
        base = _view(d)
        frames: dict[str, float] = {"base": _brightness(base)}
        _choose(d, 3)  # past the two maps
        d.type_into("light_intensity", "3")
        frames["l4_3"] = _brightness(_view(d))
        out["l4_3_texts"] = d.texts()
        out["l4_3_slots"] = _drawn(d)[-1]
        d.key(k.Z, k.MOD_CTRL)
        out["l4_undo_same"] = list(_view(d).getdata()) == list(base.getdata())
        d.key(k.Y, k.MOD_CTRL)
        out["l4_redo_intensity"] = d.renderer.settings.lights[2].intensity
        d.key(k.Z, k.MOD_CTRL)
        d.type_into("light_intensity", "0")
        zero = _view(d)
        frames["l4_0"] = _brightness(zero)
        out["l4_zero_note"] = _texts_have(d.texts(), "At brightness 0 it gives no light.")
        d.key(k.Z, k.MOD_CTRL)
        d.button("On: On")
        off = _view(d)
        frames["l4_off"] = _brightness(off)
        out["l4_zero_is_off"] = list(zero.getdata()) == list(off.getdata())
        d.key(k.Z, k.MOD_CTRL)
        # Dimmer at the bottom: the smallest step goes to 0 (as dark as off), then Dimmer is disabled; Brighter recovers.
        def l4() -> tuple[Any, float]:
            return studio.project.scene()["lights"][3].get("intensity"), d.renderer.settings.lights[2].intensity

        d.type_into("light_intensity", "0.05")
        floor: dict[str, Any] = {"start": l4()}
        d.button("Dimmer")
        floor["dimmed"] = l4()
        floor["dimmed_is_off"] = list(_view(d).getdata()) == list(off.getdata())
        floor["dimmer_disabled"] = bool(_button_widget(d, "Dimmer").disabled)
        scene = copy.deepcopy(studio.project.scene())
        d.button("Dimmer")
        floor["disabled_click_no_edit"] = studio.project.scene() == scene
        d.button("Brighter")
        floor["recovered"] = l4()
        floor["recovered_lit"] = _brightness(_view(d)) > frames["l4_0"]
        floor["dimmer_enabled_again"] = not _button_widget(d, "Dimmer").disabled
        d.key(k.Z, k.MOD_CTRL)
        floor["undo_brighter"] = l4()
        d.key(k.Z, k.MOD_CTRL)
        floor["undo_dimmer"] = l4()
        d.key(k.Y, k.MOD_CTRL)
        floor["redo_dimmer"] = l4()
        d.key(k.Z, k.MOD_CTRL)
        d.key(k.Z, k.MOD_CTRL)
        floor["back_to_start"] = list(_view(d).getdata()) == list(base.getdata())
        out["dimmer_floor"] = floor
        _choose(d, 1)  # a shadow map's lamp
        before = d.renderer.settings.lights[0].intensity
        d.button("Brighter")
        frames["l2_brighter"] = _brightness(_view(d))
        out["l2_brighter"] = (before, d.renderer.settings.lights[0].intensity)
        d.key(k.Z, k.MOD_CTRL)
        d.button("Dimmer")
        frames["l2_dimmer"] = _brightness(_view(d))
        out["l2_dimmer"] = (before, d.renderer.settings.lights[0].intensity)
        d.key(k.Z, k.MOD_CTRL)
        _choose(d, 5)  # switched off
        drawn = _drawn(d)
        d.type_into("light_intensity", "3")
        out["l6_off"] = {"edited": studio.project.scene()["lights"][5].get("intensity") == 3.0,
                         "drawn_same": _drawn(d) == drawn, "frame_same": list(_view(d).getdata()) == list(base.getdata()),
                         "tagged_off": _texts_have(d.texts(), "Light 6: Warm, size 200 - off")}
        d.key(k.Z, k.MOD_CTRL)
        out["frames"] = frames

        # Shadows on/off: the room's HD-2D shadows.
        d.button("Shadows off")
        shadowless = _view(d)
        out["shadows_off"] = {"enabled": d.renderer.lighting.enabled, "file": studio.project.scene()["settings"]["hd2d"]
                              .get("shadows"), "texts": d.texts(),
                              "frame_differs": list(shadowless.getdata()) != list(base.getdata())}
        d.key(k.Z, k.MOD_CTRL)
        out["shadows_undo_same"] = list(_view(d).getdata()) == list(base.getdata())
        d.key(k.Y, k.MOD_CTRL)
        out["shadows_redo_same"] = list(_view(d).getdata()) == list(shadowless.getdata())
        d.key(k.Z, k.MOD_CTRL)

        # Placing a light switches on no 2D lighting.
        settings_before = copy.deepcopy(studio.project.scene()["settings"])
        count = len(studio.project.scene()["lights"])
        d.button("+ Add light")
        left, right, bottom, top = studio._map_rect()
        d.click((left + right) / 2, (bottom + top) / 2)
        out["placed"] = {"added": len(studio.project.scene()["lights"]) == count + 1,
                         "settings_same": studio.project.scene()["settings"] == settings_before,
                         "said": studio.message}
        d.key(k.Z, k.MOD_CTRL)

        # A 2D room in the same project: the 2D panel, as before; back in the HD-2D room, its own.
        studio.new_room_form = {"kind": "2d", "width": 24, "depth": 16, "outdoor": True}
        studio.create_room("Cellar")
        d.advance()
        if not d.has_button("As project"):
            d.button("Lighting")
        out["room_2d"] = {"buttons": _panel_survey(d)[0], "texts": d.texts()}
        studio.switch_room(origin)
        d.advance()
        if not d.has_button("Shadows on"):
            d.button("Lighting")
        out["back_in_hd2d"] = _panel_survey(d)[0]

        # Saved and reopened: what was set, and the 2D values kept.
        _choose(d, 3)
        d.type_into("light_intensity", "2.5")
        d.button("Shadows off")
        d.key(k.S, k.MOD_CTRL)
        out["saved_clean"] = not studio.project.is_dirty
    finally:
        d.close()
    d = StudioDriver(project)
    try:
        out["reopened"] = {"shadows": d.renderer.settings.shadows, "l4": d.renderer.settings.lights[2].intensity,
                           "slots": _drawn(d)[-1]}
        d.button("Lighting")
        out["reopened"]["texts"] = d.texts()
        widget = _button_widget(d, "Shadows off")
        from engine.studio import S_ACTIVE

        out["reopened"]["off_active"] = widget is not None and widget.style == S_ACTIVE
    finally:
        d.close()
    out["file"] = json.loads(path.read_text(encoding="utf-8"))
    return out


HIDDEN_2D = ("On", "Off", "As project", "Day", "Dusk", "Night", "Cave", "Black", "Darker", "Project's",
             "> Fine-tune shadows", "Low", "Normal", "High", "Characters cast shadows: On",
             "Steady", "Candle", "Torch", "Fire", "Faulty lamp", "Custom", "Calmer", "Livelier")


def test_the_hd2d_panel_shows_only_what_the_renderer_reads(run: dict) -> None:
    for survey in (run["panel"]["survey"], run["sweep_light2"]["buttons"], run["sweep_light4"]["buttons"],
                   run["back_in_hd2d"]):
        assert not set(HIDDEN_2D) & set(survey), set(HIDDEN_2D) & set(survey)
    assert {"Shadows on", "Shadows off", "Sharp", "Soft", "Softer"} <= set(run["panel"]["survey"])
    assert {"Dimmer", "Brighter", "On: On", "Casts shadows: On"} <= set(run["sweep_light2"]["buttons"])
    texts = run["panel"]["texts"]
    assert _texts_have(texts, "An HD-2D room's lights are always lit")
    assert _texts_have(texts, "Not in HD-2D rooms: lighting on/off, room light presets, shadow edge width and quality, "
                              "characters' lamp shadows, flicker. This room keeps its 2D lighting on/off, room light, "
                              "shadow quality for 2D lighting; unused here.")
    assert any(t == "Light 1: room light colour (custom)" for t in texts), texts


def test_every_edit_from_the_hd2d_panel_changes_what_is_drawn_and_undoes(run: dict) -> None:
    for name in ("sweep_light2", "sweep_light4"):
        sweep = run[name]
        assert sweep["edits"], name
        inert = {text: e for text, e in sweep["edits"].items() if not (e["drawn_changed"] and e["undone"])}
        if name == "sweep_light4":  # past the two maps, "Casts shadows" draws nothing new: it changes which lamp the
            # next free map goes to (C2's allocation), and the panel says it shines through walls (C2's note)
            assert inert.pop("Casts shadows: On") == {"drawn_changed": False, "undone": True,
                                                      "allocation_changed": True}
            assert run["light4_note"]
        assert not inert, (name, inert)
        assert all(sweep["no_edit"].values()), (name, sweep["no_edit"])  # (only the choice already made)
        assert set(sweep["boxes"]) == set(sweep["box_values"]), name  # (every box the panel shows was tried)
        assert {"Dimmer", "Brighter", "Smaller", "Bigger", "Shadows off", "Duplicate", "Delete"} <= set(sweep["edits"])


def test_brightness_in_real_frames(run: dict) -> None:
    f = run["frames"]
    assert f["l4_0"] < f["base"] < f["l4_3"], f  # (past the two maps: lit, without a shadow map)
    assert run["l4_zero_is_off"] and f["l4_0"] == f["l4_off"]  # (brightness 0: as dark as switched off)
    assert run["l4_zero_note"]
    assert run["l4_undo_same"] and run["l4_redo_intensity"] == 3.0
    assert run["l4_3_slots"] == (0, 1, -1, -1)  # (its brightness changes no shadow map)
    assert _texts_have(run["l4_3_texts"], "brightness 3x")
    assert f["l2_dimmer"] < f["base"] < f["l2_brighter"], f
    assert run["l2_brighter"] == (1.6, 2.0) and run["l2_dimmer"] == (1.6, 1.28)


def test_dimmer_at_the_bottom_reaches_zero_and_stops_and_brighter_recovers(run: dict) -> None:
    f = run["dimmer_floor"]
    assert f["start"] == (0.05, 0.05)
    assert f["dimmed"] == (0.0, 0.0) and f["dimmed_is_off"]  # (the smallest step: 0, as dark as switched off)
    assert f["dimmer_disabled"] and f["disabled_click_no_edit"]  # (at 0: disabled, never raises it)
    assert f["recovered"] == (0.06, 0.06) and f["recovered_lit"] and f["dimmer_enabled_again"]
    assert f["undo_brighter"] == (0.0, 0.0) and f["undo_dimmer"] == (0.05, 0.05) and f["redo_dimmer"] == (0.0, 0.0)
    assert f["back_to_start"]


def test_a_switched_off_lamps_brightness_draws_nothing_and_says_off(run: dict) -> None:
    assert run["l6_off"] == {"edited": True, "drawn_same": True, "frame_same": True, "tagged_off": True}


def test_shadows_off_is_the_rooms_hd2d_shadows(run: dict) -> None:
    off = run["shadows_off"]
    assert off["enabled"] is False and off["file"] is False and off["frame_differs"]
    assert _texts_have(off["texts"], "Shadows are off in this room: every light shines through walls.")
    assert not any(t.endswith(" - shadows") for t in off["texts"])
    assert not _texts_have(off["texts"], "Shadow edges")  # (nothing to shape)
    assert run["shadows_undo_same"] and run["shadows_redo_same"]


def test_lamp_rows_name_flicker_as_not_drawn(run: dict) -> None:
    assert _texts_have(run["light2"], "Flicker: none in HD-2D rooms, lamps shine steadily.")
    assert _texts_have(run["light5"], "This light keeps its torch flicker for 2D.")
    assert _texts_have(run["light2"], "brightness 1.6x")


def test_placing_a_light_switches_on_no_2d_lighting(run: dict) -> None:
    assert run["placed"]["added"] and run["placed"]["settings_same"]
    assert "lighting turned on" not in run["placed"]["said"]


def test_a_2d_room_keeps_the_2d_panel(run: dict) -> None:
    buttons = set(run["room_2d"]["buttons"])
    assert {"On", "Off", "As project", "Dusk", "Darker", "Shadows on", "Shadows off", "Project's"} <= buttons
    assert "Dimmer" not in buttons  # (its "Brighter" is the room light's, as before)
    assert not _texts_have(run["room_2d"]["texts"], "Not in HD-2D rooms")


def test_saved_and_reopened_as_set_with_the_2d_values_kept(run: dict) -> None:
    assert run["saved_clean"]
    reopened = run["reopened"]
    assert reopened["shadows"] is False and reopened["l4"] == 2.5 and reopened["off_active"]
    assert _texts_have(reopened["texts"], "Shadows are off in this room")
    saved = run["file"]
    assert {key: saved["settings"].get(key) for key in KEPT_2D} == KEPT_2D
    assert saved["settings"]["hd2d"]["shadows"] is False and saved["lights"][3]["intensity"] == 2.5
    assert saved["lights"][4]["flicker_enabled"] is True and saved["lights"][4]["flicker_preset"] == "torch"
