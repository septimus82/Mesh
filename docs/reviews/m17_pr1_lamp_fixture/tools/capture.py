"""M17 audit: real in-engine captures through tooling/scene_snapshot.py (hidden window, one process per shot)."""
import json
import os
import subprocess
import sys
from pathlib import Path

M17 = Path(__file__).resolve().parents[1]
REPO = Path(os.environ.get("M17_REPO", r"D:\Games\Mesh"))  # the engine checkout that renders
PY = str(Path(r"D:\Games\Mesh") / ".venv" / "Scripts" / "python.exe")
ENV = {**os.environ, "MESH_USER_DIR": str(M17 / "user"), "MESH_PROJECTS_DIR": str(M17 / "userprojects"),
       "APPDATA": str(M17 / "appdata"), "XDG_DATA_HOME": str(M17 / "xdg")}


def shot(name: str, project: str, scene: str, *extra: str) -> None:
    out = M17 / "shots" / f"{name}.png"
    if extra and extra[0] in ("grade", "tilt"):  # the scratch post-effect prototype (tools/proto_post.py)
        cmd = [PY, str(M17 / "tools" / "proto_post.py"), str(M17 / "projects" / project), scene, str(out), *extra]
    else:
        cmd = [PY, str(REPO / "tooling" / "scene_snapshot.py"), str(M17 / "projects" / project), scene, str(out),
               "--size", "1280", "720", *extra]
    proc = subprocess.run(cmd, cwd=REPO, env=ENV, capture_output=True, text=True, timeout=300)
    (M17 / "shots" / f"{name}.json").write_text(proc.stdout + proc.stderr[-3000:], encoding="utf-8")
    print(name, "rc", proc.returncode, "png", out.exists(), "" if out.exists() else proc.stderr[-600:])


if __name__ == "__main__":
    for spec in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")):
        shot(*spec)
