"""Scratch (Lakeside visual audit): the comparison scenes, made from the shipped scenes with Mesh's own authoring
operations (engine.project_ops: what Studio, `mesh author` and MCP apply), written beside them in the SCRATCH copy.
The shipped scene files are never changed (their sha256 is checked before and after).
Usage: variants.py PROJECT
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, r"D:\Games\Mesh-lva")
from engine import project_ops as ops  # noqa: E402

project = Path(sys.argv[1])
scenes = project / "packs" / "core_regions" / "scenes"
SHIPPED = {"lakeside.json": "18a7ee94b1c8e9444326f9643ebb4bbbb9315bad1edff5b777ab67da8c7f3901",
           "start.json": "d2e8a80e420d506d0773d88daaa223dd323f73601893c7ab164ca17e290c401b",
           "cottage.json": "1a07a9cb307253aabb1a06aa04b1a3532079f0795202fe8d78c1b884a9440f08"}


def check():
    for name, digest in SHIPPED.items():
        got = hashlib.sha256((scenes / name).read_bytes()).hexdigest()
        assert got == digest, (name, got)


check()
made = {}
for base in ("lakeside", "start"):
    doc = json.loads((scenes / f"{base}.json").read_text(encoding="utf-8"))
    variants = {
        "morning": ops.set_hd2d_sun(doc, preset="morning"),
        "evening": ops.set_hd2d_sun(doc, preset="evening"),
        "night": ops.set_hd2d_sun(doc, preset="night"),
        "overcast": ops.set_hd2d_sun(doc, preset="overcast"),
        "dof": ops.set_depth_of_field(doc, preset="subtle"),
        "evening_dof": ops.set_depth_of_field(ops.set_hd2d_sun(doc, preset="evening"), preset="subtle"),
        "wide": ops.set_hd2d_camera(doc, preset="wide"),
    }
    for key, out in variants.items():
        path = scenes / f"{base}__{key}.json"
        path.write_text(json.dumps(out, indent=2), encoding="utf-8")
        made[path.name] = {"base": f"{base}.json", "op": key,
                           "hd2d_changed": sorted(k for k in set(out["settings"]["hd2d"]) | set(doc["settings"]["hd2d"])
                                                  if out["settings"]["hd2d"].get(k) != doc["settings"]["hd2d"].get(k))}
check()
(project / "variants.json").write_text(json.dumps(made, indent=1), encoding="utf-8")
print(json.dumps(made, indent=1))
