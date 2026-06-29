# The Differentiator — Autonomous Companion ("train it, don't command it")

**Decided 2026-06-30.** The monster game's hook — ported from the user's RPG Maker MZ prototype
(`MonsterProject_Plan.md`, plugin `TrainableMonster.js`, Phases 0–4 all proven there). This is what makes
it the user's game and **not** Pokémon.

## The hook

You don't *command* the monster — you **raise** it. The monster is a **semi-autonomous agent with a
personality**: it fights on its own, choosing actions from behavior weights. You are the trainer — you
**Praise / Scold / Wait** to *reinforce* what it just did, and over time it **learns**. The game is the
**relationship** (earning trust, shaping a mind), not piloting a stat-puppet. User's words: *"training the
monster, not a loyal follower that obeys every whim — that's the challenge."*

## The model (from the proven prototype)

- **Temperament** (innate, stable, inheritable): `aggression` (pull to attack), `fear` (pull to defend/
  hesitate).
- **Relationship**: `trust` (praise ↑ / scold ↓; low trust → hesitation), `bond` (slow attachment; gates
  traits). These have **teeth**: neglected/mistreated monsters hesitate, freeze, or **flee and abandon you**;
  loyal ones stay.
- **Learned memory**: per-behavior weights (`learn.ATTACK / DEFEND / HESITATE`). Praise the last action
  raises its weight; scold lowers it. *This is the "learning."*
- **Mood**: short-term −100..100 layer (swings on praise/scold/win/loss, decays over steps).
- **Traits**: innate, inheritable (Brave, Timid, Loyal, Wild, Stubborn, Quick Learner…); bias learning,
  relationship gains, and behavior scores.
- **Behavior registry** (the engine): each behavior has `available(state, ctx)`, `score(state, ctx)`,
  `perform()`. Decision = score all *available* behaviors → **weighted-random** pick. Context-gated
  behaviors (HEAL/EAT/FLEE) only enter the pool when relevant. Adding a behavior = a few lines; learning +
  debug + reinforcement pick it up automatically.
- **Explainability**: every decision is inspectable ("why did it do that?" shows the scores).
- **Capture is a bond journey**: weaken → bait raises tameness → throw → caught monster starts *wary*
  (low trust); the relationship begins at capture.
- **Breeding inherits the personality**: temperament (parent avg ±), traits (% pass + mutation), learned
  habits (fraction of parent avg).

## What flips vs. what we keep

- **FLIP — the battle control layer.** Command-battler (MON-0/1): *player picks the move*. Companion model:
  *the monster decides autonomously (behavior registry); the player's turn = Praise/Scold/Wait reinforcing
  the last action.* Drop "Command: Attack/Defend" — direct orders fight the "it learns" concept.
- **KEEP — the whole battle substrate.** Damage, types, status, party/box, capture, XP, breeding, save
  persistence (MON-0/1) all carry over unchanged. **Mesh now has TWO RPG battle models on one substrate:**
  the command-battler AND the autonomous companion. Building the game = mostly the *fun bits* (the mind, the
  relationship), not re-coding from scratch.

## Why Mesh fits this *better than RPG Maker*

The monster is literally "a behavior **registry** that scores available behaviors and picks weighted-random,
shaped by learned weights, with explainable decisions." That **is** Mesh's component/behaviour + AI
architecture. In RPGM the user had to *fight* the battle engine (force Auto-Battle, override `makeActions`,
hook `processTurn`). In Mesh, an autonomous creature-agent is **native** — and "explainable decisions"
aligns with Mesh's AI-first north star. It also suits the **real-time action overworld** even better than
turns (a companion fighting *beside* you, acting on its own) — a later option.

## Starting target & port plan

**Start TURN-BASED** (reuses the MON-0/1 substrate; lowest lift). The real-time action-overworld companion
is a later option once the model is proven.

- **MON-2a (pure):** the companion "mind" — a pure behavior registry + weighted decision (temperament +
  learned weights → score available behaviors → seeded weighted-random pick), explainable. Mirrors prototype
  Phase 0. No UI/runtime. *(This is the soul's core; pure like MON-0a.)*
- **MON-2b:** reinforcement + relationship — Praise/Scold adjust learned weights; trust/bond model; mood.
- **MON-2c:** flip the battle control layer — the monster takes its turn via the registry; the player's
  command menu becomes **Praise / Scold / Wait** (reinforce last action). Reuse the battle mode/overlay +
  paced log.
- **MON-2d:** relationship teeth — HESITATE / FLEE gated by trust/bond; mood + traits bias scores; the
  "neglect has consequences" loop.
- **MON-2e+:** traits at capture/create; breeding inheritance of temperament/traits/learned habits (ties to
  the breeding substrate); optional map-side training loop + energy economy; per-monster food/heal.

## Status

The user's RPGM prototype **proves all of this is fun and works** (Phases 0–4 done). We are **porting a
validated design to the engine it should have been built on**, not inventing. Assets: the user already has
monster graphics made (in the RPGM project's `img/`). See [[monster-game-is-engine-tester]],
[[north-star-ai-first-engine]].
