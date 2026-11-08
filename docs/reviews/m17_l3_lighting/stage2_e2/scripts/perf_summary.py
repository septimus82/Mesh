"""Summarise perf/base-N.json and perf/e2-N.json: per shot, p10 / p50 ranges, each round's E2 - base difference,
draw calls, lamp-head draws, buffer and texture bytes, and the clocks seen. py -3.13 perf_summary.py <perf dir>"""
import json
import statistics
import sys
from pathlib import Path

d = Path(sys.argv[1])
runs = {tag: {int(p.stem.split("-")[1]): json.loads(p.read_text()) for p in d.glob(f"{tag}-*.json")} for tag in ("base", "e2")}
rounds = sorted(set(runs["base"]) & set(runs["e2"]))
shots = [k for k in runs["base"][rounds[0]] if k != "worktree"]
out = {"rounds": rounds, "shots": {}}
for shot in shots:
    row = {}
    for tag in ("base", "e2"):
        v = [runs[tag][r][shot] for r in rounds]
        row[tag] = {"p10": [min(x["p10_ms"] for x in v), max(x["p10_ms"] for x in v)],
                    "p10_median": statistics.median(x["p10_ms"] for x in v),
                    "p50_median": statistics.median(x["p50_ms"] for x in v),
                    "draw_calls": sorted({x["draw_calls"] for x in v}), "lamp_head_draws": sorted({x["lamp_head_draws"] for x in v}),
                    "buffer_bytes": sorted({x["buffer_bytes"] for x in v}), "texture_bytes": sorted({x["texture_bytes"] for x in v}),
                    "targets": len({tuple(x["target"]) for x in v}), "clocks": sorted({x["clocks"] for x in v})}
    d10 = [round(runs["e2"][r][shot]["p10_ms"] - runs["base"][r][shot]["p10_ms"], 3) for r in rounds]
    d50 = [round(runs["e2"][r][shot]["p50_ms"] - runs["base"][r][shot]["p50_ms"], 3) for r in rounds]
    row["paired_p10"] = d10
    row["paired_p10_median"] = statistics.median(d10)
    row["paired_p50_median"] = statistics.median(d50)
    out["shots"][shot] = row
(d.parent / "perf_e2_summary.json").write_text(json.dumps(out, indent=1))
for shot, r in out["shots"].items():
    b, e = r["base"], r["e2"]
    print(f"{shot:24} base p10 {b['p10'][0]:.3f}-{b['p10'][1]:.3f} e2 {e['p10'][0]:.3f}-{e['p10'][1]:.3f} "
          f"paired {r['paired_p10']} med {r['paired_p10_median']:+.3f} (p50 med {r['paired_p50_median']:+.3f}) | "
          f"draws {b['draw_calls']}->{e['draw_calls']} heads {e['lamp_head_draws']} buf {b['buffer_bytes']}->{e['buffer_bytes']} "
          f"tex {b['texture_bytes']}->{e['texture_bytes']} targets {b['targets']}/{e['targets']}")
clk = sorted({c for tag in runs for rr in runs[tag].values() for k, v in rr.items() if k != "worktree" for c in [v["clocks"]]})
print("clocks:", clk[:4], "...", len(clk), "distinct")
