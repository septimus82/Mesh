"""Scratch look at the R4 study village's mouth (hidden Studio window): joined vs not joined, same camera."""
import os
import shutil
import sys
from pathlib import Path

HERE = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\c18a071c64bbe7a7\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\river4")
sys.path.insert(0, str(HERE))
from scratch_guard import inside_scratch  # noqa: E402

ROOT = inside_scratch(HERE / "village")
if ROOT.exists():
    shutil.rmtree(ROOT)
ROOT.mkdir(parents=True)
sys.path[:0] = [r"D:\Games\Mesh-rivers", r"D:\Games\Mesh-rivers\tooling"]
os.environ.update({"MESH_USER_DIR": str(ROOT / "user"), "MESH_PROJECTS_DIR": str(ROOT / "userprojects"),
                   "APPDATA": str(ROOT / "appdata"), "XDG_DATA_HOME": str(ROOT / "xdg"), "MESH_STUDIO_NO_AI_BRIDGE": "1"})
import r4_river_mouth_study as st  # noqa: E402
from hd2d_studio_demo import StudioDriver  # noqa: E402

for name, mouth in (("joined", True), ("free", False)):
    d = StudioDriver(st.make_project(ROOT, name, mouth=mouth, carved=True))
    try:
        v = d.studio.hd2d
        for cam, (target, dist, pitch) in {"top": ((19.0, 36.0, 0.0), 10.0, 89.0),
                                           "angled": ((19.0, 36.5, 0.0), 12.0, 40.0)}.items():
            v.camera.target, v.camera.distance, v.camera.pitch = target, dist, pitch
            d.advance(3)
            d.picture(ROOT / f"{name}_{cam}.png")
    finally:
        d.close()
print("ok")
