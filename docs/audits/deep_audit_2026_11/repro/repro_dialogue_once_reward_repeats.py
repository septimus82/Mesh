"""Repro: a Studio-authored conversation marked "Only once" with a reward choice marked "Choice once" pays its
reward again after the room is re-entered (or a save is loaded): the once-memory (Dialogue._has_played,
Dialogue._choice_history) lives only on the behaviour instance, Dialogue has no saveable_state, and the scene loader
builds fresh behaviour instances on every room load (scene_controller_parts/entity_factory._rebuild_behaviours_for_sprite).

This drives engine.behaviours.dialogue.Dialogue directly (two instances = two visits) with a real GameStateController
holding the gold; the dialogue-box UI is bypassed by calling the choice handler the box submits to.
"""
import os
import sys
from types import SimpleNamespace

os.chdir(r"D:\Games\Mesh-audit")
import engine  # noqa: E402
from engine.behaviours.dialogue import Dialogue  # noqa: E402
from engine.game_state_controller import GameStateController  # noqa: E402

print("engine from", engine.__file__)
window = SimpleNamespace(event_bus=None, emit_signal=lambda *a, **k: None)
gs = GameStateController(window)
window.game_state_controller, window.game_state = gs, gs.state
window.set_flag = gs.set_flag
window.inc_counter = lambda name, amount: gs.add_counter(name, amount)

# The shape Studio writes (project_ops.set_conversation(once=True) + set_choice(add_counters=..., once=True)).
config = {"once": True, "dialogue": {"speaker": "Elder", "start": "n1", "nodes": {
    "n1": {"speaker": "Elder", "text": "You saved the village. Take this.",
           "choices": [{"text": "Thank you", "once": True, "inc_counters": {"gold": 50}}]}}}}


def visit(n):
    entity = SimpleNamespace(mesh_name="elder", mesh_entity_data={}, properties={})
    talk = Dialogue(entity, window, **config)  # what each room load builds
    available = talk.can_interact_with(None)
    talk._current_node_id = "n1"
    choice_id = talk._graph_nodes["n1"]["choices"][0]["id"]
    talk._has_played = True
    talk._handle_submitted_choice({"id": choice_id})
    second = talk._choice_is_available(talk._graph_nodes["n1"]["choices"][0])
    print(f"visit {n}: could talk={available}, gold now {gs.get_counter('gold', 0)}, choice still offered this visit={second}")
    return talk


visit(1)
visit(2)  # leave the room and come back (or load a save made after visit 1)
gold = gs.get_counter("gold", 0)
print("DEFECT REPRODUCED: once-only reward paid twice" if gold > 50 else "not reproduced", gold)
sys.exit(1 if gold > 50 else 0)
