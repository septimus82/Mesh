"""#484 (H-484A prototype, evidence branch only): room round trips leave live GL objects flat.

Each frame ends as arcade's event loop ends it: on_update, on_draw, then the deferred deletion arcade's
``Window.flip()`` runs (``ctx.gc()``; no buffer swap, so nothing a test reads back is lost). Arcade's default
``gc_mode="context_gc"`` keeps every dropped GL object queued in ``ctx.objects`` until then, so a loop that never ends a
frame (#484's original probe) counts that queue as live objects. One round trip of warm-up is allowed for one-time
caches; after it each room must come back to exactly the same counts. GL-gated: MESH_GL_SMOKE=1."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from engine import optional_arcade

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("MESH_GL_SMOKE") != "1" or not optional_arcade.has_arcade(),
                       reason="real-GPU render test is opt-in (set MESH_GL_SMOKE=1 with a display/GL context)"),
    pytest.mark.filterwarnings("ignore:draw_text is an extremely slow function"),
    pytest.mark.filterwarnings("ignore:UIInputText is now a UIStyledWidget:DeprecationWarning"),
]

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tooling"))
KINDS = ("texture", "framebuffer", "program", "buffer", "geometry", "vertex_array")
SCENES = "packs/core_regions/scenes"
ROUND_TRIPS = 8


def test_room_round_trips_leave_live_gl_objects_flat(tmp_path: Path) -> None:
    from hd2d_demo import HiddenGame

    from engine.project_scaffold import create_project

    project = tmp_path / "game"
    create_project(project, "Game", template_id="hd2d_rpg")
    game = HiddenGame(project, size=(960, 540))
    try:
        game.window.audio.set_muted(True)
        w, ctx = game.window, game.window.ctx

        def live() -> dict[str, int]:
            return {k: getattr(ctx.stats, k)[0] - getattr(ctx.stats, k)[1] for k in KINDS}

        seen: list[tuple[str, dict[str, int]]] = []
        for v in range(2 * ROUND_TRIPS + 1):
            room = ("start", "cottage")[v % 2]
            w.load_scene(f"{SCENES}/{room}.json")
            for _ in range(30):
                w.dispatch_event("on_update", 1 / 60)
                w.dispatch_event("on_draw")
                ctx.gc()  # (what Window.flip() does each frame)
            assert not ctx.objects, f"visit {v}: garbage GL objects left after the frame ended"
            seen.append((room, live()))
        report = json.dumps(seen)
        for v in range(4, len(seen)):  # (visits 0-3: warm-up, one round trip)
            assert seen[v] == seen[v - 2], f"visit {v} ({seen[v][0]}) differs from the last visit to it: {report}"
    finally:
        game.close()
