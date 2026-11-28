# S1 intake — independent runtime-boundary audit (2026-11-25)

> **Evidence intake, not S1 implementation approval.** This document faithfully records an independent audit report supplied by the owner for the forthcoming S1 technical-debt investigation. The author of this documentation has not rerun the auditor's disposable-project reproductions. The related GitHub issues, PR status and integration baseline were checked when the report was recorded. No production code changes are included here.

## Provenance and scope

- **Audited branch and exact commit:** \`redesign/visual-editor\` at \`49686331f1ec526b051b04851c5d7a89ce04e5b6\`.
- **Method reported by the auditor:** real runtime paths in isolated checkouts/disposable projects; each finding reproduced; audited checkout remained clean; no CI runs or repository changes made by that audit.
- **Verification scope reported:** 29 focused existing tests passed across vendor integrity, cutscenes, puzzles, quest progress and bounded networking history. Separate real-runtime probes exposed the failures below. No full-suite rerun or GPU performance measurements were made.
- **S1 purpose:** capture reproducible integration defects, avoid duplicate audits, and prioritize real-runtime contract testing rather than expanding mock-only tests.

## Ranked findings

### 1. P1 — Legacy editor asset rename overwrites an existing destination

A disposable source and destination held distinct bytes. Through the real legacy-editor rename confirmation flow, renaming onto the occupied destination succeeded, destroyed its original bytes and removed the source. The filesystem commit uses \`os.replace\`.

**Reach:** legacy editor, not the main Studio workflow. **Correction:** evaluate the existing [PR #628](https://github.com/septimus82/Mesh/pull/628), linked to [issue #618](https://github.com/septimus82/Mesh/issues/618). Prove that both an already-occupied destination and one appearing after confirmation are refused with **both original files intact**. Include safe path/junction validation and no partial reference rewrite. This is a destructive operation and must fail closed.

### 2. P1 — Save slots cross project boundaries

Two real \`SaveManager\` instances for disposable projects A and B were run in one process while the working directory stayed at A. Both quicksave calls reported success; B overwrote A's slot and created no save in B. The non-exported save path is relative to the working directory even when the runtime API selects another project root.

**Correction:** anchor writes to the selected project root and define how existing relative saves remain readable without allowing cross-project overwrites. Regression: two independent projects, one process, unchanged working directory, distinct quicksave data and reloads. See [issue #623](https://github.com/septimus82/Mesh/issues/623). The audit ranks this P1 for data loss even though the pre-existing issue was recorded as P2 by path reachability; reconcile severity explicitly.

### 3. P1 — Reward chest reports success but grants nothing

A real \`GameWindow\` with an ordinary player and empty inventory opened a chest containing one healing potion and 10 gold. The chest marked itself looted and emitted \`reward_collected\`, yet the player received **neither the potion nor the gold**. The chest assumes inventory is attached to the actor; the unit-test actor has that interface, the real game path does not.

**Correction:** use production game-state inventory/currency APIs; choose and specify the full-inventory rule; mark looted and emit completion only after the award succeeds as intended. Regression through real \`GameWindow\`: empty inventory, full inventory, persistence/reentry as applicable. Extend [issue #627](https://github.com/septimus82/Mesh/issues/627), which previously described a suspected P2 full-inventory loss: this audit reports a **confirmed P1 empty-inventory failure**.

### 4. P1 — Authored actions and cutscene steps fail at the runtime boundary

A configured signal emitted in a live scene did not make the action list set its flag. Calling a production \`move_entity\` cutscene step raised \`AttributeError\`: the real \`SceneController\` lacks \`find_sprite\`, which a test double supplies. Existing evidence also documents behaviour-attribute and event-delivery mismatches.

**Correction:** align event subscriptions, entity lookup and runtime behaviour access with production contracts. Regression should create an authored scene, emit a signal, move a named entity and observe the target flag through the real delivery path, not a fake controller. See [issue #622](https://github.com/septimus82/Mesh/issues/622).

### 5. P2 in this audit — One quest event advances two consecutive stages

One kill signal plus one update completed both stages of a two-stage quest and awarded its 100-gold completion reward. A second quest-processing pass, intended to enable dependent quests, also processes the same event against the newly entered stage.

**Correction:** explicitly consume one event at most once per quest while retaining dependent-quest activation. Test both properties together through live quest processing. See [issue #621](https://github.com/septimus82/Mesh/issues/621). Earlier issue triage called this P1; reconcile the prioritization instead of silently changing it.

### 6. P2 in this audit — One-shot dialogue rewards reset on room re-entry

A 50-gold choice marked once paid 50 again after room re-entry (50 → 100). Consumption history is stored on the behaviour instance, which room loading recreates.

**Correction:** persist consumed authored choices under stable room/entity/choice identifiers in game state; test room re-entry and save/reload, including old saves lacking these records. See [issue #620](https://github.com/septimus82/Mesh/issues/620). Earlier issue triage called this P1; reconcile the prioritization.

### 7. P2 — Removed entities keep handling events

After an entity was removed, a door still responded to its unlock signal; a removed \`SetGameStateOnEvent\` sprite continued incrementing a live counter. Removal calls \`on_destroy\`, but these subscriptions are cleaned in \`destroy\`. A repeated room entry alone did **not** reproduce multiplying effects.

**Correction:** align entity lifecycle teardown and event unsubscription. Regression: remove the entity, emit its formerly subscribed event, and verify no observable state changes. Check existing issue tracking before creating a duplicate; this is a distinct lifecycle finding.

### 8. P2 in this audit — Ruff/mypy wrappers pass when their checker is missing

In a clean Python 3.13 environment without Ruff or mypy, both \`python -m tooling.ruff_gate\` and \`python -m tooling.mypy_gate\` reported success and exited 0. Hosted CI installs these tools, so this **does not prove** that hosted CI missed diagnostics; it proves local verification can give a false green.

**Correction:** treat failed checker import/startup and invalid output as gate failures. Test missing tool, genuine clean output and actual diagnostics separately. The broader CI baseline/allow-list concern remains distinct and not wholly reproduced in this audit. See [issue #624](https://github.com/septimus82/Mesh/issues/624).

## Improvements and exclusions

- The earlier vendor/shop bug from [issue #619](https://github.com/septimus82/Mesh/issues/619) has an integrated correction via [PR #625](https://github.com/septimus82/Mesh/pull/625). Focused regressions cover full stacks, unknown items and duplicate non-stackable items. Treat as a fixed defect with retained tests rather than opening another fix.
- Release replay verification is reported to run in ordinary CI, with the audited head's replay job passing. This is a narrower claim than proof that all quality gates are sound.
- The audit did **not** profile renderer performance, retest the full suite, or provide a full independent finding-to-finding mapping to the earlier external 13-findings audit.
- The major recurring test risk is **test doubles supplying interfaces absent from the actual runtime**. Avoid counting passing isolated tests as evidence that the authored game workflow functions.

## Recommended remediation order for S1 coordination

1. Complete and verify the existing destructive-rename fix, PR #628, rather than opening competing work.
2. Isolate save writes per selected project root, including compatibility and cross-project regression.
3. Fix the reward chest award contract, based on the confirmed empty-inventory case, and adopt a deliberate full-inventory policy.
4. Repair authored actions/cutscene runtime wiring using real game entry points.
5. Address quest event consumption, persistent one-shot dialogue rewards and removed-entity cleanup.
6. Make missing checker tools fail closed; investigate the broader baseline/allow-list concerns separately.

This sequence is an **audit recommendation**, not authorization to override already scheduled M4 work or S1 implementation gates. Confirm current branches and outstanding PRs before assigning workers.

## S1 investigation questions

- Which fake interfaces in tests differ from the production \`GameWindow\`, \`SceneController\`, behaviours and game-state APIs?
- Where do the event-bus, lifecycle, inventory and persistence responsibilities diverge between authoring and runtime?
- What small number of real-game smoke/integration checks would have caught these defects earlier?
- Which defects are already fixed, and which remain reproduced on the **current** integration tip after subsequent merges?
- What objective S1 exit gates demonstrate reliable create → author → play → reward/quest → save/reload → export workflows without an uncontrolled growth in test runtime?

**Do not re-label unresolved issues as fixed merely because their PR is open. Preserve reproducibility, compatibility and no-data-loss evidence.**
