"""Contract tests for the Scene Render Pipeline.

Verifies that the pipeline:
1. Sorts sprites correctly (y-sort, z-explicit, etc).
2. Generates correct draw commands (shadows, outlines).
3. Respects render context settings (batching, culling).
4. Is deterministic given the same input.
"""
# Mock these instead of strict typing for tests, or just pass dicts/objects if allowed
# But for now, let's just use Any or mocks where needed.
# We need the classes just for typing? No python is dynamic.
# But build_render_context expects them.
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

import engine.optional_arcade as optional_arcade
from engine.render_queue import DrawSpriteCmd
from engine.scene_render_pipeline import (
    DrawPlan,
    SpriteDrawOp,
    build_render_context,
    compute_draw_plan,
    execute_scene_plan,
)

pytestmark = [pytest.mark.fast]

@dataclass
class MockShadowSettings:
    enabled: bool = False
    ao_enabled: bool = False
    contact_enabled: bool = False

@dataclass
class MockDepthTintSettings:
    enabled: bool = False

@dataclass
class MockOutlineSettings:
    enabled: bool = False


class MockSprite:
    def __init__(self, x=0, y=0, z=0, texture=None):
        self.center_x = x
        self.center_y = y
        self.width = 32
        self.height = 32
        self.scale = 1.0
        self.angle = 0.0
        self.alpha = 255
        self.color = (255, 255, 255, 255)
        self.texture = texture or MagicMock()
        self.mesh_entity_data = {"render_layer": 0, "depth_z": z}
        self.mesh_texture_key = ("texture", "mock")

class MockRenderQueue:
    def __init__(self):
        self.commands = []

    def submit(self, cmd):
        self.commands.append(cmd)

    def flush(self):
        pass

    def is_enabled(self):
        return True


class MockRenderOnlySprite:
    def __init__(self):
        self.center_x = 0
        self.center_y = 0
        self.width = 16
        self.height = 16
        self.scale = 1.0
        self.angle = 0.0
        self.alpha = 255
        self.color = (255, 255, 255, 255)
        self.texture = MagicMock()
        self.mesh_entity_data = {"render_layer": 0, "depth_z": 0}
        self.mesh_texture_key = ("texture", "render_only")
        self.render_called = False

    def render(self):
        self.render_called = True

def test_build_context_defaults():
    """Verify build_render_context creates a valid context with default settings."""
    ctx = build_render_context(
        sprites=[],
        background_planes=[],
        camera_pos=(0, 0),
        viewport_size=(800, 600),
        zoom=1.0,
        sort_mode="y_sort",
        shadows_enabled=False,
        shadows_ao_enabled=False,
        shadows_contact_enabled=False,
        depth_tint_settings=MockDepthTintSettings(),
        outline_settings=MockOutlineSettings(),
        use_culling=False
    )
    assert ctx.sort_mode == "y_sort"
    assert isinstance(ctx.shadows_enabled, bool)
    assert not ctx.use_culling

def test_compute_draw_plan_sorting():
    """Verify sprites are sorted correctly (y-sort)."""
    s1 = MockSprite(y=100)
    s2 = MockSprite(y=0)
    s3 = MockSprite(y=200)

    ctx = build_render_context(
        sprites=[s1, s2, s3],
        background_planes=[],
        camera_pos=(0, 0),
        viewport_size=(800, 600),
        zoom=1.0,
        sort_mode="y_sort",
        shadows_enabled=False,
        shadows_ao_enabled=False,
        shadows_contact_enabled=False,
        depth_tint_settings=MockDepthTintSettings(),
        outline_settings=MockOutlineSettings(),
        use_culling=False
    )

    plan = compute_draw_plan(ctx)

# Sort uses render_sort_model.
    # Current implementation in render_sort_model uses +y as sort key.
    # So Low Y (Bottom) -> First -> Back
    # High Y (Top) -> Last -> Front
    # (Matches side-scroller or specific layering, but confusing for top-down).
    # We assert what the model DOES, not what it hypothetically should do.

    assert len(plan.sprite_ops) == 3
    # Expect order: s2 (0), s1 (100), s3 (200)
    assert plan.sprite_ops[0].sprite == s2
    assert plan.sprite_ops[1].sprite == s1
    assert plan.sprite_ops[2].sprite == s3


def test_compute_draw_plan_culling_accepts_tuple_sprite_scale():
    """Arcade may expose non-uniform sprite scale as a tuple."""
    sprite = MockSprite(x=0, y=0)
    sprite.width = None
    sprite.height = None
    sprite.texture.width = 32
    sprite.texture.height = 64
    sprite.scale = (2.0, 0.5)

    ctx = build_render_context(
        sprites=[sprite],
        background_planes=[],
        camera_pos=(0, 0),
        viewport_size=(800, 600),
        zoom=1.0,
        sort_mode="y_sort",
        shadows_enabled=False,
        shadows_ao_enabled=False,
        shadows_contact_enabled=False,
        depth_tint_settings=MockDepthTintSettings(),
        outline_settings=MockOutlineSettings(),
        use_culling=True,
        camera_rect=(-100, -100, 100, 100),
    )

    plan = compute_draw_plan(ctx)

    assert [op.sprite for op in plan.sprite_ops] == [sprite]


def test_execution_emits_commands():
    """Verify execute_scene_plan submits DrawSpriteCmds to the queue."""
    sprite = MockSprite(x=10, y=20)
    ctx = build_render_context(
        sprites=[sprite],
        background_planes=[],
        camera_pos=(0, 0),
        viewport_size=(800, 600),
        zoom=1.0,
        sort_mode="y_sort",
        shadows_enabled=False,
        shadows_ao_enabled=False,
        shadows_contact_enabled=False,
        depth_tint_settings=MockDepthTintSettings(),
        outline_settings=MockOutlineSettings(),
        use_culling=False
    )
    plan = compute_draw_plan(ctx)

    queue = MockRenderQueue()
    execute_scene_plan(plan, render_queue=queue, use_batching=True)

    assert len(queue.commands) == 1
    cmd = queue.commands[0]
    assert isinstance(cmd, DrawSpriteCmd)
    assert cmd.x == 10
    assert cmd.y == 20

def test_shadow_generation():
    """Verify shadow operations are generated if enabled."""
    sprite = MockSprite()

    # Enable shadows
    ctx = build_render_context(
        sprites=[sprite],
        background_planes=[],
        camera_pos=(0, 0),
        viewport_size=(800, 600),
        zoom=1.0,
        sort_mode="y_sort",
        shadows_enabled=True,
        shadows_ao_enabled=True,
        shadows_contact_enabled=False,
        depth_tint_settings=MockDepthTintSettings(),
        outline_settings=MockOutlineSettings(),
        use_culling=False
    )

    plan = compute_draw_plan(ctx)

    # Shadows are put into shadow_ops
    assert len(plan.shadow_ops) > 0

def test_determinism():
    """Verify the pipeline produces identical plans for identical inputs."""
    sprites = [MockSprite(y=i) for i in range(10)]
    args = dict(
        sprites=sprites,
        background_planes=[],
        camera_pos=(0,0),
        viewport_size=(800,600),
        zoom=1.0,
        sort_mode="y_sort",
        shadows_enabled=False,
        shadows_ao_enabled=False,
        shadows_contact_enabled=False,
        depth_tint_settings=MockDepthTintSettings(),
        outline_settings=MockOutlineSettings(),
        use_culling=False
    )

    ctx1 = build_render_context(**args)
    ctx2 = build_render_context(**args)

    plan1 = compute_draw_plan(ctx1)
    plan2 = compute_draw_plan(ctx2)

    # Compare op lists
    assert len(plan1.sprite_ops) == len(plan2.sprite_ops)
    for op1, op2 in zip(plan1.sprite_ops, plan2.sprite_ops):
        assert op1.sprite == op2.sprite


def test_execute_scene_plan_uses_render_when_draw_missing(monkeypatch):
    sprite = MockRenderOnlySprite()
    plan = DrawPlan(background_ops=[], shadow_ops=[], sprite_ops=[SpriteDrawOp(sprite=sprite)])

    monkeypatch.setattr(optional_arcade, "arcade", object())

    execute_scene_plan(plan, render_queue=None, use_batching=False)

    assert sprite.render_called is True

