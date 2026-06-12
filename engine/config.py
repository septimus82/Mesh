"""Engine configuration helpers for Mesh Engine."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any, Dict

from . import json_io
from .diagnostics import add_exception as diag_add_exception
from .diagnostics import error as diag_error
from .diagnostics import warn as diag_warn
from .logging_tools import get_logger
from .repo_root import find_repo_root
from .schema_validation import validate
from .swallowed_exceptions import record_swallowed, should_log

_log = get_logger(__name__)


@dataclass
class EngineConfig:
    """Top-level engine configuration with sensible defaults."""

    width: int = 1280
    height: int = 720
    title: str = "Mesh Engine - Demo"

    fullscreen: bool = False
    vsync: bool = True
    resizable: bool = True

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
    tour_completed: bool = False
    auto_open_quest_log: bool = False

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
    input_bindings: dict[str, list[str]] = field(default_factory=dict)
    input: dict[str, Any] = field(default_factory=lambda: {
        "rumble_enabled": False,
        "rumble_strength": 1.0,
    })

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
    except Exception as exc:  # noqa: BLE001  # REASON: unexpected coercion failures should remain visible without spamming and preserve the original config value
        record_swallowed("engine.config._coerce_type", exc)
        if should_log("engine.config._coerce_type"):
            _log.error(
                "[Mesh][Config] ERROR coercing config value target_type=%s value_type=%s: %s",
                getattr(target_type, "__name__", str(target_type)),
                type(value).__name__,
                exc,
                exc_info=True,
            )
        diag_add_exception(
            "config.coerce_type_failed",
            exc,
            "engine.config",
            context={"target_type": str(target_type)},
        )
        return value


def _validate_config_value(key: str, value: Any) -> str | None:
    if key in {"width", "height"}:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return "must be a positive integer"
        return None

    if key == "title":
        if not isinstance(value, str) or not value.strip():
            return "must be a non-empty string"
        return None

    if key == "start_scene":
        if not isinstance(value, str) or not value.strip():
            return "must be a non-empty string path"
        if not value.strip().endswith(".json"):
            return "must point to a .json file"
        return None

    if key in {"main_menu_scene", "world_file"}:
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            return "must be null or a non-empty string path"
        if not value.strip().endswith(".json"):
            return "must point to a .json file"
        return None

    if key == "content_roots":
        if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
            return "must be a list of non-empty strings"
        return None

    return None


_PRESETS_DIR_NAME = "presets"
_PRESETS_COMPAT_MIRROR_NAME = "config_presets.json"
_PRESET_FILE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*\.json$")
_DAY_NIGHT_LEGACY_ALIASES = {
    "day_start_hour": "day_night_start_hour",
    "day_length_seconds": "day_night_cycle_length_seconds",
}


def _apply_day_night_aliases(raw: dict[str, Any], cfg_path: Path) -> dict[str, Any]:
    normalized = dict(raw)
    for legacy_key, canonical_key in _DAY_NIGHT_LEGACY_ALIASES.items():
        legacy_present = legacy_key in raw
        canonical_present = canonical_key in raw
        if legacy_present and not canonical_present:
            normalized[canonical_key] = raw[legacy_key]
            print(
                f"[Mesh][Config] WARNING: Config key '{legacy_key}' is deprecated; "
                f"use '{canonical_key}' instead"
            )
            diag_warn(
                "config.day_night_legacy_alias",
                f"Config key '{legacy_key}' is deprecated; use '{canonical_key}' instead",
                "engine.config",
                location=str(cfg_path),
                context={"legacy_key": legacy_key, "canonical_key": canonical_key},
            )
        elif legacy_present and canonical_present:
            print(
                f"[Mesh][Config] WARNING: Config keys '{legacy_key}' and '{canonical_key}' "
                f"are both set; using '{canonical_key}'"
            )
            diag_warn(
                "config.day_night_legacy_conflict",
                f"Config keys '{legacy_key}' and '{canonical_key}' are both set; using '{canonical_key}'",
                "engine.config",
                location=str(cfg_path),
                context={"legacy_key": legacy_key, "canonical_key": canonical_key},
            )
        normalized.pop(legacy_key, None)
    return normalized


def _iter_split_preset_files(presets_dir: Path) -> list[Path]:
    files: list[Path] = []
    if not presets_dir.exists() or not presets_dir.is_dir():
        return files
    for path in sorted(presets_dir.glob("*.json"), key=lambda p: p.name):
        if path.name == _PRESETS_COMPAT_MIRROR_NAME:
            continue
        if not _PRESET_FILE_PATTERN.fullmatch(path.name):
            continue
        files.append(path)
    return files


def _load_split_presets_or_none(presets_dir: Path) -> dict[str, Any] | None:
    files = _iter_split_preset_files(presets_dir)
    if not files:
        return None
    loaded: dict[str, Any] = {}
    for path in files:
        preset_id = path.stem
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            raise ValueError(f"preset file '{path.as_posix()}' root must be an object")
        if preset_id in loaded:
            raise ValueError(f"duplicate preset id '{preset_id}' in '{path.as_posix()}'")
        loaded[preset_id] = raw
    return loaded


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
        diag_warn(
            "config.file_missing",
            f"No config file at '{cfg_path}', using defaults",
            "engine.config",
            location=str(cfg_path),
        )
        return cfg

    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    validate(raw, "config.schema.json", cfg_path)

    setattr(cfg, "_loaded_keys", set(raw.keys()))
    raw = _apply_day_night_aliases(raw, cfg_path)

    field_types: Dict[str, Any] = {f.name: f.type for f in fields(EngineConfig)}

    for key, value in raw.items():
        if key not in field_types:
            print(f"[Mesh][Config] WARNING: Unknown config key '{key}' ignored")
            diag_warn(
                "config.unknown_key",
                f"Unknown config key '{key}' ignored",
                "engine.config",
                location=str(cfg_path),
                context={"key": str(key)},
            )
            continue
        validation_error = _validate_config_value(key, value)
        if validation_error is not None:
            print(f"[Mesh][Config] ERROR: Invalid config key '{key}': {validation_error}; using default")
            diag_error(
                "config.invalid_value",
                f"Invalid config key '{key}': {validation_error}; using default",
                "engine.config",
                location=str(cfg_path),
                context={"key": str(key)},
            )
            continue
        expected = field_types[key]
        coerced = _coerce_type(value, expected)
        setattr(cfg, key, coerced)

    # Presets source of truth:
    # 1) Split files under presets/*.json (excluding compatibility mirror)
    # 2) Fallback to inline config.json "presets" map
    presets_dir = cfg_path.parent / _PRESETS_DIR_NAME
    inline_presets = cfg.presets if isinstance(cfg.presets, dict) else {}
    try:
        split_presets = _load_split_presets_or_none(presets_dir)
    except Exception as exc:  # noqa: BLE001  # REASON: split preset load failures should fall back to inline presets without breaking config load
        print(f"[Mesh][Config] WARNING: Failed to load split presets from '{presets_dir}': {exc}")
        diag_add_exception(
            "config.presets.split_load_failed",
            exc,
            "engine.config",
            location=str(presets_dir),
        )
        split_presets = None
    if split_presets is not None:
        cfg.presets = split_presets
        setattr(cfg, "_presets_source", "split_files")
        setattr(cfg, "_presets_dir", str(presets_dir))
    else:
        cfg.presets = inline_presets
        setattr(cfg, "_presets_source", "config_inline")
        if inline_presets:
            diag_warn(
                "config.presets.fallback_inline",
                "Using inline presets fallback from config.json",
                "engine.config",
                location=str(cfg_path),
                context={"presets_count": int(len(inline_presets))},
            )

    return cfg


def save_config(config: EngineConfig, path: str = "config.json") -> None:
    """Serialize EngineConfig to a pretty-printed JSON file."""
    cfg_path = Path(path)
    try:
        data: Dict[str, Any] = asdict(config)
        json_io.write_json_atomic(cfg_path, data)
        print(f"[Mesh][Config] Saved configuration to '{path}'")
    except OSError as exc:
        print(f"[Mesh][Config] ERROR: Could not write '{path}': {exc}")
