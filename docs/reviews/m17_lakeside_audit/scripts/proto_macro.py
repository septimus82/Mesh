"""Scratch PROTOTYPE (NOT engine behaviour): a broad, world-space tone variation over the meadow, so the audit can
show what the top finding's remedy would look like before anyone builds it. In THIS process only, the ground's
shader (renderer.GROUND_FS: its unpainted grass texels) and the scatter billboards' shader (scatter_layer.BILLBOARD_FS:
grass, flowers, bushes, reeds, canopies) multiply their colour by one smooth value-noise field of the world position
(~11 m and ~4 m features): lusher/darker/cooler patches and paler/warmer ones. No file in the engine is changed.
Then runs capture.py's shots. Usage: proto_macro.py STRENGTH PROJECT OUT W H SHOTS_JSON
"""
import runpy
import sys

sys.path.insert(0, r"D:\Games\Mesh-lva")
import engine.hd2d.renderer as R  # noqa: E402
import engine.hd2d.scatter_layer as S  # noqa: E402

strength = float(sys.argv[1])
MACRO = """
float mhash(ivec2 p) {
    uint h = uint(p.x) * 2654435761u + uint(p.y) * 2246822519u + 97u;
    h = (h ^ (h >> 15u)) * 2246822519u; h ^= h >> 13u;
    return float(h & 0xffffffu) / 16777215.0;
}
float mvalue(vec2 x) {
    ivec2 i = ivec2(floor(x)); vec2 f = fract(x); f = f * f * (3.0 - 2.0 * f);
    return mix(mix(mhash(i), mhash(i + ivec2(1, 0)), f.x), mix(mhash(i + ivec2(0, 1)), mhash(i + ivec2(1, 1)), f.x), f.y);
}
vec3 meadow_tone(vec2 m) {  // m: world metres
    float n = 0.7 * mvalue(m / 11.0) + 0.3 * mvalue(m / 4.0 + 17.0);
    n = smoothstep(0.2, 0.8, n);
    vec3 lush = vec3(0.80, 0.88, 0.84), dry = vec3(1.12, 1.06, 0.84);
    return mix(vec3(1.0), mix(lush, dry, n), %.3f);
}
""" % strength
g = R.GROUND_FS
g = g.replace("float hash(ivec2 p, int m) {", MACRO + "float hash(ivec2 p, int m) {", 1)
g = g.replace("vec4 c = pick == 0 ? own : mat;", "vec4 c = pick == 0 ? vec4(own.rgb * meadow_tone(v_world.xy), own.a) : mat;", 1)
assert g != R.GROUND_FS and g.count("meadow_tone") == 2
R.GROUND_FS = g
b = S.BILLBOARD_FS
b = b.replace("void main() {", MACRO + "void main() {", 1)
b = b.replace("f_color = vec4(c.rgb * max(", "f_color = vec4(c.rgb * meadow_tone(v_world.xy) * max(", 1)
assert b != S.BILLBOARD_FS and b.count("meadow_tone") == 2
S.BILLBOARD_FS = b
sys.argv = ["capture.py"] + sys.argv[2:]
runpy.run_path(r"C:\Users\slebb\AppData\Local\Temp\claude\c18a071c64bbe7a7\bff3a484-a7b8-4c6b-bf14-a015c42db67e\scratchpad\lva\capture.py", run_name="__main__")
