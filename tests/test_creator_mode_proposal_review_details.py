from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.editor.creator_mode import (
    CreatorModeController,
    build_creator_overlay_model,
    build_creator_proposal_review_details,
    build_creator_proposal_review_details_from_status,
)
from engine.editor.creator_mode.creator_overlay_renderer import build_creator_overlay_draw_commands
from engine.editor.creator_mode.creator_proposal_status import (
    CreatorProposalListRow,
    CreatorProposalStatusModel,
)

pytestmark = pytest.mark.fast


def test_unavailable_status_returns_unavailable_details_model() -> None:
    model = build_creator_proposal_review_details_from_status(
        CreatorProposalStatusModel(
            available=False,
            pending_count=0,
            summary="Proposal review status unavailable.",
            warnings=("Bridge unavailable.",),
        )
    )

    assert model.available is False
    assert model.details == ()
    assert model.summary == "Proposal review details unavailable."
    assert model.warnings == ("Bridge unavailable.",)


def test_zero_rows_returns_available_empty_model() -> None:
    model = build_creator_proposal_review_details_from_status(
        CreatorProposalStatusModel(
            available=True,
            pending_count=0,
            summary="No staged proposals.",
            rows=(),
        )
    )

    assert model.available is True
    assert model.details == ()
    assert model.summary == "No proposal details to show."


def test_valid_row_creates_detail_with_proposal_id_and_summary() -> None:
    model = build_creator_proposal_review_details_from_status(
        CreatorProposalStatusModel(
            available=True,
            pending_count=1,
            summary="1 proposal waiting for review",
            rows=(CreatorProposalListRow("proposal-1", "Set SceneExit params"),),
        )
    )

    assert model.summary == "1 proposal detail ready."
    assert model.details[0].proposal_id == "proposal-1"
    assert model.details[0].summary == "Set SceneExit params"


def test_affected_ids_list_is_sanitized_to_tuple() -> None:
    model = build_creator_proposal_review_details(
        FakeBridge(
            [
                {
                    "proposal_id": "proposal-1",
                    "affected_ids": ["door_north", 123, "", None, "  door_south  "],
                }
            ]
        )
    )

    assert model.details[0].affected_ids == ("door_north", "123", "door_south")


def test_malformed_affected_ids_becomes_empty_tuple() -> None:
    model = build_creator_proposal_review_details(
        FakeBridge([{"proposal_id": "proposal-1", "affected_ids": "door_north"}])
    )

    assert model.details[0].affected_ids == ()


def test_dry_run_ok_true_and_false_are_captured() -> None:
    model = build_creator_proposal_review_details(
        FakeBridge(
            [
                {"proposal_id": "proposal-1", "dry_run": {"ok": True}},
                {"proposal_id": "proposal-2", "dry_run": {"success": False}},
            ]
        )
    )

    assert tuple(detail.dry_run_ok for detail in model.details) == (True, False)


def test_dry_run_warnings_and_errors_are_sanitized() -> None:
    model = build_creator_proposal_review_details(
        FakeBridge(
            [
                {
                    "proposal_id": "proposal-1",
                    "dry_run": {
                        "warnings": ["warn", 42, "", None],
                        "errors": ["error", {"code": "E"}, ""],
                    },
                }
            ]
        )
    )

    assert model.details[0].warnings == ("warn", "42")
    assert model.details[0].errors == ("error", "{'code': 'E'}")


def test_malformed_dry_run_fails_closed_without_crash() -> None:
    model = build_creator_proposal_review_details(
        FakeBridge([{"proposal_id": "proposal-1", "dry_run": "not a dict"}])
    )

    assert model.details[0].dry_run_ok is None
    assert model.details[0].warnings == ("Dry-run details unavailable.",)
    assert model.details[0].errors == ()


def test_missing_proposal_id_fallback_remains_safe() -> None:
    model = build_creator_proposal_review_details(FakeBridge([{"preview_summary": "Preview"}]))

    assert model.details[0].proposal_id == "proposal"
    assert model.details[0].summary == "Preview"


def test_from_status_builder_does_not_call_bridge() -> None:
    bridge = HostileBridge([{"proposal_id": "proposal-1"}])

    model = build_creator_proposal_review_details_from_status(
        CreatorProposalStatusModel(
            available=True,
            pending_count=1,
            summary="1 proposal waiting for review",
            rows=(CreatorProposalListRow("proposal-1", "Preview"),),
        )
    )

    assert model.available is True
    assert bridge.calls == []


def test_compatibility_bridge_wrapper_calls_list_pending_proposals_once() -> None:
    bridge = FakeBridge([{"proposal_id": "proposal-1"}])

    model = build_creator_proposal_review_details(bridge)

    assert model.available is True
    assert bridge.calls == ["list_pending_proposals"]


def test_hostile_bridge_proves_no_accept_reject_apply_or_stage_calls() -> None:
    bridge = HostileBridge([{"proposal_id": "proposal-1"}])

    model = build_creator_proposal_review_details(bridge)

    assert model.available is True
    assert bridge.calls == ["list_pending_proposals"]


def test_snapshot_includes_review_details_derived_from_status() -> None:
    bridge = FakeBridge(
        [
            {
                "proposal_id": "proposal-1",
                "preview_summary": "Preview",
                "affected_ids": ["door_north"],
                "dry_run": {"ok": True},
            }
        ]
    )
    controller = CreatorModeController(_editor_with_bridge(bridge))
    controller.show()

    snapshot = controller.build_snapshot()

    assert snapshot.proposal_review_details.details[0].proposal_id == "proposal-1"
    assert snapshot.proposal_review_details.details[0].affected_ids == ("door_north",)
    assert snapshot.proposal_review_details.details[0].dry_run_ok is True
    assert bridge.calls == ["list_pending_proposals"]


def test_overlay_model_includes_proposal_review_details() -> None:
    controller = CreatorModeController(
        _editor_with_bridge(FakeBridge([{"proposal_id": "proposal-1", "affected_ids": ["door_north"]}]))
    )
    controller.show()

    model = build_creator_overlay_model(controller.build_snapshot())

    assert model.proposal_review_details.details[0].proposal_id == "proposal-1"
    assert model.proposal_review_details.details[0].affected_ids == ("door_north",)


def test_render_shows_affected_id_detail_for_valid_proposal() -> None:
    text = _render_text(
        FakeBridge(
            [
                {
                    "proposal_id": "proposal-1",
                    "affected_ids": ["door_north"],
                    "dry_run": {"ok": True},
                }
            ]
        )
    )

    assert "Details: Affects door_north - Dry-run OK - W0/E0" in text


def test_render_shows_affects_none_for_no_affected_ids() -> None:
    text = _render_text(FakeBridge([{"proposal_id": "proposal-1"}]))

    assert "Details: Affects none - Dry-run Unknown - W0/E0" in text


def test_render_shows_dry_run_ok_failed_and_unknown() -> None:
    text = _render_text(
        FakeBridge(
            [
                {"proposal_id": "proposal-1", "dry_run": {"ok": True}},
                {"proposal_id": "proposal-2", "dry_run": {"ok": False}},
                {"proposal_id": "proposal-3"},
            ]
        )
    )

    assert "Details: Affects none - Dry-run OK - W0/E0" in text
    assert "Details: Affects none - Dry-run Failed - W0/E0" in text
    assert "Details: Affects none - Dry-run Unknown - W0/E0" in text


def test_render_shows_warning_and_error_counts() -> None:
    text = _render_text(
        FakeBridge(
            [
                {
                    "proposal_id": "proposal-1",
                    "dry_run": {
                        "ok": False,
                        "warnings": ["warn"],
                        "errors": ["error-1", "error-2"],
                    },
                }
            ]
        )
    )

    assert "Details: Affects none - Dry-run Failed - W1/E2" in text


def test_rendered_detail_line_has_no_action_id_or_hitbox() -> None:
    commands = _render_commands(
        FakeBridge(
            [
                {
                    "proposal_id": "proposal-1",
                    "affected_ids": ["door_north"],
                    "dry_run": {"ok": True},
                }
            ]
        )
    )
    detail_commands = [
        command
        for command in commands
        if command.text == "Details: Affects door_north - Dry-run OK - W0/E0"
    ]

    assert len(detail_commands) == 1
    assert detail_commands[0].action_id == ""
    assert detail_commands[0].hit_left == 0.0
    assert detail_commands[0].hit_right == 0.0
    assert detail_commands[0].hit_top == 0.0
    assert detail_commands[0].hit_bottom == 0.0


def test_more_than_three_proposals_only_render_details_for_first_three() -> None:
    text = _render_text(
        FakeBridge(
            [
                {
                    "proposal_id": f"proposal-{index}",
                    "preview_summary": f"Preview {index}",
                    "affected_ids": [f"entity_{index}"],
                }
                for index in range(5)
            ]
        )
    )

    assert text.count("Details: Affects entity_") == 3
    assert "Details: Affects entity_0 - Dry-run Unknown - W0/E0" in text
    assert "Details: Affects entity_1 - Dry-run Unknown - W0/E0" in text
    assert "Details: Affects entity_2 - Dry-run Unknown - W0/E0" in text
    assert "Details: Affects entity_3 - Dry-run Unknown - W0/E0" not in text
    assert "...and 2 more" in text


def test_snapshot_model_and_render_do_not_accept_reject_apply_or_stage() -> None:
    bridge = HostileBridge(
        [
            {
                "proposal_id": "proposal-1",
                "affected_ids": ["door_north"],
                "dry_run": {"ok": True},
            }
        ]
    )

    text = _render_text(bridge)

    assert "Review: Use AI Proposals" in text
    assert "Details: Affects door_north - Dry-run OK - W0/E0" in text
    assert bridge.calls == ["list_pending_proposals"]


def test_review_details_module_imports_without_arcade() -> None:
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
                "'engine.editor.creator_mode.creator_proposal_review_details', "
                "root / 'creator_proposal_review_details.py'); "
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


def test_review_details_module_does_not_import_real_bridge_modules() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from engine.editor.creator_mode.creator_proposal_review_details "
                "import build_creator_proposal_review_details; "
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
        window=SimpleNamespace(
            width=1280,
            height=720,
            scene_controller=SimpleNamespace(current_scene_path="forest"),
        ),
    )
    if include_proposal_inbox:
        editor.proposal_inbox = SimpleNamespace()
    return editor


def _render_commands(bridge: object):
    controller = CreatorModeController(_editor_with_bridge(bridge))
    controller.show()
    return build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )


def _render_text(bridge: object) -> str:
    return "\n".join(command.text for command in _render_commands(bridge) if command.kind == "text")
