import pytest

from engine.tooling.plan_executor import PlanExecutor
from engine.tooling.plan_types import Action, Plan


def test_apply_plan_touches_match_actions_success(tmp_path):
    """Verify that if touches matches action targets, execution proceeds."""
    plan = Plan(
        wizard="test",
        version=1,
        inputs={
            "meta": {
                "touches": ["scenes/test.json"]
            }
        },
        actions=[
            Action(type="create_scene", args={"path": "scenes/test.json", "template": "basic"}, description="test")
        ]
    )

    executor = PlanExecutor(dry_run=True)
    # Should not raise
    executor.execute(plan, ai_safe=True)

def test_apply_plan_touches_match_actions_failure(tmp_path):
    """Verify that if touches is missing a target, execution fails."""
    plan = Plan(
        wizard="test",
        version=1,
        inputs={
            "meta": {
                "touches": ["scenes/other.json"] # Missing scenes/test.json
            }
        },
        actions=[
            Action(type="create_scene", args={"path": "scenes/test.json", "template": "basic"}, description="test")
        ]
    )

    executor = PlanExecutor(dry_run=True)

    with pytest.raises(ValueError) as excinfo:
        executor.execute(plan, ai_safe=True)

    assert "AI-safe apply requires plan.meta.touches to include all action targets" in str(excinfo.value)
    assert "scenes/test.json" in str(excinfo.value)

def test_apply_plan_touches_match_actions_superset_ok(tmp_path):
    """Verify that touches can be a superset of action targets (conservative estimate)."""
    plan = Plan(
        wizard="test",
        version=1,
        inputs={
            "meta": {
                "touches": ["scenes/test.json", "scenes/extra.json"]
            }
        },
        actions=[
            Action(type="create_scene", args={"path": "scenes/test.json", "template": "basic"}, description="test")
        ]
    )

    executor = PlanExecutor(dry_run=True)
    # Should not raise
    executor.execute(plan, ai_safe=True)

def test_apply_plan_touches_match_actions_ignored_if_not_ai_safe(tmp_path):
    """Verify that the check is skipped if ai_safe=False."""
    plan = Plan(
        wizard="test",
        version=1,
        inputs={
            "meta": {
                "touches": ["scenes/other.json"] # Mismatch
            }
        },
        actions=[
            Action(type="create_scene", args={"path": "scenes/test.json", "template": "basic"}, description="test")
        ]
    )

    executor = PlanExecutor(dry_run=True)
    # Should not raise
    executor.execute(plan, ai_safe=False)
