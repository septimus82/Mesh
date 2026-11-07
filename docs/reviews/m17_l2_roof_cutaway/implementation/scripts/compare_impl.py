"""M17-L2 scratch: before (f9f1f81) vs the implementation (feature/m17-l2-cutaway), and the prototype, per shot."""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

D = Path(sys.argv[1])
b = json.load(open(D / "base" / "report.json")); p = json.load(open(D / "proto" / "report_proto.json")); m = json.load(open(D / "impl" / "report.json"))
same_proto = same_plain = 0
rows = {}
for k in b:
    same_proto += np.array_equal(np.asarray(Image.open(D / "impl" / f"{k}__cut.png")), np.asarray(Image.open(D / "proto" / f"{k}__proto.png")))
    same_plain += np.array_equal(np.asarray(Image.open(D / "impl" / f"{k}__nocut.png")), np.asarray(Image.open(D / "base" / f"{k}__nocut.png")))
    rows[k] = {"visible_without_cut": b[k]["visible_without_cut"], "visible_with_cut_before": b[k]["visible_with_cut"],
               "visible_with_cut_after": m[k]["visible_with_cut"], "cut_px_before": b[k]["cut_changed_px"],
               "cut_px_after": m[k]["cut_changed_px"], "outside_box_px_before": b[k]["cut_changed_outside_player_box_px"],
               "outside_box_px_after": m[k]["cut_changed_outside_player_box_px"], "note": b[k]["note"]}
summary = {"impl_frames_identical_to_prototype": f"{same_proto}/{len(b)}", "cutaway_off_frames_identical": f"{same_plain}/{len(b)}",
           "visibility_unchanged_in_every_shot": all(rows[k]["visible_with_cut_after"] == rows[k]["visible_with_cut_before"] for k in rows)}
hid = [k for k in rows if rows[k]["visible_without_cut"] == 1.0]
summary["nothing_hidden_cut_px_before_after"] = {k: [rows[k]["cut_px_before"], rows[k]["cut_px_after"]] for k in hid}
need = [k for k in rows if rows[k]["visible_without_cut"] < 1.0]
red = [1 - rows[k]["cut_px_after"] / rows[k]["cut_px_before"] for k in need]
red_out = [1 - rows[k]["outside_box_px_after"] / rows[k]["outside_box_px_before"] for k in need]
summary["needed_cuts_hole_smaller_pct"] = [round(100 * min(red)), round(100 * max(red))]
summary["needed_cuts_outside_box_less_pct"] = [round(100 * min(red_out)), round(100 * max(red_out))]
tb = sum(r["cut_px_before"] for r in rows.values()); ta = sum(r["cut_px_after"] for r in rows.values())
ob = sum(r["outside_box_px_before"] for r in rows.values()); oa = sum(r["outside_box_px_after"] for r in rows.values())
summary["all_27_cut_px"] = [tb, ta, round(100 * (ta / tb - 1))]
summary["all_27_outside_box_px"] = [ob, oa, round(100 * (oa / ob - 1))]
json.dump({"summary": summary, "shots": rows}, open(D / "comparison_impl.json", "w"), indent=1)
print(json.dumps(summary, indent=1))
