"""Inventory, equip, and unequip console command handlers."""

from __future__ import annotations

from typing import Any

from engine.console_runtime.utils import parse_int
from engine.inventory import get_or_create_inventory, load_item_database


# ---------------------------------------------------------------------------
# Dispatch-compatible handlers  (controller, args) -> bool
# ---------------------------------------------------------------------------

def handle_inventory(controller: Any, args: list[str]) -> bool:
    """``inventory`` command."""
    inventory = get_or_create_inventory(controller.window.game_state.values)
    subcommand = args[0].lower() if args else "list"

    if subcommand in {"list", "ls"}:
        _inventory_list(controller, inventory)
        return True

    if subcommand in {"add", "give"}:
        if len(args) < 2:
            controller.log("Usage: inventory add <item_id> [amount]")
            return True
        item_id = args[1]
        amount = 1
        if len(args) >= 3:
            parsed = _inventory_parse_amount(controller, args[2])
            if parsed is None:
                return True
            amount = parsed
        _inventory_add(controller, inventory, item_id, amount)
        return True

    if subcommand in {"remove", "rm", "take"}:
        if len(args) < 2:
            controller.log("Usage: inventory remove <item_id> [amount]")
            return True
        item_id = args[1]
        amount = 1
        if len(args) >= 3:
            parsed = _inventory_parse_amount(controller, args[2])
            if parsed is None:
                return True
            amount = parsed
        _inventory_remove(controller, inventory, item_id, amount)
        return True

    if subcommand == "clear":
        inventory.clear()
        controller.log("Inventory cleared")
        return True

    if subcommand == "show":
        overlay = controller.window.ui_controller.inventory_overlay
        if overlay is None:
            controller.log("Inventory overlay unavailable")
            return True
        overlay.set_visible(True)
        controller.log("Inventory overlay shown")
        return True

    if subcommand == "hide":
        controller.window.hide_inventory_overlay()
        controller.log("Inventory overlay hidden")
        return True

    if subcommand == "toggle":
        visible = controller.window.toggle_inventory_overlay()
        controller.log(f"Inventory overlay {'shown' if visible else 'hidden'}")
        return True

    controller.log("Usage: inventory [list|add|remove|clear|show|hide|toggle]")
    return True


def handle_equip(controller: Any, args: list[str]) -> bool:
    """``equip <item_id> [slot]``"""
    gs = getattr(controller.window, "game_state_controller", None)
    if gs is None:
        controller.log("[Equip] No game state controller.")
        return True
    if not args:
        controller.log("Usage: equip <item_id> [slot]")
        return True
    item_id = args[0]
    slot = args[1] if len(args) > 1 else None
    result = gs.equip_item(item_id, slot=slot)
    if result.get("ok"):
        controller.log(f"[Equip] Equipped {result.get('item')} to {result.get('slot')}")
    else:
        controller.log(f"[Equip] Failed: {result.get('reason', 'unknown')}")
    return True


def handle_unequip(controller: Any, args: list[str]) -> bool:
    """``unequip <weapon|armor|accessory>``"""
    gs = getattr(controller.window, "game_state_controller", None)
    if gs is None:
        controller.log("[Unequip] No game state controller.")
        return True
    if not args:
        controller.log("Usage: unequip <weapon|armor|accessory>")
        return True
    slot = args[0]
    result = gs.unequip(slot)
    if result.get("ok"):
        controller.log(f"[Unequip] Cleared {result.get('slot')}")
    else:
        controller.log(f"[Unequip] Failed: {result.get('reason', 'unknown')}")
    return True


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _inventory_list(controller: Any, inventory: Any) -> None:
    entries = list(inventory.list_items())
    if not entries:
        controller.log("Inventory: <empty>")
        return
    db = _inventory_db()
    controller.log("Inventory contents:")
    for item_id, amount in entries:
        label = _inventory_label(item_id, db)
        controller.log(f"  - {label} ({item_id}) x{amount}")


def _inventory_add(controller: Any, inventory: Any, item_id: str, amount: int) -> None:
    normalized = item_id.strip()
    if not normalized:
        controller.log("Item id required")
        return
    before = inventory.get_count(normalized)
    try:
        added = inventory.add_item(normalized, amount)
    except Exception as exc:  # noqa: BLE001
        controller.log(f"Inventory add failed: {exc}")
        return
    after = inventory.get_count(normalized)
    if not added:
        db = _inventory_db()
        definition = db.get(normalized) if db else None
        if definition is None:
            _inventory_unknown_item(controller, normalized, db)
        else:
            controller.log(
                f"{definition.name or normalized} already at max stack ({definition.max_stack})"
            )
        return
    delta = max(0, after - before)
    label = _inventory_label(normalized)
    controller.log(f"Added {delta} x {label}")


def _inventory_remove(controller: Any, inventory: Any, item_id: str, amount: int) -> None:
    normalized = item_id.strip()
    if not normalized:
        controller.log("Item id required")
        return
    before = inventory.get_count(normalized)
    if before <= 0:
        controller.log(f"Item '{normalized}' not currently in inventory")
        return
    try:
        removed = inventory.remove_item(normalized, amount)
    except Exception as exc:  # noqa: BLE001
        controller.log(f"Inventory remove failed: {exc}")
        return
    if not removed:
        controller.log(f"Item '{normalized}' not currently in inventory")
        return
    after = inventory.get_count(normalized)
    delta = before - after
    label = _inventory_label(normalized)
    controller.log(f"Removed {delta} x {label}")


def _inventory_parse_amount(controller: Any, text: str) -> int | None:
    parsed = parse_int(controller, text, "amount")
    if parsed is None:
        return None
    if parsed <= 0:
        controller.log("Amount must be positive")
        return None
    return parsed


def _inventory_db() -> Any:
    try:
        return load_item_database()
    except Exception:  # pragma: no cover
        return None


def _inventory_label(item_id: str, db: Any = None) -> str:
    if db is None:
        db = _inventory_db()
    if db is not None:
        definition = db.get(item_id)
        if definition is not None and definition.name:
            return str(definition.name)
    return item_id


def _inventory_unknown_item(controller: Any, item_id: str, db: Any = None) -> None:
    message = f"Unknown item '{item_id}'"
    db = db or _inventory_db()
    if db is not None:
        suggestion = db.suggest(item_id)
        if suggestion:
            message += f". Did you mean '{suggestion}'?"
    controller.log(message)
