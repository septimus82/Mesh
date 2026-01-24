from __future__ import annotations

import json


def test_entity_persist_write_atomic_and_noop(tmp_path) -> None:
    from engine.scene_serializer import compact_scene_payload
    from engine.tooling_runtime.entity_persist import persist_scene_payload

    scene_path = tmp_path / "scenes" / "foo.json"
    payload = {"entities": []}

    result1 = persist_scene_payload(str(scene_path), payload, strict_no_overwrite=False)
    assert result1.ok is True
    assert result1.wrote is True
    assert scene_path.exists() is True
    assert scene_path.with_suffix(scene_path.suffix + ".tmp").exists() is False

    saved = json.loads(scene_path.read_text(encoding="utf-8"))
    assert saved == compact_scene_payload(payload)

    result2 = persist_scene_payload(str(scene_path), payload, strict_no_overwrite=False)
    assert result2.ok is True
    assert result2.wrote is False


def test_entity_persist_strict_no_overwrite_blocks_existing_diff(tmp_path) -> None:
    from engine.tooling_runtime.entity_persist import persist_scene_payload

    scene_path = tmp_path / "scene.json"
    scene_path.write_text('{"entities": []}\n', encoding="utf-8")

    payload = {"entities": [{"id": "e1", "prefab_id": "slime_blob", "x": 0.0, "y": 0.0}]}

    result = persist_scene_payload(str(scene_path), payload, strict_no_overwrite=True)
    assert result.ok is False
    assert result.wrote is False
    assert "exists_different" in (result.errors or [])
    assert scene_path.read_text(encoding="utf-8") == '{"entities": []}\n'
