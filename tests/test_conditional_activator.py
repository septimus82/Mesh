"""ConditionalActivator ("Show when"): hidden objects stop blocking, shown ones block again."""

import pytest

import engine.optional_arcade as optional_arcade
from engine.behaviours.conditional_activator import ConditionalActivator

pytestmark = pytest.mark.fast


class _Window:
    def __init__(self) -> None:
        self.flags: dict[str, bool] = {}
        self.solid_sprites = optional_arcade.arcade.SpriteList()

    def get_flag(self, name: str) -> bool:
        return self.flags.get(name, False)


def test_a_hidden_solid_object_stops_blocking_even_though_it_joins_the_solids_after_spawning() -> None:
    window = _Window()
    grave = optional_arcade.arcade.Sprite()
    grave.mesh_entity_data = {"solid": True}
    activator = ConditionalActivator(grave, window, require_flags=["dug"])
    window.solid_sprites.append(grave)  # what the loader does after building behaviours

    activator.update(0.016)
    assert grave.visible is False and grave not in window.solid_sprites

    window.flags["dug"] = True
    activator.update(0.016)
    assert grave.visible is True and grave in window.solid_sprites
