"""Milestone 15: Mesh Studio's branding (the MeshMind brain-and-network mark as its icon, the MeshMind Studios
wordmark as the publisher's credit) is present, kept apart from the code licence, and optional."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine import studio_ui

pytestmark = pytest.mark.fast


def test_the_brand_assets_and_their_notice_are_there() -> None:
    names = {p.name for p in studio_ui.BRANDING.iterdir()}
    assert {"mesh_studio_mark_64.png", "mesh_studio_mark_128.png", "meshmind_studios_wordmark.png", "NOTICE.md"} <= names
    assert {f"mesh_studio_icon_{n}.png" for n in (16, 24, 32, 48, 64, 256)} <= names
    assert "not covered by the Mesh Engine code licence" in (studio_ui.BRANDING / "NOTICE.md").read_text(encoding="utf-8")


def test_the_window_gets_the_mesh_studio_icon_and_a_copy_without_branding_still_runs(tmp_path, monkeypatch) -> None:
    icons: list[object] = []
    studio_ui.set_app_icon(SimpleNamespace(set_icon=lambda *images: icons.extend(images)))
    assert len(icons) == 6 and {getattr(i, "width") for i in icons} == {16, 24, 32, 48, 64, 256}

    monkeypatch.setattr(studio_ui, "BRANDING", tmp_path)  # assets/branding missing (a bare install)
    monkeypatch.setattr(studio_ui, "_BRAND_TEXTURES", {})
    studio_ui.set_app_icon(SimpleNamespace(set_icon=lambda *images: pytest.fail("no icon to set")))
    assert studio_ui.brand_texture("mesh_studio_mark_64.png") is None


def test_selected_buttons_are_outlined_in_the_accent_and_every_state_uses_the_ui_font() -> None:
    for state in studio_ui.S_ACTIVE.values():
        assert state.font_name == studio_ui.FONT
    assert studio_ui.S_ACTIVE["normal"].border == studio_ui.C_ACCENT
    assert studio_ui.S_ACTIVE["normal"].border_width == 1
