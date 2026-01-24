from __future__ import annotations

import json
from pathlib import Path

from engine.paths import get_content_roots, set_content_roots
from engine.tooling_runtime.pack_manifest import load_all_manifests, load_manifest


def test_pack_manifest_load_validate(tmp_path: Path) -> None:
    original_roots = get_content_roots()
    set_content_roots([tmp_path])
    try:
        packs_dir = tmp_path / "packs"
        packs_dir.mkdir()
        pack_root = packs_dir / "alpha"
        pack_root.mkdir()

        manifest_path = pack_root / "pack.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "id": "alpha",
                    "version": "1.2.3",
                    "title": "Alpha Pack",
                    "dependencies": [{"id": "base", "version_range": "*"}],
                }
            ),
            encoding="utf-8",
        )

        manifest, errors = load_manifest(pack_root)
        assert not errors
        assert manifest.id == "alpha"
        assert manifest.version == "1.2.3"
        assert manifest.title == "Alpha Pack"
        assert manifest.dependencies[0].id == "base"

        implicit_root = packs_dir / "implicit"
        implicit_root.mkdir()
        implicit_manifest, implicit_errors = load_manifest(implicit_root)
        assert not implicit_errors
        assert implicit_manifest.implicit is True

        manifests, manifest_errors = load_all_manifests(pack_id="alpha")
        assert not manifest_errors
        assert [m.id for m in manifests] == ["alpha"]
    finally:
        set_content_roots(original_roots)
