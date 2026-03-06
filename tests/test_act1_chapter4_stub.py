import pytest
import json
from pathlib import Path

from engine.scene_loader import SceneLoader
from engine.ui import maybe_enqueue_quest_progress_toast
from engine.validators.transition_validator import TransitionValidator
from tests._variant_contracts import _StubWindow



pytestmark = pytest.mark.builtin_behaviours

def test_act1_chapter4_stub_world_and_scene_validate_strict() -> None:
    world_path = Path("worlds/act1_chapter4_stub.json")
    assert world_path.exists()
    world = json.loads(world_path.read_text(encoding="utf-8"))
    assert isinstance(world, dict)

    scenes = world.get("scenes")
    assert isinstance(scenes, dict)
    assert world.get("start_scene") == "act1_chapter4_stub"
    assert set(scenes.keys()) == {
        "act1_chapter4_stub",
        "act1_chapter4_bastion",
        "act1_chapter4_fork",
        "act1_chapter5_stub",
        "act1_chapter3_stub",
    }

    loader = SceneLoader()
    for scene_key in [
        "act1_chapter4_stub",
        "act1_chapter4_bastion",
        "act1_chapter4_fork",
        "act1_chapter5_stub",
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


def test_act1_chapter4_start_quest_gating_and_idempotency() -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()

    q_ch4 = "quest_act1_chapter4_start"
    assert q_ch4 in qm._definitions

    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    gold_start = window.get_counter("gold", 0.0)

    # Cannot start before Chapter 3 completion.
    window.emit_signal("entered_zone", zone="Chapter4StartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_ch4) is False
    assert qm.is_quest_completed(q_ch4) is False
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False
    assert window.get_counter("gold", 0.0) == gold_start

    # Once Chapter 3 is complete, entering Chapter4StartZone starts the quest.
    window.set_flag("act1_chapter3_complete", True)
    window.emit_signal("entered_zone", zone="Chapter4StartZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_active(q_ch4) is True
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Chapter 4 begins."]
    window.player_hud.toasts.clear()

    gold_before = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="Chapter4CheckpointZone", actor="Player", position=(0.0, 0.0))
    assert qm.is_quest_completed(q_ch4) is True
    assert window.get_flag("act1_chapter4_started") is True
    assert window.get_counter("gold", 0.0) == gold_before + 10.0

    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is True
    assert window.player_hud.toasts == ["Act 1: Chapter 4 underway."]

    gold_after = window.get_counter("gold", 0.0)
    window.player_hud.toasts.clear()
    window.emit_signal("entered_zone", zone="Chapter4CheckpointZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    # Still idempotent after definitions reload.
    qm.load_definitions()
    window.emit_signal("entered_zone", zone="Chapter4StartZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="Chapter4CheckpointZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False


def test_act1_chapter3_stub_has_tochapter4_transition() -> None:
    ch3_scene = json.loads(Path("packs/core_regions/scenes/Act1_Chapter3_Stub.json").read_text(encoding="utf-8"))
    entities = ch3_scene.get("entities")
    assert isinstance(entities, list)

    to_ch4 = [e for e in entities if isinstance(e, dict) and e.get("name") == "ToChapter4"]
    assert len(to_ch4) == 1

    cfg = to_ch4[0].get("behaviour_config")
    assert isinstance(cfg, dict)
    st = cfg.get("SceneTransition")
    assert isinstance(st, dict)
    assert st.get("target_scene") == "packs/core_regions/scenes/Act1_Chapter4_Stub.json"
