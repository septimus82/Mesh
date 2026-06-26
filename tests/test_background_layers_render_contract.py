"""Contract tests for background-layer rendering under Arcade 3.

Arcade 3 removed ``arcade.draw_texture_rectangle`` in favour of
``draw_texture_rect(texture, rect)``. The headless arcade stub historically still
defined the removed function, so no test caught the regression and real windows
rendered a flat clear colour with no background layers/planes.

These tests pin:
  * ``draw_background_layers`` emits the expected centred draws (arcade-free).
  * ``optional_arcade.draw_texture_rect_compat`` prefers the Arcade-3 API and
    falls back to the legacy call (so the headless stub path keeps working).
  * No engine source calls the removed API as a bare attribute (grep ratchet).
  * (optional, GL-gated) a real offscreen render produces non-clear pixels.
"""

from __future__ import annotations

import os
import re
import struct
import zlib
from pathlib import Path

import pytest

from engine import background_layers, optional_arcade
from engine.background_layers import (
    BackgroundLayer,
    compute_background_screen_center,
    draw_background_layers,
)

pytestmark = [pytest.mark.fast]


class _FakeTexture:
    def __init__(self, name: str, width: int, height: int) -> None:
        self.name = name
        self.width = width
        self.height = height


# ---------------------------------------------------------------------------
# 1. Draw-capture: world-space positions (live render path).
# ---------------------------------------------------------------------------
def test_draw_background_layers_projected_space_parallax_centers() -> None:
    layers = [
        BackgroundLayer(id="far", path="far.png", z=0, parallax=0.5),
        BackgroundLayer(id="near", path="near.png", z=10, parallax=1.0),
    ]
    textures = {
        "far.png": _FakeTexture("far", 128, 64),
        "near.png": _FakeTexture("near", 64, 32),
    }
    recorded: list[tuple[float, float, float, float, str]] = []

    def recorder(cx: float, cy: float, w: float, h: float, tex) -> None:  # type: ignore[no-untyped-def]
        recorded.append((cx, cy, w, h, tex.name))

    draw_background_layers(
        layers,
        camera_x=100.0,
        camera_y=50.0,
        viewport_w=800.0,
        viewport_h=600.0,
        zoom=1.0,
        coordinate_space="projected",
        draw_texture=recorder,
        get_texture=lambda path: textures.get(path),
    )

    by_name = {name: (cx, cy, w, h) for cx, cy, w, h, name in recorded}
    assert by_name["far"][:2] == compute_background_screen_center(
        camera_x=100.0, camera_y=50.0, parallax=0.5, viewport_w=800.0, viewport_h=600.0
    )
    assert by_name["near"][:2] == compute_background_screen_center(
        camera_x=100.0, camera_y=50.0, parallax=1.0, viewport_w=800.0, viewport_h=600.0
    )
    assert by_name["far"][2:] == (128.0, 64.0)
    assert by_name["near"][2:] == (64.0, 32.0)


def test_draw_background_layers_screen_space_legacy_path() -> None:
    layers = [
        BackgroundLayer(id="far", path="far.png", z=0, parallax=0.5),
        BackgroundLayer(id="near", path="near.png", z=10, parallax=1.0),
    ]
    textures = {
        "far.png": _FakeTexture("far", 128, 64),
        "near.png": _FakeTexture("near", 64, 32),
    }
    recorded: list[tuple[float, float, float, float, str]] = []

    def recorder(cx: float, cy: float, w: float, h: float, tex) -> None:  # type: ignore[no-untyped-def]
        recorded.append((cx, cy, w, h, tex.name))

    draw_background_layers(
        layers,
        camera_x=0.0,
        camera_y=0.0,
        viewport_w=800.0,
        viewport_h=600.0,
        zoom=1.0,
        coordinate_space="screen",
        draw_texture=recorder,
        get_texture=lambda path: textures.get(path),
    )

    assert recorded == [
        (400.0, 300.0, 128.0, 64.0, "far"),
        (400.0, 300.0, 64.0, 32.0, "near"),
    ]


def test_draw_background_layers_screen_space_parallax_offsets() -> None:
    layers = [
        BackgroundLayer(id="far", path="far.png", z=0, parallax=0.5),
        BackgroundLayer(id="near", path="near.png", z=10, parallax=1.0),
    ]
    textures = {
        "far.png": _FakeTexture("far", 100, 100),
        "near.png": _FakeTexture("near", 100, 100),
    }
    recorded: list[tuple[float, float, str]] = []

    def recorder(cx: float, cy: float, w: float, h: float, tex) -> None:  # type: ignore[no-untyped-def]
        recorded.append((cx, cy, tex.name))

    draw_background_layers(
        layers,
        camera_x=100.0,
        camera_y=0.0,
        viewport_w=800.0,
        viewport_h=600.0,
        zoom=1.0,
        coordinate_space="screen",
        draw_texture=recorder,
        get_texture=lambda path: textures.get(path),
    )

    by_name = {name: (cx, cy) for cx, cy, name in recorded}
    assert by_name["far"] == (400.0 - 100.0 * 0.5, 300.0)
    assert by_name["near"] == (400.0 - 100.0 * 1.0, 300.0)


def test_draw_background_layers_repeat_x_tiles_across_viewport() -> None:
    layers = [BackgroundLayer(id="tiled", path="t.png", z=0, parallax=1.0, repeat_x=True)]
    textures = {"t.png": _FakeTexture("t", 100, 100)}
    count = 0

    def recorder(cx: float, cy: float, w: float, h: float, tex) -> None:  # type: ignore[no-untyped-def]
        nonlocal count
        count += 1

    draw_background_layers(
        layers,
        camera_x=0.0,
        camera_y=0.0,
        viewport_w=800.0,
        viewport_h=600.0,
        zoom=1.0,
        coordinate_space="projected",
        draw_texture=recorder,
        get_texture=lambda path: textures.get(path),
    )

    assert count > 1


def test_draw_background_layers_projected_parallax_zero_stays_screen_center() -> None:
    layers = [BackgroundLayer(id="sky", path="sky.png", z=0, parallax=0.0)]
    textures = {"sky.png": _FakeTexture("sky", 64, 64)}
    recorded: list[tuple[float, float]] = []

    def recorder(cx: float, cy: float, w: float, h: float, tex) -> None:  # type: ignore[no-untyped-def]
        recorded.append((cx, cy))

    draw_background_layers(
        layers,
        camera_x=500.0,
        camera_y=300.0,
        viewport_w=640.0,
        viewport_h=480.0,
        coordinate_space="projected",
        draw_texture=recorder,
        get_texture=lambda path: textures.get(path),
    )

    assert recorded == [(320.0, 240.0)]


def test_draw_background_layers_skips_missing_textures() -> None:
    layers = [BackgroundLayer(id="missing", path="nope.png", z=0)]
    recorded: list[tuple] = []

    draw_background_layers(
        layers,
        camera_x=0.0,
        camera_y=0.0,
        viewport_w=800.0,
        viewport_h=600.0,
        draw_texture=lambda *a: recorded.append(a),
        get_texture=lambda path: None,
    )
    assert recorded == []


# ---------------------------------------------------------------------------
# 2. Compat shim: prefer Arcade-3 draw_texture_rect, fall back to legacy.
# ---------------------------------------------------------------------------
class _FakeArcade3:
    """Mimics the real Arcade-3 surface (draw_texture_rect + XYWH, NO legacy)."""

    def __init__(self) -> None:
        self.rect_calls: list[tuple] = []

    def XYWH(self, x, y, w, h, anchor=None):  # type: ignore[no-untyped-def]
        return ("XYWH", float(x), float(y), float(w), float(h))

    def draw_texture_rect(self, texture, rect, *, angle=0.0, alpha=255, **kw):  # type: ignore[no-untyped-def]
        self.rect_calls.append((texture, rect, angle, alpha))


class _FakeArcade2:
    """Mimics the headless stub / old Arcade (only the legacy function)."""

    def __init__(self) -> None:
        self.legacy_calls: list[tuple] = []

    def draw_texture_rectangle(self, cx, cy, w, h, texture, **kw):  # type: ignore[no-untyped-def]
        self.legacy_calls.append((cx, cy, w, h, texture, kw))


def test_compat_prefers_arcade3_draw_texture_rect(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeArcade3()
    monkeypatch.setattr(optional_arcade, "arcade", fake)
    tex = _FakeTexture("t", 64, 48)

    optional_arcade.draw_texture_rect_compat(400, 300, 64, 48, tex, alpha=200)

    assert fake.rect_calls == [(tex, ("XYWH", 400.0, 300.0, 64.0, 48.0), 0.0, 200)]


def test_compat_falls_back_to_legacy_when_new_api_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeArcade2()
    monkeypatch.setattr(optional_arcade, "arcade", fake)
    tex = _FakeTexture("t", 10, 10)

    optional_arcade.draw_texture_rect_compat(1, 2, 3, 4, tex, angle=90.0, alpha=128)

    assert len(fake.legacy_calls) == 1
    cx, cy, w, h, texture, kw = fake.legacy_calls[0]
    assert (cx, cy, w, h, texture) == (1.0, 2.0, 3.0, 4.0, tex)
    assert kw.get("angle") == 90.0
    assert kw.get("alpha") == 128


def test_compat_noop_when_arcade_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(optional_arcade, "arcade", None)
    # Must not raise.
    optional_arcade.draw_texture_rect_compat(0, 0, 1, 1, _FakeTexture("t", 1, 1))


# ---------------------------------------------------------------------------
# 3. Anti-regression ratchet: no bare draw_texture_rectangle calls in engine.
# ---------------------------------------------------------------------------
_BARE_CALL = re.compile(r"\.draw_texture_rectangle\s*\(")


def test_no_engine_source_calls_removed_draw_texture_rectangle() -> None:
    root = Path(os.getcwd())
    engine_dir = root / "engine"
    violations: list[str] = []

    for path in sorted(engine_dir.rglob("*.py")):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            code = line.split("#", 1)[0]
            if _BARE_CALL.search(code):
                rel = path.relative_to(root).as_posix()
                violations.append(f"{rel}:{lineno}: {line.strip()}")

    assert not violations, (
        "Arcade 3 removed arcade.draw_texture_rectangle. Use "
        "optional_arcade.draw_texture_rect_compat (getattr-guarded) instead:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# 4. Optional real-arcade offscreen smoke (GL-gated; skipped by default).
# ---------------------------------------------------------------------------
def _write_solid_png(path: Path, width: int, height: int, rgba=(255, 0, 0, 255)) -> None:
    def _chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 8-bit RGBA
    row = bytes(rgba) * width
    raw = b"".join(b"\x00" + row for _ in range(height))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )
    path.write_bytes(png)


@pytest.mark.skipif(
    os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
    reason="real-arcade GL smoke is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)",
)
def test_real_arcade_background_layer_renders_non_clear_pixels(tmp_path: Path) -> None:
    from engine.camera_controller import CameraController

    arcade = optional_arcade.arcade
    png = tmp_path / "bg.png"
    _write_solid_png(png, 64, 64, (255, 0, 0, 255))

    window = arcade.Window(128, 128, "bg-smoke", visible=False)
    try:
        cc = CameraController(window)
        cc.resize(128, 128)
        cc.camera.position = (200.0, 200.0)
        window.clear()
        cc.camera.use()
        layers = [BackgroundLayer(id="bg", path=str(png), z=0, parallax=0.0)]
        cache = background_layers.BackgroundTextureCache()
        cc.gui_camera.use()
        draw_background_layers(
            layers,
            camera_x=200.0,
            camera_y=200.0,
            viewport_w=128.0,
            viewport_h=128.0,
            texture_cache=cache,
            coordinate_space="projected",
        )
        cc.camera.use()
        image = arcade.get_image(0, 0, 128, 128)
        center = image.convert("RGB").getpixel((64, 64))
        clearish = image.convert("RGB").getpixel((0, 0))
        assert center[0] > clearish[0] + 40
    finally:
        window.close()


@pytest.mark.skipif(
    os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
    reason="real-arcade GL smoke is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)",
)
def test_scene_controller_draw_composites_background_layer(tmp_path: Path) -> None:
    """Full draw-path smoke: bg layer must survive LightLayer compositing."""
    from types import SimpleNamespace

    from arcade.future.light import LightLayer

    from engine.camera_controller import CameraController
    from engine.scene_controller import SceneController

    arcade = optional_arcade.arcade
    fixture_png = Path("tests/fixtures/background_layer_red.png")
    _write_solid_png(fixture_png, 64, 64, (255, 0, 0, 255))

    window = arcade.Window(128, 128, "bg-full-path", visible=False)
    try:
        cc = CameraController(window)
        cc.resize(128, 128)
        cc.camera.position = (400.0, 300.0)

        controller = object.__new__(SceneController)
        controller._background_layers = [
            BackgroundLayer(id="sky", path=str(fixture_png.resolve()), z=-100, parallax=0.0),
        ]
        controller._background_planes = []
        controller._background_plane_texture_cache = {}
        controller._render_culled_count = 0
        controller._render_sort_mode = "y_sort"
        controller._shadows_enabled = False
        controller._shadows_contact_enabled = False
        controller._shadows_ao_enabled = False
        controller._depth_tint_settings = object()
        controller._outline_settings = object()
        controller._tilemap_background_layers = []
        controller._tilemap_foreground_layers = []
        controller._tilemap_draw_layers = []
        controller._tilemap_batcher = None
        controller.tilemap_instance = None
        controller.layers = {
            "background": [],
            "entities": [],
            "foreground": [],
        }
        controller.window = SimpleNamespace(
            width=128,
            height=128,
            render_queue=None,
            render_batching_enabled=False,
            render_culling_enabled=False,
            tilemap_batching_enabled=False,
            get_camera_center=lambda: (400.0, 300.0),
            camera=cc.camera,
            camera_controller=cc,
            perf_stats=SimpleNamespace(set_counter=lambda *_a, **_k: None),
            assets=None,
        )

        light_layer = LightLayer(128, 128)
        window.clear()
        cc.camera.use()
        with light_layer:
            controller.draw()
        light_layer.draw(ambient_color=(64, 64, 64))

        center = arcade.get_image(64, 64, 1, 1).convert("RGB").getpixel((0, 0))
        assert center[0] > 40, f"expected red background at screen center, got {center}"
    finally:
        window.close()
