# Phase 38 Architecture Hardening

This phase hardens orchestration boundaries without changing gameplay behavior.

## What moved out of `GameWindow`

Three non-rendering orchestration responsibilities now live behind pure service facades:

- `engine/services/input_service.py`
  - Window input callbacks (`key`, `mouse`, `text`) dispatch through `InputService`.
- `engine/services/persistence_service.py`
  - Scene flow, scene persistence, and undo orchestration dispatch through `PersistenceService`.
- `engine/services/replay_service.py`
  - Deterministic debug bundle capture/export and scene snapshot helpers.

`GameWindow` keeps the same public methods, but those methods now forward to service instances.

## Singleton Registry Rules

`engine/singletons.py` is now the central access point for mutable singleton state.

- Use `get_registry()` for singleton access.
- Use `reset_registry_for_tests()` in tests that require deterministic reset.
- Registry-managed mutable singleton state includes:
  - RNG singleton (`rng_service`)
  - action runtime cache globals
  - editor shortcut warning cache
  - behaviour builtins-loaded sentinel
  - encounter theme manager singleton

Policy tests enforce:

- No direct imports of `rng_service` / `get_rng` outside the registry.
- No new tracked singleton globals outside the allowlist.

## Typing Island Expansion

`tooling/mypy_island.py` now includes:

- `engine/services/input_service.py`
- `engine/services/persistence_service.py`
- `engine/services/replay_service.py`
- `engine/singletons.py`

These modules are expected to remain clean under strict island checks.

## Safe Expansion Pattern

When extracting more responsibilities:

1. Move orchestration into a service with explicit dependencies.
2. Keep window/controller public APIs as shims first.
3. Add a contract test for deterministic behavior.
4. Add/adjust policy ratchets if singleton/global state is involved.
5. Add the new module to mypy island only after it is clean.

