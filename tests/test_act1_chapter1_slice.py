import json
from pathlib import Path

import pytest

from engine.scene_loader import SceneLoader
from engine.ui import maybe_enqueue_quest_progress_toast
from engine.validators.transition_validator import TransitionValidator
from tests._variant_contracts import _StubWindow

pytestmark = pytest.mark.builtin_behaviours

def _complete_to_act1_chapter1_started(window: _StubWindow) -> None:
    window.set_flag("act1_prologue_complete", True)
    window.emit_signal("entered_zone", zone="Chapter1StartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="Chapter1CheckpointZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_chapter1_started") is True


def _complete_to_act1_ch1_gate_complete(window: _StubWindow) -> None:
    _complete_to_act1_chapter1_started(window)
    window.emit_signal("entered_zone", zone="GatePathStartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("act1_ch1_gate_unlock", actor="Player")
    window.emit_signal("entered_zone", zone="GatePathGoalZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_ch1_gate_complete") is True


def _complete_to_act1_ch1_arrival_complete(window: _StubWindow) -> None:
    _complete_to_act1_ch1_gate_complete(window)
    window.emit_signal("entered_zone", zone="ClearingStartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="ClearingGoalZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_ch1_arrival_complete") is True


def test_act1_chapter1_world_and_scenes_validate_strict() -> None:
    world_path = Path("worlds/act1_chapter1_stub.json")
    assert world_path.exists()
    world = json.loads(world_path.read_text(encoding="utf-8"))
    assert isinstance(world, dict)

    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    assert world.get("start_scene") == "act1_chapter1_stub"
    assert set(scenes.keys()) == {
        "act1_chapter1_stub",
        "act1_chapter1_gatepath",
        "act1_chapter1_clearing",
        "act1_chapter1_overlook",
        "act1_chapter2_stub",
    }

    loader = SceneLoader()
    for scene_id, entry in scenes.items():
        assert isinstance(entry, dict)
        path_str = entry.get("path")
        assert isinstance(path_str, str)
        assert path_str
        report = loader.validate_scene_file(path_str, strict=True)
        assert report.ok, f"{scene_id} invalid: {report.errors}"

    tv = TransitionValidator(strict=True)
    assert tv.validate(world_path) is True


def test_act1_chapter1_world_entrypoint_validate_strict() -> None:
    world_path = Path("worlds/act1_chapter1.json")
    assert world_path.exists()
    world = json.loads(world_path.read_text(encoding="utf-8"))
    assert isinstance(world, dict)

    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    assert world.get("start_scene") == "act1_chapter1_stub"
    assert set(scenes.keys()) == {
        "act1_chapter1_stub",
        "act1_chapter1_gatepath",
        "act1_chapter1_clearing",
        "act1_chapter1_overlook",
        "act1_chapter2_stub",
    }

    loader = SceneLoader()
    for scene_id, entry in scenes.items():
        assert isinstance(entry, dict)
        path_str = entry.get("path")
        assert isinstance(path_str, str)
        assert path_str
        report = loader.validate_scene_file(path_str, strict=True)
        assert report.ok, f"{scene_id} invalid: {report.errors}"

    tv = TransitionValidator(strict=True)
    assert tv.validate(world_path) is True


def test_act1_chapter1_puzzle_lite_gate_chain_and_idempotency() -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()

    q_switch = "quest_act1_ch1_gate_switch"
    q_route = "quest_act1_ch1_gate_route"
    q_arrival = "quest_act1_ch1_arrival"
    assert q_switch in qm._definitions
    assert q_route in qm._definitions
    assert q_arrival in qm._definitions

    gatepath_scene = json.loads(Path("packs/core_regions/scenes/Act1_Chapter1_GatePath.json").read_text(encoding="utf-8"))
    entities = gatepath_scene.get("entities")
    assert isinstance(entities, list)
    to_clearing = [e for e in entities if isinstance(e, dict) and e.get("name") == "ToClearing"]
    assert len(to_clearing) == 1
    cfg = to_clearing[0].get("behaviour_config")
    assert isinstance(cfg, dict)
    st = cfg.get("SceneTransition")
    assert isinstance(st, dict)
    assert st.get("target_scene") == "packs/core_regions/scenes/Act1_Chapter1_Clearing.json"

    clearing_scene = json.loads(Path("packs/core_regions/scenes/Act1_Chapter1_Clearing.json").read_text(encoding="utf-8"))
    entities = clearing_scene.get("entities")
    assert isinstance(entities, list)
    to_overlook = [e for e in entities if isinstance(e, dict) and e.get("name") == "ToOverlook"]
    assert len(to_overlook) == 1
    cfg = to_overlook[0].get("behaviour_config")
    assert isinstance(cfg, dict)
    st = cfg.get("SceneTransition")
    assert isinstance(st, dict)
    assert st.get("target_scene") == "packs/core_regions/scenes/Act1_Chapter1_Overlook.json"

    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    gold_start = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="GatePathStartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_switch) is False
    assert qm.is_quest_completed(q_switch) is False
    assert window.get_flag("act1_ch1_gate_unlocked") is False
    assert window.get_counter("gold", 0.0) == gold_start

    window.emit_signal("entered_zone", zone="ClearingStartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_arrival) is False
    assert qm.is_quest_completed(q_arrival) is False

    _complete_to_act1_chapter1_started(window)
    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    window.emit_signal("entered_zone", zone="GatePathGoalZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_route) is False
    assert qm.is_quest_completed(q_route) is False
    assert window.get_flag("act1_ch1_gate_complete") is False

    window.emit_signal("entered_zone", zone="GatePathStartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_switch) is True
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Activate the gate switch."]
    window.player_hud.toasts.clear()

    window.emit_signal("act1_ch1_gate_unlock", actor="Player")
    assert qm.is_quest_completed(q_switch) is True
    assert window.get_flag("act1_ch1_gate_unlocked") is True
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [
        "Act 1: Gate unlocked.",
        "Act 1: Proceed beyond the gate.",
    ]
    window.player_hud.toasts.clear()

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="GatePathGoalZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q_route) is True
    assert window.get_flag("act1_ch1_gate_complete") is True
    assert window.get_counter("gold", 0.0) == gold_before + 15.0
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Gate path cleared."]

    window.player_hud.toasts.clear()
    gold_clearing_start = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="ClearingStartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_arrival) is True
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Follow the path into the clearing."]
    window.player_hud.toasts.clear()

    window.emit_signal("entered_zone", zone="ClearingGoalZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q_arrival) is True
    assert window.get_flag("act1_ch1_arrival_complete") is True
    assert window.get_counter("gold", 0.0) == gold_clearing_start + 20.0
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: The clearing opens ahead."]

    gold_after_arrival = window.get_counter("gold", 0.0)
    window.player_hud.toasts.clear()
    window.emit_signal("entered_zone", zone="ClearingGoalZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after_arrival
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    qm.load_definitions()
    window.emit_signal("entered_zone", zone="ClearingStartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="ClearingGoalZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after_arrival
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    gold_after = window.get_counter("gold", 0.0)
    window.player_hud.toasts.clear()
    window.emit_signal("entered_zone", zone="GatePathGoalZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False


def test_act1_chapter1_clearing_choice_a_blocks_b_and_depart_idempotent() -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()

    q_a = "quest_act1_ch1_choice_a"
    q_b = "quest_act1_ch1_choice_b"
    q_depart_a = "quest_act1_ch1_depart_a"
    q_depart_b = "quest_act1_ch1_depart_b"
    assert q_a in qm._definitions
    assert q_b in qm._definitions
    assert q_depart_a in qm._definitions
    assert q_depart_b in qm._definitions

    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    # Cannot start choice quests before arrival complete
    window.emit_signal("entered_zone", zone="ClearingChoiceAZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_a) is False
    assert qm.is_quest_completed(q_a) is False

    _complete_to_act1_ch1_arrival_complete(window)
    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="ClearingChoiceAZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_a) is True
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Take the upper trail."]
    window.player_hud.toasts.clear()

    window.emit_signal("entered_zone", zone="ClearingGoalAZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q_a) is True
    assert window.get_flag("act1_ch1_choice_a_done") is True
    assert window.get_counter("gold", 0.0) == gold_before + 10.0
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [
        "Act 1: Upper trail secured.",
        "Act 1: Head for the exit.",
    ]
    window.player_hud.toasts.clear()

    # Choice B should not start after A is done
    window.emit_signal("entered_zone", zone="ClearingChoiceBZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_b) is False
    assert qm.is_quest_completed(q_b) is False

    # Depart should trigger only for the chosen path (A)
    window.emit_signal("entered_zone", zone="ClearingGoalBZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_depart_b) is False
    assert qm.is_quest_completed(q_depart_b) is False

    gold_depart_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="ClearingDepartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q_depart_a) is True
    assert window.get_flag("act1_ch1_depart_complete") is True
    assert window.get_counter("gold", 0.0) == gold_depart_before + 15.0

    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Ready to move on."]

    gold_after = window.get_counter("gold", 0.0)
    window.player_hud.toasts.clear()
    window.emit_signal("entered_zone", zone="ClearingDepartZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    qm.load_definitions()
    window.emit_signal("entered_zone", zone="ClearingChoiceAZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="ClearingGoalAZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="ClearingDepartZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False


def test_act1_chapter1_clearing_choice_b_blocks_a_and_depart_idempotent() -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()

    q_a = "quest_act1_ch1_choice_a"
    q_b = "quest_act1_ch1_choice_b"
    q_depart_a = "quest_act1_ch1_depart_a"
    q_depart_b = "quest_act1_ch1_depart_b"
    assert q_a in qm._definitions
    assert q_b in qm._definitions
    assert q_depart_a in qm._definitions
    assert q_depart_b in qm._definitions

    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    _complete_to_act1_ch1_arrival_complete(window)
    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="ClearingChoiceBZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_b) is True
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Take the lower trail."]
    window.player_hud.toasts.clear()

    window.emit_signal("entered_zone", zone="ClearingGoalBZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q_b) is True
    assert window.get_flag("act1_ch1_choice_b_done") is True
    assert window.get_counter("gold", 0.0) == gold_before + 10.0
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [
        "Act 1: Lower trail secured.",
        "Act 1: Head for the exit.",
    ]
    window.player_hud.toasts.clear()

    # Choice A should not start after B is done
    window.emit_signal("entered_zone", zone="ClearingChoiceAZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_a) is False
    assert qm.is_quest_completed(q_a) is False

    # Depart should trigger only for the chosen path (B)
    window.emit_signal("entered_zone", zone="ClearingGoalAZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_depart_a) is False
    assert qm.is_quest_completed(q_depart_a) is False

    gold_depart_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="ClearingDepartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q_depart_b) is True
    assert window.get_flag("act1_ch1_depart_complete") is True
    assert window.get_counter("gold", 0.0) == gold_depart_before + 15.0

    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Ready to move on."]

    gold_after = window.get_counter("gold", 0.0)
    window.player_hud.toasts.clear()
    window.emit_signal("entered_zone", zone="ClearingDepartZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False


def test_act1_chapter1_complete_quest_overlook_gating_and_idempotency() -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()

    q_complete = "quest_act1_ch1_complete"
    assert q_complete in qm._definitions

    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    # Cannot start before depart is complete
    window.emit_signal("entered_zone", zone="OverlookStartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_complete) is False
    assert qm.is_quest_completed(q_complete) is False
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    # Complete depart via path A (includes gate/arrival/choice/depart)
    _complete_to_act1_ch1_arrival_complete(window)
    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    window.emit_signal("entered_zone", zone="ClearingChoiceAZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="ClearingGoalAZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="ClearingDepartZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_ch1_depart_complete") is True
    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="OverlookStartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_complete) is True
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Press onward to the overlook."]
    window.player_hud.toasts.clear()

    window.emit_signal("entered_zone", zone="OverlookGoalZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q_complete) is True
    assert window.get_flag("act1_chapter1_complete") is True
    assert window.get_counter("gold", 0.0) == gold_before + 20.0
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Chapter 1 complete."]

    gold_after = window.get_counter("gold", 0.0)
    window.player_hud.toasts.clear()
    window.emit_signal("entered_zone", zone="OverlookGoalZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    qm.load_definitions()
    window.emit_signal("entered_zone", zone="OverlookStartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="OverlookGoalZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    qm.load_definitions()
    window.emit_signal("entered_zone", zone="ClearingChoiceBZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="ClearingGoalBZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="ClearingDepartZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    qm.load_definitions()
    window.emit_signal("act1_ch1_gate_unlock", actor="Player")
    window.emit_signal("entered_zone", zone="GatePathGoalZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

