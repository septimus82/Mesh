"""Prefab palette loader for the in-engine editor."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from .logging_tools import get_logger

_LOG = get_logger("engine.editor_palette")

DEFAULT_PREFAB_PATH = os.path.join("assets", "prefabs.json")


def _resolve_path(path: str) -> str:
    if os.path.isabs(path):
        return path
    return os.path.join(os.getcwd(), path)


def _normalize_behaviours(entity: Dict[str, Any]) -> None:
    behaviours = entity.get("behaviours")
    if behaviours is None:
        entity["behaviours"] = []
        return
    if isinstance(behaviours, list):
        entity["behaviours"] = list(behaviours)
        return
    entity["behaviours"] = [behaviours]


def load_prefab_palette(path: str = DEFAULT_PREFAB_PATH, *, strict: bool = False) -> List[Dict[str, Any]]:
    """Load prefab definitions from JSON for the editor palette."""

    resolved_path = _resolve_path(path)
    try:
        with open(resolved_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        message = f"[Editor][Prefab] Missing prefab file: {path}"
        if strict:
            raise RuntimeError(message) from exc
        _LOG.warning("%s", message)
        return []
    except json.JSONDecodeError as exc:
        message = f"[Editor][Prefab] Invalid JSON in {path}: {exc}"
        if strict:
            raise RuntimeError(message) from exc
        _LOG.warning("%s", message)
        return []

    if not isinstance(data, list):
        message = f"[Editor][Prefab] Expected list at root of {path}"
        if strict:
            raise RuntimeError(message)
        _LOG.warning("%s", message)
        return []

    palette: List[Dict[str, Any]] = []
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            message = f"[Editor][Prefab] Entry {index} is not an object"
            if strict:
                raise RuntimeError(message)
            _LOG.warning("%s", message)
            return []

        for required in ("id", "display_name", "entity"):
            if required not in entry:
                message = f"[Editor][Prefab] Entry {index} missing '{required}'"
                if strict:
                    raise RuntimeError(message)
                _LOG.warning("%s", message)
                return []

        entity = entry["entity"]
        if not isinstance(entity, dict):
            message = f"[Editor][Prefab] Entry {index} has invalid entity data"
            if strict:
                raise RuntimeError(message)
            _LOG.warning("%s", message)
            return []

        normalized_entity = dict(entity)
        _normalize_behaviours(normalized_entity)

        prefab = {
            "id": str(entry["id"]),
            "display_name": str(entry["display_name"]),
            "entity": normalized_entity,
        }
        palette.append(prefab)

    return palette
