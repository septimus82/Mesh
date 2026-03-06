from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from engine.assets_reload import reload_render_assets
from engine.post_processing import PostProcessEffect, PostProcessPipeline

pytestmark = [pytest.mark.fast]


class _MutableEffect(PostProcessEffect):
    name = "mutable_effect"

    def __init__(self, source: str) -> None:
        self._source = source

    @property
    def fragment_source(self) -> str:
        return self._source


class _MockCtx:
    def __init__(self) -> None:
        self.compile_calls: list[str] = []

    def program(self, *, vertex_shader: str, fragment_shader: str) -> Any:
        _ = vertex_shader
        self.compile_calls.append(fragment_shader)
        if "COMPILE_FAIL" in fragment_shader:
            raise RuntimeError("compile failed")
        return {"program_source": fragment_shader}


def test_post_process_shader_reload_keeps_last_good_on_compile_failure() -> None:
    ctx = _MockCtx()
    effect = _MutableEffect("COMPILE_FAIL")
    pipeline = PostProcessPipeline()
    pipeline.add_effect(effect)
    cache_key = "_mesh_pp_mutable_effect_program"
    last_good = object()
    setattr(ctx, cache_key, last_good)
    window = SimpleNamespace(ctx=ctx)

    counts = pipeline.reload_shaders(window, changed_paths=("assets/fx/test.frag",))

    assert counts["shader_programs_failed"] == 1
    assert counts["shader_programs_reloaded"] == 1  # passthrough program
    assert getattr(ctx, cache_key) is last_good


def test_assets_reload_shader_changes_trigger_shader_reload_path() -> None:
    calls: list[tuple[str, ...] | None] = []

    class _Pipeline:
        def reload_shaders(
            self,
            _window: object,
            *,
            changed_paths: tuple[str, ...] | None = None,
        ) -> dict[str, int]:
            calls.append(changed_paths)
            return {"shader_programs_reloaded": 2, "shader_programs_failed": 0}

    window = SimpleNamespace(post_process_pipeline=_Pipeline())
    counts = reload_render_assets(window, changed_paths=("packs/core/shaders/fx.glsl",))
    assert calls == [("packs/core/shaders/fx.glsl",)]
    assert counts["shader_programs_reloaded"] == 2
    assert counts["shader_programs_failed"] == 0


def test_assets_reload_non_shader_changes_skip_shader_reload_path() -> None:
    calls: list[tuple[str, ...] | None] = []

    class _Pipeline:
        def reload_shaders(
            self,
            _window: object,
            *,
            changed_paths: tuple[str, ...] | None = None,
        ) -> dict[str, int]:
            calls.append(changed_paths)
            return {"shader_programs_reloaded": 99, "shader_programs_failed": 99}

    window = SimpleNamespace(post_process_pipeline=_Pipeline())
    counts = reload_render_assets(window, changed_paths=("assets/sprite.png",))
    assert calls == []
    assert counts["shader_programs_reloaded"] == 0
    assert counts["shader_programs_failed"] == 0
