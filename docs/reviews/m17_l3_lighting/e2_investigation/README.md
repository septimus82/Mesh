# M17-L3 E2: lamp-driven lantern glow (investigation only; no implementation; never merged)

**Goal (owner's brief):**
- enabled lamps light their own lamp-head materials;
- disabled lamps give no glow;
- the glow follows the lamp's colour;
- ordinary glTF emission (E1) stays independent;
- nothing in Lakeside Village or its assets changes.

**Engine:** `redesign/visual-editor` `bc547f9` (C1–C3), with E1 (`feature/m17-l3-e1`) for compatibility. All scenes
are scratch copies: Stage 1's scratch Lakeside copy, the template village and #459's fixture room.

## 1. Associating a lamp with its own lamp head (`scripts/assoc.py`, `data/assoc_*.json`)

**Stage 1 prototype rule ("box"):** every fragment of *any* geometry inside the world box (+2 cm) of the lamp
fixture's nearest drawn node glows.

**Proposed rule ("part"):**
1. **The lamp's own fixture:** C1's `lamp_fixtures` (already merged and tested). A structure at most 1 m across, one
   of whose drawn nodes has a box within 0.15 m of the lamp.
2. **Its head:** the fixture's node whose box is nearest the lamp, within 0.15 m.
3. **What glows:** of that node, the materials no other node of the model uses. In the kit lamp post that is
   `lantern`, not the `iron` shared by the post, cap and lantern frame. If the node has none of its own, all of its
   parts glow.

Nothing else can glow: not another structure, not another node, not the ground.

| Scene (all lamps treated as on) | Lamp | Part rule glows | Box rule *also* glows |
|---|---|---|---|
| Template village | west, east | `lamp_*/lantern/lantern` (10 tris) | the post's top and the cap of the same lamp post |
| Lakeside (Stage 1 scratch copy) | 1, 2, 3 | `lamp_post*/lantern/lantern` | post top, cap |
| Lakeside | 4 (0.2 m inside the cottage's SE corner) | `lamp_post_4/lantern/lantern` | post top, cap, **the cottage's roof (shingles, plaster) and two high walls** |
| #459 fixture room | lamp_a | `lamp_a/lantern/lantern` | post top, cap, **the independent panel 0.23 m away** (`near_panel`) |
| #459 fixture room | lamp_b | `lamp_b/lantern/lantern` | post top, cap |
| Template cottage interior | ceiling lamp, no fixture | nothing | nothing |

**Conclusion:** the box rule is unreliable, because it lights whatever happens to overlap the head. Lakeside
`lamp_post_4` would light the cottage. The part rule selects exactly the lantern glass in every case, and needs no
asset or scene change.

**Authoring override (proposed, optional):** a glTF node custom property `mesh_lamp_head` (exported as `extras`,
like `mesh_collision`). It names the head explicitly for a fixture the rule can't read. The kit and Lakeside don't
need it.

## 2. The +0.6 ms, re-measured (`scripts/perf.py`, `scripts/protos.py`, `perf_runs/`, `data/perf_summary.json`)

Stage 1's prototype, unchanged, was patched into the current base. Method:
- one process per run;
- 6 rounds alternating base / prototype / E1;
- the same settled frame drawn 660 times, first 60 dropped;
- GPU clocks recorded per shot (unlocked: 1005–1185 MHz, P0 / P3).

| View | Base p10 (ms) | Prototype − base, per round (p10, ms) | Median |
|---|---|---|---|
| Village | 0.234–0.308 | −0.06, −0.05, +0.05, +0.03, +0.02, +0.01 | +0.013 |
| Lakeside, lamps 1–2 (shadow maps) | 1.651–1.794 | −0.09, +0.03, +0.03, −0.13, −0.00, +0.08 | +0.011 |
| **Lakeside, lamps 3–4** | 0.556–0.639 | **+0.55, +0.52, +0.55, +0.18, +0.55, +0.48** | **+0.532** |
| Cottage | 0.120–0.167 | +0.03, +0.00, −0.01, −0.01, −0.05, −0.02 | −0.011 |

- **The observation is real and reproducible:** about +0.5 ms (+85 %) in the Lakeside lamps 3–4 view, in 6 of 6
  rounds. The other views show nothing.
- **Why:** the prototype runs up to eight box tests in every structure fragment of the frame. In the shadow-mapped
  view that work hides behind the shadow-map sampling; in the lamps 3–4 view it doesn't.
- **Its median frame time is noisy:** clock states make p50 jump by about 1 ms between runs in the lamps 1–2 view.
  p10 is the steadier figure.
- **Rejected:** a per-fragment cost on everything, for ten triangles per lamp.

## 3. Proposed implementation (for a later, separate PR)

1. **At build** (the static batch is rebuilt on every room edit): find each lamp's head parts by the part rule.
   Draw each head part as its own draw, keyed by structure. Everything else stays batched exactly as now. C1's
   shadow spans are kept, so a lamp's own fixture is still left out of its shadow map.
2. **Per frame:** each head draw gets one uniform, `u_glow` (linear RGB):
   - lamp colour × intensity × K when its lamp is in the frame's enabled lamps;
   - otherwise 0, since a switched-off lamp isn't in `settings.lights`.
   
   K is a single constant, tuned on the kit lantern (Stage 1: 0.8).
3. **Shader:** in E1's emission step, `e = u_emissive × texel + linear(albedo) × u_glow`. The glow multiplies the
   lantern's own texture, so the glass glows and the iron frame stays dark (pixel art kept). Draws with neither term
   skip the step, as now.
4. **Cost:**
   - **Fragments:** extra work only in the head draws (about 10 triangles per lamp, 8 lamps at most).
   - **Draw calls:** +1 per lit head (2 in the village, 4 in Lakeside).
   - **No box tests.**
   - **Proxy:** E1's emissive lanterns use the same shader path and showed no measurable cost (E1 README).
5. **Tests to write then:**
   - the glow colour follows the lamp's colour and intensity;
   - a disabled lamp gives none;
   - every pixel outside the heads is byte-identical to E1;
   - Lakeside lamp 4's cottage walls are unchanged;
   - #459's panel is unchanged;
   - no fixture means no glow.

## 4. Compatibility with E1

- **E1 emission is the author's and stays independent:** a material with glTF emission glows whatever the lamps do.
- **A head part whose material already has glTF emission keeps it and gets no lamp glow:** no double glow, and the
  author's choice wins.
- **Both share one linear add and one branch:** E2 adds one uniform and a per-draw split for head parts only.
- **Daytime:** L1b ships its lamps off, so with E2 its lanterns are dark at noon, as wanted. E1 alone on an emissive
  lantern would glow at noon; no automatic daytime switching is proposed.

## 5. Content note

The kit's lantern texture is mostly dark frame, so a glow multiplied by it is modest. Stage 1 measured lamp-head
luminance 43–56 at night, against 12 now. Brighter glass texels would be a content change: optional, and not needed
for correctness.
