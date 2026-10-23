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


def test_the_solids_are_found_where_the_game_keeps_them_on_the_scene_controller() -> None:
    """The real window has no solid_sprites; the scene controller does. Looking on the window did nothing, so a
    gate hidden by a flag stayed in the way, invisible (found playing a game built in Mesh Studio)."""

    class _Controller:
        def __init__(self) -> None:
            self.solid_sprites = optional_arcade.arcade.SpriteList()

    class _RealishWindow:
        def __init__(self) -> None:
            self.flags: dict[str, bool] = {"gate_open": True}
            self.scene_controller = _Controller()

        def get_flag(self, name: str) -> bool:
            return self.flags.get(name, False)

    window = _RealishWindow()
    gate = optional_arcade.arcade.Sprite()
    gate.mesh_entity_data = {"solid": True}
    activator = ConditionalActivator(gate, window, forbid_flags=["gate_open"])
    window.scene_controller.solid_sprites.append(gate)
    activator.update(0.016)
    assert gate.visible is False and gate not in window.scene_controller.solid_sprites


def test_building_it_leaves_the_solid_list_to_the_loader() -> None:
    """The loader adds solid sprites after building their behaviours; adding them here too broke scene loading."""
    window = _Window()
    window.scene_controller = type("C", (), {"solid_sprites": window.solid_sprites})()
    gate = optional_arcade.arcade.Sprite()
    gate.mesh_entity_data = {"solid": True}
    ConditionalActivator(gate, window, forbid_flags=["open"])  # shown: it should block once the loader adds it
    window.solid_sprites.append(gate)  # the loader; raised "Sprite already in SpriteList" before
    assert gate in window.solid_sprites
