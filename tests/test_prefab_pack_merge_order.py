import json
import logging
from pathlib import Path

from engine.prefabs import PrefabManager


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_pack_prefabs_override_order(tmp_path, monkeypatch, caplog):
    assets_path = tmp_path / "assets" / "prefabs.json"
    alpha_path = tmp_path / "packs" / "alpha" / "data" / "prefabs.json"
    beta_path = tmp_path / "packs" / "beta" / "data" / "prefabs.json"

    _write_json(
        assets_path,
        [
            {"id": "p_tree", "entity": {"sprite": "base.png"}},
        ],
    )
    _write_json(
        alpha_path,
        [
            {"id": "p_tree", "entity": {"sprite": "alpha.png"}},
            {"id": "p_alpha_unique", "entity": {"sprite": "alpha_unique.png"}},
        ],
    )
    _write_json(
        beta_path,
        [
            {"id": "p_tree", "entity": {"sprite": "beta.png"}},
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
