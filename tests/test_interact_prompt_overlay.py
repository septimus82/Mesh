from __future__ import annotations


def test_format_interact_prompt_text_is_stable() -> None:
    from engine.interaction import format_interact_prompt_text

    assert format_interact_prompt_text(None) == ""
    assert format_interact_prompt_text(object()) == "E: Interact"

