"""Run hd2d_emissive_demo.check and print each panel's pixels against what glTF means (compact)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, "tooling")
import hd2d_emissive_demo as d  # noqa: E402

r = d.check(Path(sys.argv[1]))
Path(sys.argv[1], "report.json").write_text(json.dumps(r, indent=1))
print("\n".join(r["report"]))
tex = d.TEXELS
print("saved evening:", r["studio_saved_evening"])
for label in ("noon", "night", "night_lamp_on", "night_lamp_off", "reimported", "studio", "studio_reopened"):
    print("==", label)
    for name, base, factor, textured, _s in d.SWATCHES:
        px = r[label][name]
        if textured:
            got = [px[f"t{k}"] for k in range(4)]
            want = [d.expected_glow(factor, tex[k]) for k in range(4)]
        else:
            got = [px["middle"]]
            want = [d.expected_glow(factor) if factor and base == d.BLACK else None]
        print(f"  {name:20} got {got}  want {want}")
