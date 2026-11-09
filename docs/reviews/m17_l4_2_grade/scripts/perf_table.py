import json, sys
from pathlib import Path
for f in sorted(Path(sys.argv[1]).glob("*.json")):
    d = json.loads(f.read_text())
    wf = d["whole_frame"]
    print(f"== {f.stem} ({d['gl'][:24]}, {d['size']}) clocks {d.get('whole_frame_clocks')}")
    print("   whole frame GPU p50/p95 | CPU p50: " + " ; ".join(f"{n} {v['gpu']['p50_ms']:.3f}/{v['gpu']['p95_ms']:.3f} | {v['cpu']['p50_ms']:.3f}" for n, v in wf.items()))
    if "passes" in d:
        print("   passes GPU p50/p95 | CPU p50: " + " ; ".join(f"{n} {v['gpu']['p50_ms']:.4f}/{v['gpu']['p95_ms']:.4f} | {v['cpu']['p50_ms']:.4f}" for n, v in d["passes"].items()), d.get("passes_clocks"))
        print("   configure", d.get("configure_us"), "allocations", d.get("allocations"))
