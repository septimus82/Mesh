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
from engine.background_layers import BackgroundLayer, draw_background_layers

pytestmark = [pytest.mark.fast]


class _FakeTexture:
    def __init__(self, name: str, width: int, height: int) -> None:
        self.name = name
        self.width = width
        self.height = height


# ---------------------------------------------------------------------------
# 1. Draw-capture: draw_background_layers emits the expected centred draws.
# ---------------------------------------------------------------------------
def test_draw_background_layers_emits_centered_draws() -> None:
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
        draw_texture=recorder,
        get_texture=lambda path: textures.get(path),
    )

    # Camera at origin -> every layer centres on the viewport centre (400, 300).
    assert recorded == [
        (400.0, 300.0, 128.0, 64.0, "far"),
        (400.0, 300.0, 64.0, 32.0, "near"),
    ]


def test_draw_background_layers_parallax_offsets_each_layer() -> None:
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
        draw_texture=recorder,
        get_texture=lambda path: textures.get(path),
    )

    # base_x = center_x + (-camera_x * parallax * zoom)
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
        draw_texture=recorder,
        get_texture=lambda path: textures.get(path),
    )

    # An 800px-wide viewport tiled with a 100px texture needs many draws (>1).
    assert count > 1


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
    arcade = optional_arcade.arcade
    png = tmp_path / "bg.png"
    _write_solid_png(png, 8, 8, (255, 0, 0, 255))

    window = arcade.Window(64, 64, "bg-smoke", visible=False)
    try:
        window.clear()
        layers = [BackgroundLayer(id="bg", path=str(png), z=0, parallax=0.0)]
        cache = background_layers.BackgroundTextureCache()
        draw_background_layers(
            layers,
            camera_x=0.0,
            camera_y=0.0,
            viewport_w=64.0,
            viewport_h=64.0,
            texture_cache=cache,
        )
        image = arcade.get_image(0, 0, 64, 64)
        pixels = list(image.convert("RGB").getdata())
        assert any(px != pixels[0] for px in pixels) or pixels[0] == (255, 0, 0)
    finally:
        window.close()
