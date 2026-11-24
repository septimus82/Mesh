# M4 — responsive server-authoritative online combat: measurements and design (M4-0)

> **Status:** design approved by the owner (2026-11-24, OD1–OD11 below); being implemented in stages.
> M4-0 (#609) added this document, a headless measurement tool (`tooling/m4_latency_probe.py`) and one test of the
> tool's link model and statistics. M4-1 (#610) and M4-2 (#611: protocol v3 and attack presentation) are merged.
> M4-3 (own-movement prediction and the server's input queue, #613) is merged; its follow-ups (round 4: tests, the
> probe's flag order, the drain's fork guard) are in review: §4 M4-3 "As implemented". Its input queue is the owner's
> choice after playing; "drain" is the provisional default (owner decision, 2026-11-24).
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
