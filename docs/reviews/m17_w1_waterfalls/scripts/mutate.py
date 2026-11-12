"""M17-W1 mutations: each breaks one behaviour; the test aimed at it must fail. Files restored byte for byte."""
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(r"D:\Games\Mesh-w1")
PY = [sys.executable, "-m", "pytest", "-q", "-o", "addopts=", "-p", "no:cacheprovider", "-x"]
FAST = "tests/test_river_falls.py"
GPU = "tests/test_river_falls_gpu.py"
RIVER, WATER, WORLD = "engine/hd2d/river.py", "engine/water.py", "engine/hd2d/world.py"
REND, OPS, STUDIO = "engine/hd2d/renderer.py", "engine/project_ops.py", "engine/studio_river.py"

MUTANTS = [
    ("jet curve linear", RIVER, "(pts[span][3] - pts[span + 1][3]) * f * f) / PX", "(pts[span][3] - pts[span + 1][3]) * f) / PX",
     FAST, "surface_leaves"),
    ("ribbon drawn over the fall", RIVER, "                continue  # (M17-W1: a fall is drawn as its curtain, fall_vertices)",
     "                pass", FAST, "curtain_down"),
    ("no sample at lip/foot", RIVER, "        targets = sorted([t for t in targets if all(abs(t - m) > 0.4 * step for m in marks_u)] + marks_u)",
     "        targets = sorted(targets + [m + 0.01 for m in marks_u])", FAST, "surface_leaves"),
    ("too gentle accepted", RIVER, "    if drop / PX < FALL_STEEP * run:", "    if False:", FAST, "refusals"),
    ("neighbouring falls accepted", RIVER, "        if out and start <= out[-1].start + 1:", "        if False:",
     FAST, "refusals"),
    ("room limit ignored", RIVER, "    if sum(len(r.falls) for r in rivers) > MAX_FALLS:", "    if False:", FAST, "eight"),
    ("falling never blocks", RIVER, "        return bool(self._falling) and any(", "        return False and any(",
     FAST, "blocks"),
    ("world ignores falling", WORLD, '                    kind = "block"  # (M17-W1', '                    pass  # (M17-W1',
     FAST, "blocks"),
    ("join checks above the fall", RIVER,
     "    start = max([u - BLEND_M - STEP_M] + [rib.u[foot] for _lip, foot in rib.falls if rib.u[foot] <= u + BLEND_M])",
     "    start = u - BLEND_M - STEP_M", FAST, "pond"),
    ("lip over the pond accepted", RIVER, "        if inside[lip] or any(_in_pond(pond, c) for c in (rib.left[lip], rib.right[lip])):",
     "        if False:", FAST, "pond"),
    ("carve cuts the cliff", RIVER, "            if dist > half:  # beside it is kept as it is (no bank cut into it)\n                continue",
     "            if dist > half:  # beside it is kept as it is (no bank cut into it)\n                target = level + BANK_SLOPE * (dist - half)",
     FAST, "carving"),
    ("sinking measures the fall", RIVER, "        if any(lip < k < foot for lip, foot in rib.falls):\n            continue  # (M17-W1",
     "        if False:\n            continue  # (M17-W1", FAST, "sinking"),
    ("renumbering unguarded", OPS, "        if (river.get(\"falls\") and \"falls\" not in given and isinstance(points, list)",
     "        if (False and river.get(\"falls\") and \"falls\" not in given and isinstance(points, list)", FAST, "eight"),
    ("streaks move up", WATER, "    float pulse = fract((v_fall.z - t) / (0.16 + 0.22 * h) + h2);",
     "    float pulse = fract((v_fall.z + t) / (0.16 + 0.22 * h) + h2);", GPU, "streaks_move"),
    ("curtain ignores depth", WATER, "                if falls:  # (after the water they fall into, over it)\n",
     "                if falls:  # (after the water they fall into, over it)\n                    ctx.disable(ctx.DEPTH_TEST)\n",
     GPU, "cliff_hides"),
    ("no foam in the pond", WATER, "    if (u_falls_n > 0 && material && sd_at(m) <= 0.0) {  // M17-W1",
     "    if (false && u_falls_n > 0 && material && sd_at(m) <= 0.0) {  // M17-W1", GPU, "foam_at"),
    ("foam without end", WATER, " * (1.0 - smoothstep(2.0 * reach, 3.0 * reach, a)) * dir.z;", " * dir.z;", GPU, "foam_at"),
    ("spray always made", REND, "        feet = [f for f in self.water.feet if f[7] > 0.0] if self.water is not None else []",
     "        feet = list(self.water.feet) if self.water is not None else []", GPU, "foam_at"),
    ("falls never freed", WATER, "        if not feet:\n            self._free_falls()\n            return",
     "        if not feet:\n            return", GPU, "two_draws"),
    ("pond easing above the fall", WATER,
     "        float from_u = kind.w > 0.5 ? max(info.y - MOUTH_BLEND, kind.z) : info.y - MOUTH_BLEND;  // (M17-W1)",
     "        float from_u = info.y - MOUTH_BLEND;  // (M17-W1)", GPU, "streaks_move"),
    ("studio insert not renumbered", STUDIO, '''        shifted = [{**f, "from": f["from"] + 1} if isinstance(f.get("from"), int) and f["from"] > i else f for f in falls]''',
     '''        shifted = falls''', GPU, "refuses_impossible"),
    ("water writes emission", WATER, "    f_emit = vec4(0.0, 0.0, 0.0, alpha);  // (water dims what glows behind it as it dims its colour)",
     "    f_emit = vec4(lit, alpha);  // (water dims what glows behind it as it dims its colour)", GPU, "no_emission"),
]


def run(name: str, path: str, old: str, new: str, tests: str, key: str) -> dict:
    target = REPO / path
    original = target.read_bytes()
    text = original.decode("utf-8").replace("\r\n", "\n")
    if text.count(old) != 1:
        return {"name": name, "error": f"anchor matched {text.count(old)} times"}
    mutated = text.replace(old, new)
    if b"\r\n" in original:
        mutated = mutated.replace("\n", "\r\n")
    target.write_bytes(mutated.encode("utf-8"))
    try:
        env = {**os.environ, "MESH_GL_SMOKE": "1"} if tests == GPU else dict(os.environ)
        done = subprocess.run([*PY, tests, "-k", key], cwd=REPO, capture_output=True, text=True, timeout=1500, env=env)
        tail = done.stdout.strip().splitlines()[-1] if done.stdout.strip() else done.stderr[-300:]
        return {"name": name, "file": path, "test": f"{tests} -k {key}", "caught": done.returncode != 0, "result": tail}
    finally:
        target.write_bytes(original)
        assert target.read_bytes() == original


if __name__ == "__main__":
    only = sys.argv[1:]
    results = [run(*m) for m in MUTANTS if not only or m[0] in only]
    for r in results:
        print(json.dumps(r))
    out = Path(__file__).parent / "mutations.json"
    out.write_text(json.dumps(results, indent=1), encoding="utf-8")
    print(f"caught {sum(r.get('caught', False) for r in results)}/{len(results)}")
