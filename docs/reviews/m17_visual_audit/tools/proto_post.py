"""M17 audit PROTOTYPE (scratch only, no engine code changed): the same real capture as tooling/scene_snapshot.py,
with post effects added to the game's existing PostProcessPipeline at runtime in this process:

  - grade: engine.post_processing.Vignette + ColorGrading (existing engine classes, never used by the engine today);
  - tilt:  + a tilt-shift prototype defined HERE (screen-space blur growing away from the player's horizontal band;
           at a fixed camera pitch, screen height stands in for depth - a production version would read depth).

    python proto_post.py PROJECT SCENE OUT.png MODE [X Y]     MODE: grade | tilt
"""
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

REPO = Path(r"D:\Games\Mesh")
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tooling"))

import engine.post_processing as pp  # noqa: E402


@dataclass
class TiltShift(pp.PostProcessEffect):
    name: str = "m17_tilt_shift"
    focus: float = 0.47   # screen height (0 bottom, 1 top) of the sharp band: the player, whom the camera follows
    band: float = 0.10    # half-height of the sharp band
    max_px: float = 3.5   # blur radius at the top and bottom edges, in pixels

    @property
    def fragment_source(self) -> str:
        return """
        #version 330
        uniform sampler2D u_texture; uniform float u_focus; uniform float u_band; uniform float u_max;
        in vec2 v_uv; out vec4 fragColor;
        void main() {
            vec2 px = 1.0 / vec2(textureSize(u_texture, 0));
            float d = max(0.0, abs(v_uv.y - u_focus) - u_band) / max(0.001, 0.5 - u_band);
            float r = clamp(d, 0.0, 1.0); r = r * r * u_max;
            vec4 acc = vec4(0.0); float w = 0.0;
            for (int i = -3; i <= 3; i++) for (int j = -3; j <= 3; j++) {
                vec2 o = vec2(float(i), float(j)) / 3.0;
                if (dot(o, o) > 1.0) continue;
                acc += texture(u_texture, v_uv + o * r * px); w += 1.0;
            }
            fragColor = acc / w;
        }
        """

    def uniforms(self) -> Dict[str, Any]:
        return {"u_focus": self.focus, "u_band": self.band, "u_max": self.max_px}


def main() -> None:
    project, scene, out, mode = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), sys.argv[4]
    player = (float(sys.argv[5]), float(sys.argv[6])) if len(sys.argv) > 6 else None
    original = pp.PostProcessPipeline.__init__

    def with_effects(self: Any) -> None:
        original(self)
        if mode == "tilt":
            self.add_effect(TiltShift())
        self.add_effect(pp.ColorGrading(brightness=1.02, contrast=1.08, saturation=1.12))
        self.add_effect(pp.Vignette(strength=0.35, radius=0.85))

    pp.PostProcessPipeline.__init__ = with_effects  # type: ignore[method-assign]
    import scene_snapshot

    info = scene_snapshot.snapshot(project.resolve(), scene, out.resolve(), player=player, size=(1280, 720))
    print("camera", info.get("camera"))


if __name__ == "__main__":
    main()
