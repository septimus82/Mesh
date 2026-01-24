from __future__ import annotations

from typing import Any, Dict


def generate_plan_skeleton(prompt: str, *, allow_todos: bool = False) -> Dict[str, Any]:
    from engine.tooling.ai_plan_command import generate_plan_skeleton as _gen  # noqa: PLC0415

    return _gen(prompt, allow_todos=allow_todos)


def generate_ai_schema() -> Dict[str, Any]:
    from engine.tooling.ai_plan_command import generate_ai_schema as _schema  # noqa: PLC0415

    return _schema()

