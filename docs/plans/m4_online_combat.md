# M4 — responsive server-authoritative online combat: measurements and design (M4-0)

> **Status:** investigation and design for owner review (escalation of major architecture, owner's standing rule).
> Nothing here is implemented. This PR adds this document, a headless measurement tool
> (`tooling/m4_latency_probe.py`) and one test of the tool's link model and statistics. `mesh_net` and `engine`
> behaviour is unchanged.
>
> **Authority:** owner decision D7 (2026-11-23, `docs/plans/hd2d_online_investigation.md` §6, §7.4): M4 is approved
> to begin now that M3 has passed. Focus: responsive server-authoritative online combat, including simulated latency.
> M5 is planning only. M6 is not authorized.
>
> **Citations** are `file:line` at `a81b511f`. *(inferred)* marks reasoning that was not measured.

## 0. Summary

- **Today, everything a player sees of their own actions waits a full round trip plus up to two 50 ms quantisation
  waits.** At 100 ms RTT the median local avatar starts moving 160 ms after the key press, and the hit shows after
  163 ms (p95 244 / 282 ms). At 200 ms RTT both are about 270 ms. Even at 0 ms the median is 54 ms (§2.2).
- **A swing is never shown.** No attack state is on the wire, and the client keeps only the Animator. The attacker
  sees nothing until the enemy's HP changes. That HP appears in the window caption, and the sprite hides at 0 HP
  (§1.3).
- **Hit fairness is dominated by the attacker's own motion, not the target's.** Today's enemies never move online.
  Measured on a scripted moving target, ideal rewind removes all of the moving-target error. It does nothing for the
  error from the attacker's own movement: 24% of samples disagree at 100 ms when walking up to an enemy and away, and
  59% on the HD-2D stairs case. Only own-avatar prediction addresses that (§2.3).
- **A stale view can make a cross-floor attack look possible.** On stairs near the 1.5 m `same_level` reach, 29% of
  sampled presses disagree at 100 ms *because of the floor rule alone*. That is 15% even at 0 ms RTT, from tick
  quantisation. The server is always right; the player just can't tell (§2.4).
- **A latent disconnect.** The server ends any session that delivers more than 8 inputs within one tick
  (`mesh_net/server.py:77-84`). A TCP stall of 400 ms or more at 20 Hz delivers 9 inputs at once, which this study
  reproduced on loopback. At 60 Hz a single 200 ms retransmission is enough to trigger it (§2.5).
- **Recommendation (§4):** stay server-authoritative on TCP, and stage the work as follows:
  - **M4-1:** robustness and send-on-press. No protocol change.
  - **M4-2:** protocol v3 with input acknowledgements and confirmed attack/hit state; local swing presentation.
  - **M4-3:** own-avatar movement prediction and reconciliation through the one shared floor solver.
  - **M4-4:** server-side enemy movement on floors, replicated like peers. Owner decision OD7.
  - **M4-5:** lag compensation for hits on moving enemies, capped at 200 ms. Only if M4-4's measurements need it.
  - **M4-6:** two-window rendered evidence under injected latency.

## 1. Current architecture

### 1.1 What is authoritative where

| Concern | Where | Evidence |
|---|---|---|
| Position, elevation, floor, facing | Server only. Clients never send them; an input is a direction plus an optional action. | `mesh_net/protocol.py:17-21`, `mesh_net/scene_room.py:694-706` |
| Movement | `SceneRoom.step` at a fixed `HZ = 20`. HD-2D rooms use `World.move`, the one floor solver. | `protocol.py:35`, `scene_room.py:565-577` |
| Attack | One instant check on the tick the input is read: a 4-way-facing AABB at `range` ahead with side `hitbox_size`, plus `same_level`. | `scene_room.py:582-584`, `:629-641`, `:74` |
| Enemy HP, death, loot | Server. A snapshot row is `[id, hp]`, with no position. | `scene_room.py:384-391`, `:656` |
| Enemy movement | **None.** The server moves no enemy or NPC. The client strips every behaviour except the Animator, so an authored mover such as the floors demo's warden (`FloorRoute`) walks in single-player and stands still online. | `scene_client.py:23`, `:72-73`; `tooling/hd2d_floors_demo.py:87-93` |
| Validation of server state | Client: exact frame shape, plus floor and elevation against its own collision world. | `scene_room.py:714-770` |

### 1.2 Flow and where latency enters

1. **Key press → send.** The client sends its current intent every 1/HZ s on its own timer, so an action waits
   0–50 ms (`mesh_net/demo.py:108-113`). An action is latched once (`:74-76`, `scene_room.py:555-556`).
2. **Uplink.** The connection is TCP on 127.0.0.1 today (`server.py:33`). Delivery is in order, so a lost segment
   holds up everything behind it.
3. **Server.** An input is applied on the next tick, a further 0–50 ms (`server.py:103-111`). Movement is held for
   `HZ // 4` = 5 ticks after the last input (`scene_room.py:569`). Then a full snapshot goes to every peer
   (`server.py:113-118`; N7: `world.py:585-596`).
4. **Downlink.** The same TCP behaviour applies.
5. **Display.** The local avatar is drawn at the latest snapshot. Everyone else is drawn by `Playback` two ticks
   behind, and its cursor never goes backwards (`scene_client.py:181-191`, `playback.py:348-368`). Positions are set
   directly, with no smoothing (`scene_client.py:109-119`). The window runs at 60 fps (`demo.py:186`).

Expected first-visible delay ≈ U(0,50) + RTT/2 + U(0,50) + RTT/2 + U(0,16.7) ms, which is about 58 ms + RTT on
average. N5.1 chose "latest snapshot for the local avatar, no prediction" on loopback
(`docs/networking/n5_1_responsiveness.md`), and deferred prediction "against a measured play-feel budget". This
document is that measurement.

### 1.3 Findings beyond latency

- **No swing on the wire.**
  - Single-player `Combat.attack` plays `attack_anim`, a sound and rumble, then spawns a hitbox
    (`engine/behaviours/combat.py:126-158`).
  - Online, none of this exists: the snapshot has no attack state and the client keeps only the Animator.
  - A non-lethal hit shows only in the caption text (`scene_client.py:175-179`). A lethal one hides the sprite
    (`:129-130`).
- **Combat timing parity gap (pre-existing).**
  - Single-player: the hitbox lives 0.2 s and checks overlap every frame (`combat.py:217`,
    `engine/behaviours/hitbox.py:95-131`). Its direction is the velocity angle (`combat.py:186-196`).
  - Server: one check on one tick, 4 facings.
  - M3-4 unified the *level* rule (`same_level`), not the hitbox lifetime.
- **The local avatar visibly steps at 20 Hz.** It is drawn at the latest snapshot, so 68% of 60 fps frames show no
  movement while walking (measured, §2.2), even at 0 ms.
- **The input-rate limit and TCP stalls collide** (§2.5).

## 2. Measurements

### 2.1 Method

`py -3.13 tooling/m4_latency_probe.py [--seed N] [--hz HZ] [--sessions K] [--json OUT]`, with
`PYTHONPATH` set to the worktree.

- **Headless and deterministic.** There are no sockets, windows or wall clock.
  - The real `SceneRoom` (step, input, `_attack`, `same_level`) and the client's real display rules (latest snapshot
    for the local avatar, `Playback` for others) run on one virtual millisecond clock.
  - The client's send clock has a seeded phase against the server tick. Results are pooled over 6 sessions per
    profile, because one session measures only one phase.
  - Seeds 7 and 8 agree within about 5 ms on medians and about 2 percentage points on rates. Seed 7 is reported.
- **Link model (TCP).** Each message has a one-way delay of RTT/2 ± uniform jitter.
  - A loss adds max(200 ms, RTT) for the retransmission. 200 ms is Linux's minimum RTO; Windows' is higher, so this
    is optimistic.
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
  stands in for what moving enemies replicated like peers would look like *(inferred)*.
- **Fairness.** Every client frame is a hypothetical press.
  - *Seen:* `_attack` and `same_level` evaluated with the bodies where the screen showed them.
  - *Real:* the same evaluation on the authority's bodies, on the tick that press lands. The press rides the next
    input sent and is applied on the next tick after arrival.
  - *Rewind:* real attacker against the targets where the screen showed them, which is ideal lag compensation.
- **Limits.**
  - This is a model, not a packet capture.
  - No OS scheduling, rendering or display scan-out is included. N5.1's real-window loopback median was 99.6 ms
    against this model's 54 ms; the difference is window, scheduler and GL time.
  - Rates are conditional on the scripted motions described in §2.3–§2.4, which are deliberately adversarial.
  - Numbers are descriptive. This tool has no timing assertions.

### 2.2 Responsiveness today (20 Hz)

Times are p50 / p95 in ms, from key press to the first frame showing it.

| RTT (jitter, loss) | Local avatar moves | A peer sees it move | Local avatar stops after release | Hit shows (HP drops) | Swing shows |
|---|---|---|---|---|---|
| 0 (none) | 54 / 96 | 112 / 151 | 4 / 46 | 48 / 88 | never |
| 0 (±10, 1%) | 63 / 117 | 117 / 167 | 16 / 129 | 69 / 109 | never |
| 50 (±10, 1%) | 102 / 191 | 150 / 208 | 52 / 122 | 104 / 163 | never |
| 100 (±10, 1%) | 160 / 244 | 209 / 275 | 107 / 193 | 163 / 282 | never |
| 200 (±10, 1%) | 270 / 332 | 314 / 382 | 219 / 324 | 272 / 386 | never |

- **Stepping and bursts.** The local avatar moves on only about 31% of frames while walking, in 7.5 px steps.
  After a retransmission stall, buffered snapshots arrive together and the avatar jumps 37.5 px in one frame.
- **No rubber-banding today.** There is no prediction, so there is nothing to correct.
- **Snapshot size.** 2D co-op: 260 B for 1 player, 285 B for 2, 435 B for 8. HD-2D crossing: 242, 273 and 459 B. At
  20 Hz, 8 players is about 8.7 KB/s down per client.

### 2.3 Hit fairness

Each cell shows *looked like a hit but missed* / *looked like a miss but hit* / *any disagreement*, as a percentage of
the matching sampled presses. The last column is the disagreement with ideal rewind.

| Scenario | 0 (none) | 0 (±10, 1%) | 50 | 100 | 200 | 100, with rewind |
|---|---|---|---|---|---|---|
| Moving target 70 px/s, still attacker | 10 / 8 / 9 | 11 / 8 / 9 | 15 / 10 / 12 | 17 / 12 / 14 | 25 / 18 / 21 | **0** |
| Moving target 150 px/s, still attacker | 22 / 18 / 20 | 25 / 20 / 22 | 31 / 25 / 28 | 39 / 31 / 34 | 56 / 45 / 50 | **0** |
| Attacker walks up to a still enemy and away (today's case) | 24 / 7 / 10 | 30 / 8 / 12 | 45 / 12 / 19 | 62 / 15 / 24 | 90 / 24 / 37 | 24 (no change) |
| HD-2D: strafing the stairs at a ground enemy | 29 / 29 / 29 | 36 / 31 / 33 | 52 / 44 / 48 | 73 / 50 / 59 | 100 / 55 / 71 | 59 (no change) |

- **Rewind fixes target motion only.** It removes the moving-target error entirely; the attacker there is still, so
  its own pose is exact.
- **Rewind does nothing for the attacker's own motion.** The screen shows the attacker where the server had it
  RTT/2 ago. The attack lands RTT/2 plus up to two quantisation waits later, where the attacker has since moved or
  turned. With ideal own-movement prediction, the screen and the landing tick agree by construction *(inferred)*.
- **The quantisation floor (0 ms row) is a tick-rate lever.** At 60 Hz, the 0 ms walk-away case drops from 10% to
  2.4%, the stairs case from 29% to 8%, and median local movement from 54 ms to 15 ms (`--hz 60`).

### 2.4 HD-2D floors and latency

Share of all sampled stairs presses that disagree *because `same_level` differs* between the shown pose and the
landing pose (shown as same level and in reach, but refused, or the reverse):

| 0 (none) | 0 (±10, 1%) | 50 ms | 100 ms | 200 ms |
|---|---|---|---|---|
| 14.8% | 16.6% | 23.4% | 29.3% | 34.3% |

- **Yes, a stale view can make a cross-floor attack look possible**, and the reverse.
  - **Where:** near `BODY` on stairs and slopes (`engine/hd2d/world.py:56`, `:165-205`), where elevation changes with
    planar motion.
  - **Not between a deck and the ground.** That gap is 2 m and constant, so latency never changes the answer.
  - **The server is always authoritative.** `_level` runs on the authority's bodies (`scene_room.py:589-596`, `:636`).
    This is a perception and fairness problem, not an exploit.
  - **The client asks nothing.** It never evaluates `same_level` itself, so the player has no cue.
- **Interpolated targets don't help.** A target shown through `Playback` carries an interpolated elevation and the
  nearer state's floor (`playback.py:365-366`). A moving enemy on stairs would add the same error on the target's side
  *(inferred)*.

### 2.5 Smoothness, enemies and the input-rate cliff

- **Enemies today.**
  - They never move online, so they cannot snap or rubber-band.
  - Their HP changes in a step on the next snapshot.
  - The single-player warden's `FloorRoute` walk is simply absent.
- **A moving target shown through `Playback`, the stand-in for replicated enemies.**
  - Never reverses spuriously, because the cursor is monotonic: 0 extra reversals in every profile.
  - Under 1% loss it freezes on 2–4% of frames, for up to 150 ms (one retransmission).
  - Then it jumps: 30–37 frames per 66 s moved more than twice its speed.
  - At 0 ms it is perfectly smooth.
- **The input-rate limit.**
  - `Server._handle` ends a session that delivers more than 8 frames within one tick (`server.py:77-84`). N7 has the
    same rule (`server.py:163-170`).
  - After a TCP stall, buffered inputs arrive together. The probe saw up to 6 in one tick at 20 Hz under 1% loss, 8 at
    30 Hz, and 9 or more at 60 Hz.
  - A direct loopback check against the real `Server` (9 back-to-back inputs) disconnected the client; 8 did not.
  - So today, a stall of 400 ms or more (a doubled RTO, or Windows' higher minimum RTO plus RTT) kicks the player.
  - Raising HZ without changing this rule would kick on a single loss.

## 3. Options

Each option keeps the owner's invariants:
- the server alone decides position, elevation, floor, hits, HP and loot;
- one floor solver (`World.move`) and one `same_level` rule (M1-A, M3-4);
- no duplicated rule logic;
- single-player replays unchanged.

### (a) Stay fully authoritative; tune

- **Changes.**
  - Send an input frame immediately on a key change or action, in addition to the 20 Hz heartbeat. This removes the
    0–50 ms send wait from (1).
  - Replace the per-tick "more than 8" rule with a token bucket, for example a sustained 2 × HZ per second with a burst
    of 2 s.
  - Set `TCP_NODELAY` explicitly *(asyncio sets it on new connections; verify)*.
  - Optionally a higher tick rate (30 Hz), or an adaptive interpolation delay for peers.
  - Optionally, extrapolate the local avatar by one tick between snapshots, to remove the 20 Hz stepping.
- **Protocol.** Send-on-press and the token bucket need no wire change. HZ is an implicit constant on both sides
  (`Playback`, input expiry). Changing it needs v3, or HZ in the welcome frame.
- **Parity.** None affected. A higher HZ reduces the tick quantisation already noted as risk R3 (plan §7.3).
- **Cheating.** None. A burst allowance must stay bounded, because inputs are cheap to forge in quantity.
- **Complexity and risk.** Low. The tick rate costs server CPU per tick (M1-B-2 measured scene cost) and 1.5–3×
  bandwidth (still under 30 KB/s for 8 players at 60 Hz).
- **Effect.** About −25 ms p50 everywhere from send-on-press *(inferred from the model's U(0,50) term)*. 30 Hz:
  −16 ms p50 at 0 ms, and the quantisation floor drops about a third (measured). **It cannot remove the round trip**:
  at 100 ms RTT the local avatar still starts moving after more than 100 ms.
- **Tests.** Probe-based acceptance on a virtual clock; a burst-tolerance test against the real `Server`.

### (b) Client-side prediction and reconciliation, own movement only

- **Changes.**
  - The client already builds the room's `SceneRoom` from its own files, with the server's collision world (identity
    check, `scene_client.py:155`).
  - It applies each input to its own avatar immediately, through **the same per-body step** the authority uses.
  - It keeps unacknowledged inputs. On each snapshot it resets to the server's row and replays the inputs the server
    hasn't processed. It smooths the remaining correction over a few frames.
  - `SceneRoom.step`'s per-player body (movement, bounds, input expiry) is extracted into one function that both sides
    call. This keeps the single floor solver and adds no second movement implementation.
- **Protocol (v3).** The client needs to know which input each snapshot reflects, so the player row gains the last
  input `seq` the server applied: `[entity, x, y, facing, elevation, floor, seq]`. That keeps one shared encoding per
  room (`server.py:113`, `:205-218`).
- **Parity.** The same code path, so no divergence by construction, apart from:
  - solids changing between prediction and authority: a gate opening, an enemy dying;
  - float drift across platforms.
  Both are corrected on the next snapshot. Other players are not solid for movement (`scene_room.py:560-563`), so
  peers never cause mispredictions.
- **Cheating.** No new authority. Prediction is presentation only, and the server still validates `check_levels`.
  The client's predicted elevation and floor must come from the same `World.move`; it never sends them.
- **Complexity and risk.** Medium.
  - Visible snaps when a prediction is wrong (gate timing, doors, the input-expiry rule).
  - M3's acceptance currently reads the local avatar at the server row. At loopback the two converge within a frame
    *(inferred)*, but tests must allow convergence.
- **Effect.** The local avatar moves on the next frame, at most 16.7 ms, at any RTT *(inferred)*. Fairness for the
  attacker-motion scenarios moves towards 0 (§2.3) *(inferred)*.
- **Tests.**
  - Virtual-clock prediction vs authority: zero divergence with no loss and static solids.
  - Bounded corrections under jitter and loss.
  - Stairs: the predicted elevation and floor equal the authority's once it has caught up.
  - A parity test that both sides call the one step function.

### (c) Local attack presentation; server-confirmed hits

- **Changes.**
  - On a press, the client immediately plays the attack animation through the same
    `request_animation_state(..., attack_anim)` path Combat uses (`combat.py:136-137`), plus sound and rumble. It
    mirrors the cooldown locally so it never shows a swing the server will refuse (the cooldown comes from the
    template, `scene_room.py:430`).
  - Hit flash, HP and death show **only** on server confirmation.
  - Peers see others' swings.
- **Protocol (v3).** Counters, not events, so a missed snapshot is never ambiguous:
  - a per-player `attack_seq` (in the row, or a parallel list);
  - a per-enemy `hit_seq` in `enemies` rows, `[id, hp, hit_seq]`.
- **Parity.** Reuses single-player's own presentation parameters. No rule logic on the client.
- **Cheating.** None; presentation only.
- **Complexity and risk.** Low to medium.
  - Swing-without-hit is normal and must read as a miss, not lag.
  - A cooldown mismatch (`ceil(cooldown × HZ)` ticks vs seconds) needs one shared conversion.
- **Effect.** Swing feedback within one frame at any RTT. The hit still arrives about RTT + 50 ms later (§2.2)
  *(inferred)*.
- **Tests.** Virtual-clock tests: swing on the next frame; the hit flash only after the counter changes; no swing
  during cooldown; a refused hit (cross-floor) shows a swing and no flash.

### (d) Server-side lag compensation (rewind) for hit detection

- **Changes.**
  - The authority keeps a short per-tick history of target bodies (position, elevation, collider), for example 5
    ticks.
  - An attack input carries the client's interpolation time (the `Playback` cursor, a tick with a fraction).
  - The server evaluates `_attack` with the **attacker at its current pose** and **targets rewound** to that time,
    clamped to the oldest allowed tick. `same_level` uses the rewound target's elevation; the floor solver is not
    re-run.
- **Protocol (v3).** An optional `view_tick` on attack inputs, bounded by the newest snapshot tick the client could
  have had and by the cap.
- **Parity.** Single-player has no latency. Rewind evaluates the same `_attack` and `same_level` on historic bodies,
  with no new rule *(design constraint)*.
- **Cheating and fairness.** A client can claim any view time within the cap. PvE victims are AI, so the cost of
  "hit after it moved away" falls on nobody. PvP is out of scope; there the victim pays, and the cap matters.
- **Complexity and risk.** Medium. It is only useful once enemies move.
- **Effect.** Moving-target disagreement 0% with an ideal rewind (§2.3); small residuals from time quantisation
  *(inferred)*. **No effect** on the dominant attacker-motion error.
- **Tests.** Probe scenario as acceptance; a cap-boundary test; a stale `view_tick` beyond the cap clamps rather than
  refuses *(OD5)*; a cross-floor rewound target is refused.

### (e) Combinations

The measurements rank the levers.

| Lever | Effect | Needs |
|---|---|---|
| (b) own-movement prediction | Fixes the felt delay of movement and the dominant fairness error | The v3 acknowledgement |
| (c) local swing | Fixes "my attack did nothing" | — |
| (a) send-on-press and the burst fix | Cheap and needed regardless | — |
| (d) rewind | Matters only with moving enemies | Moving enemies (M4-4) |

(b) without (c) still leaves attacks feeling dead. (d) without (b) fixes the smaller half of fairness.

## 4. Recommendation: (a) + (c) + (b), then moving enemies, then (d) if measured necessary

**M4-1 — robustness and send-on-press** (no protocol change; `mesh_net` and tests only):
- Send-on-change input, and a token-bucket rate limit in `Server` and `WorldServer`.
- Promote the probe's link model to a test helper, `tests/net_latency.py`, reusing `tests/net_sim_time.py` where a
  real `Server` and client are needed.
- **Acceptance:**
  - 9–40 back-to-back inputs after a simulated 2 s stall keep the session, and sustained floods are still refused.
  - The virtual-clock first-move median drops by at least 20 ms at every profile (probe).
  - All M3 tests, replays 13/13, and graphics-free tests green.

**M4-2 — protocol v3 and attack presentation:**
- v3 adds the `seq` acknowledgement in player rows, `attack_seq` per player and `hit_seq` per enemy. Optional
  `view_tick` is reserved but unused.
- A v2 peer is refused explicitly, as D1 did (`protocol.py:1-6`).
- The client shows a local swing (c) and a confirmed hit flash.
- **Acceptance:**
  - The version-refusal tests (v2 to v3, both directions).
  - Malformed, stale and inconsistent v3 frames are refused whole.
  - Virtual-clock tests: swing within one frame at every profile; a hit flash only after confirmation; no swing in
    cooldown; a cross-floor refusal shows a swing and no flash.
  - The `"v": 2` literals in about 10 `tests/test_mesh_net_*` files are updated.

**M4-3 — own-movement prediction and reconciliation (b):**
- Extract the per-body step from `SceneRoom.step` into one function used by the authority and the client. Predict,
  replay unacknowledged inputs, and smooth corrections. Peers stay on `Playback`.
- **Acceptance (virtual clock, probe scenarios):**
  - Local first move within one frame at every profile.
  - Zero corrections with no loss and static solids.
  - p95 correction at most one tick's step (7.5 px) at 100 ms, ±10 ms, 1%.
  - The stairs scenario's level-caused disagreement down from 29% to under 5% at 100 ms.
  - An HD-2D parity test: the predicted elevation and floor equal the authority's after settle.
  - M3's acceptance unchanged in intent: the own avatar converges to the server row.

**M4-4 — enemies move on floors server-side (if OD7):**
- The authority runs the authored mover behaviours it can reproduce. `FloorRoute` comes first, on `World.move`/
  `World.path`, the same solver.
- Enemy rows gain position, elevation and floor; clients show them through `Playback`.
- Movers it can't reproduce are refused at load, as N6 does for anything it can't run (`scene_room.py:291-294`).
- **Acceptance:**
  - Single-player vs authority parity of a `FloorRoute` walk at equal deltas, as M1-A-3 did for players.
  - The probe's moving-target scenario on the real mover.
  - Replays unchanged.

**M4-5 — lag compensation (d), only if M4-4's measured moving-target disagreement at the agreed envelope exceeds the
owner's budget (OD5):**
- Rewind history, `view_tick`, and the cap.
- **Acceptance:** the probe shows disagreement under the budget; cap and cross-floor tests.

**M4-6 — rendered evidence:**
- A small asyncio TCP delay proxy in `tooling/`. Two hidden windows (non-activating hook) through it at 100 and
  200 ms. Framebuffer evidence of the local swing, prediction and confirmed hit, in the gpu lane's style
  (`tests/test_mesh_net_hd2d_gpu.py`).
- Descriptive timings only, never gates.

Each PR is bounded, independently reviewed, and keeps M1-A/M3 parity. Every stage re-runs the probe and records the
table in its PR.

## 5. Owner decisions needed

1. **OD1 — latency envelope.** Proposed:
   - *responsive* to 100 ms RTT (±10 ms jitter, 1% loss): local movement and swing within one frame, hit confirmation
     p50 at most RTT + 75 ms;
   - *playable, never unfair in rules* to 200 ms;
   - beyond that, best effort.
2. **OD2 — protocol v3.** Acceptable, with an explicit refusal of v2 and no downgrade, as D1? (Required by (b), (c)
   and (d).)
3. **OD3 — client prediction of the local avatar's movement.** Acceptable? The server stays authoritative. The cost
   is occasional visible corrections.
4. **OD4 — local attack presentation.** A swing is shown before confirmation; hits, HP and death only on confirmation.
   Acceptable?
5. **OD5 — lag-compensation policy.** Recommended:
   - defer until enemies move (M4-4);
   - PvE only;
   - maximum rewind 200 ms (4 ticks at 20 Hz), clamped and never refused;
   - never rewind the attacker;
   - `same_level` on the rewound target.
   An alternative is to never rewind.
6. **OD6 — tick rate.** Stay at 20 Hz for M4 (recommended; send-on-press and prediction recover most of the gain), or
   move to 30 Hz. The input-burst fix must come first either way.
7. **OD7 — moving enemies.** Is server-side enemy movement on floors (M4-4) part of M4? Online combat against static
   enemies is what exists today. The coordinator's earlier M4 proposal listed it; the owner's D7 scope is "responsive
   combat".
8. **OD8 — virtual-clock acceptance thresholds.** Probe numbers are deterministic, not wall-clock. May M4 PRs gate on
   them (for example "first move within one frame")? Wall-clock timings stay report-only (D5 spirit).
9. **OD9 — transport.** Stay on TCP for M4 (recommended). Retransmission stalls drive p95 (§2.2, §2.5), but UDP and a
   reliability layer are a separate architecture decision.
10. **OD10 — combat timing parity.** Should the server mirror single-player's 0.2 s lingering hitbox (4 ticks) instead
    of a one-tick check? This is a server-only change that is forgiving under latency. Single-player stays unchanged.

## 6. Risks

- **Prediction errors near changing solids and floors.** Doors, gates, dying solid enemies, stair edges. Mitigation:
  correct on every snapshot; the stairs and floor parity tests.
- **Float determinism across platforms.** Small drift in the shared step. Mitigation: always reconcile; never trust
  the prediction.
- **Duplicated logic creeping in.** Mitigation: one extracted step function and a parity test that both sides import
  it, the M1-A pattern.
- **A protocol v3 ripple.** About 10 test files plus the M3 tooling. Mitigation: one PR (M4-2) that touches only the
  version and new fields.
- **The model is optimistic.** RTO 200 ms; real WANs have bursty loss. Mitigation: the M4-6 rendered evidence
  through a real delay proxy, and a real-network play-feel check before promising action-game responsiveness (as N5.1
  said).
- **Player-perceived unfairness at the BODY boundary** remains until (b). The server's rule never changes; owner D8
  stands.

**Out of scope:**
- RPG content;
- M5 persistence (N8 schema);
- M6 production;
- PvP;
- UDP transport;
- internet hosting, authentication and anti-abuse beyond the input bucket;
- 8-direction facing on the wire, unless OD10 needs it.

## 7. Coordination

- **M3 acceptance** (`tests/test_mesh_net_hd2d_gpu.py`, `tooling/m3_two_client_evidence.py`, `tests/test_mesh_net_hd2d.py`)
  stays green at every stage.
  - Rows still carry elevation and floor, and `check_levels` still validates them.
  - With prediction (M4-3), the own avatar is drawn at its predicted pose. At loopback that converges to the server's
    row, and the tests compare after settle.
  - M4-2 updates the version literals in the same PR.
- **Replays** are single-player and must stay 13/13 with no golden updates. M4 changes `mesh_net` and adds client
  presentation; it changes no engine rule. The OD10 change is server-only. Extracting the step function moves code
  inside `mesh_net` only.
- **The graphics-free authority** (`test_mesh_net_scene.py`, `test_mesh_net_world.py`) stays import-clean: the shared
  step uses `engine.physics_model` and `engine.hd2d.world` only.
- **Extended** (Ubuntu and Windows, gpu shards) is dispatched for M4-3, M4-4 and M4-6, which touch the play path. The
  hidden-window rule applies. The owner's desktop is never automated.
- **M5 planning** can proceed in parallel. Nothing here changes the N8 store.

## Appendix: reproduce

```powershell
$env:PYTHONPATH = 'D:\Games\Mesh-M4design'
py -3.13 tooling/m4_latency_probe.py --json out20.json             # §2 tables (seed 7, 6 sessions per profile)
py -3.13 tooling/m4_latency_probe.py --hz 30 --json out30.json     # what-if: 30 Hz tick and send rate
py -3.13 tooling/m4_latency_probe.py --hz 60 --json out60.json     # what-if: 60 Hz
```

Each run is about 1–2 minutes, headless and deterministic per seed. The 30 and 60 Hz what-if p50 local first move at
0 / 100 / 200 ms RTT (with jitter and loss on the latter two): 30 Hz 38 / 145 / 250 ms; 60 Hz 15 / 128 / 228 ms. At
60 Hz, 1% loss produced input bursts of 9 or more per tick, which the current rate limit would disconnect (§2.5).
