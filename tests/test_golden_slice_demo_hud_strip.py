from engine.ui import (
    GOLDEN_SLICE_DEMO_HUD_MAX_CHARS,
    build_act1_demo_hud_status_line,
    build_golden_slice_demo_hud_status_line,
    is_act1_demo_context,
    is_golden_slice_demo_context,
)


def test_golden_slice_demo_hud_status_line_is_stable_and_capped() -> None:
    line = build_golden_slice_demo_hud_status_line(
        preset_id="golden_slice_variant_k",
        world_id=None,
        active_quest="ridge_variant_k_switch_gate",
        gold_delta=35,
        new_flags=1,
        hint_keys=["V", "H"],
    )
    assert isinstance(line, str)
    assert len(line) <= GOLDEN_SLICE_DEMO_HUD_MAX_CHARS
    assert "GS K" in line
    assert "Quest:" in line
    assert "Δg +35" in line
    assert "+flags 1" in line
    assert "Keys: V,H" in line
    line2 = build_golden_slice_demo_hud_status_line(
        preset_id="golden_slice2_variant_k",
        world_id=None,
        active_quest="ridge2_variant_k_route",
        gold_delta=45,
        new_flags=1,
        hint_keys=["V", "H"],
    )
    assert "GS K2" in line2


def test_golden_slice_demo_hud_context_gate() -> None:
    assert is_golden_slice_demo_context(
        preset_id="golden_slice_variant_g",
        world_id=None,
        world_file=None,
    )
    assert is_golden_slice_demo_context(
        preset_id=None,
        world_id="golden_slice_variant_h",
        world_file=None,
    )
    assert is_golden_slice_demo_context(
        preset_id=None,
        world_id=None,
        world_file="worlds/golden_slice_variant_i.json",
    )
    assert (
        is_golden_slice_demo_context(
            preset_id="not_golden",
            world_id="main_world",
            world_file="worlds/main_world.json",
        )
        is False
    )
    assert is_golden_slice_demo_context(
        preset_id="golden_slice2_variant_g",
        world_id=None,
        world_file=None,
    )
    assert is_golden_slice_demo_context(
        preset_id=None,
        world_id="golden_slice2_variant_j",
        world_file=None,
    )
    assert is_golden_slice_demo_context(
        preset_id=None,
        world_id=None,
        world_file="worlds/golden_slice2_variant_k.json",
    )


def test_act1_demo_hud_context_gate() -> None:
    assert is_act1_demo_context(
        preset_id="act1_demo",
        world_id=None,
        world_file=None,
    )
    assert is_act1_demo_context(
        preset_id=None,
        world_id="act1_chapter1",
        world_file=None,
    )
    assert is_act1_demo_context(
        preset_id=None,
        world_id=None,
        world_file="worlds/act1_prologue.json",
    )
    assert (
        is_act1_demo_context(
            preset_id="not_act1",
            world_id="main_world",
            world_file="worlds/main_world.json",
        )
        is False
    )


def test_act1_demo_hud_status_line_format_is_compact_and_stable() -> None:
    line = build_act1_demo_hud_status_line(
        preset_id="act1_chapter1",
        world_id="act1_chapter1",
        world_file="worlds/act1_chapter1.json",
        active_quest="quest_act1_ch1_complete",
        gold_delta=20,
        new_flags=2,
        show_picker_hint=True,
    )
    assert isinstance(line, str)
    assert len(line) <= GOLDEN_SLICE_DEMO_HUD_MAX_CHARS
    assert line.startswith("Act 1: act1_chapter1")
    assert "| quest:quest_act1_ch1_complete" in line
    assert "+gold:+20" in line
    assert "+flags:2" in line
    assert line.endswith("| V picker")
