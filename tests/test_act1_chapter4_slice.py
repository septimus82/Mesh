import pytest
import json
from pathlib import Path

from engine.scene_loader import SceneLoader
from engine.ui import maybe_enqueue_quest_progress_toast
from engine.validators.transition_validator import TransitionValidator
from tests._variant_contracts import _StubWindow



pytestmark = pytest.mark.builtin_behaviours

def _complete_to_act1_chapter4_started(window: _StubWindow) -> None:
    # Chapter 4 start quest requires Chapter 3 completion.
    window.set_flag("act1_chapter3_complete", True)

    maybe_enqueue_quest_progress_toast(window, quest_manager=window.game_state_controller.quests)
    window.player_hud.toasts.clear()

    window.emit_signal("entered_zone", zone="Chapter4StartZone", actor="Player", position=(0.0, 0.0))
    maybe_enqueue_quest_progress_toast(window, quest_manager=window.game_state_controller.quests)
    window.player_hud.toasts.clear()

    window.emit_signal("entered_zone", zone="Chapter4CheckpointZone", actor="Player", position=(0.0, 0.0))
    maybe_enqueue_quest_progress_toast(window, quest_manager=window.game_state_controller.quests)
    window.player_hud.toasts.clear()

    assert window.get_flag("act1_chapter4_started") is True


def test_act1_chapter4_slice_world_and_scenes_validate_strict() -> None:
    world_path = Path("worlds/act1_chapter4_stub.json")
    assert world_path.exists()
    world = json.loads(world_path.read_text(encoding="utf-8"))
    assert isinstance(world, dict)

    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    assert world.get("start_scene") == "act1_chapter4_stub"
    assert set(scenes.keys()) == {"act1_chapter4_stub", "act1_chapter4_fork", "act1_chapter5_stub", "act1_chapter3_stub"}

    loader = SceneLoader()
    for scene_key in ["act1_chapter4_stub", "act1_chapter4_fork", "act1_chapter5_stub", "act1_chapter3_stub"]:
        entry = scenes.get(scene_key)
        assert isinstance(entry, dict)
        path_str = entry.get("path")
        assert isinstance(path_str, str)
        assert path_str
        report = loader.validate_scene_file(path_str, strict=True)
        assert report.ok, f"{scene_key} invalid: {report.errors}"

    tv = TransitionValidator(strict=True)
    assert tv.validate(world_path) is True


def test_act1_chapter4_stub_has_toch4fork_transition() -> None:
    stub_scene = json.loads(Path("packs/core_regions/scenes/Act1_Chapter4_Stub.json").read_text(encoding="utf-8"))
    entities = stub_scene.get("entities")
    assert isinstance(entities, list)

    to_fork = [e for e in entities if isinstance(e, dict) and e.get("name") == "ToCh4Fork"]
    assert len(to_fork) == 1

    cfg = to_fork[0].get("behaviour_config")
    assert isinstance(cfg, dict)
    st = cfg.get("SceneTransition")
    assert isinstance(st, dict)
    assert st.get("target_scene") == "packs/core_regions/scenes/Act1_Chapter4_Fork.json"


def test_act1_chapter4_choice_mutual_exclusion_and_reconverged_completion() -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()

    _complete_to_act1_chapter4_started(window)

    q_a = "quest_act1_ch4_choice_a"
    q_b = "quest_act1_ch4_choice_b"
    q_complete_a = "quest_act1_ch4_complete_a"
    q_complete_b = "quest_act1_ch4_complete_b"

    assert q_a in qm._definitions
    assert q_b in qm._definitions
    assert q_complete_a in qm._definitions
    assert q_complete_b in qm._definitions

    gold_start = window.get_counter("gold", 0.0)

    # Choose A and complete A.
    window.emit_signal("entered_zone", zone="Ch4ChoiceAZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="Ch4GoalAZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_ch4_choice_a_done") is True
    assert window.get_counter("gold", 0.0) == gold_start + 10.0

    gold_after_a = window.get_counter("gold", 0.0)

    # Mutual exclusion: B should not be able to complete after A is done.
    window.emit_signal("entered_zone", zone="Ch4ChoiceBZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="Ch4GoalBZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_ch4_choice_b_done") is False
    assert window.get_counter("gold", 0.0) == gold_after_a

    # Reconverge depart sets single completion flag.
    window.emit_signal("entered_zone", zone="Ch4DepartZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_chapter4_complete") is True
    assert window.get_counter("gold", 0.0) == gold_after_a + 20.0

    gold_after_complete = window.get_counter("gold", 0.0)

    # Idempotent on re-entry.
    window.emit_signal("entered_zone", zone="Ch4DepartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="Ch4GoalAZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after_complete

    # Still idempotent after definitions reload.
    qm.load_definitions()
    window.emit_signal("entered_zone", zone="Ch4DepartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="Ch4ChoiceAZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after_complete


def test_act1_chapter4_choice_b_then_depart_completes_once() -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()

    _complete_to_act1_chapter4_started(window)

    gold_start = window.get_counter("gold", 0.0)

    window.emit_signal("entered_zone", zone="Ch4ChoiceBZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="Ch4GoalBZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_ch4_choice_b_done") is True
    assert window.get_counter("gold", 0.0) == gold_start + 10.0

    gold_after_b = window.get_counter("gold", 0.0)

    # Mutual exclusion: A should not be able to complete after B is done.
    window.emit_signal("entered_zone", zone="Ch4ChoiceAZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="Ch4GoalAZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_ch4_choice_a_done") is False
    assert window.get_counter("gold", 0.0) == gold_after_b

    window.emit_signal("entered_zone", zone="Ch4DepartZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_chapter4_complete") is True
    assert window.get_counter("gold", 0.0) == gold_after_b + 20.0

    gold_after_complete = window.get_counter("gold", 0.0)

    # Idempotent on re-entry.
    window.emit_signal("entered_zone", zone="Ch4DepartZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after_complete
