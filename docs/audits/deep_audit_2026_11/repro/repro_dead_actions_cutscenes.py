"""Repro (two wiring defects, real classes, the live delivery/tick functions):

A) ActionListRunner never fires in a running game: the scene's per-frame delivery
   (scene_controller_parts/runtime_hooks._deliver_events_to_behaviours, called from game_runtime/tick.py) only calls
   behaviour.on_event; ActionListRunner only implements handle_event(event_type, payload), which nothing in engine/ calls.
B) CutsceneController steps move_entity / camera_focus / start_dialogue(target) call scene_controller.find_sprite(),
   which the real SceneController doesn't have -> AttributeError out of CutsceneController.update (tick.py:239, no guard).
"""
import os
import sys
from types import SimpleNamespace

os.chdir(r"D:\Games\Mesh-audit")
import engine  # noqa: E402
from engine.behaviours.action_list_runner import ActionListRunnerBehaviour as ActionListRunner  # noqa: E402
from engine.cutscene_controller import CutsceneController  # noqa: E402
from engine.events import MeshEvent  # noqa: E402
from engine.game_state_controller import GameStateController  # noqa: E402
from engine.scene_controller import SceneController  # noqa: E402
from engine.scene_controller_parts import runtime_hooks  # noqa: E402

print("engine from", engine.__file__)
defects = []

# --- A
window = SimpleNamespace(event_bus=None, emit_signal=lambda *a, **k: None, strict_mode=True)
gs = GameStateController(window)
window.game_state_controller = gs
sprite = SimpleNamespace(mesh_name="lever_logic", properties={})
runner = ActionListRunner(sprite, window, listen_events=["lever_pulled"], actions=[{"type": "set_flag", "flag": "gate_open"}])
sprite.mesh_behaviours_runtime = [runner]
scene = SimpleNamespace(window=window, _iter_layered_sprites=lambda: [sprite])
runtime_hooks._deliver_events_to_behaviours(scene, [MeshEvent(type="lever_pulled", payload={})])
for _ in range(5):
    runner.update(0.1)
live = bool(gs.state.flags.get("gate_open"))
print("A) via the game's event delivery: gate_open =", live)
runner.handle_event("lever_pulled", {})
for _ in range(5):
    runner.update(0.1)
print("A) via handle_event (what the tests call): gate_open =", bool(gs.state.flags.get("gate_open")))
if not live:
    defects.append("A: ActionListRunner inert under the live delivery path")

# --- B
print("B) SceneController has find_sprite:", hasattr(SceneController, "find_sprite"),
      "| has find_entity:", hasattr(SceneController, "find_entity"))
cwin = SimpleNamespace(scene_controller=object.__new__(SceneController))  # the real class; method lookup is all that matters
cc = CutsceneController(cwin)
cc.register_cutscenes([{"id": "intro", "steps": [{"type": "move_entity", "entity": "elder", "x": 10, "y": 10}]}])
cc.play_cutscene("intro")
try:
    cc.update(0.016)
    print("B) update ran")
except AttributeError as exc:
    print("B) CutsceneController.update raised:", exc)
    defects.append("B: cutscene move_entity crashes the frame")

print("DEFECTS REPRODUCED:" if defects else "not reproduced", defects)
sys.exit(1 if defects else 0)

