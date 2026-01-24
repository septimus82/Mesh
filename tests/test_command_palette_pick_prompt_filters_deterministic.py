from __future__ import annotations


def test_command_palette_pick_prompt_filters_deterministic() -> None:
    from engine.command_palette import filter_options

    options = [
        ("scenes/b.json", "scenes/b.json"),
        ("packs/core_regions/scenes/Ashen_hub.json", "packs/core_regions/scenes/Ashen_hub.json"),
        ("scenes/a.json", "scenes/a.json"),
        ("", ""),
    ]

    assert filter_options(options, "scenes/") == [
        ("scenes/a.json", "scenes/a.json"),
        ("scenes/b.json", "scenes/b.json"),
        ("packs/core_regions/scenes/Ashen_hub.json", "packs/core_regions/scenes/Ashen_hub.json"),
    ]

    assert filter_options(options, "hub") == [
        ("packs/core_regions/scenes/Ashen_hub.json", "packs/core_regions/scenes/Ashen_hub.json"),
    ]
