from __future__ import annotations

from typing import List


def validate_scene_file(path: str) -> List[str]:
    from engine.scene_loader import SceneLoader  # noqa: PLC0415

    report = SceneLoader().validate_scene_file(path)
    return list(report.errors)
