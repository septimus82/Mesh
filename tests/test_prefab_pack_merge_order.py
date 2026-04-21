import json
import logging
from pathlib import Path

import pytest

from engine.prefabs import PrefabManager
from engine.schema_validation import SchemaValidationError

pytestmark = [pytest.mark.fast]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _prefab(prefab_id: str, sprite: str) -> dict[str, object]:
    return {
        "display_name": prefab_id,
        "entity": {"sprite": sprite},
        "id": prefab_id,
        "tags": ["test"],
    }


def test_pack_prefabs_override_order(tmp_path, monkeypatch, caplog):
    assets_path = tmp_path / "assets" / "prefabs.json"
    alpha_path = tmp_path / "packs" / "alpha" / "data" / "prefabs.json"
    beta_path = tmp_path / "packs" / "beta" / "data" / "prefabs.json"

    _write_json(
        assets_path,
        [
            _prefab("p_tree", "base.png"),
        ],
    )
    _write_json(
        alpha_path,
        [
            _prefab("p_tree", "alpha.png"),
            _prefab("p_alpha_unique", "alpha_unique.png"),
        ],
    )
    _write_json(
        beta_path,
        [
            _prefab("p_tree", "beta.png"),
        ],
    )

    def fake_resolve_path(path: str) -> Path:
        return tmp_path / path

    monkeypatch.setattr("engine.prefabs.resolve_path", fake_resolve_path)
    monkeypatch.setattr("engine.prefabs.get_content_roots", lambda: [tmp_path])

    monkeypatch.setenv("MESH_PREFAB_WARN_OVERRIDES", "1")
    caplog.set_level(logging.WARNING)

    manager = PrefabManager()
    manager.load(force=True)
    manager.load(force=True)
    assert "[Prefabs] override id=p_tree" in caplog.text
    assert "assets/prefabs.json" in caplog.text
    assert "packs/beta/data/prefabs.json" in caplog.text

    resolved = manager.get_prefab("p_tree")
    assert resolved is not None
    assert resolved["entity"]["sprite"] == "beta.png"
    assert "p_alpha_unique" in manager.prefabs
    assert manager.prefab_sources["p_tree"] == "packs/beta/data/prefabs.json"
    assert manager.prefab_sources["p_alpha_unique"] == "packs/alpha/data/prefabs.json"
    assert manager.prefab_source_chain["p_tree"] == [
        "assets/prefabs.json",
        "packs/alpha/data/prefabs.json",
        "packs/beta/data/prefabs.json",
    ]


def test_prefab_manager_loads_valid_existing_style_prefab(tmp_path, monkeypatch):
    assets_path = tmp_path / "assets" / "prefabs.json"
    _write_json(assets_path, [_prefab("p_tree", "tree.png")])

    def fake_resolve_path(path: str) -> Path:
        return tmp_path / path

    monkeypatch.setattr("engine.prefabs.resolve_path", fake_resolve_path)
    monkeypatch.setattr("engine.prefabs.get_content_roots", lambda: [tmp_path])

    manager = PrefabManager()
    manager.load(force=True)

    assert manager.get_prefab("p_tree") is not None
    assert manager.get_prefab("p_tree")["entity"]["sprite"] == "tree.png"


def test_prefab_manager_rejects_missing_entity_block_with_schema_error(tmp_path, monkeypatch):
    assets_path = tmp_path / "assets" / "prefabs.json"
    _write_json(
        assets_path,
        [
            {"display_name": "bad_missing_entity", "id": "bad_missing_entity", "tags": ["test"]},
            _prefab("good_prefab", "ok.png"),
        ],
    )

    def fake_resolve_path(path: str) -> Path:
        return tmp_path / path

    monkeypatch.setattr("engine.prefabs.resolve_path", fake_resolve_path)
    monkeypatch.setattr("engine.prefabs.get_content_roots", lambda: [tmp_path])

    manager = PrefabManager()
    with pytest.raises(SchemaValidationError) as exc_info:
        manager.load(force=True)

    assert exc_info.value.file_path == str(assets_path)
    assert exc_info.value.json_pointer == "/0"
    assert "entity" in str(exc_info.value)


def test_prefab_manager_rejects_wrong_type_id_with_schema_error(tmp_path, monkeypatch):
    assets_path = tmp_path / "assets" / "prefabs.json"
    _write_json(
        assets_path,
        [
            {"display_name": "bad_prefab", "entity": {"sprite": "bad.png"}, "id": 123, "tags": ["test"]},
            _prefab("good_prefab", "ok.png"),
        ],
    )

    def fake_resolve_path(path: str) -> Path:
        return tmp_path / path

    monkeypatch.setattr("engine.prefabs.resolve_path", fake_resolve_path)
    monkeypatch.setattr("engine.prefabs.get_content_roots", lambda: [tmp_path])

    manager = PrefabManager()
    with pytest.raises(SchemaValidationError) as exc_info:
        manager.load(force=True)

    assert exc_info.value.file_path == str(assets_path)
    assert exc_info.value.json_pointer == "/0/id"
    assert "not of type 'string'" in str(exc_info.value)
