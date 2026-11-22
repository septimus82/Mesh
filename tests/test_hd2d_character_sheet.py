"""M2-2: the committed eight-direction character sheet (tooling/hd2d_assets/character_8dir.png, rendered by Blender
through character_sheet.py; CI has no Blender) matches its JSON sidecar, and today's four-direction setup still
reads it unchanged (M2-3 adds opt-in 8-way facing)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from engine import project_ops as ops
from engine.behaviours.animator import SpriteAnimatorBehaviour

pytestmark = pytest.mark.fast

ASSETS = Path(__file__).resolve().parents[1] / "tooling" / "hd2d_assets"
SHEET, SIDECAR = ASSETS / "character_8dir.png", ASSETS / "character_8dir.json"
FACINGS = ["down", "down_left", "left", "up_left", "up", "up_right", "right", "down_right"]
COMPASS = ["S", "SW", "W", "NW", "N", "NE", "E", "SE"]


@pytest.fixture(scope="module")
def meta() -> dict:
    return json.loads(SIDECAR.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sheet() -> Image.Image:
    with Image.open(SHEET) as image:
        return image.convert("RGBA")


def _frame(sheet: Image.Image, meta: dict, facing: str, animation: str, i: int) -> Image.Image:
    w, h = meta["frame_width"], meta["frame_height"]
    x, y = (meta["animations"][animation]["first"] + i) * w, meta["facings"].index(facing) * h
    return sheet.crop((x, y, x + w, y + h))


def test_sidecar_describes_the_sheet(meta: dict, sheet: Image.Image) -> None:
    assert meta["sheet"] == SHEET.name
    assert meta["facings"] == FACINGS and meta["compass"] == COMPASS and meta["rows"] == 8
    spans = sorted((a["first"], a["frames"]) for a in meta["animations"].values())
    assert spans[0][0] == 0 and all(f0 + n0 == f1 for (f0, n0), (f1, _) in zip(spans, spans[1:]))  # contiguous
    assert sum(n for _, n in spans) == meta["columns"]
    assert {"idle", "walk"} <= set(meta["animations"]) and meta["animations"]["walk"]["frames"] >= 4
    assert all(a["fps"] > 0 for a in meta["animations"].values())
    assert sheet.size == (meta["columns"] * meta["frame_width"], meta["rows"] * meta["frame_height"])
    assert set(sheet.getchannel("A").getdata()) <= {0, 255}  # rendered without anti-aliasing
    assert meta["camera"]["pitch_deg"] == 32 and meta["camera"]["projection"] == "orthographic"
    px, py = meta["pivot"]
    assert 0 <= px < meta["frame_width"] and 0 <= py < meta["frame_height"]


def test_every_frame_is_drawn_whole_and_stands_on_the_pivot(meta: dict, sheet: Image.Image) -> None:
    w, h = meta["frame_width"], meta["frame_height"]
    px, py = meta["pivot"]
    frames = {}
    for facing in FACINGS:
        for name, anim in meta["animations"].items():
            for i in range(anim["frames"]):
                frame = _frame(sheet, meta, facing, name, i)
                box = frame.getbbox()
                assert box is not None, f"{facing} {name} {i} is empty"
                left, top, right, bottom = box
                assert left > 0 and top > 0 and right < w and bottom < h, f"{facing} {name} {i} touches its edge"
                assert left <= px < right and py <= bottom <= py + 6, f"{facing} {name} {i}: feet off the pivot"
                frames[(facing, name, i)] = frame.tobytes()
    idles = [frames[(f, "idle", 0)] for f in FACINGS]
    assert len(set(idles)) == 8  # eight different facings
    for facing in FACINGS:  # the walk moves
        assert len({frames[(facing, "walk", i)] for i in range(meta["animations"]["walk"]["frames"])}) > 2


def _face_x(frame: Image.Image) -> tuple[int, float]:
    """How many skin pixels the head shows, and their mean x."""
    _, top, _, _ = frame.getbbox()
    xs = [x for y in range(top, top + 14) for x in range(frame.width)
          if (p := frame.getpixel((x, y)))[3] and p[0] > 180 and p[1] > 130]
    return len(xs), sum(xs) / len(xs) if xs else -1.0


def test_rows_follow_the_facing_order(meta: dict, sheet: Image.Image) -> None:
    face = {f: _face_x(_frame(sheet, meta, f, "idle", 0)) for f in FACINGS}
    assert face["down"][0] > 10 and face["up"][0] == 0  # the face toward the camera; the back of the head away
    for side in ("", "up_", "down_"):  # a left facing shows its face left of the matching right facing
        assert face[f"{side}left"][1] < face[f"{side}right"][1], side


class _Assets:
    """Slices the sheet the way engine/assets.py does: columns = width // frame width."""

    def __init__(self, sheet: Image.Image) -> None:
        self.sheet = sheet

    def load_sprite_sheet(self, path, fw, fh, count, start):
        columns = self.sheet.width // fw
        return [("frame", *divmod(start + i, columns)) for i in range(count)]  # (row, column)


class _Entity:
    def __init__(self) -> None:
        self.mesh_entity_data, self.mesh_behaviours_runtime = {}, []
        self.change_x = self.change_y = 0.0
        self.texture = None


def test_four_direction_setup_reads_the_sheet_unchanged(meta: dict, sheet: Image.Image) -> None:
    assert ops.DIRECTIONS == ("down", "left", "right", "up")  # 8-way is M2-3's opt-in; 4-way stays the default
    idle, walk = meta["animations"]["idle"], meta["animations"]["walk"]
    rows = {d: FACINGS.index(d) for d in ops.DIRECTIONS}
    clips = ops.character_clips(SHEET.name, meta["frame_width"], meta["frame_height"], meta["columns"], rows,
                                walk_first=walk["first"], walk_count=walk["frames"], idle_first=idle["first"],
                                idle_count=idle["frames"], walk_fps=walk["fps"], idle_fps=idle["fps"],
                                sheet_rows=meta["rows"])
    assert sorted(clips) == sorted(f"{k}_{d}" for k in ("idle", "walk") for d in ops.DIRECTIONS)
    assert not any(c.get("flip_x") for c in clips.values())  # the sheet draws left; nothing is mirrored
    scene = {"name": "S", "schema_version": 1, "version": 1, "entities": [{"id": "hero", "name": "Hero", "x": 0.0,
                                                                            "y": 0.0, "sprite": SHEET.name}]}
    config = ops.find_entity(ops.set_animation(scene, "hero", clips), "hero")["behaviour_config"]["Animator"]
    assert config["directional_mode"] == "4-way" and config["animation_state"] == "idle_down"

    window = type("W", (), {"assets": _Assets(sheet)})()
    entity = _Entity()
    params = {k: v for k, v in config.items() if k != "animations"}
    animator = SpriteAnimatorBehaviour(entity, window, animations=config["animations"], **params)
    for vx, vy, facing in ((-100, 0, "left"), (100, 0, "right"), (0, 100, "up"), (0, -100, "down")):
        entity.change_x, entity.change_y = vx, vy
        animator.update(0.01)
        animator.late_update(0.01)
        row = FACINGS.index(facing)
        assert animator.current_state == f"walk_{facing}"
        assert animator.animations[animator.current_state] == [("frame", row, walk["first"] + i)
                                                               for i in range(walk["frames"])]
