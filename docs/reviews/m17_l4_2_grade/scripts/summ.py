import json, sys
m = json.load(open(sys.argv[1]))
rows = [v for v in m.values() if isinstance(v, dict) and v.get("preset") not in (None, "off")]
for preset in ("natural", "golden_hour", "moonlight", "interior_warm"):
    r = [v for v in rows if v["preset"] == preset]
    def agg(k, f):
        xs = [v[k] for v in r if v.get(k) is not None]
        return round(f(xs), 3) if xs else None
    sp = [s for v in r for s in v["sprites"]]
    glass = [g for v in r for g in v.get("glass_hue_shift", [])]
    print(f"{preset:13} crushed+ max {agg('crushed_increase', max)} clipped+ max {agg('clipped_increase', max)} | "
          f"char |W| min {min((s['abs_weber_change'] for s in sp), default=None)} edge min {min((s['edge_ratio'] for s in sp), default=None)} "
          f"char hue max {max((s['hue_shift'] or 0 for s in sp), default=None)} | grass hue max {agg('grass_hue_shift', max)} sat {agg('grass_sat_ratio', min)}-{agg('grass_sat_ratio', max)} "
          f"| blue hue max {agg('blue_hue_shift', max)} | dark detail min {agg('dark_detail_ratio', min)} dark mean {agg('dark_mean_ratio', min)}-{agg('dark_mean_ratio', max)} "
          f"| corners {agg('corner_ratio', min)} | glass hue max {max(glass, default=None)}")
