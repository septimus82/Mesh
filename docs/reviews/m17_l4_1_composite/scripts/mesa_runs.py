import json, sys
from pathlib import Path
for f in sorted(Path(sys.argv[1]).glob("*.json")):
    w = json.loads(f.read_text())["whole_frame"]
    print(f.stem, {n: (v["gpu"]["p50_ms"], v["cpu"]["p50_ms"]) for n, v in w.items()})
