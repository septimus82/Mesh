from __future__ import annotations


def test_command_palette_filter_scoring() -> None:
    from engine.command_palette import CommandSpec, filter_commands

    noop = lambda *_a: None
    always = lambda _w: (True, "")
    cmds = [
        CommandSpec(id="b", title="Reload Scene", section="Scene", keywords=("scene", "reload"), is_enabled=always, prompt=None, action=noop),
        CommandSpec(id="a", title="Toggle Tile Paint", section="Modes", keywords=("tile", "paint"), is_enabled=always, prompt=None, action=noop),
        CommandSpec(id="c", title="Persist Scene", section="Scene", keywords=("save", "persist"), is_enabled=always, prompt=None, action=noop),
        CommandSpec(id="d", title="Toggle Palette Mode", section="Modes", keywords=("palette", "stamp"), is_enabled=always, prompt=None, action=noop),
    ]

    # Prefix beats substring/keyword; tie-break by title then id.
    out = filter_commands(cmds, "tog")
    assert [c.id for c in out][:2] == ["d", "a"]

    # Substring beats keyword.
    out = filter_commands(cmds, "ene")
    assert [c.id for c in out][:1] == ["b"]

    out = filter_commands(cmds, "stamp")
    assert [c.id for c in out] == ["d"]

    out = filter_commands(
        [
            CommandSpec(id="z", title="Alpha", section="X", keywords=("x",), is_enabled=always, prompt=None, action=noop),
            CommandSpec(id="a", title="Alpha", section="X", keywords=("y",), is_enabled=always, prompt=None, action=noop),
        ],
        "alp",
    )
    assert [c.id for c in out] == ["a", "z"]

