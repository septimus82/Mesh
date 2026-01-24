from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def export_ai_context(scene_paths: List[Path]) -> Dict[str, Any]:
    from engine.tooling.ai_context_exporter import export_ai_context as _export  # noqa: PLC0415

    return _export(scene_paths)

