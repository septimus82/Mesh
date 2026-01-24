from engine.ui import PlayerHUD


class StubQuestManager:
    def __init__(self, entries):
        self._entries = entries

    def list_active_quests(self):
        return self._entries


def test_build_pinned_objective_text_prefers_active_quest_and_uses_stage_fields():
    qm = StubQuestManager(
        [
            {
                "id": "inactive_quest",
                "title": "Inactive Quest",
                "status": "inactive",
                "stage_title": "Should Not Pick",
                "stage_text": "Ignore",
            },
            {
                "id": "main_quest",
                "title": "Main Quest",
                "status": "active",
                "stage_title": "Talk to the Elder",
                "stage_text": "Return to  Ridge Outpost.\nSpeak  with the Elder.",
            },
        ],
    )

    text = PlayerHUD.build_pinned_objective_text(qm)
    assert text is not None
    assert "Objective: Talk to the Elder" in text
    assert "Return to Ridge Outpost. Speak with the Elder." in text


def test_build_pinned_objective_text_returns_none_without_entries():
    qm = StubQuestManager([])
    assert PlayerHUD.build_pinned_objective_text(qm) is None

