"""S1-0 part B section 3: behaviour progress that lives only on the behaviour instance (the #620 / #636 pattern).

A room is rebuilt from its authored file on every entry (engine/scene_runtime/room_memory.py remembers only which
authored objects were REMOVED). So any "this already happened" fact a behaviour keeps in ``self.<field>`` is
forgotten on room re-entry unless the behaviour also writes it to game state (flags / vars / counters) or reads it
back from there. A save restores ``saveable_state()`` only for the entities of the room the save was made in.

Static scan (AST, no engine import): for every class in engine/behaviours/, the ``self.<field>`` assignments made
OUTSIDE ``__init__`` whose names say "progress" (once/triggered/used/looted/unlocked/...), whether the class has
``saveable_state``, and whether it touches game state at all (set_flag/set_var/add_counter/get_flag/...).

Prints the table and always exits 0 (a heuristic candidate list). Classes that record progress only on the instance
with no game-state write or read are the at-risk set; repro_instance_state_resets_on_reentry.py checks them for real.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PROGRESS = re.compile(
    r"(once|triggered|fired|used|looted|unlocked|locked|opened|is_open|activated|consumed|done|completed|"
    r"given|played|started|finished|collected|is_on|_on$|^on$|state$|visited|spent|claimed|count|cleared|"
    r"remaining|_shown|_seen|_ran|has_)", re.I)
TRANSIENT = re.compile(r"(timer|elapsed|cooldown|_dt|anim|frame|path|target|velocity|vx|vy|_last_|cache|_owner|"
                       r"_box|sprite|texture|_subscri|unsub|_handle|_listener|_pending_events|_warned|_logged)", re.I)
GAME_STATE = re.compile(r"\b(set_flag|toggle_flag|set_var|set_counter|add_counter|inc_counter|get_flag|get_var|"
                        r"get_counter|game_state|game_state_controller|room_memory|flag_on_|set_flags|"
                        r"remember)\b")


def scan() -> list[dict[str, object]]:
    rows = []
    for path in sorted((REPO / "engine" / "behaviours").glob("*.py")):
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for cls in (n for n in tree.body if isinstance(n, ast.ClassDef)):
            fields: dict[str, list[str]] = {}
            methods = {f.name for f in cls.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))}
            for fn in (f for f in cls.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))):
                if fn.name in ("__init__", "restore_state", "reset", "_reset", "configure", "apply_config"):
                    continue
                for node in ast.walk(fn):
                    targets = node.targets if isinstance(node, ast.Assign) else (
                        [node.target] if isinstance(node, (ast.AugAssign, ast.AnnAssign)) else [])
                    for t in targets:
                        if (isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self"
                                and PROGRESS.search(t.attr) and not TRANSIENT.search(t.attr)):
                            fields.setdefault(t.attr, []).append(f"{fn.name}:{node.lineno}")
            if not fields:
                continue
            body = ast.get_source_segment(src, cls) or ""
            rows.append({
                "cls": cls.name,
                "file": path.relative_to(REPO).as_posix(),
                "fields": fields,
                "saveable": "saveable_state" in methods,
                "game_state": bool(GAME_STATE.search(body)),
            })
    return rows


def main() -> int:
    rows = scan()
    at_risk = [r for r in rows if not r["game_state"]]
    print(f"{'behaviour class':34} {'saveable':8} {'gamestate':9}  progress fields set outside __init__ (method:line)")
    for r in rows:
        fields = "; ".join(f"{k}@{','.join(v[:2])}" for k, v in sorted(r["fields"].items()))  # type: ignore[union-attr]
        print(f"{r['cls']:34} {str(r['saveable']):8} {str(r['game_state']):9}  {fields}  [{r['file']}]")
    print(f"\n{len(rows)} classes record progress on the instance; {len(at_risk)} never touch game state: "
          f"{', '.join(str(r['cls']) for r in at_risk)}")
    return 0  # a heuristic scan, not a repro: each row needs a runtime check


if __name__ == "__main__":
    sys.exit(main())
