"""Repro: one gameplay event completes two consecutive quest stages when both complete on the same event.

engine.quest_runtime.progress.handle_event loops twice over every quest ("two passes ... to start deterministically")
and re-runs check_completion_triggers in the second pass: stage 1 completes on the event, stage 2 auto-starts, and the
second pass completes stage 2 with that same event. Uses the live engine.quests.QuestManager (what GameWindow installs
as game_state_controller.quests) and GameStateController.handle_event (what game_runtime/tick.py calls per event).
Also scans shipped quest data for consecutive stages sharing a completion trigger.
"""
import glob
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.chdir(r"D:\Games\Mesh-audit")
import engine  # noqa: E402
from engine.events import MeshEvent  # noqa: E402
from engine.game_state_controller import GameStateController  # noqa: E402
from engine.quests import QuestManager  # noqa: E402

print("engine from", engine.__file__)
tmp = Path(tempfile.mkdtemp(prefix="mesh_audit_quest_"))
try:
    data = {"quests": [{"id": "wolves", "title": "Thin the pack", "auto_start": True,
                        "reward": {"inc_counters": {"gold": 100}},
                        "stages": [{"id": "first_wolf", "title": "Kill a wolf", "complete_on": {"type": "enemy_killed", "payload": {"kind": "wolf"}}},
                                   {"id": "second_wolf", "title": "Kill another wolf", "complete_on": {"type": "enemy_killed", "payload": {"kind": "wolf"}}}]}]}
    (tmp / "quests.json").write_text(json.dumps(data), encoding="utf-8")
    signals = []
    window = SimpleNamespace(event_bus=None, emit_signal=lambda name, **k: signals.append((name, k.get("stage_id"))))
    gs = GameStateController(window)
    window.game_state_controller, window.game_state = gs, gs.state
    window.set_flag, window.get_flag = gs.set_flag, gs.get_flag
    window.inc_counter = lambda n, a: gs.add_counter(n, a)
    gs.quests = QuestManager(window, data_path=str(tmp / "quests.json"))
    gs.quests._definitions = {k: v for k, v in gs.quests._definitions.items() if k == "wolves"}  # (ignore pack quests)
    gs.quests.reload_from_state()
    print("before:", gs.quests.get_state_snapshot("wolves"))
    gs.handle_event(MeshEvent(type="enemy_killed", payload={"kind": "wolf"}))  # ONE wolf killed
    after = gs.quests.get_state_snapshot("wolves")
    print("after one kill:", after, "gold:", gs.get_counter("gold", 0))
    bad = bool(after) and after.get("status") == "completed"
finally:
    shutil.rmtree(tmp, ignore_errors=True)  # (the temp folder this script created)

# shipped data: consecutive stages with the same completion trigger
hits = []
for f in ["assets/data/quests.json", *glob.glob("packs/*/assets/data/quests.json"), *glob.glob("packs/*/quests/*.json")]:
    try:
        raw = json.load(open(f, encoding="utf-8"))
    except Exception:
        continue
    quests = raw.get("quests", raw) if isinstance(raw, dict) else raw
    items = quests.values() if isinstance(quests, dict) else quests
    for q in items if isinstance(items, (list, type({}.values()))) else []:
        if not isinstance(q, dict):
            continue
        stages = [s for s in q.get("stages") or [] if isinstance(s, dict)]
        trig = [json.dumps(s.get("complete_on") or s.get("complete_event") or s.get("complete_when"), sort_keys=True) for s in stages]
        for a, b, sa, sb in zip(trig, trig[1:], stages, stages[1:]):
            if a != "null" and a == b and not sb.get("start_on_event") and not sb.get("start_event"):
                hits.append(f"{f}: {q.get('id')} {sa.get('id')} -> {sb.get('id')} {a}")
print("shipped consecutive same-trigger stages:", hits or "none")
print("DEFECT REPRODUCED: one event completed both stages" if bad else "not reproduced")
sys.exit(1 if bad else 0)
