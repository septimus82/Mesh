# M4 checkpoint: responsive server-authoritative online co-op combat (draft for the owner)

> **Status:** DRAFT. M4-0 to M4-6 are built (M4-6 in review). This is the agreed M4 stop: nothing beyond M4 is
> started, and nothing here is a new measurement campaign. Every number comes from
> `docs/plans/m4_online_combat.md` (cited as "plan §…") or from the M4-6 rendered runs
> (`docs/reviews/m4_rendered_evidence/`, cited as "evidence"). Ranges are [lowest, highest] over seeds 7/8/9 ×
> 24 sessions, at 20 Hz.
>
> **Nothing here says the game feels good.** These are simulation and rendered-timing results. Whether it is pleasant
> to play is the owner's judgement after playing (`docs/plans/m4_playable_demo.md`), and that includes which queue
> preset to keep.

The owner's checkpoint asks for five things:
1. **A playable two-client combat demo:** `tooling/m4_demo_world.py`. It is an HD-2D crossing with walking bandits on
   the ground, the stairs and the bridge deck, plus a 2D room through a door. Its server switches
   `--queue drain|deep|small` and `--rewind on|off`.
2. **Reproducible launch instructions:** `docs/plans/m4_playable_demo.md`.
3. **Measurements and visual evidence:** §1 below and `docs/reviews/m4_rendered_evidence/README.md`.
4. **Remaining problems, risks and debt:** §3 and §4.
5. **Recommended next steps, not started:** §5.

## 1. Key numbers per round trip

Each profile adds ±10 ms jitter and 1% loss, with every loss stalling as a TCP retransmission does (RTT + 200 ms);
"0 (none)" has no jitter and no loss. Where the presets differ, values read drain / deep / small. Drain is the
provisional default.

### 1.1 What the player sees of their own actions (the same in every preset)

| Measure | 0 (none) | 0 ±10 1% | 50 ±10 1% | 100 ±10 1% | 200 ±10 1% | Source |
|---|---|---|---|---|---|---|
| Local first move, p50 / max ms | 8.0–8.5 / 16.7 | 7.6–8.2 / 16.7 | 8.0–8.7 / 16.7 | 8.1–8.6 / 16.7 | 8.1–8.9 / 16.7 | plan §4 M4-3, "The chosen design, measured" |
| Before M4-3, for comparison | 54.0–60.8 / 115 | 65.8–71.4 / 446 | 106.9–113.5 / 567 | 157.4–167.6 / 714 | 260.9–264.6 / 2102 | same table |
| Local swing shown | within one frame | within one frame | within one frame | within one frame | within one frame | plan §4 M4-2 acceptance; M4-3 acceptance table |
| Local swing visible in rendered frames (one run each), ms | — | 7.1 | not run | 6.3 (drain), 15.9 (deep), 18.0 (small) | 15.4 | evidence, measurements table |

Since M4-6 the swing has a picture: a white crescent over the hitbox. Before it, nothing was drawn (the packaged
player has no `attack` clip).

### 1.2 Hit confirmation, p50 ms (press to the first frame showing the server's hit)

| Case | 0 (none) | 0 ±10 1% | 50 ±10 1% | 100 ±10 1% | 200 ±10 1% | Source |
|---|---|---|---|---|---|---|
| OD1's aim, RTT + 75 ms | 75 | 75 | 125 | **175** | 275 | plan revision 3, OD1 |
| Standing, still enemy (2D) | 61.8–65.7 | 72.0–77.3 | 115–123 | **166.0–175.9** | 269–273 | plan §4 M4-4, hit confirmation table |
| Standing, walking enemy 70, before M4-5 | 62–66 | 67–82 | 110–117 | 160–174 | 273–276 | same |
| Standing, walking enemy 70, **with M4-5** | not reported | not reported | not reported | **165.8–180.3** | not reported | plan §4 M4-5, hit confirmation table |
| Standing, enemy on the stairs, with M4-5 (before) | — | — | — | **181.4–187.7** (166.7–168.4) | — | same |
| Standing, enemy on the bridge deck, with M4-5 (before) | — | — | — | **178.6–181.8** (159.5–173.5) | — | same |
| Swing made while walking, still enemy (drain / deep / small) | 65–70 (drain, deep) | 120–123 / 269–271 / — | 165–173 / 359–371 / — | **210–229 / 457–474 / 200–205** | 321–325 / 585–593 / — | plan §4 M4-4 and M4-3 ("Its costs"; drain thresholds) |
| Rendered runs, one swing each (rewind on) | — | 81.2 | not run | 168.0 / 161.2 / 182.0 | 273.2 | evidence |

Why rewind slows confirmation (plan §4 M4-5, measured by the #626 reviewer): at 100 ms ±10 1% over 12 sessions, every
real hit landed on hitbox update 1 without rewind. With rewind, 5 of 21 confirmed hits (moving target 70) and 8 of 29
(stairs) landed on updates 2–3.

### 1.3 Hit fairness against moving enemies: disagreement before → after lag compensation

The share of all sampled presses where the window's picture and the server's answer differ, drain (plan §4 M4-5,
disagreement table). For moving both, the ideal rewind bound is in brackets.

| Scenario | 0 (none) | 0 ±10 1% | 50 ±10 1% | 100 ±10 1% | 200 ±10 1% |
|---|---|---|---|---|---|
| Moving target 70 (52 px/s) | 6.0–6.1 → 0 | 6.4–6.5 → 0–0.1 | 8.1–8.5 → 0.2 | 10.2–10.3 → **0.4–0.6** | 14.2–15.4 → 2.9–3.6 |
| Moving target 150 (88.6 px/s) | 11.3–11.6 → 0 | 12.0–12.1 → 0.1 | 15.9–16.1 → 0.1–0.5 | 19.8–20.1 → **0.6–1.5** | 27.3–28.3 → 5.4–7.2 |
| Stairs, moving enemy | 16.0–16.3 → 0 | 17.5–18.2 → 0.1 | 22.8–23.5 → 0.2–0.5 | 28.2–29.6 → **1.3–1.5** | 38.2–39.7 → 7.6–8.3 |
| Bridge deck, moving enemy | 6.0–6.1 → 0 | 6.4–6.5 → 0–0.1 | 8.0–8.5 → 0.2–0.3 | 10.2–10.4 → **0.4–0.7** | 14.3–15.2 → 3.2–3.4 |
| Under the deck (never in reach) | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 | 0 → 0 |
| Room transition (arrival) | 6.2–7.5 → 0 | 8.8–10.1 → 0–0.2 | 10.2–14.0 → 0–0.4 | 14.0–17.2 → **0.1–1.4** | 12.8–21.7 → 2.0–5.2 |
| Moving both (walking attacker), drain | 3.3–3.4 → 0.7–0.8 [0.7–0.8] | 3.7–4.2 → 1.0–1.2 | 4.4–4.7 → 1.2–1.4 | 4.8–5.5 → **1.4–1.6** [1.2–1.5] | 6.4–7.4 → 2.1–2.8 |
| Moving both, deep | — | 5.1–5.3 → 1.3–1.4 | 5.8–6.2 → 1.8–2.1 | 7.2–7.7 → 2.9–3.5 | 8.2–9.1 → 4.4–4.9 |
| Moving both, small | — | 3.7–3.9 → 0.9 | 3.6–4.2 → 0.8–1.1 | 4.3–4.7 → 1.4–1.6 | 6.5–7.4 → 2.7–3.0 |

- What remains comes from views beyond the 300 ms cap, which are clamped. At 100 ms, 9.0–10.5% of a still attacker's
  presses need more than 300 ms (all during a retransmission stall). **At 200 ms, 97.8–99.2% do** (plan §4 M4-5).
- "Looked like a miss but hit" still happens: 0–1.7% of such presses at 100 ms, and 0.8–5.1% at 200 ms (plan §4 M4-5).

### 1.4 Attacks shown but never executed

| Case | 0 (none) to 100 ±10 1% | 200 ±10 1% (drain / deep / small) | Source |
|---|---|---|---|
| Standing, still enemy (2D), of 720 | 0 in every preset | 3–10 in every preset, all stale | plan §4 M4-3 (b), M4-4 |
| Walking, still enemy (2D), of ~693 | 0 in every preset | 17–25 / 75–139 / 7–11, all stale | same |
| Standing, moving target or stairs, of 192 | 0 | 1–7, unchanged by M4-5 | plan §4 M4-4, M4-5 |
| Moving both (walking), of 192 | 0 | 3–10 / 18–35 / 1–8 | plan §4 M4-4 |
| Rendered runs (stale, refused) | 0, 0 | 0, 0 | evidence |

None was refused in the cooldown or dropped from a full queue. Every one was a claim older than the 600 ms window,
which the window then shows as a miss (plan §4 M4-3 (b)). At 200 ms they are reported, not accepted (the owner's
words).

### 1.5 Corrections and discarded steps

| Measure | 0 ±10 1% | 50 ±10 1% | 100 ±10 1% | 200 ±10 1% | Source |
|---|---|---|---|---|---|
| Movement corrections at 100 ms, n / max px (drain / deep / small) | — | — | 72–89 / 7.5; 0; 486–565 / 45 | — | plan §4 M4-3, drain thresholds table |
| With jitter alone (100 ms ±10, no loss) | — | — | 0; 0; 83–147 | — | same |
| Large stair corrections a minute, drain (round 4) | 0 | 0 | **0.8–1.3** (worst 19–27 px, none over 30 px) | **1.8–3.0** (worst 55–64 px; 2–5 over 30 px in 6 min) | plan §4 M4-3, round 4 table |
| Large stair corrections a minute, deep | 0 | 0 | 0 | 0.17–0.5 (worst 36 px) | plan §4 M4-3, large stair corrections table |
| Large stair corrections a minute, small | 9.2–10 (worst 21 px) | — | 11–12.8 (worst 81 px) | 12.8–14.7 (worst 124 px) | same |
| Corrections beside a walking solid enemy (moving both): n, max px, large a minute (drain / small / deep) | — | — | 732–796, 7.5–99, 0–0.23 / 768–827, 94.5–109.5, 11.1–13.0 / 449–468, 3.5, 0 | 941–1107, 93–128, 0.45–1.14 / 955–1122, 109.5–133.5, 8.2–11.8 / 705–720, 93–128, 0.45–0.91 | plan §4 M4-4, the three presets |
| Discarded movement steps, overflow / drained, of ~28,550 inputs, drain | 0 / 88–90 | 0 / 74–112 | 0 / 114–133 | 262–282 / 148–157 | plan §4 M4-3 (a) |
| The same, deep | 0 / 0 | 0 / 0 | 0 / 0 | 262–284 / 0 | same |
| The same, small | 799–831 / 0 | — | 1393–1502 / 0 | 1877–2031 / 0 | same |
| Peer sees a walking player, p50 ms at 100 ms (drain / deep / small) | — | — | 270–291 / 516–541 / 260–266 | — | plan §4 M4-3, M4-4 |
| Rendered runs: corrections (max px) | 5 (7.5), drain | — | 7 (7.5) drain; 0 deep; 15 (37.5) small | 9 (7.5), drain | evidence |

With no loss and static solids, drain and deep give 0 corrections (plan §4 M4-3).

## 2. Owner decisions OD1–OD11

| OD | What was approved | Status | Evidence |
|---|---|---|---|
| OD1 | Responsive movement and swing feedback through 100 ms ±10 1% | **MET** (measured): local move ≤ 16.7 ms, swing within one frame, visible since M4-6. Feel not yet judged by a person | plan §4 M4-3; evidence |
| OD1 | Median hit confirmation ≤ RTT + 75 ms | **NOT MET**. Standing, still enemy: 166.0–175.9 ms (0.9 ms over on one seed). Walking: 210–229 (drain). With M4-5, moving target 165.8–180.3, stairs 181.4–187.7, bridge 178.6–181.8 | plan §4 M4-3, M4-4, M4-5 |
| OD1 | Playable and server-authoritative at 200 ms; limitations reported | **PARTIAL**. Server authority holds and the limitations are reported (§3). "Playable" is the owner's call after playing | plan §4 M4-3 "Honest limitations at 200 ms" |
| OD2 | Protocol v3, explicit v2 refusal, no downgrade | **MET**. No protocol change since M4-2 | plan §4 M4-2 |
| OD3 | Local prediction through the shared movement implementation | **MET**. One `SceneRoom.walk`; the duplicate scan and spy tests | plan §4 M4-3 |
| OD4 | Immediate local swing, sound and feedback; outcomes server-confirmed | **MET** since M4-6: the crescent on the press, the sound and the rumble; the hit burst keyed off `hit_seq`. The swing *animation* clip is still missing from the content | this PR; evidence |
| OD5 | PvE-only lag compensation, 300 ms cap, never rewinding the attacker | **MET** for the co-op prototype, with the documented cheating bound (§4) | plan §4 M4-5, §6 |
| OD6 | Stay at 20 Hz | **MET** (a cost: §3, enemy walk speed) | — |
| OD7 | Server-authoritative moving enemies through one shared model | **MET**. Parity with single-player at equal deltas | plan §4 M4-4 |
| OD8 | Same-seed comparisons, ≥ 3 seeds × 24 sessions; p95 report-only | **MET** throughout | plan §4 |
| OD9 | TCP stays | **MET** (a cost: §4, head-of-line) | — |
| OD10 | Server matches single-player's persistent hitbox timing | **MET**. Parity test; single-player unchanged | plan §4 M4-2 |
| OD11 | Bounded input queue, one input a tick, proper acks (starting depth 2) | **MET** as a mechanism. Depth 2 failed the correction criterion and was adjusted by measurement, as OD11 allows. **All three presets fail some important criterion, so none is declared the winner.** The owner chooses after playing | plan §4 M4-3 round 3, acceptance per preset |

Against the M4-3 acceptance per preset (plan §4 M4-3, round 3):
- **drain** meets §4's criteria as written, but makes large stair corrections (about one a minute at 100 ms);
- **deep** breaks condition 6: its backlog lasts the whole walk;
- **small** fails the correction criteria;
- **every preset** misses OD1's hit-confirmation aim.

## 3. Remaining noticeable gameplay problems

- **Hits confirm slower than OD1's aim.** About 170 ms at 100 ms standing, and 210–230 ms for a swing made while
  walking (drain). With lag compensation it is a little slower again against moving enemies (§1.2). Deep's walking
  swing is about 460 ms.
- **The 300 ms rewind cap is nearly always reached at 200 ms** (97.8–99.2% of views clamped). Moving targets there are
  judged 300 ms back, not where they were shown: 2.9–8.3% disagreement remains (§1.3).
- **At 200 ms some swings come back as misses (stale).** For walking swings that is 2.4–3.6% with drain and 10.8–20.1%
  with deep (§1.4).
- **Enemies walk slower online.** `FloorRoute` stands for one update at each 0.5 m waypoint, which is 50 ms at 20 Hz.
  So 70 px/s authored walks 52 px/s online, against about 64 in single-player (plan §4 M4-4).
- **Enemies on screen are two ticks behind** and freeze for up to a retransmission under loss, then jump. For the
  52 px/s walker that is 16.7–19.4% frozen frames at 100–200 ms (its waypoint pauses included), with the longest
  freeze 333–350 ms at 100 ms and 417–433 ms at 200 ms (plan §4 M4-4).
- **Corrections beside walking enemies.** Pushing against a walking solid enemy corrects on most snapshots (3.5 px
  each). Under loss a few are large: up to 99 px at 100 ms with drain, and 11–13 large ones a minute with small
  (plan §4 M4-4).
- **Stair corrections.** With drain, about one large one a minute at 100 ms, each with a floor snap. Small has many
  more (§1.5).
- **No attack animation in the content.** The packaged player has no `attack` clip, so the M4-6 crescent is the
  swing's only picture. A swing pose would be content work.
- **Little HP feedback in the world client.** The bandits' HP is not on screen, and the burst is the only sign of a
  hit until the bandit dies.

## 4. Architectural risks and technical debt

- **Greedy-liar burst (the 600 ms claim window).** A dishonest client can bank a burst after a pause: 13 attacks on
  consecutive ticks at a 2-tick cooldown, and 2 at the co-op room's 10. It needs attention before any public
  deployment (plan §6).
- **`view_tick` cheating bound (M4-5).** A client may pick the most favourable enemy pose of the last 300 ms. That
  gains up to speed × 0.3 s of reach along the motion (+31% / +52% for the bandit), and about 8 px of elevation on
  stairs. **PvE only, never PvP as built** (plan §6).
- **TCP head-of-line blocking (OD9).** One lost segment holds every later frame for RTT + RTO. That burst is the
  source of nearly every correction, every stale claim and every clamped view (plan §4 M4-3, M4-5).
- **The M4-6 proxy is chunk-level.** It delays socket reads, not segments: frames in one chunk share one fate, and
  the loss model is per message, not bursty (plan §4 M4-6 groundwork). The real-network feel is unmeasured.
- **The input queue is undecided.** Drain is provisional, and three presets stay in the code until the owner chooses.
- **Rendered evidence is one run per cell**, with window A sharing a process with the authority and the proxy.
- **#612 is still open:** an ep05 replay wall-clock budget test that failed once on hosted Linux. It is unrelated to
  `mesh_net`, which the engine never imports.
- **Frame-rate dependence of `FloorRoute`'s waypoint pause** (the slower online walk). Fixing it changes single-player
  traces, so it is an owner decision (plan §4 M4-4).
- **Simulation optimism.** The probe has no phase drift and models a retransmission as RTT + 200 ms. Real WANs have
  bursty loss (plan §6).

## 5. Recommended next steps (not started)

1. **The owner plays the demo** at 0/50/100/200 ms with each queue preset and rewind on and off
   (`docs/plans/m4_playable_demo.md`). Decisions: the queue preset, and whether OD1's confirmation aim (missed by
   0.9–12.7 ms standing) is acceptable for the co-op prototype or needs work.
2. **If confirmation must improve**, candidates measured or named in the plan, none built:
   - a shorter interpolation delay than two ticks;
   - a client-side drain (skip a send while the server is behind);
   - (outside OD6) a higher tick rate.
3. **Before any public deployment:**
   - bound `view_tick` and the claim window by each client's measured delay instead of flat caps;
   - add a per-player rate check;
   - keep PvE only (plan §6).
4. **An owner decision on `FloorRoute`'s frame-rate dependence** (matching enemy speed online), which changes
   single-player traces.
5. **Content:** an attack pose for the packaged player, and an on-screen enemy HP indication in the world client.
6. **A real-network play check** (two PCs, a real WAN) before promising action-game responsiveness (plan §6).
