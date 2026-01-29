from __future__ import annotations

import engine.optional_arcade as oa


def test_optional_arcade_window_subclassable() -> None:
    class W(oa.arcade.Window):
        pass

    assert issubclass(W, oa.arcade.Window)

    has_arcade = getattr(oa.arcade, "HAS_ARCADE", None)
    if has_arcade is None:
        has_arcade = getattr(oa, "HAS_ARCADE", None)
    assert isinstance(has_arcade, bool)
