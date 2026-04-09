from __future__ import annotations

import pytest

from engine.ui_overlays.widget_overlay_helpers import OverlayFocusModel
from tests._typing import as_any

pytestmark = [pytest.mark.fast]


def test_overlay_focus_model_default_focus_on_init() -> None:
    model = OverlayFocusModel()
    assert model.focus == "input"


def test_overlay_focus_model_toggle_is_reversible_and_deterministic() -> None:
    model = OverlayFocusModel("input")
    assert model.toggle_focus() == "results"
    assert model.focus == "results"
    assert model.toggle_focus() == "input"
    assert model.focus == "input"
    # Deterministic repeat
    assert model.toggle_focus() == "results"
    assert model.toggle_focus() == "input"


def test_overlay_focus_model_reset_explicit_focus_targets() -> None:
    model = OverlayFocusModel("results")
    assert model.focus == "results"
    assert model.reset("input") == "input"
    assert model.focus == "input"
    assert model.reset("results") == "results"
    assert model.focus == "results"


def test_overlay_focus_model_invalid_focus_target_handling_is_deterministic() -> None:
    model = OverlayFocusModel("results")
    # Current behavior coerces unknown values to "input"
    assert model.reset("unknown") == "input"
    assert model.focus == "input"
    assert model.reset("") == "input"
    assert model.focus == "input"
    assert model.reset(as_any(None)) == "input"
    assert model.focus == "input"


def test_overlay_focus_model_compatible_with_legacy_focus_target_mirror_pattern() -> None:
    model = OverlayFocusModel("input")
    legacy_focus_target = model.reset("input")
    assert legacy_focus_target == "input"
    assert model.focus == legacy_focus_target
    legacy_focus_target = model.toggle_focus()
    assert legacy_focus_target == "results"
    assert model.focus == legacy_focus_target
