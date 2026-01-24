import json
from pathlib import Path

from engine.ui import maybe_enqueue_quest_progress_toast
from tests._variant_contracts import _StubWindow


def _complete_to_act1_chapter3_started(window: _StubWindow) -> None:
    # Chapter 3 start quest requires Chapter 2 completion.
    window.set_flag("act1_chapter2_complete", True)

    # Initialize HUD quest toast state.
    maybe_enqueue_quest_progress_toast(window, quest_manager=window.game_state_controller.quests)
    window.player_hud.toasts.clear()

    window.emit_signal("entered_zone", zone="Chapter3StartZone", actor="Player", position=(0.0, 0.0))
    maybe_enqueue_quest_progress_toast(window, quest_manager=window.game_state_controller.quests)
    window.player_hud.toasts.clear()

    window.emit_signal("entered_zone", zone="Chapter3CheckpointZone", actor="Player", position=(0.0, 0.0))
    maybe_enqueue_quest_progress_toast(window, quest_manager=window.game_state_controller.quests)
    window.player_hud.toasts.clear()

    assert window.get_flag("act1_chapter3_started") is True


def test_act1_chapter3_stub_has_note_and_exit_zones() -> None:
    scene = json.loads(Path("packs/core_regions/scenes/Act1_Chapter3_Stub.json").read_text(encoding="utf-8"))
    entities = scene.get("entities")
    assert isinstance(entities, list)

    names = [e.get("name") for e in entities if isinstance(e, dict)]
    assert "Chapter3NoteZone" in names
    assert "Chapter3ExitZone" in names

    note = [e for e in entities if isinstance(e, dict) and e.get("name") == "Chapter3NoteZone"][0]
    exit_zone = [e for e in entities if isinstance(e, dict) and e.get("name") == "Chapter3ExitZone"][0]

    for e, expected_trigger in [(note, "act1_ch3_note"), (exit_zone, "act1_ch3_exit")]:
        cfg = e.get("behaviour_config")
        assert isinstance(cfg, dict)
        tz = cfg.get("TriggerZone")
        assert isinstance(tz, dict)
        assert tz.get("on_trigger") == expected_trigger


def test_act1_chapter3_note_and_exit_quests_gating_and_idempotency() -> None:
    window = _StubWindow(with_hud=True)
    qm = window.game_state_controller.quests
    qm.load_definitions()

    q_note = "quest_act1_ch3_note"
    q_exit = "quest_act1_ch3_exit"
    assert q_note in qm._definitions
    assert q_exit in qm._definitions

    # Initialize HUD quest toast state.
    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    window.player_hud.toasts.clear()

    gold_start = window.get_counter("gold", 0.0)

    # Gate: note cannot be found until Chapter 3 has started.
    window.emit_signal("entered_zone", zone="Chapter3NoteZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_ch3_note_found") is False
    assert qm.is_quest_completed(q_note) is False
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False
    assert window.get_counter("gold", 0.0) == gold_start

    # Gate: exit cannot complete until the note is found.
    _complete_to_act1_chapter3_started(window)
    gold_after_started = window.get_counter("gold", 0.0)

    window.emit_signal("entered_zone", zone="Chapter3ExitZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_chapter3_complete") is False
    assert qm.is_quest_completed(q_exit) is False
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False
    assert window.get_counter("gold", 0.0) == gold_after_started

    # Find the note.
    window.emit_signal("entered_zone", zone="Chapter3NoteZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_ch3_note_found") is True
    assert qm.is_quest_completed(q_note) is True
    assert window.get_counter("gold", 0.0) == gold_after_started + 5.0

    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)

    # Idempotent on re-entry before Chapter 3 completion.
    window.player_hud.toasts.clear()
    gold_after_note = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="Chapter3NoteZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after_note
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    # Exit completes Chapter 3.
    gold_before_exit = window.get_counter("gold", 0.0)
    window.emit_signal("entered_zone", zone="Chapter3ExitZone", actor="Player", position=(0.0, 0.0))
    assert window.get_flag("act1_chapter3_complete") is True
    assert qm.is_quest_completed(q_exit) is True
    assert window.get_counter("gold", 0.0) == gold_before_exit + 15.0

    maybe_enqueue_quest_progress_toast(window, quest_manager=qm)

    # Note quest cannot re-award after Chapter 3 complete.
    gold_after_complete = window.get_counter("gold", 0.0)
    window.player_hud.toasts.clear()
    window.emit_signal("entered_zone", zone="Chapter3NoteZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after_complete
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False

    # Still idempotent after definitions reload.
    qm.load_definitions()
    window.emit_signal("entered_zone", zone="Chapter3ExitZone", actor="Player", position=(0.0, 0.0))
    window.emit_signal("entered_zone", zone="Chapter3NoteZone", actor="Player", position=(0.0, 0.0))
    assert window.get_counter("gold", 0.0) == gold_after_complete
    did_toast = maybe_enqueue_quest_progress_toast(window, quest_manager=qm)
    assert did_toast is False
