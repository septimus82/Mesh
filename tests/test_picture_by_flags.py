"""PictureByFlags: an object's picture follows game flags (a grave that's been dug)."""

from types import SimpleNamespace

import pytest

from engine.behaviours.picture_by_flags import PictureByFlags

pytestmark = pytest.mark.fast


def test_the_first_matching_rule_picks_the_picture_and_it_reverts_when_none_match() -> None:
    flags: dict[str, bool] = {}
    window = SimpleNamespace(get_flag=lambda name: flags.get(name, False),
                             assets=SimpleNamespace(get_texture=lambda path: f"tex:{path}"))
    grave = SimpleNamespace(texture="tex:closed.png", mesh_entity_data={})
    rules = [{"sprite": "open.png", "require_flags": ["dug"]}, {"sprite": "marked.png", "require_flags": "seen, marked"}]
    behaviour = PictureByFlags(grave, window, pictures=rules)
    assert grave.texture == "tex:closed.png"

    flags.update(seen=True, marked=True)
    behaviour.update(0.016)
    assert grave.texture == "tex:marked.png"
    flags["dug"] = True
    behaviour.update(0.016)
    assert grave.texture == "tex:open.png"
    flags.clear()
    behaviour.update(0.016)
    assert grave.texture == "tex:closed.png"
