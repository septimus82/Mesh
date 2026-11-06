"""Scratch: the Studio flow (preview lines, editing view) with the samples' cap set to argv[1]. Usage: studiocap.py CAP OUT"""
import json
import os
import sys
import warnings
from pathlib import Path
sys.path.insert(0, r"D:\Games\Mesh-dof")
sys.path.insert(0, r"D:\Games\Mesh-dof\tooling")
import engine.hd2d.dof as dof  # noqa: E402
dof.TAPS_MAX = int(sys.argv[1])
out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
for name in ("APPDATA", "LOCALAPPDATA", "XDG_DATA_HOME", "MESH_USER_DIR", "MESH_PROJECTS_DIR"):
    os.environ[name] = str(out / "env" / name.lower()); Path(os.environ[name]).mkdir(parents=True, exist_ok=True)
os.environ["MESH_RUNTIME_SETTINGS_PATH"] = str(out / "user_settings.json")
os.environ["MESH_STUDIO_NO_AI_BRIDGE"] = "1"
import dof_studio  # noqa: E402
warnings.filterwarnings("ignore", message="draw_text is an extremely slow function")
r = dof_studio.studio(out, export=False)
(out / "studio.json").write_text(json.dumps(r, indent=1, default=str), encoding="utf-8")
print(json.dumps({k: r.get(k) for k in ("preview", "editing_view_unchanged_without_preview", "editing_view_drawn")}, default=str))
