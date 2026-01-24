from __future__ import annotations

import json
from pathlib import Path

from engine.behaviours.particle_emitter import ParticleEmitter
from engine.fx_presets import FxPresetRegistry
from engine.particles_core import ParticleSystem
from engine.tooling_runtime.pack_manifest import load_manifest, resolve_pack_order


class _StubWindow:
    def __init__(self, fx_presets: FxPresetRegistry) -> None:
        self.fx_presets = fx_presets
        self.particle_system = ParticleSystem()
        self.scene_controller = type("Scene", (), {"current_scene_path": "packs/a/scenes/test.json"})()


class _StubEntity:
    def __init__(self, config: dict) -> None:
        self.center_x = 0.0
        self.center_y = 0.0
        self.mesh_entity_data = {"behaviour_config": {"ParticleEmitter": dict(config)}}


def _write_pack(root: Path, pack_id: str, presets: dict[str, dict]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    payload = {"id": pack_id, "version": "1.0.0"}
    (root / "pack.json").write_text(json.dumps(payload), encoding="utf-8")
    fx_dir = root / "fx"
    fx_dir.mkdir(exist_ok=True)
    (fx_dir / "presets.json").write_text(
        json.dumps({"schema_version": 1, "presets": presets}),
        encoding="utf-8",
    )


def test_particle_emitter_preset_merge(tmp_path: Path) -> None:
    pack_a = tmp_path / "packs" / "a"
    presets = {
        "spark": {
            "mode": "burst",
            "count": 5,
            "sprite": "packs/a/fx/spark.png",
            "rect": [0, 0, 8, 8],
            "additive": False,
        }
    }
    _write_pack(pack_a, "a", presets)

    manifest_a, _ = load_manifest(pack_a)
    order, errors = resolve_pack_order([manifest_a])
    assert not errors
    registry = FxPresetRegistry.from_pack_roots([pack_a], order)

    window = _StubWindow(registry)
    entity = _StubEntity({"preset": "spark", "count": 2, "additive": True})
    emitter = ParticleEmitter(entity, window)
    emitter.update(1.0 / 60.0)

    particles = window.particle_system.particles
    assert len(particles) == 2
    particle = particles[0]
    assert particle.sprite_path == "packs/a/fx/spark.png"
    assert particle.sprite_rect == (0, 0, 8, 8)
    assert particle.additive is True
