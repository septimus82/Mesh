import logging

import pytest

import engine.swallowed_exceptions as swallowed_exceptions
from engine.ui import PlayerHUD

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


def test_collect_hud_history_logs_typed_failures_once(capsys: pytest.CaptureFixture[str]) -> None:
    hud = object.__new__(PlayerHUD)
    hud.window = _Window()
    swallowed_exceptions._SWALLOW_ONCE_TAGS.clear()
    logging.getLogger("engine.swallowed_exceptions").setLevel(logging.DEBUG)

    try:
        assert hud._collect_hud_history(limit=5) == ()
        assert hud._collect_hud_history(limit=5) == ()
    finally:
        swallowed_exceptions._SWALLOW_ONCE_TAGS.clear()

    stderr = capsys.readouterr().err
    assert stderr.count("SWALLOW[HUD-003]") == 1
    assert stderr.count("SWALLOW[HUD-004]") == 1
