"""Scratch control: the shipped scene with its point lights removed (ops.remove_light; the ambient light kept), to
isolate what the lamps add to a NOON frame. Usage: nolamps.py PROJECT"""
import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Games\Mesh-lva")
from engine import project_ops as ops  # noqa: E402

scenes = Path(sys.argv[1]) / "packs" / "core_regions" / "scenes"
for base in ("lakeside", "start"):
    doc = json.loads((scenes / f"{base}.json").read_text(encoding="utf-8"))
    for i in reversed(range(len(doc["lights"]))):
        if doc["lights"][i].get("type") != "ambient":
            doc = ops.remove_light(doc, i)
    print(base, "lights left:", [l.get("type", "point") for l in doc["lights"]])
    (scenes / f"{base}__nolamps.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
