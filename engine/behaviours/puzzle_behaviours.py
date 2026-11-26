"""Puzzle interaction behaviours."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import engine.optional_arcade as optional_arcade
from engine.inventory import get_or_create_inventory
from engine.log_utils import get_logger
from engine.paths import resolve_path

if TYPE_CHECKING:
    from arcade import Sprite

from ..event_emit import emit_gameplay_event
from ..events import MeshEvent
from .base import Behaviour, ParamDef
from .registry import register_behaviour

logger = get_logger(__name__)


def _show_picture(behaviour: Behaviour, path: str) -> None:
    """Swap the object's picture through the asset manager, as PictureByFlags does. A missing file keeps the current
    picture (the asset manager would show its placeholder)."""
    if not path:
        return
    assets = getattr(behaviour.window, "assets", None)
    if assets is None or not Path(resolve_path(path)).is_file():
        logger.warning("Picture '%s' not found; '%s' keeps its picture", path, getattr(behaviour.entity, "mesh_name", ""))
        return
    texture = assets.get_texture(path)
    if texture is not None:
        behaviour.entity.texture = texture


def _explicit_attr(ctx: object, name: str) -> Any:
    """Read only explicitly-defined attributes to avoid MagicMock auto attrs."""
    try:
        return object.__getattribute__(ctx, name)
    except Exception:
        return None


def _emit_puzzle_event(
    ctx: object,
    event_type: str,
    payload: dict[str, Any],
    *,
    source_entity_id: str,
    source_behaviour: str,
) -> None:
    """Preserve legacy MeshEvent emission while supporting gameplay_event_bus."""
    gameplay_bus = _explicit_attr(ctx, "gameplay_event_bus")
    if gameplay_bus is not None and hasattr(gameplay_bus, "emit"):
        emit_gameplay_event(
            ctx,
            event_type,
            payload,
            source_entity_id=source_entity_id,
            source_behaviour=source_behaviour,
        )
        return

    legacy_bus = _explicit_attr(ctx, "event_bus")
    if legacy_bus is not None and hasattr(legacy_bus, "emit"):
        legacy_bus.emit(MeshEvent(event_type, payload))
        return

    emit_gameplay_event(
        ctx,
        event_type,
        payload,
        source_entity_id=source_entity_id,
        source_behaviour=source_behaviour,
    )


@register_behaviour(
    "SwitchInteract",
    description="Emits an event when interacted with.",
    config_fields=[
        {
            "name": "event_id",
            "description": "Event ID to emit",
            "type": "string",
            "default": "",
        },
        {
            "name": "one_shot",
            "description": "If true, can only be used once",
            "type": "bool",
            "default": False,
        },
        {
            "name": "active_sprite",
            "description": "Sprite path for active state",
            "type": "string",
            "default": "",
        },
    ],
)
class SwitchInteract(Behaviour):
    """Emits an event when interacted with."""

    PARAM_DEFS = {
        "event_id": ParamDef(str, default="", description="Event ID to emit"),
        "one_shot": ParamDef(bool, default=False, description="If true, can only be used once"),
        "active_sprite": ParamDef(str, default="", description="Sprite path for active state"),
    }

    def __init__(self, entity: Sprite, window, **config) -> None:
        super().__init__(entity, window, **config)
        self.event_id = config.get("event_id", "")
        self.one_shot = config.get("one_shot", False)
        self.active_sprite = config.get("active_sprite", "")
        self.activated = False

    def on_interact(self, interactor: Sprite) -> None:
        if self.activated and self.one_shot:
            return

        if not self.event_id:
            return

        self.activated = True
        _emit_puzzle_event(
            self.window,
            self.event_id,
            {"source": self.entity},
            source_entity_id=str(getattr(self.entity, "mesh_id", "") or ""),
            source_behaviour="SwitchInteract",
        )

        _show_picture(self, self.active_sprite)  # "Picture once used"
        print(f"[Puzzle] Switch {self.entity} activated, emitted '{self.event_id}'")

    def can_interact_with(self, _actor: Sprite) -> bool:
        if self.activated and self.one_shot:
            return False
        return bool(self.event_id)

    def get_interact_label(self, _actor: Sprite | None = None) -> str | None:
        return str(getattr(self.entity, "mesh_name", "") or "Switch").strip() or "Switch"


@register_behaviour(
    "DoorLock",
    description="Unlocks when a specific event is received.",
    config_fields=[
        {
            "name": "unlock_event",
            "description": "Event ID that unlocks this door",
            "type": "string",
            "default": "",
        },
        {
            "name": "starts_locked",
            "description": "If true, starts in locked state",
            "type": "bool",
            "default": True,
        },
        {
            "name": "open_sprite",
            "description": "Sprite path for open state",
            "type": "string",
            "default": "",
        },
    ],
)
class DoorLock(Behaviour):
    """Unlocks when a specific event is received."""

    PARAM_DEFS = {
        "unlock_event": ParamDef(str, default="", description="Event ID that unlocks this door"),
        "starts_locked": ParamDef(bool, default=True, description="If true, starts in locked state"),
        "open_sprite": ParamDef(str, default="", description="Sprite path for open state"),
    }

    def __init__(self, entity: Sprite, window, **config) -> None:
        super().__init__(entity, window, **config)
        self.unlock_event = config.get("unlock_event", "")
        self.locked = config.get("starts_locked", True)
        self.open_sprite = config.get("open_sprite", "")
        self._picture_open = False

        self._unsubscribe = None
        if self.unlock_event:
            self._unsubscribe = self.window.event_bus.subscribe(self.unlock_event, self._on_unlock_event)
        # A door that starts unlocked opens on the first frame: the loader adds a solid sprite to the solid list after
        # this constructor (as ConditionalActivator notes).

    def pre_update(self, dt: float) -> None:  # noqa: ARG002
        if not self.locked:
            self._open()

    def _open(self) -> None:
        """Let the player through and show "Picture when open". Solidity is membership of the scene controller's
        solid list (what the movers collide with); the door never relocks."""
        solids = getattr(getattr(self.window, "scene_controller", None), "solid_sprites", None)
        if isinstance(solids, optional_arcade.arcade.SpriteList) and self.entity in solids:
            solids.remove(self.entity)
        if not self._picture_open:
            self._picture_open = True
            _show_picture(self, self.open_sprite)

    def _on_unlock_event(self, event: MeshEvent) -> None:
        if not self.locked:
            return

        print(f"[Puzzle] Door {self.entity} unlocked by event '{event.type}'")
        self.locked = False
        self._open()

        # Emit door_unlocked event for chaining.
        _emit_puzzle_event(
            self.window,
            "door_unlocked",
            {"door_id": getattr(self.entity, "id", "unknown")},
            source_entity_id=str(getattr(self.entity, "mesh_id", "") or ""),
            source_behaviour="DoorLock",
        )

    def destroy(self) -> None:
        """Unsubscribe from event bus on teardown."""
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None


@register_behaviour(
    "RewardChest",
    description="Spawns or enables a reward when unlocked.",
    config_fields=[
        {
            "name": "unlock_event",
            "description": "Event ID that reveals the reward",
            "type": "string",
            "default": "",
        },
        {
            "name": "item_id",
            "description": "Item ID to reward",
            "type": "string",
            "default": "",
        },
        {
            "name": "gold",
            "description": "Amount of gold to reward",
            "type": "int",
            "default": 0,
        },
    ],
)
class RewardChest(Behaviour):
    """Gives its item and gold once, when unlocked (Studio's "Treasure chest").

    The reward goes into the game-state inventory and the ``gold`` counter, all or nothing (#636, owner decision D7):
    a chest whose item the inventory can't take (full stack, owned non-stackable, unknown id) stays closed, gold
    included, and says why, as a pickup does. ``looted`` and ``enabled`` (unlocked) are facts in room memory (D6), so a
    looted chest stays looted, and a refused one stays unlocked, across re-entry and saves. A save from before facts
    has none: its chests are as authored (not yet looted)."""

    FACT_FIELDS = ("looted", "enabled")

    PARAM_DEFS = {
        "unlock_event": ParamDef(str, default="", description="Event ID that reveals the reward"),
        "item_id": ParamDef(str, default="", description="Item ID to reward"),
        "gold": ParamDef(int, default=0, description="Amount of gold to reward"),
    }

    def __init__(self, entity: Sprite, window, **config) -> None:
        super().__init__(entity, window, **config)
        self.unlock_event = config.get("unlock_event", "")
        self.item_id = config.get("item_id", "")
        self.gold = config.get("gold", 0)
        self.looted = False

        self._unsubscribe = None
        if self.unlock_event:
            self._unsubscribe = self.window.event_bus.subscribe(self.unlock_event, self._on_unlock_event)
            # Start hidden/disabled if waiting for event?
            # For now, let's assume it's a chest that unlocks, not spawns.
            # Or maybe it spawns. Let's assume it's visible but locked until event?
            # The prompt says "spawn or enable on door_unlocked".
            # Let's assume it's enabled (interactable) only after event.
            self.enabled = False
        else:
            self.enabled = True

    def _on_unlock_event(self, event: MeshEvent) -> None:
        self.record_fact("enabled", True)
        print(f"[Puzzle] RewardChest {self.entity} enabled by '{event.type}'")

    def destroy(self) -> None:
        """Unsubscribe from event bus on teardown."""
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

    def on_interact(self, interactor: Sprite) -> None:  # noqa: ARG002
        if not self.enabled or self.looted:
            return
        gs = self.window.game_state_controller
        inventory = get_or_create_inventory(gs.state.values)
        refusal = inventory.refusal(self.item_id) if self.item_id else None
        if refusal is not None:  # stays closed: nothing granted, nothing recorded, no event
            logger.warning("RewardChest '%s' refused: %s", getattr(self.entity, "mesh_name", ""), refusal)
            hud = getattr(self.window, "player_hud", None)
            enqueue = getattr(hud, "enqueue_toast", None) if hud is not None else None
            if callable(enqueue):
                enqueue(refusal, seconds=2.0)
            return
        if self.item_id:
            inventory.add_item(self.item_id)
        if self.gold:
            gs.add_counter("gold", self.gold)
        self.record_fact("looted", True)  # (only after the grant)
        print(f"[Puzzle] RewardChest looted! Item: {self.item_id}, Gold: {self.gold}")

        emit_gameplay_event(
            self.window,
            "reward_collected",
            {
                "source": self.entity,
                "item_id": self.item_id,
                "gold": self.gold,
            },
            source_entity_id=str(getattr(self.entity, "mesh_id", "") or ""),
            source_behaviour="RewardChest",
        )

    def can_interact_with(self, _actor: Sprite) -> bool:
        return bool(self.enabled and not self.looted)

    def get_interact_label(self, _actor: Sprite | None = None) -> str | None:
        return str(getattr(self.entity, "mesh_name", "") or "Chest").strip() or "Chest"
