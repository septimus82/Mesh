# S1 Owner Decision Brief

Each decision below gives the options, a recommendation and the consequences. **Bold** marks the recommended option.

The evidence is in `10_health_report.md` and the items in `12_stabilization_roadmap.md`. Nothing here is implemented until you approve it.

## At a glance

| # | Decision | Recommendation |
|---|---|---|
| D1 | Roadmap and scope | Approve S1-1 to S1-5 as exit-required; S1-6 and S1-7 best-effort |
| D2 | Severity disputes | #623 P1, #654 P1, #653 P2, #624 B P2/P3, #621 P2, #620 P1 |
| D3 | Legacy editor strategy | Repair the file ops (#641 + #631, #632); keep the editor out of game launches; retire it post-S1 |
| D4 | F3 debug mode in shipped games | Read-only overlays only; state-changing debug keys need an editor launch or an env var |
| D5 | One project-root resolver | Yes: one resolver, read-only fallback for old CWD saves |
| D6 | Room/entity state persistence | Per-entity facts in room memory |
| D7 | Item database scaffold policy | Scaffold a small starter `items.json` and degrade to an empty database |
| D8 | Draft PR #629 | Merge as historical evidence |
| D9 | CI dedup (changes what runs where) | Approve R1 and R4; approve R2 after measuring; R3 optional |
| D10 | Flake quarantine policy | Approve as written |
| D11 | Duplicate runtimes in S1 | Contain (bounded steps); no merges in S1 |
| D12 | Existing files with tool-written `hp: 1.0` | `mesh doctor` warning plus opt-in fix; never auto-rewrite |
| D13 | Owner hands-on Studio GUI acceptance as an exit step | Yes, once, at the end |
| D14 | Load-time entity gates and sample content | Keep the semantics; warn in tooling; convert the sample exits |

---

### D1: Approve the S1 roadmap and its finish line

**Options:**
- **A. Approve S1-1 to S1-5 (P0/P1 and gates) as exit-required, with exit criteria E1–E12. S1-6 and S1-7 are best-effort.**
- B. Make all seven stages exit-required.
- C. P0/P1 only, with no gates or CI work.

**Consequences:**
- **A:** about 35–40 PRs to the finish line, with P2 debt carried forward by name.
- **B:** adds about 16 PRs of convergence work, and S1 gets longer.
- **C:** fixes today's defects but leaves the five test patterns that produced them, so the same class recurs.

---

### D2: Severity disputes

| Item | View 1 | View 2 | Recommendation | Why |
|---|---|---|---|---|
| #623 (saves follow the CWD) | P1: part A, #629. Irreversible overwrite of another project's save; public `run_game` API | P2: triage, challenge review. The menu project switch is blocked in standalone launches | **P1** | The irreversible-loss convention (#618, #631) applies consistently. E7 requires the fix either way, and it is S–M |
| #654 (Shopkeeper never opens) | P2: challenge review. A Studio-only route exists (Interactable with `interact_event=open_shop`) | P1: s1v. That route is undiscoverable, the guide shows a never-sent event, and every generated project fails on the obvious path | **P1** | Same class as #640 and #622: a picker feature that silently does nothing. **Also decide:** on a talking NPC, the shop opens at the end of the conversation (recommended) or on a choice |
| #653 (flag-gated entities) | P1: part D | P2: challenge review, upheld by s1v (documented load-time semantics; Studio uses ConditionalActivator) | **P2** | Studio's supported path works; the affected exits are checkout-only sample content |
| #624 B (mypy count guard no-op) | P1: issue | P2/P3: challenge review (the baseline file is committed, so growth shows in diffs) | **P2/P3** (grouped with C/D at P2 in roadmap item 5.1) | — |
| #621 (two quest stages from one event) | P1: triage | P2: part A, #629 | **P2** | No shipped or authorable shape today; an over-grant, not a loss |
| #620 (once-reward repeats) | P1: triage, part A | P2: #629 | **P1** | It breaks an explicit Studio promise on the main path, without limit |
| #660, #631 | — | — | **Confirm P0 and P1** | Agreed by everyone who reviewed them |

**Consequence:** #623 and #654 stay in exit criterion E2 (fixed, or dispositioned by you).

---

### D3: Legacy editor strategy

**Context:**
- The legacy editor is 282 files, 59k lines, and is built into every GameWindow.
- #660 (P0, fix in flight) made it reachable in exported games.
- Its file ops are broken in a real window (#641, #631, #632).
- It still holds capabilities Studio lacks (#347's migration list): safe rename, move and delete, the item editor, Build for Windows, and more.

| Option | What | Cost | Consequence |
|---|---|---|---|
| **A. Repair file ops** | One root (#641), safe delete for every entry point (#631), unique trash (#632); re-verify #618 in a real window | M (3 PRs) | Keeps the capabilities; the code is already mutation-strong, only the root seam is wrong |
| B. Disable legacy delete, rename and move | They refuse with a message | S | Safest and smallest, but removes a capability Studio doesn't have |
| C. Retire the legacy editor | Remove it from the product | L | Out of S1 scope; blocked by the migration list |

**Recommendation:** **A**, with B as the fallback if A's review finds more hazards. Also **approve 6.8**: don't construct the legacy editor in game launches. This is defence in depth after #662, M, best-effort in S1. Keep C as the post-S1 goal, driven by #347's migration list.

---

### D4: What F3 debug mode may do in shipped games

**Context:**
- F3 toggles debug mode in any launch.
- Debug mode unlocks debug battles, F10 party breeding and the batching toggle, and, per #660, Ctrl+S scene save.

**Options:**
- **A. In non-editor launches, debug mode may show read-only overlays only. State-changing debug keys need an editor launch or `MESH_DEV_TOOLS=1`.**
- B. Disable F3 entirely in non-editor launches.
- C. Leave it as is.

**Consequences:**
- **A:** players can't cheat or write files, and developers keep diagnostics.
- B: simplest, but loses in-game diagnostics in `main.py` runs.
- C: leaves a suspected write path in exported games.

**If roadmap 1.2 shows that Ctrl+S writes into the bundle, it becomes a P0 regardless of this choice.**

---

### D5: One project-root resolver

**Options:**
- **A. One resolver for every project file read or written (saves, items, cutscenes, `savegame.py`, AI history), with a read-only fallback that still finds old CWD-relative saves.**
- B. Fix only the saves (#623).
- C. Require the CWD to be the project, and document it.

**Consequences:**
- **A:** closes the whole family that produced #623, #641 and the CWD-relative `cutscenes.json`.
- B: leaves the cutscene and item reads to fail the same way later.
- C: keeps `run_game(project_root=)` and the checkout project browser broken.

---

### D6: Room/entity state persistence model

**Options:**
- **A. Per-entity "facts" in room memory (game-state vars, carried in saves). Behaviours declare their fact fields, which are applied on construction. A missing record means "as authored".**
- B. Per-behaviour flags in game state (#620's original proposal), one ad hoc key per feature.
- C. Apply `saveable_state` on room entry.

**Consequences:**
- **A:** one mechanism for #620, #636, #639 and the suspected rows; old saves load.
- B: works, but repeats the design four times.
- C: still loses state for rooms other than the one the save was made in.

**Note:** saves made before the fix can pay a once-reward one more time after upgrading. This is unavoidable; document it.

---

### D7: Item database scaffold policy

**Options:**
- **A. The scaffold writes a small starter `assets/data/items.json` (for example a potion and a key), and a missing file degrades to an empty database with one log line instead of raising.**
- B. The engine ships a default item list used when the project has none.
- C. Degrade only, with no starter file.

**Consequences:**
- **A:** every picker item feature works in a new project, and nothing raises in old ones.
- B: hides project data inside the engine, and the export must carry it.
- C: no crash, but every item feature still does nothing until a creator hand-writes JSON, because Studio has no item editor.

**Also decide:**
- the full-inventory rule for chests and drops. Recommended, consistent with pickups: don't loot, toast "can't carry", keep the gold;
- **retiring the `lighting_playground` and `demo_slice` templates** (#656; recommended over porting them).

A Studio item operation is post-S1.

---

### D8: Draft PR #629 (the owner-supplied independent audit)

**Options:**
- **A. Merge it as historical evidence, together with or after the S1-0 docs.**
- B. Close it as superseded.

**Consequences:**
- **A:** keeps the owner-supplied input in the repo with its provenance (audited at `49686331`). `10_health_report.md` §5 maps all 8 findings to issues and status, so no edit to #629 is needed.
- B: loses the in-repo record.

---

### D9: CI dedup changes (these alter what runs where)

| Change | Effect | Risk | Recommendation |
|---|---|---|---|
| R1: fast tier not re-run in `verify` | −3.6 job-min per run | The fast-tier timing budget needs a new home (report-only, from pytest durations) | **Approve** |
| R2: in-suite verify-all out of the critical path | est. −1.5 to −3 min wall per OS | Unmeasured. Audit tests would read the `verify` job's reports | **Approve "measure first"; decide on numbers** |
| R3: fold the `web-smoke` job | −0.5 job-min | negligible | Optional |
| R4: push-side identical-tree dedup | up to −58 / −104 job-min per merge | Must never skip when the base moved; the #344 rule is the template | **Approve**, with the identical-tree proof linked in the run |

**Consequence of approving all:** per-merge cost goes from ≈ 345 to ≈ 200 job-minutes, and CI wall falls ≈ 1–3 min.

**Consequence of declining:** the new contract tests push CI p90 above today's 15.7 min, so B1's Linux shard split becomes mandatory to meet E10.

---

### D10: Flake quarantine policy

**Options:**
- **A. Adopt `13_testing_ci_proposal.md` §5:**
  - never weaken a flaky test;
  - quarantine only with an issue, a dated entry (expiry ≤ 30 days) and a report-only Extended lane that still runs the test;
  - a contract test enforces it;
  - no silent retries.
- B. Keep the current ad hoc practice.
- C. Allow automatic retries in required lanes.

**Consequences:**
- **A:** E9 becomes measurable and flakes stay visible.
- B: works today but doesn't scale.
- C: hides real races (NEW-15 is an ownership-race test) and contradicts "never weaken".

---

### D11: Duplicate runtimes: contain in S1, merge later?

| Pair | Contain in S1 (recommended) | Merge (post-S1) |
|---|---|---|
| a. Two quest managers | Default to `engine.quests`; move the tests; fix #621 and #644 (6.1, M) | Delete the lightweight manager |
| b. Two cutscene runtimes | `mesh cutscene validate` checks the live schema (6.2, S) | One runtime |
| c. Two hotkey systems | A binding-matrix test plus a lint for double bindings (6.3, M) | One dispatcher |
| d. Episode harness on MagicMock windows | One real-window episode; label the rest "harness" (6.4, M) | Move the harness onto real windows |
| e. mesh_net duplicating engine rules | Call the shared pure functions (drops, interaction ranking); add a gate parity test (6.5, S–M) | — |

**Recommendation:** **contain all five in S1 (best-effort, S1-6); no merges in S1.**

**Consequence:** the failure modes that S1-0 demonstrated are blocked. The structural duplication remains as named debt.

---

### D12: Existing projects with tool-written `hp: 1.0`

**Context:** fixing #651 stops new damage. But files that Studio, `mesh author` or MCP already wrote carry an explicit `hp: 1.0`.

**Options:**
- **A. `mesh doctor` warns about Health where `hp` equals 1 and `max_hp` is greater than 1, and offers an opt-in fix. Never rewrite silently.**
- B. Migrate automatically on load.
- C. Do nothing.

**Consequences:**
- **A:** creators see the problem and choose.
- B: risks overriding a deliberate 1 HP.
- C: old projects stay broken with no hint.

**Also approve:** re-blessing any replay or trace goldens that change because sample-content players get their stats' HP. Recommended: yes, after review of the diff.

---

### D13: Owner hands-on Studio GUI acceptance as an exit step

**Options:**
- **A. Yes:** once, at the end of S1, you author the E3 workflow project in the Studio GUI and play it (E12).
- B. No: rely on the ops-level e2e test.

**Consequences:**
- **A:** the only check of Studio's actual UI, since agents may not run visible GUI automation. It costs about an hour of your time.
- B: the picker UI → ops link stays verified by code reading only.

---

### D14: Load-time entity gates and sample content (#653, #658)

**Options:**
- **A. Keep the documented load-time semantics. `set_entity_fields` warns and points to `set_show_when`, and a one-off script converts the 65–71 sample exits to ConditionalActivator.**
- B. Re-evaluate entity gates at runtime (spawn inactive, re-check on flag change).
- C. Leave both.

**Consequences:**
- **A:** small, with no engine semantics change.
- B: more invasive, and changes documented behaviour.
- C: leaves sample chapters confusing, though checkout-only.

**Also decide:** whether to add walls around the 14 walk-round sample gates (#658). Recommended: only if the campaign is meant as a showcase, since it is checkout-only content.
