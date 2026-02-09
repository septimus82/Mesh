from __future__ import annotations

from types import SimpleNamespace

from engine.editor.editor_dock_controller import EditorDockController


class SessionStub:
    def __init__(self) -> None:
        self.project_focused: bool | None = None
        self.problems_focused: bool | None = None

    def set_project_explorer_focused(self, value: bool) -> None:
        self.project_focused = value

    def set_problems_panel_focused(self, value: bool) -> None:
        self.problems_focused = value


def test_dock_controller_rev_changes_on_update() -> None:
    session = SessionStub()
    dock = EditorDockController(session, left_tab="Outliner", right_tab="Inspector")
    snap_a = dock.get_snapshot()
    assert dock.set_left_tab("Project") is True
    snap_b = dock.get_snapshot()
    assert snap_b.rev == snap_a.rev + 1
    assert session.project_focused is True

    # No change -> no rev bump
    assert dock.set_left_tab("Project") is False
    snap_c = dock.get_snapshot()
    assert snap_c.rev == snap_b.rev


def test_dock_controller_sets_problems_focus() -> None:
    session = SessionStub()
    dock = EditorDockController(session, left_tab="Outliner", right_tab="Inspector")
    assert dock.set_right_tab("Problems") is True
    assert session.problems_focused is True


def test_apply_tab_change_left_project_updates_host() -> None:
    session = SessionStub()
    dock = EditorDockController(session, left_tab="Outliner", right_tab="Inspector")

    class HostStub:
        def __init__(self) -> None:
            self.active = True
            self._menu_active = "menu"
            self.scene_browser_active = True
            self.entity_panels_active = True
            self.entity_panels_focus = ""
            self._entity_panels_selected_id = None
            self._refresh_project_explorer_rows_called = 0
            self._refresh_entity_panels_list_called = 0
            self._sync_search_focus_called = 0
            self._autosave_workspace_called = 0

            def close_context_menu() -> None:
                self._menu_active = None

            self.panels = SimpleNamespace(close_context_menu=close_context_menu)
            self.search = SimpleNamespace(sync_search_focus=self._sync_search_focus)

        def _entity_panels_selected_id_value(self) -> str:
            return "entity_1"

        def _refresh_project_explorer_rows(self) -> None:
            self._refresh_project_explorer_rows_called += 1

        def _refresh_entity_panels_list(self, *, sync_selected: bool) -> None:
            if sync_selected:
                self._refresh_entity_panels_list_called += 1

        def _sync_search_focus(self) -> None:
            self._sync_search_focus_called += 1

        def _autosave_workspace(self) -> None:
            self._autosave_workspace_called += 1

    host = HostStub()
    assert dock.apply_tab_change(host, "left", "Project") is True
    assert dock.left_tab == "Project"
    assert host.scene_browser_active is False
    assert host.entity_panels_active is False
    assert host._refresh_project_explorer_rows_called == 1
    assert host._sync_search_focus_called == 1
    assert host._autosave_workspace_called == 1


def test_apply_tab_change_right_assets_updates_host() -> None:
    session = SessionStub()
    dock = EditorDockController(session, left_tab="Outliner", right_tab="Inspector")

    class HostStub:
        def __init__(self) -> None:
            self.active = True
            self._menu_active = None
            self.asset_browser_active = False
            self.entity_panels_active = False
            self.entity_panels_focus = ""
            self.problems = SimpleNamespace(preview_open=True, close_preview=self._close_preview)
            self._sync_search_focus_called = 0
            self._autosave_workspace_called = 0
            self._refresh_assets_called = 0
            self.panels = SimpleNamespace(close_context_menu=lambda: None)
            self.search = SimpleNamespace(sync_search_focus=self._sync_search_focus)

        def _close_preview(self, _host: object) -> None:
            self.problems.preview_open = False

        def refresh_asset_browser(self) -> None:
            self._refresh_assets_called += 1

        def _sync_search_focus(self) -> None:
            self._sync_search_focus_called += 1

        def _autosave_workspace(self) -> None:
            self._autosave_workspace_called += 1

    host = HostStub()
    assert dock.apply_tab_change(host, "right", "Assets") is True
    assert dock.right_tab == "Assets"
    assert host.asset_browser_active is True
    assert host._refresh_assets_called == 1
    assert host._sync_search_focus_called == 1
    assert host._autosave_workspace_called == 1
