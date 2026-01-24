from engine.ui import maybe_auto_open_quest_log


class StubQuestManager:
    def __init__(self, entries: list[dict]):
        self.entries = entries

    def list_active_quests(self):
        return list(self.entries)


class StubWindow:
    def __init__(self) -> None:
        self._flags: dict[str, bool] = {}
        self._visible = False
        self.toggle_calls = 0

    def get_flag(self, name: str, default: bool = False) -> bool:
        return bool(self._flags.get(str(name), default))

    def set_flag(self, name: str, value: bool = True) -> None:
        self._flags[str(name)] = bool(value)

    def is_quest_log_visible(self) -> bool:
        return bool(self._visible)

    def toggle_quest_log(self) -> bool:
        self.toggle_calls += 1
        self._visible = not self._visible
        if self._visible:
            self.set_flag("auto_opened_quest_log", True)
        return bool(self._visible)

    def emit_signal(self, _event_type: str, **_payload) -> None:
        return


def test_auto_open_triggers_once_on_first_active_quest() -> None:
    window = StubWindow()
    qm = StubQuestManager([{"id": "q1", "status": "inactive"}])

    assert maybe_auto_open_quest_log(window, qm) is False
    assert window.toggle_calls == 0
    assert window.is_quest_log_visible() is False

    qm.entries[0]["status"] = "active"
    assert maybe_auto_open_quest_log(window, qm) is True
    assert window.toggle_calls == 1
    assert window.is_quest_log_visible() is True
    assert window.get_flag("auto_opened_quest_log") is True

    assert maybe_auto_open_quest_log(window, qm) is False
    assert window.toggle_calls == 1


def test_auto_open_does_nothing_when_log_already_open() -> None:
    window = StubWindow()
    window._visible = True
    qm = StubQuestManager([{"id": "q1", "status": "active"}])

    assert maybe_auto_open_quest_log(window, qm) is False
    assert window.toggle_calls == 0
    assert window.get_flag("auto_opened_quest_log") is True


def test_auto_open_does_nothing_when_flag_already_set() -> None:
    window = StubWindow()
    window.set_flag("auto_opened_quest_log", True)
    qm = StubQuestManager([{"id": "q1", "status": "active"}])

    assert maybe_auto_open_quest_log(window, qm) is False
    assert window.toggle_calls == 0

