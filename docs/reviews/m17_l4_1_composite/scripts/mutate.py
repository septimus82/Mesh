"""Mutation checks for M17-L4-1 (run in D:\\Games\\Mesh-l4c with MESH_GL_SMOKE=1 and the scratch env):
each mutation applied alone, the composite tests run, the file restored byte for byte."""
import subprocess
import sys
from pathlib import Path

COMP = Path("engine/hd2d/composite.py")
REND = Path("engine/hd2d/renderer.py")
TESTS = ["tests/test_hd2d_composite.py", "tests/test_hd2d_composite_gpu.py"]
M = [
    (COMP, "identity reads the neighbouring texel", "    f_color = texelFetch(u_color, px, 0);",
     "    f_color = texelFetch(u_color, min(px + ivec2(1, 0), top), 0);"),
    (COMP, "identity looks up by gl_FragCoord (not viewport-safe)",
     "    ivec2 px = clamp(ivec2(floor(v_uv * vec2(top + 1))), ivec2(0), top);",
     "    ivec2 px = clamp(ivec2(gl_FragCoord.xy), ivec2(0), top);"),
    (COMP, "identity drops alpha", "    f_color = texelFetch(u_color, px, 0);",
     "    f_color = vec4(texelFetch(u_color, px, 0).rgb, 1.0);"),
    (COMP, "chain target not freed on a new size", "        self._free_chain()\n        ctx = self.ctx", "        ctx = self.ctx"),
    (COMP, "release keeps the chain target", "    def release(self) -> None:\n        self._free_chain()\n",
     "    def release(self) -> None:\n"),
    (REND, "renderer release forgets the composite", "        if self._composite is not None:\n            self._composite.release()\n            self._composite = None\n", ""),
    (REND, "composite made eagerly every frame (off too)",
     "        composite = self._final_composite() if solid is None and self.force_identity_composite else None",
     "        made = self._final_composite()\n        composite = made if solid is None and self.force_identity_composite else None"),
    (REND, "Studio's lines drawn into the world before the composite",
     "        lines_after = overlay is not None and solid is None and overlay_after(stage)",
     "        lines_after = overlay is not None and solid is None and stage == \"dof\""),
    (REND, "DoF drawn into the window, not the chain",
     "                chain.use()\n                self._composite_dof(dof, cam, None)", "                self._composite_dof(dof, cam, None)"),
    (REND, "read_final ignores the viewport",
     "            pixels = previous.read(viewport=tuple(int(v) for v in viewport) if viewport else (0, 0, *size), components=3)",
     "            pixels = previous.read(viewport=(0, 0, *size), components=3)"),
    (REND, "composite viewport not set", "                if viewport:\n                    ctx.viewport = viewport\n                composite.render",
     "                composite.render"),
]
saved = {f: f.read_bytes() for f in (COMP, REND)}
cmd = [sys.executable, "-m", "pytest", *TESTS, "-q", "-p", "no:cacheprovider", "-x",
       "--basetemp=" + sys.argv[1]]
r0 = subprocess.run(cmd, capture_output=True, text=True)
print("control (unmutated):", "PASS" if r0.returncode == 0 else "FAIL\n" + r0.stdout[-1500:], flush=True)
try:
    for f, name, a, b in M:
        text = saved[f].decode().replace("\r\n", "\n")
        assert text.count(a) == 1, (name, text.count(a))
        f.write_bytes(text.replace(a, b).encode())
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        failed = [ln for ln in r.stdout.splitlines() if ln.startswith(("FAILED", "ERROR"))][:2]
        print(f"{'CAUGHT' if r.returncode else 'MISSED':7} {name}  {failed}", flush=True)
        f.write_bytes(saved[f])
finally:
    for f, data in saved.items():
        f.write_bytes(data)
print("restored:", all(f.read_bytes() == d for f, d in saved.items()))
