"""Scratch (CI-422A): the evidence run's 8 runners: calibration, the gate test, and the A/B with each fault."""
import glob
import json
import re
import statistics as st
import sys
from pathlib import Path

D = Path(sys.argv[1])
KEYS = ("sculpt_frame_ms", "control_frame_ms", "incremental_ms", "ratio", "update_terrain_ms", "commit_ms", "release_extra_ms")
runners = []
for job in sorted(p for p in D.iterdir() if p.is_dir()):
    cal = [json.loads(l) for l in (job / "calibration_before.txt").read_text(encoding="utf-8").splitlines() if l.startswith("{")]
    c = {k: v for d in cal for k, v in d.items()}
    gate = None
    x = job / "gate.xml"
    if x.exists():
        m = re.search(r'measure.terrain_stroke" value="([^"]*)"', x.read_text(encoding="utf-8"))
        if m:
            gate = json.loads(m.group(1).replace("&quot;", '"'))
        gate_failed = 'failures="0"' not in x.read_text(encoding="utf-8")
    ab = {}
    for f in sorted(job.glob("ab_*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        ab[f.stem[3:]] = {**r["summary"], **r["reloads"], "frames_all": r["sculpt_frame_all"]}
    runners.append({"job": job.name, "cpu": c.get("cpu"), "cpu_ms": c.get("cpu_ms"), "gl_ms": c.get("gl_frame_ms"),
                    "gate": gate, "gate_failed": gate_failed, "ab": ab})
json.dump(runners, open(D / "runners.json", "w"), indent=1)
print(f"{'job':22} {'cpu':26} {'cpu_ms':>6} {'gl':>5} | gate med  | " + " ".join(f"{k[:12]:>12}" for k in KEYS))
for r in runners:
    n = r["ab"]["1_none_5"]
    g = r["gate"]["frame_ms"]["median"] if r["gate"] else None
    print(f"{r['job']:22} {r['cpu'][:26]:26} {r['cpu_ms']:6.1f} {r['gl_ms']:5.1f} | {g!s:6} {'F' if r['gate_failed'] else ' '} | " + " ".join(f"{n[k]:12.2f}" for k in KEYS))
print()
def cv(v): return st.pstdev(v) / st.mean(v) * 100
for k in KEYS:
    v = [r["ab"]["1_none_5"][k] for r in runners]
    vn = [r["ab"]["1_none_5"][k] / r["cpu_ms"] for r in runners]
    print(f"baseline {k:18} min {min(v):7.2f} max {max(v):7.2f}  cv {cv(v):5.1f}%   /cpu_ms cv {cv(vn):5.1f}%")
v1 = [r["ab"]["1_none_5"]["sculpt_frame_ms"] for r in runners]; v2 = [r["ab"]["8_none_5"]["sculpt_frame_ms"] for r in runners]
print("drift none_5 -> none_8 sculpt frame:", [round(b / a, 3) for a, b in zip(v1, v2)])
v1 = [r["ab"]["1_none_5"]["incremental_ms"] for r in runners]; v2 = [r["ab"]["8_none_5"]["incremental_ms"] for r in runners]
print("drift none_5 -> none_8 incremental:", [round(b / a, 3) for a, b in zip(v1, v2)])
print()
for mut in ("2_reload_on_release_5", "3_reload_per_flush_5", "4_rebuild_all_5", "5_cpu_frame_5", "6_cpu_dab_5", "7_cpu_frame_15"):
    print(f"== {mut}: reloads {[r['ab'][mut]['room_reloads'] for r in runners]}")
    for k in KEYS:
        ratios = []
        for r in runners:
            base = (r["ab"]["1_none_5"][k] + r["ab"]["8_none_5"][k]) / 2
            val = r["ab"][mut][k]
            ratios.append(None if val is None or not base else round(val / base, 2))
        print(f"   {k:18} x baseline (same runner): {ratios}")
