# Milestone 22C: scatter placement diagnostics

Why a scatter stroke placed fewer things than asked, said from the brush's own decisions, with what to do. M22C is based on `redesign/visual-editor` at `b3f3275` (#411). Evidence is in `m22c_evidence/`.

## The Lakeside problem, reproduced and explained

`engine.hd2d.scatter.brush` keeps every new instance at least the mean of its spacing and each neighbour's spacing away from it, whatever the neighbour is.
- **Trees after a meadow:** a small tree needs (3.0 + 0.16) / 2 ≈ 1.58 m clear of every grass tuft. A dense meadow (2.5 a square metre) leaves no such place, so every candidate is refused for spacing. The density count, meanwhile, counts only the tree's own collection, so the brush keeps trying until it gives up.
- **Rocks after a meadow:** for a rock (1.0 m) the gap needed is ≈ 0.58 m, so a few find room.

Before M22C, Studio said only "The stroke changed nothing (the rules, or the density already reached, left nothing to do).", or "Scattered 118 (Rocks)" with no hint that far fewer were placed than asked.

**Measured with the brush's own counts** (`tests/scatter_scenarios.py`, a 40 × 30 m room):

| Stroke over a dense meadow | Placed | Places tried and refused for spacing | What they were too near |
|---|---|---|---|
| Small trees | 0 | 2,170 | grass tufts 1,085, tall grass 605, pink flowers 248, … |
| Rocks | 53 | 6,323 | (the same meadow) |
| The meadow again | 0 | none tried | every dab (234 of 234) found its circle already at Per m² |

## What was built

**`engine/hd2d/scatter.py`:**
- **`refusal(asset, x, y, ground, rules)`** returns why a thing may not stand there, checked in exactly `allowed`'s order (the first that refuses). The reasons are: off the ground, slope, a material the brush isn't set to, a material the thing never grows on, water, a structure. `allowed` is now `refusal(...) is None`, so the logic is the same.
- **`Tally`**, passed optionally to `brush(..., tally=)`, counts what the brush decided:
  - **per dab:** dabs that found their circle already at the density, the room at its limit (50,000), or a brush too small for even one; and dabs that stopped short of what they set out to add;
  - **per refused place:** its reason, including "outside a clump" (Clumps) and "too near something already standing" (spacing);
  - **detail:** which asset it was too near, which materials were refused, and per asset what was refused and placed (a mixed collection's things differ);
  - **thin and remove:** what was under the brush.

  Counting adds no random numbers and changes no decision. The spacing check finds the first neighbour too near where it used `any()`: the same test, now naming it.
- **`explain(tally, collection, weights)`** says the most relevant verified reasons, with their counts, then what to do in Studio's own words (Per m², Clumps, Slope (°), the materials row, Out of water, Off buildings, Ctrl+drag thins). Rules:
  - **Short:** Studio says it on one line.
  - **When it speaks:** only when a stroke added under 90% of what it set out to add.
  - **Clumps** are blamed only when they are nearly all there is.
  - **Mixed collections:** a reason that applied to only some of the collection's things names them. A thing the stroke never placed is named even when the others filled its place: "No fallen branch: the ground is too steep (29 of 71 tries)."
- **`project_ops.scatter_stroke(..., tally=)`** fills one in for AI and CLI use.

**Mesh Studio (`engine/studio_hd2d.py`):**
- **A stroke that added nothing** says "Added nothing (*collection*). *why*". It still changes nothing: no edit, no undo step.
- **A stroke that added fewer than asked** says "Scattered *n* (*collection*): one undo step." and then why.
- **A thinning or removing stroke over bare ground** says "Nothing under the brush to thin out." (or "to remove.").

## Evidence

**Studio, hidden window, its own input events** (`tooling/scatter_diagnostics_studio.py`; `m22c_evidence/before_studio.json`, `after_studio.json`). A starter project's 40 × 30 m HD-2D room, with one continuous drag per stroke:

| Stroke | Before M22C (`b3f3275`) | After | Room changed; undo steps |
|---|---|---|---|
| Meadow | "Scattered 1055 (Meadow): one undo step." | the same | yes; 1 |
| Small trees over it | "The stroke changed nothing (the rules, or the density already reached, left nothing to do)." | "Added nothing (Small tree). Held back: the Meadow already there leaves too little room (2,903 of 4,356 tries). Thin it first (Ctrl+drag) or scatter these before it." | no; 0 |
| Rocks over it | "Scattered 118 (Rocks): one undo step." | "Scattered 118 (Rocks): one undo step. Held back: the Meadow already there leaves too little room (4,087 of 6,377 tries). Thin it first (Ctrl+drag) or scatter these before it." | yes; 1 |
| The meadow again | "The stroke changed nothing (…)" | "Added nothing (Meadow). Already as dense as Per m² asks here. Raise Per m² or brush somewhere sparser." | no; 0 |
| Ctrl+drag over bare ground | "The stroke changed nothing (…)" | "Nothing under the brush to thin out." | no; 0 |

The same strokes left the same scatter before and after: 1,055, 1,055, 1,173, 1,173 and 1,173 instances. Pictures: `before_trees_over_meadow.png`, `after_trees_over_meadow.png`, `after_rocks_over_meadow.png`, `after_meadow_again.png` (the longest message, 174 characters, fits Studio's status line at 1280 px wide).

**Every reason, from a real stroke** (`tests/test_scatter_diagnostics.py`, 10 fast tests). Each test also checks that the stroke places exactly the same with or without a tally.
- trees over a meadow;
- density already reached;
- too close to their own kind (a dense tree stroke);
- a steep mound, by the trees' own 25° limit and by a 10° Slope rule ("Raise Slope (°) (up to 40° for these)");
- a material the brush isn't set to, and stone a meadow never grows on;
- a pond, a hut, past the edge of the ground;
- Clumps, a brush too small for one, the room's limit;
- earth and water at once (both said, most first);
- a mixed rock-and-branch collection on a 20° hill, where the rocks fill and "No fallen branch: the ground is too steep" is said;
- thinning with nothing, and with something, under the brush.

**Placement unchanged** (`tests/test_scatter_placement_unchanged.py`, integration). Twelve steps of three scenarios (a dense meadow then trees and rocks; steep ground, a path, a pond and a hut; mixed collections) were recorded on `b3f3275` before any change. Each gives the identical scatter (SHA-256 of the stored rows, and the count), with and without a tally.

**Performance** (the three scenarios, median of 5 runs, ms; base `b3f3275` against M22C with a tally, measured twice each):

| Scenario | Base | M22C with a tally |
|---|---|---|
| Meadow, then trees and rocks | 472, 476 | 475, 483 |
| Varied ground | 550, 563 | 576, 570 |
| Mixed collections | 305, 311 | 314, 317 |

That is within run-to-run noise (about 1–3%). Nothing runs per frame; a stroke's words are made once, when it ends.

## Tests and gates

- **Fast:** `tests/test_scatter_diagnostics.py`, 10.
- **Integration:** `tests/test_scatter_placement_unchanged.py`, 7.
- **GPU:** `tests/test_scatter_diagnostics_gpu.py`, 3 (the Studio strokes above).
- **Existing scatter tests** (`test_scatter.py`, `test_editor_scatter_selection.py`) pass unchanged.
- **Gates:**
  - default selection: 10,067 passed, 212 skipped;
  - GPU tier: 217 passed, 0 failed (it ran before the final shortening of the words; the 7 scatter GPU tests were rerun after it and pass);
  - ruff gate ok; mypy 73 (baseline).
- **The timed fast tier** gains the 10 diagnostics tests (4,953 tests, from 4,943): about 0.02 s each once the scatter modules are imported, as they are in a full run. No timing budget or baseline was changed.

## Not changed

- The scene format, the stored scatter, the RNG sequence, spacing, and the collision, water and structure rules. Nothing is overridden or loosened.
- Ctrl+drag still thins everything under the brush, whatever collection is chosen. Thinning only the meadow where trees should go is now in the M22 backlog.
