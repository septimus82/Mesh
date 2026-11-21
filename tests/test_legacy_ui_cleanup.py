"""Post-Milestone 15 legacy UI cleanup: Mesh Studio is the editor. The legacy editor stays available on purpose (an
editor launch of a project without a world, or MESH_LEGACY_EDITOR=1) but a game no longer drops into it on F4; no
visible hint points players at an editor; no legacy menu entry is inert; developer-only title-menu items appear
only where they can run."""

from __future__ import annotations

import types

import pytest

from engine.action_runtime.registry import _toggle_editor, legacy_editor_allowed

pytestmark = pytest.mark.fast


class _Editor:
    def __init__(self, *, active: bool = False, playing: bool = False) -> None:
        self.active, self.toggles = active, 0
        self.play_session = types.SimpleNamespace(is_playing=playing)

    def toggle(self) -> None:
        self.toggles += 1


def _window(mode: str | None, editor: _Editor) -> types.SimpleNamespace:
    return types.SimpleNamespace(engine_config=types.SimpleNamespace(_mesh_launch_mode=mode), editor_controller=editor)


def test_f4_in_a_game_no_longer_opens_the_legacy_editor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MESH_LEGACY_EDITOR", raising=False)
    game = _window(None, _Editor())
    _toggle_editor(game)
    assert game.editor_controller.toggles == 0 and not legacy_editor_allowed(game)


def test_the_legacy_editor_stays_reachable_where_it_is_meant_to_be(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MESH_LEGACY_EDITOR", raising=False)
    editor_launch = _window("editor", _Editor())  # mesh edit on a project without a world
    _toggle_editor(editor_launch)
    assert editor_launch.editor_controller.toggles == 1

    for open_editor in (_Editor(active=True), _Editor(playing=True)):  # an open editor (or its play-test) can be left
        window = _window(None, open_editor)
        _toggle_editor(window)
        assert open_editor.toggles == 1

    monkeypatch.setenv("MESH_LEGACY_EDITOR", "1")  # the explicit developer / compatibility option
    game = _window(None, _Editor())
    _toggle_editor(game)
    assert game.editor_controller.toggles == 1


def test_no_visible_hint_points_players_at_an_editor() -> None:
    from engine.ui_overlays.help_overlay import HelpOverlay

    body = HelpOverlay._build_body_text(types.SimpleNamespace())
    assert "Editor" not in body and "F2:" not in body
    import inspect

    from engine.ui_overlays import hud

    assert "F2: Editor" not in inspect.getsource(hud)


def test_every_legacy_menu_entry_has_a_real_action_and_the_inert_export_is_gone() -> None:
    from engine.editor import editor_actions_impl as impl
    from engine.editor import menu_bar_model

    ids = {a.id for a in impl.get_editor_actions(None, None)}
    assert "app.export_web_demo" not in ids
    for group, order in menu_bar_model.MENU_ACTION_ORDER.items():
        for action_id in order:
            assert action_id == "|" or action_id in ids, f"{group} menu names a missing action: {action_id}"


def test_title_menu_web_demo_items_only_where_their_tool_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.ui_overlays import main_menu_overlay as mm

    monkeypatch.delenv("PYGBAG", raising=False)
    menu = mm.MainMenuOverlay.__new__(mm.MainMenuOverlay)
    menu._has_continue = lambda: False
    monkeypatch.setattr(mm, "_tool_available", lambda module: False)  # a creator's own game, or a pip install
    actions = [action for _label, action in menu._items()]
    assert "run_web_preview" not in actions and "export_web" not in actions
    assert actions == ["start_game", "settings", "quit"], "the game's own items stay"
    monkeypatch.setattr(mm, "_tool_available", lambda module: True)  # the engine checkout
    actions = [action for _label, action in menu._items()]
    assert "run_web_preview" in actions and "export_web" in actions
