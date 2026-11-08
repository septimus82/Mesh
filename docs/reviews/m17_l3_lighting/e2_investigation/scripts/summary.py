"""Summarise the alternating runs (base / glow / e1, rounds 1..N): per shot, p10 and p50 ranges, and each round's
paired difference to the base run just before it. py -3.13 summary.py <runs dir>"""
import json
import statistics
import sys
from pathlib import Path

runs = Path(sys.argv[1])
data = {}
for f in sorted(runs.glob("*.json")):
    variant, rnd = f.stem.rsplit("-", 1)
    data.setdefault(variant, {})[int(rnd)] = json.loads(f.read_text())["shots"]
rounds = sorted(data["base"])
shots = [k for k in data["base"][rounds[0]] if not k.startswith("_")]
out = {}
for shot in shots:
    row = {}
    for variant in data:
        p10 = [data[variant][r][shot]["p10_ms"] for r in rounds if r in data[variant]]
        p50 = [data[variant][r][shot]["p50_ms"] for r in rounds if r in data[variant]]
        targets = {tuple(data[variant][r][shot]["camera_target"]) for r in rounds if r in data[variant]}
        row[variant] = {"p10": [min(p10), max(p10)], "p10_median": statistics.median(p10), "p50": [min(p50), max(p50)],
                        "p50_median": statistics.median(p50), "targets": len(targets)}
        if variant != "base":
            d10 = [round(data[variant][r][shot]["p10_ms"] - data["base"][r][shot]["p10_ms"], 3) for r in rounds
                   if r in data[variant]]
            d50 = [round(data[variant][r][shot]["p50_ms"] - data["base"][r][shot]["p50_ms"], 3) for r in rounds
                   if r in data[variant]]
            row[variant] |= {"paired_p10_diff": d10, "paired_p50_diff": d50,
                             "paired_p10_diff_median": statistics.median(d10),
                             "paired_p50_diff_median": statistics.median(d50)}
    out[shot] = row
clocks = {v: sorted({c for r in data[v] for c in data[v][r].get("_clocks", [])}) for v in data}
(runs.parent / "perf_summary.json").write_text(json.dumps({"shots": out, "clocks": clocks}, indent=1))
for shot, row in out.items():
    print("==", shot)
    for v, r in row.items():
        extra = (f" paired p10 diff {r['paired_p10_diff']} (median {r['paired_p10_diff_median']:+.3f});"
                 f" p50 diff median {r['paired_p50_diff_median']:+.3f}") if v != "base" else ""
        print(f"  {v:5} p10 {r['p10'][0]:.3f}-{r['p10'][1]:.3f} (med {r['p10_median']:.3f}) p50 med {r['p50_median']:.3f}"
              f" targets={r['targets']}{extra}")
for v, c in clocks.items():
    print(v, "clocks seen:", c[:6], "..." if len(c) > 6 else "")
