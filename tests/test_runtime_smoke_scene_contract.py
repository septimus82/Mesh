from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]


def test_runtime_smoke_scene_exists_and_parses() -> None:
    from engine.runtime_only import DEFAULT_SMOKE_SCENE

    scene_path = Path(DEFAULT_SMOKE_SCENE)
    assert scene_path.exists(), f"missing runtime smoke scene: {scene_path.as_posix()}"
    payload = json.loads(scene_path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    assert payload.get("name")


def test_runtime_smoke_scene_loads_via_public_runtime_loader() -> None:
    from engine.public_api.runtime import load_scene_payload
    from engine.runtime_only import DEFAULT_SMOKE_SCENE

    scene = load_scene_payload(DEFAULT_SMOKE_SCENE)
    assert isinstance(scene, dict)
    assert str(scene.get("name") or "").strip() != ""
