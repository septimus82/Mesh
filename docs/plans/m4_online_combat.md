# M4 — responsive server-authoritative online combat: measurements and design (M4-0)

> **Status:** design approved by the owner (2026-11-24, OD1–OD11 below); being implemented in stages.
> M4-0 (#609) added this document, a headless measurement tool (`tooling/m4_latency_probe.py`) and one test of the
> tool's link model and statistics. M4-1 (#610) and M4-2 (#611: protocol v3 and attack presentation) are merged.
> M4-3 (own-movement prediction and the server's input queue) is in review: §4 M4-3 "As implemented".
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
      evaluated on the server's current geometry and floors, never on positions from the claimed tick. A test checks
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
- **As implemented** (owner decisions OD3 and OD11; `mesh_net/scene_room.py` has the code and its notes):
  - **One movement step.** `SceneRoom.walk(body, dx, dy, solids)` is the only code in `mesh_net` that moves a body:
    - in an HD-2D room, `World.move` with this module's sweep; in a 2D room, the sweep alone;
    - a diagonal is normalised, and the body is kept within the wire's bound.

    The authority's tick (N6 `SceneRoom.step`, and so every N7 room instance) and the window's prediction both call
    it. The no-duplicate scan in `tests/test_hd2d_net_parity.py` is extended: no other `mesh_net` function calls
    `move`/`World.move`, and only one `walk` is defined. A spy test checks that both sides call it. Single-player is
    untouched: replays 13/13, no golden updated.
  - **The server's input queue (OD11).**
    - Each tick reads ONE input, the oldest waiting (`moves`, at most `DEPTH` = 2), and walks one step with its
      direction. `ack` is the seq of that input.
    - A full queue drops its oldest direction (`dropped_moves`), so the newest direction wins.
    - An input's attack and its use or take wait apart, in M4-2's queues (`PENDING` of each, one of each kind a
      tick). They run on the tick that reads their input or a later one. So a dropped direction never loses an
      action, and no action runs before its own input.
    - With nothing waiting, the last direction is walked until `HOLD` = 5 ticks after it was read (the existing
      lease, its own tick included), then the body stops.
    - An input's actions run **before** that tick's step, from where the player stood. That is where a predicting
      window showed the player when the key was pressed. The attack faces the way the input turns it.
    - `leave` (disconnect, transfer) empties the queue.
    - The queue is sized with M4-1's `InputBudget`: the bucket bounds how fast frames come, and the room bounds what
      it keeps of a burst. A burst the bucket lets through never walks a body faster, nor loses an attack.
  - **One change to the queue, with measurements: a standing player gets its tick back.** Once jitter has emptied
    the queue once, it settles one input deep, which adds a tick to everything the server does for that player: its
    attacks, and what peers see.
    - Measured first without the change: median hit confirmation at 100 ms, ±10 ms, 1% loss was 204–209 ms, against
      OD1's RTT + 75 = 175 ms (155.8–165.4 before M4-3).
    - So while the player stands, of two still inputs waiting, the older is dropped. It walks nowhere, as does the
      one after it, and its actions run with that one. No step is ever dropped, so this causes no correction.
    - Now 166.0–175.9 ms (see the limitation below). A test and three mutants pin it.
    - The cost: a queue drained while standing can empty when walking starts, so jitter alone (100 ms ±10, no loss)
      gives one-step corrections: 83–147 in 960 presses (one step, 7.5 px, every time).
  - **The prediction (`Prediction`, one object for `SceneArena` and `WorldArena`).**
    - A direction press builds the next input at once and walks the avatar on that frame. The next send carries that
      input; the send rate stays one input a tick.
    - Every input sent walks the predicted avatar through `SceneRoom.walk` and waits until a snapshot's `ack` passes
      it.
    - Each snapshot rebuilds the avatar from the server's row, then walks the unread inputs again, through what
      blocked in that snapshot (`SceneRoom.solids(state)`: its gates and live enemies).
    - x/y corrections fade over `SMOOTH_S` = 0.1 s, exactly to zero. Elevation and floor take the server's at once.
    - A take or use is chosen by the predicted position (where the server will run it).
    - The window starts predicting at a welcome (a resume's too) and when an N7 room first shows. It stops at every
      `enter` and at a session's end, so no input is walked again in another room or session.
    - Peers stay as before (`Playback`).
  - **The tick estimate:** every input now carries the tick `Feedback` reckons: an attack its swing's, a move the
    tick reckoned when it goes. That is one estimate; M4-2 sent the last snapshot's tick + 1 for moves. The server
    judges only attack cooldowns on it. Movement is read one a tick in arrival order, so the tick can never make the
    server walk more than one step.
  - **Hidden solver state** (M4-2 follow-up e). The floor solver keeps per-body water state that is not on the wire
    (`mesh_hd2d_deep_cap`).
    - Replays start from a body rebuilt from the row, so none of it is carried. A prediction escaping deep water can
      differ until the next snapshot puts it back.
    - Online rooms refuse such water today (owner D4), so this is unreachable in play. A test checks that nothing
      hidden survives a reconciliation and that the prediction converges exactly once the two sides agree again.
  - **M4-2 follow-ups folded in.**
    - (a) The reckoning's recovery settings are pinned by
      `test_the_reckoning_rides_out_a_retransmission_but_follows_a_stall`: a ~400 ms retransmission hold and lateness
      under a tick leave it; a real stall brings it down after exactly 20 snapshots. Mutants at 2 and 19 snapshots,
      and coming down on lateness under a tick, are killed.
    - (b) The probe reports `dropped_actions` beside `stale_attacks` and `refused_attacks`.
    - (c) §6 cites the repository test.
    - (d) The narrow resume case is noted in M4-2 "As implemented".
  - **The probe:** the same seeds 7/8/9 × 24 sessions, before at b81765ae and after (`tooling/m4_latency_probe.py`,
    `--depth` for what-ifs).
    - The probe now models the window as it is. The local avatar is shown as `Prediction` shows it, built at a press
      and reconciled at each snapshot. Space is read at the frame after the press: M4-2's probe let a press ride the
      next send without the frame that reads it, which made every hit confirmation look up to a frame sooner.
    - It also reports the prediction's corrections (per reconciliation), level snaps, queue drops and walks on an
      empty queue, and a jitter-only profile.
    - A correction is a reconciliation that moves the avatar more than 0.05 px; the wire's 0.01 px rounding stays
      below that.

    | RTT (jitter, loss) | Local first move p50 / max, ms | Stairs level-caused disagreement | Stairs any disagreement | Walk-away disagreement | Hit confirmed p50, ms |
    |---|---|---|---|---|---|
    | 0 (none) | 54.0–60.8 / 115 → **8.0–8.5 / 16.7** | 14.8–15.5% → **0.0%** | 29.3–30.7% → **0.0%** | 10.4–10.9% → 1.5–1.7% | 52.6–57.6 → 61.8–65.7 |
    | 0 (±10, 1%) | 65.8–71.4 / 446 → **7.6–8.2 / 16.7** | 16.6–17.8% → 0.6–0.8% | 33.5–35.7% → 1.3–1.5% | 11.6–12.5% → 1.7–2.2% | 63.4–71.8 → 72.0–77.3 |
    | 50 (±10, 1%) | 106.9–113.5 / 567 → **8.0–8.7 / 16.7** | 22.7–23.1% → 0.8–0.9% | 46.6–46.9% → 2.0–2.3% | 16.2–19.3% → 2.1–2.5% | 106.0–114.4 → 115.0–122.8 |
    | 100 (±10, 1%) | 157.4–167.6 / 714 → **8.1–8.6 / 16.7** | 27.4–29.0% → **1.4–1.7%** | 55.6–58.6% → 3.1–3.4% | 20.9–22.3% → 2.2–2.7% | 155.8–165.4 → 166.0–175.9 |
    | 200 (±10, 1%) | 260.9–264.6 / 2102 → **8.1–8.9 / 16.7** | 33.1–33.4% → 1.8% | 66.9–67.7% → 3.7–4.1% | 27.6–31.7% → 2.4–3.6% | 263.8–265.4 → 269.0–273.4 |
    | 100 (±10, no loss) | — → 8.3–8.7 / 16.7 | — → 0.0% | — → 0.0% | — → 1.7–1.9% | — → 163.7–171.4 |

    The prediction's corrections. Each cell is p95 over every reconciliation, px / how many corrections / their size
    p50, p95, max (px). The movement column is 960 presses with 400 ms holds; the stairs column is 16 s strafing.

    | RTT (jitter, loss) | Movement (2D) | Stairs (HD-2D) |
    |---|---|---|
    | 0 (none) | **0 / 0** | **0.01 / 0** |
    | 0 (±10, 1%) | 0 / 439–507 / 7.5, 22.5, 30 | 0.01 / 286–322 / 5.3, 15.9, 21.2 |
    | 50 (±10, 1%) | 0 / 436–493 / 7.5, 30, 37.5 | 0.01–5.3 / 368–414 / 5.3, 21.2, 26.5 |
    | 100 (±10, 1%) | **0** / 486–565 / 7.5, 37.5, 45 | **5.3** / 393–452 / 5.3, 26.5, 38.6–80.9 |
    | 200 (±10, 1%) | 0 / 481–531 / 7.5, 37.5–45, 52.5–60 | 0.01–5.3 / 358–414 / 5.3, 52.2–63.9, 93.8–123.7 |
    | 100 (±10, no loss) | 0 / 83–147 / 7.5, 7.5, 7.5 | 0.01 / 2–9 / 5.3, 5.3, 5.3 |

  - **Against the acceptance:**
    - Local first move within one frame on every seed and profile: met (max 16.7 ms).
    - Zero corrections with no loss and static solids: met at 0 ms with no jitter, in every scenario and on every
      seed. Jitter alone (no loss) gives one-step corrections; see the cost of the standing drain above.
    - p95 correction at most one step at 100 ms, ±10, 1%: met as p95 over all reconciliations (0 px moving, 5.3 px
      on the stairs).
      - The corrections themselves are larger: at 1% loss there are about 0.35–0.41 a second of walking, p95
        26.5–37.5 px, max 45–81 px.
      - They come from TCP's retransmission hold (RTT + RTO, 300 ms at 100 ms). During it the server walks the last
        direction on (`HOLD`), then drops the oldest directions of the burst that follows.
      - No depth or hold removes this: the server cannot know what was pressed while it heard nothing.
    - Stairs level-caused disagreement below 5% at 100 ms on every seed: met (1.4–1.7%).
    - Buffers cleared at welcome, enter and session end, with tests for N6 resume, N7 resume and an N7 transfer with
      inputs in flight.
    - Resume-sync, N8, M3 acceptance (`tests/test_mesh_net_hd2d_gpu.py`, the own avatar compared after it rests) and
      every graphics-free `test_mesh_net*` suite are green.
  - **Depth 3, measured** (`--depth 3`, same seeds):
    - The standing drain makes its latency cost nothing while the player stands (identical hit confirmation).
    - It gives slightly fewer and smaller corrections: at 100 ms, 474–553 corrections with p95 30 px against 486–565
      at 37.5 px.
    - It also lowers the stairs disagreement (0.8–1.2% level-caused).
    - While walking it can hold one more tick of server-side latency than depth 2 (not measured by the probe's
      standing attacks).
    - Depth 2 passes every safeguard, so it stays, as OD11 set it.
  - **What the owner's safeguards are tested by** (`tests/test_mesh_net_prediction.py`, the probe's virtual clock and
    link, seeds 7/8/9):
    - Quick direction reversals (keys changed every 20–70 ms).
    - Key release and a 30 ms tap.
    - Attacks mashed while walking (every swing one attack, or stale beyond OD1's envelope; none twice, none refused).
    - The cooldown, and jitter (the jitter-only profile).
    - A 300 ms loss burst, a 1.2 s server stall and a 1.5 s outage.
    - Disconnect and resume (N6, N7), and an N7 transfer with inputs waiting and in flight.
    - Overflow at depth 2.

    In every one, each tick the server walks at most one step, and only a direction an input gave (read that tick, or
    walked on within `HOLD`), in its sense. It stops once the keys are let go, and the window ends exactly on the
    server's row. Every behaviour has a mutant the tests kill (31 of 31, PR body).
  - **Immediate presentation and server-confirmed outcomes stay apart.**
    - The local avatar's movement and its swing are presentation: immediate, corrected by the server's row.
    - Hits, damage, HP, death, loot and every position on the wire are the server's, shown only as snapshots say.
    - Nothing predicted is ever sent.
  - **Honest limitations at 200 ms (±10, 1%):**
    - Corrections: about 0.35–0.38 a second of walking, median one step (7.5 px), p95 37.5–45 px moving, 52–64 px on the
      stairs, worst 124 px on the stairs. The avatar slides back or on over 0.1 s, and its floor and height jump.
    - A release under loss: the avatar stops at once but may be carried on afterwards (stop-after-release p95
      461–500 ms, against 386–432 ms of plain waiting before M4-3). The server walked on during a retransmission
      hold.
    - Confirmation still waits: hits show 269–273 ms after the press (median), an unchanged round trip.
    - Stale swings: 3–10 of 720 swings per seed run were stale (0–6 before M4-3). Each was shown, dropped and counted,
      and reads as a miss, because the queue can add up to a tick to an attack's way.
    - Remaining unfair-looking moments: 3.7–4.1% of stairs presses and 2.4–3.6% of walk-away presses disagree with
      the server, nearly all within a retransmission. Moving targets are unchanged (they need M4-4/M4-5).
    - These are simulation results. No subjective claim about how it plays is made here; that is M4-6's rendered
      evidence and a person's play-test.
  - **Limitation at 100 ms:** median hit confirmation is 166.0–175.9 ms. One seed is 0.9 ms over OD1's RTT + 75 ms.
    About 9 ms of the rise is the probe now reading Space at the frame after the press, as the window does: at 0 ms,
    where nothing else changed, the same rise is 8.1–9.2 ms. It is reported, not adjusted.

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

**M4-5 — lag compensation (d), only if M4-4's measured moving-target disagreement at OD1's envelope exceeds the
owner's budget:**
- Rewind history, `view_tick`, and the OD5 cap.
- **Acceptance:** same-seed probe under the budget; cap and cross-floor tests.

**M4-6 — rendered evidence:**
- A small asyncio TCP delay proxy in `tooling/`. Two hidden windows (non-activating hook) at 100 and 200 ms.
  Framebuffer evidence of the local swing, prediction, confirmed hit, and a transfer under latency.
- Descriptive timings only.

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
- **Queue and latency trade-off (OD11(a)).** Each queued input adds up to one tick. Mitigation: depth 2; drop to the
  newest input on overflow, keeping any pending attack; a standing player's queue gives its tick back (M4-3 "As
  implemented": measured, and its cost in one-step corrections under jitter).
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
