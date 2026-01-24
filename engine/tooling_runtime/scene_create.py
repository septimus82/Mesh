from __future__ import annotations

from pathlib import Path
from typing import Any

from engine.tooling_runtime.entity_persist import PersistResult, persist_scene_payload


def create_empty_scene_file(scene_path: str, *, name: str | None = None) -> PersistResult:
    path_text = str(scene_path or "").strip()
    if not path_text:
        return PersistResult(ok=False, path="-", wrote=False, errors=["empty_path"])

    scene_name = str(name or "").strip() or Path(path_text).stem
    payload: dict[str, Any] = {"name": scene_name, "entities": []}
    return persist_scene_payload(path_text, payload, strict_no_overwrite=True)

