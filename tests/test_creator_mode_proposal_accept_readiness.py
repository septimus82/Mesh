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
    build_creator_proposal_accept_readiness,
    build_creator_proposal_accept_readiness_from_status,
)
from engine.editor.creator_mode.creator_overlay_renderer import build_creator_overlay_draw_commands
from engine.editor.creator_mode.creator_proposal_status import (
    CreatorProposalListRow,
    CreatorProposalStatusModel,
)

pytestmark = pytest.mark.fast


def test_no_bridge_returns_unavailable_model() -> None:
    model = build_creator_proposal_accept_readiness(None)

    assert model.available is False
    assert model.rows == ()
    assert model.summary == "Proposal review actions unavailable."
    assert model.warnings == ()


def test_zero_pending_rows_returns_available_empty_model() -> None:
    bridge = FakeBridge([])

    model = build_creator_proposal_accept_readiness(bridge)

    assert model.available is True
    assert model.rows == ()
    assert model.summary == "No proposals waiting for review."
    assert bridge.calls == ["list_pending_proposals"]


def test_one_valid_proposal_row_creates_enabled_review_actions() -> None:
    model = build_creator_proposal_accept_readiness(
        FakeBridge(
            [
                {
                    "proposal_id": "proposal-1",
                    "preview_summary": "Set SceneExit params on door_north",
                }
            ]
        )
    )

    row = model.rows[0]
    assert model.available is True
    assert model.summary == "1 proposal can be reviewed."
    assert row.proposal_id == "proposal-1"
    assert row.summary == "Set SceneExit params on door_north"
    assert row.accept_action.label == "Accept"
    assert row.accept_action.enabled is True
    assert row.accept_action.reason == ""
    assert row.reject_action.label == "Reject"
    assert row.reject_action.enabled is True
    assert row.reject_action.reason == ""


def test_multiple_proposal_rows_create_multiple_review_rows() -> None:
    model = build_creator_proposal_accept_readiness(
        FakeBridge(
            [
                {"proposal_id": "proposal-1", "preview_summary": "First"},
                {"proposal_id": "proposal-2", "preview_summary": "Second"},
            ]
        )
    )

    assert model.summary == "2 proposals can be reviewed."
    assert tuple(row.proposal_id for row in model.rows) == ("proposal-1", "proposal-2")
    assert all(row.accept_action.enabled for row in model.rows)
    assert all(row.reject_action.enabled for row in model.rows)


def test_missing_proposal_id_disables_review_actions_with_reason() -> None:
    model = build_creator_proposal_accept_readiness(
        FakeBridge([{"preview_summary": "Missing proposal id"}])
    )

    row = model.rows[0]
    assert row.proposal_id == "proposal"
    assert row.accept_action.enabled is False
    assert row.accept_action.reason == "Missing proposal id"
    assert row.reject_action.enabled is False
    assert row.reject_action.reason == "Missing proposal id"


def test_malformed_rows_do_not_crash() -> None:
    model = build_creator_proposal_accept_readiness(FakeBridge([None, "bad"]))

    assert model.available is True
    assert len(model.rows) == 2
    assert tuple(row.proposal_id for row in model.rows) == ("proposal", "proposal")
    assert all(not row.accept_action.enabled for row in model.rows)
    assert all(not row.reject_action.enabled for row in model.rows)


def test_model_does_not_call_accept_reject_apply_or_stage() -> None:
    bridge = HostileBridge([{"proposal_id": "proposal-1"}])

    model = build_creator_proposal_accept_readiness(bridge)

    assert model.available is True
    assert bridge.calls == ["list_pending_proposals"]


def test_broken_bridge_fails_closed_with_warning() -> None:
    model = build_creator_proposal_accept_readiness(BrokenBridge())

    assert model.available is False
    assert model.summary == "Proposal review actions unavailable."
    assert model.warnings


def test_from_status_unavailable_status_returns_unavailable_model() -> None:
    model = build_creator_proposal_accept_readiness_from_status(
        CreatorProposalStatusModel(
            available=False,
            pending_count=0,
            summary="Proposal review status unavailable.",
            warnings=("Bridge unavailable.",),
        )
    )

    assert model.available is False
    assert model.summary == "Proposal review actions unavailable."
    assert model.warnings == ("Bridge unavailable.",)


def test_from_status_zero_rows_returns_available_empty_model() -> None:
    model = build_creator_proposal_accept_readiness_from_status(
        CreatorProposalStatusModel(
            available=True,
            pending_count=0,
            summary="No staged proposals.",
            rows=(),
        )
    )

    assert model.available is True
    assert model.rows == ()
    assert model.summary == "No proposals waiting for review."


def test_from_status_valid_proposal_row_creates_enabled_actions() -> None:
    model = build_creator_proposal_accept_readiness_from_status(
        CreatorProposalStatusModel(
            available=True,
            pending_count=1,
            summary="1 proposal waiting for review",
            rows=(CreatorProposalListRow("proposal-1", "Preview"),),
        )
    )

    assert model.rows[0].proposal_id == "proposal-1"
    assert model.rows[0].accept_action.enabled is True
    assert model.rows[0].reject_action.enabled is True


def test_from_status_missing_proposal_id_row_creates_disabled_actions() -> None:
    model = build_creator_proposal_accept_readiness_from_status(
        CreatorProposalStatusModel(
            available=True,
            pending_count=1,
            summary="1 proposal waiting for review",
            rows=(CreatorProposalListRow("proposal", "Preview"),),
        )
    )

    assert model.rows[0].proposal_id == "proposal"
    assert model.rows[0].accept_action.enabled is False
    assert model.rows[0].accept_action.reason == "Missing proposal id"
    assert model.rows[0].reject_action.enabled is False
    assert model.rows[0].reject_action.reason == "Missing proposal id"


def test_build_snapshot_reads_pending_proposals_once() -> None:
    bridge = FakeBridge([{"proposal_id": "proposal-1"}])
    controller = CreatorModeController(_editor_with_bridge(bridge))
    controller.show()

    snapshot = controller.build_snapshot()

    assert snapshot.proposal_status.rows[0].proposal_id == "proposal-1"
    assert snapshot.proposal_accept_readiness.rows[0].proposal_id == "proposal-1"
    assert bridge.calls == ["list_pending_proposals"]


def test_snapshot_includes_accept_readiness_model() -> None:
    controller = CreatorModeController(_editor_with_bridge(FakeBridge([{"proposal_id": "proposal-1"}])))
    controller.show()

    snapshot = controller.build_snapshot()

    assert snapshot.proposal_accept_readiness.available is True
    assert snapshot.proposal_accept_readiness.rows[0].proposal_id == "proposal-1"


def test_overlay_model_includes_accept_readiness_model() -> None:
    controller = CreatorModeController(_editor_with_bridge(FakeBridge([{"proposal_id": "proposal-1"}])))
    controller.show()

    model = build_creator_overlay_model(controller.build_snapshot())

    assert model.proposal_accept_readiness.available is True
    assert model.proposal_accept_readiness.rows[0].accept_action.enabled is True


def test_render_shows_handoff_label_when_inbox_available() -> None:
    controller = CreatorModeController(_editor_with_bridge(FakeBridge([{"proposal_id": "proposal-1"}])))
    controller.show()

    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )

    text = _command_text(commands)

    assert "Review in AI Proposals" in text
    assert "Review: Use AI Proposals" not in text


def test_render_shows_unavailable_handoff_when_inbox_missing() -> None:
    controller = CreatorModeController(
        _editor_with_bridge(FakeBridge([{"proposal_id": "proposal-1"}]), include_proposal_inbox=False)
    )
    controller.show()

    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )

    assert "AI Proposals unavailable - AI Proposals inbox unavailable" in _command_text(commands)


def test_rendered_enabled_handoff_line_has_action_id_and_hitbox() -> None:
    controller = CreatorModeController(_editor_with_bridge(FakeBridge([{"proposal_id": "proposal-1"}])))
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


def test_zero_pending_proposals_does_not_render_handoff_line() -> None:
    controller = CreatorModeController(_editor_with_bridge(FakeBridge([])))
    controller.show()

    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )
    text = _command_text(commands)

    assert "Review in AI Proposals" not in text
    assert "AI Proposals unavailable" not in text


def test_render_shows_unavailable_reason_for_missing_proposal_id_without_inbox() -> None:
    controller = CreatorModeController(
        _editor_with_bridge(FakeBridge([{"preview_summary": "Preview"}]), include_proposal_inbox=False)
    )
    controller.show()

    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )

    assert "AI Proposals unavailable - AI Proposals inbox unavailable" in _command_text(commands)


def test_more_than_three_pending_proposals_render_one_handoff_line() -> None:
    controller = CreatorModeController(
        _editor_with_bridge(
            FakeBridge(
                [
                    {"proposal_id": f"proposal-{index}", "preview_summary": f"Preview {index}"}
                    for index in range(5)
                ]
            )
        )
    )
    controller.show()

    text = _command_text(
        build_creator_overlay_draw_commands(
            build_creator_overlay_model(controller.build_snapshot()),
            1280,
            720,
        )
    )

    assert text.count("Review in AI Proposals") == 1
    assert "proposal-0 - Preview 0" in text
    assert "proposal-1 - Preview 1" in text
    assert "proposal-2 - Preview 2" in text
    assert "proposal-3 - Preview 3" not in text
    assert "...and 2 more" in text


def test_snapshot_model_and_render_do_not_accept_reject_apply_or_stage() -> None:
    bridge = HostileBridge([{"proposal_id": "proposal-1"}])
    controller = CreatorModeController(_editor_with_bridge(bridge))
    controller.show()

    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )

    text = _command_text(commands)

    assert "Review in AI Proposals" in text
    assert "Review: Use AI Proposals" not in text
    assert bridge.calls == ["list_pending_proposals"]


def test_accept_readiness_module_imports_without_arcade() -> None:
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
                "'engine.editor.creator_mode.creator_proposal_accept_readiness', "
                "root / 'creator_proposal_accept_readiness.py'); "
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


def test_accept_readiness_module_does_not_import_real_bridge_modules() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from engine.editor.creator_mode.creator_proposal_accept_readiness "
                "import build_creator_proposal_accept_readiness; "
                "blocked = ["
                "'engine.editor.live_session_bridge', "
                "'engine.editor.editor_live_ops_controller', "
                "'engine.editor.proposal_inbox'"
                "]; "
                "print(any(name in sys.modules for name in blocked))"
            ),
        ],
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stdout.strip() == "False"


def test_package_import_still_does_not_eagerly_import_renderer() -> None:
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


class FakeBridge:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows
        self.calls: list[str] = []

    def list_pending_proposals(self) -> list[object]:
        self.calls.append("list_pending_proposals")
        return list(self._rows)


class BrokenBridge:
    def list_pending_proposals(self) -> list[dict[str, object]]:
        raise RuntimeError("bridge read failed")


class HostileBridge(FakeBridge):
    def accept_pending_proposal(self, proposal_id: str) -> dict[str, object]:
        raise AssertionError("accept must not be called")

    def reject_pending_proposal(self, proposal_id: str) -> dict[str, object]:
        raise AssertionError("reject must not be called")

    def apply_live_op(self, op: dict[str, object]) -> dict[str, object]:
        raise AssertionError("apply must not be called")

    def stage_pending_proposal(self, ops: list[dict[str, object]]) -> dict[str, object]:
        raise AssertionError("stage must not be called")


def _editor_with_bridge(bridge: object, *, include_proposal_inbox: bool = True) -> SimpleNamespace:
    editor = SimpleNamespace(
        selected_entity=None,
        live_bridge=bridge,
        dock=FakeDock(),
        window=SimpleNamespace(
            width=1280,
            height=720,
            scene_controller=SimpleNamespace(current_scene_path="forest"),
        ),
    )
    if include_proposal_inbox:
        editor.proposal_inbox = SimpleNamespace()
    return editor


def _command_text(commands) -> str:
    return "\n".join(command.text for command in commands if command.kind == "text")


class FakeDock:
    right_tab = "Inspector"

    def __init__(self) -> None:
        self.right_collapsed = False
        self.viewport_maximized = False

    def get_right_collapsed(self) -> bool:
        return self.right_collapsed

    def toggle_right_dock(self, _host: object) -> None:
        self.right_collapsed = not self.right_collapsed

    def apply_tab_change(self, _host: object, dock: str, tab: str) -> bool:
        if dock != "right" or tab != "AI Proposals":
            return False
        self.right_tab = tab
        return True

    def get_viewport_maximized(self) -> bool:
        return self.viewport_maximized

    def toggle_viewport_maximized(self, _host: object) -> None:
        self.viewport_maximized = not self.viewport_maximized
