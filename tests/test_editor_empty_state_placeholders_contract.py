from __future__ import annotations

import pytest

from engine.asset_index import AssetRow
from engine.editor.asset_browser_panel import build_asset_browser_lines
from engine.editor.entity_panels import build_inspector_lines, build_outliner_lines
from engine.editor.state import ENTITY_PANEL_FOCUS_INSPECTOR, ENTITY_PANEL_FOCUS_OUTLINER
from engine.editor_entity_ops import EntitySummary

pytestmark = [pytest.mark.fast]


def _asset_lines(*, search_text: str, rows: list[AssetRow]) -> list[str]:
    return build_asset_browser_lines(
        active=True,
        search_text=search_text,
        search_focused=False,
        kind_filter="All",
        rows=rows,
        selection_index=0,
    )


def _outliner_lines(*, items: list[EntitySummary], selected_id: str | None = None) -> list[str]:
    return build_outliner_lines(
        active=True,
        focus=ENTITY_PANEL_FOCUS_OUTLINER,
        search_text="",
        search_focused=False,
        items=items,
        cursor_index=0,
        selected_id=selected_id,
    )


def _inspector_lines(*, sprite_name: str | None) -> list[str]:
    return build_inspector_lines(
        active=True,
        focus=ENTITY_PANEL_FOCUS_INSPECTOR,
        text_edit_active=False,
        sprite_name=sprite_name,
        entity_data={"id": "entity_1", "name": "Entity"},
        inspector_index=0,
        text_field=None,
        text_buffer="",
    )


def test_asset_browser_empty_folder_placeholder_line_present() -> None:
    lines = _asset_lines(search_text="", rows=[])

    assert "  No assets in this folder." in lines


def test_asset_browser_search_no_results_placeholder_escapes_query() -> None:
    lines = _asset_lines(search_text="boss's key", rows=[])

    assert "  No results for 'boss\\'s key'." in lines


def test_entity_inspector_no_selection_placeholder_line_present() -> None:
    lines = _inspector_lines(sprite_name=None)

    assert "Select an entity to inspect." in lines


def test_entity_outliner_empty_scene_placeholder_line_present() -> None:
    lines = _outliner_lines(items=[])

    assert "  No entities in this scene." in lines


def test_non_empty_asset_browser_has_no_empty_placeholder() -> None:
    row = AssetRow(
        rel_path="assets/props/crate.png",
        kind="image",
        display_name="crate.png",
    )
    lines = _asset_lines(search_text="", rows=[row])

    assert "  No assets in this folder." not in lines
    assert not any(line.startswith("  No results for '") for line in lines)
    assert any("crate.png [image]" in line for line in lines)


def test_non_empty_entity_panels_have_no_empty_placeholder() -> None:
    item = EntitySummary(id="entity_1", name="Entity", type="prop", x=1.0, y=2.0)

    outliner = _outliner_lines(items=[item], selected_id="entity_1")
    inspector = _inspector_lines(sprite_name="Entity")

    assert "  No entities in this scene." not in outliner
    assert "Select an entity to inspect." not in inspector
    assert any("Entity (entity_1) [prop]" in line for line in outliner)
    assert "Selected: Entity" in inspector
