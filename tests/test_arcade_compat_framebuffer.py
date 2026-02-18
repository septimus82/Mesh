from __future__ import annotations

import pytest

from engine.arcade_compat import (
    activate_framebuffer,
    clear_framebuffer,
    close_framebuffer_activation,
    restore_framebuffer,
)

pytestmark = [pytest.mark.fast]


def test_activate_framebuffer_auto_prefers_use() -> None:
    called: list[str] = []

    class _Fbo:
        def use(self) -> None:
            called.append("use")

        def activate(self):  # noqa: ANN201
            called.append("activate")
            return None

    backend, cm = activate_framebuffer(_Fbo(), backend="auto")
    assert backend == "fbo.use"
    assert cm is None
    assert called == ["use"]


def test_activate_framebuffer_explicit_activate_enters_context() -> None:
    called: list[str] = []

    class _CM:
        def __enter__(self):  # noqa: ANN204
            called.append("enter")
            return self

        def __exit__(self, *_args: object) -> bool:
            called.append("exit")
            return False

    class _Fbo:
        def activate(self):  # noqa: ANN201
            called.append("activate")
            return _CM()

    backend, cm = activate_framebuffer(_Fbo(), backend="fbo.activate")
    assert backend == "fbo.activate"
    assert cm is not None
    assert called == ["activate", "enter"]
    close_framebuffer_activation(cm)
    assert called == ["activate", "enter", "exit"]


def test_clear_framebuffer_falls_back_to_ctx_clear() -> None:
    called: list[str] = []

    class _Fbo:
        def clear(self, *_args: object) -> None:
            raise RuntimeError("nope")

    class _Ctx:
        def clear(self, *_args: object) -> None:
            called.append("ctx.clear")

    assert clear_framebuffer(_Ctx(), _Fbo(), 1.0, 1.0, 1.0, 1.0) is True
    assert called == ["ctx.clear"]


def test_restore_framebuffer_prefers_screen_use() -> None:
    called: list[str] = []

    class _Screen:
        def use(self) -> None:
            called.append("screen.use")

    class _Prev:
        def use(self) -> None:
            called.append("prev.use")

    class _Ctx:
        screen = _Screen()

    restore_framebuffer(_Ctx(), _Prev())
    assert called == ["screen.use"]

