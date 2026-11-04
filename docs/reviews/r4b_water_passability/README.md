# Rivers R4B evidence (#461, PR #468) — not for merge

Head `ddff3ce`, base `b5ef725` (R4A merged). Captured on Windows in hidden 1280x720 windows from **scratch copies** of
`D:\Games\Lakeside Village`; the original project was only read.

## Frames

| File | What |
|---|---|
| `A1_lakeside_from_the_east_before_after.png` | The player walks west into Lakeside's lake (blocking: *Walk through it* off). Before: stopped by the pond's 2D box, 29.5 px short of the visible water. After: 10.5 px (half a footprint). |
| `A2_lakeside_from_the_north_by_the_mouth_before_after.png` | The same towards the lake by the brook's mouth: 49.4 px short before, 14.5 px after. |
| `B_studio_river_panel_walking_into_it_wade.png` | Studio's River panel: **Walking into it** Auto / Wade / Block, with Wade depth. |
| `B_studio_water_inspector_walking_into_it_block.png` | The water inspector's **Walking into it**, set to Block (the status line says what it means). |

## Measurements (`report.json`; same machine, back to back, nothing else running)

| | before (b5ef725) | after (ddff3ce) |
|---|---|---|
| Stopped short of the visible shore, east / north by the mouth | 29.5 / 49.4 px | 10.5 / 14.5 px |
| Navigation cells (Lakeside) | 11725 | 11349 (the lake's cells left out) |
| Navigation grid build | 462 ms | 501 ms |
| `World.stand` near the lake | 36.8 µs | 57.6 µs |
| Play frame, median | 17.53 ms | 17.61 ms |
| Scene load | 864 ms | 831 ms |

## Tools (`tools/`)

- `r4b_evidence.py <repo> before|after` — the Lakeside walks, frames and timings (scratch copy; `scratch_guard.py`
  refuses any output outside the scratch folder).
- `r4b_studio.py` — the Studio frames.
- `mutate_b.py` — 28 mutations of the R4B rules, each run against the test meant to catch it; all 28 caught.

## Independent review

Five rounds by a fresh reviewer agent with its own probes (trap searches over ponds, blocked rivers and an uneven
terrain-shored pond; Lakeside's lakes; dry-ground comparisons; NPC sweeps; a fuzz of `World.path`'s start fallback).
Final verdict at `ddff3ce`: no blockers, no should-fix. See the PR for each round's findings and fixes.
