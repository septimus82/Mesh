# Agent Rules

NON-NEGOTIABLE RULES

1) Reuse-first: reuse existing seams/components; only add new components when clearly missing.
2) Test Integrity: never delete/skip/xfail/loosen tests; never replace specific asserts with vague ones.
3) Determinism: stable ordering, stable outputs; no time/random dependencies in tests.
4) AI-safe plans: plan.meta.touches is required and must include all action targets in ai_safe apply.
5) Shipping bar: full suite must be green; no “ignored flake”.

## How to run checks

- `python -m pytest -q`
- `mesh check`
- `mesh doctor --world ... --json`
- `mesh triage --world ... --out ... --write-artifacts`
