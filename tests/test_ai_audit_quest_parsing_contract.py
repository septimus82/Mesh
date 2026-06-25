import json
from pathlib import Path

from engine.ai_audit import _extract_quest_ids, build_audit_report


def _quest_ids_from_real_assets() -> set[str]:
    payload = json.loads(Path("assets/data/quests.json").read_text(encoding="utf-8"))
    quests = payload["quests"]
    return {
        entry["id"]
        for entry in quests
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    }


def test_extracts_quest_ids_from_real_assets_shape() -> None:
    payload = json.loads(Path("assets/data/quests.json").read_text(encoding="utf-8"))

    assert _extract_quest_ids(payload) == _quest_ids_from_real_assets()
    assert _extract_quest_ids(payload) != {"quests"}


def test_extracts_quest_ids_from_bare_list_shape() -> None:
    payload = [{"id": "intro"}, {"id": "finale"}, "bad", {"name": "missing"}]

    assert _extract_quest_ids(payload) == {"intro", "finale"}


def test_extracts_quest_ids_from_legacy_mapping_shape() -> None:
    payload = {"intro": {"title": "Intro"}, "finale": {"title": "Finale"}}

    assert _extract_quest_ids(payload) == {"intro", "finale"}


def test_ai_audit_does_not_report_quests_container_as_quest_id() -> None:
    report = build_audit_report()

    quest_ids = {quest.id for quest in report.quests}
    assert quest_ids == _quest_ids_from_real_assets()
    assert "quests" not in quest_ids
    assert "Quest 'quests' has no triggers in any scene." not in report.global_warnings
