"""Plant each leak alone, run the prototype test, restore byte for byte."""
import subprocess
import sys
from pathlib import Path

T = "tests/test_room_transition_gl_lifetime_gpu.py"
KEPT = "\n_KEPT: list = []\n"
M = [
    (Path("engine/hd2d/runtime.py"), "HD-2D renderer never released and still referenced after a room change",
     "        renderer.release()\n", "        _KEPT.append(renderer)\n", KEPT),
    (Path("engine/particles.py"), "each frame's dropped particle SpriteList buffers kept (unbounded cache)",
     "        self._sprites = active\n        self.particles.clear()\n",
     "        self._sprites = active\n        _KEPT.append(self.particles._data)\n        self.particles.clear()\n", KEPT),
    (Path(T), "frames never end (no ctx.gc(): #484's original probe)",
     "                ctx.gc()  # (what Window.flip() does each frame)\n", "                pass\n", ""),
]
saved = {f: f.read_bytes() for f, *_ in M}
try:
    for f, name, a, b, extra in M:
        t = saved[f].decode().replace("\r\n", "\n")
        assert t.count(a) == 1, (name, t.count(a))
        f.write_bytes((t.replace(a, b) + extra).encode())
        r = subprocess.run([sys.executable, "-m", "pytest", T, "-q", "-p", "no:cacheprovider", "-o", "addopts=",
                            "--basetemp=" + sys.argv[1]], capture_output=True, text=True, timeout=900)
        why = [ln for ln in r.stdout.splitlines() if ln.startswith("E ")][:1]
        print(f"{'CAUGHT' if r.returncode else 'MISSED':7} {name} | {why[0][:260] if why else r.stdout.strip().splitlines()[-1]}",
              flush=True)
        f.write_bytes(saved[f])
finally:
    for f, d in saved.items():
        f.write_bytes(d)
print("restored:", all(f.read_bytes() == d for f, d in saved.items()))
