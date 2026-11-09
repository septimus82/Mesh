"""M17-L4-1: the HD-2D final composite's bookkeeping, without a GPU: which stage makes the picture, when Studio's lines
are drawn after it, what is allocated (only when needed, once per picture size) and freed, the driver refusing it,
and draw()'s two readbacks kept apart."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest

from engine.hd2d import renderer as R
from engine.hd2d.composite import FinalComposite, final_stage, overlay_after

pytestmark = [pytest.mark.fast]


class _Obj:
    def __init__(self, kind: str, log: list[tuple[str, str]], size: tuple[int, int] | None = None) -> None:
        self.kind, self.log, self.size, self.filter = kind, log, size, None
        log.append(("make", kind))

    def delete(self) -> None:
        self.log.append(("delete", self.kind))


class _Ctx:
    NEAREST = 9728

    def __init__(self, refuse: bool = False) -> None:
        self.log: list[tuple[str, str]] = []
        self.refuse = refuse

    def program(self, **_shaders: str) -> _Obj:
        if self.refuse:
            raise R._gpu_refused()[0]("refused")
        return _Obj("program", self.log)

    def texture(self, size: tuple[int, int], components: int) -> _Obj:
        assert components == 4  # (RGBA8, as the world's colour)
        return _Obj("texture", self.log, size)

    def framebuffer(self, color_attachments: list[Any]) -> _Obj:
        return _Obj("framebuffer", self.log, color_attachments[0].size)


def test_the_stage_and_when_studio_s_lines_go_after_it() -> None:
    assert final_stage(dof=False, composite=False) == "blit"
    assert final_stage(dof=True, composite=False) == "dof"
    assert final_stage(dof=False, composite=True) == "composite"
    assert final_stage(dof=True, composite=True) == "dof+composite"
    assert [overlay_after(s) for s in ("blit", "dof", "composite", "dof+composite")] == [False, True, True, True]


def test_one_program_and_a_chain_target_only_when_asked_for_once_per_size() -> None:
    ctx = _Ctx()
    comp = FinalComposite(ctx, "vs")
    assert ctx.log == [("make", "program")]  # nothing else until the depth of field runs before it
    fbo, tex = comp.chain_target((640, 360))
    assert tex.size == (640, 360) and fbo.size == (640, 360) and tex.filter == (ctx.NEAREST, ctx.NEAREST)
    assert comp.chain_target((640, 360)) == (fbo, tex) and comp.chain_allocations == 1  # reused while the size holds
    comp.chain_target((800, 450))  # a new size: the old target freed, a new one made
    assert comp.chain_allocations == 2
    assert ctx.log[1:] == [("make", "texture"), ("make", "framebuffer"), ("delete", "framebuffer"), ("delete", "texture"),
                           ("make", "texture"), ("make", "framebuffer")]
    assert len(comp.gl_objects()) == 3
    comp.release()
    made = sum(1 for op, _k in ctx.log if op == "make")
    freed = sum(1 for op, _k in ctx.log if op == "delete")
    assert made == freed == 5  # everything it ever made, freed


def test_release_without_a_chain_target_frees_its_program() -> None:
    ctx = _Ctx()
    FinalComposite(ctx, "vs").release()
    assert ctx.log == [("make", "program"), ("delete", "program")]


def test_the_renderer_makes_it_once_and_a_refusing_driver_leaves_the_original_picture() -> None:
    fake = SimpleNamespace(ctx=_Ctx(), _composite=None, composite_unavailable=None)
    first = R.Hd2dRenderer._final_composite(cast(Any, fake))
    assert first is not None and R.Hd2dRenderer._final_composite(cast(Any, fake)) is first
    assert fake.ctx.log == [("make", "program")]
    refused = SimpleNamespace(ctx=_Ctx(refuse=True), _composite=None, composite_unavailable=None)
    assert R.Hd2dRenderer._final_composite(cast(Any, refused)) is None
    assert refused.composite_unavailable.startswith("the final composite is off on this computer: the graphics driver")
    assert R.Hd2dRenderer._final_composite(cast(Any, refused)) is None  # (not tried again every frame)


def test_draw_keeps_the_world_readback_and_the_picture_readback_apart() -> None:
    with pytest.raises(ValueError, match="not both"):
        R.Hd2dRenderer.draw(cast(Any, SimpleNamespace()), read=True, read_final=True)
