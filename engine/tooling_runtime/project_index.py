from __future__ import annotations

from pathlib import Path

from engine import json_io
def build_project_index(root_dir: str, output_path: str) -> None:
    from engine.tooling.project_index import build_project_index as _build  # noqa: PLC0415

    index = _build(root_dir, config=None)
    out_path = Path(output_path)
    json_io.write_json_atomic(out_path, index)
