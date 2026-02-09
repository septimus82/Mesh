"""
Contract tests for scene transition policy model.
"""
from engine.scene_transition_policy_model import (
    SceneTransitionRequest,
    decide_scene_transition,
)


def test_runtime_no_editor_allows():
    req = SceneTransitionRequest(
        from_scene_path="scenes/a.json",
        to_scene_path="scenes/b.json",
        reason="Switch Scene",
        is_editor=False,
        has_unsaved_changes=False,
    )
    decision = decide_scene_transition(req)
    assert decision.allowed is True
    assert decision.requires_confirm is False


def test_editor_allows_when_clean():
    req = SceneTransitionRequest(
        from_scene_path="scenes/a.json",
        to_scene_path="scenes/b.json",
        reason="Switch Scene",
        is_editor=True,
        has_unsaved_changes=False,
    )
    decision = decide_scene_transition(req)
    assert decision.allowed is True
    assert decision.requires_confirm is False


def test_editor_blocks_when_dirty():
    req = SceneTransitionRequest(
        from_scene_path="scenes/a.json",
        to_scene_path="scenes/b.json",
        reason="Switch Scene",
        is_editor=True,
        has_unsaved_changes=True,
    )
    decision = decide_scene_transition(req)
    assert decision.allowed is False
    assert decision.requires_confirm is True
    assert decision.message_lines == ("Switch Scene",)
