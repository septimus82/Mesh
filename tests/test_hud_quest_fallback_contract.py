import logging

import pytest

from engine.ui import PlayerHUD
from engine.ui_overlays import common as ui_common


pytestmark = [pytest.mark.fast]


class _BrokenQuestManager:
    def list_active_quests(self) -> object:
        raise KeyError("status")


class _Window:
    def __init__(self) -> None:
        self._flags: dict[str, bool] = {}

    def get_flag(self, name: str, default: bool = False) -> bool:
        return bool(self._flags.get(name, default))

    def set_flag(self, name: str, value: bool = True) -> None:
        self._flags[str(name)] = bool(value)


def test_hud_quest_read_fallback_uses_stable_once_keys(caplog: pytest.LogCaptureFixture) -> None:
    qm = _BrokenQuestManager()
    window = _Window()
    ui_common._LOG_ONCE.clear()

    try:
        with caplog.at_level(logging.ERROR, logger="engine.ui_overlays.common"):
            assert PlayerHUD.build_pinned_objective_text(qm) is None
            assert PlayerHUD.build_pinned_objective_text(qm) is None
            assert PlayerHUD.maybe_show_quest_log_hint(window, quest_manager=qm) is None
            assert PlayerHUD.maybe_show_quest_log_hint(window, quest_manager=qm) is None
    finally:
        seen_keys = set(ui_common._LOG_ONCE)
        ui_common._LOG_ONCE.clear()

    messages = [record.getMessage() for record in caplog.records]
    assert seen_keys == {"ui_pinned_objective", "ui_quest_log_hint"}
    assert sum("Error reading active quests for pinned objective" in message for message in messages) == 1
    assert sum("Error reading active quests for quest log hint" in message for message in messages) == 1
