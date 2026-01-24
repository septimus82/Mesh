from engine.ui import maybe_enqueue_quest_progress_toast


class StubHUD:
    def __init__(self) -> None:
        self.toasts: list[str] = []

    def enqueue_toast(self, message: str, *, seconds: float = 4.0) -> None:  # noqa: ARG002
        self.toasts.append(message)


class StubQuestManager:
    def __init__(self, entries: list[dict]):
        self.entries = entries

    def list_active_quests(self):
        return list(self.entries)


class StubWindow:
    def __init__(self) -> None:
        self.player_hud = StubHUD()
        self._vars: dict[str, object] = {}

    def get_var(self, name: str, default=None):
        return self._vars.get(name, default)

    def set_var(self, name: str, value) -> None:
        self._vars[str(name)] = value


def test_stage_change_enqueues_once() -> None:
    window = StubWindow()
    qm = StubQuestManager(
        [
            {
                "id": "q1",
                "title": "Quest One",
                "status": "active",
                "stage_id": "s1",
                "stage_title": "Find the thing",
                "completed": False,
            }
        ]
    )

    assert maybe_enqueue_quest_progress_toast(window, qm) is True
    assert window.player_hud.toasts == ["Objective updated: Find the thing"]

    assert maybe_enqueue_quest_progress_toast(window, qm) is False
    assert window.player_hud.toasts == ["Objective updated: Find the thing"]

    qm.entries[0]["stage_id"] = "s2"
    qm.entries[0]["stage_title"] = "Return to town"
    assert maybe_enqueue_quest_progress_toast(window, qm) is True
    assert window.player_hud.toasts == [
        "Objective updated: Find the thing",
        "Objective updated: Return to town",
    ]


def test_completion_enqueues_once() -> None:
    window = StubWindow()
    qm = StubQuestManager(
        [
            {
                "id": "q1",
                "title": "Quest One",
                "status": "active",
                "stage_id": "s1",
                "stage_title": "Find the thing",
                "completed": False,
            }
        ]
    )

    assert maybe_enqueue_quest_progress_toast(window, qm) is True
    qm.entries[0]["status"] = "completed"
    qm.entries[0]["completed"] = True

    assert maybe_enqueue_quest_progress_toast(window, qm) is True
    assert window.player_hud.toasts[-1] == "Quest complete: Quest One"

    assert maybe_enqueue_quest_progress_toast(window, qm) is False


def test_no_active_quest_does_nothing() -> None:
    window = StubWindow()
    qm = StubQuestManager([{"id": "q1", "status": "inactive"}])

    assert maybe_enqueue_quest_progress_toast(window, qm) is False
    assert window.player_hud.toasts == []

