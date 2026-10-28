"""Milestone 23B: a campfire's settings, its light (deterministic flicker), its checked operation, and its sprites
kept out of the scatter brushes."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from engine import fire
from engine import project_ops as ops

pytestmark = pytest.mark.fast


def _scene() -> dict:
    return {"entities": [{"id": "f1", "name": "Campfire", "x": 320, "y": 96}]}


def test_settings_default_and_refuse_what_the_game_cannot_use() -> None:
    assert fire.parse_fire({}) == fire.Fire()
    assert fire.parse_fire({"size": 1.5, "light": 0, "smoke": False}).size == 1.5
    for bad in ({"size": 2.0}, {"light": -1}, {"light_radius": 4}, {"enabled": "yes"}, {"heat": 3}, []):
        with pytest.raises(fire.FireError):
            fire.parse_fire(bad)


def test_flicker_is_the_same_at_the_same_time_and_stays_subtle() -> None:
    values = [fire.flicker(t / 10, 320, 96) for t in range(600)]
    assert values == [fire.flicker(t / 10, 320, 96) for t in range(600)]
    assert 0.84 <= min(values) and max(values) <= 1.06 and max(values) - min(values) > 0.1
    assert fire.flicker(3.0, 320, 96) != fire.flicker(3.0, 900, 96)  # (fires out of step)


def test_only_burning_fires_light_and_none_casts_a_shadow_map() -> None:
    def hearth(**settings: object) -> fire.Hearth:
        entity = SimpleNamespace(center_x=320.0, center_y=96.0, mesh_entity_data={})
        return fire.Hearth(entity, fire.parse_fire(settings))

    lamps = fire.lamps([hearth(), hearth(enabled=False), hearth(light=0.0)], 2.0)
    assert len(lamps) == 1 and not lamps[0].shadows
    assert lamps[0].radius == pytest.approx(192.0, rel=0.04) and lamps[0].elevation == pytest.approx(19.2)
    assert fire.lamps([hearth()], 2.0, ground=lambda x, y: 64.0)[0].elevation == pytest.approx(83.2)


def test_registration_replaces_an_objects_old_fire() -> None:
    window = SimpleNamespace()
    entity = SimpleNamespace(center_x=0.0, center_y=0.0)
    fire.reset(window)
    fire.register(window, entity, fire.Fire())
    fire.register(window, entity, fire.Fire(size=1.2))
    assert [h.fire.size for h in window.campfires] == [1.2]
    assert len(fire.fires_of(window)) == 1


def test_set_campfire_is_one_checked_edit_and_its_crackle_follows_the_fire() -> None:
    scene = ops.set_campfire(_scene(), "f1")
    entity = scene["entities"][0]
    assert ops.entity_behaviours(entity) == ["Campfire"] and ops.campfire_of(entity)["sound"] == ""
    scene = ops.set_campfire(scene, "f1", sound="assets/ambience/fire.wav", size=1.25)
    scene = ops.set_campfire(scene, "f1", enabled=False)
    entity = scene["entities"][0]
    assert entity["behaviour_config"]["SoundEmitter"]["enabled"] is False  # (put out: silent)
    assert ops.campfire_of(entity) == {"enabled": False, "size": 1.25, "smoke": True, "light": 1.0,
                                       "light_radius": 192.0, "sound": "assets/ambience/fire.wav"}
    assert ops.entity_behaviours(ops.set_campfire(scene, "f1", sound="")["entities"][0]) == ["Campfire"]
    with pytest.raises(ops.OpError):
        ops.set_campfire(scene, "f1", size=3)
    assert ops.campfire_of(_scene()["entities"][0]) is None


def test_the_campfire_sprites_are_not_a_brushes() -> None:
    from engine.hd2d.scatter import ASSETS, COLLECTIONS

    hidden = {a.name for a in ASSETS.values() if a.hidden}
    assert hidden == {"Campfire", "Campfire flames"}
    assert not hidden & set(COLLECTIONS)
    assert not any({"campfire", "campfire_flame"} & set(weights) for weights in COLLECTIONS.values())


def test_an_older_copy_of_the_animated_sheet_is_updated_and_a_changed_one_kept(tmp_path: Path) -> None:
    from PIL import Image

    from engine.hd2d.scatter import MOTION_SHEET
    from engine.repo_root import bundled_file
    from engine.studio_project import _older_sheet

    source = bundled_file(MOTION_SHEET)
    assert source is not None
    with Image.open(source) as new:
        old = new.crop((0, 0, new.width - 480, new.height))
    old.save(tmp_path / "old.png")
    assert _older_sheet(tmp_path / "old.png", Path(source))
    old.putpixel((5, 40), (1, 2, 3, 255))  # (a creator's own change)
    old.save(tmp_path / "changed.png")
    assert not _older_sheet(tmp_path / "changed.png", Path(source))
    assert not _older_sheet(Path(source), Path(source))
