from __future__ import annotations

import json
from pathlib import Path

from engine.lighting.occluders import build_occluders_from_scene_payload


def test_guard_patrol_chase_demo_has_occluders_for_hard_shadows() -> None:
    scene_path = "scenes/guard_patrol_chase_demo.json"
    payload = json.loads(Path(scene_path).read_text(encoding="utf-8"))

    occluders = build_occluders_from_scene_payload(payload, scene_path=scene_path, revision=0)
    assert len(occluders) >= 1
    assert any(
        float(o.get("width") or 0.0) >= 32.0 and float(o.get("height") or 0.0) >= 32.0 for o in occluders
    )
