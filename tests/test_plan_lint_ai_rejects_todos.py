from __future__ import annotations


def test_plan_lint_ai_rejects_placeholder_tokens_with_paths() -> None:
    from engine.tooling.plan_linter import lint_ai_plan
    from engine.tooling.plan_types import Action, Plan

    plan = Plan(
        wizard="test",
        version=1,
        inputs={"prompt": "TBD"},
        actions=[
            Action(
                type="create_scene",
                args={"path": "scenes/TODO_scene.json", "template": "empty"},
                description="Create scene",
            )
        ],
    )

    issues = lint_ai_plan(plan)
    assert any(i.code == "PLACEHOLDER_TEXT" for i in issues)
    messages = "\n".join(i.message for i in issues)
    assert "inputs.prompt" in messages
    assert "actions[0].args.path" in messages

