"""Engine configuration helpers for Mesh Engine."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict

from .repo_root import find_repo_root


@dataclass
class EngineConfig:
    """Top-level engine configuration with sensible defaults."""

    width: int = 1280
    height: int = 720
    title: str = "Mesh Engine - Demo"

    fullscreen: bool = False
    vsync: bool = True

    start_scene: str = "scenes/cellar.json"
    main_menu_scene: str | None = None
    world_file: str | None = "worlds/main_world.json"

    master_volume: float = 1.0
    sfx_volume: float = 1.0
    music_volume: float = 1.0

    profile: str = "release"

    debug_on_start: bool = False
    show_fps: bool = True
    debug_mode: bool = False
    debug_page: int = 0

    # Scene transition FX
    scene_fade_enabled: bool = False
    scene_fade_out_s: float = 0.2
    scene_fade_in_s: float = 0.2
    scene_fade_show_loading_text: bool = False
    music_crossfade_enabled: bool = False
    music_crossfade_out_s: float = 0.25
    music_crossfade_in_s: float = 0.25
    soft_shadows_enabled: bool = False
    soft_shadows_expand_px: float = 6.0
    soft_shadows_alpha_scale: float = 0.35
    ambient_light_rgba: tuple[int, int, int, int] = (255, 255, 255, 255)
    ambient_darkness_alpha: int = 255
    fog_enabled: bool = False
    fog_rgba: tuple[int, int, int, int] = (255, 255, 255, 0)
    fog_density: float = 0.0
    fog_noise_speed: float = 0.15
    fog_noise_amount: float = 0.25

    lighting_enabled: bool = True
    lighting_ambient_color: list[int] = field(default_factory=lambda: [10, 10, 10, 255])
    lighting_max_static_lights: int = 128
    lighting_max_dynamic_lights: int = 64
    lighting_shadows_mode: str = "hard"
    lighting_debug_shadows: bool = False

    # Day/night cycle
    day_night_enabled: bool = False
    day_night_start_hour: float = 21.0
    day_night_cycle_length_seconds: float = 600.0
    day_length_seconds: float = 600.0
    day_start_hour: float = 21.0
    input_bindings: dict[str, list[str]] = field(default_factory=dict)

    # XP / Stats
    xp_base: int = 50
    xp_per_level: int = 25

    # Encounter Budget
    encounter_budget_profiles: dict[str, float] = field(default_factory=lambda: {
        "easy": 0.8,
        "normal": 1.0,
        "hard": 1.25
    })

    # Profiles
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Audit Policy
    audit_policy: dict[str, Any] = field(default_factory=dict)
    # Plan Test Policy
    plan_test_policy: dict[str, Any] = field(default_factory=dict)
    player_stats_enabled: bool = True
    hud_show_xp_bar: bool = True
    hud_show_objective: bool = True

    player_base_max_hp: int = 30
    player_base_attack: int = 5
    player_base_defense: int = 2
    player_base_speed: float = 3.0

    player_hp_per_level: int = 5
    player_attack_per_level: int = 1
    player_defense_per_level: int = 1
    player_speed_per_level: float = 0.25

    # Content Roots
    content_roots: list[str] = field(default_factory=lambda: ["."])

    # Presets
    presets: dict[str, Any] = field(default_factory=dict)

    # Wizard Tooling
    wizard_macros: dict[str, Any] = field(default_factory=dict)
    wizard_presets: dict[str, Any] = field(default_factory=dict)


def _coerce_type(value: Any, target_type: Any) -> Any:
    """Best-effort type coercion; fall back to the original value on failure."""
    try:
        if not isinstance(target_type, type):
            return value
        if target_type is bool:
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on"}
            return bool(value)
        return target_type(value)
    except (TypeError, ValueError):
        return value
    except Exception as exc:  # noqa: BLE001
        if not getattr(_coerce_type, "_mesh_error_logged", False):
            print(f"[Mesh][Config] ERROR coercing config value: {exc}")
            setattr(_coerce_type, "_mesh_error_logged", True)
        return value


def load_config(path: str | None = None) -> EngineConfig:
    """Load EngineConfig from disk, falling back to defaults on error.

    If no explicit path is provided, prefer <repo_root>/config.json (repo_root is
    discovered by walking upward from the current working directory looking for
    pyproject.toml or config.json).
    """
    cfg = EngineConfig()
    if path is None:
        repo_root = find_repo_root()
        cfg_path = (repo_root / "config.json") if repo_root else Path("config.json")
    else:
        cfg_path = Path(path)

    setattr(cfg, "_config_path", str(cfg_path))
    setattr(cfg, "_config_base_dir", str(cfg_path.parent))

    if not cfg_path.exists():
        print(f"[Mesh][Config] No config file at '{cfg_path}', using defaults")
        return cfg

    try:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("config root is not an object")
    except Exception as exc:
        print(f"[Mesh][Config] Failed to load '{cfg_path}': {exc}; using defaults")
        return cfg

    setattr(cfg, "_loaded_keys", set(raw.keys()))

    field_types: Dict[str, Any] = {f.name: f.type for f in fields(EngineConfig)}

    for key, value in raw.items():
        if key not in field_types:
            print(f"[Mesh][Config] WARNING: Unknown config key '{key}' ignored")
            continue
        expected = field_types[key]
        coerced = _coerce_type(value, expected)
        setattr(cfg, key, coerced)

    return cfg


def save_config(config: EngineConfig, path: str = "config.json") -> None:
    """Serialize EngineConfig to a pretty-printed JSON file."""
    cfg_path = Path(path)
    try:
        data: Dict[str, Any] = asdict(config)
        cfg_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[Mesh][Config] Saved configuration to '{path}'")
    except OSError as exc:
        print(f"[Mesh][Config] ERROR: Could not write '{path}': {exc}")
