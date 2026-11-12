"""Semantic mutations of the L4-3 haze: each applied alone, the named tests run, every one must FAIL (caught)."""
import json
import os
import subprocess
import sys
from pathlib import Path

WT = Path(r"D:\Games\Mesh-l4h")
BT = r"C:\Users\slebb\AppData\Local\Temp\claude\c18a071c64bbe7a7\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\l4h\bt_mut"
GPU = "tests/test_hd2d_haze_gpu.py"
FAST = "tests/test_hd2d_haze.py"
MUTATIONS = [
    ("depth_to_screen_height", "engine/hd2d/composite.py", "view_depth(texelFetch(u_depth, px, 0).r)",
     "(u_haze_onset + v_uv.y * 20.0)", [GPU, "-k", "depth_calls or walking or flat"]),
    ("mix_in_srgb", "engine/hd2d/composite.py", "if (a > 0.0) o = mix(o, u_haze_color, a);",
     "if (a > 0.0) o = lin(mix(c.rgb, enc(u_haze_color), a));", [GPU, "-k", "texels or depth_calls"]),
    ("grade_then_haze", "engine/hd2d/composite.py", "    f_color = vec4(enc(g), c.a);\r\n}",
     "    f_color = vec4(enc(mix(g, u_haze_color, a)), c.a);\r\n}", [GPU, "-k", "before_the_grade"]),
    ("haze_unlit", "engine/hd2d/renderer.py",
     "        light = light_of(s.ambient, s.ambient_color, self.lighting.sun, s.sun_intensity, s.sun_color)",
     "        light = (1.0, 1.0, 1.0)", [GPU, "-k", "depth_calls or night"]),
    ("no_character_rule", "engine/hd2d/renderer.py", "begin = haze_onset(focus, v.start, band if followed else None)",
     "begin = haze_onset(focus, v.start, None)", [GPU, "-k", "start_of_zero"]),
    ("uniforms_every_frame", "engine/hd2d/composite.py",
     "        if post is self._configured[0] and haze == self._configured[1]:", "        if False:",
     [GPU, "-k", "depth_calls"]),
    ("onset_set_once", "engine/hd2d/composite.py", "        if key != self._frame:", "        if self._frame is None:",
     [GPU, "-k", "walking"]),
    ("studio_view_not_updated", "engine/studio_hd2d.py",
     "            renderer.settings = dataclasses.replace(renderer.settings, haze=haze, haze_error=None)",
     "            pass", [GPU, "-k", "studio_hazes"]),
    ("haze_not_read", "engine/hd2d/settings.py", "        haze = parse_haze(raw.get(\"haze\"))", "        haze = None",
     [FAST, GPU, "-k", "settings or plays"]),
    ("no_corner_lost", "engine/hd2d/composite.py", "a = u_haze * (1.0 - exp(-3.0 * x * x));",
     "a = u_haze * min(1.0, x);", [GPU, "-k", "depth_calls or texels"]),
]


def main() -> None:
    results = {}
    for name, rel, old, new, args in MUTATIONS:
        path = WT / rel
        original = path.read_bytes()
        text = original.decode("utf-8")
        assert text.count(old) == 1, (name, text.count(old))
        path.write_bytes(text.replace(old, new).encode("utf-8"))
        try:
            ran = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--basetemp={BT}",
                                  *args], cwd=WT, capture_output=True, text=True, timeout=1800,
                                 env={**os.environ, "MESH_GL_SMOKE": "1"})
        finally:
            path.write_bytes(original)
        tail = (ran.stdout.strip().splitlines() or [""])[-1]
        results[name] = {"caught": ran.returncode != 0, "summary": tail}
        print(name, results[name], flush=True)
    Path(BT + ".json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("caught", sum(r["caught"] for r in results.values()), "of", len(results))


if __name__ == "__main__":
    main()
