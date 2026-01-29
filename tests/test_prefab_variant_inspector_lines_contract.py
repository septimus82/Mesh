from __future__ import annotations

from engine.editor.entity_panels import build_inspector_lines
from engine.editor.state import ENTITY_PANEL_FIELDS
from engine.editor_prefab_variant_ops import DiffRow


def test_inspector_lines_include_prefab_overrides() -> None:
    rows = [
        DiffRow(key="scale", base_value=1.0, override_value=1.2, effective_value=1.2),
    ]

    field_count = len(ENTITY_PANEL_FIELDS)
    lines = build_inspector_lines(
        active=True,
        focus="inspector",
        text_edit_active=False,
        sprite_name="Crate",
        entity_data={"scale": 1.2},
        inspector_index=field_count,  # selects first override row after fields
        text_field=None,
        text_buffer="",
        sprite=None,
        prefab_label="crate_small",
        override_rows=rows,
    )

    assert any("Prefab: crate_small" in line for line in lines)
    assert any("Overrides:" in line for line in lines)
    assert any(line.startswith("> scale: 1.0 -> 1.2") for line in lines)


def test_inspector_selection_clamps_to_override_rows() -> None:
    rows = [
        DiffRow(key="scale", base_value=1.0, override_value=1.2, effective_value=1.2),
    ]
    lines = build_inspector_lines(
        active=True,
        focus="inspector",
        text_edit_active=False,
        sprite_name="Crate",
        entity_data={"scale": 1.2},
        inspector_index=999,
        text_field=None,
        text_buffer="",
        sprite=None,
        prefab_label="crate_small",
        override_rows=rows,
    )

    assert any(line.startswith("> scale: 1.0 -> 1.2") for line in lines)
