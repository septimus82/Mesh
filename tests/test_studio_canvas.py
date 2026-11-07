"""Milestone 15 Stage 3: the graphite canvas around the map is drawn only outside the map's bounds, so the map
itself (and editing on it) is untouched; a room without a map gets none."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from engine import optional_arcade
from engine import project_ops as ops

pytestmark = pytest.mark.fast


def _studio(scene: dict, view: tuple[float, float, float, float]):
    from engine.studio import Studio

    left, right, bottom, top = view  # the map view in world units: unproject maps screen corners straight there
    corners = {(230, 26): (left, bottom), (950, 676): (right, top)}
    fake = SimpleNamespace(project=SimpleNamespace(scene=lambda: scene),
                           window=SimpleNamespace(camera=SimpleNamespace(unproject=lambda p: corners[tuple(p)]),
                                                  width=1280, height=720))
    fake._map_rect = lambda: (230, 950, 26, 676)
    return Studio._draw_canvas, fake


def _drawn(monkeypatch, scene: dict, view: tuple[float, float, float, float]) -> list[tuple[float, ...]]:
    rects: list[tuple[float, ...]] = []
    monkeypatch.setattr(optional_arcade.arcade, "draw_lrbt_rectangle_filled",
                        lambda l_, r_, b_, t_, colour: rects.append((l_, r_, b_, t_)))
    draw, fake = _studio(scene, view)
    draw(fake)
    return rects


def test_the_canvas_covers_only_what_lies_outside_the_map(monkeypatch) -> None:
    scene, _ = ops.place_blank({"name": "A", "schema_version": 1, "version": 1, "entities": []}, "a", "x", 0, 0)
    scene, _path, _skeleton = ops.add_map(scene, "a", width=24, height=16, ground=ops.STARTER_GRASS)
    map_w, map_h = 24 * 32, 16 * 32
    rects = _drawn(monkeypatch, scene, (-200.0, 900.0, -100.0, 600.0))
    assert rects, "something to cover around the map"
    for l_, r_, b_, t_ in rects:
        overlaps = l_ < map_w and r_ > 0 and b_ < map_h and t_ > 0
        assert not overlaps, f"{(l_, r_, b_, t_)} reaches into the map"
    covered = sum((r_ - l_) * (t_ - b_) for l_, r_, b_, t_ in rects)
    assert covered == pytest.approx(1100 * 700 - map_w * map_h), "all of the view outside the map, once"
    assert _drawn(monkeypatch, scene, (100.0, 300.0, 100.0, 300.0)) == [], "zoomed in on the map: nothing to cover"


def test_a_room_without_a_map_gets_no_canvas(monkeypatch) -> None:
    room = {"name": "B", "schema_version": 1, "version": 1, "entities": []}
    assert _drawn(monkeypatch, room, (-200.0, 900.0, -100.0, 600.0)) == []
