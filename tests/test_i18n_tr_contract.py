from __future__ import annotations

import pytest

from engine import i18n


@pytest.mark.fast
def test_tr_returns_english_string() -> None:
    i18n.set_locale("en")
    assert i18n.tr("UI_LIGHT_EDITOR") == "Light Editor"


@pytest.mark.fast
def test_tr_formatting() -> None:
    i18n.set_locale("en")
    assert i18n.tr("UI_SAVED_PRESET", slot="custom_1") == "Saved: custom_1"


@pytest.mark.fast
def test_tr_missing_key_fallback() -> None:
    i18n.set_locale("en")
    assert i18n.tr("UI_DOES_NOT_EXIST") == "UI_DOES_NOT_EXIST"


@pytest.mark.fast
def test_tr_missing_locale_falls_back_to_en() -> None:
    i18n.set_locale("zz")
    assert i18n.tr("UI_OCCLUDER_EDITOR") == "Occluder Editor"
