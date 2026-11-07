"""M17-L3 scratch: lighting variants of the scratch copy's scenes (never the installed project).

Writes <scene>__l3_<preset>[_<control>].json beside each scene in the SCRATCH project:
  preset: noon / evening / night (project_ops.set_hd2d_sun, as Studio's buttons do)
  control: '' = lamps as authored (Lakeside's four lamps turned ON in the scratch copy: the L1b scene ships them off
           for daytime; the first two of them cast shadows, MAX_SHADOW_LIGHTS = 2)
           'noshadow' = every lamp "shadows": false (the per-lamp Studio toggle)
           'roomoff' = settings.hd2d.shadows false (no shadow maps at all: sun and lamps)
Usage: make_variants.py PROJECT
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Games\Mesh-l3")
from engine import project_ops as ops  # noqa: E402

assert ops.__file__.startswith(r"D:\Games\Mesh-l3"), ops.__file__
project = Path(sys.argv[1])
assert "scratchpad" in str(project), project
scenes = project / "packs" / "core_regions" / "scenes"
out = []
for base in ("lakeside", "start", "cottage"):
    src = scenes / f"{base}.json"
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    doc = json.loads(src.read_text(encoding="utf-8"))
    for light in doc.get("lights", []):
        if light.get("type") != "ambient":
            light["enabled"] = True
    for preset in ("noon", "evening", "night"):
        lit = ops.set_hd2d_sun(doc, preset=preset)
        for control in ("", "noshadow", "roomoff"):
            v = json.loads(json.dumps(lit))
            if control == "noshadow":
                for light in v.get("lights", []):
                    if light.get("type") != "ambient":
                        light["shadows"] = False
            elif control == "roomoff":
                v["settings"]["hd2d"]["shadows"] = False
            name = f"{base}__l3_{preset}{'_' + control if control else ''}.json"
            (scenes / name).write_bytes(json.dumps(v, indent=2).encode("utf-8"))
            out.append(name)
    assert hashlib.sha256(src.read_bytes()).hexdigest() == before
print(len(out), "variants")
