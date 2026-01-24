from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .config import EngineConfig
from .constants import EVENT_ENTERED_ZONE, EVENT_LEVEL_UP, KEY_NEXT_SPAWN_POINT
from .inventory import get_or_create_inventory, load_item_database
from .logging_tools import get_logger
from .perks import PerkManager
from .quest_manager import QuestManager
from .state_runtime import economy as state_economy
from .state_runtime import events as state_events
from .state_runtime import flags as state_flags
from .state_runtime import variables as state_variables

if TYPE_CHECKING:
    from .game import GameWindow

logger = get_logger(__name__)


@dataclass(slots=True)
class GameState:
    flags: dict[str, bool] = field(default_factory=dict)
    counters: dict[str, float] = field(default_factory=dict)
    values: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    chapter: int = 1
    main_quest_id: str | None = None
    playtime_seconds: float = 0.0
    level: int = 1
    xp: int = 0
    equipment: dict[str, Any] = field(default_factory=dict)
    perks: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Keep values and variables pointing to the same mapping for compatibility
        if not isinstance(self.values, dict):
            self.values = {}
        if not isinstance(self.variables, dict):
            self.variables = {}
        if self.values is self.variables:
            return
        if self.values and not self.variables:
            self.variables = self.values
            return
        if self.variables and not self.values:
            self.values = self.variables
            return
        merged = dict(self.values)
        merged.update(self.variables)
        self.values = merged
        self.variables = self.values
        # Normalize equipment slots
        if not isinstance(self.equipment, dict):
            self.equipment = {}
        required_slots = ("weapon", "armor", "accessory")
        for slot in required_slots:
            if slot not in self.equipment:
                self.equipment[slot] = None

    def snapshot(self) -> dict[str, Any]:
        return {
            "flags": dict(self.flags),
            "counters": dict(self.counters),
            "values": dict(self.values),
            "variables": dict(self.variables),
            "chapter": int(self.chapter),
            "main_quest_id": self.main_quest_id,
            "playtime_seconds": float(self.playtime_seconds),
            "level": int(self.level),
            "xp": int(self.xp),
            "equipment": dict(self.equipment),
            "perks": sorted(list(self.perks)),
        }

    def restore(self, data: dict[str, Any]) -> None:
        self.flags = dict(data.get("flags", {}))
        self.counters = dict(data.get("counters", {}))
        self.values = dict(data.get("values", {}))
        self.variables = dict(data.get("variables", {}))
        self.chapter = int(data.get("chapter", 1))
        self.main_quest_id = data.get("main_quest_id")
        self.playtime_seconds = float(data.get("playtime_seconds", 0.0))
        self.level = int(data.get("level", 1))
        self.xp = int(data.get("xp", 0))
        self.equipment = dict(data.get("equipment", {}))
        self.perks = list(data.get("perks", []))
        self.__post_init__()


class GameStateController:
    def __init__(self, window: GameWindow) -> None:
        self.window = window
        self.state = GameState()
        self.quests = QuestManager()
        self.perk_manager = PerkManager()
        self.perk_manager.load_perks()
        self._equipment_slots = ("weapon", "armor", "accessory")

    def _ensure_game_state(self) -> GameState:
        if not isinstance(self.state, GameState):
            self.state = GameState()
        self._normalize_equipment()
        return self.state

    def _normalize_equipment(self) -> None:
        """Ensure equipment slots exist."""
        if not isinstance(self.state.equipment, dict):
            self.state.equipment = {}
        for slot in self._equipment_slots:
            if slot not in self.state.equipment:
                self.state.equipment[slot] = None

    def add_perk(self, perk_id: str) -> bool:
        """Add a perk to the player's active perks."""
        state = self._ensure_game_state()
        if perk_id in state.perks:
            return False

        perk = self.perk_manager.get_perk(perk_id)
        if not perk:
            logger.warning("[Mesh][GameState] Warning: Adding unknown perk '%s'", perk_id)

        state.perks.append(perk_id)
        logger.info("[Mesh][GameState] Added perk: %s", perk_id)

        # Apply immediate effects if any (e.g. heal on pickup?)
        # Most effects are passive and calculated on demand.
        return True

    def has_perk(self, perk_id: str) -> bool:
        """Check if the player has a specific perk."""
        state = self._ensure_game_state()
        return perk_id in state.perks

    def get_active_perks(self) -> list[str]:
        """Get list of active perk IDs."""
        state = self._ensure_game_state()
        return list(state.perks)

    def get_perk_bonus(self, effect_name: str) -> float:
        """Calculate total bonus for a specific effect from all active perks."""
        total = 0.0
        for perk_id in self.get_active_perks():
            perk = self.perk_manager.get_perk(perk_id)
            if perk:
                total += perk.effects.get(effect_name, 0.0)
        return total

    # ------------------------------------------------------------------
    # XP / Level / Stats
    # ------------------------------------------------------------------
    def get_level(self) -> int:
        return int(self._ensure_game_state().level)

    def get_xp(self) -> int:
        return int(self._ensure_game_state().xp)

    def add_xp(self, amount: int) -> dict[str, Any]:
        state = self._ensure_game_state()
        cfg: EngineConfig = getattr(self.window, "engine_config", EngineConfig())

        # Apply perk XP bonus
        bonus_pct = 0.0
        for perk_id in state.perks:
            perk = self.perk_manager.get_perk(perk_id)
            if perk:
                bonus_pct += perk.effects.get("xp_bonus_pct", 0.0)

        xp_gain = max(0, int(amount * (1.0 + bonus_pct)))
        state.xp += xp_gain
        leveled = False
        while True:
            needed = max(1, int(cfg.xp_base + cfg.xp_per_level * (state.level - 1)))
            if state.xp < needed:
                break
            state.xp -= needed
            state.level += 1
            leveled = True
        if leveled:
            bus = getattr(self.window, "event_bus", None)
            if bus is not None:
                try:
                    bus.emit(EVENT_LEVEL_UP, level=state.level, xp=state.xp, stats=self.get_player_stats())
                except Exception as exc:  # noqa: BLE001
                    if not getattr(self, "_mesh_level_up_emit_error_logged", False):
                        logger.error("[Mesh][GameState] ERROR emitting level up event: %s", exc)
                        setattr(self, "_mesh_level_up_emit_error_logged", True)
            console_log = getattr(self.window, "console_log", None)
            if callable(console_log):
                try:
                    console_log(f"[XP] Level up! Reached level {state.level}")
                except Exception as exc:  # noqa: BLE001
                    if not getattr(self, "_mesh_level_up_console_error_logged", False):
                        logger.error("[Mesh][GameState] ERROR writing level up console log: %s", exc)
                        setattr(self, "_mesh_level_up_console_error_logged", True)
        return {"level": state.level, "xp": state.xp, "leveled": leveled}

    def set_level(self, level: int) -> None:
        state = self._ensure_game_state()
        state.level = max(1, int(level))

    def set_xp(self, xp: int) -> None:
        state = self._ensure_game_state()
        state.xp = max(0, int(xp))

    def get_player_stats(self) -> dict[str, Any]:
        cfg: EngineConfig = getattr(self.window, "engine_config", EngineConfig())
        lvl = max(1, self.get_level())
        factor = max(0, lvl - 1)
        xp = self.get_xp()
        xp_needed = max(1, int(cfg.xp_base + cfg.xp_per_level * (lvl - 1)))
        xp_to_next = max(0, xp_needed - xp)
        stats: dict[str, Any] = {
            "level": lvl,
            "xp": xp,
            "xp_to_next": xp_to_next,
            "max_hp": cfg.player_base_max_hp + cfg.player_hp_per_level * factor,
            "attack": cfg.player_base_attack + cfg.player_attack_per_level * factor,
            "defense": cfg.player_base_defense + cfg.player_defense_per_level * factor,
            "speed": cfg.player_base_speed + cfg.player_speed_per_level * factor,
        }

        # Apply perk bonuses
        state = self._ensure_game_state()
        for perk_id in state.perks:
            perk = self.perk_manager.get_perk(perk_id)
            if perk:
                stats["max_hp"] += perk.effects.get("max_hp", 0.0)
                stats["attack"] *= (1.0 + perk.effects.get("damage_pct", 0.0))
                stats["speed"] += perk.effects.get("speed", 0.0)

        bonuses = self._equipment_bonuses()
        stats["max_hp"] += bonuses.get("max_hp", 0)
        stats["attack"] += bonuses.get("attack", 0)
        stats["defense"] += bonuses.get("defense", 0)
        stats["speed"] += bonuses.get("speed", 0.0)
        stats["equipment"] = dict(self.get_equipment())
        return stats

    def get_equipment(self) -> dict[str, str | None]:
        self._normalize_equipment()
        return dict(getattr(self.state, "equipment", {}) or {})

    def equip_item(self, item_id: str, slot: str | None = None) -> dict[str, Any]:
        """Equip an item into a slot if owned and recognized."""
        result: dict[str, Any] = {"ok": False}
        state = self._ensure_game_state()
        item_id = str(item_id or "").strip()
        if not item_id:
            result["reason"] = "invalid_item"
            return result

        try:
            db = load_item_database()
        except Exception:
            result["reason"] = "item_db_unavailable"
            return result

        item_def = db.get(item_id)
        if item_def is None:
            result["reason"] = "unknown_item"
            return result

        slot_name = slot.lower() if slot else ""
        if not slot_name:
            if "weapon" in item_def.tags:
                slot_name = "weapon"
            elif "armor" in item_def.tags:
                slot_name = "armor"
            elif "accessory" in item_def.tags:
                slot_name = "accessory"
        if slot_name not in self._equipment_slots:
            result["reason"] = "invalid_slot"
            return result
        if slot_name and slot_name not in item_def.tags and "equipment" not in item_def.tags:
            result["reason"] = "not_equippable"
            return result

        inv = get_or_create_inventory(state.values)
        if not inv.has_item(item_id, 1):
            result["reason"] = "not_owned"
            return result

        self._normalize_equipment()
        previous = state.equipment.get(slot_name)
        state.equipment[slot_name] = item_id
        result.update({"ok": True, "slot": slot_name, "item": item_id, "previous": previous})
        return result

    def unequip(self, slot: str) -> dict[str, Any]:
        """Clear an equipment slot."""
        result: dict[str, Any] = {"ok": False}
        slot_name = str(slot or "").lower()
        if slot_name not in self._equipment_slots:
            result["reason"] = "invalid_slot"
            return result
        state = self._ensure_game_state()
        self._normalize_equipment()
        previous = state.equipment.get(slot_name)
        state.equipment[slot_name] = None
        result.update({"ok": True, "slot": slot_name, "previous": previous})
        return result

    def _equipment_bonuses(self) -> dict[str, float]:
        """Compute bonus stats from equipped items."""
        self._normalize_equipment()
        bonuses = {"max_hp": 0.0, "attack": 0.0, "defense": 0.0, "speed": 0.0}
        eq = getattr(self.state, "equipment", {}) or {}
        try:
            db = load_item_database()
        except Exception as exc:  # noqa: BLE001
            if not getattr(self, "_mesh_item_db_error_logged", False):
                logger.error("[Mesh][GameState] ERROR loading item database for equipment bonuses: %s", exc)
                setattr(self, "_mesh_item_db_error_logged", True)
            return bonuses

        for slot, item_id in eq.items():
            if not item_id:
                continue
            item_def = db.get(item_id)
            if item_def is None:
                continue
            effects = item_def.effects or {}
            bonuses["max_hp"] += float(effects.get("max_hp_bonus", effects.get("hp_bonus", effects.get("max_hp", 0))) or 0)
            bonuses["attack"] += float(effects.get("attack_bonus", effects.get("damage_bonus", effects.get("damage", effects.get("attack", 0)))) or 0)
            bonuses["defense"] += float(effects.get("defense_bonus", effects.get("defense", 0)) or 0)
            bonuses["speed"] += float(effects.get("speed_bonus", effects.get("speed", 0)) or 0.0)
        return bonuses

    # ------------------------------------------------------------------
    # Flags
    # ------------------------------------------------------------------
    def set_flag(self, name: str, value: bool = True) -> None:
        state = self._ensure_game_state()
        state_flags.set_flag(state, name, value)

    def get_flag(self, name: str, default: bool = False) -> bool:
        return state_flags.get_flag(getattr(self, "state", None), name, default)

    def toggle_flag(self, name: str) -> bool:
        state = self._ensure_game_state()
        return state_flags.toggle_flag(state, name)

    # ------------------------------------------------------------------
    # Counters
    # ------------------------------------------------------------------
    def set_counter(self, name: str, value: float = 0.0) -> float:
        state = self._ensure_game_state()
        return state_economy.set_counter(state, name, value)

    def inc_counter(self, name: str, amount: float = 1.0) -> float:
        return self.add_counter(name, amount)

    def add_counter(self, name: str, delta: float = 1.0) -> float:
        state = self._ensure_game_state()
        return state_economy.add_counter(state, name, delta, perk_manager=self.perk_manager)

    def get_counter(self, name: str, default: float = 0.0) -> float:
        return state_economy.get_counter(getattr(self, "state", None), name, default)

    def get_quest_counter(self, quest_id: str, name: str, default: float = 0.0) -> float:
        """Get a counter scoped to a specific quest."""
        state = self._ensure_game_state()
        # We store scoped counters in the main counters dict with a prefix
        # to avoid changing the GameState schema which expects dict[str, float].
        # Prefix format: "quest:{quest_id}:{name}"
        key = f"quest:{quest_id}:{name}"
        return state.counters.get(key, default)

    def inc_quest_counter(self, quest_id: str, name: str, amount: float = 1.0) -> float:
        """Increment a counter scoped to a specific quest."""
        state = self._ensure_game_state()
        key = f"quest:{quest_id}:{name}"
        current = state.counters.get(key, 0.0)
        new_val = current + amount
        state.counters[key] = new_val
        return new_val

    # ------------------------------------------------------------------
    # Arbitrary variables
    # ------------------------------------------------------------------
    def set_var(self, name: str, value: Any) -> None:
        state = self._ensure_game_state()
        state_variables.set_var(state, name, value)

    def get_var(self, name: str, default: Any = None) -> Any:
        return state_variables.get_var(getattr(self, "state", None), name, default)

    # ------------------------------------------------------------------
    # Spawn points
    # ------------------------------------------------------------------
    def set_next_spawn_point(self, spawn_id: str | None) -> None:
        state = self._ensure_game_state()
        key = KEY_NEXT_SPAWN_POINT
        if spawn_id is None:
            state.values.pop(key, None)
            return
        cleaned = str(spawn_id).strip()
        if cleaned:
            state.values[key] = cleaned
        else:
            state.values.pop(key, None)

    def get_next_spawn_point(self) -> str | None:
        state = self.state
        if not isinstance(state, GameState):
            return None
        value = state.values.get(KEY_NEXT_SPAWN_POINT)
        if isinstance(value, str):
            cleaned = value.strip()
            return cleaned or None
        if value is None:
            return None
        return str(value).strip() or None

    def consume_next_spawn_point(self) -> str | None:
        spawn_id = self.get_next_spawn_point()
        if not spawn_id:
            return None
        state = self._ensure_game_state()
        state.values.pop(KEY_NEXT_SPAWN_POINT, None)
        return spawn_id

    # ------------------------------------------------------------------
    # Campaign / quest state
    # ------------------------------------------------------------------
    def set_chapter(self, chapter: int) -> None:
        state = self._ensure_game_state()
        try:
            state.chapter = int(chapter)
        except (TypeError, ValueError):
            state.chapter = state.chapter

    def get_chapter(self) -> int:
        state = self._ensure_game_state()
        try:
            return int(state.chapter)
        except (TypeError, ValueError):
            return 0

    def set_main_quest(self, quest_id: str | None) -> None:
        state = self._ensure_game_state()
        state.main_quest_id = quest_id

    def get_main_quest(self) -> str | None:
        state = self._ensure_game_state()
        return state.main_quest_id

    # ------------------------------------------------------------------
    # Time tracking
    # ------------------------------------------------------------------
    def update(self, delta_time: float) -> None:
        state = self._ensure_game_state()
        try:
            dt = float(delta_time)
        except (TypeError, ValueError):
            return
        if dt <= 0.0:
            return
        state.playtime_seconds += dt
        # Auto-complete quests whose requirements now match flags/counters
        self.quests.update_quest_states(self)

    def get_playtime_seconds(self) -> float:
        state = self._ensure_game_state()
        try:
            return float(state.playtime_seconds)
        except (TypeError, ValueError):
            return 0.0

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------
    def export_state(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of game state."""
        state = self._ensure_game_state()
        payload = state.snapshot()
        payload["quests"] = self.quests.to_dict()
        return payload

    def import_state(self, data: dict[str, Any]) -> None:
        """Load game state from a JSON-friendly dict, with defaults."""
        if not isinstance(data, dict):
            return
        state = self._ensure_game_state()
        flags = data.get("flags") or {}
        counters = data.get("counters") or {}
        variables = data.get("variables") or data.get("values") or {}

        if isinstance(flags, dict):
            state.flags = {str(k): bool(v) for k, v in flags.items()}

        if isinstance(counters, dict):
            cleaned: dict[str, float] = {}
            for k, v in counters.items():
                try:
                    cleaned[str(k)] = float(v)
                except (TypeError, ValueError):
                    continue
            state.counters = cleaned

        if isinstance(variables, dict):
            state.variables = dict(variables)
            state.values = state.variables

        try:
            state.chapter = int(data.get("chapter", state.chapter))
        except (TypeError, ValueError):
            pass

        state.main_quest_id = data.get("main_quest_id", state.main_quest_id)

        try:
            state.playtime_seconds = float(
                data.get("playtime_seconds", state.playtime_seconds)
            )
        except (TypeError, ValueError):
            pass
        try:
            state.level = int(data.get("level", state.level))
        except (TypeError, ValueError):
            pass
        try:
            state.xp = int(data.get("xp", state.xp))
        except (TypeError, ValueError):
            pass
        equipment = data.get("equipment")
        if isinstance(equipment, dict):
            state.equipment = dict(equipment)
        self._normalize_equipment()

        perks = data.get("perks")
        if isinstance(perks, list):
            state.perks = list(perks)

        quests_data = data.get("quests")
        if quests_data is not None:
            self.quests.load_from_dict(quests_data)

    def replace_state(self, state_data: dict[str, Any]) -> None:
        """Completely replace the current game state with the provided data."""
        self.state = GameState()  # Reset to clean state
        self.import_state(state_data)

    def handle_event(self, event: Any) -> None:
        """Centralized event handler for game state updates."""
        # 1. Normalize event
        # If it's a dict (from trace), wrap it or use as is.
        # If it's MeshEvent, use it.
        # For simplicity, we pass it down as is, consumers should handle both or we normalize here.

        # 2. Pass to QuestManager
        # QuestManager needs access to this controller to check flags/counters
        self.quests.handle_event(event, self)

        # 2b. Persist last entered zone anchor for deterministic respawn.
        event_type = getattr(event, "type", None)
        payload = getattr(event, "payload", None)
        if event_type is None and isinstance(event, dict):
            event_type = event.get("type")
            payload = event.get("payload")
        if event_type == EVENT_ENTERED_ZONE:
            if isinstance(payload, dict):
                state_events.apply_event(self, str(event_type), dict(payload))
            elif isinstance(event, dict):
                # Some callers may inline payload at top-level.
                state_events.apply_event(self, str(event_type), {"zone": event.get("zone")})

        # 3. Future: Update global stats/counters based on event type?
        # e.g. if event.type == "died", self.inc_counter("total_kills")
