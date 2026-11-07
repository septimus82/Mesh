"""M17-L3 scratch: lamp heads and pools, base vs glow (E2) vs material emissive (E1); pixels changed vs base."""
import json
import numpy as np
from PIL import Image
b = json.load(open("frames_base/frames.json")); g = json.load(open("frames_glow/frames_glow.json"))
e = json.load(open("frames_em/frames_emissive_em.json"))
rows = []
print(f"{'shot':30s} {'lamp':5s} {'head base':>9s} {'E2 glow':>8s} {'E1 emis':>8s} | {'pool base':>9s} {'E2':>6s} {'E1':>6s} | changed px E2 / E1")
for k, v in b.items():
    if k.endswith("roomoff"):
        continue
    kg, ke = k + "__glow", k + "__emissive__em"
    if kg not in g or ke not in e:
        continue
    ia = np.asarray(Image.open(f"frames_base/{k}.png")).astype(int)
    cg = int((np.abs(np.asarray(Image.open(f"frames_glow/{kg}.png")).astype(int) - ia).max(axis=2) > 0).sum())
    ce = int((np.abs(np.asarray(Image.open(f"frames_em/{ke}.png")).astype(int) - ia).max(axis=2) > 0).sum())
    for pb in v["pools"]:
        pg = [p for p in g[kg]["pools"] if p["lamp"] == pb["lamp"]][0]
        pe = [p for p in e[ke]["pools"] if p["lamp"] == pb["lamp"]][0]
        rows.append({"shot": k, "lamp": pb["lamp"], "head": [pb["lamp_head_lum"], pg["lamp_head_lum"], pe["lamp_head_lum"]],
                     "pool": [pb["pool_mean_lum"], pg["pool_mean_lum"], pe["pool_mean_lum"]], "changed_px": [cg, ce]})
        print(f"{k:30s} L{pb['lamp']:<4d} {pb['lamp_head_lum']!s:>9s} {pg['lamp_head_lum']!s:>8s} {pe['lamp_head_lum']!s:>8s} | "
              f"{pb['pool_mean_lum']:9.1f} {pg['pool_mean_lum']:6.1f} {pe['pool_mean_lum']:6.1f} | {cg} / {ce}")
json.dump(rows, open("compare_emissive.json", "w"), indent=1)
