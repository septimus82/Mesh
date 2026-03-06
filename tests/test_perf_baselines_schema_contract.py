from __future__ import annotations

import json
from pathlib import Path

import pytest


pytestmark = [pytest.mark.fast]


def _load_json(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict), f"{path.as_posix()}: expected JSON object"
    return payload


def test_perf_scene_set_schema_and_paths_exist() -> None:
    path = Path("tooling/perf_baselines/scenes.json")
    payload = _load_json(path)
    assert payload.get("schema_version") == 1

    scenes = payload.get("scenes")
    assert isinstance(scenes, list)
    assert 3 <= len(scenes) <= 5

    ids: list[str] = []
    for entry in scenes:
        assert isinstance(entry, dict)
        scene_id = str(entry.get("id", "")).strip()
        scene_path = str(entry.get("path", "")).strip()
        assert scene_id
        assert scene_path
        ids.append(scene_id)
        assert Path(scene_path).exists(), f"missing baseline scene file: {scene_path}"
    assert ids == sorted(ids), "scene ids must be deterministic (sorted)"
    assert len(ids) == len(set(ids)), "duplicate perf scene ids detected"


def test_perf_baseline_schema_matches_scene_set() -> None:
    scene_set_path = Path("tooling/perf_baselines/scenes.json")
    baseline_path = Path("tooling/perf_baselines/baselines.json")
    scene_set = _load_json(scene_set_path)
    baseline = _load_json(baseline_path)

    assert baseline.get("schema_version") == 1
    assert baseline.get("scene_set") == scene_set_path.as_posix()
    assert int(baseline.get("ticks", 0)) > 0

    scene_set_entries = scene_set.get("scenes")
    baseline_entries = baseline.get("scenes")
    assert isinstance(scene_set_entries, list)
    assert isinstance(baseline_entries, list)

    expected_ids = [str(entry.get("id", "")).strip() for entry in scene_set_entries if isinstance(entry, dict)]
    actual_ids = [str(entry.get("id", "")).strip() for entry in baseline_entries if isinstance(entry, dict)]
    assert actual_ids == sorted(actual_ids), "baseline scene ids must be deterministic (sorted)"
    assert actual_ids == sorted(expected_ids)

    metric_names = baseline.get("metric_names")
    assert isinstance(metric_names, list) and metric_names
    assert metric_names == sorted(str(name) for name in metric_names)

    totals = baseline.get("totals")
    assert isinstance(totals, dict)
    for metric_name in metric_names:
        assert metric_name in totals
        assert isinstance(totals[metric_name], int)

    tolerances = baseline.get("tolerances")
    assert isinstance(tolerances, dict)
    assert "__default__" in tolerances
    default_tol = tolerances.get("__default__", {})
    assert isinstance(default_tol, dict)
    assert isinstance(default_tol.get("increase_allowed", 0), int)

    for entry in baseline_entries:
        assert isinstance(entry, dict)
        counters = entry.get("counters")
        assert isinstance(counters, dict)
        assert sorted(counters.keys()) == metric_names
        for metric_name in metric_names:
            assert isinstance(counters[metric_name], int)
            assert counters[metric_name] >= 0

