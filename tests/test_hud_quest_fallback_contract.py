import logging

import pytest

import engine.swallowed_exceptions as swallowed_exceptions
from engine.ui import PlayerHUD


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


def test_hud_quest_read_fallback_uses_stable_once_keys(capsys: pytest.CaptureFixture[str]) -> None:
    qm = _BrokenQuestManager()
    window = _Window()
    swallowed_exceptions._SWALLOW_ONCE_TAGS.clear()
    logging.getLogger("engine.swallowed_exceptions").setLevel(logging.DEBUG)

    try:
        assert PlayerHUD.build_pinned_objective_text(qm) is None
        assert PlayerHUD.build_pinned_objective_text(qm) is None
        assert PlayerHUD.maybe_show_quest_log_hint(window, quest_manager=qm) is None
        assert PlayerHUD.maybe_show_quest_log_hint(window, quest_manager=qm) is None
    finally:
        seen_keys = set(swallowed_exceptions._SWALLOW_ONCE_TAGS)
        swallowed_exceptions._SWALLOW_ONCE_TAGS.clear()

    stderr = capsys.readouterr().err
    assert seen_keys == {"ui_pinned_objective", "ui_quest_log_hint"}
    assert stderr.count("Error reading active quests for pinned objective") == 1
    assert stderr.count("Error reading active quests for quest log hint") == 1
