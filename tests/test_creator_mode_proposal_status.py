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


def test_fake_bridge_with_one_pending_shows_singular_text() -> None:
    status = build_creator_proposal_status(FakeBridge([{"proposal_id": "proposal-1"}]))

    assert status.available is True
    assert status.pending_count == 1
    assert status.summary == "1 proposal waiting for review"


def test_fake_bridge_with_multiple_pending_shows_plural_text() -> None:
    rows = [{"proposal_id": f"proposal-{index}"} for index in range(3)]
    status = build_creator_proposal_status(FakeBridge(rows))

    assert status.available is True
    assert status.pending_count == 3
    assert status.summary == "3 proposals waiting for review"


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
