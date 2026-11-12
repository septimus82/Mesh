"""M17-L4-4 mutations: each realistic defect applied alone to the worktree; the named tests must FAIL. Files are
restored byte for byte after each (checked at the end). Usage: py -3.13 mutate.py [names...]"""
import json
import os
import subprocess
import sys
from pathlib import Path

WT = Path(r"D:\Games\Mesh-l4h")
HERE = Path(__file__).resolve().parent
BT = str(HERE / "bt_mut")
GPU = "tests/test_hd2d_bloom_gpu.py"
FAST = "tests/test_hd2d_bloom.py"
NOT_STUDIO = "not studio"
MUTATIONS = [
    # name, file, old, new, (test file, -k)
    ("threshold_ignored", "engine/hd2d/bloom.py",
     "    return e * (max(soft, y - u_threshold) / max(y, 1e-5));",
     "    return e * max(1.0, max(soft, y - u_threshold) / max(y, 1e-5));", (GPU, NOT_STUDIO)),
    ("ground_emits_its_colour", "engine/hd2d/renderer.py",
     "    f_color = vec4(c.rgb * light_at(v_world, normalize(v_nrm), false), 1.0);\n    f_emit = vec4(0.0, 0.0, 0.0, 1.0);",
     "    f_color = vec4(c.rgb * light_at(v_world, normalize(v_nrm), false), 1.0);\n    f_emit = vec4(f_color.rgb, 1.0);",
     (GPU, NOT_STUDIO)),
    ("characters_drawn_without_emission", "engine/hd2d/renderer.py",
     ["        lighting.bind(sp)\n        self.shadow_prog[\"u_vp\"] = vp\n",
      "        self._draw_water(vp, cam, world, weather, maps, solid)\n"],
     ["        lighting.bind(sp)\n        self.shadow_prog[\"u_vp\"] = vp\n"
      "        if bloom is not None:  # MUTATION: characters drawn with only the colour attachment\n"
      "            from pyglet import gl as _g\n"
      "            _g.glDrawBuffers(1, (_g.GLenum * 1)(_g.GL_COLOR_ATTACHMENT0))\n",
      "        if bloom is not None:\n            world.use(force=True)\n"
      "        self._draw_water(vp, cam, world, weather, maps, solid)\n"],
     (GPU, "behind")),
    ("emission_not_cleared", "engine/hd2d/renderer.py",
     "        if bloom is not None:\n            bloom[0].clear_emission()\n", "", (GPU, NOT_STUDIO)),
    ("glow_after_the_grade", "engine/hd2d/composite.py",
     ["    if (u_grade == 0) { f_color = vec4(enc(o), c.a); return; }\n", "    f_color = vec4(enc(g), c.a);\n}"],
     ["    if (u_grade == 0) { f_color = vec4(enc(o), c.a); return; }\n    o -= b;\n",
      "    f_color = vec4(enc(g + b), c.a);\n}"],
     (GPU, "texels")),
    ("glow_in_srgb", "engine/hd2d/composite.py",
     "    o += b;                                               // the bloom, after the haze\n",
     "    o = lin(enc(o) + b);\n", (GPU, "texels")),
    ("haze_doesnt_dim_it", "engine/hd2d/bloom.py",
     "    if (u_haze > 0.0) {\n        float d = texelFetch(u_depth, t, 0).r;",
     "    if (u_haze > 9.0) {\n        float d = texelFetch(u_depth, t, 0).r;", (GPU, "haze")),
    ("one_tap_prefilter", "engine/hd2d/bloom.py",
     "    f_color = vec4(sum / (u_scale.x * u_scale.y), 1.0);",
     "    f_color = vec4(passed(clamp(ivec2(lo + 0.5 * u_scale), ivec2(0), size - 1)), 1.0);", (GPU, NOT_STUDIO)),
    ("spread_inverted", "engine/hd2d/bloom.py",
     "    f_color = vec4(mix(texture(u_here, v_uv).rgb, s / 16.0, u_spread), 1.0);",
     "    f_color = vec4(mix(texture(u_here, v_uv).rgb, s / 16.0, 1.0 - u_spread), 1.0);", (GPU, "spread")),
    ("no_cap", "engine/hd2d/bloom.py",
     "    if (y > u_max) { e *= u_max / y; y = u_max; }\n",
     "    if (y > u_max * 1.0e6) { e *= u_max / y; y = u_max; }\n", (GPU, "capped")),
    ("kept_when_off", "engine/hd2d/renderer.py",
     "        if bloom is None or not bloom.active:\n            self._free_bloom()\n            return None\n",
     "        if bloom is None or not bloom.active:\n            return None\n", (GPU, NOT_STUDIO)),
    ("strength_zero_still_runs", "engine/hd2d/bloom.py",
     "        return self.values.strength > 0.0\n", "        return True\n", (GPU, "zero")),
    ("studio_view_not_updated", "engine/studio_hd2d.py",
     "            renderer.settings = dataclasses.replace(renderer.settings, bloom=bloom, bloom_error=None)\n",
     "", (GPU, "studio")),
    ("knee_hard_edge", "engine/hd2d/bloom.py",
     "    soft = min(max(luminance - threshold + knee, 0.0), 2.0 * knee)\n",
     "    soft = 0.0\n", (FAST, "knee")),
]


def main() -> None:
    names = sys.argv[1:] or [m[0] for m in MUTATIONS]
    originals = {f: (WT / f).read_bytes() for f in {m[1] for m in MUTATIONS}}
    results = {}
    out = HERE / "mutations.json"
    if out.exists():
        results = json.loads(out.read_text(encoding="utf-8"))
    for name, path, old, new, (tests, k) in MUTATIONS:
        if name not in names:
            continue
        p = WT / path
        raw = originals[path].decode("utf-8")
        nl = "\r\n" if "\r\n" in raw else "\n"
        mutated = raw
        for one_old, one_new in zip(*((old, new) if isinstance(old, list) else ([old], [new]))):
            o, n = one_old.replace("\n", nl), one_new.replace("\n", nl)
            assert mutated.count(o) == 1, (name, mutated.count(o))
            mutated = mutated.replace(o, n)
        p.write_bytes(mutated.encode("utf-8"))
        try:
            ran = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "addopts=",
                                  f"--basetemp={BT}", tests, "-k", k, "-x"], cwd=WT, capture_output=True, text=True,
                                 timeout=3000, env={**os.environ, "MESH_GL_SMOKE": "1"})
        finally:
            p.write_bytes(originals[path])
        failed = [ln for ln in ran.stdout.splitlines() if ln.startswith(("FAILED ", "ERROR tests"))]
        results[name] = {"caught": ran.returncode != 0, "tests": f"{tests} -k {k!r}",
                         "summary": (ran.stdout.strip().splitlines() or [""])[-1], "failed": failed[:3]}
        print(name, json.dumps(results[name]), flush=True)
        out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    for f, b in originals.items():
        assert (WT / f).read_bytes() == b, f
    print("caught", sum(r["caught"] for r in results.values()), "of", len(results))


if __name__ == "__main__":
    main()
