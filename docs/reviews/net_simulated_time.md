# Networking tests: simulated time for the simulated harnesses

Astra finding (12 November): the networking tests wait on real time. This is the last of the three test-performance
findings. Baseline `2cf9d8de` (CI 43811262872, Extended 43811263074, both green on attempt 1).
Evidence: `docs/reviews/net_simulated_time_evidence/`.

## 1. Baseline

Headless networking modules, Windows 11, Python 3.13, three runs (`baseline_local_3_runs.txt`):

| module | tests | median | spread |
|---|---|---|---|
| `test_mesh_net_walk` | 16 | 35.25 s | 0.13 |
| `test_mesh_net_owed` | 27 | 17.49 s | 0.19 |
| `test_mesh_net_resume` | 18 | 17.03 s | 0.08 |
| `test_mesh_net_world` | 38 | 16.18 s | 2.13 |
| characters, owed_reset, owed_writes | 69 | 19.02 s | |
| scene, mesh_net, downlink, encounter, playback | 32 | 7.21 s | |
| **all** | **200** | **112.26 s** | 3.82 |

By kind of test:

| kind | tests | time | what it waits for |
|---|---|---|---|
| simulated walking (stand-in window and server) | 16 | 35.3 s | the wall clock, for simulated ticks |
| of which negative (input never arrives, wall blocks) | 2 | 2.3 s | a 1 s timeout each |
| simulated reconnect (stand-in window, real `World`) | 9 | 7.3 s | 5 ms frames, a 150 ms close, 25 ms polls |
| of which negative (wrong resume) | 4 | 5.4 s | a 1 s timeout each |
| real loopback reconnect (N6: real `Server`, TCP, `Arena`) | 9 | 9.7 s | a real 20 Hz server and connection |
| of which negative | 6 | 8.0 s | a 1 s timeout on the real server (five of them) |
| other real loopback and in-process (world, scene, net, downlink) | 70 | 23.4 s | real sockets, real 20 Hz ticks |
| persistence (server processes killed and restarted, files) | 96 | 36.6 s | real processes |
| real windows (gpu lane, Extended 43811263074) | 4 | 83.6 s Windows, 75.2 s Linux | real windows, real server |

Setup and teardown are under 5 ms a test, apart from one import of the engine (1.8 to 2.7 s) in whichever test
runs first.

On CI (43811262872, JUnit of the Windows shards): walking 35.22 s and reconnect 16.41 s, both in Windows shard 2,
whose tests total 366 s. The Linux job runs plain `pytest -q` and keeps no per-test record.

### Where the simulated tests' time went (`split_baseline.json`)

| | walking (16 tests) | simulated reconnect (9 tests) |
|---|---|---|
| wall | 35.45 s | 7.46 s |
| server ticks simulated | 1,087 | (frames, not ticks) |
| computing those ticks | **0.20 s** | under 0.01 s |
| `asyncio.sleep` calls | 4,374 (2,770 of 1 ms, 1,604 of 5 ms) | 496 (298 of 5 ms, 189 of 25 ms, 9 of 150 ms) |
| waiting for timeouts that must expire | 2 x 1 s | 4 x 1 s |

The walking tests' server advanced from elapsed real time: a 20 ms tick found by polling the clock every 1 ms. On
Windows a 1 ms or 5 ms sleep lasts one timer period (15.6 ms), so a "20 ms" tick took 31 to 33 ms: 1,087 ticks,
35 s, for a fifth of a second of simulation. Nothing in these two harnesses takes real time to answer: the window
and the server are objects in the test's own process.

## 2. What changed

Two related harnesses, both simulated end to end:

1. `tests/test_mesh_net_walk.py` (the walking helper against a late window).
2. The world half of `tests/test_mesh_net_resume.py` (the drop/resume wait against a queued window).

Their `play()` ran `asyncio.run(main())`; it now runs `tests.net_sim_time.run(main())`: the same coroutine on an
event loop of its own whose clock is simulated. When every task is waiting on a timer, the clock moves to the next
timer instead of the process sleeping. `asyncio.sleep`, `asyncio.timeout` and `loop.time()` on that loop read the
one clock, so the helpers under test (`tests/net_walk.py`, `tests/net_resume.py`) run **unchanged**, on the code
path the real-window tests use.

- `tests/net_sim_time.py` (new, 77 lines): the loop, its clock, and its guards.
- The walking tests' stand-in server now ticks on a 20 ms timer (`await asyncio.sleep(TICK)`), not by polling the
  clock every 1 ms. On simulated time the poll made some ticks 21 ms apart (twenty additions of 0.001 are not
  always 0.02); the timer makes each tick exactly 20 ms after the last.
- `play(window, driver, phase)`: where the server's ticks fall between the helper's polls is now a parameter
  (real time left it to chance).

Nothing is patched: not `asyncio.sleep`, not a shared loop, not Python's clock. The simulated loop exists for one
`run` call; every other loop in the process is a normal one (a test holds this: a real 50 ms sleep after a
simulated run still takes 50 ms).

**For the reviewer to decide:** the brief says not to *globally monkeypatch* event-loop time. This is neither global
nor a patch, but it is a loop whose `time()` is simulated, and it pins one private attribute of asyncio's loop
(`_clock_resolution`, see section 6). The alternative was to pass a clock into `walk` and `drop_and_resume`; I did
not, because that changes the helpers the real-window acceptance tests depend on and takes the headless tests off
the code path those tests use.

### Left on real time, and why

| tests | why real time is the property |
|---|---|
| N6 reconnect tests (`scene_session`, 9 tests, 9.7 s) | a real `Server` ticking at 20 Hz, a real TCP connection whose close is held 300 ms, a real `Arena.run` |
| `test_mesh_net_world` socket tests | two real clients over loopback; a cancellation race reproduced with real `wait_for` |
| `test_mesh_net_downlink`, `test_mesh_net`, `test_mesh_net_scene` | real backpressure on a real stream; real process start |
| `test_mesh_net_gpu` (gpu lane) | real windows: independent acceptance evidence |
| `mesh_net/server.py` | production scheduling: not touched |

A simulated clock would run past a real peer's answer, so `net_sim_time` says so and these keep `asyncio.run`.

## 3. Event order is preserved

`real_vs_simulated_walks.json`: every walking test, run from the same test functions once on simulated time (twice,
to compare) and twice on real time.

- All 14 positive tests: **identical** on real and simulated time in server tick count, the commands in the order
  they took effect, every walk's legs (key, from, carry) and the final position. The two historical reproductions
  end at the failed runs' x 406.5 on both.
- Simulated runs are identical to each other in every recorded value.
- The two negative tests fail the same way; a simulated second holds 51 and 53 ticks where a real Windows second
  held 34 and 36.
- The new tick test (50 ticks in 1.01 s) cannot pass on real Windows time, which gave 33: the stand-in was never
  the 20 ms server it was written as there.

The same comparison made before the stand-in server's change to a timer (`real_vs_simulated_walks_polling_server.json`)
gave the same tick counts: 67, 69, 30, 32, 38, 40, 57, 59, 96, 54, 127, 75, 157, 115.

`test_events_come_in_the_order_and_at_the_times_real_time_gives_them` runs one set of sleeps, a poll, a timeout and a
cancellation on a real loop and on the simulated one and requires the same order.

## 4. The historical failures still reproduce, and faults are still caught

The reproductions are tests in the modules and pass on simulated time:
`test_the_old_driver_reproduces_both_failures` (Extended 43008772085 and 43016671504: y below the gap, x 406.5) and
`test_the_old_wait_takes_the_pre_drop_reply` (Extended 43049464084: the pre-drop entity returned, another drawn).

Faults put into the helpers, run against the unchanged baseline on real time and against this branch on simulated
time (`faults_baseline_real_time.json`, `faults_branch_helpers.json`):

| fault in the helper | baseline, real time | branch, simulated time |
|---|---|---|
| walk decides while the avatar still moves (the old driver's fault) | 5 fail | the same 5, + 4 new |
| walk lets go without allowing for the last leg's carry | 6 fail | the same 6, + 3 new |
| walk never walks back after an overshoot | 6 fail | the same 6, + 3 new |
| walk settles anywhere | 14 fail | the same 14, + 3 new |
| walk takes a timed-out wait as reached | 2 fail | the same 2 |
| walk gives up only after 1000 legs | **passes** | 1 fails (new test) |
| resume sends R without waiting for the old session to close | 2 fail | the same 2 |
| resume takes the pre-drop reply as the resumed session (N7's fault) | 4 fail | the same 4, + 1 new |
| resume does not compare the window's entity with the server's | **passes** | 1 fails (new case) |
| resume does not check the room resumed into | 1 fails | the same 1 |
| resume does not compare the window's room with the server's | 1 fails | the same 1 |
| resume does not look at the restored state | 1 fails | the same 1 |
| resume takes a timed-out wait as reached | 4 fail | the same 4, + 1 new |

Every fault the baseline caught fails the same tests here; the two it missed are now caught.

Faults put into the stand-ins and the clock (`faults_branch_standins.json`):

| fault | caught by |
|---|---|
| a release takes effect one tick early | key-timing test (2 delays), order test |
| a release takes effect one tick late | key-timing test (3 delays), order test |
| a press takes effect one tick late | key-timing test (3 delays), order test |
| commands due in one tick handled last first | order test |
| every tenth server tick skipped | key-timing test, tick test, a negative test |
| every tenth server tick run twice | key-timing test, tick test |
| the server ticks every 40 ms | tick test |
| the server never ticks | 20 tests fail; none hangs |
| the resume window's old session closes at once (no race left) | `test_the_old_wait_takes_the_pre_drop_reply` |
| the resume window handles a key as its command arrives (no frame queue) | 9 tests fail; none hangs (the real-time guard ends each) |
| the clock calls a timer due 15.6 ms early (a real Windows loop's rule) | 2 clock tests |
| the clock's waits run twice as long | 3 clock tests, tick test |
| simulated time never moves | 6 clock tests fail on the real-time guard |
| a wait nothing can end is waited on | its test |
| no real-time limit | its test never ends (stopped from outside after 90 s) |

## 5. New tests

`tests/test_mesh_net_sim_time.py` (8): order and exact times against a real loop; a 5 ms timer not woken by a 1 ms
one; a timeout is simulated time and still fails the wait; results and exceptions come back; no task or loop left,
and real loops keep real time; and the three guards (a wait nothing can end fails at once; an endless poll fails on
simulated time; a loop that never waits fails on real time).

`tests/test_mesh_net_walk.py` (+9): a key takes effect exactly `late` ticks after its command (3 delays); commands
sent in one tick take effect in order; the server ticks once every 20 ms of simulated time; walk fails when the
server never ticks; walk gives up at its limit of legs; walk gets through the gap at every delay at five phases of
tick against poll, in both rooms (30 walks).

`tests/test_mesh_net_resume.py` (+1): a window that reports an avatar the server did not give it.

## 6. Guards

- A wait nothing can end (no timer, nothing ready) raises `SimulationStuck` at once.
- A run past `real_limit` (30 s) of **real** time raises `SimulationStuck`: read from `time.perf_counter()`, not
  the simulated clock, so a loop that never waits is still ended.
- A run past `simulated_limit` (600 s) of simulated time raises `SimulationStuck`.
- The helpers' own `asyncio.timeout` still bounds each wait (in simulated seconds), with the same messages.

`_clock_resolution`: asyncio calls a timer due when the clock is within this of it. The real value is the
platform's (15.6 ms on Windows, 1 ns on Linux), which on Windows would end a 5 ms sleep with the first 1 ms one.
The loop sets it to 1 ns on both. It is a private attribute; `test_a_timer_fires_at_its_own_time_not_at_an_earlier_timers`
fails if a Python version stops honouring it (shown by the fault above).

After every test of the walking, reconnect, clock, downlink, net, world and scene modules: no event loop open, no
task unfinished, no socket open, and no child process at the end (`leftovers_branch.json`; the baseline is the
same, `leftovers_baseline.json`).

## 7. Before and after

Same selection plus the new module, same machine, three runs each (`baseline_local_3_runs.txt`, `branch_local_3_runs.txt`):

| | before | after |
|---|---|---|
| `test_mesh_net_walk` | 35.25 s (16 tests) | **3.12 s** (25 tests) |
| `test_mesh_net_resume` | 17.03 s (18 tests) | **11.40 s** (19 tests; 9.7 s of it the real N6 tests) |
| `test_mesh_net_sim_time` | | 1.03 s (8 tests) |
| every headless networking module | 112.26 s (200 tests) | **74.84 s** (218 tests) |
| the pytest run of them, wall | 124.9 to 128.9 s | 88.5 to 88.8 s |

- Simulated ticks: the 14 positive original walking tests take the same 1,016 (identical per test); the two
  negative ones 104, where a real Windows second gave 71; the nine new walking tests add 1,531.
- Real waits removed: 4,374 sleeps in the walking tests and 496 in the simulated reconnect tests no longer wait
  (`split_branch.json`); 6 one-second timeouts expire in simulated time.
- New overhead: one event loop per `play` (about 1 ms); the walking tests' remaining time is building their rooms.

CI figures are in the pull request (the Windows shard's JUnit gives per-test times; Linux gives only the job's).

## 8. CI history

The first CI run of this branch (43830807804, head `ce7df836`) **failed** on attempt 1, in one of the new tests:
`test_a_loop_that_never_waits_fails_on_real_time` required the real-time guard to take at least its 0.2 s and
measured 0.1965 s. The guard read `time.monotonic()`, which Python 3.11 on Windows reads from a counter that moves
in 15.6 ms steps (`GetTickCount64`; Python 3.13, used locally, reads the fine counter), so a limit set from it
could end up to one step early. Extended 43830804815 on that head passed on attempt 1. Nothing was rerun.

Corrected in a second commit: the guard reads `time.perf_counter()` (fine on every version). The two other
real-time assertions in the new tests were made independent of timer steps and of a stalled runner at the same
time: the comparison with a real loop sets every timer at the start (a stall then cannot reorder them), and the
"real loops keep real time" check sleeps 200 ms and requires 150.

## 9. Limits

- Windows shard 2 holds both changed modules; in the reference run shard 1 was the longer Windows shard and the
  Linux job the longest of the three. A shorter shard 2 does not shorten the workflow by itself.
- Linux has no per-test record at the baseline. Its timers are finer, so its walking tests were probably nearer
  25 s than 35 s; that is an estimate, not a measurement.
- The N6 reconnect tests' five one-second timeouts stay: they prove the wait fails closed against a real
  server.
- Simulated time fixes one interleaving per phase; the phase sweep covers five. Real time covered an unknown,
  changing set.
- One private asyncio attribute is relied on (section 6), under a test.
