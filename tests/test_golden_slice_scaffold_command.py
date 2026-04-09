import json
import importlib.abc
import importlib.util
import sys
from pathlib import Path

import mesh_cli
from engine.ui import build_golden_slice_variant_picker_presets, load_config_json


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load_module_from_path(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    loader = spec.loader
    assert isinstance(loader, importlib.abc.Loader)
    loader.exec_module(module)
    return module


def test_golden_slice_scaffold_puzzle_lite_is_idempotent(tmp_path, monkeypatch, capsys):
    _write_json(
        tmp_path / "config.json",
        {"presets": {"zzz_preset": {"steps": []}, "aaa_preset": {"steps": []}}},
    )
    _write_json(
        tmp_path / "assets/data/quests.json",
        {"quests": [{"id": "zzz_quest", "stages": [], "reward": {"set_flags": {}, "inc_counters": {}}}]},
    )
    _write_json(tmp_path / "assets/data/events.json", {"events": [{"name": "zzz_event"}]})

    contracts_path = tmp_path / "tests/_variant_contracts.py"
    contracts_path.parent.mkdir(parents=True, exist_ok=True)
    contracts_path.write_text(
        "\n".join(
            [
                "GOLDEN_SLICE_VARIANT_CASES: tuple[object, ...] = (",
                "    GoldenSliceVariantCase(",
                "        variant=\"g2\",",
                "    ),",
                ")",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)

    rc = mesh_cli.main(
        [
            "golden-slice",
            "scaffold",
            "--location",
            "hollowmere_outskirts",
            "--kind",
            "puzzle_lite",
            "--variant",
            "L",
            "--gold",
            "45",
        ]
    )
    assert rc == 0
    assert capsys.readouterr().out == ""

    expected_paths = [
        Path("packs/core_regions/scenes/Hollowmere_outskirts_variant_l.json"),
        Path("worlds/golden_slice2_variant_l.json"),
        Path("assets/data/quests.json"),
        Path("assets/data/events.json"),
        Path("config.json"),
        Path("tests/_variant_contracts.py"),
    ]
    for rel in expected_paths:
        assert (tmp_path / rel).exists(), f"Missing generated file: {rel}"

    for rel in expected_paths:
        if rel.suffix == ".json":
            json.loads((tmp_path / rel).read_text(encoding="utf-8"))

    contracts_text = contracts_path.read_text(encoding="utf-8")
    assert "variant=\"l2\"" in contracts_text
    assert contracts_text.index("variant=\"g2\"") < contracts_text.index("variant=\"l2\"")

    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert "golden_slice2_variant_l" in config["presets"]
    assert list(config["presets"].keys()) == sorted(config["presets"].keys())

    quests = json.loads((tmp_path / "assets/data/quests.json").read_text(encoding="utf-8"))["quests"]
    quest_ids = {q["id"] for q in quests}
    assert "ridge2_variant_l_switch" in quest_ids
    assert "ridge2_variant_l_route" in quest_ids
    assert [q["id"] for q in quests if isinstance(q, dict) and "id" in q] == sorted(quest_ids)

    events = json.loads((tmp_path / "assets/data/events.json").read_text(encoding="utf-8"))["events"]
    event_names = {e["name"] for e in events}
    assert "ridge2_variant_l_unlock" in event_names
    assert [e["name"] for e in events if isinstance(e, dict) and "name" in e] == sorted(event_names)

    snapshot = {rel: (tmp_path / rel).read_bytes() for rel in expected_paths}

    rc2 = mesh_cli.main(
        [
            "golden-slice",
            "scaffold",
            "--location",
            "hollowmere_outskirts",
            "--kind",
            "puzzle_lite",
            "--variant",
            "L",
            "--gold",
            "45",
        ]
    )
    assert rc2 == 0
    assert capsys.readouterr().out == ""

    for rel, before in snapshot.items():
        assert (tmp_path / rel).read_bytes() == before, f"Non-idempotent output: {rel}"


def test_golden_slice_scaffold_dry_run_does_not_write(tmp_path, monkeypatch, capsys):
    _write_json(
        tmp_path / "config.json",
        {
            "presets": {
                "golden_slice2_index": {"steps": [{"cmd": "run-preset", "args": ["golden_slice2_showcase_all"]}]},
                "golden_slice2_showcase_all": {"steps": []},
            }
        },
    )
    _write_json(tmp_path / "assets/data/quests.json", {"quests": []})
    _write_json(tmp_path / "assets/data/events.json", {"events": []})
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests/_variant_contracts.py").write_text(
        "\n".join(
            [
                "GOLDEN_SLICE_VARIANT_CASES: tuple[object, ...] = (",
                "    GoldenSliceVariantCase(",
                "        variant=\"g2\",",
                "    ),",
                ")",
                "",
            ]
        ),
        encoding="utf-8",
    )

    before = {
        "config.json": (tmp_path / "config.json").read_bytes(),
        "assets/data/quests.json": (tmp_path / "assets/data/quests.json").read_bytes(),
        "assets/data/events.json": (tmp_path / "assets/data/events.json").read_bytes(),
        "tests/_variant_contracts.py": (tmp_path / "tests/_variant_contracts.py").read_bytes(),
    }

    monkeypatch.chdir(tmp_path)
    rc = mesh_cli.main(
        [
            "golden-slice",
            "scaffold",
            "--location",
            "hollowmere_outskirts",
            "--kind",
            "puzzle_lite",
            "--variant",
            "L",
            "--gold",
            "45",
            "--dry-run",
            "--register",
        ]
    )
    assert rc == 0

    out = capsys.readouterr().out.splitlines()
    assert out == [
        "[Mesh][GoldenSlice][dry-run] packs/core_regions/scenes/Hollowmere_outskirts_variant_l.json: would create new file",
        "[Mesh][GoldenSlice][dry-run] worlds/golden_slice2_variant_l.json: would create new file",
        "[Mesh][GoldenSlice][dry-run] config.json: would add preset 'golden_slice2_variant_l' (sorted)",
        "[Mesh][GoldenSlice][dry-run] config.json: would register 'golden_slice2_variant_l' in golden_slice2_showcase_all (sorted)",
        "[Mesh][GoldenSlice][dry-run] assets/data/quests.json: would add quests ['ridge2_variant_l_route', 'ridge2_variant_l_switch'] (sorted)",
        "[Mesh][GoldenSlice][dry-run] assets/data/events.json: would add event 'ridge2_variant_l_unlock' (sorted)",
        "[Mesh][GoldenSlice][dry-run] tests/_variant_contracts.py: would insert case variant 'l2'",
    ]

    assert not (tmp_path / "packs/core_regions/scenes/Hollowmere_outskirts_variant_l.json").exists()
    assert not (tmp_path / "worlds/golden_slice2_variant_l.json").exists()

    for rel, contents in before.items():
        assert (tmp_path / rel).read_bytes() == contents, f"dry-run mutated {rel}"


def test_golden_slice_scaffold_register_updates_showcase_all_and_picker_discovers(tmp_path, monkeypatch, capsys):
    _write_json(
        tmp_path / "config.json",
        {
            "presets": {
                "golden_slice_index": {"steps": [{"cmd": "run-preset", "args": ["golden_slice_showcase_all"]}]},
                "golden_slice_showcase_all": {"steps": []},
            }
        },
    )
    _write_json(tmp_path / "assets/data/quests.json", {"quests": []})
    _write_json(tmp_path / "assets/data/events.json", {"events": []})

    contracts_path = tmp_path / "tests/_variant_contracts.py"
    contracts_path.parent.mkdir(parents=True, exist_ok=True)
    contracts_path.write_text(
        "\n".join(
            [
                "GOLDEN_SLICE_VARIANT_CASES: tuple[object, ...] = (",
                "    GoldenSliceVariantCase(",
                "        variant=\"g\",",
                "    ),",
                ")",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    rc = mesh_cli.main(
        [
            "golden-slice",
            "scaffold",
            "--location",
            "ridge_outpost",
            "--kind",
            "linear",
            "--variant",
            "L",
            "--gold",
            "45",
            "--register",
        ]
    )
    assert rc == 0
    assert capsys.readouterr().out == ""

    config = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    presets = config.get("presets") or {}
    assert isinstance(presets, dict)
    showcase_all = presets.get("golden_slice_showcase_all")
    assert isinstance(showcase_all, dict)
    assert showcase_all.get("steps") == [{"cmd": "run-preset", "args": ["golden_slice_variant_l"]}]

    discovered = build_golden_slice_variant_picker_presets(load_config_json("config.json"))
    assert "golden_slice_variant_l" in discovered


def test_golden_slice_scaffold_generated_case_is_contract_green(tmp_path, monkeypatch, capsys):
    _write_json(tmp_path / "config.json", {"presets": {}})
    _write_json(tmp_path / "assets/data/quests.json", {"quests": []})
    _write_json(tmp_path / "assets/data/events.json", {"events": []})
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests/_variant_contracts.py").write_text(
        Path("tests/_variant_contracts.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    rc = mesh_cli.main(
        [
            "golden-slice",
            "scaffold",
            "--location",
            "hollowmere_outskirts",
            "--kind",
            "puzzle_lite",
            "--variant",
            "L",
            "--gold",
            "45",
        ]
    )
    assert rc == 0
    assert capsys.readouterr().out == ""

    contracts = _load_module_from_path("_tmp_variant_contracts", tmp_path / "tests/_variant_contracts.py")
    cases = [c for c in contracts.GOLDEN_SLICE_VARIANT_CASES if c.variant == "l2"]
    assert len(cases) == 1
    case = cases[0]
    assert case.kind == "puzzle_lite"

    contracts.load_scene_and_assert_valid(case.scene)
    contracts.assert_preset_targets_world(case.preset, case.world)
    contracts.assert_puzzle_lite_content_invariants(
        scene_json_path=case.scene,
        start_zone_id=case.start_zone,
        goal_zone_id=case.goal_zone,
        on_trigger_start=case.on_trigger_start,
        on_trigger_goal=case.on_trigger_goal,
        unlock_event=case.puzzle_unlock_event,
        unlocked_flag=case.puzzle_unlocked_flag,
        puzzle_quest_id=case.puzzle_quest_id,
        puzzle_start_toast=case.puzzle_start_toast,
        puzzle_complete_toast=case.puzzle_complete_toast,
        goal_quest_id=case.goal_quest_id,
        goal_start_toast=case.goal_start_toast,
        goal_complete_toast=case.goal_complete_toast,
        goal_complete_flag=case.goal_complete_flag,
        goal_gold=case.goal_gold,
    )
    contracts.assert_puzzle_lite_paths(
        start_zone_id=case.start_zone,
        goal_zone_id=case.goal_zone,
        unlock_event=case.puzzle_unlock_event,
        unlocked_flag=case.puzzle_unlocked_flag,
        puzzle_quest_id=case.puzzle_quest_id,
        puzzle_start_toast=case.puzzle_start_toast,
        puzzle_complete_toast=case.puzzle_complete_toast,
        goal_quest_id=case.goal_quest_id,
        goal_complete_flag=case.goal_complete_flag,
        goal_start_toast=case.goal_start_toast,
        goal_complete_toast=case.goal_complete_toast,
        goal_gold=case.goal_gold,
    )
