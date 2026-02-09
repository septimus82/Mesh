"""Policy test: stateful behaviours must participate in save/restore.

Every Behaviour subclass that holds **mutable gameplay state** (HP, cooldowns,
locked/looted flags, counters, etc.) MUST implement ``saveable_state()`` and
``restore_state()``.  Behaviours that only hold configuration or transient
rendering state may be added to the allowlist with justification.

This test scans ``engine/behaviours/`` via the behaviour registry and
programmatically verifies the contract.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from pathlib import Path
from typing import Any

import pytest

import engine.behaviours as _behaviours_pkg
from engine.behaviours.base import Behaviour

# --------------------------------------------------------------------------- #
# Allowlist — behaviours with mutable __init__ attrs that are intentionally
# NOT persisted.  Each entry must include a one-line justification.
# --------------------------------------------------------------------------- #
_SAVE_EXEMPT: dict[str, str] = {
    # Render-only / transient state — re-derived from scene on load
    "SwitchInteract": "Visual toggle state is re-initialised from scene JSON",
    "DoorLock": "Lock state is re-initialised from scene JSON (TODO: add save)",
    "RewardChest": "Loot state is re-initialised from scene JSON (TODO: add save)",
    "EventLogger": "Debug-only; no gameplay state",
    "DamageOnTouch": "Transient collision helper; no meaningful state",
    "Hitbox": "Transient collision helper; no meaningful state",
    "Collectible": "One-shot pickup; entity is removed after collection",
    "PickupCollectible": "Mirror of Collectible pickup logic",
    "Projectile": "Short-lived entity; destroyed on impact",
    "MainMenuBehaviour": "UI-only behaviour; no gameplay state",
    "IncrementCounterOnEvent": "Fires once then idle; state is in GameState counters",
    "SetGameStateOnEvent": "Fires once then idle; state is in GameState flags",
    "EnemyAI": "Re-derived from scene + patrol data on load",
    "FollowBehaviour": "Transient chase; target re-acquired each frame",
    "FollowPathBehaviour": "Transient path following; re-derived from scene",
    "DropTable": "Config-only loot table reference",
    "CameraFollowBehaviour": "Re-derived from scene config",
    "PlayerController": "Input handler; state is in GameState + Health",
    "SceneExit": "Config-only zone trigger",
    "SceneTransition": "Config-only zone trigger",
    "Combat": "Combat state is transient per-encounter",
    "RangedEnemyAI": "Re-derived from scene + patrol data on load",
    "PatrolChaseBehaviour": "Re-derived from scene + patrol data on load",
    "Shooter": "Transient projectile spawner; config-only",
    "SpriteAnimatorBehaviour": "Re-derived from spritesheet on scene load",
    "ListenForEvent": "Transient event listener; no persistent state",
    "GrantExperience": "One-shot grant; state is in GameState",
    "OfferPerkChoice": "UI-only behaviour; no persistent state",
    "ToggleSwitch": "Visual toggle state; re-initialised from scene JSON",
    "TriggerZoneBehaviour": "Transient zone trigger; re-initialised from scene",
    "SequencePlayer": "Transient animation sequence; re-derived on load",
    "ParticleEmitter": "Transient visual effect; no persistent state",
}


def _import_all_behaviour_modules() -> None:
    """Import every module under engine.behaviours so all @register_behaviour
    decorators fire and subclasses are visible to ``Behaviour.__subclasses__()``."""
    pkg_path = Path(_behaviours_pkg.__file__).parent
    for info in pkgutil.walk_packages([str(pkg_path)], prefix="engine.behaviours."):
        try:
            importlib.import_module(info.name)
        except Exception:
            pass  # some modules may require arcade; skip them


def _all_behaviour_classes() -> list[type]:
    """Return every concrete Behaviour subclass discovered in the engine."""
    _import_all_behaviour_modules()

    result: list[type] = []
    seen: set[type] = set()
    queue = list(Behaviour.__subclasses__())
    while queue:
        cls = queue.pop()
        if cls in seen:
            continue
        seen.add(cls)
        if not inspect.isabstract(cls):
            result.append(cls)
        queue.extend(cls.__subclasses__())
    return sorted(result, key=lambda c: c.__name__)


# Attributes that strongly suggest mutable gameplay state
_MUTABLE_INDICATORS = frozenset({
    "hp", "max_hp", "_dead", "alive", "dead",
    "locked", "looted", "enabled", "activated", "consumed", "_consumed",
    "cooldown", "cooldown_remaining", "timer", "_timer",
    "counter", "count", "_count",
    "state", "_state", "phase", "_phase",
    "target", "_target",
    "current_step", "step_index",
    "visited", "_visited",
    "triggered", "_triggered",
})


def _has_mutable_gameplay_state(cls: type) -> bool:
    """Heuristic: does the class set any indicator attribute in __init__?"""
    try:
        src = inspect.getsource(cls.__init__)
    except (TypeError, OSError):
        return False
    for attr in _MUTABLE_INDICATORS:
        if f"self.{attr}" in src or f"self._{attr}" in src:
            return True
    return False


def _has_saveable(cls: type) -> bool:
    return (
        hasattr(cls, "saveable_state")
        and callable(getattr(cls, "saveable_state", None))
        and hasattr(cls, "restore_state")
        and callable(getattr(cls, "restore_state", None))
    )


class TestSaveParticipationPolicy:
    """Behaviours with mutable state must opt-in to save or be in the allowlist."""

    def test_stateful_behaviours_have_save_or_are_exempt(self) -> None:
        classes = _all_behaviour_classes()
        assert classes, "No Behaviour subclasses found — import issue?"

        violations: list[str] = []
        for cls in classes:
            name = cls.__name__
            if not _has_mutable_gameplay_state(cls):
                continue  # stateless — fine
            if _has_saveable(cls):
                continue  # has contract — fine
            if name in _SAVE_EXEMPT:
                continue  # explicitly allowed
            violations.append(name)

        if violations:
            msg = (
                "Behaviours with mutable gameplay state that lack "
                "saveable_state()/restore_state() and are not in the "
                f"allowlist:\n  {', '.join(sorted(violations))}\n\n"
                "Either implement the save contract or add to "
                "_SAVE_EXEMPT with justification."
            )
            pytest.fail(msg)

    def test_allowlist_entries_still_exist(self) -> None:
        """Every entry in the allowlist must correspond to a real class.
        Remove stale entries when behaviours are deleted or renamed."""
        classes = _all_behaviour_classes()
        class_names = {cls.__name__ for cls in classes}

        stale = sorted(set(_SAVE_EXEMPT) - class_names)
        if stale:
            pytest.fail(
                f"Stale entries in _SAVE_EXEMPT (class no longer exists): "
                f"{', '.join(stale)}"
            )
