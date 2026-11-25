# S1: stabilization investigation (S1-0)

S1-0 was investigation and planning only: no production code changed.

**Baselines:**
- parts A–D were checked at `9d3580b9` (`redesign/visual-editor`);
- the integration tip at synthesis is `7b2b884e`.

**Start with the health report, then the decision brief.**

## The five S1-0 deliverables

| # | Document | What it answers |
|---|---|---|
| 1 | [10_health_report.md](10_health_report.md) | Technical Debt and Architecture Health Report: bottom line, what works, findings by class, corrections, the #629 reconciliation, metrics, what we could not check, provenance |
| 2 | [11_subsystem_risk_map.md](11_subsystem_risk_map.md) | Subsystem Risk Map: severity, defects, architectural risks, coupling, ownership, test reality and reliability per subsystem |
| 3 | [12_stabilization_roadmap.md](12_stabilization_roadmap.md) | S1 Stabilization Roadmap: stages S1-1 to S1-7, the per-item fields, exit criteria E1–E12, and an appendix mapping every issue to its roadmap item |
| 4 | [13_testing_ci_proposal.md](13_testing_ci_proposal.md) | Testing and CI Improvement Proposal: costed changes, the lane map, the flake policy and growth rules |
| 5 | [14_owner_decision_brief.md](14_owner_decision_brief.md) | Owner Decision Brief: D1–D15, each with options, a recommendation and consequences |

## Investigation parts (inputs)

| Part | Document | Scope |
|---|---|---|
| A | [01_audit_reconciliation.md](01_audit_reconciliation.md) | Reconciles the triage, #629 and the filed issues; new runtime findings; data-integrity and destructive-operation sweep |
| B | [02_contracts_lifecycle_coupling.md](02_contracts_lifecycle_coupling.md) | Real-window vs test-double contracts; Studio-authored gameplay matrix; entity and event lifecycle; duplicate implementations and coupling |
| C | [03_testing_ci_debt.md](03_testing_ci_debt.md) | Test portfolio, mutation probes, CI and Extended timing, gates, flakes, M3/M4 debt, costed recommendations |
| D | [04_developer_workflows.md](04_developer_workflows.md) | Create → import → author → play → save → export → multiplayer, end to end; shipped templates and chapters |

## Evidence

- [evidence/](evidence/): repro and scan scripts. Each repro exits 1 while its defect is present. Run with `PYTHONPATH=<checkout> py -3.13 docs/s1/evidence/<script>.py`.
- [evidence/data/](evidence/data/): CI run and job history, the timing report, mutation results and the test-portfolio CSV.
- [evidence/s1v/](evidence/s1v/): verification of #651–#654 on generated projects. It covers all 7 `mesh new` templates and Studio-created projects, authored through tools only, played through each project's own `main.py`, and exported with the bundled engine.

## External inputs (not on this branch)

- **Owner-supplied independent audit:** draft PR #629, `docs/audits/s1_independent_runtime_audit_2026_11_25.md` on `docs/s1-0-independent-runtime-audit-20261125`.
- **Coordinator triage:** `audit/deep-audit-triage:docs/audits/deep_audit_2026_11/TRIAGE.md` and its `repro/` scripts.
- **GitHub issues** #612, #618–#624, #627, #631, #632, #636–#660, #663 and #496, with their challenge-review and s1v comments; merged PR #347.

## Provenance note

**This branch is pushed and the repository is public.**
- Commit `035d0280` contains the owner's Windows username inside temp paths in 7 copied s1v outputs, so it is publicly readable through that commit.
- `30d44f27` scrubbed it, and the current tree is clean.
- Six tracked files that predate S1 also contain the username.
- Rewriting or deleting the branch, and scrubbing those six files, is owner decision D15.

See `10_health_report.md` §8.
