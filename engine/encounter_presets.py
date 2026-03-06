from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_SWALLOW_ONCE_TAGS: set[str] = set()

def _log_swallow(tag: str, context: str, *, once: bool = True) -> None:
    if once and tag in _SWALLOW_ONCE_TAGS:
        return
    if once:
        _SWALLOW_ONCE_TAGS.add(tag)
    from engine.logging_tools import get_logger

    get_logger(__name__).debug("SWALLOW[%s] %s", tag, context, exc_info=True)


ALLOWED_PRESET_KEYS: frozenset[str] = frozenset(
    {
        "id",
        "encounter_budget",
        "boss_budget_reserve",
        "elite_cap",
        "allow_elites",
        "mini_boss_cap",
        "allow_mini_bosses",
    }
)


@dataclass(frozen=True)
class PresetIssue:
    level: str  # "ERROR" | "WARN"
    message: str
    sort_key: tuple


def _as_one_line(text: str) -> str:
    raw = str(text or "")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = " ".join(raw.split())
    return raw


def _display_path(path: Path) -> str:
    try:
        parts = list(path.parts)
        for i, part in enumerate(parts):
            if part.replace("\\", "/").lower() == "packs":
                return Path(*parts[i:]).as_posix()
    except Exception:
        _log_swallow("ENCO-001", "engine/encounter_presets.py pass-only blanket swallow")
        pass
    return path.as_posix()


def load_encounter_presets(
    path: Path,
    *,
    strict_unknown_keys: bool,
) -> tuple[dict[str, dict[str, Any]], list[PresetIssue]]:
    """Load encounter presets with deterministic validation.

    Accepted JSON shapes:
    - {"presets": [ {"id": "...", ...}, ... ]}
    - {"presets": { "id": {...}, ... }}
    - { "id": {...}, ... }
    - [ {"id": "...", ...}, ... ]
    """
    issues: list[PresetIssue] = []
    label = _display_path(path)

    if not path.exists():
        return {}, issues

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        msg = _as_one_line(f"{label}: failed to parse JSON: {type(exc).__name__}: {exc}")
        issues.append(PresetIssue("ERROR", msg, ("ERROR", msg)))
        return {}, issues

    presets_list: list[dict[str, Any]] = []

    if isinstance(data, dict):
        if "presets" in data:
            extra_keys = sorted(k for k in data.keys() if k != "presets")
            if extra_keys:
                msg = f"{label}: unknown top-level keys: {', '.join(extra_keys)}"
                level = "ERROR" if strict_unknown_keys else "WARN"
                issues.append(PresetIssue(level, msg, (level, msg)))

            raw = data.get("presets")
            if isinstance(raw, dict):
                for preset_id, preset_data in raw.items():
                    if isinstance(preset_data, dict):
                        presets_list.append({"id": preset_id, **preset_data})
                    else:
                        msg = f"{label}: preset '{preset_id}' must be an object"
                        issues.append(PresetIssue("ERROR", msg, ("ERROR", msg)))
            elif isinstance(raw, list):
                presets_list = [p for p in raw if isinstance(p, dict)]
                non_dict = [type(p).__name__ for p in raw if not isinstance(p, dict)]
                if non_dict:
                    msg = f"{label}: presets list items must be objects"
                    issues.append(PresetIssue("ERROR", msg, ("ERROR", msg)))
            else:
                msg = f"{label}: 'presets' must be a list or object"
                issues.append(PresetIssue("ERROR", msg, ("ERROR", msg)))
                return {}, sorted(issues, key=lambda i: i.sort_key)
        else:
            for preset_id, preset_data in data.items():
                if isinstance(preset_data, dict):
                    presets_list.append({"id": preset_id, **preset_data})
                else:
                    msg = f"{label}: preset '{preset_id}' must be an object"
                    issues.append(PresetIssue("ERROR", msg, ("ERROR", msg)))
    elif isinstance(data, list):
        presets_list = [p for p in data if isinstance(p, dict)]
        non_dict = [type(p).__name__ for p in data if not isinstance(p, dict)]
        if non_dict:
            msg = f"{label}: presets list items must be objects"
            issues.append(PresetIssue("ERROR", msg, ("ERROR", msg)))
    else:
        msg = f"{label}: root must be an object or list"
        issues.append(PresetIssue("ERROR", msg, ("ERROR", msg)))
        return {}, issues

    presets: dict[str, dict[str, Any]] = {}
    for preset in presets_list:
        preset_id_raw = preset.get("id")
        if not isinstance(preset_id_raw, str) or not preset_id_raw.strip():
            msg = f"{label}: preset id must be a non-empty string"
            issues.append(PresetIssue("ERROR", msg, ("ERROR", msg)))
            continue
        preset_id = preset_id_raw.strip()

        if preset_id in presets:
            msg = f"{label}: duplicate preset id '{preset_id}'"
            issues.append(PresetIssue("ERROR", msg, ("ERROR", msg)))
            continue

        unknown_keys = sorted(k for k in preset.keys() if k not in ALLOWED_PRESET_KEYS)
        if unknown_keys:
            msg = f"{label}: preset '{preset_id}' has unknown keys: {', '.join(unknown_keys)}"
            level = "ERROR" if strict_unknown_keys else "WARN"
            issues.append(PresetIssue(level, msg, (level, preset_id, msg)))

        cleaned: dict[str, Any] = {"id": preset_id}
        for key in sorted(ALLOWED_PRESET_KEYS):
            if key == "id":
                continue
            if key in preset:
                cleaned[key] = preset.get(key)

        for key in ("encounter_budget", "boss_budget_reserve"):
            if key in cleaned:
                val = cleaned.get(key)
                if val is None:
                    continue
                if not isinstance(val, (int, float)):
                    msg = f"{label}: preset '{preset_id}' {key} must be a number"
                    issues.append(PresetIssue("ERROR", msg, ("ERROR", preset_id, msg)))
                elif float(val) < 0:
                    msg = f"{label}: preset '{preset_id}' {key} must be non-negative"
                    issues.append(PresetIssue("ERROR", msg, ("ERROR", preset_id, msg)))

        for key in ("elite_cap", "mini_boss_cap"):
            if key in cleaned:
                val = cleaned.get(key)
                if val is None:
                    continue
                if not isinstance(val, int):
                    msg = f"{label}: preset '{preset_id}' {key} must be an integer"
                    issues.append(PresetIssue("ERROR", msg, ("ERROR", preset_id, msg)))
                elif val < 0:
                    msg = f"{label}: preset '{preset_id}' {key} must be non-negative"
                    issues.append(PresetIssue("ERROR", msg, ("ERROR", preset_id, msg)))

        for key in ("allow_elites", "allow_mini_bosses"):
            if key in cleaned:
                val = cleaned.get(key)
                if val is None:
                    continue
                if not isinstance(val, bool):
                    msg = f"{label}: preset '{preset_id}' {key} must be a boolean"
                    issues.append(PresetIssue("ERROR", msg, ("ERROR", preset_id, msg)))

        presets[preset_id] = cleaned

    issues_sorted = sorted(issues, key=lambda i: i.sort_key)
    return presets, issues_sorted
