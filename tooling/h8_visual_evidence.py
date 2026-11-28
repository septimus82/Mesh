"""H8 (#422) visual evidence: real gameplay frames of the 2D (adventure) and HD-2D (hd2d_rpg) starter games, in
hidden windows, at 1280x720, 1920x1080 and a window too narrow for the controls hint on one line.

    python tooling/h8_visual_evidence.py OUT_DIR

It writes one PNG per entry of ``CAPTURES`` (the start rooms with the controls hint as a player first sees them,
small interior rooms, the HD-2D map's corner, a short toast) and ``facts.json``:
measured from the frames themselves, never from layout numbers. A toast is found as the pixels that change when it is
taken away (the same frame drawn again without it); its border as the sky-blue pixels among them. The background is
read in the window's corners.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

GAMES = ("adventure", "hd2d_rpg")
SIZES = ((1280, 720), (1920, 1080), (560, 420))
SKY_BLUE = (135, 206, 235)


def toast_geometry(with_toast: Any, without: Any) -> dict[str, Any]:
    """Where a toast's pixels are, from two frames (with and without it): the bounding box of everything that
    changed, that of its sky-blue border, and how many changed pixels lie outside the border (text that overflows)."""
    import numpy as np

    a, b = (np.asarray(img.convert("RGB")).astype(int) for img in (with_toast, without))
    changed = np.any(np.abs(a - b) > 24, axis=2)
    border = changed & (np.abs(a - np.array(SKY_BLUE)).sum(axis=2) < 60)
    if not border.any():
        return {"toast": False}
    # The outline is the rows and columns where sky-blue makes a line, not the odd text pixel that blends to sky-blue
    # over water.
    rows, cols = border.sum(axis=1), border.sum(axis=0)
    ys, xs = np.nonzero(rows >= rows.max() / 2)[0], np.nonzero(cols >= cols.max() / 2)[0]
    box = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]  # left, top, right, bottom (image rows)
    cys, cxs = np.nonzero(changed)
    outside = changed.copy()
    outside[box[1]:box[3] + 1, box[0]:box[2] + 1] = False
    return {"toast": True, "border": box, "changed": [int(cxs.min()), int(cys.min()), int(cxs.max()), int(cys.max())],
            "changed_outside_border": int(outside.sum()), "window": [a.shape[1], a.shape[0]]}


def corners(img: Any) -> list[list[int]]:
    rgb = img.convert("RGB")
    w, h = rgb.size
    return [list(rgb.getpixel((x, y))) for x, y in ((2, 2), (w - 3, 2), (2, h - 3), (w - 3, h - 3))]


def capture(project: Path, size: tuple[int, int], out: Path, name: str, *, room: str | None = None,
            walk: tuple[str, ...] = (), toast: str | None = None, resize: tuple[int, int] | None = None,
            text_scale: float | None = None) -> dict[str, Any]:
    """One frame of ``project``'s game at ``size``: its start room (or ``room``) a moment after it opens, after the
    player held each key of ``walk`` for 400 frames, with ``toast`` shown instead of what's showing when given; the
    window resized to ``resize`` before the frame, or the player's text scale (Settings) set to ``text_scale``."""
    from hd2d_demo import HiddenGame

    from engine import text_draw

    game = HiddenGame(project, size=size)
    scale = text_draw.get_text_scale()
    try:
        if text_scale is not None:
            text_draw.set_text_scale(text_scale)
        config = json.loads((project / "config.json").read_text(encoding="utf-8"))
        game.load(room or config["start_scene"])
        game.step(40)  # (the controls hint shows in the start room for 4 s)
        for key in walk:
            game.hold(getattr(game.arcade.key, key), 400)
        hud = game.window.player_hud
        if resize:
            game.window.set_size(*resize)
            game.window.dispatch_event("on_resize", *resize)
            game.step(1)
        if toast:
            hud.clear_toasts()
            hud.enqueue_toast(toast)
            game.step(1)
        shown = game.draw()
        shown.convert("RGB").save(out / f"{name}.png")
        toasts = list(hud.active_toasts())
        hud.clear_toasts()
        hidden = game.draw()
        return {"image": f"{name}.png", "toasts": toasts, "corners": corners(shown), **toast_geometry(shown, hidden),
                "layouts": [list(hud.toast_layout(t).lines) for t in toasts] if hasattr(hud, "toast_layout") else None}
    finally:
        text_draw.set_text_scale(scale)
        game.close()


# (name, game, size, options): the start rooms at three sizes (the controls hint showing), a small interior room of
# each, the HD-2D map's far corner, and a short toast.
CAPTURES: tuple[tuple[str, str, tuple[int, int], dict[str, Any]], ...] = (
    *((f"{g}_{w}x{h}", g, (w, h), {}) for g in GAMES for w, h in SIZES),
    ("adventure_house_1280x720", "adventure", (1280, 720), {"room": "packs/core_regions/scenes/house.json"}),
    ("hd2d_rpg_cottage_1920x1080", "hd2d_rpg", (1920, 1080), {"room": "packs/core_regions/scenes/cottage.json"}),
    ("hd2d_rpg_1280x720_corner", "hd2d_rpg", (1280, 720), {"walk": ("LEFT", "DOWN")}),
    ("adventure_1280x720_saved", "adventure", (1280, 720), {"toast": "Game saved"}),
    ("hd2d_rpg_1280x720_resized_to_560x420", "hd2d_rpg", (1280, 720), {"resize": (560, 420)}),
    ("adventure_1280x720_text_scale_1.5", "adventure", (1280, 720), {"text_scale": 1.5}),
)


def main(argv: list[str]) -> int:
    out = Path(argv[0]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = out / "_projects"
    if work.exists():
        shutil.rmtree(work)
    from engine.project_scaffold import create_project

    facts: dict[str, Any] = {}
    for game in GAMES:
        create_project(work / game, game, game)
    for name, game, size, options in CAPTURES:
        facts[name] = capture(work / game, size, out, name, **options)
    shutil.rmtree(work)
    (out / "facts.json").write_text(json.dumps(facts, indent=1) + "\n", encoding="utf-8")
    for key, value in facts.items():
        print(key, {k: value.get(k) for k in ("border", "changed_outside_border", "corners")})
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
