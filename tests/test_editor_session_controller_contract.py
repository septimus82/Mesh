from __future__ import annotations

from engine.editor.editor_session_controller import EditorSessionController


def test_session_controller_rev_increments_on_change() -> None:
    ctl = EditorSessionController()
    snap_a = ctl.get_snapshot()
    ctl.set_tile_paint_active(True)
    snap_b = ctl.get_snapshot()
    assert snap_b.rev == snap_a.rev + 1

    ctl.set_tile_paint_active(True)
    snap_c = ctl.get_snapshot()
    assert snap_c.rev == snap_b.rev

    ctl.set_command_palette_focused(True)
    snap_d = ctl.get_snapshot()
    assert snap_d.rev == snap_c.rev + 1


def test_session_controller_snapshot_cached_until_change() -> None:
    ctl = EditorSessionController()
    snap_a = ctl.get_snapshot()
    snap_b = ctl.get_snapshot()
    assert snap_a is snap_b

    ctl.set_project_explorer_focused(True)
    snap_c = ctl.get_snapshot()
    assert snap_c is not snap_b
