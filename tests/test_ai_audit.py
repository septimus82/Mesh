import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.ai_audit import _audit_scene, run_ai_audit
from engine.content_index import ContentIndex


@pytest.fixture
def mock_content_index(tmp_path):
    """Mock ContentIndex to return specific files."""
    idx = MagicMock(spec=ContentIndex)
    # Mock entries dict
    idx.entries = {}
    return idx

def test_audit_scene_basic(tmp_path, mock_content_index):
    """Test auditing a simple scene with NPCs and transitions."""
    scene_file = tmp_path / "test_scene.json"
    scene_data = {
        "entities": [
            {
                "name": "NPC1",
                "dialogue": {"id": "d1"},
                "tags": ["friendly"]
            },
            {
                "name": "NPC2",
                # No dialogue, no tags
            },
            {
                "behaviours": [
                    {
                        "type": "SceneTransition",
                        "params": {"target_scene": "scenes/target.json"}
                    }
                ]
            }
        ]
    }
    scene_file.write_text(json.dumps(scene_data), encoding="utf-8")

    # Mock resolve_path to simulate target existence
    with patch("engine.ai_audit.resolve_path") as mock_resolve:
        mock_resolve.return_value.exists.return_value = True

        report = _audit_scene(scene_file, mock_content_index, set())

        assert report.scene_id == str(scene_file.as_posix())
        assert report.npc_count == 2
        assert report.npc_with_dialogue == 1
        assert report.npc_without_dialogue == 1
        assert report.npc_with_tags == 1
        assert report.npc_without_tags == 1
        assert report.transition_count == 1
        assert report.transitions_with_missing_target == 0
        assert len(report.warnings) == 1 # NPC2 has name but no dialogue

@pytest.mark.fast
def test_audit_scene_warns_for_dialogue_with_id_and_no_tags(tmp_path, mock_content_index):
    """NPCs with dialogue IDs but no tags should be flagged for AI context."""
    scene_file = tmp_path / "dialogue_no_tags.json"
    scene_data = {
        "entities": [
            {
                "name": "TaglessNPC",
                "dialogue": {"id": "tagless_intro"},
            }
        ]
    }
    scene_file.write_text(json.dumps(scene_data), encoding="utf-8")

    report = _audit_scene(scene_file, mock_content_index, set())

    assert "NPC 'TaglessNPC' has dialogue but no tags." in report.warnings

@pytest.mark.fast
def test_audit_scene_tags_suppress_dialogue_without_tags_warning(tmp_path, mock_content_index):
    """NPCs with dialogue IDs and tags should not produce the no-tags warning."""
    scene_file = tmp_path / "dialogue_with_tags.json"
    scene_data = {
        "entities": [
            {
                "name": "TaggedNPC",
                "dialogue": {"id": "tagged_intro"},
                "tags": ["friendly"],
            }
        ]
    }
    scene_file.write_text(json.dumps(scene_data), encoding="utf-8")

    report = _audit_scene(scene_file, mock_content_index, set())

    assert "NPC 'TaggedNPC' has dialogue but no tags." not in report.warnings

@pytest.mark.fast
def test_audit_scene_dialogue_without_id_does_not_warn_for_missing_tags(tmp_path, mock_content_index):
    """Dialogue dictionaries without IDs keep the existing no-dialogue-ID path."""
    scene_file = tmp_path / "dialogue_without_id.json"
    scene_data = {
        "entities": [
            {
                "name": "NoIdNPC",
                "dialogue": {"text": "Hello"},
            }
        ]
    }
    scene_file.write_text(json.dumps(scene_data), encoding="utf-8")

    report = _audit_scene(scene_file, mock_content_index, set())

    assert "NPC 'NoIdNPC' has dialogue but no tags." not in report.warnings
    assert "NPC 'NoIdNPC' has no dialogue ID." in report.warnings

def test_audit_scene_missing_target(tmp_path, mock_content_index):
    """Test auditing a scene with a broken transition."""
    scene_file = tmp_path / "broken_scene.json"
    scene_data = {
        "entities": [
            {
                "behaviours": [
                    {
                        "type": "SceneTransition",
                        "params": {"target_scene": "scenes/missing.json"}
                    }
                ]
            }
        ]
    }
    scene_file.write_text(json.dumps(scene_data), encoding="utf-8")

    with patch("engine.ai_audit.resolve_path") as mock_resolve:
        mock_resolve.return_value.exists.return_value = False

        report = _audit_scene(scene_file, mock_content_index, set())

        assert report.transition_count == 1
        assert report.transitions_with_missing_target == 1
        assert any("does not exist" in w for w in report.warnings)

def test_audit_quest_hooks(tmp_path, mock_content_index):
    """Test detecting quest hooks."""
    scene_file = tmp_path / "quest_scene.json"
    scene_data = {
        "entities": [
            {
                "behaviours": [
                    {
                        "type": "IncrementCounterOnEvent",
                        "params": {"quest_id": "my_quest"}
                    }
                ]
            }
        ]
    }
    scene_file.write_text(json.dumps(scene_data), encoding="utf-8")

    report = _audit_scene(scene_file, mock_content_index, {"my_quest"})

    assert "my_quest" in report.quest_hooks
    assert not report.warnings

def test_audit_quest_hooks_unknown(tmp_path, mock_content_index):
    """Test detecting unknown quest hooks."""
    scene_file = tmp_path / "quest_scene.json"
    scene_data = {
        "entities": [
            {
                "behaviours": [
                    {
                        "type": "IncrementCounterOnEvent",
                        "params": {"quest_id": "unknown_quest"}
                    }
                ]
            }
        ]
    }
    scene_file.write_text(json.dumps(scene_data), encoding="utf-8")

    report = _audit_scene(scene_file, mock_content_index, {"my_quest"})

    assert "unknown_quest" in report.quest_hooks
    assert any("unknown quest" in w for w in report.warnings)

def test_run_ai_audit_integration(tmp_path):
    """Test the full run_ai_audit function with mocked file system."""
    # Setup mock files
    quests_file = tmp_path / "assets/data/quests.json"
    quests_file.parent.mkdir(parents=True, exist_ok=True)
    quests_file.write_text(json.dumps({"q1": {}, "q2": {}}), encoding="utf-8")

    scene_file = tmp_path / "scenes/scene1.json"
    scene_file.parent.mkdir(parents=True, exist_ok=True)
    scene_file.write_text(json.dumps({
        "entities": [
            {"behaviours": [{"type": "IncrementCounterOnEvent", "params": {"quest_id": "q1"}}]}
        ]
    }), encoding="utf-8")

    with patch("engine.ai_audit.resolve_path") as mock_resolve, \
         patch("engine.ai_audit.discover_scene_paths", return_value=[scene_file]):

        # Mock resolve_path to return our temp files
        def side_effect(path):
            if str(path).endswith("quests.json"):
                return quests_file
            return Path(path) # Default

        mock_resolve.side_effect = side_effect

        # Run audit
        report_dict = run_ai_audit(json_output=True)

        assert report_dict is not None
        assert len(report_dict["scenes"]) == 1
        assert report_dict["scenes"][0]["scene_id"] == str(scene_file.as_posix())
        assert "q1" in report_dict["scenes"][0]["quest_hooks"]

        # Check quests
        quests = {q["id"]: q for q in report_dict["quests"]}
        assert quests["q1"]["has_triggers"] is True
        assert quests["q2"]["has_triggers"] is False

        # Check global warnings
        assert any("Quest 'q2' has no triggers" in w for w in report_dict["global_warnings"])
