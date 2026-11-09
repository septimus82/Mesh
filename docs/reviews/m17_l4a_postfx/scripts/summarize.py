"""Summarise lab.py metrics per candidate over every shot x time: py -3.13 summarize.py FRAMES OUT.json
  sprite_weber_ratio / sprite_edge_ratio: min and median over characters (1.0 = as readable as the original)
  crushed / clipped: worst increase in % of pixels vs the original
  depth_cue: (far-band RMS contrast / near-band RMS contrast) relative to the original's (<1: far recedes)
  far_sat / near_sat: band saturation relative to the original
  lamp hue shift: worst |hue change| (degrees) of a lamp head's brightest pixel (lamp variants)
"""
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

M = json.loads((Path(sys.argv[1]) / "metrics.json").read_text(encoding="utf-8"))
orig = {(v["shot"], v["time"]): v for v in M.values() if isinstance(v, dict) and v.get("candidate") == "original"}
rows: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
for v in M.values():
    if not isinstance(v, dict) or "candidate" not in v or v["candidate"] == "original":
        continue
    o = orig[(v["shot"], v["time"])]
    r = rows[v["candidate"]]
    outdoor = v["shot"] != "interior"
    for s in v["sprites"]:
        if s.get("weber_ratio") is not None:
            r["weber"].append(s["weber_ratio"])
        o_s = next((x for x in o["sprites"] if x["pixels"] == s["pixels"]), None)
        if o_s is not None:
            r["weber_abs_loss"].append(abs(s["weber"]) - abs(o_s["weber"]))
        r["edge"].append(s["edge_ratio"])
    f, of = v["frame"], o["frame"]
    r["crushed"].append(f["crushed_pct"] - of["crushed_pct"])
    r["clipped"].append(f["clipped_pct"] - of["clipped_pct"])
    r["luma"].append(f["mean_luma"] / max(1e-6, of["mean_luma"]))
    if outdoor:
        cue = (f["far_band"]["rms_contrast"] / f["near_band"]["rms_contrast"]) / \
              (of["far_band"]["rms_contrast"] / of["near_band"]["rms_contrast"])
        r["cue"].append(cue)
        r["far_sat"].append(f["far_band"]["saturation"] / max(1e-6, of["far_band"]["saturation"]))
        r["near_sat"].append(f["near_band"]["saturation"] / max(1e-6, of["near_band"]["saturation"]))
    if v.get("changed_pct") is not None:
        r["changed"].append(v["changed_pct"])
    for lh, ol in zip(v.get("lamp_heads") or [], o.get("lamp_heads") or []):
        dh = abs(lh["hue_deg"] - ol["hue_deg"])
        r["lamp_hue"].append(min(dh, 360 - dh))
        r["lamp_sat"].append(lh["sat"] - ol["sat"])
        r["lamp_val"].append(lh["val"] - ol["val"])


def q(xs: list[float], f) -> float | None:
    return round(f(xs), 3) if xs else None


out = {}
for cand, r in rows.items():
    out[cand] = {
        "frames": len(r["luma"]),
        "sprite_weber_ratio_min": q(r["weber"], min), "sprite_weber_ratio_median": q(r["weber"], statistics.median),
        "sprite_abs_weber_change_min": q(r["weber_abs_loss"], min),
        "sprite_edge_ratio_min": q(r["edge"], min), "sprite_edge_ratio_median": q(r["edge"], statistics.median),
        "crushed_pct_increase_max": q(r["crushed"], max), "clipped_pct_increase_max": q(r["clipped"], max),
        "mean_luma_ratio_median": q(r["luma"], statistics.median),
        "depth_cue_median": q(r["cue"], statistics.median), "depth_cue_min": q(r["cue"], min),
        "far_sat_ratio_median": q(r["far_sat"], statistics.median),
        "near_sat_ratio_median": q(r["near_sat"], statistics.median),
        "changed_pct_median": q(r["changed"], statistics.median),
        "lamp_hue_shift_max_deg": q(r["lamp_hue"], max), "lamp_sat_change_min": q(r["lamp_sat"], min),
        "lamp_val_change_min": q(r["lamp_val"], min),
    }
Path(sys.argv[2]).write_text(json.dumps(out, indent=1), encoding="utf-8")
cols = ["frames", "sprite_abs_weber_change_min", "sprite_edge_ratio_min", "crushed_pct_increase_max",
        "clipped_pct_increase_max", "mean_luma_ratio_median", "depth_cue_median", "far_sat_ratio_median",
        "near_sat_ratio_median", "lamp_hue_shift_max_deg", "lamp_val_change_min"]
print("| candidate | " + " | ".join(c.replace("_", " ") for c in cols) + " |")
print("|---" * (len(cols) + 1) + "|")
for cand in ["grade", "vignette", "vignette_strong", "haze", "haze_overlay", "dof_subtle", "dof_miniature", "combo",
             "combo_dof"]:
    if cand in out:
        print(f"| {cand} | " + " | ".join(str(out[cand][c]) for c in cols) + " |")
