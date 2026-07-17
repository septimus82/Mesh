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


def test_handoff_draw_commands_stay_inside_bottom_panel_at_required_sizes() -> None:
    for width, height in ((1280, 720), (1024, 576), (320, 240)):
        controller = CreatorModeController(
            _editor_with_bridge(FakeBridge([{"proposal_id": "proposal-1"}]), proposal_inbox=SimpleNamespace())
        )
        controller.show()
        commands = build_creator_overlay_draw_commands(
            build_creator_overlay_model(controller.build_snapshot()),
            width,
            height,
        )
        bottom = next(command for command in commands if command.kind == "rect" and command.region == "bottom")
        targets = [command for command in commands if command.action_id == PROPOSAL_OPEN_INBOX_ACTION_ID]

        assert len(targets) == 1
        target = targets[0]
        assert bottom.x - bottom.width / 2 <= target.hit_left <= target.hit_right <= bottom.x + bottom.width / 2
        assert bottom.y - bottom.height / 2 <= target.hit_bottom <= target.hit_top <= bottom.y + bottom.height / 2


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


class FakeDock:
    def __init__(
        self,
        *,
        right_tab: str = "Inspector",
        right_collapsed: bool = False,
        viewport_maximized: bool = False,
        fail_toggle: bool = False,
        fail_expand: bool = False,
    ) -> None:
        self.right_tab = right_tab
        self.right_collapsed = right_collapsed
        self.viewport_maximized = viewport_maximized
        self.fail_toggle = fail_toggle
        self.fail_expand = fail_expand

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

    def get_right_collapsed(self) -> bool:
        return self.right_collapsed

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
