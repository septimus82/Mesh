"""Compare exact485 runs: every frame hash equal across all given files; camera moved during the walk."""
import json
import sys

runs = [json.load(open(f)) for f in sys.argv[1:]]
ref = runs[0]["rooms"]
for name, r in ref.items():
    hashes = lambda rr: [f[1] for f in rr["rooms"][name]["frames"]] + [f[2] for f in rr["rooms"][name]["frames"] if f[0] == "settled"]  # noqa: E731
    same = all(hashes(rr) == hashes(runs[0]) for rr in runs)
    distinct = len(set(f[1] for f in r["frames"]))
    t0, t1 = r["frames"][1][2], r["frames"][-2][2]
    live_same = all(rr["rooms"][name]["live"] == r["live"] for rr in runs)
    print(f"{name:28} frames {len(r['frames'])} distinct {distinct} identical_across_{len(runs)}_runs {same} live_same {live_same} cam {t0} -> {t1}")
