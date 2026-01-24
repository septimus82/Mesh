from __future__ import annotations

import json
from pathlib import Path

def build_project_index(root_dir: str, output_path: str) -> None:
    from engine.tooling.project_index import build_project_index as _build  # noqa: PLC0415

    index = _build(root_dir, config=None)
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
