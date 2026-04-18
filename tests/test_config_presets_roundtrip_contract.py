from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest

from engine.config import load_config
from engine.schema_validation import SchemaValidationError


pytestmark = [pytest.mark.fast]
_MIRROR_FILE = "config_presets.json"
_SLUG_FILE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*\.json$")
_SCHEMA_PREFIX_FAMILIES: tuple[str, ...] = (
    "act1_",
    "golden_slice",
    "lighting-",
    "encounter-",
    "ci-",
    "agent-",
)


@lru_cache(maxsize=None)
def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


@lru_cache(maxsize=None)
def _split_preset_paths() -> tuple[Path, ...]:
    preset_dir = Path("presets")
    return tuple(
        sorted(
            [
                path
                for path in preset_dir.glob("*.json")
                if path.is_file() and path.name != _MIRROR_FILE
            ],
            key=lambda path: path.name,
        )
    )


def _split_preset_paths_for(base_dir: Path | None = None) -> list[Path]:
    preset_dir = base_dir or Path("presets")
    return list(
        _split_preset_paths()
        if base_dir is None
        else sorted(
        [
            path
            for path in preset_dir.glob("*.json")
            if path.is_file() and path.name != _MIRROR_FILE
        ],
        key=lambda path: path.name,
    ))


@lru_cache(maxsize=None)
def _load_split_presets() -> dict[str, dict[str, Any]]:
    loaded: dict[str, dict[str, Any]] = {}
    for path in _split_preset_paths():
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        assert isinstance(payload, dict), f"{path.as_posix()} must contain a preset object"
        loaded[path.stem] = payload
    return loaded


def _deterministic_schema_subset_ids() -> list[str]:
    ids = sorted(_load_split_presets().keys())
    chosen: list[str] = []
    chosen_set: set[str] = set()

    for preset_id in ids[:5]:
        chosen.append(preset_id)
        chosen_set.add(preset_id)

    for prefix in _SCHEMA_PREFIX_FAMILIES:
        candidate = next((preset_id for preset_id in ids if preset_id.startswith(prefix)), None)
        if candidate is None or candidate in chosen_set:
            continue
        chosen.append(candidate)
        chosen_set.add(candidate)
    return chosen


def test_presets_directory_inventory_matches_config_registry() -> None:
    config_doc = _load_json("config.json")
    inline_presets = config_doc.get("presets")
    assert isinstance(inline_presets, dict), "config.json must contain presets object"
    split_files = _split_preset_paths()
    assert split_files, "presets/*.json must not be empty"
    split_ids = sorted(path.stem for path in split_files)
    expected_ids = sorted(inline_presets)
    assert split_ids == expected_ids


def test_preset_filenames_are_slug_stable_and_unique() -> None:
    files = _split_preset_paths()
    names = [path.name for path in files]
    assert names == sorted(names), "preset filenames must be deterministic"
    assert len(set(names)) == len(names), "preset filenames must be unique"
    invalid = [name for name in names if _SLUG_FILE_RE.fullmatch(name) is None]
    assert not invalid, f"preset filenames must be lowercase slug-style: {invalid}"


def test_each_split_preset_matches_minimum_schema_shape() -> None:
    split = _load_split_presets()
    assert split
    subset_ids = _deterministic_schema_subset_ids()
    assert subset_ids, "deterministic schema subset must not be empty"
    for preset_id in subset_ids:
        preset = split[preset_id]
        assert isinstance(preset, dict), f"{preset_id} must be a dict"
        description = preset.get("description")
        assert isinstance(description, str) and description.strip(), f"{preset_id} missing description"
        has_steps = isinstance(preset.get("steps"), list)
        has_action = isinstance(preset.get("action"), str)
        assert has_steps or has_action, f"{preset_id} must define 'steps' or 'action'"


def test_config_load_roundtrip_presets_and_day_night_keys_stable() -> None:
    cfg = load_config("config.json")
    split = _load_split_presets()
    assert cfg.presets == split
    assert getattr(cfg, "_presets_source", None) == "split_files"
    assert sorted(cfg.presets.keys()) == sorted(split.keys())
    config_doc = _load_json("config.json")
    assert isinstance(config_doc.get("day_night_start_hour"), (int, float))
    assert isinstance(config_doc.get("day_start_hour"), (int, float))


def test_split_presets_are_primary_source_over_inline(tmp_path: Path) -> None:
    config_doc = {
        "presets": {
            "inline_only": {
                "description": "inline fallback",
                "steps": [{"cmd": "pipeline", "args": ["--dry-run"]}],
            }
        }
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(config_doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    preset_dir = tmp_path / "presets"
    preset_dir.mkdir(parents=True, exist_ok=True)
    external = {
        "description": "external source of truth",
        "steps": [{"cmd": "pipeline", "args": ["--demo"]}],
    }
    (preset_dir / "external_only.json").write_text(
        json.dumps(external, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    cfg = load_config(str(cfg_path))
    assert cfg.presets == {"external_only": external}
    assert getattr(cfg, "_presets_source", None) == "split_files"


def test_split_presets_fallback_to_inline_when_split_invalid(tmp_path: Path) -> None:
    inline = {
        "inline_ok": {
            "description": "inline fallback",
            "steps": [{"cmd": "pipeline", "args": ["--dry-run"]}],
        }
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"presets": inline}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    preset_dir = tmp_path / "presets"
    preset_dir.mkdir(parents=True, exist_ok=True)
    (preset_dir / "bad.json").write_text("{ invalid json\n", encoding="utf-8")
    cfg = load_config(str(cfg_path))
    assert cfg.presets == inline
    assert getattr(cfg, "_presets_source", None) == "config_inline"


def test_load_config_rejects_invalid_start_scene_type(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps({"start_scene": 123, "title": "Validation Demo"}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(SchemaValidationError) as exc_info:
        load_config(str(cfg_path))

    assert exc_info.value.file_path == str(cfg_path)
    assert exc_info.value.json_pointer == "/start_scene"
    assert "config.schema.json" in str(exc_info.value)


def test_config_presets_compat_mirror_matches_split_aggregate() -> None:
    split = _load_split_presets()
    mirror = _load_json(f"presets/{_MIRROR_FILE}")
    assert isinstance(mirror, dict), "compat mirror must be an object"
    assert mirror == split


def test_run_preset_references_resolve_deterministically() -> None:
    presets_doc = _load_split_presets()
    assert isinstance(presets_doc, dict)

    links: list[tuple[str, str]] = []
    for preset_id, preset in sorted(presets_doc.items()):
        if not isinstance(preset, dict):
            continue
        steps = preset.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            cmd = step.get("cmd")
            args = step.get("args")
            if cmd not in {"run-preset", "preset"} or not isinstance(args, list) or not args:
                continue
            target = str(args[0]).strip()
            if target:
                links.append((preset_id, target))
    assert links, "expected at least one deterministic run-preset link"
    representative = sorted(links)[0]
    assert representative[1] in presets_doc, f"representative preset link must resolve: {representative}"
    missing = [(preset_id, target) for preset_id, target in links if target not in presets_doc]
    assert not missing, f"missing run-preset targets: {missing}"
