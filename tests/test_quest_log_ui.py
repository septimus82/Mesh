from engine.game_state_controller import GameStateController


class StubAudio:
    def play_sound(self, path: str) -> None:  # pragma: no cover - stub
        self.last = path


class StubWindow:
    def __init__(self):
        from engine.config import EngineConfig
        cfg = EngineConfig()
        self.width = cfg.width
        self.height = cfg.height
        self.audio = StubAudio()
        self.game_state_controller = GameStateController(self)


def _patch_arcade(monkeypatch):
    import engine.optional_arcade as optional_arcade
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)


def test_quest_log_toggle_visibility(monkeypatch):
    _patch_arcade(monkeypatch)
    from engine.ui_overlays.hud import QuestLog

    window = StubWindow()
    panel = QuestLog(window)
    assert panel.is_visible() is False
    panel.toggle()
    assert panel.is_visible() is True
    panel.toggle()
    assert panel.is_visible() is False


def test_quest_log_collects_active_quests(monkeypatch):
    _patch_arcade(monkeypatch)
    from engine.ui_overlays.hud import QuestLog

    window = StubWindow()
    gs = window.game_state_controller
    gs.quests.register_quest(
        {"id": "q1", "title": "Quest One", "state": "active", "description": "Find the relay"}
    )
    gs.quests.register_quest({"id": "q2", "title": "Quest Two", "state": "completed"})
    panel = QuestLog(window)
    entries = {entry["id"]: entry for entry in panel._collect_entries()}
    assert entries["q1"]["title"] == "Quest One"
    assert entries["q1"]["current_objective"] == "Find the relay"
    assert entries["q2"]["title"] == "Quest Two"
    assert entries["q2"]["completed"] is True
