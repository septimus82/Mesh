"""Rewrite mesh_net/behaviours.json: the behaviour registry's validation metadata, which the graphics-free net
authority validates scene entities with (engine.behaviours.registry.validation_metadata). Run after a behaviour's
params or config fields change; tests/test_mesh_net_hd2d.py fails until it is current.

    py -3.13 tooling/write_net_behaviours.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from engine.behaviours import load_builtin_behaviours  # noqa: E402
from engine.behaviours.registry import validation_metadata  # noqa: E402

load_builtin_behaviours()
rows = [f"{json.dumps(name)}: {json.dumps(entry, sort_keys=True)}" for name, entry in validation_metadata().items()]
(REPO / "mesh_net" / "behaviours.json").write_text("{\n" + ",\n".join(rows) + "\n}\n", encoding="utf-8")
