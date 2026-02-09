from dataclasses import dataclass
from engine.editor.project_explorer_context_menu_model import (
    build_project_explorer_context_menu,
    clamp_menu_position,
    hit_test_menu_item,
    first_selectable_index,
    find_index_by_action_id,
    ProjectExplorerSelectionPayload,
    CONTEXT_MENU_WIDTH,
    CONTEXT_MENU_ITEM_HEIGHT,
    CONTEXT_MENU_PADDING_Y,
)


@dataclass(frozen=True)
class _Action:
    id: str
    shortcut: str
    shortcut_scope: str = "global"


def _actions():
    return [
        _Action("editor.project_explorer.safe_rename_asset", "F2", "project_explorer"),
        _Action("editor.project_explorer.refactor_move_selected", "Ctrl+Shift+M", "project_explorer"),
        _Action("editor.project_explorer.refactor_delete_selected", "Del", "project_explorer"),
        _Action("editor.project_explorer.reveal_current", "Ctrl+Shift+E"),
        _Action("editor.project_explorer.copy_path", "Ctrl+Shift+C"),
        _Action("editor.project_explorer.copy_common_parent", "Ctrl+Shift+Alt+C"),
        _Action("editor.project_explorer.select_all", "Ctrl+A"),
        _Action("editor.project_explorer.clear_selection", "Escape"),
        _Action("editor.project_explorer.invert_selection", "Ctrl+I"),
    ]


def test_menu_build_no_selection():
    payload = ProjectExplorerSelectionPayload(
        selection_count=0,
        has_common_parent=False,
        can_rename=False,
        can_move=False,
        can_delete=False,
        can_reveal=False,
        can_copy_paths=False,
        can_copy_common_parent=False,
        can_select_all=True,
        can_clear_selection=True,
        can_invert_selection=True,
    )
    items = build_project_explorer_context_menu(payload, _actions(), ("project_explorer", "global"))
    assert [item.action_id for item in items if item.kind == "action"] == [
        "editor.project_explorer.safe_rename_asset",
        "editor.project_explorer.refactor_move_selected",
        "editor.project_explorer.refactor_delete_selected",
        "editor.project_explorer.reveal_current",
        "editor.project_explorer.copy_path",
        "editor.project_explorer.copy_common_parent",
        "editor.project_explorer.select_all",
        "editor.project_explorer.clear_selection",
        "editor.project_explorer.invert_selection",
    ]
    assert [i.kind for i in items].count("separator") == 2
    assert items[0].action_id == "editor.project_explorer.safe_rename_asset"
    assert items[0].enabled is False
    assert items[1].action_id == "editor.project_explorer.refactor_move_selected"
    assert items[2].action_id == "editor.project_explorer.refactor_delete_selected"
    assert items[-3].action_id == "editor.project_explorer.select_all"


def test_menu_build_single_selection():
    payload = ProjectExplorerSelectionPayload(
        selection_count=1,
        has_common_parent=False,
        can_rename=True,
        can_move=True,
        can_delete=True,
        can_reveal=True,
        can_copy_paths=True,
        can_copy_common_parent=False,
        can_select_all=True,
        can_clear_selection=True,
        can_invert_selection=True,
    )
    items = build_project_explorer_context_menu(payload, _actions(), ("project_explorer", "global"))
    assert items[0].enabled is True
    assert items[4].action_id == "editor.project_explorer.reveal_current"
    assert items[6].action_id == "editor.project_explorer.copy_common_parent"
    assert items[6].enabled is False


def test_menu_build_multi_selection_with_common_parent():
    payload = ProjectExplorerSelectionPayload(
        selection_count=2,
        has_common_parent=True,
        can_rename=False,
        can_move=True,
        can_delete=True,
        can_reveal=True,
        can_copy_paths=True,
        can_copy_common_parent=True,
        can_select_all=True,
        can_clear_selection=True,
        can_invert_selection=True,
    )
    items = build_project_explorer_context_menu(payload, _actions(), ("project_explorer", "global"))
    assert items[0].enabled is False
    assert items[6].action_id == "editor.project_explorer.copy_common_parent"
    assert items[6].enabled is True


def test_menu_build_multi_selection_no_common_parent():
    payload = ProjectExplorerSelectionPayload(
        selection_count=2,
        has_common_parent=False,
        can_rename=False,
        can_move=True,
        can_delete=True,
        can_reveal=True,
        can_copy_paths=True,
        can_copy_common_parent=False,
        can_select_all=True,
        can_clear_selection=True,
        can_invert_selection=True,
    )
    items = build_project_explorer_context_menu(payload, _actions(), ("project_explorer", "global"))
    assert items[6].action_id == "editor.project_explorer.copy_common_parent"
    assert items[6].enabled is False


def test_menu_build_deterministic():
    payload = ProjectExplorerSelectionPayload(
        selection_count=1,
        has_common_parent=False,
        can_rename=True,
        can_move=True,
        can_delete=True,
        can_reveal=True,
        can_copy_paths=True,
        can_copy_common_parent=False,
        can_select_all=True,
        can_clear_selection=True,
        can_invert_selection=True,
    )
    items1 = build_project_explorer_context_menu(payload, _actions(), ("project_explorer", "global"))
    items2 = build_project_explorer_context_menu(payload, _actions(), ("project_explorer", "global"))
    summary1 = [(i.kind, i.action_id, i.enabled, i.shortcut_text) for i in items1]
    summary2 = [(i.kind, i.action_id, i.enabled, i.shortcut_text) for i in items2]
    assert summary1 == summary2


def test_shortcuts_only_in_active_scopes():
    payload = ProjectExplorerSelectionPayload(
        selection_count=1,
        has_common_parent=False,
        can_rename=True,
        can_move=True,
        can_delete=True,
        can_reveal=True,
        can_copy_paths=True,
        can_copy_common_parent=False,
        can_select_all=True,
        can_clear_selection=True,
        can_invert_selection=True,
    )
    items = build_project_explorer_context_menu(payload, _actions(), ())
    assert all(item.shortcut_text is None for item in items if item.kind == "action")


def test_first_selectable_none_when_all_disabled():
    payload = ProjectExplorerSelectionPayload(
        selection_count=0,
        has_common_parent=False,
        can_rename=False,
        can_move=False,
        can_delete=False,
        can_reveal=False,
        can_copy_paths=False,
        can_copy_common_parent=False,
        can_select_all=False,
        can_clear_selection=False,
        can_invert_selection=False,
    )
    items = build_project_explorer_context_menu(payload, _actions(), ("project_explorer", "global"))
    assert first_selectable_index(items) is None


def test_find_index_by_action_id_only_enabled():
    payload = ProjectExplorerSelectionPayload(
        selection_count=0,
        has_common_parent=False,
        can_rename=False,
        can_move=False,
        can_delete=False,
        can_reveal=False,
        can_copy_paths=False,
        can_copy_common_parent=False,
        can_select_all=True,
        can_clear_selection=True,
        can_invert_selection=True,
    )
    items = build_project_explorer_context_menu(payload, _actions(), ("project_explorer", "global"))
    assert find_index_by_action_id(items, "editor.project_explorer.safe_rename_asset") is None


def test_clamp_menu_position():
    pos = clamp_menu_position(100, 100, 200, 300, 1000, 1000)
    assert pos == (100, 100)
    pos = clamp_menu_position(900, 100, 200, 300, 1000, 1000)
    assert pos == (800, 100)
    pos = clamp_menu_position(100, 800, 200, 300, 1000, 1000)
    assert pos == (100, 700)
    pos = clamp_menu_position(900, 800, 200, 300, 1000, 1000)
    assert pos == (800, 700)


def test_hit_test():
    top_padding = CONTEXT_MENU_PADDING_Y
    item_h = CONTEXT_MENU_ITEM_HEIGHT
    assert hit_test_menu_item(10, 1, 5) is None
    assert hit_test_menu_item(10, top_padding + 1, 5) == 0
    assert hit_test_menu_item(10, top_padding + item_h - 1, 5) == 0
    assert hit_test_menu_item(10, top_padding + item_h + 1, 5) == 1
    assert hit_test_menu_item(CONTEXT_MENU_WIDTH + 10, top_padding + 1, 5) is None
    assert hit_test_menu_item(10, top_padding + item_h * 10, 5) is None
