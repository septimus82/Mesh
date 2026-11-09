"""Compare exact.py runs: py -3.13 exact_compare.py BASE.json OTHER.json [OTHER2.json ...]"""
import json
import sys

base = json.load(open(sys.argv[1]))
for other_path in sys.argv[2:]:
    o = json.load(open(other_path))
    keys = [k for k in base if isinstance(base[k], dict)]
    same = [k for k in keys if base[k]["sha256"] == o[k]["sha256"]]
    diff = [k for k in keys if k not in same]
    calls = [k for k in keys if base[k].get("draw_calls") != o[k].get("draw_calls")]
    objs = {k: (base[k].get("renderer_gl_objects"), o[k].get("renderer_gl_objects")) for k in keys
            if base[k].get("renderer_gl_objects") != o[k].get("renderer_gl_objects")}
    live = {k: {kk: o[k]["live"][kk] - base[k]["live"][kk] for kk in base[k]["live"]} for k in keys
            if "live" in base[k] and base[k]["live"] != o[k]["live"]}
    print(f"{other_path.split(chr(92))[-1].split('/')[-1]} vs base ({o['gl']}): identical {len(same)}/{len(keys)}"
          f"; different: {diff}; draw-call differences: {calls}; gl-object differences: {objs}; live differences: {live}")
    print("   dof drawn:", sorted({k: base[k]['dof_drawn'] for k in keys if 'dof_drawn' in base[k]}.items())[:3], "...")
