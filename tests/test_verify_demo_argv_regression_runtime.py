import sys

from engine.tooling_runtime.verify_demo import build_verify_demo_pytest_cmd


def test_verify_demo_runtime_builds_exact_curated_pytest_argv() -> None:
    # This is intentionally duplicated (not imported from the module)
    # to lock argv ordering and curated test selection.
    curated = [
        "tests/test_golden_slice_content_invariants.py",
        "tests/test_golden_slice_boss_victory_ux_contract.py",
        "tests/test_golden_slice_demo_hud_strip.py",
        "tests/test_golden_slice_variant_picker_list_source.py",
        "tests/test_golden_slice_variant_picker_hardening.py",
        "tests/test_golden_slice_variant_e_occluder_showcase.py",
        "tests/test_golden_slice_variant_e_boss_reward_clarity.py",
        "tests/test_golden_slice_variants_contract.py",
        "tests/test_golden_slice_scaffold_command.py",
        "tests/test_golden_slice_pipeline_gate.py",
        "tests/test_golden_slice_lighting_showcase_intent.py",
        "tests/test_act1_prologue_slice.py",
        "tests/test_act1_chapter1_slice.py",
        "tests/test_act1_chapter1_preset_exists.py",
        "tests/test_act1_chapter2_stub.py",
        "tests/test_act1_chapter2_slice.py",
        "tests/test_act1_chapter3_stub.py",
        "tests/test_act1_chapter3_slice.py",
        "tests/test_act1_chapter4_stub.py",
        "tests/test_act1_chapter4_slice.py",
        "tests/test_act1_chapter5_stub.py",
        "tests/test_presets_required_exist.py",
        "tests/test_presets_not_duplicated.py",
        "tests/test_preset_demo_master_exists.py",
        "tests/test_preset_act1_full_demo_exists.py",
        "tests/test_preset_golden_slice_demo_all_exists.py",
        "tests/test_preset_golden_slice_index_exists.py",
        "tests/test_preset_golden_slice_showcase_all_exists.py",
        "tests/test_preset_registry_schema.py",
    ]

    expected = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-W",
        "error",
        "--ignore-glob=tests/temp_*",
        *curated,
    ]

    assert build_verify_demo_pytest_cmd() == expected
