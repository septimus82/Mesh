from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from engine.behaviours.offer_perk_choice import OfferPerkChoice
from engine.perks import PerkManager

pytestmark = [pytest.mark.fast]


class _StubGameState:
    def __init__(self, perk_manager: PerkManager) -> None:
        self.perk_manager = perk_manager
        self._owned: set[str] = set()

    def has_perk(self, perk_id: str) -> bool:
        return str(perk_id) in self._owned

    def add_perk(self, perk_id: str) -> None:
        self._owned.add(str(perk_id))


class _StubWindow:
    def __init__(self, perk_manager: PerkManager) -> None:
        self.game_state_controller = _StubGameState(perk_manager)
        self.audio = MagicMock()
        self.audio.play_sound = MagicMock()
        self.audio.play_sound_at = MagicMock()

    def show_dialogue(self, _entries, *, owner: str) -> bool:  # noqa: ARG002
        return True

    def close_dialogue(self, *, owner: str | None = None) -> None:  # noqa: ARG002
        return None


class _DummyEntity:
    def __init__(self) -> None:
        self.mesh_name = "PerkShrine"
        self.mesh_entity_data: dict[str, str] = {}


def test_offer_perk_choice_ui_sound_stays_non_spatial() -> None:
    perks = PerkManager()
    perks.register_perk({"id": "vitality_boost", "name": "Vitality", "description": "More HP"})
    window = _StubWindow(perks)
    behaviour = OfferPerkChoice(_DummyEntity(), window, pool=["vitality_boost"])

    behaviour._handle_choice({"id": "vitality_boost"})

    window.audio.play_sound.assert_called_once_with("assets/sounds/ui_buy.wav")
    window.audio.play_sound_at.assert_not_called()
