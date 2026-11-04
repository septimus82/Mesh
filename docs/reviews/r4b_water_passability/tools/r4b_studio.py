"""R4B evidence (scratch only): Studio's Walking into it choices, River panel and water inspector (hidden window)."""
import os
import shutil
import sys
from pathlib import Path

HERE = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\c18a071c64bbe7a7\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\river4")
sys.path.insert(0, str(HERE))
from scratch_guard import inside_scratch  # noqa: E402

ROOT = inside_scratch(HERE / "r4b" / "studio")
if ROOT.exists():
    shutil.rmtree(ROOT)
ROOT.mkdir(parents=True)
sys.path[:0] = [r"D:\Games\Mesh-rivers", r"D:\Games\Mesh-rivers\tooling"]
os.environ.update({"MESH_USER_DIR": str(ROOT / "user"), "MESH_PROJECTS_DIR": str(ROOT / "userprojects"),
                   "APPDATA": str(ROOT / "appdata"), "XDG_DATA_HOME": str(ROOT / "xdg"), "MESH_STUDIO_NO_AI_BRIDGE": "1"})
import r4_river_mouth_study as study  # noqa: E402
from hd2d_studio_demo import StudioDriver  # noqa: E402

project = study.make_project(ROOT, "studio", carved=True)
pond = study.pond_id(project)
d = StudioDriver(project)
try:
    d.button("Terrain")
    d.button("River")
    d.button("Select 'brook'")
    d.button("Wade")
    d.type_into("river_wade_depth", "1.2")
    d.advance(3)
    d.picture(ROOT / "studio_river_panel_walking_into_it_wade.png")
    d.button("River")
    d.studio.select(pond)
    d.advance(2)
    d.button("Block")
    d.advance(3)
    d.picture(ROOT / "studio_water_inspector_walking_into_it_block.png")
finally:
    d.close()
print("ok")
