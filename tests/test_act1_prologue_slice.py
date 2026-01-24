import pytest
import json
from pathlib import Path

from engine.scene_loader import SceneLoader
from engine.ui import maybe_enqueue_quest_progress_toast
from engine.validators.transition_validator import TransitionValidator
from tests._variant_contracts import _StubWindow



pytestmark = pytest.mark.builtin_behaviours

def _complete_act1_prologue_chain(window: _StubWindow) -> None:
    window.emit_signal("entered_zone", zone="PrologueStep1StartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="PrologueStep1CompleteZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="PrologueStep2StartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="PrologueStep2CompleteZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="PrologueStep3CompleteZone", actor="Player", position=(0.0, 0.0))


def test_act1_prologue_world_and_scenes_validate_strict() -> None:
    world_path = Path("worlds/act1_prologue.json")
    assert world_path.exists()
    world = json.loads(world_path.read_text(encoding="utf-8"))
    assert isinstance(world, dict)

    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    assert world.get("start_scene") == "act1_prologue_exterior"
    assert set(scenes.keys()) == {
        "act1_prologue_exterior",
        "act1_prologue_cabin",
        "act1_prologue_fork",
        "act1_prologue_convergence",
        "act1_chapter1_stub",
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


def test_act1_prologue_quest_chain_progression_and_gating() -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()

    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    q1 = "quest_prologue_step1"
    q2 = "quest_prologue_step2"
    q3 = "quest_prologue_step3"
    assert q1 in qm._definitions
    assert q2 in qm._definitions
    assert q3 in qm._definitions

    gold_start = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="PrologueStep3CompleteZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q3) is False
    assert qm.is_quest_completed(q3) is False
    assert window.get_flag("prologue_step3_complete") is False
    assert window.get_counter("gold", 0.0) == gold_start

    window.emit_signal("entered_zone", zone="PrologueStep2StartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q2) is False
    assert qm.is_quest_completed(q2) is False

    window.emit_signal("entered_zone", zone="PrologueStep1StartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q1) is True
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Prologue: Follow the path to the cabin."]

    window.emit_signal("entered_zone", zone="PrologueStep1CompleteZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q1) is True
    assert window.get_flag("prologue_step1_complete") is True
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [
        "Prologue: Follow the path to the cabin.",
        "Prologue: Cabin reached - head inside.",
    ]

    window.emit_signal("entered_zone", zone="PrologueStep2StartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q2) is True
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [
        "Prologue: Follow the path to the cabin.",
        "Prologue: Cabin reached - head inside.",
        "Prologue: Inside the cabin, light the hearth.",
    ]

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="PrologueStep2CompleteZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q2) is True
    assert window.get_flag("prologue_step2_complete") is True
    assert window.get_counter("gold", 0.0) == gold_before + 15.0

    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert qm.is_quest_active(q3) is True
    assert qm.is_quest_completed(q3) is False
    assert window.player_hud.toasts == [
        "Prologue: Follow the path to the cabin.",
        "Prologue: Cabin reached - head inside.",
        "Prologue: Inside the cabin, light the hearth.",
        "Prologue: Hearth lit - warmth returns.",
        "Prologue: Return to the trailhead.",
    ]

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="PrologueStep3CompleteZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q3) is True
    assert window.get_flag("prologue_step3_complete") is True
    assert window.get_counter("gold", 0.0) == gold_before + 10.0
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [
        "Prologue: Follow the path to the cabin.",
        "Prologue: Cabin reached - head inside.",
        "Prologue: Inside the cabin, light the hearth.",
        "Prologue: Hearth lit - warmth returns.",
        "Prologue: Return to the trailhead.",
        "Prologue: Trailhead reached - prologue complete.",
    ]


def test_act1_prologue_rewards_are_idempotent_on_reentry_and_reload() -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()

    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    window.emit_signal("entered_zone", zone="PrologueStep1StartZone", actor="Player", position=(0.0, 0.0))
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Prologue: Follow the path to the cabin."]

    window.emit_signal("entered_zone", zone="PrologueStep1CompleteZone", actor="Player", position=(0.0, 0.0))
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [
        "Prologue: Follow the path to the cabin.",
        "Prologue: Cabin reached - head inside.",
    ]

    window.emit_signal("entered_zone", zone="PrologueStep2StartZone", actor="Player", position=(0.0, 0.0))
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [
        "Prologue: Follow the path to the cabin.",
        "Prologue: Cabin reached - head inside.",
        "Prologue: Inside the cabin, light the hearth.",
    ]

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="OptionalNoteZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("prologue_note_found") is True
    assert window.get_counter("gold", 0.0) == gold_before + 5.0
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False
    assert window.get_counter("gold", 0.0) == gold_before + 5.0

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="PrologueStep2CompleteZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_before + 15.0

    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [
        "Prologue: Follow the path to the cabin.",
        "Prologue: Cabin reached - head inside.",
        "Prologue: Inside the cabin, light the hearth.",
        "Prologue: Hearth lit - warmth returns.",
        "Prologue: Return to the trailhead.",
    ]

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="PrologueStep3CompleteZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_before + 10.0
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [
        "Prologue: Follow the path to the cabin.",
        "Prologue: Cabin reached - head inside.",
        "Prologue: Inside the cabin, light the hearth.",
        "Prologue: Hearth lit - warmth returns.",
        "Prologue: Return to the trailhead.",
        "Prologue: Trailhead reached - prologue complete.",
    ]

    gold_after = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="OptionalNoteZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="PrologueStep2CompleteZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="PrologueStep3CompleteZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    qm.load_definitions()
    window.emit_signal("entered_zone", zone="PrologueStep1StartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="PrologueStep1CompleteZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="PrologueStep2StartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="OptionalNoteZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="PrologueStep2CompleteZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="PrologueStep3CompleteZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False
    assert window.player_hud.toasts == [
        "Prologue: Follow the path to the cabin.",
        "Prologue: Cabin reached - head inside.",
        "Prologue: Inside the cabin, light the hearth.",
        "Prologue: Hearth lit - warmth returns.",
        "Prologue: Return to the trailhead.",
        "Prologue: Trailhead reached - prologue complete.",
    ]


def test_act1_prologue_optional_note_is_blocked_after_step3() -> None:
    window = _StubWindow(with_hud=False)
    qm = window.game_state_controller.quests
    qm.load_definitions()
    q_optional = "quest_prologue_optional_note"
    assert q_optional in qm._definitions

    gold_start = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="PrologueStep1StartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="PrologueStep1CompleteZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="PrologueStep2StartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="PrologueStep2CompleteZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="PrologueStep3CompleteZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("prologue_step3_complete") is True

    assert window.get_flag("prologue_note_found") is False
    assert qm.is_quest_completed(q_optional) is False
    window.emit_signal("entered_zone", zone="OptionalNoteZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("prologue_note_found") is False
    assert qm.is_quest_completed(q_optional) is False
    assert window.get_counter("gold", 0.0) == gold_start + 25.0


def test_act1_scene3_branching_choice_mutual_exclusion_and_idempotency() -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()
    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    q_a = "quest_act1_route_a"
    q_b = "quest_act1_route_b"
    assert q_a in qm._definitions
    assert q_b in qm._definitions

    gold_start = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="Act1ForkChoiceAZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_a) is False
    assert qm.is_quest_completed(q_a) is False
    assert window.get_counter("gold", 0.0) == gold_start

    _complete_act1_prologue_chain(window)
    assert window.get_flag("prologue_step3_complete") is True
    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    window.emit_signal("entered_zone", zone="Act1ForkChoiceAZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_a) is True
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Take the upper path."]

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="Act1ForkGoalAZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q_a) is True
    assert window.get_flag("act1_route_a_done") is True
    assert window.get_counter("gold", 0.0) == gold_before + 10.0
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [
        "Act 1: Take the upper path.",
        "Act 1: Upper route cleared.",
    ]

    gold_after = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="Act1ForkChoiceBZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_b) is False
    assert qm.is_quest_completed(q_b) is False
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False
    assert window.get_counter("gold", 0.0) == gold_after

    window.emit_signal("entered_zone", zone="Act1ForkGoalAZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    qm.load_definitions()
    window.emit_signal("entered_zone", zone="Act1ForkChoiceAZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="Act1ForkGoalAZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False


def test_act1_scene3_branching_choice_route_b_blocks_route_a() -> None:
    window = _StubWindow(with_hud=False)
    qm = window.game_state_controller.quests
    qm.load_definitions()

    q_a = "quest_act1_route_a"
    q_b = "quest_act1_route_b"
    assert q_a in qm._definitions
    assert q_b in qm._definitions

    _complete_act1_prologue_chain(window)
    assert window.get_flag("prologue_step3_complete") is True

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="Act1ForkChoiceBZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="Act1ForkGoalBZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q_b) is True
    assert window.get_flag("act1_route_b_done") is True
    assert window.get_counter("gold", 0.0) == gold_before + 10.0

    gold_after = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="Act1ForkChoiceAZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="Act1ForkGoalAZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_a) is False
    assert qm.is_quest_completed(q_a) is False
    assert window.get_counter("gold", 0.0) == gold_after


def test_act1_scene4_convergence_after_route_a() -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()
    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    q_route_a = "quest_act1_route_a"
    q_conv_a = "quest_act1_convergence_a"
    q_conv_b = "quest_act1_convergence_b"
    q_ack_a = "quest_act1_ack_route_a"
    q_ack_b = "quest_act1_ack_route_b"
    for qid in (q_route_a, q_conv_a, q_conv_b, q_ack_a, q_ack_b):
        assert qid in qm._definitions

    _complete_act1_prologue_chain(window)
    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    window.emit_signal("entered_zone", zone="Act1ForkChoiceAZone", actor="Player", position=(0.0, 0.0))
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Take the upper path."]
    window.player_hud.toasts.clear()

    window.emit_signal("entered_zone", zone="Act1ForkGoalAZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q_route_a) is True
    assert window.get_flag("act1_route_a_done") is True
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Upper route cleared."]
    window.player_hud.toasts.clear()

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="ConvergenceStartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_conv_a) is True
    assert qm.is_quest_active(q_conv_b) is False
    assert window.get_flag("act1_ack_route_a") is True
    assert window.get_flag("act1_ack_route_b") is False
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [
        "Act 1: Routes converge - reach the crossroads.",
    ]
    assert window.get_counter("gold", 0.0) == gold_before

    window.emit_signal("entered_zone", zone="ConvergenceGoalZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_convergence_complete") is True
    assert window.get_counter("gold", 0.0) == gold_before + 20.0
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [
        "Act 1: Routes converge - reach the crossroads.",
        "Act 1: Crossroads reached.",
        "Act 1: Continue onward.",
    ]

    gold_after = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="ConvergenceStartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="ConvergenceGoalZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    qm.load_definitions()
    window.emit_signal("entered_zone", zone="ConvergenceStartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="ConvergenceGoalZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False


def test_act1_scene4_convergence_after_route_b_blocks_route_a_convergence() -> None:
    window = _StubWindow(with_hud=False)
    qm = window.game_state_controller.quests
    qm.load_definitions()

    q_route_b = "quest_act1_route_b"
    q_conv_a = "quest_act1_convergence_a"
    q_conv_b = "quest_act1_convergence_b"
    q_ack_a = "quest_act1_ack_route_a"
    q_ack_b = "quest_act1_ack_route_b"
    for qid in (q_route_b, q_conv_a, q_conv_b, q_ack_a, q_ack_b):
        assert qid in qm._definitions

    _complete_act1_prologue_chain(window)
    window.emit_signal("entered_zone", zone="Act1ForkChoiceBZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="Act1ForkGoalBZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q_route_b) is True
    assert window.get_flag("act1_route_b_done") is True

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="ConvergenceStartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_conv_b) is True
    assert qm.is_quest_active(q_conv_a) is False
    assert window.get_flag("act1_ack_route_b") is True
    assert window.get_flag("act1_ack_route_a") is False
    assert window.get_counter("gold", 0.0) == gold_before

    window.emit_signal("entered_zone", zone="ConvergenceGoalZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_convergence_complete") is True
    assert window.get_counter("gold", 0.0) == gold_before + 20.0


def test_act1_scene4_handoff_quest_gating_and_idempotency() -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()
    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    q_handoff = "quest_act1_prologue_complete"
    assert q_handoff in qm._definitions

    gold_start = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="Act1HandoffZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_handoff) is False
    assert qm.is_quest_completed(q_handoff) is False
    assert window.get_flag("act1_prologue_complete") is False
    assert window.get_counter("gold", 0.0) == gold_start
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    _complete_act1_prologue_chain(window)
    window.emit_signal("entered_zone", zone="Act1ForkChoiceAZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="Act1ForkGoalAZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="ConvergenceStartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="ConvergenceGoalZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_convergence_complete") is True

    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts[-1] == "Act 1: Continue onward."

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="Act1HandoffZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q_handoff) is True
    assert window.get_flag("act1_prologue_complete") is True
    assert window.get_counter("gold", 0.0) == gold_before + 5.0
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts[-1] == "Act 1: Prologue complete."

    gold_after = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="Act1HandoffZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    qm.load_definitions()
    window.emit_signal("entered_zone", zone="Act1HandoffZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False


def test_act1_chapter1_stub_world_and_scene_validate_strict() -> None:
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


def test_act1_chapter1_start_quest_gating_and_idempotency() -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()
    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    q_ch1 = "quest_act1_chapter1_start"
    assert q_ch1 in qm._definitions

    gold_start = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="Chapter1StartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_ch1) is False
    assert qm.is_quest_completed(q_ch1) is False
    assert window.get_flag("act1_chapter1_started") is False
    assert window.get_counter("gold", 0.0) == gold_start
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    _complete_act1_prologue_chain(window)
    window.emit_signal("entered_zone", zone="Act1ForkChoiceAZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="Act1ForkGoalAZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="ConvergenceStartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="ConvergenceGoalZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="Act1HandoffZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_prologue_complete") is True
    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="Chapter1StartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_ch1) is True
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Chapter 1 begins."]
    window.player_hud.toasts.clear()

    window.emit_signal("entered_zone", zone="Chapter1CheckpointZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q_ch1) is True
    assert window.get_flag("act1_chapter1_started") is True
    assert window.get_counter("gold", 0.0) == gold_before + 5.0
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: First steps taken."]

    gold_after = window.get_counter("gold", 0.0)
    window.player_hud.toasts.clear()
    window.emit_signal("entered_zone", zone="Chapter1CheckpointZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    qm.load_definitions()
    window.emit_signal("entered_zone", zone="Chapter1StartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="Chapter1CheckpointZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False
