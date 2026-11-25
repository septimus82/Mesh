# M4 — responsive server-authoritative online combat: measurements and design (M4-0)

> **Status:** design approved by the owner (2026-11-24, OD1–OD11 below); being implemented in stages.
> M4-0 (#609) added this document, a headless measurement tool (`tooling/m4_latency_probe.py`) and one test of the
> tool's link model and statistics. M4-1 (#610) and M4-2 (#611: protocol v3 and attack presentation) are merged.
> M4-3 (own-movement prediction and the server's input queue, #613) is merged; its follow-ups (round 4: tests, the
> probe's flag order, the drain's fork guard) are merged (#615): §4 M4-3 "As implemented". Its input queue is the owner's
> choice after playing; "drain" is the provisional default (owner decision, 2026-11-24). M4-4 (server-authoritative
> moving enemies through one shared `FloorRoute` model, OD7) is merged (#616), with the measurements M4-5 depends on:
> §4 M4-4 "As implemented". The M4-6 groundwork (a TCP delay proxy, a hidden-window capture harness and one trial;
> two #616 review follow-ups) is merged (#617): §4 M4-6 "groundwork as implemented". M4-5 (bounded server-side lag
> compensation, approved by the owner on 2026-11-25) is merged (#626): §4 M4-5 "As implemented", and §6 for its
> security and fairness limitation. M4-6's final evidence (a visible swing, the playable demo and its launch
> instructions, the rendered set) is in review: §4 M4-6 "Final evidence as implemented". **M4 stops there, at the
> agreed checkpoint:** `docs/plans/m4_checkpoint.md`.
>
> **Authority:** owner decision D7 (2026-11-23, `docs/plans/hd2d_online_investigation.md` §6, §7.4): M4 is approved
> to begin now that M3 has passed. Focus: responsive server-authoritative online combat, including simulated latency.
> M5 is planning only. M6 is not authorized.
>
> **Citations** are `file:line` at `a81b511f`. *(inferred)* marks reasoning that was not measured.
>
> **Revision 2** (independent review of #609):
> - seed spread is now measured over 3 seeds × 24 sessions and reported as ranges;
> - retransmission is modelled as RTT + 200 ms;
> - the server's input handling (OD11) and N7, resume and transfer semantics are specified;
> - the server-stall disconnect is added;
> - citations are fixed;
> - every OD carries a recommendation.
>
> **Revision 3** (owner approval, 2026-11-24, and the reviewer's notes on revision 2):
> - **The owner approved OD1–OD11 as recommended** (§5), with these settings:
>   - OD1: responsive movement and swing feedback through 100 ms RTT with ±10 ms jitter and 1% loss; median hit
>     confirmation at most RTT + 75 ms; playable and server-authoritative at 200 ms; actual limitations reported;
>   - OD2: protocol v3, explicit v2 refusal, no downgrade;
>   - OD3: local movement prediction and reconciliation through the shared movement implementation (M4-3);
>   - OD4: immediate local swing animation, sound and feedback; hits, damage, HP and death stay server-confirmed;
>   - OD5: conditional, PvE-only lag compensation, 300 ms cap, never rewinding the attacker (M4-5);
>   - OD6: stay at 20 Hz;
>   - OD7: server-authoritative moving enemies in M4-4 through a shared graphics-free model, with the enemy position
>     fields in protocol v3 now (static until M4-4);
>   - OD8: same-seed virtual-clock comparisons, at least 3 seeds (7, 8, 9) × 24 sessions; p95 and wall-clock timings
>     report-only;
>   - OD9: TCP stays;
>   - OD10: the server matches single-player's persistent hitbox timing without changing single-player behaviour;
>   - OD11: a bounded input queue, one consumed input per server tick, starting depth 2, proper input acks (the queue
>     itself is M4-3; v3 carries the per-row `ack` and the intended tick now).
> - **The owner's safeguards:** input correctness is mandatory. Immediate local presentation is kept distinct from
>   server-confirmed outcomes. Targets are goals, never permission to hide failures. No unrelated redesign, no UDP,
>   no PvP, no M5 work.
> - **The reviewer's notes:**
>   - (i) OD2, OD7 and OD11 were decided together, so v3 carries the enemy placement and the input fields at once;
>   - (ii) the intended tick never lets the server apply more than one input per tick;
>   - (iii) when the queue is full and an input is dropped, any pending attack is kept;
>   - (iv) the seed spread is worded as about 10 ms and about 4 points (§2.1, §4).
> - M4-1 is marked merged (#610).
> - **Owner decision, 2026-11-24, on the 600 ms attack-claim window (#611), quoted verbatim:**
>
>   > "600 ms APPROVED, with the following conditions. 1. This approval applies to the current cooperative PvE
>   > prototype. It is not blanket approval for competitive PvP or public deployment. 2. Keep OD5's separate 300 ms
>   > maximum for historical hit validation unchanged. 3. The server must remain authoritative over attack execution,
>   > hit detection, damage, death and cooldown enforcement. 4. Never use the client's claimed attack tick to authorize
>   > a hit against historical positions. Hits remain evaluated against current server-authoritative geometry and
>   > supporting floors until M4-5 is separately approved. 5. Preserve and verify the bounded attack-rate guarantees.
>   > Record the dishonest-client burst advantage, including short-cooldown attacks, as an explicit security limitation
>   > requiring attention before public deployment. 6. Server stalls, retransmissions, disconnects and room transfers
>   > must not cause persistent timing corruption or duplicate attacks. 7. Count and report stale or refused attacks. Do
>   > not conceal them, weaken acceptance tests or silently change the agreed latency targets."
>
>   The approval covers the co-op PvE prototype only. See §4 M4-2 "As implemented" and §6
>   "Security limitation: before public deployment".
> - The review of M4-2 (#611, rounds 2 and 3) is recorded in §4 M4-2 "As implemented": the attack cooldown is judged
>   on the intended tick, the client's reckoning of the tick recovers from a server stall, the true lying-client bound,
>   and no pressed action is replaced or lost on its way.

## 0. Summary

Numbers are 20 Hz, ranges over seeds 7/8/9 (§2.1).

- **Today, everything a player sees of their own actions waits a full round trip plus up to two 50 ms quantisation
  waits.** At 100 ms RTT, the median local avatar starts moving 157–168 ms after the key press, and the hit shows after
  156–165 ms. At 200 ms RTT, both take about 261–265 ms. Even at 0 ms the median is 54–61 ms. The p95 figures are
  dominated by TCP retransmissions (§2.2).
- **A swing is never shown.** No attack state is on the wire, and the client keeps only the Animator. The attacker
  sees nothing until the enemy's HP changes. That HP appears in the window caption, and the sprite hides at 0 HP
  (§1.3).
- **Hit fairness is dominated by the attacker's own motion, not the target's.** Today's enemies never move online.
  On a scripted moving target, an *ideal* rewind bound removes the target's share of the error. It removes none of the
  attacker's share: 21–22% of samples disagree at 100 ms when walking up to an enemy and away, and 56–59% on the HD-2D
  stairs case. Only own-avatar prediction addresses that (§2.3).
- **A stale view can make a cross-floor attack look possible.** On stairs near the 1.5 m `same_level` reach, 27–29% of
  sampled presses at 100 ms disagree *because the floor rule's answer differs*. That is 15–16% even at 0 ms RTT, from
  tick quantisation. The server is always right; the player just can't tell (§2.4).
- **Players get disconnected under ordinary conditions.** The server ends any session that delivers more than 8
  inputs within one tick (`mesh_net/server.py:77-84`).
  - In the model, one lost segment at 200 ms RTT delivers 9 inputs at once.
  - On loopback, a server event-loop stall of 600 ms or 1000 ms disconnected a 20 Hz client; 200, 300 and 450 ms did
    not (§2.5).
  - The fix, M4-1, was done separately as a defect fix (#610, merged): a token bucket (`InputBudget`) replaced the
    per-tick limit.
- **Recommendation (§4):** stay server-authoritative on TCP, and stage the work as follows:
  - **M4-1:** the burst defect fix, merged (#610).
  - **M4-2:** one protocol v3 that carries everything M4-3 and M4-5 need, plus local swing presentation.
  - **M4-3:** own-avatar prediction through the one shared floor solver, with the server reading inputs one per tick
    (OD11).
  - **M4-4:** server-side enemy movement through a shared mover model (OD7).
  - **M4-5:** lag compensation, only if measured necessary.
  - **M4-6:** two-window rendered evidence under injected latency.

## 1. Current architecture

### 1.1 What is authoritative where

| Concern | Where | Evidence |
|---|---|---|
| Position, elevation, floor, facing | Server only. An input is a direction plus an optional action; clients never send position. | `mesh_net/protocol.py:17-21`, `mesh_net/scene_room.py:694-706` |
| How inputs are used | The last input wins. `input()` overwrites the held direction when `seq` is newer, and latches only the first pending action (`scene_room.py:547-556`). Each tick takes **one** step with the held direction (`:569-572`). A direction is held up to `HZ // 4` = 5 ticks after the last input (`:569`). Several inputs in one tick collapse into one step. | as cited |
| Movement | `SceneRoom.step` at a fixed `HZ = 20`. HD-2D rooms use `World.move`, the one floor solver. | `protocol.py:35`, `scene_room.py:565-577` |
| Attack | One instant check on the tick the input is read: a 4-way-facing AABB at `range` ahead with side `hitbox_size`, plus `same_level`. | `scene_room.py:582-584`, `:629-641`, `:74` |
| Enemy HP, death, loot | Server. The enemy is a dataclass with no movement (`scene_room.py:384-391`). Its snapshot row is `[id, hp]`, with no position (`:656`). | as cited |
| Enemy movement | **None.** The server moves no enemy or NPC. The client strips every behaviour except the Animator, so an authored mover such as the floors demo's warden (`FloorRoute`) walks in single-player and stands still online. | `scene_client.py:23`, `:72-73`; `tooling/hd2d_floors_demo.py:87-93` |
| Validation of server state | Client: exact frame shape, plus floor and elevation against its own collision world. | `scene_room.py:714-770` |

### 1.2 Flow and where latency enters

There are three client loops, all with the same shape:
- `Arena` (2D demo): `mesh_net/demo.py:101-136`;
- `SceneArena` (N6), which reuses `Arena.session` and draws at `scene_client.py:181-192`;
- `WorldArena` (N7): its own send loop at `mesh_net/world_client.py:189-204` and draw at `:280-299`.

1. **Key press → send.**
   - Each loop sends its current intent, then drains, then sleeps 1/HZ (`demo.py:108-113`,
     `world_client.py:189-204`). The real period is therefore 1/HZ plus send and drain time.
   - **The client's send clock drifts against the server's tick** *(inferred from the code)*.
   - An action waits 0–50 ms for the next send and is latched once (`demo.py:74-76`).
   - N7 inputs also carry `room`, and the world drops an input naming another room. That happens to every input in
     flight during a transfer (`world.py:359-373`).
2. **Uplink.** The connection is TCP on 127.0.0.1 today (`server.py:33`). Delivery is in order, so a lost segment
   holds up everything behind it.
3. **Server.** The input is used on the next tick, a further 0–50 ms (`server.py:103-111`). Then a full snapshot goes
   to every peer (`server.py:113-118`; N7: `world.py:585-596`).
4. **Downlink.** The same TCP behaviour applies.
5. **Display.**
   - The local avatar is drawn at the latest snapshot (`scene_client.py:188-190`, `world_client.py:293-297`).
   - Everyone else is drawn by `Playback` two ticks behind, and its cursor never goes backwards (`playback.py:27-47`,
     cursor at `:33`).
   - Positions are set directly, with no smoothing (`scene_client.py:109-119`). The window runs at 60 fps
     (`demo.py:186`).

Expected first-visible delay ≈ U(0,50) + RTT/2 + U(0,50) + RTT/2 + U(0,16.7) ms, which is about 58 ms + RTT on
average. N5.1 chose "latest snapshot for the local avatar, no prediction" on loopback
(`docs/networking/n5_1_responsiveness.md`), and deferred prediction "against a measured play-feel budget". This
document is that measurement.

### 1.3 Findings beyond latency

- **No swing on the wire.**
  - Single-player `Combat.attack` plays `attack_anim`, a sound and rumble, then spawns a hitbox
    (`engine/behaviours/combat.py:126-158`).
  - Online, none of this exists: the snapshot has no attack state and the client keeps only the Animator.
  - A non-lethal hit shows only in the caption (`scene_client.py:175-179`). A lethal one hides the sprite (`:129-130`).
- **Combat timing parity gap (pre-existing; OD10).** Single-player's hitbox:
  - is a separate sprite that **stays where it spawned**: `range` ahead along the velocity angle, or `angle` when
    standing (`combat.py:186-196`);
  - lives 0.2 s (`:217`);
  - checks overlap **every frame**, hitting **each target once** (`hitbox.py:95-131`, `_hit_list`);
  - asks `same_level` against the **attacker's current elevation** each frame (`mesh_attacker`, `hitbox.py:122-125`).

  The server checks once, on one tick, in 4 facings. M3-4 unified the *level* rule, not the hitbox lifetime.
- **The local avatar visibly steps at 20 Hz.** It is drawn at the latest snapshot, so about 68% of 60 fps frames show
  no movement while walking (measured, §2.2), even at 0 ms.
- **The input-rate limit collides with stalls of any origin** (§2.5).

## 2. Measurements

### 2.1 Method

`py -3.13 tooling/m4_latency_probe.py [--seeds 7 8 9] [--sessions 24] [--hz HZ] [--rto 200] [--json OUT]`, with
`PYTHONPATH` set to the worktree. A full run (3 seeds × 24 sessions) takes about 5–10 minutes.

- **Headless and deterministic.** There are no sockets, windows or wall clock.
  - The real `SceneRoom` (step, input, `_attack`, `same_level`) and the client's real display rules (latest snapshot
    for the local avatar, `Playback` for others) run on one virtual millisecond clock.
  - Each session keeps one seeded phase between the client's send clock and the server's tick. Results pool
    **24 sessions** per profile, and the run repeats for **3 seeds**. Every number is reported as
    [lowest, highest] over the seeds.
- **Seed spread** (20 Hz, 24 sessions):
  - medians within about 10 ms of each other;
  - hit and fairness rates within about 4 percentage points;
  - **p95 within 5–87 ms**: at 1% loss a retransmission is a rare event, so the tail moves with the seed.
  - Revision 1 claimed "about 5 ms and 2 points" from 6 sessions. That was wrong: at 6 sessions the reviewer's seed-8
    run differed by up to 18 ms on medians, 94 ms on p95 and 6.2 points on rates.
  - p95 figures are therefore descriptive only, and every acceptance criterion below compares the same seeds before and
    after, with a margin larger than the measured spread (§4).
- **Link model (TCP).** Each message has a one-way delay of RTT/2 ± uniform jitter.
  - A loss arrives **RTT + 200 ms** later: Linux's RTO is SRTT + 4 RTTVAR, at least 200 ms. This is a parameter,
    `--rto`.
  - Everything behind a late message waits for it (in order). Nothing is dropped.
  - `mesh_net/study.py` models application-level *drops* (`study.py:33-34`), which TCP never produces. That is why
    this tool was added rather than reused.
- **Profiles.**

  | RTT | Jitter, one-way | Loss |
  |---|---|---|
  | 0 ms | none | 0 |
  | 0 ms | ±10 ms | 1% |
  | 50 ms | ±10 ms | 1% |
  | 100 ms | ±10 ms | 1% |
  | 200 ms | ±10 ms | 1% |

- **Rooms.**
  - The packaged co-op room (2D), with its gate opened (the tool's setup).
  - The floors demo crossing (HD-2D, `tooling/hd2d_floors_demo.py`), with the co-op bandit placed on the ground
    beside the west stairs. There, in-plane reach spans about 1.15–1.8 m up the stairs, and `same_level` refuses from
    1.5 m.
- **Moving target.** The authority never moves an enemy, so the tool walks the bandit back and forth through the
  hitbox and adds its position to the client's copy of each snapshot, shown through `Playback` as a peer is. This
  stands in for moving enemies replicated like peers *(inferred)*.
- **Fairness.** Every client frame is a hypothetical press.
  - *Seen:* `_attack` and `same_level` evaluated with the bodies where the screen showed them.
  - *Real:* the same evaluation on the authority's bodies, on the tick that press lands. The press rides the next
    input sent and is applied on the next tick after arrival.
  - *Ideal rewind bound:* the real attacker against the targets where the screen showed them. This is an upper bound
    on what lag compensation can achieve, **not** a measurement of an implementation.
- **Limits.**
  - This is a model, not a packet capture.
  - **The client's phase drift is not modelled.** Real send loops drift (§1.2); pooling many fixed phases stands in
    for it.
  - No OS scheduling, rendering or display scan-out is included. N5.1's real-window loopback median was 99.6 ms
    against this model's 54–61 ms.
  - The scripted motions in §2.3–§2.4 are deliberately adversarial.
  - Numbers are descriptive. The tool has no timing assertions.

### 2.2 Responsiveness today (20 Hz)

Times are p50 / p95 in ms, from key press to the first frame showing it. Each value is the range over the 3 seeds.

| RTT (jitter, loss) | Local avatar moves | A peer sees it move | Local avatar stops after release | Hit shows (HP drops) | Swing shows |
|---|---|---|---|---|---|
| 0 (none) | 54–61 / 91–96 | 112–119 / 145–150 | 4–11 / 41–46 | 53–58 / 87–96 | never |
| 0 (±10, 1%) | 66–71 / 132–155 | 118–125 / 166–183 | 15–22 / 94–129 | 63–72 / 116–203 | never |
| 50 (±10, 1%) | 107–114 / 219–272 | 154–160 / 232–286 | 57–62 / 144–159 | 106–114 / 203–258 | never |
| 100 (±10, 1%) | 157–168 / 331–352 | 203–212 / 359–380 | 105–114 / 242–263 | 156–165 / 338–383 | never |
| 200 (±10, 1%) | 261–265 / 542–561 | 307–310 / 564–581 | 209–212 / 386–432 | 264–265 / 563–574 | never |

- **Stepping and bursts.** The local avatar moves on only about 30% of frames while walking, in 7.5 px steps. After a
  retransmission stall, buffered snapshots arrive together, and the avatar jumps up to 37.5–45 px in one frame.
- **No rubber-banding today.** There is no prediction, so there is nothing to correct.
- **Snapshot size** (from the tool):
  - 2D co-op: 260 B for 1 player, 285 B for 2, 435 B for 8;
  - HD-2D crossing: 242, 273 and 459 B.

  At 20 Hz, 8 players is about 9 KB/s down per client.

### 2.3 Hit fairness

Each cell shows *looked like a hit but missed* / *any disagreement*, as a percentage of the matching sampled presses,
ranged over the 3 seeds.

| Scenario | 0 (none) | 0 (±10, 1%) | 50 | 100 | 200 | Ideal rewind bound, any RTT |
|---|---|---|---|---|---|---|
| Moving target 70 px/s, still attacker | 10.0–10.3 / 8.5–8.7 | 10.8–11.6 / 9.2–9.5 | 14.2–15.2 / 11.5–12.5 | 17.7–19.4 / 14.5–15.4 | 26.8–29.9 / 21.5–23.0 | 0 |
| Moving target 150 px/s, still attacker | 22.2–22.7 / 20.0–20.5 | 23.8–25.3 / 21.6–23.0 | 31.4–32.3 / 28.3–29.3 | 38.9–40.8 / 35.0–36.8 | 56.5–57.2 / 50.7–51.7 | 0 |
| Attacker walks up to a still enemy, waits about 0.2 s, walks away (today's case) | 23.5–24.7 / 10.4–10.9 | 30.4–32.4 / 11.6–12.5 | 48.5–52.0 / 16.2–19.3 | 62.5–64.9 / 20.9–22.3 | 83.7–84.8 / 27.6–31.7 | no change |
| HD-2D: strafing the stairs at a ground enemy | 29.2–30.6 / 29.3–30.7 | 35.7–37.9 / 33.5–35.7 | 51.5–54.5 / 46.6–46.9 | 68.9–72.9 / 55.6–58.6 | 93.5–95.8 / 66.9–67.7 | no change |

- **The ideal bound clears target motion only.** It removes the moving-target error by construction, because the
  attacker there is still and its own pose is exact.
- **It clears none of the attacker's own motion.** The screen shows the attacker where the server had it RTT/2 ago.
  The attack lands RTT/2 plus up to two quantisation waits later, where the attacker has since moved or turned. With
  ideal own-movement prediction, the screen and the landing tick agree by construction *(inferred)*.
- **The quantisation floor (0 ms row) is a tick-rate lever** (`--hz`):

  | | 20 Hz | 30 Hz | 60 Hz |
  |---|---|---|---|
  | Walk-away disagreement, 0 ms | 10.4–10.9% | 6.6–7.1% | 2.4% |
  | Stairs disagreement, 0 ms | 29–31% | 21–22% | 7.7% |
  | Median local first move, 0 ms | 54–61 ms | 39–42 ms | 15–17 ms |

### 2.4 HD-2D floors and latency

Share of all sampled stairs presses that disagree *because `same_level` differs* between the shown pose and the
landing pose (shown as same level and in reach, but refused, or the reverse):

| 0 (none) | 0 (±10, 1%) | 50 ms | 100 ms | 200 ms |
|---|---|---|---|---|
| 14.8–15.5% | 16.6–17.8% | 22.7–23.1% | 27.4–29.0% | 33.1–33.4% |

- **Yes, a stale view can make a cross-floor attack look possible**, and the reverse.
  - **Where:** near `BODY` on stairs and slopes (`engine/hd2d/world.py:56`, `:165-205`), where elevation changes with
    planar motion.
  - **Not between a deck and the ground.** That gap is 2 m and constant, so latency never changes the answer.
  - **The server is always authoritative.** `_level` runs on the authority's bodies (`scene_room.py:589-596`, `:636`).
    This is a perception and fairness problem, not an exploit.
  - **The client asks nothing.** It never evaluates `same_level` itself, so the player has no cue.
- **Interpolated targets don't help.** A target shown through `Playback` carries an interpolated elevation and the
  nearer state's floor (`playback.py:44-45`). A moving enemy on stairs would add the same error on the target's side
  *(inferred)*.

### 2.5 Smoothness, enemies and the input-rate cliff

- **Enemies today.**
  - They never move online, so they cannot snap or rubber-band.
  - Their HP changes in a step on the next snapshot.
  - The single-player warden's `FloorRoute` walk is simply absent.
- **A moving target shown through `Playback`, the stand-in for replicated enemies.**
  - Under 1% loss it freezes on 2.4–7.1% of frames, for up to one retransmission (250–283 ms at 100 ms RTT, 350–383 ms
    at 200 ms).
  - Then it jumps: 50–133 frames per 264 s moved more than twice its speed.
  - Spurious reversals: 0–1 per 264 s. The cursor is monotonic; the 1 is within the ±1 rounding of the target's own
    turn count.
  - At 0 ms it is perfectly smooth.
- **The input-rate limit.** `Server._handle` ends a session that delivers more than 8 frames within one tick
  (`server.py:77-84`). N7 has the same rule (`server.py:163-170`). Three ways to trigger it:
  - **Network stalls (model).** Buffered inputs arrive together after a retransmission. The most in one tick, by RTT,
    at 1% loss:

    | Tick rate | 0 ms | 50 ms | 100 ms | 200 ms |
    |---|---|---|---|---|
    | 20 Hz | 6 | 7 | 8 | **9** |
    | 30 Hz | 8–9 | 9 | 9 | 9 |
    | 60 Hz | 9 | 9 | 9 | 9 |

    At 200 ms RTT, a single loss disconnects the player.
  - **Bursts (loopback, real `Server`).** 9 back-to-back inputs disconnected the client; 8 did not.
  - **Server stalls (loopback, no network loss).** The reviewer's `stall.py`, a 20 Hz client against a real `Server`
    whose event loop blocks, which I reproduced: stalls of 200, 300 and 450 ms stayed connected; 600 ms and 1000 ms
    disconnected. A GC pause, disk flush or scheduler hiccup can therefore kick players today.

  Raising HZ without changing this rule would make it worse.

## 3. Options

Each option keeps the owner's invariants:
- the server alone decides position, elevation, floor, hits, HP and loot;
- one floor solver (`World.move`) and one `same_level` rule (M1-A, M3-4);
- no duplicated rule logic;
- single-player replays unchanged.

### (a) Stay fully authoritative; tune

- **Changes.**
  - Send an input frame immediately on a key change or action, in addition to the heartbeat. This removes the 0–50 ms
    send wait.
  - Make each send loop **deadline-based**, like the server's clock (`server.py:103-110`), instead of
    "send, drain, sleep" (§1.2).
  - Replace the per-tick "more than 8" rule with a bounded token bucket. This is M4-1.
  - Set `TCP_NODELAY` explicitly *(asyncio sets it on new connections; verify)*.
  - Optionally a higher tick rate, or an adaptive interpolation delay for peers.
  - Optionally, extrapolate the local avatar by one tick, to remove the 20 Hz stepping.
- **Protocol.** Send-on-press and the bucket need no wire change. HZ is an implicit constant on both sides
  (`Playback`, input expiry). Changing it needs HZ in the welcome frame (v3).
- **Parity.** None affected. A higher HZ reduces the tick quantisation already noted as risk R3 (plan §7.3).
- **Cheating.** None. The bucket stays bounded, because inputs are cheap to forge in quantity.
- **Complexity and risk.** Low. The tick rate costs server CPU and 1.5–3× bandwidth (under 30 KB/s for 8 players at
  60 Hz).
- **Effect.**
  - About −25 ms p50 from send-on-press *(inferred from the U(0,50) term)*.
  - 30 Hz: −15 to −19 ms p50 at 0 ms, and about −30% on the quantisation floor (measured).
  - **It cannot remove the round trip.**
- **Tests.** Probe-based same-seed comparisons; burst and server-stall tests against the real `Server` and
  `WorldServer`.

### (b) Client-side prediction and reconciliation, own movement only

- **Changes.**
  - The client already builds the room's `SceneRoom` from its own files, with the server's collision world
    (`scene_client.py:155`; N7 builds `World(root)`, `world_client.py:47`).
  - It applies each input to its own avatar immediately, through **the same per-body step** the authority uses.
    `SceneRoom.step`'s per-player body (movement, bounds, input hold) is extracted into one function that both sides
    call. This keeps the single floor solver and adds no second movement implementation.
  - It keeps unacknowledged inputs. On each snapshot it resets to the server's row and replays the inputs the server
    hasn't consumed.
  - **HD-2D corrections:** elevation and floor snap to the server's row, and are re-derived by replaying through
    `World.move`. Only the in-plane x/y error is smoothed over a few frames. A smoothed elevation could show a body
    between floors, which `check_levels` would never accept from the wire.
  - One predictor object serves `SceneArena` and `WorldArena`, which today have separate send loops and draws (§1.2).
- **What makes prediction exact (OD11).** Today the server is last-input-wins (§1.1). The number of steps an input
  produces therefore depends on when it arrives relative to the tick: 0, 1 or several, collapsing bursts, plus the
  5-tick hold. The client's send clock also drifts. Hence:
  - **OD11(a):** a bounded per-player input queue that the server reads **one per tick**. Inputs are tagged by `seq`
    (and the client's intended tick). It is sized together with M4-1's bucket. When the queue is empty, the server holds
    the last input for the existing 5 ticks.
    - Every consumed input is exactly one step, so the client predicts one step per input it sends.
    - Corrections happen only when the queue under- or overflows (loss, stall), or when solids change.
    - **Recommended depth: 2** (one tick of jitter absorbed, about +50 ms worst-case queueing; the reviewer recommends
      2–3).
  - **OD11(b):** keep last-input-wins and predict by time. Routine one-step corrections (7.5 px) happen whenever an
    input lands in a different tick than predicted, and smoothing hides them.
- **Protocol (v3).** Each player row gains the `seq` of the input the server **consumed** this tick (the
  acknowledgement): `[entity, x, y, facing, elevation, floor, ack]`. That keeps one shared encoding per room
  (`server.py:113`, `:205-218`).
- **Resume, transfer and enter (N6/N7).**
  - **Today's numbering.** A leave resets the server-side `seq` to 0 (`scene_room.py:541-545`). That covers
    disconnects (`server.py:91`, `world.py:326`) and transfers (`world.py:546-559`, the leave at `:550`).
    - N6 clients start a new `Client` at `seq` 0 on resume (`client.py:22`).
    - The N7 client keeps one counter for the window's life (`world_client.py:68`).
    - Either way, client numbers stay above the server's, so input is accepted.
  - **The ack's meaning.** The highest `seq` this room instance has consumed **since this player joined it**; 0 means
    none.
  - **Clearing.** The predictor clears its unacknowledged buffer and restarts from the server's row on `welcome`
    (resume included), on every N7 `enter` (`world_client.py:143-150`), and when its own avatar is missing from a
    state.
  - **Transfers.** Inputs in flight across a transfer are dropped by the world (`world.py:365-369`). The client must
    never replay them into the new room.
- **Parity.** The same code path, so no divergence by construction, apart from:
  - solids changing between prediction and authority: a gate opening, an enemy dying;
  - float drift across platforms.
  Both are corrected on the next snapshot. Players don't block each other for movement (`scene_room.py:560-563`).
- **Cheating.** No new authority. Prediction is presentation only. The client never sends position, elevation or
  floor, and the server still validates `check_levels`.
- **Complexity and risk.** Medium to high.
  - Visible snaps when a prediction is wrong.
  - M3 acceptance currently reads the local avatar at the server row. At loopback the two converge *(inferred)*, but
    tests must allow convergence.
- **Effect.** With OD11(a), the local avatar moves on the next frame, at most 16.7 ms, at any RTT *(inferred)*.
  Fairness for the attacker-motion scenarios moves towards 0 (§2.3) *(inferred)*.
- **Tests.**
  - Virtual-clock prediction vs authority: zero corrections with no loss, static solids and OD11(a).
  - Bounded corrections under jitter and loss.
  - Stairs: the predicted elevation and floor equal the authority's after settle.
  - Buffers cleared on resume, transfer and enter.
  - A parity test that both sides call the one step function.

### (c) Local attack presentation; server-confirmed hits

- **Changes.**
  - On a press, the client immediately plays the attack animation through the same
    `request_animation_state(..., attack_anim)` path Combat uses (`combat.py:136-137`), plus sound and rumble.
  - It mirrors the cooldown locally, from the template (`scene_room.py:430`), so it never shows a swing the server
    will refuse. One shared seconds-to-ticks conversion is needed.
  - Hit flash, HP and death show **only** on server confirmation.
  - Peers see others' swings.
- **Protocol (v3).** Counters, not events, so a missed snapshot is never ambiguous:
  - a per-player `attack_seq`;
  - a per-enemy `hit_seq` in `enemies` rows.

  Counters are **scoped to the room instance**, and the client takes a new baseline at `welcome` and `enter`
  (§3(b)).
- **Parity.** Reuses single-player's own presentation parameters. No rule logic on the client.
- **Cheating.** None; presentation only.
- **Complexity and risk.** Low to medium. A swing without a hit is normal and must read as a miss, not lag.
- **Effect.** Swing feedback within one frame at any RTT; the hit still arrives about RTT + 50 ms later *(inferred)*.
- **Tests.** Virtual-clock tests: swing on the next frame; flash only after the counter changes; no swing during
  cooldown; a cross-floor refusal shows a swing and no flash; counters take a new baseline across a transfer.

### (d) Server-side lag compensation (rewind) for hit detection

- **Changes.**
  - The authority keeps a short per-tick history of target bodies (position, elevation, collider).
  - An attack input carries the client's interpolation time (the `Playback` cursor, a tick with a fraction).
  - The server evaluates `_attack` with the **attacker at its current pose** and **targets rewound** to that time,
    clamped to the cap. `same_level` uses the rewound target's elevation.
- **Protocol (v3).** An optional `view_tick` on attack inputs.
- **Cap.** It follows OD1. The view lags about RTT/2 + 100 ms interpolation + one tick, about 250 ms at 200 ms RTT, so
  a cap of about **300 ms (6 ticks at 20 Hz)** covers the envelope.
- **Parity.** Single-player has no latency. Rewind evaluates the same `_attack` and `same_level` on historic bodies,
  with no new rule *(design constraint)*.
- **Cheating and fairness.** A client can claim any view time within the cap. In PvE the victims are AI. PvP is out of
  scope.
- **Complexity and risk.** Medium. It is only useful once enemies move.
- **Effect.** The ideal bound is 0% moving-target disagreement (§2.3); a real implementation keeps small time
  quantisation residuals *(inferred)*. **No effect** on the dominant attacker-motion error.
- **Tests.** Probe scenario on the real mover; cap boundary; clamp beyond the cap; a cross-floor rewound target is
  refused.

### (e) Combinations

The measurements rank the levers.

| Lever | Effect | Needs |
|---|---|---|
| (b) own-movement prediction | Fixes the felt delay of movement and the dominant fairness error | The v3 ack, and OD11(a) to be exact |
| (c) local swing | Fixes "my attack did nothing" | — |
| (a) burst fix and send-on-press | Cheap and needed regardless | — |
| (d) rewind | Matters only with moving enemies | Moving enemies (M4-4) |

## 4. Recommendation: (a) + (c) + (b), then moving enemies, then (d) if measured necessary

**Acceptance method for every stage (OD8).**
- Run the probe before and after the change with the **same seeds (at least 7, 8 and 9) and 24 sessions**.
- A criterion passes only if it holds **on every seed**, with a margin larger than the measured cross-seed spread of
  that metric (§2.1). For example, a median improvement must exceed 15 ms on each seed, against a spread of about
  10 ms (rates: about 4 points).
- p95 values and wall-clock timings are reported, never gated.

**M4-1 — input-burst defect fix (merged, #610):**
- A bounded token bucket in `Server` and `WorldServer` in place of "more than 8 frames per tick".
- **Acceptance:**
  - Bursts of 9–40 inputs after a simulated stall keep the session; sustained floods are still refused.
  - A **server event-loop stall test**: a 20 Hz client survives a 1000 ms stall (as in the reviewer's `stall.py`) on
    both servers.
  - All M3, N6/N7 resume and graphics-free tests green; replays 13/13.
  - Send-on-press and deadline-based send loops can join M4-1 or open M4-2. Acceptance: on every seed, the median
    local first move improves by more than 15 ms.

**M4-2 — protocol v3, all at once (no v4), plus attack presentation:**
- **What v3 carries:**
  - the player-row `ack` (for M4-3);
  - `attack_seq` per player and `hit_seq` per enemy;
  - `HZ` in `welcome`;
  - an optional `view_tick` on attack inputs (reserved, for M4-5);
  - the intended tick on inputs, if OD11(a);
  - **if OD7 is approved before M4-2**, enemy rows `[id, hp, hit_seq, x, y, elevation, floor]` (static until M4-4).
- **Refusal.** A v2 peer is refused explicitly by **both** `Server` (`server.py:62-66`) and `WorldServer`
  (`:150-156`), as D1 did. N7 `welcome`, `enter`, `room_state` and the N8 `character` frames (`world.py:658`) are all
  re-checked under v3.
- **Client.** A local swing (c) and a confirmed hit flash, in `SceneArena` and `WorldArena`.
- **Acceptance:**
  - v2 refused, in both directions and on both servers.
  - Malformed, stale and inconsistent v3 frames are refused whole.
  - Virtual-clock tests: swing within one frame on every seed and profile; flash only after confirmation; no swing in
    cooldown; a cross-floor refusal shows a swing and no flash; counters take a new baseline on `enter`.
  - The N6/N7 resume-sync tests (`tests/test_mesh_net_resume.py`, from #498/#499) and the N8 character tests
    (`tests/test_mesh_net_characters.py`) are green under v3.
  - The `"v": 2` literals in about 10 `tests/test_mesh_net_*` files are updated.
- **As implemented** (`mesh_net/protocol.py` has the frame reference):
  - player row `[entity, x, y, facing, elevation, floor, ack, attack_seq]`; enemy row
    `[id, hp, hit_seq, x, y, elevation, floor]` (`floor` `null` for an enemy the authority never stood on a floor);
    `welcome` (N6 and N7) carries `hz`; every `input` carries `tick`; an attack may carry `view_tick` (a number,
    reserved: nothing sends it yet, the server ignores it).
  - Today the server is still last-input-wins: `ack` is the newest input a tick consumed. M4-3's queue changes what
    is consumed, not the wire.
  - Clients refuse, before applying anything, a counter or `ack` that goes back within a room instance and an own
    `ack` beyond the last `seq` sent (`check_progress`); they take a new baseline at `welcome` and `enter`.
  - OD10, counted as single-player's Hitbox counts: each update adds 1/HZ s to its timer and the update that reaches
    0.2 s removes it. At 20 Hz it lives ceil(0.2 × 20) = 4 ticks, and the first 3 (the attack's own tick and the next
    two) check overlaps; the 4th only removes it. A parity test runs the real Combat and Hitbox behaviours at
    1/HZ s against the authority.
  - **The attack cooldown is judged on the intended tick** (review round 2 of #611; design (a)).
    - **Why:** judged on arrival, jitter alone (100 ms RTT, ±10 ms, no loss) let mashing show swings that the server
      then refused: 0, 5 and 3 on seeds 7, 8 and 9 in 19 s. With 1% loss it was 3, 7 and 4, and at 200 ms 3, 8 and 5.
      The client counted the cooldown from the press and the server from the arrival.
    - **The client** reckons the room's tick: a snapshot's tick advanced by the time since it arrived, taken from
      whichever snapshot arrived soonest. While the server keeps time, that reckoning is never ahead of the server.
    - **After a server stall** the server skips the ticks it missed (`Server._run_clock`), so its tick falls behind the
      clock. The reckoning comes back down once `RECKONING` snapshots in a row (a second's worth) have all arrived more
      than a tick late (review round 3).
      - During the stall and about a second after it, the reckoning runs ahead, its ticks count as now, and a swing
        shown then can be refused. Mashing through a 200, 450 or 1000 ms stall gives 0–3 refused swings per run, all
        pressed no later than 250 ms after the stall ends.
      - From a second plus a round trip after the stall, every swing shown runs again.
      - The window never swings early: its cooldown runs from the last swing's tick as sent, which a reckoning that
        came down reaches only later.
      - **One narrow case remains (noted in M4-3):** a resume straight after a swing shown during a stall takes a
        new baseline whose tick is behind that swing's claimed tick, so the window forgets the swing
        (`Feedback.baseline`). Its next press may then swing inside the server's cooldown: that one attack is refused
        and counted in `refused_attacks`. At most one, since that swing starts the window's cooldown again.
    - **A press swings** only a cooldown of reckoned ticks after the last swing. Its attack input carries that tick.
    - **The server** (`SceneRoom._may_attack`) judges the cooldown on that tick, within `[now - COOLDOWN_CLAIM_WINDOW, now]`.
      A tick not reached yet counts as now. An older one is **stale**: dropped, counted in `stale_attacks`, never run.
      Every attack still runs when it arrives, from where the attacker stands then.
    - **COOLDOWN_CLAIM_WINDOW is 12 ticks (600 ms), one named constant.** Measured while mashing over 3 seeds × 8 sessions (about
      900 swings per profile), with the reckoning settled, the oldest claim read was:
      - 100 ms, no loss: 4 ticks;
      - 100 ms, 1% loss: 10 ticks, so OD1's envelope has 2 ticks to spare;
      - 200 ms, 1% loss: 14 ticks, beyond the cap. 7 of 895 swings were stale (0.8%): dropped and counted, never run.

      Round 2 reported 9 and 12 ticks. Those were 1–2 ticks low because the probe delivers its first snapshot with no
      delay, and the old reckoning kept that too-early sample forever. OD5's 300 ms (6 ticks) would drop about 2% of
      swings at 100 ms with 1% loss. **The owner approved the 600 ms window on 2026-11-24, for the cooperative PvE
      prototype only, with conditions** (below).
    - **The claim judges the cooldown only.** The attack runs when it is read: its hitbox, hits, damage and death are
      evaluated on the server's current geometry and floors, never on positions from the claimed tick (since M4-5,
      only the separate `view_tick`, within 300 ms, rewinds the targets: §4 M4-5). A test checks
      this (`test_an_old_claim_judges_the_cooldown_only_never_the_hit`). `COOLDOWN_CLAIM_WINDOW` is named apart from
      OD5's separate 300 ms cap for historical hit validation (M4-5, not approved yet), which stays unchanged.
    - **What a lying client can gain:** meant ticks that start attacks rise at least a cooldown apart and are never
      older than the cap when read, and at most one attack starts per tick.
      - Over any W ticks it can start at most 1 + (W + COOLDOWN_CLAIM_WINDOW) // cooldown attacks, against 1 + W // cooldown when
        judged on arrival. That is the same long-run rate plus one cap's worth.
      - Its longest run on consecutive ticks, after a pause, comes from claiming the oldest tick accepted on every tick.
        That run is 1 + COOLDOWN_CLAIM_WINDOW // (cooldown − 1) attacks: 13 at a cooldown of 2 ticks, 7 at 3, 4 at 5 and 2 at 10
        (the co-op room's).
      - Over 200 ticks a greedy liar gets 6, 4, 3 and 2 more attacks than an honest client at those cooldowns.
      - A 1-tick cooldown allows one attack per tick anyway.
    - **Result:** the mashing test (seeds 7/8/9, every profile, plus jitter alone at 100 ms) has 0 swings shown that the
      server did not run within OD1's envelope. At 200 ms the only ones not run are stale. None are refused.
  - **Nothing pressed is replaced or lost on the way:**
    - The window queues pressed actions, each with its meant tick, and sends one per input, the oldest attack first.
      An attack whose swing showed always queues; the cap of `PENDING` = 4 applies only to uses and takes.
    - The world window queues E only in the room on screen, so nothing pressed while a room loads runs in a room the
      player hasn't seen.
    - The server queues attacks, and uses and takes, separately (`PENDING` = 4 of each), and reads one of each per
      tick. An attack is never dropped for a use in the same tick (note iii).
    - Losing focus releases held keys but keeps what was pressed. Only a session's end, or an `enter`, clears it. The
      server drops what was waiting when a player leaves.
  - **The enemy limit:** v3's longer rows lower how many enemies fit in a frame. With 8 players and floor ids at their
    128-character limit, about 25 fit with 12-character ids, 22 with 24-character ids and 18 with 40-character ids,
    against the 32 networked objects allowed before. A room that wouldn't fit is refused at load, never at run time.

**M4-3 — own-movement prediction (b), with OD11:**
- Extract the per-body step. Add the input queue (if OD11(a)). One predictor for both arenas. HD-2D corrections snap
  elevation and floor; x/y is smoothed.
- **Acceptance (same-seed probe):**
  - Local first move within one frame on every seed and profile.
  - With OD11(a): zero corrections with no loss and static solids.
  - p95 correction at most one step (7.5 px) at 100 ms, ±10 ms, 1%.
  - Stairs level-caused disagreement below 5% at 100 ms on every seed (today 27–29%).
  - Prediction buffers cleared on resume, transfer and enter: tests for N6 resume, an N7 transfer with inputs in
    flight, and an N7 resume.
  - The resume-sync and N8 tests green.
  - M3 acceptance unchanged in intent: the own avatar converges to the server row.
- **As implemented** (owner decisions OD3 and OD11; review rounds 1–3 of #613 and the owner's decision of
  2026-11-24; `mesh_net/scene_room.py` has the code and its notes). Round 4 comes first, then round 3. Round 3's
  and round 2's text below stays as it was measured; round 2's "chosen design" is now the "deep" preset.
  - **Round 4 (follow-ups to #613's independent review): the drain never drops a step at a fork.**
    - **The rule** (`SceneRoom._forks`): before the drain drops the oldest waiting input, the authority walks this
      tick's step and every input still waiting twice, from a copy of the body: with that input and without it,
      through the one step (`walk`, so `World.move`; no floor logic of its own). If the two ends are more than one
      step apart, or on different floors, the drop is refused this tick. The drain's count runs on, so a later tick
      drains instead (usually the next one). The client replays exactly those inputs from the next snapshot, so the
      two ends' distance is about the correction the drop would cost. Inputs still in flight are not seen.
    - **Why:** the review found that most large stair corrections followed a drain drop on a stair step. A step
      short beside a fork in the floors (stairs and the landing or ground beside them, where one floor blocks a
      walk that the other doesn't) sends the replayed inputs down the other branch.
    - **Rejected first: "never drain on a sloped floor".** It held the backlog for the whole stair walk (longest
      backlog 261–313 ticks, about 15 s, at 0–100 ms). Because the backlog delayed the server, the walk overshot
      onto the landing and the ground beside the stairs, so the drops happened there, at the forks. At 100 ms that
      made it worse: 6.3–7.8 large corrections a minute, all over 30 px, worst 98 px. The reviewer's "only on the
      ground" check is not general (it names the demo's floor).
    - **Same seeds** (7/8/9 × 24 sessions, every profile), drain preset, before → after:

      | Stairs, 16 s strafing (6 min a seed) | 0 ms ±10 1% | 50 ms ±10 1% | 100 ms ±10 1% | 200 ms ±10 1% |
      |---|---|---|---|---|
      | Corrections (n) | 175–201 → same | 258–270 → 257–270 | 334–368 → 243–309 | 293–333 → 213–238 |
      | p95 of the corrections px | 5.3 → 5.3 | 5.3 → 5.3 | 5.3 → 5.3 | 35.6–45.3 → 7.5–15 |
      | Worst px | 5.3 → 5.3 | 5.3 → 5.3 | 41–71 → 19–27 | 71–102 → 55–64 |
      | Large (over one step) per minute | 0 → 0 | 0 → 0 | 1.8–2.7 → 0.8–1.3 | 5.5–6.7 → 1.8–3.0 |
      | Large over 30 px (per 6 min) | 0 → 0 | 0 → 0 | 4–7 → **0** | 18–23 → 2–5 |
      | Large with an elevation or floor snap | 0 → 0 | 0 → 0 | 11–16 → 5–8 | 33–36 → 10–14 |
      | Level-caused disagreement | 0.5% → 0.5% | 0.9–1.0% → 0.9–1.1% | 1.5–1.6% → 1.1–1.4% | 1.4–1.7% → 0.6–0.7% |
      | Directions drained / overflowed | 177–201 / 0 → same | 259–273 / 0 → same | 335–369 / 0 → 332–367 / 0 | 342–389 / 76–84 → 341–388 / 76–84 |
      | Backlog (2+ waiting) length, p95 / longest ticks | 11–12 / 12–15 → 11–12 / 12–17 | 15 / 16–19 → 15 / 17–19 | 19 / 23 → 20 / 25–26 | 23 / 23–25 → 23–25 / 28–29 |

      - **Unchanged, identical to the number:** the 2D scenarios, so movement, walking, standing attacks and the
        moving targets. That includes the corrections (movement and walking: max 7.5 px at 0–100 ms, 15 px at
        200 ms), the peer view while walking (p50 270–291 ms at 100 ms), the walking-swing confirmation (p50 210–229
        ms), discarded steps, attacks never executed, and snapshot sizes. The rule could refuse a 2D drop (a wall or
        an enemy in the way: tested); none happened in these runs. Jitter alone and 0 ms with no loss: 0 corrections
        before and after.
      - **What it costs:** a backlog on the stairs lasts up to 3 ticks longer: 25–26 ticks (about 1.3 s) at 100 ms
        and 28–29 at 200 ms, against 21–25 elsewhere. Up to 150 ms more lateness for peers, for about a second,
        near a fork.
      - **The remaining large ones, at 100 ms:** 5–8 in 6 minutes, 19–27 px, every one with an elevation or floor
        snap, every one after a drain drop (no overflow at 100 ms). *(Inferred: a fork reached by inputs still in
        flight, which the server can't see.)* Making the check assume the newest direction is held for the inputs in
        flight was tried on seed 7. It cut 100 ms from 7 to 5 but raised 200 ms (over 30 px: 3 → 7), so it was not
        kept.
      - **At 200 ms**, the drops of a full queue (76–84 per seed beyond depth 8, which deep has too) are untouched by
        the rule, and 2–5 large corrections over 30 px remain.
    - **Deep and small are unchanged** (their drain is 0, so the rule never runs). Their stairs runs, same seeds and
      every profile, are byte-identical before and after. Tests drive both presets, and a raw depth 5 / hold 3,
      through N6, the stairs and an N7 instance.
    - **Also in round 4:**
      - Tests for the review's surviving mutants: each room overflows at its own depth and walks on for its own hold
        (T12/T13), ordinary walking (one input waiting) never drains (T01), and `leave` resets the drain's count
        (T11).
      - The probe's `--depth/--hold/--drain` now beat `--queue`, as the server's flags do (`queue_of`).
      - The probe reports, per scenario, the large corrections (count, per minute, over 30 px, with a snap) and each
        backlog's length.
  - **Round 3: the queue is the owner's choice, with a provisional default.**
    - The round-2 review found the conflict. Design A ("deep") keeps a retransmission burst as a backlog that never
      drains while the player walks: peers see the walk 333–340 ms late even at 0 ms ±10 ms 1% (D: 179–188 ms), and
      516–541 ms at 100 ms. That breaks the owner's 600 ms condition 6: "stalls, retransmissions, disconnects and room
      transfers must not cause persistent timing corruption". The round-2 acceptance table had left that condition
      out.
    - **Owner decision, 2026-11-24, quoted verbatim:**

      > "Decide after playing. Use Drain as the provisional default, subject to the full 24-session measurements.
      > Keep all three strategies switchable in the M4 playable demo. Do not designate Drain as the permanent
      > architecture until I've experienced the alternatives. Specifically: Report the frequency and circumstances of
      > large stair corrections. Distinguish discarded movement steps from attack inputs that were shown locally but
      > never executed by the server. Do not treat lost or unconfirmed attacks as acceptable merely because they occur
      > at 200 ms RTT. Preserve input-correctness and server-authority safeguards. If all three approaches fail
      > important acceptance criteria, report that rather than declaring a winner."

    - **The three strategies** (`mesh_net.scene_room.QUEUE_PRESETS`). Every one reads one input a tick, oldest first,
      and keeps the standing rule:

      | Preset | depth | hold | drain | What it does with a retransmission burst |
      |---|---|---|---|---|
      | **drain** (PROVISIONAL default) | 8 | 1 | 4 | keeps it, then drops the oldest waiting direction whenever more than one input has waited 4 ticks in a row (never an action; one step each) |
      | deep (round 2's A) | 8 | 1 | 0 | keeps it; the server runs that many ticks behind until the player stands |
      | small (round 1's D) | 2 | 5 | 0 | drops all but the newest two; walks the last direction on for up to 4 ticks with nothing waiting |

      - **Switching:** `python -m mesh_net.server --coop|--expedition --queue drain|deep|small`, or the raw knobs
        `--input-depth N` (1–20), `--input-hold N` (1–5) and `--input-drain N` (0 off, or 2–20). Each falls back to
        `MESH_NET_QUEUE` / `MESH_NET_INPUT_DEPTH` / `_HOLD` / `_DRAIN`, then to the preset's value.
      - Every value is checked (`queue_settings`); anything else is refused at start with the reason.
      - `SceneRoom(..., depth=, hold=, drain=)` and `World(..., depth=, hold=, drain=)` take them, and every N7 room
        instance inherits them. The probe takes `--queue` or `--depth/--hold/--drain`.
      - The client needs nothing: it predicts one step per input either way.
    - **"drain" held up at 24 sessions** (seeds 7/8/9, every profile), so it is the default, labelled PROVISIONAL in
      the code. Drain thresholds measured beside A, C and D, all at 100 ms ±10 ms 1% unless noted:

      | Variant | Corrections: movement n / max | Stairs p95 / max px | Walking corrections (one step each) | Stop after release p95 ms | Peer view while walking p50 ms | Walking swing p50 ms | Ticks in a row 2+ deep | 0 ms ±10 1%: peer view p50 | 200 ms: walking swings never run |
      |---|---|---|---|---|---|---|---|---|---|
      | drain 3 | 123–145 / 7.5 | 5.3 / 34–56 | 398–459 | 350–382 | 265–279 | 208–223 | 17 | 180–193 | 17–19 of ~693 |
      | **drain 4** | 72–89 / 7.5 | 5.3 / 41–71 | 382–435 | 224–323 | 270–291 | 210–229 | 21–23 | 183–193 | 17–25 |
      | drain 6 | 57–63 / 7.5 | 5.3–19.1 / 56–71 | 346–386 | 237–268 | 277–293 | 222–233 | 32–35 | 185–195 | 20–28 |
      | deep (A) | 0 | 0 / 0 | 0 | 6–8 | 516–541 | 457–474 | 295–308 (the whole walk) | 333–340 | 75–139 |
      | C (depth 6) | 76–89 / 15 | 10.6 / 19–34 | 93–116 | 262–286 | 459–463 | 392–399 | 295–308 | 333–340 | 8–13 |
      | small (D) | 486–565 / 45 | 26.5 / 39–81 | 450–528 (up to 45 px) | 319–369 | 260–266 | 200–205 | 0 | 179–188 | 7–11 |

      - With jitter alone (100 ms ±10 ms, no loss), every drain threshold and deep give 0 corrections; small gives
        83–147.
      - Drain 4 is kept as the reviewer measured it. Drain 3 lowers the worst stair correction (to 34–56 px) at about
        twice the movement corrections. Drain 6 corrects less but lets a backlog last longer.
    - **Large stair corrections** (over one step, 7.5 px x/y).
      - Method: 24 sessions × 3 seeds of 16 s strafing up and down the floors demo's stairs against their east edge;
        6 minutes of stair walking per seed and profile.
      - Each correction is attributed to what the server did in the ticks it covers: a drain drop (on a stair step or
        not), an overflow drop, or a step walked with nothing waiting.

      | Preset | RTT | Large per minute | Over 30 px (per 6 min) | 15–30 px | Worst | With a floor change | Cause of the large ones |
      |---|---|---|---|---|---|---|---|
      | drain | 100 ms ±10 1% | 1.8–2.7 | 4–7 | 6–9 | 71 px (16 px height, floor change) | 11–16 of 11–16 | drain drop on a stair step: 11–15; drain drop elsewhere: 0–2 |
      | drain | 200 ms ±10 1% | 5.5–6.7 | 18–23 | 10–13 | 102 px (30 px height) | 32–35 of 33–40 | drain drop on a stair step: 23–27; elsewhere: 4–8; overflow beyond depth 8: 2–9 |
      | drain | 0 ms ±10 1%, 50 ms, jitter alone | 0 | 0 | 0 | 5.3 px | — | (only one-step corrections) |
      | deep | 100 ms ±10 1% | 0 | 0 | 0 | none | — | — |
      | deep | 200 ms ±10 1% | 0.17–0.5 | 0–1 | 0 | 36 px (26 px height) | 0–1 | overflow beyond depth 8 |
      | small | 100 ms ±10 1% | 11–12.8 | 5–13 | 58–63 | 81 px (24 px height) | 15–20 of 66–77 | overflow drop: 66–76; walked on: 0–1 |
      | small | 200 ms ±10 1% | 12.8–14.7 | 59–70 | 15–17 | 124 px (38 px height) | 55–65 of 77–88 | overflow drop: 62–74; walked on: 14–17 |
      | small | 0 ms ±10 1% | 9.2–10 | 0 | 52–54 | 21 px | 3–4 | overflow drop |

      - **Why one dropped step makes a large correction on the stairs.** The drop leaves the server one step short in
        y. At the stairs' east edge that can put it on the other floor: the ground instead of the stairs, or the
        reverse.
      - The edge blocks an eastward walk from the stairs, but not from the ground. So the inputs still unread (5–7 at
        100 ms) replay from the other floor, eastward instead of blocked, and the correction grows to many steps,
        with an elevation and floor snap.
      - Every large one starts from a retransmission burst: with jitter alone there are none.
      - On flat floors a dropped step corrects exactly one step (7.5 px; walking max 7.5 px).
    - **(a) Movement steps the server discarded** (directions dropped, never their actions; the window corrects
      them). Inputs sent per seed run: about 28,550 in movement and 9,600 in walking.

      | Preset | RTT | Movement: overflow / drained (share of inputs) | Walking: overflow / drained (share) |
      |---|---|---|---|
      | drain | 0 ms (none), jitter alone | 0 / 0 | 0 / 0 |
      | drain | 0 ms ±10 1% | 0 / 88–90 (0.3%) | 0 / 220–242 (2.3–2.5%) |
      | drain | 50 ms ±10 1% | 0 / 74–112 (0.3–0.4%) | 0 / 304–328 (3.2–3.4%) |
      | drain | 100 ms ±10 1% | 0 / 114–133 (0.4–0.5%) | 0 / 382–435 (4.0–4.5%) |
      | drain | 200 ms ±10 1% | 262–282 / 148–157 (1.4–1.5%) | 95–105 / 409–481 (5.3–6.1%) |
      | deep | 0–100 ms, jitter alone | 0 / 0 | 0 / 0 |
      | deep | 200 ms ±10 1% | 262–284 / 0 (0.9–1.0%) | 103–109 / 0 (1.1%) |
      | small | 0 ms ±10 1% | 799–831 / 0 (2.8–2.9%) | 263–279 / 0 (2.7–2.9%) |
      | small | 100 ms ±10 1% | 1393–1502 / 0 (4.9–5.3%) | 457–547 / 0 (4.8–5.7%) |
      | small | 200 ms ±10 1% | 1877–2031 / 0 (6.6–7.1%) | 651–737 / 0 (6.8–7.7%) |

    - **(b) Attacks shown locally but never executed by the server** (stale + refused + dropped). Standing presses:
      720 per seed run, all shown. Walking swings: about 693 per seed run.
      - **0 for every preset at 0, 50 and 100 ms (±10 ms, 1%) and with jitter alone**, standing and walking. Nothing
        to flag within OD1's envelope.
      - **At 200 ms ±10 ms 1%** they are not acceptable just because the latency is high. They are reported:

        | Preset | Standing, never run | Walking, never run |
        |---|---|---|
        | drain | 3–10 of 720 (0.4–1.4%), all stale | 17–25 of 692–695 (2.4–3.6%), all stale |
        | deep | 3–10 of 720 (0.4–1.4%), all stale | 75–139 (10.8–20.1%), all stale |
        | small | 3–10 of 720 (0.4–1.4%), all stale | 7–11 (1.0–1.6%), all stale |

      - None was refused in the cooldown and none was dropped from a full action queue. Every one was a claim older
        than the 600 ms window when the server read it, which the window shows as a miss.
    - **Acceptance per preset** (§4's and the owner's own words; numbers at 100 ms ±10 ms 1% unless noted):

      | Criterion | drain (provisional default) | deep (A) | small (D) |
      |---|---|---|---|
      | Local first move within one frame, every seed and profile | MET (16.7 ms) | MET | MET |
      | Zero corrections with no loss and static solids | MET (0 at 0 ms and jitter alone) | MET | **NOT MET** (jitter alone: 83–147) |
      | p95 correction ≤ one step (7.5 px) at 100 ms | MET (movement 7.5, walking 7.5, stairs 5.3), but stairs max 41–71 px, 1.8–2.7 large a minute; round 4: max 19–27 px, 0.8–1.3 large a minute, none over 30 px | MET (none) | **NOT MET** (37.5 px; stairs 26.5) |
      | Stairs level-caused disagreement < 5% at 100 ms | MET (1.5–1.6%; round 4: 1.1–1.4%) | MET (0.0%) | MET (1.4–1.7%) |
      | Buffers cleared on resume, transfer, enter; resume-sync and N8 green; M3 acceptance | MET (default tested) | MET (round 2) | MET (round 1) |
      | Owner condition 6: no persistent timing corruption from stalls, retransmissions, disconnects, transfers | MET, bounded: a backlog lasts at most 21–23 ticks (about 1.1 s); peer view 270–291 ms; round 4: up to 25–26 ticks on the stairs | **NOT MET**: the backlog lasts the whole walk; peer view 516–541 ms, and 333–340 ms even at 0 ms ±10 1% | MET (at most 1 waiting) |
      | OD1: responsive movement and swing feedback | MET | MET | MET |
      | OD1: median hit confirmation ≤ RTT + 75 ms (175 ms), standing | **NOT MET** (166.0–175.9; seed 9 0.9 ms over) | **NOT MET** (same) | **NOT MET** (same) |
      | OD1: the same for a swing made while walking | **NOT MET** (210–229) | **NOT MET** (457–474) | **NOT MET** (200–205) |
      | Attacks shown but never executed within OD1's envelope | MET (0) | MET (0) | MET (0) |
      | At 200 ms: attacks shown but never executed (reported, not accepted) | 0.4–1.4% standing, 2.4–3.6% walking | 0.4–1.4% standing, 10.8–20.1% walking | 0.4–1.4% standing, 1.0–1.6% walking |
      | Input-correctness and server-authority safeguards (every tick at most one step, only an input's direction; nothing walked into a new room or session; no attack twice) | MET (tests and mutants, default) | MET | MET |

      **All three fail important criteria, so no winner is declared.**
      - Every preset misses OD1's hit-confirmation aim: by 0.9 ms on one seed for a standing attacker, and clearly for
        a swing made while walking.
      - "deep" breaks the owner's condition 6.
      - "small" fails the correction criteria.
      - "drain" meets the §4 criteria as written, but made large stair corrections about twice a minute of stair
        walking at 100 ms (up to 71 px, with a floor snap) and about six a minute at 200 ms. Since round 4's fork
        guard: about one a minute at 100 ms (up to 27 px, still with a snap) and two to three a minute at 200 ms (up
        to 64 px). That is fewer, but not none.
      - Drain is the provisional default by the owner's instruction, to be judged by playing all three in the M4 demo.
    - **Also in round 3:**
      - `riders` is reset at an `enter` and at a session's end (the reviewer's R05).
      - The drain's drops are counted apart from overflow (`drained_moves`).
      - Tests cover the presets, the bounds, the server's flags and environment, a world's instances inheriting the
        settings, and the drain (one direction at a time, never an action, never two steps a tick).
  - **One movement step.** `SceneRoom.walk(body, dx, dy, solids)` is the only code in `mesh_net` that moves a body:
    `World.move` with this module's sweep in HD-2D, the sweep alone in 2D, a diagonal normalised, then the wire's
    bound. The authority's tick (N6, so every N7 room instance) and the window's prediction both call it. The
    no-duplicate scan in `tests/test_hd2d_net_parity.py` fails if any other `mesh_net` function calls
    `move`/`World.move` or defines a second `walk`; a spy test checks that both sides call it. Single-player is
    untouched: replays 13/13, no golden updated.
  - **The server's input queue (OD11), as chosen in round 2.**
    - Each tick reads ONE input, the oldest waiting, and walks one step with its direction. `ack` is the seq of that
      input.
    - At most `DEPTH` = **8** wait; a full queue drops its oldest direction (`dropped_moves`).
    - `HOLD` = **1**: a tick with nothing waiting walks nothing. The server never takes a step no input gave (the
      old 5-tick lease is gone).
    - While the player stands, of two still inputs waiting, the older is dropped (the "standing rule"). It walks
      nowhere and its actions run with the next, so this never causes a correction.
    - An input's attack and its use or take wait in M4-2's queues (`PENDING` of each, one of each kind a tick),
      tagged with their input's seq. They run on the tick that reads their own input or a later one, **before** that
      tick's step: from where the window showed the player when the key was pressed. A dropped direction never loses
      an action.
    - `leave` (disconnect, transfer) empties the queue. M4-1's `InputBudget` bounds how fast frames come; the queue
      bounds what is kept. A burst never walks a body faster than one step a tick.
  - **Why depth 8 and hold 1, not OD11's starting depth 2.** OD11 says that if depth 2 fails, the queue is to be
    adjusted with measurements rather than forced.
    - Depth 2 fails §4's "p95 correction at most one step" at 100 ms, read honestly: the corrections that happen have
      p95 37.5 px and max 45 px.
    - The cause: TCP holds everything behind a lost segment for RTT + RTO (6 ticks at 100 ms, 8 at 200 ms) and then
      delivers it at once.
    - Depth 2 threw that burst away, so the server ended steps short of the window. The 5-tick lease walked on
      during the hold and overshot a release by up to 4 steps (30 px).
    - Depth 8 keeps the burst and walks every step the player took, one a tick, later. Hold 1 never guesses. So the
      prediction is not corrected at all at 100 ms.
  - **The variant matrix** (same seeds 7/8/9 × 24 sessions; every profile; scenarios movement, attack, stairs and the
    new `walking`; `tooling/m4_latency_probe.py` with the queue patched per cell).
    - The grid: depth {2, 4, 6, 8} × hold {5, 1} × standing rule on/off × "actions run early when nothing still to
      walk is queued ahead of them" (the reviewer's suggestion) on/off, plus a slow drain.
    - The drain: a queue two deep for a second gives one input back, a one-step correction.
    - Dominated cells are shown.
    - The costs columns come from `walking`, 20 s without stopping (turning every second) with a swing every
      ~600 ms:
      - how many inputs wait after each tick;
      - how late a peer's view shows each step, from the input's send to a peer's `Playback` showing a state that
        read it;
      - how long a swing made while walking waits, from the press to the first frame after the state of the tick
        that started it.
    - Every cell is 100 ms ±10 ms 1% unless the column says otherwise. "Jitter-only" is 100 ms ±10 ms with no loss
      (corrections summed over movement, stairs and walking).

    | Variant | Corrections at 100 ms: n / p95 / max px | Stairs p95 / max px | Jitter-only corrections | Stop after release p95 ms | Peer first move p50 ms | Standing hit p50 ms | Queue while walking p50 / max | Peer view while walking p50 ms | Walking swing p50 ms | 200 ms: corrections p95 / max px | 200 ms: walking swings stale |
    |---|---|---|---|---|---|---|---|---|---|---|---|
    | d2_h1_s0_e0 | 131–142 / 37.5 / 45 | 26.5–38.6 / 38.6–43.7 | 0 | 264–299 | 242–244 | 204–209 | 1 / 1 | 262–269 | 200–208 | 52.5 / 52.5–60 | 7–11 of 692–695 |
    | d2_h1_s0_e1 | 131–142 / 37.5 / 45 | 26.5–38.6 / 38.6–43.7 | 0 | 264–299 | 242–244 | 166–176 | 1 / 1 | 262–269 | 200–208 | 52.5 / 52.5–60 | 7–11 of 692–695 |
    | d2_h1_s1_e0 | 123–137 / 37.5 / 45 | 26.5–38.6 / 38.6–43.7 | 0 | 264–299 | 207–216 | 166–176 | 1 / 1 | 260–266 | 200–205 | 52.5 / 52.5–60 | 7–11 of 692–695 |
    | d2_h1_s1_e1 | 123–137 / 37.5 / 45 | 26.5–38.6 / 38.6–43.7 | 0 | 264–299 | 207–216 | 166–176 | 1 / 1 | 260–266 | 200–205 | 52.5 / 52.5–60 | 7–11 of 692–695 |
    | d2_h5_s0_e0 | 418–472 / 37.5 / 45 | 26.5 / 38.6–80.9 | 2–10 | 314–371 | 242–244 | 204–209 | 1 / 1 | 262–269 | 200–208 | 45 / 52.5–60 | 7–11 of 692–695 |
    | d2_h5_s0_e1 | 418–472 / 37.5 / 45 | 26.5 / 38.6–80.9 | 2–10 | 314–371 | 242–244 | 166–176 | 1 / 1 | 262–269 | 200–208 | 45 / 52.5–60 | 7–11 of 692–695 |
    | d2_h5_s1_e0 | 486–565 / 37.5 / 45 | 26.5 / 38.6–80.9 | 91–161 | 319–369 | 207–216 | 166–176 | 1 / 1 | 260–266 | 200–205 | 37.5–45 / 52.5–60 | 7–11 of 692–695 |
    | d2_h5_s1_e1 | 486–565 / 37.5 / 45 | 26.5 / 38.6–80.9 | 91–161 | 319–369 | 207–216 | 166–176 | 1 / 1 | 260–266 | 200–205 | 37.5–45 / 52.5–60 | 7–11 of 692–695 |
    | d4_h1_s0_e0 | 112–119 / 22.5 / 30 | 15.9–21.2 / 28.6–42.8 | 0 | 269–300 | 341–344 | 302–308 | 3 / 3 | 361–368 | 297–306 | 37.5 / 37.5–45 | 7–11 of 692–695 |
    | d4_h1_s0_e1 | 112–119 / 22.5 / 30 | 15.9–21.2 / 28.6–42.8 | 0 | 269–300 | 341–344 | 166–176 | 3 / 3 | 361–368 | 297–306 | 37.5 / 37.5–45 | 7–11 of 692–695 |
    | d4_h1_s0_e1_drain | 198–236 / 22.5 / 30 | 15.9–21.2 / 28.6–42.8 | 0 | 312–319 | 274–281 | 166–176 | 1 / 3 | 296–297 | 235–243 | 37.5 / 37.5–45 | 7–11 of 692–695 |
    | d4_h1_s1_e0 | 103–116 / 22.5 / 30 | 15.9–21.2 / 28.6–42.8 | 0 | 269–300 | 207–217 | 166–176 | 2–3 / 3 | 359–363 | 295–301 | 37.5 / 37.5–45 | 7–11 of 692–695 |
    | d4_h1_s1_e1 | 103–116 / 22.5 / 30 | 15.9–21.2 / 28.6–42.8 | 0 | 269–300 | 207–217 | 166–176 | 2–3 / 3 | 359–363 | 295–301 | 37.5 / 37.5–45 | 7–11 of 692–695 |
    | d4_h1_s1_e1_drain | 103–116 / 22.5 / 30 | 15.9–21.2 / 28.6–42.8 | 0 | 269–300 | 207–217 | 166–176 | 1 / 3 | 296 | 233–242 | 37.5 / 37.5–45 | 7–11 of 692–695 |
    | d4_h5_s0_e0 | 341–396 / 22.5 / 30 | 15.9–35.6 / 57.4–72.1 | 2–10 | 316–398 | 341–344 | 302–308 | 3 / 3 | 361–368 | 297–306 | 37.5 / 37.5–45 | 7–11 of 692–695 |
    | d4_h5_s0_e1 | 341–396 / 22.5 / 30 | 15.9–35.6 / 57.4–72.1 | 2–10 | 316–398 | 341–344 | 166–176 | 3 / 3 | 361–368 | 297–306 | 37.5 / 37.5–45 | 7–11 of 692–695 |
    | d4_h5_s1_e0 | 458–545 / 22.5 / 30 | 15.9–35.6 / 57.4–72.1 | 91–161 | 323–373 | 207–217 | 166–176 | 2–3 / 3 | 359–363 | 295–301 | 37.5 / 37.5–45 | 7–11 of 692–695 |
    | d4_h5_s1_e1 | 458–545 / 22.5 / 30 | 15.9–35.6 / 57.4–72.1 | 91–161 | 323–373 | 207–217 | 166–176 | 2–3 / 3 | 359–363 | 295–301 | 37.5 / 37.5–45 | 7–11 of 692–695 |
    | d6_h1_s1_e0 | 76–89 / 7.5–15 / 15 | 10.6 / 19.1–34 | 0 | 262–286 | 207–217 | 166–176 | 4–5 / 5 | 459–463 | 392–399 | 22.5–30 / 22.5–30 | 8–13 of 692–695 |
    | d6_h1_s1_e1 | 76–89 / 7.5–15 / 15 | 10.6 / 19.1–34 | 0 | 262–286 | 207–217 | 166–176 | 4–5 / 5 | 459–463 | 392–399 | 22.5–30 / 22.5–30 | 8–13 of 692–695 |
    | d8_h1_s0_e0 | 0 / 0 / 0 | 0 / 0 | 0 | 6–8 | 505–516 | 465–479 | 6 / 7 | 523–541 | 462–476 | 7.5–15 / 15 | 75–146 of 692–695 |
    | d8_h1_s0_e1 | 0 / 0 / 0 | 0 / 0 | 0 | 6–8 | 505–516 | 166–176 | 6 / 7 | 523–541 | 462–476 | 7.5–15 / 15 | 75–146 of 692–695 |
    | d8_h1_s0_e1_drain | 198–207 / 7.5 / 7.5 | 7.5–35.6 / 50.3–63.9 | 0 | 339–354 | 368–380 | 166–176 | 3 / 7 | 383–412 | 324–355 | 7.5 / 15 | 30–46 of 692–695 |
    | d8_h1_s1_e0 | 0 / 0 / 0 | 0 / 0 | 0 | 6–8 | 207–217 | 166–176 | 6 / 7 | 516–541 | 457–474 | 7.5–15 / 15 | 75–139 of 692–695 |
    | d8_h1_s1_e1 | 0 / 0 / 0 | 0 / 0 | 0 | 6–8 | 207–217 | 166–176 | 6 / 7 | 516–541 | 457–474 | 7.5–15 / 15 | 75–139 of 692–695 |
    | d8_h1_s1_e1_drain | 0 / 0 / 0 | 7.5–35.6 / 50.3–63.9 | 0 | 6–8 | 207–217 | 166–176 | 2 / 7 | 372–397 | 316–343 | 7.5–15 / 15 | 30–46 of 692–695 |
    | d8_h5_s0_e0 | 19–28 / 7.5 / 7.5 | 5.3 / 5.3 | 2–10 | 6–9 | 505–516 | 465–479 | 6 / 7 | 523–541 | 462–476 | 7.5 / 15 | 75–146 of 692–695 |
    | d8_h5_s0_e1 | 19–28 / 7.5 / 7.5 | 5.3 / 5.3 | 2–10 | 6–9 | 505–516 | 166–176 | 6 / 7 | 523–541 | 462–476 | 7.5 / 15 | 75–146 of 692–695 |
    | d8_h5_s1_e0 | 347–424 / 7.5 / 7.5 | 5.3 / 5.3 | 91–161 | 185–206 | 207–217 | 166–176 | 6 / 7 | 516–541 | 457–474 | 7.5 / 15 | 75–139 of 692–695 |
    | d8_h5_s1_e1 | 347–424 / 7.5 / 7.5 | 5.3 / 5.3 | 91–161 | 185–206 | 207–217 | 166–176 | 6 / 7 | 516–541 | 457–474 | 7.5 / 15 | 75–139 of 692–695 |

    - **Not in the grid, tried and dominated:** "hold credit". A step walked on with nothing waiting stands in for the
      missing input, which is then not walked when it comes. At 6 sessions it gave more corrections than plain depth
      8 / hold 1 and still built a backlog.
    - **Early actions (e1) change nothing once the standing rule is on.** The rule already empties a standing
      player's queue. Without the rule (s0 e1) a standing swing is as quick, but a peer sees a walk start 505–516 ms
      after the press, against 207–217 ms. So the rule is kept and early actions are not added.
  - **The chosen design, measured** (`--depth 8` is now the game's own; before = b81765ae, M4-2):

    | RTT (jitter, loss) | Local first move p50 / max ms | Corrections (movement; stairs; walking) | Stairs level-caused | Hit confirmed p50 ms (standing) | Stop after release p95 ms |
    |---|---|---|---|---|---|
    | 0 (none) | 54.0–60.8 / 115 → **8.0–8.5 / 16.7** | **0; 0; 0** | 14.8–15.5% → **0.0%** | 52.6–57.6 → 61.8–65.7 | 40.6–45.9 → 4.1–7.5 |
    | 0 (±10, 1%) | 65.8–71.4 / 446 → **7.6–8.2 / 16.7** | **0; 0; 0** | 16.6–17.8% → 0.0% | 63.4–71.8 → 72.0–77.3 | 93.6–128.8 → 7.0–7.7 |
    | 50 (±10, 1%) | 106.9–113.5 / 567 → **8.0–8.7 / 16.7** | **0; 0; 0** | 22.7–23.1% → 0.0% | 106.0–114.4 → 115.0–122.8 | 144.4–159.4 → 5.3–7.7 |
    | 100 (±10, 1%) | 157.4–167.6 / 714 → **8.1–8.6 / 16.7** | **0; 0; 0** | 27.4–29.0% → **0.0%** | 155.8–165.4 → 166.0–175.9 | 241.5–262.6 → 5.7–7.6 |
    | 200 (±10, 1%) | 260.9–264.6 / 2102 → **8.1–8.9 / 16.7** | 61–69 (p95 7.5–15, max 15); 30–41 (max 10.6–35.6); 92–100 (max 15) | 33.1–33.4% → 0.2% | 263.8–265.4 → 269.0–273.4 | 386.2–432.1 → 386.3–470.9 |
    | 100 (±10, no loss) | — → 8.3–8.7 / 16.7 | **0; 0; 0** | — → 0.0% | — → 163.7–171.4 | — → 6.3–8.4 |

    Its costs, while a player keeps walking (`walking`):

    | RTT (jitter, loss) | Inputs waiting after each tick p50 / max | Ticks in a row two or more deep (of 370) | Peer view of each step p50 / p95 ms | Swing made walking confirmed p50 / p95 ms | Walking swings stale |
    |---|---|---|---|---|---|
    | 0 (none) | 0 / 0 | 0 | 130–136 / 163–165 | 65–70 / 98–110 | 0 |
    | 0 (±10, 1%) | 4 / 5 | 332–341 | 333–340 / 365–373 | 269–271 / 316–321 | 0 |
    | 50 (±10, 1%) | 5 / 6 | 265–360 | 419–436 / 459–467 | 359–371 / 416–430 | 0 |
    | 100 (±10, 1%) | 6 / 7 | 295–308 | 516–541 / 564–575 | 457–474 / 517–566 | 0 |
    | 200 (±10, 1%) | 6–7 / 7 | 272–296 | 657–666 / 710–732 | 585–593 / 659–728 | **75–139 of 692–695** |
    | 100 (±10, no loss) | 0 / 1 | 0 | 237–245 / 261–270 | 177–180 / 216–225 | 0 |

    - **A backlog never drains while the player keeps walking.** The client sends one input a tick, the server reads
      one a tick, and nothing may walk two steps in a tick. It drains when the player stops: the steps already sent
      are walked out (peers see the walk finish late), then the standing rule drops the still inputs.
    - At depth 2 the same walk costs: peer view 260–266 ms, swing 200–205 ms, and at 200 ms 7–11 stale swings. That
      is the trade-off: what depth 2 threw away (corrections), depth 8 keeps as lateness.
  - **Against the acceptance** (§4's own words; each MET or NOT MET, with the measurement):
    - "Local first move within one frame on every seed and profile": **MET**. Max 16.7 ms on every seed and every
      profile, 200 ms included.
    - "With OD11(a): zero corrections with no loss and static solids": **MET**. 0 corrections in every scenario on
      every seed at both no-loss profiles: 0 ms without jitter, and 100 ms ±10 ms without loss.
    - "p95 correction at most one step (7.5 px) at 100 ms, ±10 ms, 1%": **MET**. There is no correction at all (0 of
      about 28,500 movement, 7,640 stairs and 9,560 walking reconciliations per seed). Round 1's depth 2 did NOT meet
      it: p95 37.5 px of the corrections that happened.
    - "Stairs level-caused disagreement below 5% at 100 ms on every seed (today 27–29%)": **MET**, 0.0% on every
      seed.
    - "Prediction buffers cleared on resume, transfer and enter: tests for N6 resume, an N7 transfer with inputs in
      flight, and an N7 resume": **MET** (`tests/test_mesh_net_prediction.py`).
    - "The resume-sync and N8 tests green": **MET**.
    - "M3 acceptance unchanged in intent: the own avatar converges to the server row": **MET**
      (`tests/test_mesh_net_hd2d_gpu.py`, hidden windows).
    - OD1, "responsive movement and swing feedback through 100 ms RTT with ±10 ms jitter and 1% loss": **MET**.
      Local move and swing within one frame.
    - OD1, "median hit confirmation at most RTT + 75 ms" (175 ms at 100 ms), for a standing attacker: **NOT MET**.
      - 166.0–175.9 ms; seed 9 is 0.9 ms over.
      - M4-2 reported 155.8–165.4 ms, but its probe let a press ride the next send without the frame that reads it.
        Arena.run dispatches key events once a frame. The reviewer re-ran round 1's queue with M4-2's press timing and
        got M4-2's figures back, so M4-2's numbers were about 10 ms optimistic. Under the honest measurement
        the aim is missed by 0.9 ms on one seed.
    - OD1, the same, for a swing made **while walking** (a measurement new in round 2): **NOT MET** by any variant.
      - 457–474 ms here, 200–205 ms at depth 2 (100 ms, 1%).
      - Without loss it is 177–180 ms here.
    - OD1, "playable and server-authoritative at 200 ms; report actual limitations": authority unchanged.
      Limitations are below.
    - Owner safeguard "queue overflow must not create ... stale actions": overflow drops directions, never actions.
      But at 200 ms the walking backlog ages swing claims beyond the 600 ms window: 75–139 of 692–695 swings made
      while walking were stale (dropped, counted, shown as misses). That is **a cost of this design, reported**.
  - **Options for the owner (M4 checkpoint).** The chosen design meets every §4 criterion; it pays in walking
    lateness.

    | Option | §4 corrections criterion | Walking costs at 100 ms (peer view / swing) | 200 ms walking swings stale |
    |---|---|---|---|
    | A (chosen): depth 8, hold 1, standing rule | MET (0) | 516–541 / 457–474 ms | 75–139 of ~693 |
    | B: A plus the slow drain (one step back per second of a two-deep queue) | NOT MET on stairs (p95 7.5–35.6, max 64 px); movement 0; walking one-step corrections 217–225 | 372–397 / 316–343 ms | 30–46 |
    | C: depth 6, hold 1, standing rule | NOT MET on one seed (p95 7.5–15, max 15 px) | 459–463 / 392–399 ms | 8–13 |
    | D: round 1 (depth 2, hold 5, standing rule) | NOT MET (p95 37.5, max 45 px) | 260–266 / 200–205 ms | 7–11 |

    - Not built, for the owner's consideration: a client-side drain. While snapshots show the server some inputs
      behind, the window could skip one send: its avatar pauses 50 ms instead of being corrected. It needs the window
      to estimate the server's backlog from `ack` and its own send times. It is not measured.
  - **Also in round 2:**
    - **A swing pressed after a direction's input was built** (item 6). The window showed that swing from after the
      step, while the server ran it before (7.5 px off). Such an action now waits for the next input, which the server
      reads from where the window showed it (`Arena.riders`). Tested.
    - **Gaps the reviewer's mutants found are tested:**
      - an action never runs a step before its own input;
      - prediction through what a snapshot opened (the window's room copy never steps, so its own gate stays locked);
      - a second correction during a fade never moves the shown avatar;
      - every input labelled with the seq it goes as, over real sockets, N6 and N7;
      - take/use chosen from the predicted position, in both arenas.
    - **The probe** gained the `walking` scenario. It drives keys and swings through `mesh_net.demo.Arena` itself
      (press, act, outgoing), so the window's own rules are measured.
  - **Kept from round 1:**
    - The prediction is one `Prediction` for `SceneArena` and `WorldArena`.
    - A press builds the next input at once; the send rate stays one a tick.
    - Each snapshot rebuilds the avatar from the row (no hidden solver state carried; the deep-water note above) and
      walks the unread inputs again through the snapshot's solids.
    - x/y fades over 0.1 s exactly to zero; elevation and floor snap.
    - It starts at a welcome and when an N7 room first shows; it stops at every `enter` and at a session's end.
    - Every input carries `Feedback`'s reckoned tick (one estimate).
    - The M4-2 follow-ups: the reckoning pinned, `dropped_actions` in the probe, the repository test cited, the
      resume note.
  - **Owner safeguards, tested** (`tests/test_mesh_net_prediction.py`, the probe's virtual clock and link, seeds
    7/8/9).
    - Scenarios:
      - quick direction reversals (every 20–70 ms);
      - key release and a 30 ms tap;
      - attacks mashed while walking;
      - the cooldown, and jitter;
      - a 300 ms loss burst, a 1.2 s server stall and a 1.5 s outage;
      - N6 and N7 resume, and an N7 transfer with inputs waiting and in flight;
      - overflow at the queue's depth.
    - Each tick the server walks at most one step, only a direction the input it read gave (hold 1), in its sense. It
      stops once the keys are let go, and the window ends exactly on the server's row.
    - The reviewer's own `adversarial.py` (54 cases): 45 pass every assertion. The other 9, its "mash + reversals +
      1.2 s server stall" cases, fail only its `refused == 0` assertion: 2 swings shown during the stall are refused.
      That is M4-2's documented stall behaviour (at most 3, counted), identical on round 1's queue.
    - The server never walks beyond the inputs: at most 1.0 step of net displacement past them, against 4.0 steps on
      round 1's 5-tick lease.
  - **Immediate presentation and server-confirmed outcomes stay apart.** The local avatar's movement and its swing
    are presentation, immediate and corrected by the server's row. Hits, damage, HP, death, loot and every position
    on the wire are the server's. Nothing predicted is sent.
  - **Honest limitations at 200 ms (±10, 1%):**
    - Corrections (movement): 61–69 per seed run, median one step, max 15 px (p95 7.5–15). They come from
      retransmission holds longer than 8 ticks, whose oldest steps the queue drops.
    - On the stairs: 30–41, max 10.6–35.6 px, with 15–16 floor or height snaps.
    - After a release the avatar can be carried on later by those corrections: stop-after-release p95 386–471 ms.
    - Hits still confirm a round trip later: 269–273 ms standing, 585–593 ms for swings made walking.
    - Stale swings: 3–10 of 720 standing, and 75–139 of ~693 made while walking.
    - Peers see a walking player 657–666 ms late once a burst has been kept.
    - Moving targets are unchanged; they need M4-4 and M4-5.
    - These are simulation results; no claim about how it feels is made. That needs M4-6's rendered evidence and a
      person's play-test.

**M4-4 — enemies move on floors server-side (if OD7):**
- `FloorRoute`'s decision logic (route legs, waits, walk-out; `engine/behaviours/floor_route.py:82` onwards) moves
  into **one shared, graphics-free model**, as M1-A did for the floor solver. The behaviour and the authority both call
  it, with no duplicate.
- The authority runs it on `World.move`/`World.path`. Enemy rows carry position, elevation and floor (in v3 already,
  if OD7 is decided before M4-2). Movers it can't reproduce are refused at load (`scene_room.py:291-294`).
- **Acceptance:**
  - Single-player vs authority parity of a `FloorRoute` walk at equal deltas.
  - The probe's moving-target scenario on the real mover.
  - Replays unchanged.
- **As implemented** (owner decision OD7; no protocol change: v3's enemy rows `[id, hp, hit_seq, x, y, elevation,
  floor]` were already on the wire, static until now).
  - **One model.** `engine/hd2d/route.py`: `FloorRoute(route, speed, wait, on_stuck=, on_strand=)`, `from_config`,
    `parse_route`, and `update(world, body, dt, solids, sweep)`. It holds the route legs, the waits, walking out of
    water it can't stand in, stranding and backing off a point it can't reach, moved verbatim from the behaviour. It
    imports only `engine.hd2d.world`, `engine.physics_model` and the standard library, and moves any body `World.move`
    moves (a sprite, or the authority's `Body`).
    - **Single-player** (`engine/behaviours/floor_route.py`) is now a thin adapter. Each frame it hands the model the
      window's World and solid sprites, with the game's sweep. It writes the model's two reports to its log, and the
      strand report also as the `stranded` gameplay event.
    - **The authority** (`SceneRoom`): an enemy with `FloorRoute` in an HD-2D room gets a model at load
      (`Enemy.route`). Each tick, *before* the players, every live one walks 1/HZ s (`_walk_enemies`) through
      `World.path`/`World.move` with the authority's Arcade-free sweep. So this tick's hits and blocking use where the
      enemy is now. That holds in N6 and in every N7 instance (each instance is its own copy).
    - Players don't block enemies, as single-player's player (not solid) doesn't. A solid enemy blocks players where
      it stands now.
    - A dead enemy stops walking, and its loot is where it died.
  - **What can't be reproduced is refused at load**, with the reason:
    - an enemy that moves by any other behaviour (`MOVERS`: Patrol, Wander, ChaseTarget, EnemyAI and the rest);
    - a solid that moves at all;
    - an enemy whose route starts where it can't stand (single-player would walk it out first, or strand it with a
      gameplay event the room doesn't have).

    A `FloorRoute` in a 2D room moves nothing in either runtime, so it loads. A non-solid, non-enemy mover (for
    example the floors demo's warden) loads too: it blocks nothing, and the window stands it still, as before.
  - **Rows carry live positions.** A client's own room checks every row, and an enemy row is now checked as player
    rows are: the floor under it, sampled at the corners of the 0.01 px rounding (`floor_under`). Otherwise a walking
    enemy at a floor's edge could have its frame refused. The client's prediction blocks on solid enemies where the
    snapshot's rows put them (`SceneRoom.solids(state)`), not where the scene file did.
  - **Clients** show enemies as they show peers: `Playback.enemies`, two ticks behind, x/y/elevation interpolated,
    the nearer state's floor, never predicted. `SceneView.sync(..., enemies)` places the sprite there and sets the
    velocity its Animator walks by. Hit flashes still key off `hit_seq`.
  - **Single-player stays identical.**
    - `tests/test_floor_route_model.py` replays four traces recorded from the behaviour as it was at 94f1792c, before
      the extraction (`tests/fixtures/floor_route_traces.json`):
      - the floors demo warden's route at 1/20 s;
      - the same route blocked by a crate (it replans, then backs off once);
      - a deep-water walk-out at 1/60 s;
      - a stranding.

      Each trace matches at every sample, and a digest of every update matches.
    - Replays 13/13, no golden updated.
    - `git diff --stat` over `engine/` is the extraction only: `engine/hd2d/route.py` (new) and the adapter.
  - **Parity, single-player vs authority, at equal deltas** (`tests/test_mesh_net_moving_enemies.py`): an enemy
    walks 1,400 ticks across the crossing in both runtimes, and the per-tick x/y match to 1e-6 px, with the same
    elevation and floor every tick. The walk goes from the east platform over the bridge deck, down the west stairs,
    across the ground and up the east stairs. In the co-op room (2D), neither runtime moves it.
  - **No duplicate.** `tests/test_hd2d_net_parity.py`'s scan fails if `mesh_net` or the adapter defines a piece of
    the route model, or calls `path`, `ways_out` or `blocked` itself. A spy checks that both runtimes call
    `FloorRoute.update`. A fresh process walks a routed enemy without importing Arcade, pyglet, the game's physics
    runtime or the behaviour.
  - **#615 review gaps:**
    - (F02) `_forks` leaves the real body's position, floor and entity data untouched, on the stairs, where its walks
      climb.
    - (F05) The threshold is pinned: one step exactly is dropped; √2 and √5 steps are refused.
  - **A limitation of the shared walk, at the server's tick.**
    - `FloorRoute` spends the update that reaches each 0.5 m navigation waypoint standing. At 1/20 s that pause is
      50 ms; at single-player's 1/60 s it is 17 ms.
    - So the same authored speed walks slower online. Measured on the ground route: 70 px/s authored walks 52 px/s on
      the server, against about 64 px/s at 60 fps single-player *(computed)*. 150 px/s authored walks 88.6 px/s,
      against about 120 *(computed)*.
    - Parity holds at equal deltas, which is the acceptance. Making the walk frame-rate-independent would change
      single-player's trace, so it is not done here (a STOP condition). It is listed for the owner as a follow-up
      decision.
  - **Measurements** (`tooling/m4_latency_probe.py --queue drain|small|deep`, seeds 7/8/9 × 24 sessions, every
    profile; each cell is the range over the seeds). The moving-target scenarios now use **the real mover**: the
    co-op bandit walking a `FloorRoute` on the authority, shown through `Playback.enemies`. All are HD-2D, since
    `FloorRoute` moves nothing in 2D:
    - `moving_target_70` and `_150`: a still attacker on the crossing's open ground, facing east. The bandit walks east
      and west through its hitbox, at 70 or 150 px/s as authored (52 and 88.6 px/s on the server).
    - `moving_both`: the attacker walks up to the walking bandit (70) and away, turning every 700 ms, predicted.
    - `stairs_moving`: the bandit walks up and down the west stairs (70), with a still attacker on the ground beside
      their east edge. Its hitbox covers where the bandit climbs out of `same_level`'s 1.5 m reach.
    - Each scenario samples every frame as a hypothetical press, as before. A disagreement is put down to one cause:
      - the **floor rule** (`same_level` differs between the shown and the real poses);
      - else the **target's motion** (the real attacker against the targets as shown agrees with the screen);
      - else the **attacker's motion** (the attacker as shown against the real targets agrees);
      - else **both**.
    - Real swings about every 600 ms go through the window's own handling (`Arena.act`, `Feedback`) and are followed
      to the server: started, or never executed (stale, refused, dropped). Each hit is confirmed at the first frame
      that shows the state of the tick it hit on.
    - Both hit questions ask the hitbox's **first** update. The persistent hitbox's later two ticks (OD10) are not in
      the fairness numbers.
    - The 2D static-enemy scenarios (`movement`, `attack`, `walking`, `moving_attacker`, `stairs`) are unchanged by
      M4-4. Their drain numbers equal M4-3 round 4's, to the number. For example: stairs corrections 243–309 at
      100 ms, peer view while walking 270–291 ms, standing hit p50 166.0–175.9 ms, walking drained 382–435.

    **drain (PROVISIONAL default).** Disagreement, % of all sampled presses: *total (target / attacker / floor rule /
    both)* [with an ideal rewind bound]:

    | Scenario | 0 (none) | 0 ±10 1% | 50 ±10 1% | 100 ±10 1% | 200 ±10 1% | 100 ±10, no loss |
    |---|---|---|---|---|---|---|
    | moving target 70 (52 px/s) | 6.0–6.1 (all target) [0] | 6.4–6.5 [0] | 8.1–8.5 [0] | **10.2–10.3 (all target) [0]** | 14.2–15.4 [0] | 9.6–9.8 [0] |
    | moving target 150 (88.6 px/s) | 11.3–11.6 (all target) [0] | 12.0–12.1 [0] | 15.9–16.1 [0] | **19.8–20.1 (all target) [0]** | 27.3–28.3 [0] | 18.7–19.0 [0] |
    | moving both | 3.3–3.4 (2.6 / 0.7–0.8 / 0 / 0) [0.7–0.8] | 3.7–4.2 [0.9–1.2] | 4.4–4.7 [1.1–1.2] | **4.8–5.5 (4.0–4.6 / 0.6–0.7 / 0 / 0.1–0.2) [1.2–1.5]** | 6.4–7.4 (5.5–6.4 / 0.6–0.7 / 0 / 0.3–0.4) [1.4–1.8] | 4.5–4.6 [0.7–0.8] |
    | stairs, moving enemy | 16.0–16.3 (8.8–9.0 / 0 / 7.1–7.3 / 0) [0] | 17.5–18.2 [0] | 22.8–23.5 [0] | **28.2–29.6 (14.3–15.2 / 0 / 13.8–14.4 / 0) [0]** | 38.2–39.7 (19.8–20.9 / 0 / 18.3–18.9 / 0) [0] | 27.6–27.8 [0] |
    | (2D) attacker walks to a still enemy | 1.5–1.7 (all attacker) | 1.8–2.3 | 2.3–2.7 | 2.3–3.0 | 2.4–2.8 | 1.7–1.9 |
    | stairs, still enemy, attacker strafing | 0 | 1.2–1.3 | 2.1–2.3 | 2.1–2.7 (0 / 1.0–1.3 / 1.1–1.4 / 0) | 1.2–1.5 | 0 |

    Seen as a hit but missed / seen as a miss but hit, % of each:

    | Scenario | 0 (none) | 100 ±10 1% | 200 ±10 1% |
    |---|---|---|---|
    | moving target 70 | 16.4–16.7 / 3.7 | 27.3–27.8 / 6.3–6.5 | 37.7–39.7 / 8.9–9.8 |
    | moving target 150 | 25.2–25.8 / 7.6–7.8 | 45.8–46.4 / 12.8–13.0 | 62.9–64.0 / 17.7–18.8 |
    | moving both | 20.3–20.9 / 1.2–1.3 | 26.9–33.1 / 2.1–2.3 | 40.3–41.3 / 2.4–3.4 |
    | stairs, moving enemy | 39.3–40.2 / 9.6–9.9 | 68.8–70.5 / 17.2–18.4 | 92.9–93.3 / 23.5–25.2 |

    Hit confirmation, p50 / p95 ms (hits):

    | Case | 0 (none) | 0 ±10 1% | 50 ±10 1% | 100 ±10 1% | 200 ±10 1% | 100 ±10, no loss |
    |---|---|---|---|---|---|---|
    | standing, still enemy (2D `attack`: HP drop seen) | 61.8–65.7 / 94–103 | 72.0–77.3 / 127–210 | 115–123 / 213–267 | **166.0–175.9** / 369–385 | 269–273 / 561–596 | 163.7–171.4 / 206–208 |
    | walking swing, still enemy (2D `walking`: its tick seen) | 65–70 / 98–110 | 120–123 / 258–263 | 165–173 / 345–357 | **210–229** / 449–469 | 321–325 / 604–616 | 177–180 / 216–225 |
    | standing, moving enemy 70 (48 hits) | 62–66 / 95–108 | 67–82 / 122–281 | 110–117 / 161–355 | **160–174** / 214–237 | 273–276 / 552–634 | 163–176 / 202–213 |
    | standing, moving enemy 150 (55–89 hits) | 59–64 / 94–103 | 68–78 / 121–160 | 115–130 / 182–241 | **164–173** / 244–394 | 261–273 / 314–450 | 160–167 / 196–205 |
    | walking, moving enemy (12–27 hits) | 51–61 / 80–93 | 101–133 / 223–296 | 170–182 / 308–388 | **228–251** / 415–531 | 319–365 / 579–796 | 183–195 / 238–275 |
    | standing, enemy on the stairs (66–72 hits) | 56–71 / 101–120 | 67–71 / 123–200 | 119–132 / 183–246 | **167–168** / 239–360 | 253–267 / 316–615 | 161–167 / 200–208 |

    Swings shown but never executed (all stale: a claim older than the 600 ms window; none refused, none dropped).
    With the 2D ones (720 standing, about 693 walking), that is **0 for every case up to 100 ms ±10 1%** and with
    jitter alone:

    | Case | 200 ±10 1% |
    |---|---|
    | standing, still enemy (2D) | 3–10 of 720 |
    | walking, still enemy (2D) | 17–25 of 692–695 |
    | moving target 70 / 150 / stairs (standing) | 1–7 of 192 each |
    | moving both (walking) | 3–10 of 192 |

    Discarded movement steps (overflow / drained), inputs sent per seed run: movement about 28,550, walking about
    9,600:

    | Scenario | 0 (none), jitter alone | 0 ±10 1% | 50 ±10 1% | 100 ±10 1% | 200 ±10 1% |
    |---|---|---|---|---|---|
    | movement | 0 / 0 | 0 / 88–90 | 0 / 74–112 | 0 / 114–133 | 262–282 / 148–157 |
    | walking | 0 / 0 | 0 / 220–242 | 0 / 304–328 | 0 / 382–435 | 95–105 / 409–481 |
    | moving both | 0 / 0 | 0 / 132–146 | 0 / 187–204 | 0 / 257–290 | 54–65 / 214–301 |

    How a moving enemy looks (moving target, the window's frames). Frozen frames include the walk's own waypoint
    pauses: 18.5% and 31.9% of frames at 0 ms.

    | | 0 (none) | 0 ±10 1% | 100 ±10 1% | 200 ±10 1% | 100 ±10, no loss |
    |---|---|---|---|---|---|
    | 70: frozen frames / longest freeze ms / frames over twice a step | 18.5% / 100 / 0 | 18.5–19.0% / 200–250 / 45–61 | 16.7–17.8% / 333–350 / 82–100 | 18.1–19.4% / 417–433 / 76–90 | 13.5–13.8% / 100 / 29–43 |
    | 150: the same | 31.9% / 100 / 0 | 30.1–30.8% / 250–267 / 47–58 | 26.1–27.0% / 350 / 62–84 | 27.3–28.3% / 433–450 / 65–76 | 23.1–23.2% / 100 / 17–21 |

    - At 0 ms the walk on screen is the server's walk two ticks late, waypoint pauses and all. Under loss it freezes
      for up to one retransmission, then catches up in a jump, exactly as a peer does (§2.5).
    - The window's frames run at 60 fps against 20 Hz states, interpolated, so a 50 ms pause shows as 3 frozen frames.

    **Corrections near a moving solid enemy (new; `moving both`)**:
    - The prediction blocks on the enemy where the last snapshot had it. The server has walked it on since: up to one
      of its steps by the tick that reads the input, plus the latency.
    - So a player pushing against a walking solid enemy is corrected on most snapshots. With no loss: 255–260
      corrections at 0 ms and 427–437 at 100 ms ±10 ms, each at most 3.5 px (one bandit step).
    - Under loss a few are large: at 100 ms ±10 1%, max 7.5–99 px and 0–0.23 large ones a minute; at 200 ms, max
      93–128 px and 0.45–1.14 a minute.
    - *(Inferred:)* the enemy walks into and through a player (players don't block enemies, in either runtime). A
      player inside a solid enemy's box then slides out differently in the replay and on the server.
    - Not fixed here: it would take predicting enemies (they are server-authoritative, never predicted, by the brief)
      or players blocking enemies (single-player's player doesn't).
    **The three presets** (same seeds, every profile).
    - **Identical in all three, to the number:** the still-attacker scenarios. That covers moving target 70 and 150
      and the enemy on the stairs, for fairness, causes, hit confirmation and swings never run. A standing player's
      queue is emptied by the standing rule in every preset. Standing hit confirmation is identical too.
    - The 2D static-enemy rows equal each preset's own M4-3 round-3/4 numbers. For example, at 100 ms the peer view
      while walking is 270–291 ms (drain), 260–266 (small) and 516–541 (deep).
    - **Where the presets differ:** a walking attacker. The values are drain / small / deep:

    | At 100 ms ±10 1% (and 200 ms) | drain (PROVISIONAL) | small | deep |
    |---|---|---|---|
    | Moving both: disagreement % (target / attacker / both) [ideal rewind] | 4.8–5.5 (4.0–4.6 / 0.6–0.7 / 0.1–0.2) [1.2–1.5] | 4.3–4.7 (3.2–3.4 / 0.7–1.0 / 0.2–0.4) [1.3–1.6] | 7.2–7.7 (6.6–7.0 / 0.4 / 0.1–0.2) [0.5–0.7] |
    | ... at 200 ms | 6.4–7.4 [1.4–1.8] | 6.5–7.4 [2.1–2.7] | 8.2–9.1 [0.8–1.0] |
    | Moving both: seen as a hit but missed % | 26.9–33.1 | 25.6–27.3 | 53.7–61.9 |
    | Walking swing confirmed p50 / p95 ms, still enemy | 210–229 / 449–469 | 200–205 / 348–394 | 457–474 / 517–566 |
    | Walking hit on a moving enemy, p50 / p95 ms | 228–251 / 415–531 | 197–210 / 265–523 | 451–487 / 500–589 |
    | Swings shown, never executed: 0 at 0–100 ms in every preset; at 200 ms, walking (2D) / moving both | 17–25 of ~693 / 3–10 of 192 | 7–11 / 1–8 | 75–139 / 18–35 |
    | Discarded steps, overflow / drained: movement, walking, moving both | 0/114–133, 0/382–435, 0/257–290 | 1393–1502/0, 457–547/0, 313–358/0 | 0/0, 0/0, 0/0 |
    | ... at 200 ms | 262–282/148–157, 95–105/409–481, 54–65/214–301 | 1877–2031/0, 651–737/0, 344–456/0 | 262–284/0, 103–109/0, 60–67/0 |
    | Corrections near the moving enemy (moving both): n, max px, large a minute | 732–796, 7.5–99, 0–0.23 | 768–827, 94.5–109.5, 11.1–13.0 | 449–468, 3.5, 0 |
    | ... at 200 ms | 941–1107, 93–128, 0.45–1.14 | 955–1122, 109.5–133.5, 8.2–11.8 | 705–720, 93–128, 0.45–0.91 |

    - Under deep, a walking attacker's backlog makes its attacks land later. So the target has moved further by then,
      and target-caused disagreement is higher (6.6–7.0% against 4.0–4.6%).
    - Under small, the dropped steps add corrections (11–13 large a minute beside the moving enemy).
    - Drain sits between them.
    - None of this changes the M4-3 verdict: **all three presets still fail important criteria, so no winner is
      declared, and drain stays PROVISIONAL**, to be judged by the owner playing all three:
      - OD1's walking-swing confirmation is missed by every preset;
      - deep breaks condition 6;
      - small fails the correction criteria.
    - M4-4 adds no new failure that separates them. Swings never executed stay 0 within OD1's envelope in all three.
      At 200 ms they are reported, not accepted (all stale; none refused, none dropped).

  - **The M4-5 question: does moving-target disagreement at OD1's envelope justify lag compensation?** The numbers,
    at 100 ms ±10 ms 1% (identical in every preset for a still attacker):
    - **Target motion is now the dominant cause.**
      - A still attacker against a walking bandit: 10.2–10.3% of presses disagree at 52 px/s and 19.8–20.1% at
        88.6 px/s, every one caused by the target's motion.
      - On the stairs: 28.2–29.6%, about half from the target's motion and half from the floor rule as the target
        climbs through `same_level`'s reach.
      - Of what looked like a hit, 27.3–27.8%, 45.8–46.4% and 68.8–70.5% missed.
      - With M4-3's prediction, the attacker's own share is small: 0.6–0.7% in moving both, 2.3–3.0% for the 2D
        walk-up.
    - **Latency's own part.** At 0 ms the same scenarios disagree 6.0–6.1%, 11.3–11.6% and 16.0–16.3%. That floor
      comes from showing the enemy two ticks behind (Playback) plus the tick quantisation. So 100 ms adds about 4, 8
      and 13 points.
    - **What a rewind could remove.** The ideal rewind bound (the real attacker against the targets as shown) is 0% in
      all three. It would also remove the floor-rule part on the stairs, since the target's elevation would be the
      one shown. In moving both it leaves 1.2–1.5%: the attacker's share.
    - **Caveats.**
      - The bound is not a measurement of an implementation.
      - The rewind needed at 100 ms is the uplink (about 50 ms), the two-tick display delay (100 ms) and up to a tick
        of quantisation, so about 150–250 ms *(inferred)*. That is inside OD5's 300 ms cap. At 200 ms it would reach
        the cap.
      - These are the probe's adversarial walks, through the hitbox. Real fights will vary.
      - The judge asks the hitbox's first update. The persistent hitbox's two later ticks already forgive some misses
        on the server (an enemy walking into the swing).
    - **Recommendation (for the owner to decide or escalate): the measurements support approving M4-5.**
      - At OD1's 100 ms envelope, between a quarter and a half of the presses that look like hits on a walking enemy
        miss, and about 70% beside stairs. Target motion, which only lag compensation addresses, causes essentially
        all of it.
      - Without a rewind, the reachable improvement is the 0 ms floor (6–16%). Only a shorter interpolation delay or a
        higher tick rate would lower that.
      - The plan sets no numeric "owner's budget", so whether these numbers exceed it is the owner's call. If the
        owner judges 10–30% disagreement on walking enemies acceptable for the co-op prototype, M4-5 can stay unbuilt.
      - The 600 ms claim window's condition 4 stands either way: today, hits use the current server geometry only.

**M4-5 — lag compensation (d), only if M4-4's measured moving-target disagreement at OD1's envelope exceeds the
owner's budget:**
- Rewind history, `view_tick`, and the OD5 cap.
- **Acceptance:** same-seed probe under the budget; cap and cross-floor tests.
- **Owner decision, 2026-11-25, quoted verbatim:**

  > "M4-5 APPROVED. The measured disagreement rates against moving enemies justify implementing bounded server-side
  > lag compensation for the cooperative PvE prototype.
  > Authorized design
  > * Rewind enemy positions only, never the attacker.
  > * Maximum historical rewind: 300 ms (6 server ticks).
  > * Retain the separate 600 ms delayed-attack-input allowance.
  > * Use the existing protocol v3 `view_tick`; no protocol v4.
  > * The server remains authoritative over attack execution, hit detection, damage, cooldowns and death.
  > * Single-player behaviour and existing replay recordings remain unchanged.
  > Mandatory safeguards
  > * Validate the client's requested historical time against authoritative server history.
  > * Never accept future timestamps or permit unbounded rewind.
  > * Preserve floor-aware reach, collision and obstruction checks, including bridge decks and stairs.
  > * Historical targets must belong to the same valid room instance.
  > * Do not reuse history across transfers, despawns, respawns or invalidated entity identities.
  > * Handle missing or insufficient history conservatively, without inventing a hit.
  > * Keep historical data bounded in memory and deterministic in tests.
  > * Document the cheating and fairness limitations before any public deployment.
  > Acceptance
  > Measure actual implementation results against the existing non-compensated baseline at 0, 50, 100 and 200 ms RTT,
  > including jitter and 1% loss.
  > Test stationary and moving attackers, moving enemies, stairs, bridge decks, room transitions and the 300 ms boundary.
  > Use independent review, mutation proofs, CI and Extended. Do not weaken tests to meet a target.
  > Report measured improvements and remaining disagreement honestly. The ideal rewind result is a theoretical bound,
  > not an assumed outcome."

- **As implemented** (`mesh_net/scene_room.py`: `REWIND_CAP`, `SceneRoom.history`, `_remember`, `_judged_at`,
  `_rewound`, `_strike`; `mesh_net/playback.py`: `between`). No protocol change: v3's optional `view_tick` on attack
  inputs was already on the wire (`mesh_net/protocol.py`'s note on it is updated, documentation only).
  - **What the client sends.** On Space, `SceneArena.press` and `WorldArena.press` queue the attack with
    `Playback.cursor`: the tick, with its fraction, that the frame on screen showed the enemies at. The cursor is
    updated at each draw, so a key read at the next dispatch carries what the player was looking at. It rides the
    attack in the window's action queue (`Arena.actions` entries are now `(action, tick, view)`), so a view never
    outlives its attack or crosses into another room or session (both clear the queue). `wire.input_frame(...,
    view_tick=)` is the one builder.
    - *Conservative mapping:* the cursor is never ahead of the newest state received, so an honest view is never ahead
      of the server's tick. Before the window's first draw in a room its cursor is 0, which the server judges as "now"
      (counted as `unseen_views`).
  - **What the server keeps.** Each room instance (the N6 room, and each N7 instance, which is its own deep copy) keeps
    `history`: a `deque(maxlen=REWIND_CAP + 1)` holding, for each of the last 7 ticks, each **live** enemy's pose
    exactly as that tick's snapshot row carries it (x/y to 0.01 px, elevation to 0.001 px, floor), together with the
    `Enemy` object it belongs to.
    - It is taken right after `_walk_enemies` each tick (enemies move nowhere else) and once at load.
    - It is bounded (7 ticks × live enemies) and deterministic (tested: two rooms stepped alike keep equal histories).
    - With rewind off it keeps nothing.
  - **How a view is validated** (`_judged_at`, on the tick the attack starts; counters are diagnostics, never on the
    wire):
    - no view, or rewind off: judged now, exactly as before M4-5;
    - a view ahead of this tick: judged now (`future_views`). It could not select anything anyway: history never holds
      a future tick;
    - a view from before the attacker **joined this room instance** (`Player.joined`, set by every `join`: a
      transfer, a resume, a first join): judged now (`unseen_views`). No state of that instance was the player's then;
    - a view more than 6 ticks (300 ms) back: **clamped** to 6 ticks back (`clamped_views`), as OD5 recommended
      ("clamp, never refuse"). An honest window that far behind (a TCP retransmission stall) is judged at the nearest
      pose allowed, which is nearer what it saw than the pose now; a liar gains nothing beyond the window either way;
    - otherwise the view itself.
  - **How the targets are rewound** (`_rewound`). For a time *t*, the poses of ticks floor(*t*) and ceil(*t*) are
    interpolated by `playback.between`, the very function `Playback.enemies` draws with, on the same rounded rows. The
    server judges the pose the window drew, to the bit (tested). An enemy is rewound only if both ticks hold a pose of
    **the same `Enemy` object** (an id reused by a new enemy, a respawn, or an enemy dead in either tick never
    matches). Otherwise, and whenever history lacks either tick, that enemy is judged where it is now: **nothing is
    made up from a neighbouring pose**.
  - **The hit test is the one that ran before** (`_strike`): `shapes_overlap(hitbox, entity_shape(target))` and
    `same_level(attacker, target)`. Only `target` changes, from the enemy's body to its rewound pose.
    - The hitbox is made where the attacker stands **now**, and the level is asked of the attacker as it stands now.
      The attacker is never rewound; no player pose is kept at all.
    - Floors, stairs and bridge decks are judged at the rewound pose by the same rule (`same_level`'s vertical reach
      and its floor-between check).
    - Damage, death, drops (where the enemy is now), hit counters and the cooldown are this tick's. An enemy dead now
      is never hit through history; a hitbox hits each enemy once.
  - **OD10's later ticks.** The hitbox checks on 3 ticks. Each later update judges the targets **the same time behind**
    as its first (*t* + ticks since it was made), since the window's view goes on lagging by as much. That stays within
    the 6 kept ticks by construction.
  - **The 600 ms claim window is untouched.** The input's `tick` still judges only the cooldown; only `view_tick`
    selects a past pose (tested: an old claim with no view is judged now).
  - **Switchable, for the same-seed baseline:** `SceneRoom(..., rewind=)`, `World(..., rewind=)`,
    `python -m mesh_net.server --rewind on|off` (else `MESH_NET_REWIND=1|0`, else on), and the probe's `--rewind off`.
    The default is on.
  - **Single-player is untouched:** nothing under `engine/` changed. Replays 13/13, no golden updated.
  - **With rewind off the implementation is the M4-4 baseline, to the number.** The extracted `a4465258` probe and this
    branch's `--rewind off` give identical results on seed 7 × 24 sessions for moving target 70, moving both and stairs
    moving, at 100 and 200 ms ±10 ms 1%: every count equal. The window now sends its view; the server ignores it.

  - **Measurements: the implementation against the non-compensated baseline.** Method: `tooling/m4_latency_probe.py
    --queue Q --rewind on|off --seeds S --sessions 24 --scenarios ... --profiles ...`, seeds 7/8/9 run one at a time,
    24 sessions each. The baseline is this branch with `--rewind off`, which equals M4-4 to the number (above).
    - **The "real" answer is now the authority's own.** For every sampled frame (a hypothetical press), the probe asks
      the server's `_attack` with the view tick that frame's press would carry, on the landing tick's actual history.
      It is no longer a re-derivation.
    - "Ideal" is still the theoretical bound: the real attacker against the targets exactly as shown.
    - Each cell is [lowest, highest] over the three seeds. Every sampled frame is a press: about 15,790 per seed per
      scenario (2,860 for `arrival`). Real swings: 192 per seed (48 for `arrival`).
    - New scenarios:
      - `bridge`: a still attacker on the bridge deck; the bandit walks the deck through its hitbox.
      - `under_bridge`: the same walk over a still attacker on the ground under the deck. It must never be hit.
      - `arrival`: a room transition. The player joins an instance whose bandit has walked 1–4 s, and swings from
        the first frame.
    - 300 ms ±10 1% is added as the boundary profile, where nearly every view is beyond the cap.

    **Disagreement**, % of all sampled presses, drain (provisional default), baseline → **M4-5**. For moving both,
    the ideal bound is in brackets; it is 0 everywhere else.

    | Scenario | 0 (none) | 0 ±10 1% | 50 ±10 1% | 100 ±10 1% | 200 ±10 1% | 300 ±10 1% (boundary) |
    |---|---|---|---|---|---|---|
    | moving target 70 (52 px/s) | 6.0–6.1 → **0** | 6.4–6.5 → **0–0.1** | 8.1–8.5 → **0.2** | 10.2–10.3 → **0.4–0.6** | 14.2–15.4 → **2.9–3.6** | 18.9–19.6 → **7.2–8.5** |
    | moving target 150 (88.6 px/s) | 11.3–11.6 → **0** | 12.0–12.1 → **0.1** | 15.9–16.1 → **0.1–0.5** | 19.8–20.1 → **0.6–1.5** | 27.3–28.3 → **5.4–7.2** | 34.6–36.5 → **14.3–15.4** |
    | moving both (walking attacker) | 3.3–3.4 → **0.7–0.8** [0.7–0.8] | 3.7–4.2 → **1.0–1.2** [0.9–1.2] | 4.4–4.7 → **1.2–1.4** [1.1–1.2] | 4.8–5.5 → **1.4–1.6** [1.2–1.5] | 6.4–7.4 → **2.1–2.8** [1.4–1.8] | 7.4–8.0 → **4.2–4.8** [2.4–3.3] |
    | stairs, moving enemy | 16.0–16.3 → **0** | 17.5–18.2 → **0.1** | 22.8–23.5 → **0.2–0.5** | 28.2–29.6 → **1.3–1.5** | 38.2–39.7 → **7.6–8.3** | 40.8–41.6 → **18.7–21.3** |
    | bridge deck, moving enemy | 6.0–6.1 → **0** | 6.4–6.5 → **0–0.1** | 8.0–8.5 → **0.2–0.3** | 10.2–10.4 → **0.4–0.7** | 14.3–15.2 → **3.2–3.4** | 19.3–19.4 → **7.8–7.9** |
    | under the deck (never in reach) | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 |
    | arrival (room transition) | 6.2–7.5 → **0** | 8.8–10.1 → **0–0.2** | 10.2–14.0 → **0–0.4** | 14.0–17.2 → **0.1–1.4** | 12.8–21.7 → **2.0–5.2** | 26.0–27.7 → **9.6–12.4** |

    - **Within OD1's envelope (100 ms ±10 ms 1%)** the remaining disagreement is 0.4–1.5% for a still attacker. On the
      stairs it is 1.3–1.5%, of which 0.4–0.9 points are the floor rule. With a walking attacker it is 1.4–1.6%, of
      which 1.0–1.2 points are the attacker's own motion, which rewinding never addresses (the ideal bound is
      1.2–1.5%).
    - **What remains comes from views beyond the cap.** At 100 ms, 9.0–10.5% of a still attacker's presses need more
      than 6 ticks (every one during a TCP retransmission stall). They are clamped, and 3.7–16.6% of those still
      disagree. Every remaining disagreement for a still attacker is target-caused or floor-caused at a clamped
      view; the attacker causes none.
    - **The rewind needed is larger than §4 M4-4 inferred.** It is the whole round trip: the view is half a round trip
      old when shown, and the attack lands half a round trip later. Add the two-tick display delay and up to about two
      ticks of send and tick quantisation.
      - Share of a still attacker's presses beyond 300 ms: 0 at 0 ms; 1.4–1.5% at 0 ms ±10 1%; 4.9–5.0% at 50 ms;
        9.0–10.5% at 100 ms; **97.8–99.2% at 200 ms**; 100% at 300 ms.
      - At 200 ms almost every view is clamped to 300 ms back. That still removes three quarters of the disagreement
        (14.2–15.4% → 2.9–3.6% at 52 px/s), because 300 ms back is far nearer what the window showed than now is.
        It is not the ideal bound.
    - **A walking attacker clamps more often under queues that delay its attacks.** The server runs an attack only on
      the tick that reads its own input, so a backlog adds lag. Beyond the cap at 100 ms: drain 37.9–53.3%, deep
      73.6–78.4%, small 18.6–29.9%.

    **Looked like a hit but missed / looked like a miss but hit** (the second is "hits the player didn't see", which a
    rewind can create; the count is presses per seed with M4-5), baseline → M4-5:

    | Scenario | 100 ±10 1% | 200 ±10 1% |
    |---|---|---|
    | moving target 70 | 27.3–27.8 / 6.3–6.5 → 0.6–1.9 / 0.2–0.3 (31–43) | 37.7–39.7 / 8.9–9.8 → 8.5–9.8 / 1.6–2.3 (204–297) |
    | moving target 150 | 45.8–46.4 / 12.8–13.0 → 1.2–2.7 / 0.5–1.2 (58–152) | 62.9–64.0 / 17.7–18.8 → 10.8–15.6 / 3.9–4.9 (483–603) |
    | moving both | 26.9–33.1 / 2.1–2.3 → 11.3–12.0 / 0.2–0.4 (21–58) | 40.3–41.3 / 2.4–3.4 → 13.3–17.4 / 0.8–1.3 (117–186) |
    | stairs, moving enemy | 68.8–70.5 / 17.2–18.4 → 3.2–4.2 / 0.6–1.0 (78–128) | 92.9–93.3 / 23.5–25.2 → 19.4–20.8 / 4.5–5.1 (557–624) |
    | bridge deck | 25.0–26.0 / 6.2–6.6 → 1.4–2.3 / 0.1–0.3 (16–33) | 33.7–37.7 / 9.2–10.0 → 7.9–8.8 / 1.9–2.1 (237–260) |
    | arrival | 21.7–25.4 / 11.0–14.6 → 0.5–2.4 / 0–1.7 (0–36) | 27.7–37.4 / 10.1–17.4 → 4.5–8.0 / 1.5–5.0 (34–100) |

    - Hits the player didn't see still happen with M4-5: 0–1.7% of presses that looked like misses at 100 ms, and
      0.8–5.1% at 200 ms (from clamped views). The baseline's are 2.1–18.4% and 2.4–25.2%. The counts are net per
      run: which of them the rewind itself created was not paired press by press.
    - **0 at 0 ms with no loss**, in every scenario except moving both, where the remaining part is the attacker's own
      motion.
    - **Under the deck: 0 hits taken**, on or off, at every profile: the deck's 2 m is never within reach.
    - **On the deck:** 47–50 hits taken against 48 without rewind (192 swings).
    - **Views never refused unseen** (`unseen_views` = 0 everywhere, `arrival` included): an honest window never sends
      a view from before it joined. `future_views` = 0 everywhere.

    **Real swings, and how soon a hit shows** (still attacker unless named; drain):
    - **Swings shown but never executed are unchanged by M4-5**, which never touches the cooldown or the claim window:
      - 0 up to 100 ms;
      - at 200 ms, 1–7 of 192 (moving both 3–10);
      - at 300 ms, 7–10 (moving both 19–26).

      All are stale claims, as before.
    - **Hit confirmation, p50 / p95 ms, 100 ±10 1%:**

      | Case | Baseline | M4-5 |
      |---|---|---|
      | moving target 70 | 159.5–173.5 / 213.7–237.2 | 165.8–180.3 / 276.5–299.7 |
      | stairs | 166.7–168.4 / 238.9–360.2 | 181.4–187.7 / 391–415.5 |
      | bridge | 159.5–173.5 / 221.7–237.2 | 178.6–181.8 / 252–295.6 |
      | moving both | 227.5–250.6 / 414.9–531 | 225.5–237.3 / 414.1–522.8 |

      - At 0 ms with no loss, the moving target 70 p95 is 94.5–107.7 → 157.7–198.8.
      - **Why confirmation is later (measured by the #626 reviewer):** the hits are a different set, and more of them
        land on the persistent hitbox's second and third updates (OD10), since a target judged several ticks back
        reaches the box later in its rewound walk. At 100 ms ±10 ms 1% over 12 sessions: without rewind every real hit
        landed on hitbox update 1; with rewind 5 of 21 confirmed hits (moving target 70) and 8 of 29 (stairs) landed on
        updates 2–3. So the median moves 6–19 ms and the p95 40–90 ms later.
      - **OD1's "median hit confirmation at most RTT + 75 ms" (175 ms)**, for a still attacker against a moving enemy,
        is now missed:
        - on every seed on the stairs (by up to 12.7 ms) and on the deck (by up to 6.8 ms);
        - on at least one seed against moving target 70 (by up to 5.3 ms).

        Without rewind it was met there (159.5–173.5). The 2D standing attack (166.0–175.9) has no moving enemy and is
        unchanged. Reported, not hidden: the owner may weigh fairness against these milliseconds.

    **The three queue presets** (moving both, the only scenario where they differ; disagreement baseline → M4-5):

    | Preset | 0 ±10 1% | 50 ±10 1% | 100 ±10 1% | 200 ±10 1% | 300 ±10 1% |
    |---|---|---|---|---|---|
    | drain (provisional) | 3.7–4.2 → 1.0–1.2 | 4.4–4.7 → 1.2–1.4 | 4.8–5.5 → 1.4–1.6 | 6.4–7.4 → 2.1–2.8 | 7.4–8.0 → 4.2–4.8 |
    | deep | 5.1–5.3 → 1.3–1.4 | 5.8–6.2 → 1.8–2.1 | 7.2–7.7 → 2.9–3.5 | 8.2–9.1 → 4.4–4.9 | 9.3–10.2 → 6.1–6.8 |
    | small | 3.7–3.9 → 0.9 | 3.6–4.2 → 0.8–1.1 | 4.3–4.7 → 1.4–1.6 | 6.5–7.4 → 2.7–3.0 | 7.1–7.7 → 4.1–4.9 |

    Deep keeps the most residual, because its backlog lags the attack beyond the cap. Still-attacker scenarios are
    identical in all three presets (the standing rule empties the queue).

    **The history's cost** (report-only; Python 3.13, this PC, best of 5, the crossing room):
    - 1 walking enemy: one tick takes 45.3 → 51.1 µs; history 7 ticks, about 3.3 KB.
    - 1 walking plus 20 standing enemies: one tick takes 105.3 → 141.5 µs; history about 26.5 KB.
    - Taking a tick's poses costs 2.1 µs (1 enemy) and 36.8 µs (21 enemies).
    - An attack with a view takes 4.0 → 6.4 µs (1 enemy) and 58.8 → 82.8 µs (21 enemies).
    - At 20 Hz that is under 0.1% of a core per room instance, and at most 8 instances × 26.5 KB.

    **Against the owner's acceptance:**
    - Measured against the baseline at 0, 50, 100 and 200 ms with jitter and 1% loss, plus 0 ms with no loss and the
      300 ms boundary: **done, above**.
    - Scenarios: still and moving attackers, moving enemies, stairs, bridge decks (on and under), room transitions,
      the 300 ms boundary: **done**.
    - Tests (`tests/test_mesh_net_lag_compensation.py`) cover:
      - the view judging then;
      - the attacker never rewound;
      - future views;
      - the cap, and clamping rather than refusing;
      - no view before the join;
      - another identity;
      - missing history;
      - dead now;
      - the later ticks' lag;
      - the drawn pose to the bit;
      - stairs and the deck at the rewound pose;
      - the wire path;
      - N7 instances and transfers;
      - the switch;
      - a bounded, deterministic history;
      - the send loop over a real socket.
    - **Mutation proof: 25 lag-compensation mutants, all killed** (listed in the PR), plus the owed rounding
      tolerance's (0.01, 0.015 and 0.03 px, killed).
    - Independent review, CI and Extended: on the PR.
    - **Remaining disagreement, honestly:**
      - 0.4–1.5% for a still attacker at 100 ms, up to 7.6–8.3% on the stairs at 200 ms and 18.7–21.3% at 300 ms;
      - nearly all of it from views beyond the 300 ms cap;
      - with a walking attacker, its own motion (about 1 point) on top.
    - The ideal bound remains a bound: the implementation reaches it within OD1's envelope only where the view is
      within the cap.

**M4-6 — rendered evidence:**
- A small asyncio TCP delay proxy in `tooling/`. Two hidden windows (non-activating hook) at 100 and 200 ms.
  Framebuffer evidence of the local swing, prediction, confirmed hit, and a transfer under latency.
- Descriptive timings only.
- **M4-6 groundwork as implemented** (the proxy, the capture harness and one trial; **not** the final evidence set,
  which waits for the owner's M4-5 decision; no rewind or historical hit validation anywhere: hits stay judged at the
  server's current positions).
  - **Two review follow-ups from #616.**
    - *A drop lies where the server measures a take from.* `SceneView` placed a new drop marker at the enemy's
      sprite, which `Playback` shows two ticks behind, and never moved it; `near_drop` measured from that sprite too.
      A walking enemy's marker could sit 5–9 px from the server's drop, so E could pick use instead of take (or the
      reverse) at the edge of the pickup reach. Now both come from the enemy's row in the same state
      (`SceneView.drops_at`: where it died; `SceneRoom._take` measures from that body). One path serves both arenas
      (`world_client` calls the same `near_drop`). Test:
      `test_mesh_net_moving_enemies.py::test_a_drop_lies_where_the_state_says_its_enemy_died` (fails before the fix).
    - *`floor_under`'s rounding tolerance has an upper bound for enemy rows.*
      `test_an_enemy_row_rounded_over_a_floors_edge_is_accepted` now also refuses a row 0.02 px beyond the stairs'
      edge. Before, `ROUNDING = 0.5` (a 1 px span) survived that module; only the player-row test in
      `test_mesh_net_hd2d.py` caught it.
  - **The delay proxy** (`tooling/net_delay_proxy.py`: asyncio, standard library only, loopback only).
    - **One link model.** M4-0's `Link` (one way RTT/2 ± uniform jitter; a loss arrives RTT + RTO later; never before
      the message sent earlier) moved into the proxy, with the RTO as a field. `tooling/m4_latency_probe.py` imports
      it and passes its `--rto`, so the probe's numbers are unchanged (the same arithmetic and the same random draws).
    - Each chunk read from a socket is one "message". It is written on at `Link.arrival`, from a FIFO queue, so jitter
      and stalls never reorder bytes. There are two guards: the link's head-of-line rule and the queue. An end of
      stream follows its bytes the same way.
    - "Stall bursts" are the probe's own loss model (`--loss`, `--rto-ms`), not a second one: at `--loss 0.01` the
      proxy runs OD1's profile.
    - Each connection draws its two links from one `--seed`ed stream, in arrival order. The chunking itself is the
      OS's, so a run's byte timing repeats only as far as its reads do.
    - **Windows' timer.** asyncio's Windows loop wakes on the 15.6 ms system timer, which added 0–15.6 ms each way
      (100 ms RTT measured 121–124 ms). The proxy holds a 1 ms timer (`timeBeginPeriod`) while it runs. Then 100 ms
      measures 100.5–102.4 ms, 200 ms 200.6–202.6 ms and 0 ms 0.3–0.6 ms (echo over loopback, 20 pings each).
    - **Never early, on every Python.** Before Python 3.13 the loop's clock on Windows is GetTickCount64, in 15.6 ms
      steps. CI's first run (Python 3.11, Windows) read one 100 ms ±10 ms round trip as 75.8 ms, under the 80 ms the
      model allows, when the proxy stamped and waited on the loop's clock. It now stamps each chunk on
      `time.perf_counter()` and waits until then (`until`): the loop sleeps the bulk, and a worker thread's
      `time.sleep` the rest, which on a fine loop clock is about nothing. Locally under Python 3.10 (the same coarse
      clock): 100 ms with no jitter read 100.4–106.5 ms.
    - **Tests** (`tests/test_net_delay_proxy.py`; the socket tests are `integration`, the model test `fast`):
      - the delay stays within the jitter;
      - a 200 kB stream arrives in order, then its end of stream;
      - a loss stalls by a retransmission;
      - one seed, one run;
      - a delivery never comes early even when the loop wakes early;
      - the real co-op `Server` with two real clients (`mesh_net.client.connect`) through it at 100 ms: an input is
        acknowledged no sooner than a round trip.

      The CLI was also run in front of the sample server: join to welcome took 1.6 / 102.5 / 203.6 ms at 0 / 100 /
      200 ms.
  - **Launching two clients through the proxy** (PowerShell, from the checkout, one process per terminal). First the
    authority, with the input queue to play (`drain` is the provisional default):

    ```powershell
    $env:PYTHONPATH = '<checkout>'
    py -3.13 -m mesh_net.server --expedition --queue drain --port 46870     # or --queue deep / --queue small; or --coop
    ```

    Then one of these proxies (clients join port 46871; OD1's ±10 ms and 1% loss on the delayed ones):

    ```powershell
    py -3.13 tooling/net_delay_proxy.py --listen 46871 --target 127.0.0.1:46870 --rtt-ms 0
    py -3.13 tooling/net_delay_proxy.py --listen 46871 --target 127.0.0.1:46870 --rtt-ms 50 --jitter-ms 10 --loss 0.01 --seed 7
    py -3.13 tooling/net_delay_proxy.py --listen 46871 --target 127.0.0.1:46870 --rtt-ms 100 --jitter-ms 10 --loss 0.01 --seed 7
    py -3.13 tooling/net_delay_proxy.py --listen 46871 --target 127.0.0.1:46870 --rtt-ms 200 --jitter-ms 10 --loss 0.01 --seed 7
    ```

    Then, in two more terminals, the clients through it:
    - `py -3.13 -m mesh_net.world_client --port 46871` (the expedition);
    - with `--coop`: `py -3.13 -m mesh_net.scene_client --port 46871`;
    - the 2D sample: `py -3.13 -m mesh_net.demo --port 46871`, against `py -3.13 -m mesh_net.server --port 46870`.

    Drop `--jitter-ms` and `--loss` for a pure delay.
  - **The capture harness** (`tooling/m4_render_evidence.py OUT [--rtt-ms] [--jitter-ms] [--loss] [--rto-ms] [--seed]
    [--queue drain|deep|small]`).
    - **Two Python processes.** The harness runs the authority (`WorldServer` over the expedition) and the proxy on
      an event loop in a thread, and window A on its main thread. Window B is `tooling/net_world_probe.py`, over its
      command channel.
    - Both windows are hidden and never activated (`tooling.hidden_windows.no_activate`), the audio is silent, and
      the controls hint is off (a new `--no-hint` on the probe). The probe's command handling and window setup are
      now `handle` and `hidden_arena`, which the harness shares.
    - **Inputs** go through the client's own key handling: key events dispatched to the window with the probe's own
      modifier mark, as the window tests do. No OS input.
    - **Scenario** (the N7 GPU test's proven walk): both meet in the hub and form a party, both go to Layer 1 (a
      transfer), A opens the gate, both go to Layer 2 (a transfer), A walks onto the guardian from above and swings
      once.
    - **Frames** come from each window's framebuffer (`arcade.get_image` after a draw):
      - the hub, and after each transfer;
      - A's local swing, taken as the window shows it (a key event reaches the window at its next dispatch), and
        100 ms later;
      - the server-confirmed hit, taken inside the flash (which lasts 0.15 s);
      - B's frames once its state shows A's swing and the hit.
    - **`evidence.json`** has:
      - the link, seed, HZ and queue preset;
      - each frame (window, moment, time, client and server tick, room);
      - every event in A's window with both ticks: `local_swing_shown`, `prediction_correction` (over 0.05 px),
        `server_confirmed_hit`, `room_transfer_enter` and `room_shown`;
      - the proxy's chunk counts and every held chunk's delay;
      - the GL renderer.
  - **Trial** (one run: 100 ms ±10 ms, 1% loss, seed 7, drain, an RTX 4070): 26.3 s from start to the last frame, and
    32.8 s with process start and teardown. 11 frames and 13 events. These numbers are descriptive, from one run:
    - press to swing shown: 17.8 ms (the next frame); press to hit confirmed: 184 ms (the flash frame at 205 ms);
    - transfers, enter to room shown: 120–172 ms;
    - 5 prediction corrections of 7.5 px (one step) on the hub and Layer 1 walks, none in Layer 2;
    - the proxy held 75 of 957 chunks up and 78 of 966 down beyond the jitter: 1% loss and the chunks queued behind
      each stall (65–360 ms);
    - foreground monitor: 0 focus changes.
  - **Limitations.**
    - **The local swing has no pixels in the packaged expedition.** Its player's Animator has no `attack` clip and the
      sound is silenced, so frame `06_A_local_swing` looks like a standing frame. The swing is evidenced by the event
      (`local_swing_shown` on the frame after the press), not by the picture. The final set needs a visible swing (an
      attack clip or a marker): that is content, not network code.
    - B's "peer swing seen" and "peer hit seen" frames are the same picture: the swing and the hit arrive in one state.
    - Window A shares a process, and its GIL, with the authority and the proxy, so a frame of A can delay a tick or a
      delivery by a few ms. That keeps the run within the owner's two-process limit.
    - The proxy delays read chunks, not TCP segments: a chunk may hold several frames, and they share one fate. Loss
      is the probe's per-message model, not bursty loss.
    - One trial, at 100 ms only, as briefed. 200 ms and the other presets were not run. The final evidence set (100
      and 200 ms, every preset the owner wants) waits for the M4-5 decision.
- **Final evidence as implemented** (after M4-5, #626; the owner: "finish the M4-6 rendered evidence with clearly
  visible swing feedback, provide playable launch instructions and stop at the agreed M4 checkpoint").
  - **A visible swing** (`mesh_net/scene_client.py`: `SceneView.swing`, `flash`, `_mark`; client presentation only,
    nothing under `engine/`, no protocol or rule change).
    - A swing draws a white crescent with a blue rim over the hitbox the server makes: the room's reach ahead, in the
      facing direction, the picture turned that way. It lasts the hitbox's life (`HITBOX_S`, 0.2 s), at the swinger's
      height and floor.
    - The window's own swing shows on the press (OD4), facing as the server will once it reads the inputs it hasn't
      yet (`Prediction.facing`). A peer's swing shows when its state shows it, facing as that state's row has it.
    - A confirmed hit (`hit_seq`) adds a red burst with a yellow core on the enemy, following it as it walks, for
      `FLASH_S`. The old red tint is kept for 2D; HD-2D's billboards ignore a sprite's tint, so before this an HD-2D
      hit showed nothing.
    - Both are scene sprites, so the 2D renderer and the HD-2D billboards both draw them. They share no colour and no
      place.
    - Tests (`tests/test_mesh_net_combat.py`):
      - the mark's place, facing, life and floor;
      - the hit burst following its enemy;
      - no shared colour;
      - the own swing marked on the press before any snapshot, and not again at the confirmation;
      - a peer's swing marked from its state.
    - **Mutation proof: 9 mutants, all killed.**
      - no mark on a swing;
      - no own mark until the server's reply, in either arena;
      - the hit drawn with the swing's picture;
      - the burst left behind a walking enemy;
      - the mark at the attacker instead of the hitbox;
      - the own facing from the stale row instead of the prediction;
      - a peer's facing ignored;
      - a mark outliving the hitbox.
    - **Single-player cannot show it:** the marks live in `mesh_net`, which the engine never imports, and nothing
      under `engine/` changed. Replays 13/13, no golden updated.
  - **The playable demo** (`tooling/m4_demo_world.py`; launch: `docs/plans/m4_playable_demo.md`).
    - The packaged expedition has no moving enemy: an enemy walks online only in an HD-2D room (M4-4). So the demo is
      a two-room world built from repository files:
      - the floors demo's HD-2D crossing, with three co-op bandits (30 HP) walking the probe's `FloorRoute`s on the
        open ground, the west stairs and the bridge deck;
      - a walk-in door to the expedition's Layer 1 (2D), here a shared room.
    - Its `server` takes `--queue drain|deep|small` and `--rewind on|off` (and the same `MESH_NET_*` variables as
      `python -m mesh_net.server`). Its `client` is `mesh_net.world_client`'s window.
  - **The rendered set** (`tooling/m4_render_evidence.py` on the demo world; `docs/reviews/m4_rendered_evidence/`).
    - Runs, seed 7, rewind on, hidden windows, a foreground monitor (0 focus changes in every run):
      - 0, 100 and 200 ms ±10 ms 1% with drain;
      - 100 ms with deep and with small.
    - Each run shows:
      - prediction (the own avatar moving 4–20 ms after the press, the server's row a round trip later);
      - the local swing visible on the frame that reads the press (6–18 ms);
      - a server-confirmed hit on the bandit while it walks (81, 168, 273, 161 and 182 ms);
      - the swing seen in B's window;
      - a room transfer (136–150 ms from the enter to the room shown).
    - One run each: descriptive, never gating.
    - `tooling/net_world_probe.py`'s replies now list the marks on screen.
  - **#626's owed review items.**
    - `test_the_attacker_is_never_rewound` now judges the very view the hitbox was placed against. The attacker
      stands there from before the view tick and walks two steps west, and a control puts it back. An
      attacker-rewinding mutant (a test-local seam) fails its discriminating assertion; under the old six steps it
      passed it.
    - "Inferred" for the slower confirmation is replaced by the reviewer's measured breakdown (§4 M4-5).

## 5. Owner decisions needed

Each decision carries the recommendation; the reviewer's view is noted where it differs.

1. **OD1 — latency envelope.**
   **Recommended:**
   - *responsive* to 100 ms RTT (±10 ms jitter, 1% loss): local movement and swing within one frame, hit confirmation
     median at most RTT + 75 ms;
   - *playable, never unfair in rules* to 200 ms;
   - best effort beyond that.
2. **OD2 — protocol v3.** **Recommended: yes**, one v3 carrying everything listed in M4-2, with an explicit refusal
   of v2 on both servers and no downgrade (as D1).
3. **OD3 — client prediction of the local avatar's movement.** **Recommended: yes.** The server stays
   authoritative, and the cost is occasional visible corrections.
4. **OD4 — local attack presentation.** **Recommended: yes.** A swing is shown before confirmation; hits, HP and
   death only on confirmation.
5. **OD5 — lag-compensation policy.** **Recommended:**
   - defer until enemies move (M4-4);
   - PvE only;
   - cap tied to OD1: about 300 ms (6 ticks at 20 Hz) for a 200 ms envelope;
   - clamp, never refuse;
   - never rewind the attacker;
   - `same_level` on the rewound target.
6. **OD6 — tick rate.** **Recommended: stay at 20 Hz for M4.** Send-on-press and prediction recover most of the gain
   without 1.5–3× server cost. The burst fix (M4-1) must come first in any case, since 30 Hz and above make it worse.
7. **OD7 — moving enemies.** **Recommended: yes, as M4-4**, decided **before M4-2** so that v3 carries enemy
   positions. Without it, M4 combat stays against static enemies and rewind is moot.
8. **OD8 — virtual-clock acceptance.** **Recommended: yes**, as same-seed before/after comparisons over at least 3
   seeds × 24 sessions, with margins larger than the measured spread (§4). Wall-clock timings and p95 stay
   report-only.
9. **OD9 — transport.** **Recommended: stay on TCP for M4.** Retransmissions drive p95 and peer freezes (§2.2,
   §2.5), but UDP with a reliability layer is a separate architecture decision.
10. **OD10 — combat timing parity.** **Recommended: the server mirrors single-player's hitbox, server-side only.**
    That means:
    - it stays at the position where it spawned;
    - it lives ceil(0.2 × HZ) = 4 ticks;
    - it hits each target once;
    - it checks `same_level` against the attacker's *current* elevation on each tick.

    Single-player is unchanged. The facing difference (velocity angle, `angle` when standing, versus 4 facings) stays
    a known gap.
11. **OD11 — how the server uses inputs.** **Recommended: (a)**, a bounded per-player queue read one per tick, tagged
    by `seq` (and intended tick), sized with M4-1's bucket, holding the last input for 5 ticks when empty. Depth **2**
    (the reviewer recommends 2–3). The alternative is (b): keep last-input-wins and accept routine one-step corrections.
    The intended tick never lets the server apply more than one input per tick, and when a full queue drops an input,
    any pending attack is kept.

## 6. Risks

- **Prediction errors near changing solids and floors.** Doors, gates, dying solid enemies, stair edges. Mitigation:
  reconcile on every snapshot; snap elevation and floor; the stairs and floor parity tests.
- **Queue and latency trade-off (OD11(a)).** Each queued input adds up to one tick. M4-3 measured it (§4 M4-3 "As
  implemented": the variant matrix): depth 8 keeps a retransmission burst (no correction) and pays in lateness while
  the player keeps walking; a standing player's queue is emptied; the owner's options are listed there.
- **Session boundaries.** Prediction or counters leaking across a resume or transfer. Mitigation: clear at `welcome`
  and `enter`; acks scoped to the room instance; the resume-sync, transfer and N8 tests.
- **Float determinism across platforms.** Mitigation: always reconcile; never trust the prediction.
- **Duplicated logic creeping in.** The step function and the `FloorRoute` model must each be shared. Mitigation:
  parity tests that both sides import them, the M1-A pattern.
- **A protocol v3 ripple.** About 10 test files plus the M3 tooling. Mitigation: one PR (M4-2); OD7 decided first.
- **The model is optimistic.** No phase drift; RTT + 200 ms retransmission; real WANs have bursty loss. Mitigation: the
  M4-6 rendered evidence through a real delay proxy, and a real-network play-feel check before promising action-game
  responsiveness (as N5.1 said).
- **Player-perceived unfairness at the BODY boundary** remains until (b). The server's rule never changes; owner D8
  stands.

- **Security limitation: before public deployment** (owner decision of 2026-11-24, condition 5). This needs attention
  before any competitive PvP or public deployment.
  - **What a dishonest client can do:** it can claim attack ticks up to `COOLDOWN_CLAIM_WINDOW` (12 ticks, 600 ms)
    old. It cannot raise its long-run attack rate. Over any W ticks it starts at most
    1 + (W + COOLDOWN_CLAIM_WINDOW) // cooldown attacks, against 1 + W // cooldown for an honest client, and never
    more than one per tick.
  - **But after a pause it can bank a burst.** Claiming the oldest tick accepted on every tick gives a run on
    consecutive ticks of 1 + COOLDOWN_CLAIM_WINDOW // (cooldown − 1) attacks. Short cooldowns gain the most. Measured
    by `tests/test_mesh_net_combat.py::test_a_lying_client_gains_one_caps_worth_at_most` (200 ticks after a
    100-tick pause):

    | Cooldown (ticks) | Run on consecutive ticks | Greedy liar / honest starts in 200 ticks |
    |---|---|---|
    | 2 | 13 | 106 / 100 |
    | 3 | 7 | 71 / 67 |
    | 5 | 4 | 43 / 40 |
    | 10 (the co-op room's) | 2 | 22 / 20 |

  - **Mitigations to consider before deployment:** a shorter window, a per-player rate check on top of the claim, or
    server-side input timestamps once M4-3's queue exists.

- **Security and fairness limitation of lag compensation (M4-5): before public deployment.** The owner's decision of
  2026-11-25 requires this to be documented; it needs attention before any public deployment, and it rules out PvP
  as built.
  - **What a lying client can do.** The server cannot tell which frame a window really showed. It accepts any
    `view_tick` between the later of the attacker's join and 6 ticks ago, and now. A client can therefore pick, per
    attack, the most favourable pose each enemy had over the last 300 ms, anywhere along its path (fractions included).
  - **The bound.** Along an enemy's motion, the stretch of attacker positions from which a hit lands grows from
    (hitbox + the enemy's shape), what an honest client gets for the one pose it saw, by at most the distance the enemy
    walked in 300 ms:
    - 15.6 px at the co-op bandit's 52 px/s on the server (70 authored);
    - 26.6 px at 88.6 px/s (150 authored);
    - in general, speed × 0.3 s.

    Against the 32 px hitbox and the bandit's 19 px wide collider (51 px of reach along the motion), that is up to +31%
    and +52%. On
    stairs, it can also pick a moment when the enemy was still within `same_level`'s 1.5 m. At the bandit's climb
    (half its walk), that is up to about 8 px (0.25 m) of elevation.
  - **What it cannot do:**
    - rewind itself: the hitbox and the level are always the attacker's current ones;
    - reach back further than 300 ms, ahead of the tick, or before it joined the room instance;
    - use another instance's or another identity's history;
    - hit an enemy dead now, or one never on its level at the chosen moment (decks, stairs);
    - attack more often: the cooldown is judged apart, with the 600 ms claim limitation above.
  - **Honest-client side effects, counted rather than hidden:** a rewound hit can land on an enemy the player sees as
    already past (it was in reach where the window showed it), and the reverse. The probe counts "looked like a miss
    but hit" with and without rewind (§4 M4-5).
  - **Mitigations to consider before deployment:**
    - bound the accepted view by the server's own measure of each client's delay (round trip from `ack` timing plus
      the fixed two-tick interpolation), with a small tolerance, instead of a flat 300 ms;
    - log and rate-limit clients whose views sit consistently at the oldest allowed;
    - keep it PvE-only.

**Out of scope:**
- RPG content;
- M5 persistence (N8 schema);
- M6 production;
- PvP;
- UDP transport;
- internet hosting, authentication and anti-abuse beyond the input bucket;
- 8-direction facing on the wire.

## 7. Coordination

- **M3 acceptance** (`tests/test_mesh_net_hd2d_gpu.py`, `tooling/m3_two_client_evidence.py`, `tests/test_mesh_net_hd2d.py`)
  stays green at every stage.
  - Rows still carry elevation and floor, and `check_levels` still validates them.
  - With prediction, the own avatar converges to the server's row at loopback, and the tests compare after settle.
  - M4-2 updates the version literals in the same PR.
- **N6/N7/N8:** resume (#498/#499, `tests/test_mesh_net_resume.py`), transfers (`tests/test_mesh_net_world.py`) and
  character frames (`tests/test_mesh_net_characters.py`) are acceptance for M4-2 and M4-3 (§4).
- **Replays** are single-player and must stay 13/13 with no golden updates.
  - M4 changes `mesh_net` and adds client presentation; it changes no engine rule.
  - OD10 is server-only.
  - M4-4's shared `FloorRoute` model must keep single-player's walk identical, proved by parity tests and replays.
- **The graphics-free authority** (`test_mesh_net_scene.py`, `test_mesh_net_world.py`) stays import-clean: the shared
  step and mover models use `engine.physics_model` and `engine.hd2d.world` only.
- **Extended** (Ubuntu and Windows, gpu shards) is dispatched for M4-3, M4-4 and M4-6, which touch the play path. The
  hidden-window rule applies. The owner's desktop is never automated.
- **M5 planning** can proceed in parallel. Nothing here changes the N8 store.

## Appendix: reproduce

```powershell
$env:PYTHONPATH = 'D:\Games\Mesh-M4design'
py -3.13 tooling/m4_latency_probe.py --json out20.json            # §2 tables: seeds 7 8 9, 24 sessions, 20 Hz
py -3.13 tooling/m4_latency_probe.py --hz 30 --json out30.json    # what-if: 30 Hz tick and send rate
py -3.13 tooling/m4_latency_probe.py --hz 60 --json out60.json    # what-if: 60 Hz
```

The output has `range` (every number as [lowest, highest] over the seeds), the per-seed `runs`, and `snapshot_bytes`.

What-if p50 local first move at 0 / 100 / 200 ms RTT, the latter two with jitter and loss:

| Tick rate | 0 ms | 100 ms | 200 ms |
|---|---|---|---|
| 30 Hz | 39–42 ms | 145–148 ms | 246–250 ms |
| 60 Hz | 15–17 ms | 132–134 ms | 235–237 ms |

At 30 Hz and above, 1% loss already produces bursts of 9 inputs per tick, which the current rate limit disconnects
(§2.5).
