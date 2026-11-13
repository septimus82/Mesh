# #422 — A* performance test: reliability and what it measures

## What failed
Post-merge CI [43471828718](https://github.com/septimus82/Mesh/actions/runs/43471828718) (`91db664`, #506 merged)
failed `pytest (ubuntu-latest)` on one test: `tests/test_pathfinding_astar_perf.py::test_astar_perf_maze_50x50`
measured 0.5466825 s against a fixed 0.5 s. Linux pytest: 11,658 passed, 540 skipped, 1 failed. Extended
[43471828481](https://github.com/septimus82/Mesh/actions/runs/43471828481) passed on its first attempt. The failed run
is kept as it was; it was not rerun. #506 changed GPU test environment handling only and no file on this path.

## Root cause
**Two faults in the test, neither in the engine.**

1. **One unrepeated wall-clock sample against a fixed limit.** The search it timed takes 5-8 ms. A single sample is
   exposed to any stall of the process, however fast the code is.
2. **Three of the four timed tests did not run the production search.** `count_expansions_astar()` in the test file
   was a copy of `engine/pathfinding/astar.py::astar` with a pop counter added. The open-grid, maze and diagonal tests
   timed and counted that copy. Only the spiral test called `astar()`, and it asserted nothing but the time (not even
   that a route came back). The copy differed from production only by its counter, so the tests looked right while a
   change to the real search could not fail them.

### Evidence that the failure was a stall, not a slow search
- **Windows CI history** (`astar_perf_guard_evidence/windows_junit_history.csv`, 42 runs with junit; the Linux job
  uploads none): the maze test took 4-16 ms in every run (median 7 ms), the open-grid test 5-15 ms. Nothing over 0.1 s.
- **Linux CI history:** the pytest job ran in 43 of the last 60 CI runs; this test failed once (this run). The three
  other red runs were unrelated contract tests.
- **Runner speed doesn't explain it.** That runner's speed was 1.13 against a calibrated range of 0.622-1.152: about
  13% slow. The sample was about 100 times the usual time.
- **Full garbage collections are long enough.** A full default-suite run on the unchanged base with a probe on
  `gc.callbacks` (`full_suite_gc_pauses.json`, Python 3.13, this project's Windows machine): 63 full collections,
  median pause 174 ms, 17 over 250 ms, the longest 474 ms, landing in whichever test was running. The heap held
  1.08 million tracked objects when the A* tests started.
- **Reproduced on purpose:** one real full collection of a large heap placed inside the old maze test's timed search
  fails it at 0.553 s; the same collection inside one sample of the new runtime check leaves it passing (probe costs
  29.7-33.6 against 150).

This is consistent with a collection or a descheduled runner landing in the 5 ms sample. It is not proof of which: the
failed run recorded only the one number.

## The replacement
Every check now runs `engine.pathfinding.astar`. Two guards, kept apart, in `tests/test_pathfinding_astar_perf.py`.

### Work, exact (deterministic, the same on every machine)
A stand-in for the grid answers as the real `NavGrid` does and counts the bounds questions `astar` asks: one per
neighbour of each tile it expands. That count is the production search's work, taken without copying the algorithm and
without adding anything to the engine. For each scenario:
- a route exists, starts and ends where asked, crosses only walkable tiles by legal steps, with no tile twice
  (`assert_path_invariants`, the existing helper);
- it is a shortest route (`Scenario.tiles`; the cardinal ones are checked against a breadth-first flood);
- the same search returns the same route, three times;
- no tile is expanded more than once;
- the tiles expanded may not exceed today's (`Scenario.expanded`).

| scenario | route (tiles) | expanded today | walkable tiles |
|---|---:|---:|---:|
| open 50x50, corner to corner | 99 | 2,499 | 2,500 |
| maze 50x50 | 185 | 2,004 | 2,059 |
| diagonal 50x50 | 50 | 49 | 2,500 |
| straight across open ground (new) | 50 | 49 | 2,500 |
| spiral 21x21 | 37 | 204 | 207 |

The open, maze and spiral searches already flood nearly every tile, so a weaker heuristic has nothing left to waste
there. The diagonal scenario and the new straight one are where the heuristic does the work (49 tiles of 2,500): they
are the ones that catch its loss.

### Runtime, coarse and runner-relative
The time one neighbour probe costs, as a fraction of `tooling.runner_calibration.cpu_ms()`: the repository's fixed
pure-Python calibration loop, the reference the enforced terrain gate already measures runners with, with its own
tests. Seven timed samples a scenario (short searches repeated so a sample is a few milliseconds), the calibration
read on every third round, one untimed warm-up, and **medians** of both. No retries, no sleeps, no fastest-of.
- A slow or busy runner slows both sides.
- One stalled sample moves neither median.
- `MAX_PROBE_COST = 150` millionths of a calibration loop per probe.

Cost: about 0.5 s (the calibration reads are most of it); the file's three timing tests together about 2 s.

## Measurements (`astar_perf_guard_evidence/probe_cost_runs.jsonl`)
Probe cost per scenario, p50 (min-max), with the search's own time:

| condition | runs | loop ms | open | maze | diagonal | straight | spiral | over 150 |
|---|---:|---:|---|---|---|---|---|---:|
| Python 3.13, idle | 100 | 19.7 | 33.0 (31.2-34.8) | 31.9 (30.6-35.1) | 39.3 (37.1-45.6) | 42.0 (39.6-54.1) | 29.2 (27.8-36.5) | 0 |
| Python 3.10, idle | 100 | 21.7 | 38.0 (37.1-40.2) | 37.2 (35.9-39.8) | 47.7 (46.0-50.6) | 48.0 (46.0-54.4) | 34.1 (33.0-36.4) | 0 |
| 3.13, 16 busy processes on 16 cores | 40 | 36.2 | 30.5 (24.6-33.8) | 29.5 (23.2-32.4) | 37.6 (30.6-45.1) | 40.0 (32.9-46.7) | 26.8 (25.1-34.8) | 0 |
| 3.13, 32 busy processes on 16 cores | 40 | 36.6 | 30.7 (6.0-48.5) | 29.4 (5.3-31.3) | 37.1 (7.8-39.8) | 39.7 (7.2-42.5) | 26.6 (5.1-46.0) | 0 |

Under load the search itself ran 1.7-2.6 times slower in wall-clock (maze 5.1 -> 8.5-9.4 ms, open 6.5 -> 11.0-16.9 ms)
and the cost did not move. Highest cost in 280 runs: 54.4. The low minimums with 32 processes are runs where the
calibration reads were the ones held up: that hides a slowdown for that run, it cannot fail one.

## Sensitivity (`slowdown_sweep.jsonl`)
Fixed extra work added to every call of the production module's heuristic (no file changed), 20 runs each. "x" is how
many times slower the search became; a scenario is flagged when its cost passes 150.

| extra work | open | maze | diagonal | straight | spiral | runs failing |
|---|---|---|---|---|---|---:|
| none | x1.0, cost 33 | x1.0, 32 | x1.0, 40 | x1.0, 43 | x1.0, 30 | 0/20 |
| `sum(range(200))` | x1.4, 47 | x1.4, 46 | x1.9, 75 | x2.0, 86 | x1.5, 43 | 0/20 |
| `sum(range(300))` | x1.7, 53 | x1.8, 52 | x2.6, 92 | x2.8, 107 | x1.8, 50 | 0/20 |
| `sum(range(400))` | x2.3, 72 | x2.3, 72 | x3.6, 137 | **x4.1, 159** | x2.5, 69 | 20/20 |
| `sum(range(600))` | x3.4, 102 | x3.1, 101 | **x5.3, 210** | **x5.9, 251** | x3.3, 99 | 20/20 |
| `sum(range(800))` | x3.9, 131 | x4.0, 131 | **x7.1, 282** | **x7.9, 335** | x4.4, 129 | 20/20 |
| `sum(range(1500))` | **x6.9, 229** | **x7.1, 228** | **x13.5, 527** | **x15.2, 633** | **x7.9, 227** | 20/20 |

A scenario is flagged once its search is about 3.5 times slower (straight, diagonal) to 5 times slower (open, maze,
spiral), and then in every run; below about 3 times, never. The old limit needed the maze search about 70-100 times
slower (0.5 s against 5-8 ms).

## Faults the guards catch
Committed, through `monkeypatch` on the production module (nothing in the engine changes):
- six broken routes (none, through a wall, a jump, stops short, starts elsewhere, a detour) fail the route check;
- the open list as a stack fails "not a shortest route";
- no heuristic: the diagonal and straight searches expand 2,499 and 1,850 tiles instead of 49 and are over budget,
  while their routes stay correct;
- every entry queued twice: all five scenarios fail (a tile expanded twice, or over budget);
- extra work in the heuristic (x15 on the straight search) fails the runtime check with the work count unchanged;
- one sample stalled for 0.55 s, as on the failed run, does **not** fail the runtime check.

Source mutations of `engine/pathfinding/astar.py`, each restored (`mutations.json`, `mutation_survivors.jsonl`):

| mutation | new guards | old file |
|---|---|---|
| walkable check dropped (walks through walls) | maze, spiral fail | passes |
| heuristic always 0 | maze, diagonal, straight, spiral fail | passes |
| open list popped newest first | all five fail | passes |
| re-queues a tile reached again at the same cost | never ends (no result in 90 s) | never ends |
| a fixed busy loop per neighbour (`sum(range(900))`) | runtime check fails | passes |
| heuristic ten times too high (greedy) | pass | passes |
| diagonal steps cost as much as straight ones | pass | passes |
| a sort of the open list on every expansion | pass | passes |

The three that pass:
- **Greedy heuristic:** in these scenarios it finds the same shortest routes with less work (the open search runs 25
  times faster), so it is not a performance regression here. `test_astar_golden[diagonal_straight]` fails on it.
- **Diagonal step cost:** a route-choice defect, not a performance one. The same golden test fails on it.
- **A sort per expansion:** the search runs 1.2-2.3 times slower (cost 36-92). That is below what the runtime check
  sees, by design. No other A* test catches it.

## Limits
- **Constant-factor slowdowns under about 3.5 times are not caught.** The bound trades that for not failing on a slow
  runner. It can come down once CI has recorded enough costs (below).
- **Hosted runners are not yet measured.** The bound rests on one machine, two Python versions, idle and loaded. The
  test records each run's costs in junit (`astar_probe_cost_*`), which CI uploads for the Windows pytest shards; the
  Linux pytest job uploads no junit, so on Linux a cost is seen only if the check fails. CI's CPUs differ by 2.4 times
  on the calibration loop (10.5-25 ms across recent GPU-lane records); how far the ratio itself moves between them is
  the open question.
- **The work count leans on how `astar` asks the grid** (one `in_bounds` per neighbour, two up front). If that changes,
  the count says so and stops rather than report a wrong number.
- **Open ground floods.** Corner to corner over open ground the search expands 2,499 of 2,500 tiles, because ties on
  `f` go to the lower `g`. Preferring the higher `g` would cut that sharply. The budget records today's behaviour; the
  engine is not changed here.
- **Other fixed wall-clock tests remain** (`test_core_region_load_perf.py`: 0.2 s; `test_prefab_resolution_perf_guard.py`)
  and are exposed to the same kind of stall. Not changed here.
