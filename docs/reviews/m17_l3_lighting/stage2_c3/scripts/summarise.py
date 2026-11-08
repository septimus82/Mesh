import json
import sys
from pathlib import Path

S = Path(sys.argv[1])
out = {}
for tag, name in (("base", "audit_Mesh-l3c.json"), ("branch", "audit_Mesh-l3s.json")):
    a = json.loads((S / name).read_text(encoding="utf-8"))
    rows = {}
    for section in ("hd2d_light2", "hd2d_light4", "hd2d_light5", "hd2d_room_light"):
        for control, rec in a[section].items():
            if control.startswith("_"):
                continue
            if rec.get("untested"):
                verdict = "UNTESTED"
            elif not rec["edit"]:
                verdict = "current choice" if rec.get("active_choice") else "NO EDIT (dead)"
            elif rec["drawn_changed"]:
                verdict = "drawn"
            elif rec["allocation_changed"]:
                verdict = "allocation only"
            else:
                verdict = "INERT: writes " + ", ".join(rec["keys"])
            rows.setdefault(control, {})[section] = verdict
    out[tag] = rows
    print(f"===== {tag}")
    for control, per in rows.items():
        print(f"{control!r:42} " + " | ".join(f"{k[5:]}: {v}" for k, v in per.items()))
# 2D: identical?
a = json.loads((S / "audit_Mesh-l3c.json").read_text(encoding="utf-8"))
b = json.loads((S / "audit_Mesh-l3s.json").read_text(encoding="utf-8"))
import re
norm = lambda xs: sorted({x for x in xs if not re.match(r"^[v^] \d+ more", x)})  # noqa: E731
print("2D panel identical (buttons, labels, boxes):", all(norm(x) == norm(y) for x, y in zip(a["2d_panel"], b["2d_panel"])))
for x, y in zip(a["2d_panel"], b["2d_panel"]):
    if norm(x) != norm(y):
        print("  only base:", sorted(set(norm(x)) - set(norm(y))), " only branch:", sorted(set(norm(y)) - set(norm(x))))
strip = lambda d: {k: ({kk: vv for kk, vv in v.items() if kk != "drawn_changed"} if isinstance(v, dict) else v)  # noqa: E731
                   for k, v in d.items() if k != "_surveys"}
print("2D sweep identical (keys written, messages):", strip(a["2d_light2"]) == strip(b["2d_light2"]))
if strip(a["2d_light2"]) != strip(b["2d_light2"]):
    for k in set(a["2d_light2"]) | set(b["2d_light2"]):
        if a["2d_light2"].get(k) != b["2d_light2"].get(k):
            print("  diff", k, a["2d_light2"].get(k), b["2d_light2"].get(k))
(S / "audit_summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
