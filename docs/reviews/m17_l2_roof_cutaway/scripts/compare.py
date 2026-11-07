"""M17-L2 scratch: baseline (engine as is) vs prototype (proposed rule), per shot. Usage: compare.py L2_DIR"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

D = Path(sys.argv[1])
b = json.loads((D / "base" / "report.json").read_text(encoding="utf-8"))
p = json.loads((D / "proto" / "report_proto.json").read_text(encoding="utf-8"))
rows = {}
print("%-30s %6s %13s %15s %15s %s" % ("shot", "vis-", "vis+ now/prop", "changed now/prop", "outside now/prop", "plain same"))
for k in b:
    same = np.array_equal(np.asarray(Image.open(D / "base" / f"{k}__nocut.png")), np.asarray(Image.open(D / "proto" / f"{k}__nocut.png")))
    rows[k] = {"visible_without_cut": b[k]["visible_without_cut"], "visible_with_cut_now": b[k]["visible_with_cut"],
               "visible_with_cut_proposed": p[k]["visible_with_cut"], "cut_px_now": b[k]["cut_changed_px"],
               "cut_px_proposed": p[k]["cut_changed_px"], "outside_box_px_now": b[k]["cut_changed_outside_player_box_px"],
               "outside_box_px_proposed": p[k]["cut_changed_outside_player_box_px"], "plain_frames_identical": same,
               "note": b[k]["note"]}
    print("%-30s %6s %6s/%-6s %7s/%-7s %7s/%-7s %s" % (k, b[k]["visible_without_cut"], b[k]["visible_with_cut"], p[k]["visible_with_cut"],
          b[k]["cut_changed_px"], p[k]["cut_changed_px"], b[k]["cut_changed_outside_player_box_px"], p[k]["cut_changed_outside_player_box_px"], same))
(D / "comparison.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
