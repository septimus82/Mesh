"""Summarise probe485 JSON: per room/pose, the cases whose Studio picture changed, and parity/restores/live counts."""
import json
import sys

for f in sys.argv[1:]:
    d = json.load(open(f))
    print(f"== {d['room']} scatter={d.get('scatter_added')} shadows={d['shadows']} canopy_blocks={d['canopy_blocks']} gl={d['gl'][:24]}")
    poses = {"default": d["pose_default"], **d.get("poses", {})}
    for name, p in poses.items():
        bits = []
        for key in ("shadows_on", "shadows_off"):
            if key not in p:
                continue
            ch = {c: v["picture"]["changed"] for c, v in p[key]["cases"].items() if v["picture"]["changed"]}
            stable = p[key]["restored_same"] and p[key]["live_before_after"][0] == p[key]["live_before_after"][1]
            bits.append(f"{key}: {ch or 'none changed'} restored+live_flat={stable}")
        sc = p["studio_cam"]
        print(f"  {name:22} studio pitch {sc['pitch']} yaw {sc['yaw']} | parity {p['parity_game_path_vs_studio_same_camera']['changed']}")
        for b in bits:
            print("     ", b)
    print("  live_end", d["live_end"])
