# Notice: PixelLab-generated files in this folder

This folder is a **review experiment**, not part of Mesh's starter kit. Nothing here is bundled into the engine
package or copied into projects (see `docs/packaging.md`). Whether any of it may ship is the owner's decision; see
`docs/reviews/milestone17_stage1b_refinement.md`.

**Which files.**

- **Generated, and derived from generated images:**
  - the images in `textures/` (except where provenance says otherwise);
  - `characters/hero_m17*.png` and `characters/hero_m17_frames/`.
- **Made from PixelLab outputs, with this repository's scripts:**
  - `textures/window_a_glass.png` (recoloured);
  - `models/cottage_m17.glb` (embeds PixelLab textures);
  - the contact sheets and previews.
- **Mesh's own, from starter textures only:** `models/cottage_m17_geo.glb`.

The `provenance.json` beside each set records each file's endpoint, prompt, seed, cost and post-processing.

**Terms that apply.**

- The images were generated with [PixelLab](https://www.pixellab.ai) under the repository owner's paid subscription, subject to PixelLab's [Terms of Service](https://www.pixellab.ai/termsofservice) (version "last updated 2025-11-23", read on 2026-10-25).
- The terms give the subscriber ownership of the outputs and allow commercial use and redistribution.
- They forbid using the outputs to **train AI models** without PixelLab's written permission.
- They require compliance with the use restrictions of the CreativeML Open RAIL-M licence.
- Anyone reusing these files must respect both conditions. This repository grants no permission beyond what those terms allow, and gives no warranty about the files.

Raw API records (job dumps, downloads) are never committed. They hold account identifiers, and
`tooling/hd2d_assets/**/raw/` is ignored. `tests/test_generated_asset_hygiene.py` checks every tracked file for them.
