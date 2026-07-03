from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.editor.creator_mode import (
    CreatorModeController,
    build_creator_overlay_model,
    build_creator_proposal_status,
)
from engine.editor.creator_mode import creator_door_staging
from engine.editor.creator_mode.creator_overlay_renderer import build_creator_overlay_draw_commands

pytestmark = pytest.mark.fast


def test_bridge_missing_shows_unavailable_status() -> None:
    status = build_creator_proposal_status(None)

    assert status.available is False
    assert status.pending_count == 0
    assert status.summary == "Proposal review status unavailable."
    assert status.warnings == ()


def test_fake_bridge_with_zero_pending_shows_no_staged_proposals() -> None:
    status = build_creator_proposal_status(FakeBridge([]))

    assert status.available is True
    assert status.pending_count == 0
    assert status.summary == "No staged proposals."
    assert status.rows == ()


def test_fake_bridge_with_one_pending_shows_singular_text() -> None:
    status = build_creator_proposal_status(
        FakeBridge(
            [
                {
                    "proposal_id": "proposal-1",
                    "preview_summary": "Set SceneExit params on door_north",
                    "affected_ids": ["door_north"],
                }
            ]
        )
    )

    assert status.available is True
    assert status.pending_count == 1
    assert status.summary == "1 proposal waiting for review"
    assert len(status.rows) == 1
    assert status.rows[0].proposal_id == "proposal-1"
    assert status.rows[0].summary == "Set SceneExit params on door_north"
    assert status.rows[0].affected_count == 1


def test_fake_bridge_with_multiple_pending_shows_plural_text() -> None:
    rows = [
        {"proposal_id": f"proposal-{index}", "preview_summary": f"Preview {index}"}
        for index in range(3)
    ]
    status = build_creator_proposal_status(FakeBridge(rows))

    assert status.available is True
    assert status.pending_count == 3
    assert status.summary == "3 proposals waiting for review"
    assert tuple(row.proposal_id for row in status.rows) == ("proposal-0", "proposal-1", "proposal-2")


def test_more_than_three_pending_renders_and_more_text() -> None:
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

    assert "proposal-0 - Preview 0" in text
    assert "proposal-1 - Preview 1" in text
    assert "proposal-2 - Preview 2" in text
    assert "proposal-3 - Preview 3" not in text
    assert "...and 2 more" in text


def test_malformed_pending_rows_do_not_crash() -> None:
    status = build_creator_proposal_status(FakeBridge([None, "bad", {"proposal_id": "proposal-1"}]))

    assert status.available is True
    assert status.pending_count == 3
    assert tuple(row.proposal_id for row in status.rows) == ("proposal", "proposal", "proposal-1")


def test_missing_proposal_id_fallback_works() -> None:
    status = build_creator_proposal_status(FakeBridge([{"preview_summary": "Preview"}]))

    assert status.rows[0].proposal_id == "proposal"


def test_missing_preview_summary_fallback_works() -> None:
    status = build_creator_proposal_status(FakeBridge([{"proposal_id": "proposal-1"}]))

    assert status.rows[0].summary == "No preview summary"


def test_affected_ids_count_works_when_list() -> None:
    status = build_creator_proposal_status(
        FakeBridge([{"proposal_id": "proposal-1", "affected_ids": ["a", "b"]}])
    )

    assert status.rows[0].affected_count == 2


def test_affected_ids_malformed_becomes_zero() -> None:
    status = build_creator_proposal_status(
        FakeBridge([{"proposal_id": "proposal-1", "affected_ids": "door_north"}])
    )

    assert status.rows[0].affected_count == 0


def test_malformed_bridge_read_error_fails_closed_without_crash() -> None:
    status = build_creator_proposal_status(BrokenBridge())

    assert status.available is False
    assert status.summary == "Proposal review status unavailable."
    assert status.warnings


def test_bridge_without_list_pending_proposals_is_unavailable() -> None:
    status = build_creator_proposal_status(SimpleNamespace(stage_pending_proposal=lambda ops: {"ok": True}))

    assert status.available is False
    assert status.summary == "Proposal review status unavailable."


def test_snapshot_includes_proposal_status() -> None:
    controller = CreatorModeController(_editor_with_bridge(FakeBridge([{"proposal_id": "proposal-1"}])))
    controller.show()

    snapshot = controller.build_snapshot()

    assert snapshot.proposal_status.summary == "1 proposal waiting for review"


def test_overlay_model_includes_proposal_status() -> None:
    controller = CreatorModeController(_editor_with_bridge(FakeBridge([])))
    controller.show()

    model = build_creator_overlay_model(controller.build_snapshot())

    assert model.proposal_status.summary == "No staged proposals."


def test_render_includes_proposal_status_text_without_action_id() -> None:
    controller = CreatorModeController(_editor_with_bridge(FakeBridge([{"proposal_id": "proposal-1"}])))
    controller.show()

    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )
    status_commands = [
        command
        for command in commands
        if command.text == "1 proposal waiting for review"
    ]

    assert len(status_commands) == 1
    assert status_commands[0].action_id == ""
    assert status_commands[0].hit_left == 0.0
    assert status_commands[0].hit_right == 0.0


def test_snapshot_model_and_render_include_pending_proposal_row_text() -> None:
    controller = CreatorModeController(
        _editor_with_bridge(
            FakeBridge(
                [
                    {
                        "proposal_id": "proposal-1",
                        "preview_summary": "Set SceneExit params on door_north",
                    }
                ]
            )
        )
    )
    controller.show()

    snapshot = controller.build_snapshot()
    model = build_creator_overlay_model(snapshot)
    commands = build_creator_overlay_draw_commands(model, 1280, 720)

    assert snapshot.proposal_status.rows[0].summary == "Set SceneExit params on door_north"
    assert model.proposal_status.rows[0].proposal_id == "proposal-1"
    assert "proposal-1 - Set SceneExit params on door_north" in _command_text(commands)


def test_rendered_proposal_rows_have_no_action_id_or_hitbox() -> None:
    controller = CreatorModeController(
        _editor_with_bridge(
            FakeBridge(
                [
                    {
                        "proposal_id": "proposal-1",
                        "preview_summary": "Set SceneExit params on door_north",
                    }
                ]
            )
        )
    )
    controller.show()

    commands = build_creator_overlay_draw_commands(
        build_creator_overlay_model(controller.build_snapshot()),
        1280,
        720,
    )
    row_commands = [
        command for command in commands if command.text == "proposal-1 - Set SceneExit params on door_north"
    ]

    assert len(row_commands) == 1
    assert row_commands[0].action_id == ""
    assert row_commands[0].hit_left == 0.0
    assert row_commands[0].hit_right == 0.0
    assert row_commands[0].hit_top == 0.0
    assert row_commands[0].hit_bottom == 0.0


def test_long_pending_proposal_row_is_truncated() -> None:
    long_summary = "Set SceneExit params on door_north " * 8
    controller = CreatorModeController(
        _editor_with_bridge(
            FakeBridge([{"proposal_id": "proposal-1", "preview_summary": long_summary}])
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

    assert long_summary not in text
    assert "proposal-1 - Set SceneExit params on door_north" in text
    assert "..." in text


def test_build_snapshot_does_not_stage(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args, **_kwargs):
        raise AssertionError("build_snapshot must not stage")

    monkeypatch.setattr(creator_door_staging, "stage_creator_door_proposal", fail)
    controller = CreatorModeController(_editor_with_bridge(FakeBridge([])))
    controller.show()

    controller.build_snapshot()


def test_build_snapshot_does_not_accept_reject_or_apply() -> None:
    controller = CreatorModeController(_editor_with_bridge(HostileBridge([])))
    controller.show()

    controller.build_snapshot()


def test_pure_proposal_status_module_does_not_import_arcade() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import importlib.util, sys; "
                "from pathlib import Path; "
                "path = Path('engine/editor/creator_mode/creator_proposal_status.py'); "
                "spec = importlib.util.spec_from_file_location('_creator_proposal_status_isolated', path); "
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


def test_pure_proposal_status_module_does_not_import_real_bridge_modules() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from engine.editor.creator_mode.creator_proposal_status "
                "import build_creator_proposal_status; "
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


class FakeBridge:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows
        self.calls: list[str] = []

    def list_pending_proposals(self) -> list[dict[str, object]]:
        self.calls.append("list_pending_proposals")
        return list(self._rows)

    def stage_pending_proposal(self, ops: list[dict[str, object]]) -> dict[str, object]:
        self.calls.append("stage_pending_proposal")
        return {"ok": True, "proposal_id": "proposal-1", "preview": "ok"}


class BrokenBridge:
    def list_pending_proposals(self) -> list[dict[str, object]]:
        raise RuntimeError("bridge read failed")


class HostileBridge:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def list_pending_proposals(self) -> list[dict[str, object]]:
        return list(self._rows)

    def accept_pending_proposal(self, proposal_id: str) -> dict[str, object]:
        raise AssertionError("accept must not be called")

    def reject_pending_proposal(self, proposal_id: str) -> dict[str, object]:
        raise AssertionError("reject must not be called")

    def apply_live_op(self, op: dict[str, object]) -> dict[str, object]:
        raise AssertionError("apply must not be called")

    def stage_pending_proposal(self, ops: list[dict[str, object]]) -> dict[str, object]:
        raise AssertionError("stage must not be called")


def _editor_with_bridge(bridge: object) -> SimpleNamespace:
    return SimpleNamespace(
        selected_entity=None,
        live_bridge=bridge,
        window=SimpleNamespace(
            width=1280,
            height=720,
            scene_controller=SimpleNamespace(current_scene_path="forest"),
        ),
    )


def _command_text(commands) -> str:
    return "\n".join(command.text for command in commands if command.kind == "text")
