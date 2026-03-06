import pytest
import json
from pathlib import Path

from engine.scene_loader import SceneLoader
from engine.ui import maybe_enqueue_quest_progress_toast
from engine.validators.transition_validator import TransitionValidator
from tests._variant_contracts import _StubWindow



pytestmark = pytest.mark.builtin_behaviours

def test_act1_chapter2_slice_world_and_scenes_validate_strict() -> None:
    world_path = Path("worlds/act1_chapter2_stub.json")
    assert world_path.exists()
    world = json.loads(world_path.read_text(encoding="utf-8"))
    assert isinstance(world, dict)

    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    assert world.get("start_scene") == "act1_chapter2_stub"
    assert set(scenes.keys()) == {
        "act1_chapter2_stub",
        "act1_chapter2_camp",
        "act1_chapter2_ambush",
        "act1_chapter2_ruined_gate",
        "act1_chapter3_stub",
    }

    loader = SceneLoader()
    for scene_key in [
        "act1_chapter2_stub",
        "act1_chapter2_camp",
        "act1_chapter2_ambush",
        "act1_chapter2_ruined_gate",
        "act1_chapter3_stub",
    ]:
        entry = scenes.get(scene_key)
        assert isinstance(entry, dict)
        path_str = entry.get("path")
        assert isinstance(path_str, str)
        assert path_str
        report = loader.validate_scene_file(path_str, strict=True)
        assert report.ok, f"{scene_key} invalid: {report.errors}"

    tv = TransitionValidator(strict=True)
    assert tv.validate(world_path) is True


def test_act1_chapter2_ruined_gate_quest_chain_gating_and_idempotency() -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()

    q_switch = "quest_act1_ch2_ruin_switch"
    q_route = "quest_act1_ch2_ruin_route"
    assert q_switch in qm._definitions
    assert q_route in qm._definitions

    # Initialize HUD quest toast state.
    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    gold_start = window.get_counter("gold", 0.0)

    # Gate: cannot start until Chapter 2 has begun.
    window.emit_signal("entered_zone", zone="RuinedGateStartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_switch) is False
    assert qm.is_quest_completed(q_switch) is False
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False
    assert window.get_counter("gold", 0.0) == gold_start

    # Start switch quest.
    window.set_flag("act1_chapter2_started", True)
    window.emit_signal("entered_zone", zone="RuinedGateStartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_switch) is True
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Find the switch at the ruined gate."]
    window.player_hud.toasts.clear()

    # Early goal attempt does nothing before unlock.
    gold_before_unlock = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="RuinedGateGoalZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_route) is False
    assert qm.is_quest_completed(q_route) is False
    assert window.get_flag("act1_ch2_ruin_unlocked") is False
    assert window.get_flag("act1_ch2_ruin_complete") is False
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False
    assert window.get_counter("gold", 0.0) == gold_before_unlock

    # Unlock event: completes switch quest and starts route quest on the same event.
    window.emit_signal("act1_ch2_ruin_unlock", actor="Player")
    assert qm.is_quest_completed(q_switch) is True
    assert window.get_flag("act1_ch2_ruin_unlocked") is True
    assert window.get_counter("gold", 0.0) == gold_before_unlock + 5.0

    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [
        "Act 1: The ruined gate unlocks.",
        "Act 1: Pass through to the marker.",
    ]
    window.player_hud.toasts.clear()

    # Payoff zone completes the route quest.
    gold_before_goal = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="RuinedGateGoalZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q_route) is True
    assert window.get_flag("act1_ch2_ruin_complete") is True
    assert window.get_counter("gold", 0.0) == gold_before_goal + 15.0

    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Ruined gate secured."]

    # Idempotent on re-entry.
    gold_after = window.get_counter("gold", 0.0)
    window.player_hud.toasts.clear()
    window.emit_signal("entered_zone", zone="RuinedGateGoalZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    # Still idempotent after definitions reload.
    qm.load_definitions()
    window.emit_signal("act1_ch2_ruin_unlock", actor="Player")
    window.emit_signal("entered_zone", zone="RuinedGateGoalZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False


def test_act1_chapter2_stub_has_toruinedgate_transition_targeting_scene_file() -> None:
    stub_scene = json.loads(Path("packs/core_regions/scenes/Act1_Chapter2_Stub.json").read_text(encoding="utf-8"))
    entities = stub_scene.get("entities")
    assert isinstance(entities, list)

    to_gate = [e for e in entities if isinstance(e, dict) and e.get("name") == "ToRuinedGate"]
    assert len(to_gate) == 1

    cfg = to_gate[0].get("behaviour_config")
    assert isinstance(cfg, dict)
    st = cfg.get("SceneTransition")
    assert isinstance(st, dict)
    assert st.get("target_scene") == "packs/core_regions/scenes/Act1_Chapter2_RuinedGate.json"


def test_act1_chapter2_ruined_gate_has_returndoor_back_to_stub() -> None:
    gate_scene = json.loads(
        Path("packs/core_regions/scenes/Act1_Chapter2_RuinedGate.json").read_text(encoding="utf-8")
    )
    entities = gate_scene.get("entities")
    assert isinstance(entities, list)

    return_door = [e for e in entities if isinstance(e, dict) and e.get("name") == "ReturnDoor"]
    assert len(return_door) == 1

    cfg = return_door[0].get("behaviour_config")
    assert isinstance(cfg, dict)
    st = cfg.get("SceneTransition")
    assert isinstance(st, dict)
    assert st.get("target_scene") == "packs/core_regions/scenes/Act1_Chapter2_Stub.json"


def test_act1_chapter2_ruined_gate_has_choice_and_depart_zones() -> None:
    gate_scene = json.loads(
        Path("packs/core_regions/scenes/Act1_Chapter2_RuinedGate.json").read_text(encoding="utf-8")
    )
    entities = gate_scene.get("entities")
    assert isinstance(entities, list)

    names = {e.get("name") for e in entities if isinstance(e, dict)}
    assert "Ch2ChoiceAZone" in names
    assert "Ch2GoalAZone" in names
    assert "Ch2ChoiceBZone" in names
    assert "Ch2GoalBZone" in names
    assert "Ch2DepartZone" in names


def test_act1_chapter2_branching_choice_a_excludes_b_and_reconverges() -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()

    q_a = "quest_act1_ch2_choice_a"
    q_b = "quest_act1_ch2_choice_b"
    q_depart_a = "quest_act1_ch2_complete_a"
    q_depart_b = "quest_act1_ch2_complete_b"
    assert q_a in qm._definitions
    assert q_b in qm._definitions
    assert q_depart_a in qm._definitions
    assert q_depart_b in qm._definitions

    # Gate the branching behind the puzzle-lite payoff.
    window.set_flag("act1_ch2_ruin_complete", True)

    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    gold0 = window.get_counter("gold", 0.0)

    # Choose A.
    window.emit_signal("entered_zone", zone="Ch2ChoiceAZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_a) is True
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Choose Path A."]
    window.player_hud.toasts.clear()

    window.emit_signal("entered_zone", zone="Ch2GoalAZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q_a) is True
    assert window.get_flag("act1_ch2_choice_a_done") is True
    assert window.get_counter("gold", 0.0) == gold0 + 10.0

    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [
        "Act 1: Path A secured.",
        "Act 1: Head to the exit.",
    ]
    window.player_hud.toasts.clear()

    # Mutual exclusion: B cannot start after A is done.
    window.emit_signal("entered_zone", zone="Ch2ChoiceBZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_b) is False
    assert qm.is_quest_completed(q_b) is False
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    # Reconverge and set chapter2-complete exactly once.
    gold_before_depart = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="Ch2DepartZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_chapter2_complete") is True
    assert window.get_counter("gold", 0.0) == gold_before_depart + 20.0

    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Chapter 2 complete."]

    gold_after = window.get_counter("gold", 0.0)
    window.player_hud.toasts.clear()
    window.emit_signal("entered_zone", zone="Ch2DepartZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    # Still idempotent after definitions reload.
    qm.load_definitions()
    window.emit_signal("entered_zone", zone="Ch2DepartZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False


def test_act1_chapter2_branching_choice_b_excludes_a_and_reconverges() -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()

    q_a = "quest_act1_ch2_choice_a"
    q_b = "quest_act1_ch2_choice_b"
    assert q_a in qm._definitions
    assert q_b in qm._definitions

    window.set_flag("act1_ch2_ruin_complete", True)
    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    gold0 = window.get_counter("gold", 0.0)

    # Choose B.
    window.emit_signal("entered_zone", zone="Ch2ChoiceBZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_b) is True
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Choose Path B."]
    window.player_hud.toasts.clear()

    window.emit_signal("entered_zone", zone="Ch2GoalBZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q_b) is True
    assert window.get_flag("act1_ch2_choice_b_done") is True
    assert window.get_counter("gold", 0.0) == gold0 + 10.0

    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == [
        "Act 1: Path B secured.",
        "Act 1: Head to the exit.",
    ]
    window.player_hud.toasts.clear()

    # Mutual exclusion: A cannot start after B is done.
    window.emit_signal("entered_zone", zone="Ch2ChoiceAZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_a) is False
    assert qm.is_quest_completed(q_a) is False
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    # Reconverge completion.
    gold_before_depart = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="Ch2DepartZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_chapter2_complete") is True
    assert window.get_counter("gold", 0.0) == gold_before_depart + 20.0

    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Chapter 2 complete."]
