import logging

import pytest

from engine.ui import PlayerHUD
from engine.ui_overlays import common as ui_common


pytestmark = [pytest.mark.fast]


class _GameplayBus:
    @staticmethod
    def get_history(limit: int) -> int:
        _ = limit
        return 1


class _EventBus:
    @staticmethod
    def get_recent_events(limit: int) -> object:
        raise ValueError(f"bad limit {limit}")


class _Window:
    gameplay_event_bus = _GameplayBus()
    event_bus = _EventBus()


def test_collect_hud_history_logs_typed_failures_once(caplog: pytest.LogCaptureFixture) -> None:
    hud = object.__new__(PlayerHUD)
    hud.window = _Window()
    ui_common._LOG_ONCE.clear()

    try:
        with caplog.at_level(logging.DEBUG, logger="engine.ui_overlays.common"):
            assert hud._collect_hud_history(limit=5) == ()
            assert hud._collect_hud_history(limit=5) == ()
    finally:
        ui_common._LOG_ONCE.clear()

    messages = [record.getMessage() for record in caplog.records]
    assert sum("SWALLOW[HUD-003]" in message for message in messages) == 1
    assert sum("SWALLOW[HUD-004]" in message for message in messages) == 1
