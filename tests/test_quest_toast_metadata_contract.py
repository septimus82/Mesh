import json
import re
from pathlib import Path


def test_quest_toast_metadata_contract() -> None:
    quests_path = Path("assets/data/quests.json")
    assert quests_path.exists()
    root = json.loads(quests_path.read_text(encoding="utf-8"))
    quests = root.get("quests", [])
    assert isinstance(quests, list)

    max_toast_len = 120
    toast_keys = ("start_toast", "complete_toast")
    gating_keys = ("requires_flags", "blocks_flags")
    allowed_prefixes = {"Beacon", "Relay", "Cache", "Choice", "Switch", "Intro"}
    toast_re = re.compile(r"^[A-Za-z][A-Za-z0-9_ -]{0,30}: .+$")

    for quest in quests:
        assert isinstance(quest, dict)
        quest_id = str(quest.get("id") or "").strip()
        assert quest_id

        for key in toast_keys:
            if key not in quest:
                continue
            value = quest.get(key)
            assert isinstance(value, str)
            assert value.strip()
            assert len(value) <= max_toast_len
            assert toast_re.fullmatch(value) is not None
            prefix = value.split(":", 1)[0]
            if quest_id.startswith("ridge_variant_"):
                assert prefix in allowed_prefixes

        for key in gating_keys:
            if key not in quest:
                continue
            flags = quest.get(key)
            assert isinstance(flags, list)
            for flag in flags:
                assert isinstance(flag, str)
                assert flag.strip()
