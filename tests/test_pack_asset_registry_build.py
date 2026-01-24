from __future__ import annotations

import json
from pathlib import Path

from engine.paths import get_content_roots, set_content_roots
from engine.tooling_runtime.pack_manifest import load_all_manifests
from engine.tooling_runtime.pack_registry import build_asset_registry


def test_pack_asset_registry_build(tmp_path: Path) -> None:
    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        packs_dir = tmp_path / "packs"
        packs_dir.mkdir()
        pack_root = packs_dir / "alpha"
        (pack_root / "assets").mkdir(parents=True)
        (pack_root / "scenes").mkdir()

        (pack_root / "pack.json").write_text(
            json.dumps({"id": "alpha", "version": "1.0.0"}), encoding="utf-8"
        )
        asset_path = pack_root / "assets" / "sprite.png"
        asset_path.write_bytes(b"\x89PNG\r\n")
        scene_path = pack_root / "scenes" / "test_scene.json"
        scene_path.write_text(
            json.dumps({"entities": [{"sprite": "assets/sprite.png"}], "missing": "assets/missing.png"}),
            encoding="utf-8",
        )

        manifests, errors = load_all_manifests(pack_id="alpha")
        assert not errors
        registry = build_asset_registry(manifests, include_unused=True)

        asset_paths = {entry["path"] for entry in registry["assets"]}
        assert "packs/alpha/assets/sprite.png" in asset_paths
        assert any(m["ref"] == "assets/missing.png" for m in registry["missing"])
        unused_paths = {entry["path"] for entry in registry["unused"]}
        assert "packs/alpha/assets/sprite.png" not in unused_paths
    finally:
        set_content_roots(original_roots)
