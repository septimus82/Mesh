"""M17-L3 C3 evidence: Studio's lighting panel (HD-2D and 2D rooms) as screenshots of its hidden window, and, on the
branch, real frames of a lamp's brightness and the room's shadows on/off.
py -3.13 frames.py <worktree> <out dir> <scratch dir> <tag>"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any

WT, OUT, SCRATCH, TAG = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
sys.path.insert(0, str(WT))
sys.path.insert(0, str(WT / "tooling"))
os.chdir(WT)
os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
OUT.mkdir(parents=True, exist_ok=True)

from hd2d_studio_demo import StudioDriver  # noqa: E402
from PIL import ImageStat  # noqa: E402

from engine import project_ops as ops  # noqa: E402
from engine.project_scaffold import create_project  # noqa: E402

SCENE = "packs/core_regions/scenes/start.json"
project = SCRATCH / f"frames-{TAG}"
create_project(project, "Frames", "hd2d_rpg")
path = project / SCENE
scene = json.loads(path.read_text(encoding="utf-8"))
scene = ops.set_hd2d_sun(scene, preset="night")
for x, y in ((400.0, 800.0), (880.0, 800.0), (960.0, 1000.0)):
    scene, _ = ops.add_light(scene, x, y, color="Warm", radius=200)
scene = ops.set_light(scene, 4, flicker="torch")
scene = ops.set_light(scene, 5, shadows=False, enabled=False)
scene["settings"].update({"lighting_enabled": False, "lighting_ambient_color": [30, 30, 40, 255],
                          "lighting_shadow_quality": "high"})
path.write_bytes(json.dumps(scene, indent=2).encode("utf-8"))
facts: dict[str, Any] = {}


def shot(d: Any, name: str) -> None:
    d.window.motion_time = 0.0
    d.window.water_time = 0.0
    d.frame().convert("RGB").save(OUT / f"{TAG}_{name}.png")


def view(d: Any, name: str) -> float:
    d.window.motion_time = 0.0
    d.window.water_time = 0.0
    image = d.frame().convert("RGB")
    left, right, bottom, top = d.studio._map_rect()
    crop = image.crop((int(left), int(image.height - top), int(right), int(image.height - bottom)))
    crop.save(OUT / f"{TAG}_view_{name}.png")
    value = float(ImageStat.Stat(crop.convert("L")).mean[0])
    facts[f"view_{name}"] = round(value, 3)
    return value


d = StudioDriver(project)
try:
    studio, k = d.studio, d.arcade.key
    d.button("Lighting")
    shot(d, "hd2d_panel_top")
    d.button("Light 2:", prefix=True)
    d._scroll_panels(lambda: any(t.startswith("Casts shadows") for t in d.texts()))
    shot(d, "hd2d_light2")
    if d.has_button("> More settings") or d._scroll_panels(lambda: d.has_button("> More settings")):
        d.button("> More settings")
        d._scroll_panels(lambda: not studio._panel_more[1])
        shot(d, "hd2d_light2_more")
    if TAG == "branch":
        d.button("Light 4:", prefix=True)
        view(d, "l4_brightness_1")
        for value in ("3", "0"):
            d.type_into("light_intensity", value)
            view(d, f"l4_brightness_{value}")
            d.key(k.Z, k.MOD_CTRL)
        d.button("On: On")
        view(d, "l4_off")
        d.key(k.Z, k.MOD_CTRL)
        d.button("Shadows off")
        view(d, "shadows_off")
        d._scroll_panels(lambda: any("Shadows are off" in t for t in d.texts()))
        shot(d, "hd2d_shadows_off_panel")
        d.key(k.Z, k.MOD_CTRL)
        view(d, "shadows_on")
    studio.new_room_form = {"kind": "2d", "width": 24, "depth": 16, "outdoor": True}
    studio.create_room("Cellar")
    d.advance()
    if not d.has_button("As project"):
        d.button("Lighting")
    d._scroll_panels(lambda: not studio._panel_more[0])
    shot(d, "2d_panel_top")
finally:
    d.close()
(OUT / f"{TAG}_facts.json").write_text(json.dumps(facts, indent=1), encoding="utf-8")
print(facts)
