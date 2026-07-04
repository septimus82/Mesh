from __future__ import annotations

import subprocess
import sys

import pytest

from engine.editor.creator_mode import (
    CreatorDoorWorkflowRequest,
    build_creator_door_panel,
    build_creator_door_workflow,
    creator_door_staging,
)
from engine.editor.creator_mode.creator_door_panel import (
    CreatorDoorPanelLine,
    _dedupe_text,
)

pytestmark = pytest.mark.fast


def test_ready_existing_door_workflow_builds_ready_status() -> None:
    bridge = FakeBridge()

    panel = build_creator_door_panel(
        build_creator_door_workflow(_existing_door_request()),
        bridge,
    )

    assert panel.status == "ready"
    assert bridge.called is False


def test_ready_panel_title_uses_preview_title() -> None:
    panel = build_creator_door_panel(
        build_creator_door_workflow(_existing_door_request()),
        FakeBridge(),
    )

    assert panel.title == "Door plan"


def test_ready_panel_includes_plan_section() -> None:
    panel = build_creator_door_panel(
        build_creator_door_workflow(_existing_door_request()),
        FakeBridge(),
    )

    assert _section(panel, "Plan").lines[0].text == "Plan door from forest to town at north_gate_entry."


def test_ready_panel_includes_what_will_happen_section() -> None:
    panel = build_creator_door_panel(
        build_creator_door_workflow(_existing_door_request()),
        FakeBridge(),
    )

    lines = _section_texts(panel, "What will happen")
    assert "Prepare door: Prepare door_north in the source map." in lines
    assert "Set destination: Send the player to town at north_gate_entry when trigger is interact." in lines


def test_ready_panel_includes_staging_section() -> None:
    panel = build_creator_door_panel(
        build_creator_door_workflow(_existing_door_request()),
        FakeBridge(),
    )

    assert _section(panel, "Staging").lines[0].text == "This door proposal is ready to stage."


def test_ready_panel_includes_live_op_preview_text() -> None:
    panel = build_creator_door_panel(
        build_creator_door_workflow(_existing_door_request()),
        FakeBridge(),
    )

    assert "Set SceneExit params on door_north." in _section_texts(panel, "Staging")


def test_ready_panel_mirrors_stage_proposal_action_enabled() -> None:
    panel = build_creator_door_panel(
        build_creator_door_workflow(_existing_door_request()),
        FakeBridge(),
    )

    assert _action_snapshot(panel) == (("Stage Proposal", True, ""),)


def test_bridge_unavailable_panel_status_is_bridge_unavailable() -> None:
    panel = build_creator_door_panel(
        build_creator_door_workflow(_existing_door_request()),
        None,
    )

    assert panel.status == "bridge_unavailable"
    assert panel.summary == "The proposal bridge is not available."


def test_bridge_unavailable_panel_action_disabled_with_reason() -> None:
    panel = build_creator_door_panel(
        build_creator_door_workflow(_existing_door_request()),
        object(),
    )

    assert _action_snapshot(panel) == (("Stage Proposal", False, "Proposal bridge is unavailable."),)


def test_blocked_workflow_panel_status_is_blocked() -> None:
    panel = build_creator_door_panel(
        build_creator_door_workflow(
            CreatorDoorWorkflowRequest(source_scene="", destination_scene="town")
        ),
        FakeBridge(),
    )

    assert panel.status == "blocked"


def test_blocked_panel_includes_errors_in_problems_section() -> None:
    panel = build_creator_door_panel(
        build_creator_door_workflow(
            CreatorDoorWorkflowRequest(source_scene="", destination_scene="town")
        ),
        FakeBridge(),
    )

    problems = _section(panel, "Problems")
    assert ("Door workflow is blocked.", "Source scene is required.") == tuple(line.text for line in problems.lines)
    assert {line.severity for line in problems.lines} == {"error"}


def test_warnings_are_deduplicated() -> None:
    panel = build_creator_door_panel(
        build_creator_door_workflow(
            CreatorDoorWorkflowRequest(
                source_scene="forest",
                destination_scene="town",
                source_entity_id="door_north",
            )
        ),
        FakeBridge(),
    )

    assert _section_texts(panel, "Warnings") == ("Door has no destination spawn point.",)


def test_errors_are_deduplicated() -> None:
    assert _dedupe_text(("blocked", "blocked", "invalid")) == ("blocked", "invalid")


def test_no_errors_case_shows_no_blocking_problems() -> None:
    panel = build_creator_door_panel(
        build_creator_door_workflow(_existing_door_request()),
        FakeBridge(),
    )

    assert _section_texts(panel, "Problems") == ("No blocking problems.",)


def test_no_warnings_case_shows_no_warnings() -> None:
    panel = build_creator_door_panel(
        build_creator_door_workflow(_existing_door_request()),
        FakeBridge(),
    )

    assert _section_texts(panel, "Warnings") == ("No warnings.",)


def test_output_is_deterministic() -> None:
    workflow = build_creator_door_workflow(_existing_door_request())

    first = build_creator_door_panel(workflow, FakeBridge())
    second = build_creator_door_panel(workflow, FakeBridge())

    assert _panel_snapshot(first) == _panel_snapshot(second)


def test_builder_does_not_call_bridge_stage_pending_proposal() -> None:
    bridge = FakeBridge()

    build_creator_door_panel(build_creator_door_workflow(_existing_door_request()), bridge)

    assert bridge.called is False


def test_builder_does_not_call_stage_creator_door_proposal(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args, **_kwargs):
        raise AssertionError("panel model must not stage")

    monkeypatch.setattr(creator_door_staging, "stage_creator_door_proposal", fail)

    panel = build_creator_door_panel(
        build_creator_door_workflow(_existing_door_request()),
        FakeBridge(),
    )

    assert panel.status == "ready"


def test_module_imports_without_arcade() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "sys.modules['arcade'] = None; "
                "from engine.editor.creator_mode.creator_door_panel "
                "import build_creator_door_panel; "
                "print(callable(build_creator_door_panel))"
            ),
        ],
        capture_output=True,
        check=True,
        text=True,
    )

    assert result.stdout.strip() == "True"


def test_package_import_still_does_not_import_renderer_module() -> None:
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


def test_module_does_not_import_real_bridge_modules() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from engine.editor.creator_mode.creator_door_panel "
                "import build_creator_door_panel; "
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


def test_panel_line_defaults_to_info_severity() -> None:
    assert CreatorDoorPanelLine("hello").severity == "info"


class FakeBridge:
    def __init__(self) -> None:
        self.called = False

    def stage_pending_proposal(self, ops):
        self.called = True
        raise AssertionError("panel model must not stage")


def _existing_door_request() -> CreatorDoorWorkflowRequest:
    return CreatorDoorWorkflowRequest(
        source_scene="forest",
        destination_scene="town",
        destination_spawn_id="north_gate_entry",
        source_entity_id="door_north",
    )


def _section(panel, title: str):
    for section in panel.sections:
        if section.title == title:
            return section
    raise AssertionError(f"missing section {title}")


def _section_texts(panel, title: str) -> tuple[str, ...]:
    return tuple(line.text for line in _section(panel, title).lines)


def _action_snapshot(panel) -> tuple[tuple[str, bool, str], ...]:
    return tuple((action.label, action.enabled, action.reason) for action in panel.actions)


def _panel_snapshot(panel):
    return (
        panel.title,
        panel.status,
        panel.summary,
        tuple((section.title, tuple((line.text, line.severity) for line in section.lines)) for section in panel.sections),
        _action_snapshot(panel),
    )
