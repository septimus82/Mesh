# Arcade 3 Migration Status

**Last reviewed:** 2026-06-03

## Status

Arcade 3 migration is in **stabilization/sign-off**:

- Runtime dependency is pinned to `arcade>=3,<4`.
- CI has a required `arcade3-canary` lane.
- Canary validates:
  - targeted Arcade 3 compatibility smoke tests,
  - runtime replay smoke with expected hash check,
  - installed-wheel replay smoke in an isolated venv.

## Compatibility Shims

These shims are intentional and currently part of the supported runtime path.

### Long-term (keep)

- `engine/arcade_compat.py`
  - Framebuffer bind/clear/restore compatibility (`use` vs `activate` semantics).
- `engine/lighting/__init__.py:_resolve_light_symbols()`
  - Light module resolution across known Arcade layouts
    (`arcade.experimental.lights`, `arcade.lights`, `arcade.future.light`).

### Temporary (revisit after stability window)

- Multi-signature `LightLayer.draw(...)` fallback chains in:
  - `engine/lighting/shadow_pipeline.py`
  - related hard-shadow composite fallback paths

Rationale: these keep rendering resilient across minor API shifts, but they add maintenance
surface and should be simplified once API behavior is confirmed stable across releases.

## Sign-off Checklist

- [x] Required Arcade 3 canary lane exists in CI.
- [x] Replay hash canary checks deterministic runtime output.
- [x] Installed-wheel replay smoke runs in CI.
- [x] Full local test suite and `verify-all` pass.
- [ ] Manual in-game visual smoke (lighting/shadows) on Arcade 3 in a real scene.

## Recommended Next Cleanup (post sign-off)

1. Remove dead/unused Arcade 2-era fallback branches if still present.
2. Keep only one preferred `LightLayer.draw` compatibility path per callsite.
3. Re-ratchet replay hash only when behavior changes are intentional.

