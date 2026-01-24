from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from engine.encounter_presets import load_encounter_presets
from engine.tooling.content_inventory import discover_scene_paths


def _rel_posix(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        return path.as_posix()


def _safe_read_json_object(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("JSON root is not an object")
    return raw


def lint_encounter_preset_references(*, repo_root: Path) -> dict[str, Any]:
    """Fast, deterministic scan to ensure referenced encounter presets exist.

    Scans:
    - scenes/*.json
    - packs/**/scenes/*.json

    Checks:
    - settings.encounter_preset_id (when present and non-empty) exists in encounter_presets.json
    """
    root = Path(repo_root).resolve()

    presets_path = root / "packs" / "core_regions" / "data" / "encounter_presets.json"
    presets, preset_issues = load_encounter_presets(presets_path, strict_unknown_keys=False)
    known_ids = set(presets.keys())

    errors: list[dict[str, str]] = []

    if preset_issues:
        for issue in preset_issues:
            if issue.level == "ERROR":
                errors.append(
                    {
                        "code": "preset.file.invalid",
                        "path": "packs/core_regions/data/encounter_presets.json",
                        "message": issue.message,
                    }
                )

    scene_paths = discover_scene_paths(root)
    reference_count = 0

    for scene_path in scene_paths:
        rel = _rel_posix(scene_path, root)
        try:
            scene = _safe_read_json_object(scene_path)
        except Exception as exc:  # noqa: BLE001
            errors.append(
                {
                    "code": "scene.json.invalid",
                    "path": rel,
                    "message": f"Failed to parse JSON: {type(exc).__name__}: {exc}",
                }
            )
            continue

        settings = scene.get("settings")
        settings = settings if isinstance(settings, dict) else {}
        raw = settings.get("encounter_preset_id")
        if not isinstance(raw, str):
            continue
        preset_id = raw.strip()
        if not preset_id:
            continue

        reference_count += 1
        if preset_id not in known_ids:
            errors.append(
                {
                    "code": "preset.unknown",
                    "path": rel,
                    "message": f"Unknown encounter_preset_id '{preset_id}'",
                }
            )

    def _sort_key(item: dict[str, str]) -> tuple[str, str]:
        return (item.get("path", ""), item.get("code", ""))

    errors.sort(key=_sort_key)
    ok = len(errors) == 0

    return {
        "ok": ok,
        "errors": errors,
        "summary": {
            "scene_count": len(scene_paths),
            "reference_count": reference_count,
            "error_count": len(errors),
        },
    }

