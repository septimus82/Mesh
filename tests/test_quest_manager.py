from unittest.mock import MagicMock

from engine.quest_manager import QuestManager


class StubGS:
    def __init__(self, flags=None, counters=None):
        self._flags = flags or {}
        self._counters = counters or {}

    def get_flag(self, name: str, default=False):
        return self._flags.get(name, default)

    def get_counter(self, name: str, default=0):
        return self._counters.get(name, default)


def test_register_and_start_quest():
    qm = QuestManager()
    qm.register_quest({"id": "intro", "title": "Intro Quest"})
    qm.start_quest("intro")
    quest = qm.get_quest("intro")
    assert quest is not None
    assert quest.state == "active"


def test_requirements_flags_and_counters_complete():
    qm = QuestManager()
    qm.register_quest(
        {
            "id": "wolf_hunt",
            "title": "Wolf Hunt",
            "requirements": {"flags": ["door_open"], "counters": {"wolf_kills": 3}},
            "state": "active",
        }
    )
    gs = StubGS(flags={"door_open": True}, counters={"wolf_kills": 5})
    qm.update_quest_states(gs)
    quest = qm.get_quest("wolf_hunt")
    assert quest.state == "completed"


def test_export_import_roundtrip():
    qm = QuestManager()
    qm.register_quest({"id": "q1", "title": "Quest One"})
    qm.start_quest("q1")
    data = qm.to_dict()

    other = QuestManager()
    other.load_from_dict(data)
    quest = other.get_quest("q1")
    assert quest is not None
    assert quest.state == "active"


def test_quest_giver_start(monkeypatch):
    from engine.behaviours.quest_giver import QuestGiver
    from engine.events import MeshEventBus

    class StubWindow:
        def __init__(self):
            self.event_bus = MeshEventBus()
            self.game_state_controller = MagicMock()
            self.game_state_controller.quests = QuestManager()

    window = StubWindow()
    entity = MagicMock()
    giver = QuestGiver(entity, window, quest_id="intro", listen_event="quest_start")
    window.event_bus.emit("quest_start")
    quest = window.game_state_controller.quests.get_quest("intro")
    assert quest is not None
    assert quest.state == "active"
    giver.on_destroy()
