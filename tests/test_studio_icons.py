"""Milestone 15 Stage 3: Mesh Studio's icons are Lucide's (ISC licence), present for every button that uses one,
and drawn from the vendored SVGs by tooling/make_icons.py."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from engine import studio_ui

pytestmark = pytest.mark.fast
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tooling"))


def test_every_icon_a_button_uses_is_there_with_its_source_and_the_licence() -> None:
    names = set(studio_ui.BUTTON_ICONS.values()) | {"map", "layout-grid", "history", "folder"}
    for name in names:
        for size in (16, 32):
            assert (studio_ui.ICONS / f"{name}_{size}.png").is_file(), f"{name}_{size}.png"
        assert (studio_ui.ICONS / "lucide" / f"{name}.svg").is_file(), f"{name}.svg"
    licence = (studio_ui.ICONS / "lucide" / "LICENSE").read_text(encoding="utf-8")
    assert "ISC License" in licence and "Lucide" in licence


def test_the_rasteriser_draws_strokes_arcs_and_round_shapes() -> None:
    from make_icons import element_lines, path_lines, render

    assert path_lines("M5 12h14") == [[(5.0, 12.0), (19.0, 12.0)]]
    quarter = path_lines("M12 2a10 10 0 0 1 10 10")[0]
    assert quarter[-1] == pytest.approx((22.0, 12.0)) and all(abs(((x - 12) ** 2 + (y - 12) ** 2) ** 0.5 - 10) < 1e-6
                                                               for x, y in quarter)
    assert len(element_lines(ET.fromstring('<circle cx="12" cy="12" r="3"/>'))[0]) > 32
    icon = render(studio_ui.ICONS / "lucide" / "check.svg", 16)
    assert icon.size == (16, 16) and icon.getchannel("A").getbbox() is not None
    assert icon.getpixel((0, 0))[3] == 0, "transparent where there's no stroke"
