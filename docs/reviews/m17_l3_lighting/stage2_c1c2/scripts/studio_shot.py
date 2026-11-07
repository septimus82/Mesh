"""M17-L3 C2 evidence: Mesh Studio's lighting panel in an HD-2D room (hidden window): 3 lamps asking for shadows."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Games\Mesh-l3c")
sys.path.insert(0, r"D:\Games\Mesh-l3c\tooling")
os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
from engine import project_ops as ops  # noqa: E402

assert ops.__file__.startswith(r"D:\Games\Mesh-l3c"), ops.__file__
from hd2d_studio_demo import StudioDriver  # noqa: E402

from engine.project_scaffold import create_project  # noqa: E402

project = out / "Shadow maps"
assert not project.exists()
create_project(project, "Shadow maps", "hd2d_rpg")
path = project / "packs/core_regions/scenes/start.json"
scene = json.loads(path.read_text(encoding="utf-8"))
scene, _ = ops.add_light(scene, 400.0, 400.0, color="Warm", radius=160)
path.write_bytes(json.dumps(scene, indent=2).encode("utf-8"))
d = StudioDriver(project)
try:
    d.button("Lighting")
    d.picture(out / "studio_lighting_panel_list.png")
    d.button("Light 4:", prefix=True)
    d._scroll_panels(lambda: any("earlier in the list" in t for t in d.texts()))
    d.picture(out / "studio_lighting_light4_note.png")
    print([t for t in d.texts() if "Shadow maps" in t or "earlier in the list" in t or t.startswith("Light ")][:8])
finally:
    d.close()
