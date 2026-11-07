"""M17-L3 scratch: the village at night with its west lamp moved off its lantern's centre (scratch copy only)."""
import json
import sys
from pathlib import Path

scenes = Path(sys.argv[1]) / "packs" / "core_regions" / "scenes"
assert "scratchpad" in str(scenes)
src = json.loads((scenes / "start__l3_night.json").read_text(encoding="utf-8"))
names = []
for dx_m, z_m in ((0.0, 2.5), (0.1, 2.5), (0.15, 2.5), (0.19, 2.5), (0.21, 2.5), (0.25, 2.5), (0.3, 2.5), (0.4, 2.5),
                  (0.0, 2.2), (0.0, 2.85), (0.0, 3.0), (0.0, 1.5), (0.6, 2.5)):
    v = json.loads(json.dumps(src))
    lamp = [l for l in v["lights"] if l.get("type") != "ambient"][0]
    lamp["x"] += dx_m * 32.0
    lamp["elevation"] = z_m * 32.0
    name = f"start__l3_off_{int(dx_m * 100):02d}cm_{int(round(z_m * 100))}cm.json"
    (scenes / name).write_bytes(json.dumps(v, indent=2).encode("utf-8"))
    names.append(name)
print("\n".join(names))
