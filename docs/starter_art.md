# Starter art: provenance

New Mesh projects get three pictures of Mesh's own (Milestone 11); the HD-2D starter adds a fourth:

| File | What | Layout |
|---|---|---|
| `assets/sprites/starter_hero.png` | the player: brown hair, blue tunic, red scarf | 4 x 4 sheet of 32 x 48 frames |
| `assets/sprites/starter_villager.png` | the "Person" object: straw hat, green tunic, apron | 4 x 4 sheet of 32 x 48 frames |
| `assets/sprites/starter_sign.png` | the "Sign" object: a wooden signpost | one 32 x 32 picture |
| `assets/sprites/starter_merchant.png` | the HD-2D starter village's shopkeeper: dark hair, plum tunic, cream apron, brown hat (Milestone 16 Stage 6A) | 4 x 4 sheet of 32 x 48 frames |
| `assets/sprites/hd2d_hero.png`, `hd2d_villager.png`, `hd2d_merchant.png` | the same three characters in Mesh's HD-2D style, used by the HD-2D RPG template (Milestone 16 visual direction) | 4 x 4 sheets of 32 x 48 frames |

The character sheets have one row per direction (down, left, right, up) and four columns: stand, step, stand,
other step. The templates set them up exactly as Studio's "Set up walking" does (`project_ops.character_clips`):
standing is the first column and walking is all four.

**Provenance.** Every pixel is drawn by `tooling/make_starter_art.py` from rectangles and a computed outline, using
Pillow. No image, font or asset from anywhere else is used, so the art is Mesh's own and ships under the
repository's licence. The script is deterministic: run it again and it writes the same files.

    py -3.13 tooling/make_starter_art.py

**The HD-2D style** draws the same figures, frames and animation to sit in a lit 3D scene: muted colours within the
saturation and lightness of the HD-2D kit's textures, three tones lit from the upper left (the engine's default sun),
outlines in a darker shade of what they edge instead of near-black, and the feet on the frame's bottom row so they
touch the ground. Its left-facing frames are drawn rather than mirrored, so the light stays on the left.
Why: `docs/reviews/milestone16_hd2d_visual_direction.md`.

To change the art, edit the palettes or shapes in that script and rerun it. Then rerun
`tooling/make_template_previews.py` for the launcher's template pictures.

`assets/sprites/animated_player.png` (eight coloured "no picture" frames) is still copied into new projects:
projects made before Milestone 11 point their player and Person at it.
