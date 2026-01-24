from __future__ import annotations


def _iter_strings(value: object) -> list[str]:
    out: list[str] = []
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for k in sorted(value.keys(), key=lambda x: str(x)):
            out.extend(_iter_strings(value[k]))
    elif isinstance(value, list):
        for item in value:
            out.extend(_iter_strings(item))
    return out


def test_ai_generate_plan_default_has_no_todos_or_tbd() -> None:
    from engine.tooling.ai_plan_command import generate_plan_skeleton
    from engine.tooling.plan_linter import lint_ai_plan
    from engine.tooling.plan_types import Plan

    plan_dict = generate_plan_skeleton("A tiny demo scene with a guide NPC.")
    plan = Plan.from_dict(plan_dict)
    assert lint_ai_plan(plan) == []

    strings = _iter_strings(plan_dict)
    lowered = [s.lower() for s in strings]
    assert not any("todo" in s for s in lowered)
    assert not any("tbd" in s for s in lowered)

