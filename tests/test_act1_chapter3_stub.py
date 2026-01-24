import pytest
import json
from pathlib import Path

from engine.scene_loader import SceneLoader
from engine.ui import maybe_enqueue_quest_progress_toast
from engine.validators.transition_validator import TransitionValidator
from tests._variant_contracts import _StubWindow



pytestmark = pytest.mark.builtin_behaviours

def test_act1_chapter3_stub_world_and_scene_validate_strict() -> None:
    world_path = Path("worlds/act1_chapter3_stub.json")
    assert world_path.exists()
    world = json.loads(world_path.read_text(encoding="utf-8"))
    assert isinstance(world, dict)

    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    assert world.get("start_scene") == "act1_chapter3_stub"
    assert set(scenes.keys()) == {"act1_chapter3_stub", "act1_chapter2_ruined_gate", "act1_chapter4_stub"}

    loader = SceneLoader()
    for scene_key in ["act1_chapter3_stub", "act1_chapter2_ruined_gate", "act1_chapter4_stub"]:
        entry = scenes.get(scene_key)
        assert isinstance(entry, dict)
        path_str = entry.get("path")
        assert isinstance(path_str, str)
        assert path_str
        report = loader.validate_scene_file(path_str, strict=True)
        assert report.ok, f"{scene_key} invalid: {report.errors}"

    tv = TransitionValidator(strict=True)
    assert tv.validate(world_path) is True


def test_act1_chapter3_start_quest_gating_and_idempotency() -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()

    q_ch3 = "quest_act1_chapter3_start"
    assert q_ch3 in qm._definitions

    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    gold_start = window.get_counter("gold", 0.0)

    # Cannot start before Chapter 2 completion.
    window.emit_signal("entered_zone", zone="Chapter3StartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_ch3) is False
    assert qm.is_quest_completed(q_ch3) is False
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False
    assert window.get_counter("gold", 0.0) == gold_start

    # Once Chapter 2 is complete, entering Chapter3StartZone starts the quest.
    window.set_flag("act1_chapter2_complete", True)
    window.emit_signal("entered_zone", zone="Chapter3StartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_ch3) is True
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Chapter 3 begins."]
    window.player_hud.toasts.clear()

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="Chapter3CheckpointZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q_ch3) is True
    assert window.get_flag("act1_chapter3_started") is True
    assert window.get_counter("gold", 0.0) == gold_before + 10.0

    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Chapter 3 underway."]

    gold_after = window.get_counter("gold", 0.0)
    window.player_hud.toasts.clear()
    window.emit_signal("entered_zone", zone="Chapter3CheckpointZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    # Still idempotent after definitions reload.
    qm.load_definitions()
    window.emit_signal("entered_zone", zone="Chapter3StartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="Chapter3CheckpointZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False


def test_act1_chapter2_ruined_gate_has_tochapter3_transition() -> None:
    gate_scene = json.loads(
        Path("packs/core_regions/scenes/Act1_Chapter2_RuinedGate.json").read_text(encoding="utf-8")
    )
    entities = gate_scene.get("entities")
    assert isinstance(entities, list)

    to_ch3 = [e for e in entities if isinstance(e, dict) and e.get("name") == "ToChapter3"]
    assert len(to_ch3) == 1

    cfg = to_ch3[0].get("behaviour_config")
    assert isinstance(cfg, dict)
    st = cfg.get("SceneTransition")
    assert isinstance(st, dict)
    assert st.get("target_scene") == "packs/core_regions/scenes/Act1_Chapter3_Stub.json"
