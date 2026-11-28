"""S1-0 part C (found while reading mesh_net's duplicated drop rules): a drop with ``"chance": 0`` always drops.

    py -3.13 docs/s1/evidence/repro_drop_chance_zero.py      (PYTHONPATH = the repository root)

Both the engine's DropTable (``engine/behaviours/drop_table.py:62``) and mesh_net's copy of its rules
(``mesh_net/scene_room.py`` ``roll_drops``) normalise ``float(entry.get("chance", 1.0) or 1.0)``: 0 is falsy, so it
becomes 1.0. ``"min_quantity": 0`` likewise becomes 1. A negative chance clamps to 0 and never drops. Component level:
the real DropTable instance and its real roll, 200 seeded rolls each; nothing is drawn or shown.
Exit 1 when the defect reproduces.
"""

from __future__ import annotations

import engine
from engine.behaviours.drop_table import DropTable
from mesh_net.scene_room import roll_drops

print(f"engine from {engine.__file__}")


def engine_drops(chance: float) -> int:
    table = DropTable(object(), None, drops=[{"item_id": "healing_potion", "chance": chance}], seed=7)
    return sum(table._roll(table.drops[0]["chance"]) for _ in range(200))


def net_drops(chance: float) -> int:
    return sum(bool(roll_drops({"seed": s, "drops": [{"item_id": "healing_potion", "chance": chance}]}))
               for s in range(200))


rows = {c: (engine_drops(c), net_drops(c)) for c in (0, 0.0, -0.5, 0.25, 1.0)}
for chance, (eng, net) in rows.items():
    print(f"chance {chance!r:>5}: engine DropTable dropped {eng:3}/200 | mesh_net roll_drops dropped {net:3}/200")
table = DropTable(object(), None, drops=[{"item_id": "healing_potion", "chance": 0, "min_quantity": 0}])
print(f"normalised entry for chance 0, min_quantity 0: {table.drops[0]}")
if rows[0][0] == 200 and rows[0][1] == 200 and rows[-0.5] == (0, 0):
    print("DEFECT REPRODUCED: chance 0 always drops (0 is read as 'unset' -> 1.0), while chance -0.5 never does")
    raise SystemExit(1)
print("not reproduced")
