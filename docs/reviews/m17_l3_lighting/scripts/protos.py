"""M17-L3 scratch prototypes, patched into the running process only (no engine file is changed). apply("a+b"):

reach      F1: a lamp's own fixture found within FIXTURE_REACH_M (0.15 m) of one of a small structure's drawn part
              boxes (not only inside one): a light that misses its lantern by a few centimetres, or hangs just
              under / over its cap, still isn't shadowed by its own lamp head. Size rule (<= 1 m across) unchanged.
slots4     F2: four shadow-casting lamps a room (MAX_SHADOW_LIGHTS 2 -> 4; the face-matrix array 12 -> 24).
emissive   E1: glTF emissive: emissiveFactor (x KHR_materials_emissive_strength) read from the material and added,
              unlit, as base colour x emissive (keeps the pixel art; emissiveTexture not read). Per draw.
glow       E2: a lamp lights its own lamp head: the drawn part of its fixture that holds the light (the lantern)
              glows with the lamp's colour x intensity x GLOW_K, so it goes dark when the lamp is off. No asset change.
"""
import inspect
import math
import textwrap

import engine.hd2d.glb as G
import engine.hd2d.lighting as L
import engine.hd2d.renderer as R
import engine.hd2d.scatter_layer as S
import engine.hd2d.settings as ST
import engine.water as W

FIXTURE_REACH_M = 0.15
GLOW_K = 0.8


def _patch_method(cls, name, old, new, module):
    src = textwrap.dedent(inspect.getsource(getattr(cls, name)))
    assert old and old in src, (name, old)
    ns = {}
    exec(compile(src.replace(old, new), f"<proto {name}>", "exec"), module.__dict__, ns)
    setattr(cls, name, ns[name])


def _box_distance(p, lo, hi):
    return math.sqrt(sum(max(lo[k] - p[k], 0.0, p[k] - hi[k]) ** 2 for k in range(3)))


def _local(lamp, st):
    dx, dy, dz = (lamp[0] - st.x / L.PIXELS_PER_METRE, lamp[1] - st.y / L.PIXELS_PER_METRE,
                  lamp[2] - st.elevation / L.PIXELS_PER_METRE)
    c, s = math.cos(math.radians(st.rotation)), math.sin(math.radians(st.rotation))
    return ((c * dx + s * dy) / st.scale, (-s * dx + c * dy) / st.scale, dz / st.scale)


def reach_fixtures(lamp, structures, models):
    out = set()
    for st in structures:
        model = models.get(st.model)
        if model is None or not model.parts or st.scale <= 0:
            continue
        lo, hi = model.bounds()
        if max(hi[0] - lo[0], hi[1] - lo[1]) * st.scale > L.FIXTURE_MAX_M:
            continue
        local = _local(lamp, st)
        reach = max(FIXTURE_REACH_M, L.FIXTURE_EPS_M) / st.scale
        if any(_box_distance(local, b_lo, b_hi) <= reach for b_lo, b_hi in L._node_boxes(model)):
            out.add(st.id)
    return frozenset(out)


def _apply_reach():
    L.lamp_fixtures = reach_fixtures


def _apply_slots4():
    ST.MAX_SHADOW_LIGHTS = 4
    L.MAX_SHADOW_LIGHTS = 4
    n = 0
    for mod in (L, R, S, W):
        for k, v in list(vars(mod).items()):
            if isinstance(v, str) and "u_face_vp[12]" in v:
                setattr(mod, k, v.replace("u_face_vp[12]", "u_face_vp[24]"))
                n += 1
    assert n >= 6, n
    _patch_method(L.Lighting, "bind", "(12 - len(self.face_vps))", "(24 - len(self.face_vps))", L)


def _apply_emissive():
    reader = G._Reader

    def materials(self):
        out = reader._l3_materials(self)
        for mat, raw in zip(out, (self.doc or {}).get("materials", [])):
            f = raw.get("emissiveFactor") or [0.0, 0.0, 0.0]
            strength = float(raw.get("extensions", {}).get("KHR_materials_emissive_strength", {})
                             .get("emissiveStrength", 1.0))
            mat.emissive = tuple(float(c) * strength for c in f)
        return out

    reader._l3_materials = reader.materials
    reader.materials = materials
    R.MESH_FS = R.MESH_FS.replace("uniform sampler2D u_tex;\n", "uniform sampler2D u_tex;\nuniform vec3 u_emissive;\n", 1)
    old = "    f_color = vec4(c.rgb * light_at(v_world, normalize(v_nrm), false), 1.0);\n}\n"
    assert R.MESH_FS.endswith(old)
    R.MESH_FS = R.MESH_FS[:-len(old)] + ("    f_color = vec4(c.rgb * (light_at(v_world, normalize(v_nrm), false)"
                                         " + u_emissive), 1.0);\n}\n")
    _patch_method(R.Hd2dRenderer, "_material_texture",
                  "        cache[key] = self._texture(image, nearest=part.material.nearest, repeat=part.material.repeat)\n",
                  "        cache[key] = self._texture(image, nearest=part.material.nearest, repeat=part.material.repeat)\n"
                  "        self.__dict__.setdefault('_l3_emissive', {})[id(cache[key])] = getattr(part.material, 'emissive', (0.0, 0.0, 0.0))\n",
                  R)
    _patch_method(R.Hd2dRenderer, "draw",
                  "        mp[\"u_model\"] = matrix\n",
                  "        mp[\"u_model\"] = matrix\n"
                  "        mp.set_uniform_safe('u_emissive', self.__dict__.get('_l3_emissive', {}).get(id(texture), (0.0, 0.0, 0.0)))\n",
                  R)


def _glow_boxes(lighting, structures, models):
    """Per lamp in the room: the world box of the drawn part of its fixture that holds the light (or is within
    FIXTURE_REACH_M of it), with the lamp's colour x intensity."""
    boxes = []
    for lamp in lighting.lamps:
        lp = lighting._lamp_pos(lamp)
        best = None
        for st in structures:
            model = models.get(st.model)
            if model is None or not model.parts or st.scale <= 0:
                continue
            lo, hi = model.bounds()
            if max(hi[0] - lo[0], hi[1] - lo[1]) * st.scale > L.FIXTURE_MAX_M:
                continue
            local = _local(lp, st)
            for b_lo, b_hi in L._node_boxes(model):
                d = _box_distance(local, b_lo, b_hi) * st.scale
                if d <= FIXTURE_REACH_M and (best is None or d < best[0]):
                    best = (d, st, b_lo, b_hi)
        if best is None:
            continue
        _d, st, b_lo, b_hi = best
        c, s = math.cos(math.radians(st.rotation)), math.sin(math.radians(st.rotation))
        pts = []
        for x in (b_lo[0], b_hi[0]):
            for y in (b_lo[1], b_hi[1]):
                for z in (b_lo[2], b_hi[2]):
                    pts.append((st.x / L.PIXELS_PER_METRE + (c * x - s * y) * st.scale,
                                st.y / L.PIXELS_PER_METRE + (s * x + c * y) * st.scale,
                                st.elevation / L.PIXELS_PER_METRE + z * st.scale))
        lo = tuple(min(p[k] for p in pts) for k in range(3))
        hi = tuple(max(p[k] for p in pts) for k in range(3))
        boxes.append((lo, hi, tuple(ch * lamp.intensity * GLOW_K for ch in lamp.color)))
    return boxes[:8]


def _apply_glow():
    R.MESH_FS = R.MESH_FS.replace(
        "uniform sampler2D u_tex;\n",
        "uniform sampler2D u_tex;\nuniform int u_glow_count; uniform vec3 u_glow_lo[8]; uniform vec3 u_glow_hi[8];"
        " uniform vec3 u_glow_col[8];\n", 1)
    if "u_emissive), 1.0);" in R.MESH_FS:
        old, new = "+ u_emissive), 1.0);", "+ u_emissive + glow()), 1.0);"
    else:
        old = "    f_color = vec4(c.rgb * light_at(v_world, normalize(v_nrm), false), 1.0);\n"
        new = "    f_color = vec4(c.rgb * (light_at(v_world, normalize(v_nrm), false) + glow()), 1.0);\n"
    assert old in R.MESH_FS
    R.MESH_FS = R.MESH_FS.replace(old, new)
    R.MESH_FS = R.MESH_FS.replace("void main() {\n    if (u_cut == 1",
                                  "vec3 glow() {\n    vec3 g = vec3(0.0);\n    for (int i = 0; i < 8; i++) {\n"
                                  "        if (i >= u_glow_count) break;\n"
                                  "        if (all(greaterThanEqual(v_world, u_glow_lo[i] - 0.02)) && "
                                  "all(lessThanEqual(v_world, u_glow_hi[i] + 0.02))) g += u_glow_col[i];\n"
                                  "    }\n    return g;\n}\nvoid main() {\n    if (u_cut == 1", 1)
    assert "vec3 glow()" in R.MESH_FS
    orig_set = L.Lighting.set_fixtures
    orig_bind = L.Lighting.bind

    def set_fixtures(self, structures, models):
        orig_set(self, structures, models)
        self._l3_glow = _glow_boxes(self, structures, models)

    def bind(self, program, *, terms=(1.0, 1.0, 1.0)):
        orig_bind(self, program, terms=terms)
        glow = getattr(self, "_l3_glow", [])
        try:
            program["u_glow_count"] = len(glow)
        except KeyError:
            return
        pad = [(0.0, 0.0, 0.0)] * (8 - len(glow))
        program["u_glow_lo"] = tuple(v for b in [g[0] for g in glow] + pad for v in b)
        program["u_glow_hi"] = tuple(v for b in [g[1] for g in glow] + pad for v in b)
        program["u_glow_col"] = tuple(v for b in [g[2] for g in glow] + pad for v in b)

    L.Lighting.set_fixtures = set_fixtures
    L.Lighting.bind = bind


BIAS_OLD = "lit += (dist - 0.006 <= texture(u_point_maps, base + vec2(dx, dy) * texel).r) ? 1.0 : 0.0;"
BIAS_NEW = ("lit += (dist - (0.02 + 0.008 * length(d)) / radius <= texture(u_point_maps, base + vec2(dx, dy) * texel).r)"
            " ? 1.0 : 0.0;")


def _apply_bias():
    """F3: the lamp shadow's depth bias in metres, growing with the distance to the lamp (a face texel's width
    grows with it), instead of 0.6 % of the lamp's radius (which grows with the radius: 4 cm at 7 m, 34 cm at 56 m)."""
    n = 0
    for mod in (L, R, S, W):
        for k, v in list(vars(mod).items()):
            if isinstance(v, str) and BIAS_OLD in v:
                setattr(mod, k, v.replace(BIAS_OLD, BIAS_NEW))
                n += 1
    assert n >= 6, n


def apply(names: str) -> None:
    for name in names.split("+"):
        {"reach": _apply_reach, "slots4": _apply_slots4, "bias": _apply_bias, "emissive": _apply_emissive, "glow": _apply_glow}[name]()
