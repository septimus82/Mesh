# Monster RPG — Build Roadmap & Handoff

**Purpose:** a self-contained plan so the project can continue *without* live direction — follow the
recipe and the slice list below. Pair this with the architecture doc
[`docs/design/monster_battle_core.md`](design/monster_battle_core.md) and the engine audit
[`docs/design/vertical_slice_game.md`](design/vertical_slice_game.md).

---

## North Star

A **monster-capture/breed action-RPG on Mesh**. A *hybrid*: a real-time action overworld (Mesh already
does this) **+** turn-based monster battles **+** capture **+** party/box **+** breeding **+** AI-assisted
content authoring. That combination — action overworld + turn battles + AI authoring — is the thing RPG
Maker can't do, and the reason to build on Mesh instead of shipping faster in RPGM.

**Yardstick:** explore → walk into the grass → a turn-based battle → weaken & capture a wild monster →
build a party → eventually breed them.

## Honest scope reality (read before committing more)

- Mesh gives you the **overworld half for free** (movement, scenes/transitions, NPCs, dialogue, deep
  quests, zones/triggers, save, items). You are building the **monster-RPG half** from scratch.
- **Two large builds:** (1) the turn-based **battle engine** — bounded, deterministic, data-driven, so
  it's AI-/grunt-friendly; (2) the **UI/menu layer** — Mesh's *weakest* area, and a monster game is
  wall-to-wall menus (battle, party, summary, box, breeding, bag). The UI is the real risk.
- **RPGM is faster to ship** (mature monster plugins exist). Mesh = build the engine but own it + AI
  authoring + the action hybrid. We chose Mesh deliberately, eyes open.

## Architecture (decided — see `docs/design/monster_battle_core.md`)

- A **battle is a MODE on `GameWindow`** — not a separate scene, not just an overlay.
- Three objects:
  - **`MonsterBattleController`** — pure state machine (turn resolution, no engine imports).
  - **`MonsterBattleMode`** — `GameWindow` integration: pause overworld, show overlay, apply result, resume.
  - **`MonsterBattleOverlay`** — the UI view (HP/menus); blocks input.
- **Reuses** the existing pause boundary (the paused tick still updates UI), `UIController.input_blocked`,
  the event bus, and `GameState.values` for `monster_party`/`monster_box`/`monster_instances` persistence
  (no parallel save file).
- The turn-based monster system is **parallel to the existing real-time action combat**, which *stays* for
  the overworld. Keep the two combat models cleanly separated.

## How to build a slice (the recipe — follow for EVERY slice)

1. **One slice = one branch** (`feat/...`), one focused change.
2. **Keep the battle core pure** — no `GameWindow`/scene/save/UI/arcade imports in `battle_model`,
   `data_load`, `battle_controller`. Add a **purity-guard test** that imports the module with no runtime.
3. **Deterministic** — inject a seeded RNG; never use module-level `random`.
4. **Headless tests** where possible. Run them with an explicit basetemp to dodge the known Windows
   temp-cleanup noise:
   `pytest -p no:cacheprovider --basetemp=<a fresh dir>`
5. **Keep the board green** — full suite `0 failed` with `--basetemp`. (A spurious `PermissionError` on
   Windows temp cleanup without `--basetemp` is *noise*, not a real failure.)
6. **Constraints:** never touch `user_settings.json` or `docs/audits/`; don't push to `main` (push a
   branch, merge via PR); verify the branch against `origin` before merging.
7. **Authoring help:** a local 14B (e.g. `qwen2.5-coder`) is *unreliable* at tool-driven staging — use it
   for content brainstorming only. Use cloud Claude (or hand-code) for engine work that needs correctness.

---

## Status — Phase 0 (proving slice: encounter → 1v1 battle → capture → party)

**DONE & merged:**

| Slice | What | Where |
|---|---|---|
| MON-0a | pure battle math: `resolve_move`, type chart, damage formula, faint | `engine/monster/battle_model.py` |
| MON-0b | JSON loaders + validators (species/moves/type-chart) | `engine/monster/data_load.py`, `assets/data/monster_*.json` |
| MON-0c | pure `MonsterBattleController` state machine (choose→resolve→faints→won/lost, speed order) | `engine/monster/battle_controller.py` |
| MON-0d | runtime battle **mode** shell (pause overworld + blocking placeholder overlay + result→`GameState.values` + `monster_battle_ended` event) | `engine/monster/battle_mode.py` |
| MON-0e | overworld encounter trigger (deterministic weighted roll → `start_monster_battle` + return context; `enabled`/flag/cooldown gates) | `engine/behaviours/monster_encounter_zone.py`, `engine/monster/encounter.py` |
| MON-0f | **playable battle UI** — HP bars/text, log, Fight/Bag/Run, move list, real mouse+keyboard input seam. Dogfood verdict: *primitive but functional = Phase-0 UI question PASSED*. Debug launch: **F3 then F12**. | `engine/monster/battle_mode.py` |
| MON-0f-polish | **turn pacing** — resolved turn is presented step-by-step (held menu; advance on Enter/Space or a ~0.7s dt timer; HP drops *with* its log line, not at submit); lethal turn shows the faint line then ends. | `engine/monster/battle_mode.py` |
| MON-0g | **capture + party** — pure seeded catch formula (`capture_rate` + HP fraction); Bag→ball decrements/blocks-at-0/continues-on-fail; caught monster → party (or box when full); `monster_party`/`box`/`instances`/ball count survive a real `SaveManager` save→load round-trip. | `engine/monster/capture.py`, `engine/monster/collection.py` |
| MON-0h | **XP + level** — pure XP curve + victory XP + `apply_experience` (level/stat recalc via `derive_stats` + auto-learn next learnset move); win grants XP with paced "gained/grew/learned" log lines; xp/level/known_moves persist through save. | `engine/monster/progression.py` |

> **Launch-key lesson (MON-0f):** debug hotkeys belong as explicit branches in
> `engine/game_runtime/input_dispatch.py` (like F6/F9), gated on `engine_config.debug_mode` — NOT in the
> capture key-router (its debug gating reads a *different* flag `window.show_debug`, plus scope/modifier
> predicates, and shadowed three attempts). A unit test on `input_controller.on_key_press` will not catch
> this — test through `input_dispatch.on_key_press` with the real bindings, and **dogfood the live key**.

**REMAINING Phase 0 — build each as its own slice (goal / scope / tests):**

### MON-0i — Menu toolkit + party view  **(REQUIRED EARLY — not polish)** *(next)*
- **Goal:** stop hand-coding every menu before party/box/breeding make it unbearable — and finally *see*
  your caught monsters.
- **Scope (minimal):** a reusable runtime **menu stack** (push/pop, top-only input) + **focus model**
  (up/down/Enter/Esc) + a vertical **selectable list** + a detail **panel** + a **confirm modal**, assembled
  from `engine/ui/widgets.py` primitives, routed through the real `UIController` input path. First consumer:
  a **party view** opened from the overworld that lists `monster_party` and shows a selected monster's
  basic stats. Defer tabs/grid/scroll/box-UI until a slice needs them.
- **Tests (drive real input):** stack push/pop routing; up/down/Enter/Esc focus + activation; modal blocks
  the lower menu; party view lists caught monsters and selection shows stats. **Dogfood live.**

> **Phase-0 GATE:** after MON-0a–0g (+ MON-0i), *play it* — grass → battle → catch → it's in your party.
> If the architecture feels sound and the menu grind is tolerable **with** the toolkit, commit to the full
> campaign. If the UI fights you even with MON-0i, RPG Maker is the honest fallback.

---

## Phases beyond 0 (higher level — slice these later)

- **Phase 1 — Battle depth:** full move/type/status systems, monster switching, multi-monster parties,
  trainer/enemy battle AI, evolution.
- **Phase 2 — Monster systems:** PC box/storage, **breeding** (compatibility → egg → stat/move inheritance
  — the genre differentiator), held items, the bag, shops.
- **Phase 3 — The game:** the actual world (towns/routes), story, gym/progression, the monster roster,
  built with AI authoring + your **RPGM PNG assets** (sprites/tilesets/battlers/parallaxes port directly —
  they're just images; you already imported parallax assets successfully).
- **Cross-cutting:** UI/menu polish; reconcile the two `QuestManager` modules (`engine.quests` is the
  canonical runtime one).

## Key references

- **Architecture:** `docs/design/monster_battle_core.md`
- **Engine capability audit / vertical-slice design:** `docs/design/vertical_slice_game.md`
- **Done modules:** `engine/monster/{battle_model,data_load,battle_controller,battle_mode}.py`
- **Data files:** `assets/data/monster_{species,moves,type_chart}.json`
- **UI widgets to reuse for MON-0f/0i:** `engine/ui/widgets.py`
- **Overworld encounter-cleared primitive (real-time combat, from the earlier GAME-1a):**
  `engine/behaviours/encounter_cleared.py`

## Risks & honest notes

- **UI is THE risk.** Do MON-0i (menu toolkit) before party/box/breeding scale up, or it becomes a slog.
- **Local 14B models are unreliable** at tool-driven authoring/staging — use cloud Claude or hand-code for
  anything that must be correct; local is fine for ideas/content drafts.
- **Keep the battle core pure** — that purity is *why* it's testable and trustworthy. Don't let
  `GameWindow`/scene/save leak into `battle_model`/`data_load`/`battle_controller`.
- **Board hygiene:** always run the suite with `--basetemp`; the Windows temp-cleanup `PermissionError` is
  spurious. After a burst of fast PRs, do a gate-triage pass (separate real failures from Windows noise;
  fix real ones, never mass-baseline).
- **One checkout:** work from a single repo path (a user-owned folder, e.g. `C:\Users\slebb\source\Mesh`,
  not `Program Files`), and launch everything from there — mixed checkouts cause silent root/path mismatches.
