"""M17-L3 C3 audit: every control Studio's lighting panel shows, clicked (or typed into) in Studio's hidden window,
and what changed: the scene (which keys), and what the HD-2D renderer draws from (its settings, lamps, shadow slots).
Run from a worktree (base or branch): py -3.13 audit.py <worktree> <out.json> <scratch dir>."""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

WT, OUT, SCRATCH = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(WT))
sys.path.insert(0, str(WT / "tooling"))
os.chdir(WT)
os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"

from hd2d_studio_demo import StudioDriver  # noqa: E402

from engine import project_ops as ops  # noqa: E402
from engine.project_scaffold import create_project  # noqa: E402
from engine.studio_ui import IconButton  # noqa: E402

SCENE = "packs/core_regions/scenes/start.json"
KEPT_2D = {"lighting_enabled": False, "lighting_ambient_color": [30, 30, 40, 255], "lighting_shadow_quality": "high"}


def drawn(d: Any) -> Any:
    r = d.studio.hd2d.renderer
    if r is None:
        return None
    s, lighting = r.settings, r.lighting
    return repr((s.shadows, s.shadow_softness, s.shadow_strength, s.lights, s.ambient_color, lighting.enabled,
                 lighting.pcf, tuple(lighting.lamp_slots)))


def allocation(scene: dict[str, Any]) -> Any:
    from engine.hd2d import settings as S

    f = getattr(S, "scene_shadow_allocation", None)
    return f(scene) if f else S.shadow_allocation(scene.get("lights"))


def changed_keys(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    out = []
    sa, sb = a.get("settings", {}), b.get("settings", {})
    for key in sorted(set(sa) | set(sb)):
        if key == "hd2d":
            ha, hb = sa.get(key) or {}, sb.get(key) or {}
            out += [f"settings.hd2d.{k}" for k in sorted(set(ha) | set(hb)) if ha.get(k) != hb.get(k)]
        elif sa.get(key) != sb.get(key):
            out.append(f"settings.{key}")
    la, lb = a.get("lights") or [], b.get("lights") or []
    if len(la) != len(lb):
        out.append(f"lights: {len(la)} -> {len(lb)}")
    else:
        for i, (x, y) in enumerate(zip(la, lb)):
            out += [f"lights[{i}].{k}" for k in sorted(set(x) | set(y)) if x.get(k) != y.get(k)]
    return out


def panel_widgets(d: Any) -> list[Any]:
    right = d.window.width - d.studio._panel_widths()[1]
    return [w for w in d.studio.ui.walk_widgets() if w.rect.left >= right - 1]


def survey(d: Any) -> tuple[list[str], list[str], list[str]]:
    buttons: list[str] = []
    labels: list[str] = []
    boxes: list[str] = []

    def look() -> bool:
        shown = panel_widgets(d)
        for w in shown:
            text = getattr(w, "mesh_text", None) or getattr(w, "text", None)
            if not isinstance(text, str) or not text:
                continue
            if isinstance(w, IconButton):
                if text not in buttons:
                    buttons.append(text)
            elif text not in labels:
                labels.append(text)
        boxes.extend(k for k, f in d.studio._focusable.items()
                     if getattr(f, "parent", None) is not None and f in shown and k not in boxes)
        return False

    d._scroll_both(look)
    return buttons, labels, boxes


def button_widget(d: Any, text: str) -> Any:
    return next((w for w in d.studio.ui.walk_widgets() if isinstance(w, IconButton) and w.text == text), None)


EXPANDERS = ("More settings", "Fine-tune shadows")
NAV = ("Done", "+ Add light")


def setup_state(d: Any, index: int, expander: str) -> None:
    studio = d.studio
    if index >= 0 and studio.light != index:
        d.button(f"Light {index + 1}:", prefix=True)
    want = {"More settings": "light_more", "Fine-tune shadows": "shadow_fine"}[expander]
    if studio.expanded != want:
        try:
            d.button(f"> {expander}")  # (scrolled to, as a person would)
        except AssertionError:
            pass  # (this panel has none)


def sweep(d: Any, index: int) -> dict[str, Any]:
    from engine.studio import S_ACTIVE

    studio, k = d.studio, d.arcade.key
    out: dict[str, Any] = {}
    for expander in EXPANDERS:
        setup_state(d, index, expander)
        buttons, labels, boxes = survey(d)
        out.setdefault("_surveys", {})[expander] = {"buttons": buttons, "labels": labels, "boxes": boxes}
        for text in buttons:
            if text in NAV or text.startswith("Light ") or text.lstrip("v> ").strip() in EXPANDERS or text in out:
                continue
            setup_state(d, index, expander)
            if button_widget(d, text) is None and not d._scroll_panels(lambda: button_widget(d, text) is not None):
                continue
            scene, was, alloc = copy.deepcopy(studio.project.scene()), drawn(d), allocation(studio.project.scene())
            d.button(text)
            now = studio.project.scene()
            if now == scene:
                w = button_widget(d, text)
                out[text] = {"edit": False, "active_choice": bool(w is not None and (w.style == S_ACTIVE or w.disabled)),
                             "said": studio.message}
                continue
            rec = {"edit": True, "keys": changed_keys(scene, now), "drawn_changed": drawn(d) != was,
                   "allocation_changed": allocation(now) != alloc, "said": studio.message}
            d.key(k.Z, k.MOD_CTRL)
            rec["undone"] = studio.project.scene() == scene and drawn(d) == was
            out[text] = rec
        light = studio.project.scene()["lights"][index] if index >= 0 else {}
        values = {"light_x": f"{light.get('x', 0) + 32:g}", "light_y": f"{light.get('y', 0) + 32:g}",
                  "light_radius": "300", "light_height": "3", "light_intensity": "3", "light_rgb": "200, 120, 40",
                  "shadow_strength_room": "0.5", "shadow_edge": "12", "light_flicker_speed": "9",
                  "light_flicker_brightness": "0.5", "light_flicker_reach": "0.3", "light_flicker_irregularity": "0.7"}
        for key in boxes:
            if f"box:{key}" in out:
                continue
            if key not in values:
                out[f"box:{key}"] = {"untested": True}
                continue
            setup_state(d, index, expander)
            scene, was, alloc = copy.deepcopy(studio.project.scene()), drawn(d), allocation(studio.project.scene())
            try:
                d.type_into(key, values[key])
            except AssertionError:
                continue
            now = studio.project.scene()
            rec = {"edit": now != scene, "keys": changed_keys(scene, now), "drawn_changed": drawn(d) != was,
                   "allocation_changed": allocation(now) != alloc, "said": studio.message}
            if now != scene:
                d.key(k.Z, k.MOD_CTRL)
                rec["undone"] = studio.project.scene() == scene and drawn(d) == was
            out[f"box:{key}"] = rec
    return out


def build(kind: str) -> Path:
    project = SCRATCH / f"{kind}-{WT.name}"
    if project.exists():
        raise SystemExit(f"{project} exists")
    create_project(project, "Audit", "hd2d_rpg")
    path = project / SCENE
    scene = json.loads(path.read_text(encoding="utf-8"))
    scene = ops.set_hd2d_sun(scene, preset="night")
    for x, y in ((400.0, 800.0), (880.0, 800.0), (960.0, 1000.0)):
        scene, _ = ops.add_light(scene, x, y, color="Warm", radius=200)
    scene = ops.set_light(scene, 4, flicker="torch")
    scene = ops.set_light(scene, 5, shadows=False, enabled=False)
    scene["settings"].update(copy.deepcopy(KEPT_2D))
    path.write_bytes(json.dumps(scene, indent=2).encode("utf-8"))
    return project


result: dict[str, Any] = {"worktree": str(WT)}
d = StudioDriver(build("hd2d"))
try:
    d.button("Lighting")
    result["hd2d_panel"] = survey(d)
    result["hd2d_light2"] = sweep(d, 1)   # a lamp with a shadow map
    result["hd2d_light4"] = sweep(d, 3)   # past the two maps
    result["hd2d_light5"] = sweep(d, 4)   # past the two maps, a torch flicker
    result["hd2d_room_light"] = sweep(d, 0)  # the room light's colour
    # a 2D room in the same project
    studio = d.studio
    studio.new_room_form = {"kind": "2d", "width": 24, "depth": 16, "outdoor": True}
    studio.create_room("Cellar")
    d.advance()
    if not d.has_button("As project"):
        d.button("Lighting")
    scene = studio.project.scene()
    for x in (200.0, 400.0):
        studio._edit(lambda s, x=x: ops.add_light(s, x, 200.0)[0], "")
    studio._edit(lambda s: ops.set_light(s, 1, flicker="torch"), "")
    studio.expanded, studio.light = None, None  # (as the 2D room opens: nothing carried from the HD-2D sweep)
    studio._rebuild()
    d.advance()
    result["2d_panel"] = survey(d)
    result["2d_light2"] = sweep(d, 1)
finally:
    d.close()
OUT.write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
print("wrote", OUT)
