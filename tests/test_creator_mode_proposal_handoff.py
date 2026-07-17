from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.editor.creator_mode import (
    PROPOSAL_OPEN_INBOX_ACTION_ID,
    CreatorModeController,
    build_creator_overlay_model,
    build_creator_proposal_handoff,
)
from engine.editor.creator_mode.creator_overlay_renderer import (
    build_creator_overlay_draw_commands,
    hit_test_creator_overlay_click,
)
from engine.editor.creator_mode.creator_proposal_status import (
    CreatorProposalListRow,
    CreatorProposalStatusModel,
    unavailable_creator_proposal_status,
)
from engine.editor.editor_dock_controller import EditorDockController

pytestmark = pytest.mark.fast

_DEFAULT_DOCK = object()


def test_pending_proposals_with_proposal_inbox_is_available() -> None:
    status = _status_with_pending(2)
    editor = SimpleNamespace(proposal_inbox=SimpleNamespace(), dock=FakeDock())

    handoff = build_creator_proposal_handoff(editor, status)

    assert handoff.available is True
    assert handoff.label == "Review in AI Proposals"
    assert handoff.reason == ""
    assert handoff.pending_count == 2
    assert handoff.enabled is True
    assert handoff.action_id == PROPOSAL_OPEN_INBOX_ACTION_ID


def test_pending_proposals_without_proposal_inbox_is_unavailable() -> None:
    status = _status_with_pending(1)

    handoff = build_creator_proposal_handoff(SimpleNamespace(live_bridge=object()), status)

    assert handoff.available is False
    assert handoff.label == "Review in AI Proposals"
    assert handoff.reason == "AI Proposals inbox unavailable"
    assert handoff.pending_count == 1
    assert handoff.enabled is False
    assert handoff.action_id == ""


def test_pending_proposals_without_dock_is_unavailable() -> None:
    status = _status_with_pending(1)

    handoff = build_creator_proposal_handoff(
        SimpleNamespace(proposal_inbox=SimpleNamespace()),
        status,
    )

    assert handoff.available is False
    assert handoff.enabled is False
    assert handoff.reason == "Right dock unavailable"
    assert handoff.action_id == ""


def test_pending_proposals_without_viewport_controls_is_unavailable() -> None:
    status = _status_with_pending(1)

    handoff = build_creator_proposal_handoff(
        SimpleNamespace(proposal_inbox=SimpleNamespace(), dock=MissingViewportDock(right_tab="Inspector", right_collapsed=False)),
        status,
    )

    assert handoff.available is False
    assert handoff.enabled is False
    assert handoff.reason == "AI Proposals dock controls unavailable"
    assert handoff.action_id == ""


def test_pending_proposals_without_apply_tab_change_is_unavailable() -> None:
    status = _status_with_pending(1)

    handoff = build_creator_proposal_handoff(
        SimpleNamespace(proposal_inbox=SimpleNamespace(), dock=MissingApplyTabChangeDock()),
        status,
    )

    assert handoff.available is False
    assert handoff.enabled is False
    assert handoff.reason == "AI Proposals dock controls unavailable"
    assert handoff.action_id == ""


def test_pending_proposals_without_canonical_expansion_is_unavailable() -> None:
    status = _status_with_pending(1)

    handoff = build_creator_proposal_handoff(
        SimpleNamespace(proposal_inbox=SimpleNamespace(), dock=MissingToggleRightDock()),
        status,
    )

    assert handoff.available is False
    assert handoff.enabled is False
    assert handoff.reason == "AI Proposals dock controls unavailable"
    assert handoff.action_id == ""


def test_zero_proposals_shows_no_proposals_to_review() -> None:
    status = CreatorProposalStatusModel(
        available=True,
        pending_count=0,
        summary="No staged proposals.",
        rows=(),
    )
    editor = SimpleNamespace(proposal_inbox=SimpleNamespace())

    handoff = build_creator_proposal_handoff(editor, status)

    assert handoff.available is False
    assert handoff.label == "No proposals to review"
    assert handoff.reason == ""
    assert handoff.pending_count == 0
    assert handoff.enabled is False
    assert handoff.action_id == ""


def test_unavailable_proposal_status_shows_review_unavailable() -> None:
    status = unavailable_creator_proposal_status(warnings=("Bridge read failed.",))

    handoff = build_creator_proposal_handoff(
        SimpleNamespace(proposal_inbox=SimpleNamespace(), dock=FakeDock()),
        status,
    )

    assert handoff.available is False
    assert handoff.label == "Proposal review unavailable"
    assert handoff.reason == "Proposal status unavailable"
    assert handoff.pending_count == 0
    assert handoff.enabled is False
    assert handoff.action_id == ""


def test_snapshot_includes_proposal_handoff() -> None:
    bridge = FakeBridge([{"proposal_id": "proposal-1", "preview_summary": "Preview"}])
    editor = _editor_with_bridge(bridge, proposal_inbox=SimpleNamespace())
    controller = CreatorModeController(editor)
    controller.show()

    snapshot = controller.build_snapshot()

    assert snapshot.proposal_handoff.available is True
    assert snapshot.proposal_handoff.label == "Review in AI Proposals"
    assert snapshot.proposal_handoff.pending_count == 1


def test_build_snapshot_calls_list_pending_proposals_once() -> None:
    bridge = FakeBridge([{"proposal_id": "proposal-1", "preview_summary": "Preview"}])
    editor = _editor_with_bridge(bridge, proposal_inbox=SimpleNamespace())
    controller = CreatorModeController(editor)
    controller.show()

    controller.build_snapshot()

    assert bridge.calls == ["list_pending_proposals"]


def test_overlay_model_includes_proposal_handoff() -> None:
    bridge = FakeBridge([{"proposal_id": "proposal-1", "preview_summary": "Preview"}])
    editor = _editor_with_bridge(bridge, proposal_inbox=SimpleNamespace())
    controller = CreatorModeController(editor)
    controller.show()

    model = build_creator_overlay_model(controller.build_snapshot())

    assert model.proposal_handoff.available is True
    assert model.proposal_handoff.label == "Review in AI Proposals"


def test_hostile_proposal_inbox_proves_no_accept_reject_or_list_pending_calls() -> None:
    status = _status_with_pending(1)
    editor = SimpleNamespace(proposal_inbox=HostileInbox(), dock=FakeDock())

    handoff = build_creator_proposal_handoff(editor, status)

    assert handoff.available is True
    assert editor.proposal_inbox.calls == []


def test_hostile_bridge_proves_no_accept_reject_apply_or_stage_calls() -> None:
    bridge = HostileBridge([{"proposal_id": "proposal-1", "preview_summary": "Preview"}])
    editor = _editor_with_bridge(bridge, proposal_inbox=SimpleNamespace())
    controller = CreatorModeController(editor)
    controller.show()

    controller.build_snapshot()

    assert bridge.calls == ["list_pending_proposals"]


def test_handoff_module_imports_without_arcade() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import importlib.util, sys, types; "
                "from pathlib import Path; "
                "root = Path('engine/editor/creator_mode'); "
                "sys.modules['engine'] = types.ModuleType('engine'); "
                "sys.modules['engine.editor'] = types.ModuleType('engine.editor'); "
                "package = types.ModuleType('engine.editor.creator_mode'); "
                "package.__path__ = [str(root)]; "
                "sys.modules['engine.editor.creator_mode'] = package; "
                "status_spec = importlib.util.spec_from_file_location("
                "'engine.editor.creator_mode.creator_proposal_status', "
                "root / 'creator_proposal_status.py'); "
                "status_module = importlib.util.module_from_spec(status_spec); "
                "sys.modules[status_spec.name] = status_module; "
                "status_spec.loader.exec_module(status_module); "
                "spec = importlib.util.spec_from_file_location("
                "'engine.editor.creator_mode.creator_proposal_handoff', "
                "root / 'creator_proposal_handoff.py'); "
                "module = importlib.util.module_from_spec(spec); "
                "sys.modules[spec.name] = module; "
                "spec.loader.exec_module(module); "
                "print('arcade' in sys.modules or 'engine.optional_arcade' in sys.modules)"
            ),
        ],
        capture_output=True,
        check=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )

    assert result.stdout.strip() == "False"


def test_handoff_module_does_not_import_real_bridge_modules() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from engine.editor.creator_mode.creator_proposal_handoff "
                "import build_creator_proposal_handoff; "
                "blocked = ["
                "'engine.editor.proposal_inbox', "
                "'engine.editor.live_session_bridge', "
                "'engine.editor.editor_live_ops_controller'"
                "]; "
                "print(any(name in sys.modules for name in blocked))"
            ),
        ],
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stdout.strip() == "False"


def test_package_import_does_not_eagerly_import_renderer() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import engine.editor.creator_mode; "
                "print('engine.editor.creator_mode.creator_overlay_renderer' in sys.modules)"
            ),
        ],
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stdout.strip() == "False"


def test_render_shows_use_ai_proposals_when_handoff_available() -> None:
    bridge = FakeBridge([{"proposal_id": "proposal-1", "preview_summary": "Preview"}])
    controller = CreatorModeController(_editor_with_bridge(bridge, proposal_inbox=SimpleNamespace()))
    controller.show()

    text = _command_text(
        build_creator_overlay_draw_commands(
            build_creator_overlay_model(controller.build_snapshot()),
            1280,
            720,
        )
    )

    assert "Review in AI Proposals" in text
    assert "Review: Use AI Proposals" not in text
    assert "Details: Affects" in text


def test_render_shows_unavailable_reason_when_inbox_missing() -> None:
    bridge = FakeBridge([{"proposal_id": "proposal-1", "preview_summary": "Preview"}])
    controller = CreatorModeController(_editor_with_bridge(bridge, proposal_inbox=None))
    controller.show()

    text = _command_text(
        build_creator_overlay_draw_commands(
            build_creator_overlay_model(controller.build_snapshot()),
            1280,
            720,
        )
    )

    assert "AI Proposals unavailable - AI Proposals inbox unavailable" in text


def test_zero_pending_proposals_does_not_render_handoff_review_line() -> None:
    controller = CreatorModeController(_editor_with_bridge(FakeBridge([]), proposal_inbox=SimpleNamespace()))
    controller.show()

    text = _command_text(
        build_creator_overlay_draw_commands(
            build_creator_overlay_model(controller.build_snapshot()),
            1280,
            720,
        )
    )

    assert "Review in AI Proposals" not in text
    assert "AI Proposals unavailable" not in text


def test_rendered_enabled_handoff_review_line_has_action_id_and_hitbox() -> None:
    controller = CreatorModeController(
        _editor_with_bridge(FakeBridge([{"proposal_id": "proposal-1"}]), proposal_inbox=SimpleNamespace())
    )
    controller.show()
    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )
    review_commands = [command for command in commands if command.text == "Review in AI Proposals"]

    assert len(review_commands) == 1
    assert review_commands[0].action_id == PROPOSAL_OPEN_INBOX_ACTION_ID
    assert review_commands[0].hit_left < review_commands[0].hit_right
    assert review_commands[0].hit_bottom < review_commands[0].hit_top


def test_disabled_handoff_review_line_has_no_action_id_or_hitbox() -> None:
    controller = CreatorModeController(
        _editor_with_bridge(FakeBridge([{"proposal_id": "proposal-1"}]), proposal_inbox=None)
    )
    controller.show()
    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )
    review_commands = [command for command in commands if "AI Proposals unavailable" in command.text]

    assert len(review_commands) == 1
    assert review_commands[0].action_id == ""
    assert review_commands[0].hit_left == 0.0
    assert review_commands[0].hit_right == 0.0


def test_enabled_handoff_hit_test_returns_stable_action_id() -> None:
    controller = CreatorModeController(
        _editor_with_bridge(FakeBridge([{"proposal_id": "proposal-1"}]), proposal_inbox=SimpleNamespace())
    )
    controller.show()
    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )
    target = next(command for command in commands if command.action_id == PROPOSAL_OPEN_INBOX_ACTION_ID)

    assert hit_test_creator_overlay_click(
        commands,
        (target.hit_left + target.hit_right) / 2.0,
        (target.hit_top + target.hit_bottom) / 2.0,
    ) == PROPOSAL_OPEN_INBOX_ACTION_ID
    assert hit_test_creator_overlay_click(commands, target.hit_right + 10.0, target.hit_top + 10.0) is None


def test_click_inside_enabled_handoff_opens_ai_proposals_inbox() -> None:
    bridge = FakeBridge([{"proposal_id": "proposal-1"}])
    dock = FakeDock(right_tab="Inspector", right_collapsed=True)
    editor = _editor_with_bridge(bridge, proposal_inbox=SimpleNamespace(), dock=dock, active=True)
    controller = CreatorModeController(editor)
    controller.show()
    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )
    target = next(command for command in commands if command.action_id == PROPOSAL_OPEN_INBOX_ACTION_ID)

    result = controller.handle_overlay_click(
        (target.hit_left + target.hit_right) / 2.0,
        (target.hit_top + target.hit_bottom) / 2.0,
    )

    assert result is not None
    assert result.ok is True
    assert controller.active is False
    assert dock.right_collapsed is False
    assert dock.right_tab == "AI Proposals"
    assert dock.apply_tab_calls == [("right", "AI Proposals")]


def test_disabled_handoff_click_area_does_not_open_inbox() -> None:
    dock = FakeDock(right_tab="Inspector", right_collapsed=True)
    editor = _editor_with_bridge(
        FakeBridge([{"proposal_id": "proposal-1"}]),
        proposal_inbox=None,
        dock=dock,
        active=True,
    )
    controller = CreatorModeController(editor)
    controller.show()
    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )
    disabled = next(command for command in commands if "AI Proposals unavailable" in command.text)

    result = controller.handle_overlay_click(disabled.x + 4.0, disabled.y - 4.0)

    assert result is None
    assert controller.active is True
    assert dock.right_collapsed is True
    assert dock.right_tab == "Inspector"


def test_bottom_panel_height_unchanged_at_720p() -> None:
    controller = CreatorModeController(
        _editor_with_bridge(FakeBridge([{"proposal_id": "proposal-1"}]), proposal_inbox=SimpleNamespace())
    )
    controller.show()
    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )
    bottom_rects = [command for command in commands if command.kind == "rect" and command.region == "bottom"]

    assert len(bottom_rects) == 1
    assert bottom_rects[0].height == 216.0


def test_more_than_three_pending_still_renders_and_more() -> None:
    rows = [{"proposal_id": f"proposal-{index}", "preview_summary": f"Preview {index}"} for index in range(5)]
    controller = CreatorModeController(_editor_with_bridge(FakeBridge(rows), proposal_inbox=SimpleNamespace()))
    controller.show()
    text = _command_text(
        build_creator_overlay_draw_commands(
            build_creator_overlay_model(controller.build_snapshot()),
            1280,
            720,
        )
    )

    assert text.count("Review in AI Proposals") == 1
    assert "...and 2 more" in text


@pytest.mark.parametrize("width,height", ((1280, 720), (1024, 576), (320, 240)))
@pytest.mark.parametrize("pending_count", (1, 3, 5))
def test_enabled_handoff_hitbox_stays_inside_bottom_panel_at_required_sizes(
    width: int,
    height: int,
    pending_count: int,
) -> None:
    controller = CreatorModeController(
        _editor_with_bridge(FakeBridge(_pending_rows(pending_count)), proposal_inbox=SimpleNamespace())
    )
    controller.show()
    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        width,
        height,
    )
    bottom = next(command for command in commands if command.kind == "rect" and command.region == "bottom")
    panel_left = bottom.x - bottom.width / 2
    panel_right = bottom.x + bottom.width / 2
    panel_bottom = bottom.y - bottom.height / 2
    panel_top = bottom.y + bottom.height / 2
    targets = [command for command in commands if command.action_id == PROPOSAL_OPEN_INBOX_ACTION_ID]

    assert len(targets) == 1
    target = targets[0]
    assert target.text == "Review in AI Proposals"
    assert target.hit_left >= panel_left
    assert target.hit_right <= panel_right
    assert target.hit_bottom >= panel_bottom
    assert target.hit_top <= panel_top
    assert all(command.action_id == "" for command in commands if command.text.startswith("proposal-"))
    assert hit_test_creator_overlay_click(
        commands,
        (target.hit_left + target.hit_right) / 2.0,
        (target.hit_top + target.hit_bottom) / 2.0,
    ) == PROPOSAL_OPEN_INBOX_ACTION_ID


@pytest.mark.parametrize("pending_count", (1, 3))
def test_pending_proposals_render_exactly_one_handoff_action(pending_count: int) -> None:
    rows = [
        {"proposal_id": f"proposal-{index}", "preview_summary": f"Preview {index}"}
        for index in range(pending_count)
    ]
    controller = CreatorModeController(_editor_with_bridge(FakeBridge(rows), proposal_inbox=SimpleNamespace()))
    controller.show()

    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )
    handoff_commands = [command for command in commands if command.text == "Review in AI Proposals"]

    assert len(handoff_commands) == 1
    assert len([command for command in commands if command.action_id == PROPOSAL_OPEN_INBOX_ACTION_ID]) == 1
    assert all(command.action_id == "" for command in commands if command.text.startswith("proposal-"))


def test_five_pending_proposals_render_one_handoff_and_overflow() -> None:
    controller = CreatorModeController(
        _editor_with_bridge(
            FakeBridge(
                [
                    {"proposal_id": f"proposal-{index}", "preview_summary": f"Preview {index}"}
                    for index in range(5)
                ]
            ),
            proposal_inbox=SimpleNamespace(),
        )
    )
    controller.show()
    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )
    text = _command_text(commands)

    assert text.count("Review in AI Proposals") == 1
    assert len([command for command in commands if command.action_id == PROPOSAL_OPEN_INBOX_ACTION_ID]) == 1
    assert "...and 2 more" in text


@pytest.mark.parametrize("width,height", ((1280, 720), (1024, 576), (320, 240)))
def test_five_pending_proposals_retain_overflow_when_layout_can_display_it(width: int, height: int) -> None:
    controller = CreatorModeController(
        _editor_with_bridge(FakeBridge(_pending_rows(5)), proposal_inbox=SimpleNamespace())
    )
    controller.show()

    text = _command_text(
        build_creator_overlay_draw_commands(
            build_creator_overlay_model(controller.build_snapshot()),
            width,
            height,
        )
    )

    assert "...and 2 more" in text


def test_minimum_layout_prioritizes_handoff_over_dry_run_details() -> None:
    controller = CreatorModeController(
        _editor_with_bridge(FakeBridge(_pending_rows(5)), proposal_inbox=SimpleNamespace())
    )
    controller.show()
    text = _command_text(
        build_creator_overlay_draw_commands(
            build_creator_overlay_model(controller.build_snapshot()),
            320,
            240,
        )
    )

    assert "Review in AI Proposals" in text
    assert "...and 2 more" in text
    assert "Details: Affects" not in text


def test_open_ai_proposals_inbox_navigates_without_mutating_pending_proposal() -> None:
    proposal = {
        "proposal_id": "proposal-1",
        "preview_summary": "Set SceneExit params on door_north",
        "affected_ids": ["door_north"],
        "dry_run": {"ok": True, "affected_ids": ["door_north"]},
        "base_revision": 7,
    }
    bridge = HostileBridge([proposal])
    dock = FakeDock(right_tab="Inspector", right_collapsed=True)
    editor = _editor_with_bridge(
        bridge,
        proposal_inbox=HostileInbox(),
        dock=dock,
        active=True,
        content_revision=42,
        undo_stack=[{"type": "HumanEdit"}],
    )
    controller = CreatorModeController(editor)
    controller.show()

    result = controller.open_ai_proposals_inbox()

    assert result.ok is True
    assert controller.active is False
    assert editor.active is True
    assert dock.right_collapsed is False
    assert dock.right_tab == "AI Proposals"
    assert dock.toggle_right_calls == 1
    assert dock.apply_tab_calls == [("right", "AI Proposals")]
    assert bridge._rows == [proposal]
    assert bridge.calls == ["list_pending_proposals"]
    assert editor.proposal_inbox.calls == []
    assert editor.content_revision == 42
    assert len(editor.undo.undo_stack) == 1


def test_open_ai_proposals_inbox_when_tab_already_selected_still_leaves_creator_mode() -> None:
    bridge = FakeBridge([{"proposal_id": "proposal-1"}])
    dock = FakeDock(right_tab="AI Proposals", right_collapsed=True)
    editor = _editor_with_bridge(bridge, proposal_inbox=SimpleNamespace(), dock=dock, active=True)
    controller = CreatorModeController(editor)
    controller.show()

    result = controller.open_ai_proposals_inbox()

    assert result.ok is True
    assert controller.active is False
    assert dock.right_collapsed is False
    assert dock.right_tab == "AI Proposals"
    assert dock.toggle_right_calls == 1
    assert dock.apply_tab_calls == []


def test_open_ai_proposals_inbox_exits_viewport_maximization_before_navigation() -> None:
    bridge = HostileBridge([{"proposal_id": "proposal-1"}])
    dock = FakeDock(right_tab="Inspector", right_collapsed=True, viewport_maximized=True)
    editor = _editor_with_bridge(
        bridge,
        proposal_inbox=HostileInbox(),
        dock=dock,
        active=True,
        content_revision=7,
        undo_stack=[{"type": "HumanEdit"}],
    )
    controller = CreatorModeController(editor)
    controller.show()

    result = controller.open_ai_proposals_inbox()

    assert result.ok is True
    assert controller.active is False
    assert editor.active is True
    assert dock.viewport_maximized is False
    assert dock.right_collapsed is False
    assert dock.right_tab == "AI Proposals"
    assert dock.toggle_right_calls == 1
    assert dock.apply_tab_calls == [("right", "AI Proposals")]
    assert bridge.calls == ["list_pending_proposals"]
    assert editor.proposal_inbox.calls == []
    assert editor.content_revision == 7
    assert len(editor.undo.undo_stack) == 1


def test_open_ai_proposals_inbox_missing_dock_fails_closed() -> None:
    bridge = FakeBridge([{"proposal_id": "proposal-1"}])
    editor = _editor_with_bridge(bridge, proposal_inbox=SimpleNamespace(), dock=None, active=True)
    controller = CreatorModeController(editor)
    controller.show()

    result = controller.open_ai_proposals_inbox()

    assert result.ok is False
    assert result.reason == "missing_dock_controller"
    assert controller.active is True


def test_open_ai_proposals_inbox_missing_inbox_fails_closed_without_dock_change() -> None:
    bridge = FakeBridge([{"proposal_id": "proposal-1"}])
    dock = FakeDock(right_tab="Inspector", right_collapsed=True)
    editor = _editor_with_bridge(bridge, proposal_inbox=None, dock=dock, active=True)
    controller = CreatorModeController(editor)
    controller.show()

    result = controller.open_ai_proposals_inbox()

    assert result.ok is False
    assert result.reason == "missing_proposal_inbox"
    assert controller.active is True
    assert dock.right_collapsed is True
    assert dock.right_tab == "Inspector"


def test_open_ai_proposals_inbox_missing_pending_fails_closed_without_dock_change() -> None:
    dock = FakeDock(right_tab="Inspector", right_collapsed=True)
    editor = _editor_with_bridge(FakeBridge([]), proposal_inbox=SimpleNamespace(), dock=dock, active=True)
    controller = CreatorModeController(editor)
    controller.show()

    result = controller.open_ai_proposals_inbox()

    assert result.ok is False
    assert result.reason == "no_pending_proposals"
    assert controller.active is True
    assert dock.right_collapsed is True
    assert dock.right_tab == "Inspector"


def test_open_ai_proposals_inbox_missing_viewport_seam_fails_closed() -> None:
    dock = MissingViewportDock(right_tab="Inspector", right_collapsed=True)
    editor = _editor_with_bridge(
        FakeBridge([{"proposal_id": "proposal-1"}]),
        proposal_inbox=SimpleNamespace(),
        dock=dock,
        active=True,
        content_revision=8,
        undo_stack=[{"type": "HumanEdit"}],
    )
    controller = CreatorModeController(editor)
    controller.show()

    result = controller.open_ai_proposals_inbox()

    assert result.ok is False
    assert result.reason == "missing_dock_controller"
    assert controller.active is True
    assert dock.right_collapsed is True
    assert dock.right_tab == "Inspector"
    assert editor.content_revision == 8
    assert len(editor.undo.undo_stack) == 1


def test_open_ai_proposals_inbox_failed_viewport_exit_restores_and_keeps_creator_active() -> None:
    dock = FakeDock(right_tab="Inspector", right_collapsed=True, viewport_maximized=True, fail_toggle=True)
    editor = _editor_with_bridge(
        FakeBridge([{"proposal_id": "proposal-1"}]),
        proposal_inbox=SimpleNamespace(),
        dock=dock,
        active=True,
        content_revision=12,
        undo_stack=[{"type": "HumanEdit"}],
    )
    controller = CreatorModeController(editor)
    controller.show()

    result = controller.open_ai_proposals_inbox()

    assert result.ok is False
    assert result.reason == "viewport_restore_failed"
    assert controller.active is True
    assert dock.viewport_maximized is True
    assert dock.right_collapsed is True
    assert dock.right_tab == "Inspector"
    assert editor.content_revision == 12
    assert len(editor.undo.undo_stack) == 1


def test_open_ai_proposals_inbox_apply_tab_failure_restores_and_keeps_creator_active() -> None:
    dock = FakeDock(right_tab="Problems", right_collapsed=False, fail_apply_tab=True)
    editor = _editor_with_bridge(
        FakeBridge([{"proposal_id": "proposal-1"}]),
        proposal_inbox=SimpleNamespace(),
        dock=dock,
        active=True,
        content_revision=14,
        undo_stack=[{"type": "HumanEdit"}],
    )
    controller = CreatorModeController(editor)
    controller.show()

    result = controller.open_ai_proposals_inbox()

    assert result.ok is False
    assert result.reason == "ai_proposals_tab_unavailable"
    assert controller.active is True
    assert dock.right_tab == "Problems"
    assert dock.right_collapsed is False
    assert dock.apply_tab_calls == [("right", "AI Proposals")]
    assert editor.content_revision == 14
    assert len(editor.undo.undo_stack) == 1


def test_open_ai_proposals_inbox_from_problems_uses_real_dock_transition_hooks() -> None:
    bridge = HostileBridge([{"proposal_id": "proposal-1"}])
    host = RealDockHost(bridge, right_tab="Problems", right_collapsed=False)
    controller = CreatorModeController(host)
    controller.show()

    result = controller.open_ai_proposals_inbox()

    assert result.ok is True
    assert controller.active is False
    assert host.active is True
    assert host.dock.right_tab == "AI Proposals"
    assert host.search.sync_calls == 1
    assert host.autosave_count == 1
    assert host.search.focus_target == ""
    assert host.content_revision == 0
    assert host.undo.undo_stack == []
    assert bridge.calls == ["list_pending_proposals"]


def test_open_ai_proposals_inbox_from_history_clears_hidden_search_focus() -> None:
    host = RealDockHost(FakeBridge([{"proposal_id": "proposal-1"}]), right_tab="History", right_collapsed=False)
    host.search.focus_target = "history_search"
    controller = CreatorModeController(host)
    controller.show()

    result = controller.open_ai_proposals_inbox()

    assert result.ok is True
    assert controller.active is False
    assert host.dock.right_tab == "AI Proposals"
    assert host.search.sync_calls == 1
    assert host.search.focus_target == ""
    assert host.text_input_routed_to == "editor"


def test_open_ai_proposals_inbox_already_ai_proposals_collapsed_uses_toggle_persistence() -> None:
    host = RealDockHost(FakeBridge([{"proposal_id": "proposal-1"}]), right_tab="AI Proposals", right_collapsed=True)
    controller = CreatorModeController(host)
    controller.show()

    result = controller.open_ai_proposals_inbox()

    assert result.ok is True
    assert controller.active is False
    assert host.dock.right_tab == "AI Proposals"
    assert host.dock.get_right_collapsed() is False
    assert host.autosave_count == 1
    assert host.search.sync_calls == 0


def _command_text(commands) -> str:
    return "\n".join(command.text for command in commands if command.kind == "text")


def _status_with_pending(count: int) -> CreatorProposalStatusModel:
    proposal_rows = tuple(
        CreatorProposalListRow(proposal_id=f"proposal-{index}", summary=f"Preview {index}")
        for index in range(count)
    )
    return CreatorProposalStatusModel(
        available=True,
        pending_count=count,
        summary=f"{count} proposals waiting for review",
        rows=proposal_rows,
    )


class FakeBridge:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.calls: list[str] = []

    def list_pending_proposals(self) -> list[dict[str, object]]:
        self.calls.append("list_pending_proposals")
        return list(self._rows)


class HostileBridge:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.calls: list[str] = []

    def list_pending_proposals(self) -> list[dict[str, object]]:
        self.calls.append("list_pending_proposals")
        return list(self._rows)

    def stage_pending_proposal(self, ops: list[dict[str, object]]) -> dict[str, object]:
        self.calls.append("stage_pending_proposal")
        raise AssertionError("stage must not be called")

    def accept_pending_proposal(self, proposal_id: str) -> dict[str, object]:
        self.calls.append("accept_pending_proposal")
        raise AssertionError("accept must not be called")

    def reject_pending_proposal(self, proposal_id: str) -> dict[str, object]:
        self.calls.append("reject_pending_proposal")
        raise AssertionError("reject must not be called")

    def apply_live_op(self, op: dict[str, object]) -> dict[str, object]:
        self.calls.append("apply_live_op")
        raise AssertionError("apply must not be called")


class HostileInbox:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def list_pending(self) -> list[dict[str, object]]:
        self.calls.append("list_pending")
        raise AssertionError("list_pending must not be called")

    def accept(self, proposal_id: str) -> dict[str, object]:
        self.calls.append("accept")
        raise AssertionError("accept must not be called")

    def reject(self, proposal_id: str) -> dict[str, object]:
        self.calls.append("reject")
        raise AssertionError("reject must not be called")


def _editor_with_bridge(
    bridge: object,
    *,
    proposal_inbox: object | None = None,
    dock: object | None = _DEFAULT_DOCK,
    active: bool = False,
    content_revision: int = 0,
    undo_stack: list[dict[str, object]] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        active=active,
        selected_entity=None,
        live_bridge=bridge,
        proposal_inbox=proposal_inbox,
        dock=FakeDock() if dock is _DEFAULT_DOCK else dock,
        content_revision=content_revision,
        undo=SimpleNamespace(undo_stack=list(undo_stack or [])),
        window=SimpleNamespace(
            width=1280,
            height=720,
            scene_controller=SimpleNamespace(current_scene_path="forest"),
        ),
    )


def _pending_rows(count: int) -> list[dict[str, object]]:
    return [
        {
            "proposal_id": f"proposal-{index}",
            "preview_summary": f"Preview {index}",
            "affected_ids": [f"entity_{index}"],
            "dry_run": {"ok": True, "affected_ids": [f"entity_{index}"]},
        }
        for index in range(count)
    ]


class FakeDock:
    def __init__(
        self,
        *,
        right_tab: str = "Inspector",
        right_collapsed: bool = False,
        viewport_maximized: bool = False,
        fail_toggle: bool = False,
        fail_expand: bool = False,
        fail_apply_tab: bool = False,
    ) -> None:
        self.right_tab = right_tab
        self.right_collapsed = right_collapsed
        self.viewport_maximized = viewport_maximized
        self.fail_toggle = fail_toggle
        self.fail_expand = fail_expand
        self.fail_apply_tab = fail_apply_tab
        self.apply_tab_calls: list[tuple[str, str]] = []
        self.toggle_right_calls = 0

    def set_right_tab(self, tab: str) -> bool:
        if tab != "AI Proposals":
            return False
        if self.right_tab == tab:
            return False
        self.right_tab = tab
        return True

    def set_right_collapsed(self, value: bool) -> None:
        if self.fail_expand and value is False:
            return
        self.right_collapsed = bool(value)

    def toggle_right_dock(self, _host: object) -> None:
        self.toggle_right_calls += 1
        if self.fail_expand and self.right_collapsed:
            return
        self.right_collapsed = not self.right_collapsed

    def get_right_collapsed(self) -> bool:
        return self.right_collapsed

    def apply_tab_change(self, _host: object, dock: str, tab: str) -> bool:
        self.apply_tab_calls.append((dock, tab))
        if self.fail_apply_tab:
            return False
        if dock != "right" or tab != "AI Proposals":
            return False
        if self.right_tab == tab:
            return False
        self.right_tab = tab
        return True

    def get_viewport_maximized(self) -> bool:
        return self.viewport_maximized

    def toggle_viewport_maximized(self, _host: object) -> None:
        if self.fail_toggle:
            return
        self.viewport_maximized = not self.viewport_maximized


class MissingViewportDock:
    def __init__(self, *, right_tab: str, right_collapsed: bool) -> None:
        self.right_tab = right_tab
        self.right_collapsed = right_collapsed

    def set_right_tab(self, tab: str) -> bool:
        if tab != "AI Proposals":
            return False
        self.right_tab = tab
        return True

    def set_right_collapsed(self, value: bool) -> None:
        self.right_collapsed = bool(value)

    def get_right_collapsed(self) -> bool:
        return self.right_collapsed

    def toggle_right_dock(self, _host: object) -> None:
        self.right_collapsed = not self.right_collapsed

    def apply_tab_change(self, _host: object, dock: str, tab: str) -> bool:
        if dock != "right" or tab != "AI Proposals":
            return False
        self.right_tab = tab
        return True


class MissingApplyTabChangeDock:
    right_tab = "Inspector"

    def __init__(self) -> None:
        self.right_collapsed = False
        self.viewport_maximized = False

    def get_right_collapsed(self) -> bool:
        return self.right_collapsed

    def toggle_right_dock(self, _host: object) -> None:
        self.right_collapsed = not self.right_collapsed

    def get_viewport_maximized(self) -> bool:
        return self.viewport_maximized

    def toggle_viewport_maximized(self, _host: object) -> None:
        self.viewport_maximized = not self.viewport_maximized


class MissingToggleRightDock:
    right_tab = "Inspector"

    def __init__(self) -> None:
        self.right_collapsed = False
        self.viewport_maximized = False

    def get_right_collapsed(self) -> bool:
        return self.right_collapsed

    def get_viewport_maximized(self) -> bool:
        return self.viewport_maximized

    def toggle_viewport_maximized(self, _host: object) -> None:
        self.viewport_maximized = not self.viewport_maximized

    def apply_tab_change(self, _host: object, dock: str, tab: str) -> bool:
        if dock != "right" or tab != "AI Proposals":
            return False
        self.right_tab = tab
        return True


class RealDockSearch:
    def __init__(self) -> None:
        self.sync_calls = 0
        self.focus_target = "right_search"

    def sync_search_focus(self) -> None:
        self.sync_calls += 1
        self.focus_target = ""


class RealDockHost:
    ENTITY_PANEL_FOCUS_INSPECTOR = "inspector"

    def __init__(self, bridge: object, *, right_tab: str, right_collapsed: bool) -> None:
        self.active = True
        self.live_bridge = bridge
        self.proposal_inbox = HostileInbox()
        self.dock = EditorDockController(None, left_tab="Outliner", right_tab=right_tab, right_collapsed=right_collapsed)
        self.search = RealDockSearch()
        self.problems = SimpleNamespace(
            preview_open=True,
            close_preview=lambda _host: setattr(self.problems, "preview_open", False),
        )
        self.panels = SimpleNamespace(close_context_menu=lambda: setattr(self, "context_closed", True))
        self.history = SimpleNamespace(on_open_tab=lambda: setattr(self, "history_opened", True))
        self.entity_panels_active = False
        self.entity_panels_focus = ""
        self.asset_browser_active = False
        self._problems_issues = ["issue"]
        self.context_closed = False
        self.autosave_count = 0
        self.content_revision = 0
        self.undo = SimpleNamespace(undo_stack=[])
        self.text_input_routed_to = "history_search"
        self.window = SimpleNamespace(width=1280, height=720, scene_controller=SimpleNamespace(current_scene_path="forest"))

    def _autosave_workspace(self) -> None:
        self.autosave_count += 1
        self.text_input_routed_to = "editor"

    def scan_scene_problems(self) -> None:
        self._problems_issues = ["scanned"]
