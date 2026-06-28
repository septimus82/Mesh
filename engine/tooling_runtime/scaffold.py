from __future__ import annotations

from typing import Any


def create_scene(path: str, template_name: str = "empty", *, extra_args: dict[str, Any] | None = None) -> bool:
    from engine.tooling.scaffold import create_scene as _create_scene  # noqa: PLC0415

    return _create_scene(path, template_name=template_name, extra_args=extra_args)


def list_scene_template_names() -> list[str]:
    from engine.tooling.scaffold import TEMPLATES  # noqa: PLC0415

    return sorted(TEMPLATES.keys())

