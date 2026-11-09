"""M17-L4A scratch: time-of-day variants of the SCRATCH copy of Lakeside Village (never the installed project).

Writes <scene>__l4_<variant>.json beside lakeside.json and cottage.json in the scratch project:
  morning / noon / evening / night: project_ops.set_hd2d_sun(preset), as Studio's sun buttons do; lamps as authored
                                    (the approved L1b scene ships its four lamps switched off)
  night_lamps: the night preset with the authored lamps switched on (a controlled variant: E1/E2 lamp glow, lamp colour)
The authored scene itself (unchanged) is the "authored" variant. The source files are hash-checked unchanged.
Usage: py -3.13 variants.py <scratch project>
"""
import hashlib
import json
import sys
from pathlib import Path

WT = Path(r"D:\Games\Mesh-l4a")
sys.path.insert(0, str(WT))
from engine import project_ops as ops  # noqa: E402

assert Path(ops.__file__).resolve().is_relative_to(WT), ops.__file__
project = Path(sys.argv[1])
assert "scratchpad" in str(project), project
scenes = project / "packs" / "core_regions" / "scenes"
written = []
for base in ("lakeside", "cottage"):
    src = scenes / f"{base}.json"
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    doc = json.loads(src.read_text(encoding="utf-8"))
    for preset in ("morning", "noon", "evening", "night"):
        lit = ops.set_hd2d_sun(doc, preset=preset)
        variants = {preset: lit}
        if preset == "night":
            lamps = json.loads(json.dumps(lit))
            for light in lamps.get("lights", []):
                if light.get("type") != "ambient" and light.get("x") is not None:
                    light["enabled"] = True
            variants["night_lamps"] = lamps
        for name, v in variants.items():
            out = scenes / f"{base}__l4_{name}.json"
            out.write_bytes(json.dumps(v, indent=2).encode("utf-8"))
            written.append(out.name)
    assert hashlib.sha256(src.read_bytes()).hexdigest() == before
print(len(written), "variants:", ", ".join(written))
