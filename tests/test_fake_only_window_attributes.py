"""S1 5.6 (b) and (c): no production feature may hang on a window attribute that only test fakes have.

The pattern behind #622 B, #636, #641 and #643: production reads ``getattr(window, "x", None)`` (or ``hasattr``) for
an ``x`` the real GameWindow never has and production never creates, while test fakes supply it. The feature works in
every test and is silently off in the game. Here a real hidden GameWindow (with a room and a player, a few frames in)
is checked against every such read (tests/_window_scan.py, from docs/s1/evidence/contract_gaps_real_window.py):

- a name that is read, missing on the real window, never created by production and given by a test fake fails,
  unless ``ALLOWED`` lists it with the open issue that tracks it;
- an ``ALLOWED`` entry that no longer matches (the read was fixed or removed) fails too, so the list only shrinks.

The same real window regenerates ``tests/fixtures/game_window_attributes.txt``, the manifest ``fake_window()``
(tests/_fake_window.py) is spec'd on; a drift fails with the command that rewrites it.
"""
from __future__ import annotations

import os
import re
from collections.abc import Iterator
from typing import Any

import pytest

import engine.optional_arcade as optional_arcade
from tests import _window_scan as scan
from tests._fake_window import MANIFEST, fake_window, window_attributes

pytestmark = [pytest.mark.integration,  # (an AST scan of the checkout and one hidden game window)
              pytest.mark.skipif(not optional_arcade.has_arcade(), reason="needs real arcade (a hidden window)")]

# name -> the open issue that tracks it (and why it is allowed until then).
ALLOWED: dict[str, str] = {
    # Lazily created or legitimately optional: each read is the fallback after the real lookup.
    "particle_system": "#705: second link after particle_manager.system",
    "particle_seed": "#705: second link after engine_config.particle_seed",
    "dialogue_box": "#705: second link after ui_controller.dialogue_box",
    "ui": "#705: second link after ui_controller",
    "solid_sprites": "#705: second link after scene_controller.solid_sprites",
    "player": "#705: last-resort fallback after scene_controller._find_player_sprite()",
    # Dead branches, to be removed.
    "dialogue_controller": "#706: dead check (the live block is ui_controller.input_blocked)",
    "editor": "#706: dead editor.workspace branch (the real window has editor_controller)",
    # The fake-only P3 bundle.
    "asset_manager": "#646: plugin ctx.asset_manager (real: window.assets)",
    "console": "#646: plugin ctx.console (real: window.console_controller)",
    "current_scene_key": "#646: legacy workspace snapshot scene id",
    "cutscene_runner": "#646: debug panels' cutscene inspector (real: cutscene_controller)",
    "digest_tracker": "#646: debug bundle digests",
    "quest_runner": "#646: debug panels' quest diagnostics (real: quest_manager)",
}
REGENERATE = "MESH_WRITE_WINDOW_MANIFEST"


@pytest.fixture(scope="module")
def real_window(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Any]:
    """A real hidden GameWindow with a room and a player, a few frames in (as the evidence script checks it)."""
    from tests._b01_arena import Arena, close_window, hero, make_window

    window = make_window()
    try:
        window.audio.set_master_volume(0.0)
        arena = Arena(window, tmp_path_factory.mktemp("window"))
        arena.write_room({**hero(), "behaviours": ["PlayerController"], "behaviour_config": {}})
        arena.enter()
        for _ in range(3):
            window.on_update(1 / 60)
        yield window
    finally:
        close_window(window)


def _fake_only(window: Any) -> dict[str, list[str]]:
    reads = scan.production_fallbacks()
    written = scan.production_window_writes()
    fakes = scan.fake_window_attrs()
    return {name: sites for name, sites in reads.items()
            if not hasattr(window, name) and name not in written and name in fakes}


def test_no_production_read_hangs_on_a_window_attribute_only_fakes_have(real_window: Any) -> None:
    found = _fake_only(real_window)
    new = {name: found[name][:3] for name in sorted(set(found) - set(ALLOWED))}
    assert not new, ("production reads these window attributes, which the real GameWindow doesn't have and nothing "
                     f"creates, while test fakes supply them (read the real attribute instead): {new}")
    stale = sorted(set(ALLOWED) - set(found))
    assert not stale, f"no longer fake-only: remove them from ALLOWED (and close out their issue's item): {stale}"


def test_every_allowed_name_names_its_issue() -> None:
    assert all(re.match(r"#\d+: \S", reason) for reason in ALLOWED.values()), ALLOWED


def _manifest_names(window: Any) -> list[str]:
    """The engine's own window attributes: what the engine's window classes define and every name production creates on
    a window. (arcade's and pyglet's side differs by OS and version, so tests/_fake_window.py takes it from the
    installed arcade.Window instead of from this file.)"""
    names = {name for cls in type(window).__mro__ if cls.__module__.split(".")[0] == "engine" for name in vars(cls)}
    names |= scan.production_window_writes()
    return sorted(name for name in names if not name.startswith("__"))


def test_the_fake_window_manifest_is_the_real_window(real_window: Any) -> None:
    names = _manifest_names(real_window)
    if os.environ.get(REGENERATE) == "1":
        header = ("# The real GameWindow's attribute names (tests/_fake_window.py); regenerated by "
                  "tests/test_fake_only_window_attributes.py")
        MANIFEST.write_text("\n".join([header, *names]) + "\n", encoding="utf-8")
        window_attributes.cache_clear()
    assert list(window_attributes()) == names, (
        f"the real GameWindow's attributes changed: rewrite the manifest with {REGENERATE}=1 "
        "python -m pytest tests/test_fake_only_window_attributes.py")


def test_a_fake_window_has_only_what_the_real_one_has(real_window: Any) -> None:
    fake = fake_window(paused=False)
    assert fake.paused is False and hasattr(fake, "scene_controller") and hasattr(fake, "event_bus")
    for name in ALLOWED:  # (what the bug class reads: absent on the fake as on the real window)
        assert not hasattr(fake, name) and not hasattr(real_window, name)
        with pytest.raises(AttributeError):
            setattr(fake, name, object())
