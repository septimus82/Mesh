# Rivers R3: the bed, scatter, wading and deep water (#461) — evidence, not for merge

These are real 1280×720 hidden-window frames from `feature/rivers-r3` at `afc674c` (two review rounds on top of
`4b2b060`), made by `tools/r3_evidence.py` through Studio's buttons and the game's own key events (no OS desktop
automation). Only scratch copies were used; the owner's Lakeside originals were not touched, and the scripts refuse
to write outside the scratchpad (`tools/scratch_guard.py`). `report.json` holds the numbers below.

## A. Studio: carve the bed, clear the plants

**The R3 study village** (`tooling/r3_river_bed_study.py`): a 3 m stream under the bridge, its water 0.25 m below
the flat ground, with meadow scattered over its course before it was there.

| | |
|---|---|
| ![](A1_studio_before_carving_water_under_the_ground.png) **A1** the river selected; its water is under the ground, so unseen | ![](A2_studio_bed_carved.png) **A2** **Carve the bed**: a channel, banks, the water showing |
| ![](A3_studio_plants_cleared.png) **A3** **Clear plants**: the scatter in its water gone; the banks' scatter kept | |

**Studio's own flow:** a river drawn by clicking flat ground. New water stands 0.25 m over the ground clicked, so it
shows at once.

| | |
|---|---|
| ![](A4_studio_drawn_over_the_ground.png) **A4** drawn: its water (+8 px) over the grass | ![](A5_studio_drawn_river_carved_lies_in_its_bed.png) **A5** **Carve the bed**: its water lowered to just under the ground beside it (−1.6 px), lying in a channel |

**Carve the bed** took 653 ms from click to the reloaded room. Each button is one undo step. The GPU test checks
that undo puts the ground back exactly and redo carves it again.

## B. Play there (carved: 0.8 m deep, but 0.3 m at its second point, a ford)

| | | |
|---|---|---|
| ![](B1_play_wading_the_ford.png) **B1** wading the ford: ripples behind | ![](B2_play_stopped_at_deep_water.png) **B2** walking into the deep stretch: stopped in shallow water at its edge | ![](B3_play_on_the_bridge_over_deep_water.png) **B3** on the bridge's deck over the deep water: dry, 2 m up |

Each walk is the window's own key events: A held for 150 frames from the east bank.

| walk | ended at x (px) | deepest water under the feet | wading steps |
|---|---|---|---|
| across the ford | 526 (across) | 0.32 m | 7 |
| into the deep stretch | 643.5 (stopped; its middle is at 604) | 0.26 m | 1 |
| across the bridge's deck | 345 (across, still 2.0 m up) | — (dry) | 0 |

In the GPU test, a player put mid-channel in 0.8 m of water wades out to the bank.

## C. Lakeside (scratch copy): R1's brook on the room's own ground, carved with the ops

| | |
|---|---|
| ![](C1_lakeside_studio_before_carving.png) **C1** before: the brook's water under the meadow | ![](C2_lakeside_studio_carved_and_cleared.png) **C2** carved and cleared: a channel to the footbridge and the lake |
| ![](C3_lakeside_play_by_the_bridge.png) **C3** Play, by the bridge | ![](C4_lakeside_play_wading_the_brook.png) **C4** walked north across the 2 m brook: by default a quarter of its width deep, 0.47 m at most, so it is wadeable; ripples behind |

- Carving Lakeside's brook took **173 ms** (its banks now reach the higher ground beside it), and clearing its
  scatter **35 ms**.
- While walking through the river, play frames had a median of **15.0 ms** locally.

## Independent review

A fresh reviewer read the `4b2b060` source cold and confirmed nine findings with headless probes. All are addressed
in `c96e3e8`, each with a test:

- **Pit past an end.** A dry bed carried on past a river's end, up to 1 m deep.
- **Floating edges.** Water drawn over the ground floated at its edges after carving.
- **Bank cliff.** The bank stopped at 4 m, leaving a cliff for water far below the ground.
- **Stuck in deep water.** A character in deep water could never move.
- **Threshold rounding.** A 2 m stream was wadeable or not depending on rounding.
- **Footprint check.** The deep check effectively tested the centre of the feet only.
- **Scatter handling.** The carve op popped and restored scatter, which could lose the key or share rows.
- **Wading memory** was kept in a dict keyed by `id(sprite)`.
- **Broken rivers.** One broken river hid the other rivers' water from scatter. While fixing this, I also found
  that a broken river blocked all sculpting in its room.

**Re-review of `c96e3e8`.** The reviewer confirmed those fixes and found two new defects, both fixed in `afc674c`
with tests and mutation checks:

- **Ratchet into deep water.** Tiny steps (0.25 px or less) could edge across deep water, because the escape
  allowance added its slack at every step. The cap is now set once and never grows.
- **Neighbouring rivers.** A river beside a carved one sank again at every carve. It is now sunk only where it
  stands *above* the ground beside it.

The final verification is on PR #465.

## Limitations

- **Carving only lowers the ground.** It may also lower a river's own water, where that stands over the ground
  beside it. A river's two ends are cut square; past an end, a bank rises from that end's water level (lake mouths
  are R4).
- **Collision follows the drawn water.** The deep-water rule asks of the ribbon (`RiverIndex`) and the floor under
  each footprint point; it ignores ponds, whose own walkable/blocking rule is unchanged.
- **Ripples, but no wading sound.** Wading shows ripples (with `water_step` events) but no speed change and no
  wading sound (rivers have no `step_sound` field yet).
- **A 2 m stream is wadeable by default.** By default a bed is a quarter of its width deep, so a 2 m stream is
  0.5 m at most. Make deeper or shallower stretches with **Bed depth**, or with per-point depths (AI / `mesh author`).
- **A test-order issue, found while checking:** `tests/test_scatter.py::test_the_way_onto_stairs_is_kept_clear…`
  fails when run right after the HD-2D world, floors and terrain suites. It fails the same way on the base commit
  `eb680c3`, passes alone, and passes in CI's order. It is reported here and not changed.
