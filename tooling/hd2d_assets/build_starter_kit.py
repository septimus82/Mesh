"""Mesh's HD-2D starter kit: every model built and exported by Blender in one headless run (original; textures from
pixel_textures.py, all sampled "Closest").

    blender --factory-startup -noaudio --background --python tooling/hd2d_assets/build_starter_kit.py -- OUT_DIR

Writes OUT_DIR/<name>.glb for each model below. Blender: X east, Y north, Z up, metres; each model's origin is where
it stands on the ground. Collision objects carry ``mesh_collision`` (solid: walk on top, solid below; floor: walk on
top, open below; wall: blocks). ``tooling/hd2d_assets/make_starter_kit.py`` runs this and makes the kit's previews
and catalogue.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_cottage  # noqa: E402
import build_stairs  # noqa: E402
from blender_kit import box, export, gable_roof, material, prism, reset  # noqa: E402


def m(name: str):
    return material(name)


def shop() -> None:
    """A market stall-shop: back and side walls, a counter across most of the open front, a striped awning and a
    roof. Walk in through the gap at the counter's east end."""
    timber, plaster, shingles, floor, awning = m("timber"), m("plaster"), m("shingles"), m("floorboards"), m("awning")
    box("floor", -2.0, -1.5, 0.0, 2.0, 1.5, 0.1, (floor, timber))
    box("col_floor", -2.0, -1.5, 0.0, 2.0, 1.5, 0.1, collision="solid")
    for name, (x0, y0, x1, y1) in {"north": (-2.0, 1.3, 2.0, 1.5), "west": (-2.0, -1.5, -1.8, 1.5),
                                   "east": (1.8, -1.5, 2.0, 1.5)}.items():
        box(f"wall_{name}_low", x0, y0, 0.1, x1, y1, 1.2, timber)
        box(f"wall_{name}_high", x0, y0, 1.2, x1, y1, 2.4, plaster)
        box(f"col_wall_{name}", x0, y0, 0.0, x1, y1, 2.4, collision="wall")
    box("counter", -1.8, -1.5, 0.1, 0.8, -1.1, 1.0, (floor, timber))
    box("col_counter", -1.8, -1.5, 0.0, 0.8, -1.1, 1.0, collision="wall")
    box("awning", -2.2, -2.6, 2.1, 2.2, -1.5, 2.2, (awning, awning))
    for x in (-2.1, 2.0):
        box(f"awning_post_{x:+.0f}", x, -2.6, 0.0, x + 0.1, -2.5, 2.1, timber)
        box(f"col_awning_post_{x:+.0f}", x, -2.6, 0.0, x + 0.1, -2.5, 2.1, collision="wall")
    gable_roof("roof", -2.2, -1.7, 2.2, 1.7, 2.4, 3.3, shingles, plaster)


def wall_2m() -> None:
    """A 2 m wall module (timber below, plaster above), 2.5 m high: line several up to build your own house."""
    timber, plaster = m("timber"), m("plaster")
    box("wall_low", -1.0, -0.1, 0.0, 1.0, 0.1, 1.3, timber)
    box("wall_high", -1.0, -0.1, 1.3, 1.0, 0.1, 2.5, plaster)
    box("col_wall", -1.0, -0.1, 0.0, 1.0, 0.1, 2.5, collision="wall")


def roof_4m() -> None:
    """A 4 x 4 m gable roof module: place it 2.5 m up (Height in the inspector) on four wall modules."""
    gable_roof("roof", -2.2, -2.2, 2.2, 2.2, 0.0, 1.4, m("shingles"), m("plaster"))


def platform(width: float) -> None:
    """A raised platform (a cliff section) 2 m high and 4 m deep: grass on top, rock sides; walk on it, not
    through it. Join several to make a plateau; a staircase reaches it."""
    grass, rock = m("grass"), m("rock")
    box("platform", -width / 2, -2.0, 0.0, width / 2, 2.0, 2.0, (grass, rock))
    box("col_platform", -width / 2, -2.0, 0.0, width / 2, 2.0, 2.0, collision="solid")


def bridge_6m() -> None:
    """A 6 m wooden bridge whose deck is 2 m up (the height of a platform): walk across it, or under it."""
    floor, timber = m("floorboards"), m("timber")
    box("deck", -3.0, -1.0, 1.85, 3.0, 1.0, 2.0, (floor, timber))
    box("col_deck", -3.0, -1.0, 1.85, 3.0, 1.0, 2.0, collision="floor")
    for side, (y0, y1) in (("south", (-1.0, -0.88)), ("north", (0.88, 1.0))):
        box(f"rail_{side}", -3.0, y0, 2.55, 3.0, y1, 2.65, timber)
        for x in (-3.0, -1.0, 1.0, 2.88):
            box(f"post_{side}_{x:+.0f}", x, y0, 2.0, x + 0.12, y1, 2.65, timber)
        box(f"col_rail_{side}", -3.0, y0, 2.0, 3.0, y1, 2.65, collision="wall")


def fence_2m() -> None:
    """A 2 m fence section, 1 m high."""
    timber = m("timber")
    for x in (-1.0, 0.92):
        box(f"post_{x:+.0f}", x, -0.06, 0.0, x + 0.08, 0.06, 1.0, timber)
    for z in (0.35, 0.75):
        box(f"rail_{z}", -1.0, -0.04, z, 1.0, 0.04, z + 0.1, timber)
    box("col_fence", -1.0, -0.06, 0.0, 1.0, 0.06, 1.0, collision="wall")


def crate() -> None:
    """A 1 m wooden crate."""
    face = m("crate")
    box("crate", -0.5, -0.5, 0.0, 0.5, 0.5, 1.0, (face, face))
    box("col_crate", -0.5, -0.5, 0.0, 0.5, 0.5, 1.0, collision="solid")


def barrel() -> None:
    """A barrel, 1 m high."""
    staves, top = m("barrel"), m("floorboards")
    prism("barrel", 0.0, 0.0, 0.4, 0.0, 1.0, 10, (top, staves))
    prism("col_barrel", 0.0, 0.0, 0.4, 0.0, 1.0, 10, collision="solid")


def lamp_post() -> None:
    """An iron lamp post with a lantern 2.5 m up. Mesh lights the room: add a lamp light at the lantern (Lighting)."""
    iron, lantern = m("iron"), m("lantern")
    box("post", -0.08, -0.08, 0.0, 0.08, 0.08, 2.3, iron)
    box("lantern", -0.2, -0.2, 2.3, 0.2, 0.2, 2.75, (iron, lantern))
    box("cap", -0.26, -0.26, 2.75, 0.26, 0.26, 2.85, iron)
    box("col_post", -0.12, -0.12, 0.0, 0.12, 0.12, 2.85, collision="wall")


def path_2m() -> None:
    """A 2 x 2 m earth path tile, a hair above the grass (nothing to collide with): lay a path through the village."""
    dirt = m("dirt")
    box("path", -1.0, -1.0, 0.0, 1.0, 1.0, 0.02, (dirt, dirt))


def interior() -> None:
    """A cottage's inside, open above so the camera sees in: a 6 x 5 m wooden floor, walls with a doorway south,
    a table and a bed."""
    timber, plaster, floor = m("timber"), m("plaster"), m("floorboards")
    box("floor", -3.0, -2.5, 0.0, 3.0, 2.5, 0.1, (floor, timber))
    box("col_floor", -3.0, -2.5, 0.0, 3.0, 2.5, 0.1, collision="solid")
    for name, (x0, y0, x1, y1) in {"north": (-3.0, 2.3, 3.0, 2.5), "west": (-3.0, -2.5, -2.8, 2.5),
                                   "east": (2.8, -2.5, 3.0, 2.5), "south_w": (-3.0, -2.5, -0.6, -2.3),
                                   "south_e": (0.6, -2.5, 3.0, -2.3)}.items():
        box(f"wall_{name}_low", x0, y0, 0.1, x1, y1, 1.2, timber)
        box(f"wall_{name}_high", x0, y0, 1.2, x1, y1, 2.2, plaster)
        box(f"col_wall_{name}", x0, y0, 0.0, x1, y1, 2.2, collision="wall")
    box("table", -0.6, 0.6, 0.1, 0.6, 1.4, 0.85, (floor, timber))
    box("col_table", -0.6, 0.6, 0.0, 0.6, 1.4, 0.85, collision="wall")
    box("bed", 1.6, 0.6, 0.1, 2.7, 2.2, 0.6, (m("awning"), timber))
    box("col_bed", 1.6, 0.6, 0.0, 2.7, 2.2, 0.6, collision="wall")


KIT = {
    "cottage": build_cottage.build,
    "shop": shop,
    "wall_2m": wall_2m,
    "roof_4m": roof_4m,
    "stairs": lambda: build_stairs.build("Closest"),
    "platform_4m": lambda: platform(4.0),
    "platform_2m": lambda: platform(2.0),
    "bridge_6m": bridge_6m,
    "fence_2m": fence_2m,
    "crate": crate,
    "barrel": barrel,
    "lamp_post": lamp_post,
    "path_2m": path_2m,
    "interior": interior,
}

if __name__ == "__main__":
    out = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
    for name, make in KIT.items():
        reset()
        make()
        export(out / f"{name}.glb")
