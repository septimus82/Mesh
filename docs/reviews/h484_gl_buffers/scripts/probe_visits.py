"""Room visits on a worktree (argv[1]), composite never used: live GL objects per kind after each visit."""
import os, sys
from pathlib import Path
WT = Path(sys.argv[1]); sys.path.insert(0, str(WT)); sys.path.insert(1, str(WT / "tooling")); os.chdir(WT)
import engine.optional_arcade  # noqa
from hd2d_demo import HiddenGame
proj = Path(sys.argv[2])
game = HiddenGame(proj, size=(960, 540)); game.window.audio.set_muted(True)
ctx = game.window.ctx
for name in ("start", "cottage", "start", "cottage", "start", "cottage", "start"):
    game.load(f"packs/core_regions/scenes/{name}.json"); game.step(30); game.window.use(); game.window.hd2d_renderer.draw()
    print(name, {k: getattr(ctx.stats, k)[0] - getattr(ctx.stats, k)[1] for k in ("texture", "framebuffer", "program", "buffer", "geometry")})
game.close()
