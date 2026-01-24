from __future__ import annotations

from types import SimpleNamespace


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


def _patch_arcade(monkeypatch):
    import engine.optional_arcade as optional_arcade
    from engine import arcade_fallback as arcade_stub

    monkeypatch.setattr(optional_arcade, "arcade", arcade_stub)


def test_quest_log_selection_clamps(monkeypatch):
    _patch_arcade(monkeypatch)
    from engine.ui_overlays.hud import QuestLog

    window = StubWindow()
    panel = QuestLog(window)

    monkeypatch.setattr(
        panel,
        "_collect_entries",
        lambda: [
            {"id": "q1", "title": "Quest One"},
            {"id": "q2", "title": "Quest Two"},
        ],
    )

    panel._selection_index = 0
    panel._move_selection(-1)
    assert panel._selection_index == 0

    panel._move_selection(1)
    assert panel._selection_index == 1

    panel._move_selection(5)
    assert panel._selection_index == 1

    monkeypatch.setattr(panel, "_collect_entries", lambda: [])
    panel._move_selection(1)
    assert panel._selection_index == 0


def test_get_active_quests_adapter_filters_and_maps():
    from engine.quest_ui import get_active_quests

    class StubQuestManager:
        def list_active_quests(self):
            return [
                {
                    "id": "q1",
                    "title": "Quest One",
                    "status": "active",
                    "stage_text": "Find the key",
                },
                {
                    "id": "q2",
                    "title": "Quest Two",
                    "status": "inactive",
                },
                {
                    "id": "q3",
                    "title": "Quest Three",
                    "state": "completed",
                    "description": "Return to town",
                },
            ]

    window = SimpleNamespace(quest_manager=StubQuestManager())
    summaries = get_active_quests(window)
    assert [summary.quest_id for summary in summaries] == ["q1", "q3"]
    assert summaries[0].current_objective == "Find the key"
    assert summaries[1].is_complete is True
