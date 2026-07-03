from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from engine.editor.creator_mode import (
    CreatorModeController,
    build_creator_overlay_model,
    build_creator_proposal_handoff,
)
from engine.editor.creator_mode.creator_proposal_status import (
    CreatorProposalStatusModel,
    unavailable_creator_proposal_status,
)

pytestmark = pytest.mark.fast


def test_pending_proposals_with_proposal_inbox_is_available() -> None:
    status = _status_with_pending(2)
    editor = SimpleNamespace(proposal_inbox=SimpleNamespace())

    handoff = build_creator_proposal_handoff(editor, status)

    assert handoff.available is True
    assert handoff.label == "Review in AI Proposals"
    assert handoff.reason == ""
    assert handoff.pending_count == 2


def test_pending_proposals_without_proposal_inbox_is_unavailable() -> None:
    status = _status_with_pending(1)

    handoff = build_creator_proposal_handoff(SimpleNamespace(live_bridge=object()), status)

    assert handoff.available is False
    assert handoff.label == "Review in AI Proposals"
    assert handoff.reason == "AI Proposals inbox unavailable"
    assert handoff.pending_count == 1


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


def test_unavailable_proposal_status_shows_review_unavailable() -> None:
    status = unavailable_creator_proposal_status(warnings=("Bridge read failed.",))

    handoff = build_creator_proposal_handoff(SimpleNamespace(proposal_inbox=SimpleNamespace()), status)

    assert handoff.available is False
    assert handoff.label == "Proposal review unavailable"
    assert handoff.reason == "Proposal status unavailable"
    assert handoff.pending_count == 0


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
    editor = SimpleNamespace(proposal_inbox=HostileInbox())

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


def _status_with_pending(count: int) -> CreatorProposalStatusModel:
    from engine.editor.creator_mode.creator_proposal_status import CreatorProposalListRow

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


def _editor_with_bridge(bridge: object, *, proposal_inbox: object | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        selected_entity=None,
        live_bridge=bridge,
        proposal_inbox=proposal_inbox,
        window=SimpleNamespace(
            width=1280,
            height=720,
            scene_controller=SimpleNamespace(current_scene_path="forest"),
        ),
    )
