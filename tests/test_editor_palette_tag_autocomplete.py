from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from engine.editor_controller import EditorModeController, _palette_tag_frequencies


class MockWindow:
    def __init__(self, *, width: int = 800, height: int = 600):
        self.width = width
        self.height = height
        self.paused = False
        self.scene_controller = MagicMock()
        self.screen_to_world = MagicMock(return_value=(0, 0))


@pytest.fixture()
def controller_with_tags(monkeypatch: pytest.MonkeyPatch) -> EditorModeController:
    prefabs = [
        {"id": "p_barrel", "display_name": "Barrel", "tags": ["scenery", "prop"]},
        {"id": "p_tree", "display_name": "Tree", "tags": ["scenery"]},
        {"id": "p_sword", "display_name": "Sword", "tags": ["weapon"]},
    ]

    # Avoid touching real content packs.
    monkeypatch.setattr("engine.editor_controller.load_prefab_palette", lambda *args, **kwargs: list(prefabs))
    monkeypatch.setattr("engine.editor_controller.get_prefab_palette", lambda: list(prefabs))

    window = MockWindow()
    controller = EditorModeController(window)
    controller.active = True
    controller.palette_active = True
    controller.palette_filter_active = True

    # Seed the ranked tag list (same logic used when opening palette).
    controller._palette_tag_ranked = _palette_tag_frequencies(list(controller.prefab_palette))

    return controller


def test_tag_autocomplete_hash_prefix(controller_with_tags: EditorModeController) -> None:
    c = controller_with_tags
    c.palette_filter = "#sc"

    sugg = c._palette_tag_suggestions()
    assert sugg and sugg[0] == "scenery"

    changed = c._apply_palette_tag_autocomplete()
    assert changed is True
    assert c.palette_filter == "#scenery"


def test_tag_autocomplete_mixed_tokens_only_replaces_last(controller_with_tags: EditorModeController) -> None:
    c = controller_with_tags
    c.palette_filter = "bar #sc"

    changed = c._apply_palette_tag_autocomplete()
    assert changed is True
    assert c.palette_filter == "bar #scenery"


def test_tag_autocomplete_t_prefix(controller_with_tags: EditorModeController) -> None:
    c = controller_with_tags
    c.palette_filter = "t:wea"

    sugg = c._palette_tag_suggestions()
    assert sugg and sugg[0] == "weapon"

    changed = c._apply_palette_tag_autocomplete()
    assert changed is True
    assert c.palette_filter == "t:weapon"


def test_tag_autocomplete_no_suggestions_no_change(controller_with_tags: EditorModeController) -> None:
    c = controller_with_tags
    c.palette_filter = "#zzz"

    before = c.palette_filter
    sugg = c._palette_tag_suggestions()
    assert sugg == []

    changed = c._apply_palette_tag_autocomplete()
    assert changed is False
    assert c.palette_filter == before
