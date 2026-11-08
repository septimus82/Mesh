import json
import sys
from pathlib import Path

sys.path.insert(0, "tooling")
import hd2d_emissive_demo as d  # noqa: E402

r = d.check(Path(sys.argv[1]))
Path(sys.argv[1], "report.json").write_text(json.dumps(r, indent=1))
print("\n".join(r["sampling_report"]))
for name, pts in r["sampling"].items():
    print("==", name)
    for k, v in pts.items():
        print("  ", k, v)
