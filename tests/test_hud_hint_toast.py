from engine.ui import PlayerHUD


class StubQuestManager:
    def __init__(self, entries):
        self._entries = entries

    def list_active_quests(self):
        return list(self._entries)


class StubWindow:
    def __init__(self):
        self._flags: dict[str, bool] = {}

    def get_flag(self, name: str, default: bool = False) -> bool:
        return bool(self._flags.get(name, default))

    def set_flag(self, name: str, value: bool = True) -> None:
        self._flags[str(name)] = bool(value)


def test_quest_log_hint_shown_once_when_active_quest_exists():
    window = StubWindow()
    qm = StubQuestManager([{"id": "q1", "status": "active", "title": "Quest"}])

    first = PlayerHUD.maybe_show_quest_log_hint(window, quest_manager=qm, scene_id="packs/core_regions/scenes/Ridge Outpost_hub.json")
    assert first == "Press Q to open Quest Log"
    assert window.get_flag("hint_shown_quest_log") is True

    second = PlayerHUD.maybe_show_quest_log_hint(window, quest_manager=qm, scene_id="packs/core_regions/scenes/Ridge Outpost_hub.json")
    assert second is None


def test_quest_log_hint_not_shown_when_no_active_quests():
    window = StubWindow()
    qm = StubQuestManager([{"id": "q1", "status": "inactive", "title": "Quest"}])

    hint = PlayerHUD.maybe_show_quest_log_hint(window, quest_manager=qm, scene_id="packs/core_regions/scenes/Ridge Outpost_hub.json")
    assert hint is None
    assert window.get_flag("hint_shown_quest_log") is False

