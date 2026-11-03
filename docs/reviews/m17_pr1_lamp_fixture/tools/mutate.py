"""Failure injection for the lamp-fixture fix: each mutation, applied alone, must make the new tests fail."""
import os
import subprocess
from pathlib import Path

PY = r"D:\Games\Mesh\.venv\Scripts\python.exe"
SP = Path(__file__).resolve().parent
ENV = {**os.environ, "APPDATA": str(SP / "appdata"), "XDG_DATA_HOME": str(SP / "xdg"), "MESH_USER_DIR": str(SP / "user"),
       "MESH_PROJECTS_DIR": str(SP / "uprojects"), "MESH_GL_SMOKE": "1", "MESH_REQUIRE_GL": "1"}
TESTS = ["tests/test_hd2d_lamp_fixture_gpu.py", "tests/test_hd2d_lamp_fixtures.py"]
L, R, D = "engine/hd2d/lighting.py", "engine/hd2d/renderer.py", "tooling/hd2d_lighting_demo.py"
M = [
    ("1 self-shadowing back (lamp pass ignores fixtures)", L, "                skip = self.fixtures[i]\n",
     "                skip = frozenset()\n"),
    ("2 self-shadowing back (fixture rule finds nothing)", L, "            out.add(st.id)\n", "            pass\n"),
    ("3 near walls lost (blanket 0.35 m clearance)", L,
     "void main() { gl_FragDepth = clamp(length(v_world - u_lamp.xyz) / u_lamp.w, 0.0, 1.0); }",
     "void main() { if (length(v_world - u_lamp.xyz) < 0.35) discard; "
     "gl_FragDepth = clamp(length(v_world - u_lamp.xyz) / u_lamp.w, 0.0, 1.0); }"),
    ("4 CPU reference ignores the fixture (agreement)", D,
     "        seen.add(not tris.blocked(o, (d[0] / n, d[1] / n, d[2] / n), n - 0.05, skip))",
     "        seen.add(not tris.blocked(o, (d[0] / n, d[1] / n, d[2] / n), n - 0.05))"),
    ("5 lamp maps redrawn every frame", L, "            self._lamp_maps_ready = True\n", "            pass\n"),
    ("6 spans recorded at vertex, not index, offsets", R,
     "                    batch_spans.append((st.id, len(idx), len(part.indices)))",
     "                    batch_spans.append((st.id, len(verts) // 8, len(part.indices)))"),
    ("7 kept ranges keep the fixture", L, "        if sid in skip:\n            continue\n", "        if False:\n            continue\n"),
]
for name, f, a, b in M:
    p = Path(f)
    orig = p.read_bytes()
    t = orig.decode("utf-8")
    nl = "\r\n" if "\r\n" in t else "\n"
    a2, b2 = a.replace("\n", nl), b.replace("\n", nl)
    if t.count(a2) != 1:
        print("NOT FOUND", name, t.count(a2))
        continue
    p.write_bytes(t.replace(a2, b2).encode("utf-8"))
    try:
        r = subprocess.run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=", "-W", "error", *TESTS],
                           capture_output=True, text=True, env=ENV, timeout=900)
        failed = sorted({line.split("::")[1].split(" ")[0] for line in r.stdout.splitlines() if line.startswith("FAILED")})
        print(("KILLED   " if r.returncode else "SURVIVED ") + name, "::", r.stdout.strip().splitlines()[-1], failed)
    finally:
        p.write_bytes(orig)
