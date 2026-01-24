from __future__ import annotations

from unittest.mock import MagicMock

from engine.constants import EVENT_ENTERED_ZONE
from engine.game_state_controller import GameStateController


class _StubWindow:
    def __init__(self) -> None:
        self.engine_config = MagicMock()


def test_entered_zone_sets_last_zone_id_from_payload_zone() -> None:
    window = _StubWindow()
    controller = GameStateController(window)  # type: ignore[arg-type]

    controller.handle_event({"type": EVENT_ENTERED_ZONE, "payload": {"zone": " ZoneA "}})

    assert controller.get_var("last_zone_id") == "ZoneA"


def test_non_entered_zone_event_does_not_clobber_last_zone_id() -> None:
    window = _StubWindow()
    controller = GameStateController(window)  # type: ignore[arg-type]
    controller.set_var("last_zone_id", "ZoneA")

    controller.handle_event({"type": "other_event", "payload": {"zone": "ZoneB"}})

    assert controller.get_var("last_zone_id") == "ZoneA"


def test_entered_zone_falls_back_to_top_level_zone_only_when_payload_not_dict() -> None:
    window = _StubWindow()
    controller = GameStateController(window)  # type: ignore[arg-type]

    controller.handle_event({"type": EVENT_ENTERED_ZONE, "payload": "ignored", "zone": "ZoneTop"})
    assert controller.get_var("last_zone_id") == "ZoneTop"

    controller.set_var("last_zone_id", "ZoneKeep")
    controller.handle_event({"type": EVENT_ENTERED_ZONE, "payload": {"zone": None}, "zone": "ZoneIgnored"})
    assert controller.get_var("last_zone_id") == "ZoneKeep"

