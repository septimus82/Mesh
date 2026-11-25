"""S1-0 part B section 1: production fallback reads vs a REAL constructed GameWindow vs test fakes.

1. Statically collects every getattr/hasattr fallback that production code (engine/, mesh_net/, mesh_cli/) makes on a
   window-like receiver (see _contract_scan.py).
2. Builds a real, hidden, muted GameWindow (docs/s1/evidence/_hidden_game.py), loads a scene with a player, ticks
   on_update a few times, and checks which of those names the real window actually has.
3. Cross-references the missing names with the attribute names tests give their fake windows.

A name that production reads through a fallback, that the real window lacks, AND that test fakes supply is the
"test double invents an API" pattern: the feature works in tests and is silently off in the game.

Names production creates lazily (``window.x = ...`` on first use) are listed but not counted. Exits 1 when at least
one name is never created on a window by production yet is supplied by test fakes. Prints the full table either way.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _contract_scan import (  # noqa: E402
    production_direct_reads,
    production_fallbacks,
    production_window_writes,
    test_fake_attrs,
)
from _hidden_game import HERO, hidden_game, scene  # noqa: E402

fallbacks = production_fallbacks()
fake_attrs, counts = test_fake_attrs()
written = production_window_writes()

import re  # noqa: E402

# Other runtime objects: (label, receiver regex, how to reach the real object from the window).
OTHERS = [
    ("SceneController", re.compile(r"(^|\.)_?(scene_controller|scene_ctrl|scene)$"), lambda w: w.scene_controller),
    ("GameStateController", re.compile(r"(^|\.)_?(game_state_controller|gs_controller|gsc|gs_ctrl)$"),
     lambda w: w.game_state_controller),
    ("QuestManager (engine.quests)", re.compile(r"(^|\.)_?(quest_manager|qm|quests)$"), lambda w: w.quest_manager),
    ("MeshEventBus", re.compile(r"(^|\.)_?(event_bus|bus)$"), lambda w: w.event_bus),
    ("player MeshEntitySprite", re.compile(r"(^|\.)_?(player|player_sprite|interactor|actor)$"),
     lambda w: w.scene_controller._find_player_sprite()),
]
other_missing: dict[str, list[tuple[str, list[str]]]] = {}

with hidden_game({"Yard": scene("Yard", HERO)}) as (window, _paths, _tmp):
    for _ in range(3):
        window.on_update(1 / 60)
    present = {name for name in fallbacks if hasattr(window, name)}
    real_names = set(dir(window))
    for label, pattern, reach in OTHERS:
        reads = production_fallbacks(receiver=pattern)
        obj = reach(window)
        other_missing[label] = [(n, reads[n]) for n in sorted(reads) if not hasattr(obj, n)]
        print(f"[{label}] fallback names read: {len(reads)}; missing on the real object: {len(other_missing[label])}")

missing = sorted(set(fallbacks) - present)
# Lazily-created names (production sets them on first use) are fine behind a fallback. The defect class is a name
# production NEVER creates on any window, that test fakes nevertheless supply.
invented = [n for n in missing if n in fake_attrs and n not in written]
print(f"\nproduction fallback reads on window-like receivers: {sum(len(v) for v in fallbacks.values())} "
      f"reads of {len(fallbacks)} names")
print(f"test fake windows: {counts}")
print(f"names the real GameWindow LACKS: {len(missing)}; never created on a window by production AND supplied by "
      f"test fakes: {len(invented)}\n")
print(f"{'name':36} {'prod reads':>10} {'test files':>10} {'prod creates':>12}  first production site")
for name in sorted(missing, key=lambda n: (n in written, -len(fake_attrs.get(n, ())), -len(fallbacks[n]), n)):
    sites = fallbacks[name]
    print(f"{name:36} {len(sites):>10} {len(fake_attrs.get(name, ())):>10} {str(name in written):>12}  {sites[0]}")

# Test-only attributes that no production code reads at all are harmless noise; report the count only.
test_only = sorted(n for n in fake_attrs if n not in real_names and n not in fallbacks and not n.startswith("_"))
print(f"\nattribute names on fake windows that the real window lacks and production never reads by fallback: "
      f"{len(test_only)} (e.g. {', '.join(test_only[:12])})")

# Plain `window.attr` loads in production whose attribute the real window lacks: these raise AttributeError when
# reached (often inside a blanket except, so they also fail silently). Receivers named `win`/`window` are sometimes
# other objects (a pyglet window, Studio's window), so treat this list as leads, not findings.
direct = production_direct_reads()
direct_missing = sorted(n for n in direct if n not in real_names and n not in fallbacks)
print(f"\nplain window.<attr> loads in production whose attribute the real GameWindow lacks: {len(direct_missing)}")
for name in direct_missing:
    print(f"  {name:36} {len(direct[name]):>3} reads  e.g. {direct[name][0]}")

print("\nother runtime objects: getattr/hasattr fallback names the real object lacks (leads: optional members, "
      "other objects sharing the variable name, or test-double-only API)")
for label, rows in other_missing.items():
    print(f"  [{label}] {len(rows)}")
    for name, sites in rows:
        print(f"      {name:34} {len(sites):>3} reads  e.g. {sites[0]}")

if invented:
    print(f"\nDEFECT CLASS PRESENT: {len(invented)} window attributes exist only on test doubles (production never "
          f"creates them) but gate production code through getattr/hasattr fallbacks: {', '.join(invented)}")
    sys.exit(1)
print("\nno fake-only window attribute gates production code")
