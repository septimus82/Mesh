"""Print the timing JSONs as a table: py -3.13 perf_table.py PERF_DIR"""
import json
import sys
from pathlib import Path

for f in sorted(Path(sys.argv[1]).glob("*.json")):
    d = json.loads(f.read_text())
    print(f"== {f.stem}: {d['gl']} {d['size']} ({d['method']}, {d['rounds']} rounds)")
    for shot in ("village_noon", "village_night_lamps"):
        r = d.get(shot)
        if not r:
            continue
        cells = []
        for k in ("blit", "grade", "vignette", "haze", "combo", "dof", "dof+combo"):
            v = r[k]
            cells.append(f"{k} {v['p50_ms']:.3f}/{v['p95_ms']:.3f}" + (f" cpu {v['cpu_p50_ms']:.3f}" if "cpu_p50_ms" in v else ""))
        print(f"  {shot} clocks {r['clocks']}")
        print("   ", " | ".join(cells))
        print(f"    whole frame p50: draw+blit {r['draw+blit']['p50_ms']:.2f}, draw+combo {r['draw+combo']['p50_ms']:.2f}")
