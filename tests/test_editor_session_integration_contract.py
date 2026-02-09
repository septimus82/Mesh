from __future__ import annotations

from types import SimpleNamespace

from engine.capture_mode import CaptureState
from engine.editor.editor_session_controller import EditorSessionController
from engine.entity_paint_mode import EntityPaintState, PrefabInfo
from engine.entity_select_mode import EntitySelectState, set_selection
from engine.input_runtime import capture_key_router_handlers_entity_paint as entity_paint_handlers
from engine.input_runtime import capture_key_router_handlers_palette as palette_handlers
from engine.editor_runtime import editor_input_router
from engine.editor.editor_session_query import get_session_snapshot


def test_session_updates_via_capture_entity_paint_and_selection() -> None:
    session = EditorSessionController()
    editor = SimpleNamespace(session=session)
    window = SimpleNamespace(editor_controller=editor)

    # Capture mode toggle should update session.
    window.capture_state = CaptureState(layer_id="layer")
    start_rev = session.get_snapshot().rev
    assert palette_handlers.dispatch_palette_action(window, SimpleNamespace(), "capture.capture_mode.toggle") is True
    snap = session.get_snapshot()
    assert snap.capture_mode_active is True
    assert snap.rev == start_rev + 1

    # Entity paint toggle should update session.
    window.entity_paint_state = EntityPaintState(prefabs=(PrefabInfo("prefab_a", ()),))
    mid_rev = session.get_snapshot().rev
    assert entity_paint_handlers.dispatch_entity_paint_action(window, SimpleNamespace(), "capture.entity_paint.toggle") is True
    snap = session.get_snapshot()
    assert snap.entity_paint_active is True
    assert snap.rev == mid_rev + 1

    # Authoring selected updates session.
    select_state = EntitySelectState()
    before_select_rev = session.get_snapshot().rev
    set_selection(window, select_state, ["entity_a"])
    snap = session.get_snapshot()
    assert snap.authoring_selected_active is True
    assert snap.rev == before_select_rev + 1

    # Focus snapshot should not carry session state; access session directly.
    controller = SimpleNamespace(
        session=session,
        panels=SimpleNamespace(is_command_palette_open=lambda: False),
        project_explorer=SimpleNamespace(context_menu_open=False, inline_rename_active=False),
    )
    focus_snapshot = editor_input_router._build_focus_snapshot(controller)
    assert "session" not in focus_snapshot
    session_snapshot = get_session_snapshot(controller)
    assert session_snapshot.capture_mode_active is True
    assert session_snapshot.entity_paint_active is True
    assert session_snapshot.authoring_selected_active is True
