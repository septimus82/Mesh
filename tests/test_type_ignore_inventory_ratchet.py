from __future__ import annotations

from pathlib import Path

import pytest

from tooling import count_type_ignores

pytestmark = [pytest.mark.fast]

_BASELINE_MAX_TOTAL = 0
_MUST_BE_ZERO_FILES = (
    "mesh_cli/headless_arcade.py",
    "engine/behaviours/npc_schedule.py",
    "engine/particles.py",
    "engine/tilemap.py",
    "engine/editor/editor_command_dispatch_controller.py",
    "engine/quest_manager.py",
    "engine/scene_runtime/persistence.py",
    "engine/tooling/assist_command.py",
    "engine/tooling/trace_command.py",
    "engine/ui_overlays/debug.py",
    "mesh_cli/scene/stamp.py",
    "mesh_cli/verify_steps/pipeline.py",
    "engine/behaviours/conditional_activator.py",
    "engine/behaviours/cutscene_trigger.py",
)


def test_type_ignore_inventory_total_ratcheted() -> None:
    report = count_type_ignores._build_report([Path("engine"), Path("mesh_cli")], top_n=15)
    total = int(report["total_ignores"])
    assert total == _BASELINE_MAX_TOTAL, f"type ignore total regressed: {total} != {_BASELINE_MAX_TOTAL}"


def test_type_ignore_inventory_must_be_zero_files() -> None:
    report = count_type_ignores._build_report([Path("engine"), Path("mesh_cli")], top_n=15)
    rows = {str(row["file"]): int(row["count"]) for row in report["results"]}
    for rel_path in _MUST_BE_ZERO_FILES:
        count = rows.get(rel_path.replace("\\", "/"), 0)
        assert count == 0, f"{rel_path} reintroduced type: ignore ({count})"
