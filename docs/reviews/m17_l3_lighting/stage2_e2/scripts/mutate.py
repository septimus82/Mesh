"""Mutation checks for E2: each change applied alone, the named test file run, the file restored byte-for-byte.
py -3.13 mutate.py fast|gpu  (run from the E2 worktree, through run.sh)"""
import os
import subprocess
import sys
from pathlib import Path

S = Path(r"C:\Users\slebb\AppData\Local\Temp\claude\c18a071c64bbe7a7\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\e2")
LIT, REN = Path("engine/hd2d/lighting.py"), Path("engine/hd2d/renderer.py")
FAST = [
    ("all the head node's parts glow (no unique-material rule)", LIT,
     "    shared = {p.material.name for p in parts if p.node != node}\n", "    shared: set = set()\n"),
    ("a tie is not refused", LIT, "    if not near or (len(near) > 1 and near[1][0] - near[0][0] <= 1e-6):\n",
     "    if not near:\n"),
    ("intensity 0 kept", REN, "                if lamp.intensity <= 0:\n", "                if lamp.intensity < 0:\n"),
    ("lamps past MAX_LIGHTS glow", REN, "            for lamp in self.settings.lights[:MAX_LIGHTS]:\n",
     "            for lamp in self.settings.lights:\n"),
]
GPU = [
    ("glow not multiplied by the head's texture", REN,
     "        e += mix(c.rgb / 12.92, pow((c.rgb + 0.055) / 1.055, vec3(2.4)), step(0.04045, c.rgb)) * u_glow;\n",
     "        e += u_glow;\n"),
    ("heads batched with their material (glow on the whole batch)", REN,
     '                key = (id(texture), st.cutaway, st.id if (st.id, part_index) in heads else "")\n',
     '                key = (id(texture), st.cutaway, "")\n'
     '                if (st.id, part_index) in heads:\n'
     '                    glows[key] = heads[(st.id, part_index)]\n'),
    ("every structure node within reach glows (any material)", LIT,
     "    shared = {p.material.name for p in parts if p.node != node}\n", "    shared: set = set()\n"),
]
kind = sys.argv[1]
cases, target = (FAST, "tests/test_hd2d_lamp_glow.py") if kind == "fast" else (GPU, "tests/test_hd2d_lamp_glow_gpu.py")
lines = []
for i, (label, path, old, new) in enumerate(cases):
    original = path.read_bytes()
    text = original.decode("utf-8")
    if "\r\n" in text:
        old, new = old.replace("\n", "\r\n"), new.replace("\n", "\r\n")
    assert text.count(old) == 1, label
    path.write_bytes(text.replace(old, new).encode("utf-8"))
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-W", "error",
                            f"--basetemp={S / f'm{kind[0]}{i}'}", target], capture_output=True, text=True, env=os.environ)
        tail = [ln for ln in r.stdout.splitlines() if ln.startswith(("FAILED", "ERROR")) or " passed" in ln or " failed" in ln]
        lines.append(f"{label}: exit {r.returncode}; " + " | ".join(tail[-6:]))
    finally:
        path.write_bytes(original)
    assert path.read_bytes() == original
print("\n".join(lines))
(S / f"mutations_{kind}.log").write_text("\n".join(lines) + "\n", encoding="utf-8")
