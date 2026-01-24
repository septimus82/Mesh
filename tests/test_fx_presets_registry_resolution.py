from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.fx_presets import FxPresetRegistry
from engine.tooling_runtime.pack_manifest import load_manifest, resolve_pack_order


def _write_pack(root: Path, pack_id: str, deps: list[str], presets: dict[str, dict]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {"id": pack_id, "version": "1.0.0"}
    if deps:
        payload["dependencies"] = [{"id": dep} for dep in deps]
    (root / "pack.json").write_text(json.dumps(payload), encoding="utf-8")
    fx_dir = root / "fx"
    fx_dir.mkdir(exist_ok=True)
    (fx_dir / "presets.json").write_text(
        json.dumps({"schema_version": 1, "presets": presets}),
        encoding="utf-8",
    )


def test_fx_presets_registry_resolution(tmp_path: Path) -> None:
    pack_b = tmp_path / "packs" / "b"
    pack_a = tmp_path / "packs" / "a"
    _write_pack(pack_b, "b", [], {"spark": {"count": 1}})
    _write_pack(pack_a, "a", ["b"], {"spark": {"count": 2}})

    manifest_a, _ = load_manifest(pack_a)
    manifest_b, _ = load_manifest(pack_b)
    order, errors = resolve_pack_order([manifest_a, manifest_b])
    assert not errors

    registry = FxPresetRegistry.from_pack_roots([pack_a, pack_b], order)
    assert registry.resolve("spark", context_pack_id="a")["count"] == 2
    assert registry.resolve("b:spark")["count"] == 1
    with pytest.raises(ValueError):
        registry.resolve("missing", context_pack_id="a")
    with pytest.raises(ValueError):
        registry.resolve("c:spark")
