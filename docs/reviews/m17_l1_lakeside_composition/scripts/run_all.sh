#!/bin/bash
set -u
L=/c/Users/slebb/AppData/Local/Temp/claude/c18a071c64bbe7a7/bff3a484-a7b8-4c6b-bf14-a015c42db67e/scratchpad/lva
P=$L/proj/packs/core_regions/scenes
cd $L/l1
cp cand/packs/core_regions/scenes/lakeside.json $P/lakeside__l1.json
py -3.13 - "$(cygpath -w $P)" <<'PY'
import json, sys
sys.path.insert(0, r"D:\Games\Mesh-lva")
from engine import project_ops as ops
P = sys.argv[1]
d = json.load(open(P + r"\lakeside__l1.json", encoding="utf-8"))
json.dump(ops.set_hd2d_camera(d, preset="wide"), open(P + r"\lakeside__l1__wide.json", "w", encoding="utf-8"), indent=2)
for i in reversed(range(len(d["lights"]))):
    if d["lights"][i].get("type") != "ambient":
        d = ops.remove_light(d, i)
json.dump(d, open(P + r"\lakeside__l1__nolights.json", "w", encoding="utf-8"), indent=2)
PY
rm -rf final out validate
echo "=== captures $(date +%T)"
timeout 1200 py -3.13 ../capture.py "$(cygpath -w $L/proj)" "$(cygpath -w $L/l1/final/720)" 1280 720 "$(cygpath -w $L/l1/final_720.json)" > f720.log 2>&1 || echo FAILED720
timeout 900 py -3.13 ../capture.py "$(cygpath -w $L/proj)" "$(cygpath -w $L/l1/final/1080)" 1920 1080 "$(cygpath -w $L/l1/final_1080.json)" > f1080.log 2>&1 || echo FAILED1080
timeout 900 py -3.13 ../capture.py "$(cygpath -w $L/proj)" "$(cygpath -w $L/l1/final/ctrl)" 1280 720 "$(cygpath -w $L/l1/ctrl.json)" > ctrl.log 2>&1 || echo FAILEDCTRL
py -3.13 l1_metrics.py "$(cygpath -w $L/l1/final)" "$(cygpath -w $L/l1/base/packs/core_regions/scenes/lakeside.json)" "$(cygpath -w $L/l1/cand/packs/core_regions/scenes/lakeside.json)" "$(cygpath -w $L/l1/metrics.json)" > metrics.log 2>&1 || echo FAILEDMETRICS
py -3.13 l1_sheets.py "$(cygpath -w $L/l1/final)" "$(cygpath -w $L/l1/out)" > sheets.log 2>&1 || echo FAILEDSHEETS
py -3.13 l1_diff.py "$(cygpath -w $L/l1/base/packs/core_regions/scenes/lakeside.json)" "$(cygpath -w $L/l1/cand/packs/core_regions/scenes/lakeside.json)" "$(cygpath -w $L/l1/diff.json)" > diff.log 2>&1 || echo FAILEDDIFF
py -3.13 - "$(cygpath -w $L/l1/final)" <<'PY'
import sys, json
from pathlib import Path
import numpy as np
from PIL import Image
F = Path(sys.argv[1])
lum = lambda p: float((np.asarray(Image.open(p).convert("RGB")).astype(float) @ np.array([0.2126, 0.7152, 0.0722])).mean())
out = {}
for v in ("v0_overview_wide", "v1_village", "v3_cottage", "v4_paths"):
    b, n, a = lum(F/"720"/f"{v}__before.png"), lum(F/"ctrl"/f"{v}__before_lights_removed.png"), lum(F/"720"/f"{v}__after.png")
    out[v] = {"before": round(b, 1), "before_lights_removed": round(n, 1), "after": round(a, 1), "from_lamps": round(b - n, 1), "from_composition": round(n - a, 1)}
json.dump(out, open(F.parent / "luma_split.json", "w"), indent=1)
PY
echo "=== validation $(date +%T)"
bash run_validate.sh
echo "=== gpu $(date +%T)"
timeout 1200 py -3.13 gpu_cost.py "$(cygpath -w $L/proj)" "$(cygpath -w $L/l1/gpu_cost.json)" > gpu.log 2>&1 || echo FAILEDGPU
echo "=== all done $(date +%T)"
sha256sum $L/l1/cand/packs/core_regions/scenes/*.json $L/l1/base/packs/core_regions/scenes/*.json "/d/Games/Lakeside Village/packs/core_regions/scenes/"*.json | awk '{print $1, $2}'
tasklist | grep -c -i nvidia-smi
