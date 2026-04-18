from __future__ import annotations

import pytest

from engine.schema_validation import SchemaValidationError, validate


pytestmark = [pytest.mark.fast]


def test_cutscene_schema_accepts_start_dialogue_references() -> None:
    payload = {
        "cutscenes": [
            {
                "id": "intro",
                "steps": [
                    {"type": "wait", "duration": 0.1},
                    {
                        "type": "start_dialogue",
                        "dialogue_id": "ep01_dialogue_intro",
                        "target": "Episode01Mentor",
                    },
                ],
            }
        ]
    }

    assert validate(payload, "cutscene.schema.json", "cutscenes.json") is payload


def test_cutscene_schema_rejects_legacy_commands_and_schema_version() -> None:
    payload = {
        "cutscenes": [
            {
                "id": "intro",
                "schema_version": 1,
                "commands": [{"type": "wait", "duration": 0.1}],
                "steps": [],
            }
        ]
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate(payload, "cutscene.schema.json", "cutscenes.json")

    message = str(exc_info.value)
    assert "schema_version" in message
    assert "commands" in message


def test_cutscene_schema_rejects_unknown_step_fields() -> None:
    payload = {
        "cutscenes": [
            {
                "id": "intro",
                "steps": [
                    {"type": "wait", "duration": 0.1, "unexpected": True},
                ],
            }
        ]
    }

    with pytest.raises(SchemaValidationError) as exc_info:
        validate(payload, "cutscene.schema.json", "cutscenes.json")

    assert "unexpected" in str(exc_info.value)


def test_prefab_schema_accepts_supported_sprite_sheet_keys() -> None:
    payload = [
        {
            "id": "hero",
            "display_name": "Hero",
            "tags": ["player"],
            "entity": {
                "sprite_sheet": {
                    "image": "assets/hero.png",
                    "path": "assets/hero.png",
                    "frame_w": 16,
                    "frame_h": 16,
                    "frames": 4,
                }
            },
        }
    ]

    assert validate(payload, "prefab.schema.json", "assets/prefabs.json") is payload


def test_prefab_schema_rejects_unknown_sprite_sheet_keys() -> None:
    payload = [
        {
            "id": "hero",
            "display_name": "Hero",
            "tags": ["player"],
            "entity": {
                "sprite_sheet": {
                    "image": "assets/hero.png",
                    "frame_width": 16,
                    "frame_height": 16,
                    "bogus": 1,
                }
            },
        }
    ]

    with pytest.raises(SchemaValidationError) as exc_info:
        validate(payload, "prefab.schema.json", "assets/prefabs.json")

    assert "bogus" in str(exc_info.value)