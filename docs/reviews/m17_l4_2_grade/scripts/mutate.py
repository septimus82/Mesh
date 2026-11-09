"""Mutation checks for M17-L4-2 (run in D:\\Games\\Mesh-l4g2, MESH_GL_SMOKE=1, scratch env): each alone, the post tests
run, the file restored byte for byte."""
import subprocess
import sys
from pathlib import Path

POST = Path("engine/hd2d/post.py")
COMP = Path("engine/hd2d/composite.py")
REND = Path("engine/hd2d/renderer.py")
STUD = Path("engine/studio_hd2d.py")
OPS = Path("engine/project_ops.py")
TESTS = ["tests/test_hd2d_post.py", "tests/test_hd2d_post_authoring.py", "tests/test_hd2d_post_gpu.py"]
M = [
    (POST, "strength 0 still grades", "        return self.strength > 0.0", "        return self.strength >= 0.0"),
    (POST, "strength doesn't scale the vignette", '"u_vignette": self.vignette_amount * s}', '"u_vignette": self.vignette_amount}'),
    (POST, "stored keeps default strength", "    if post.strength != STRENGTH[0]:", "    if True:"),
    (POST, "unknown keys accepted", '    if unknown:\n        raise PostError', '    if False:\n        raise PostError'),
    (COMP, "graded in sRGB values (no decode)", "    vec3 o = lin(c.rgb);", "    vec3 o = c.rgb;"),
    (COMP, "alpha forced opaque", "    f_color = vec4(enc(g), c.a);", "    f_color = vec4(enc(g), 1.0);"),
    (COMP, "no highlight protection", "    g = mix(g, o, keep);", "    g = g;"),
    (COMP, "no new-clip limit", "    g = mix(g, max(soft, o), vec3(greaterThan(g, max(o, vec3(0.9)))));", ""),
    (COMP, "vignette by the window (gl_FragCoord)", "    vec2 q = (vec2(px) + 0.5) / vec2(size) - 0.5;",
     "    vec2 q = gl_FragCoord.xy / vec2(size) - 0.5;"),
    (COMP, "uniforms set every frame (no cache)", "        if post is self._configured:\n            return\n", ""),
    (REND, "grade never configured (identity drawn)", "            composite.configure(post if grading else None)", "            composite.configure(None)"),
    (STUD, "Studio edit doesn't reach the view", "            renderer.settings = dataclasses.replace(renderer.settings, post=post, post_error=None)\n", ""),
    (OPS, "choosing a preset keeps the old vignette", '''        raw = {"preset": preset}
    elif now is None:''', '''        raw = {**(stored(now) or {}), "preset": preset}
    elif now is None:'''),
    (OPS, "off leaves the block", '        hd2d.pop("post", None)\n        return _checked(scene, out)', '        return _checked(scene, out)'),
]
saved = {f: f.read_bytes() for f in {m[0] for m in M}}
cmd = [sys.executable, "-m", "pytest", *TESTS, "-q", "-p", "no:cacheprovider", "-x", "--basetemp=" + sys.argv[1]]
r0 = subprocess.run(cmd, capture_output=True, text=True)
print("control (unmutated):", "PASS" if r0.returncode == 0 else "FAIL\n" + r0.stdout[-1500:], flush=True)
try:
    for f, name, a, b in M:
        text = saved[f].decode().replace("\r\n", "\n")
        assert text.count(a) == 1, (name, text.count(a))
        f.write_bytes(text.replace(a, b).encode())
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        failed = [ln for ln in r.stdout.splitlines() if ln.startswith(("FAILED", "ERROR"))][:1]
        print(f"{'CAUGHT' if r.returncode else 'MISSED':7} {name}  {failed}", flush=True)
        f.write_bytes(saved[f])
finally:
    for f, data in saved.items():
        f.write_bytes(data)
print("restored:", all(f.read_bytes() == d for f, d in saved.items()))
