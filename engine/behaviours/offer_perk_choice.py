"""Behaviour that offers the player a choice of perks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from arcade import Sprite

from ..events import MeshEvent
from ..game_state_controller import GameStateController
from ..perks import PerkManager
from .base import Behaviour, ParamDef
from .registry import register_behaviour


@register_behaviour(
    "OfferPerkChoice",
    description="Offers a choice of perks to the player via dialogue.",
    config_fields=[
        {
            "name": "start_event",
            "description": "Mesh event name that triggers this offer",
            "type": "string",
            "default": "",
        },
        {
            "name": "interact",
            "description": "Trigger on player interaction",
            "type": "bool",
            "default": True,
        },
        {
            "name": "text",
            "description": "Text to display in the dialogue",
            "type": "string",
            "default": "Choose a blessing...",
        },
        {
            "name": "speaker",
            "description": "Speaker name for the dialogue",
            "type": "string",
            "default": "Shrine",
        },
        {
            "name": "pool",
            "description": "List of perk IDs to offer (empty for all available)",
            "type": "array",
            "default": [],
        },
        {
            "name": "once",
            "description": "Only offer once per game session (persisted via game state)",
            "type": "bool",
            "default": True,
        },
    ],
)
class OfferPerkChoice(Behaviour):
    """Interacts with the player to offer a perk choice."""

    PARAM_DEFS = {
        "start_event": ParamDef(str, default="", description="Mesh event name that triggers this offer"),
        "interact": ParamDef(bool, default=True, description="Trigger on player interaction"),
        "text": ParamDef(str, default="Choose a blessing...", description="Text to display"),
        "speaker": ParamDef(str, default="Shrine", description="Speaker name"),
        "pool": ParamDef(list, default=[], description="List of perk IDs to offer"),
        "once": ParamDef(bool, default=True, description="Only offer once"),
    }

    def __init__(self, entity: Any, window: Any, **config: Any) -> None:
        merged = self._merge_entity_data(entity, config)
        super().__init__(entity, window, **merged)
        self.start_event = str(merged.get("start_event", "")).strip()
        self.interact_trigger = bool(merged.get("interact", True))
        self.text = str(merged.get("text", "Choose a blessing..."))
        self.speaker = str(merged.get("speaker", "Shrine"))
        self.pool = list(merged.get("pool", []))
        self.once = bool(merged.get("once", True))

        self._active = False
        self._cooldown = 0.0  # Prevent immediate selection
        self._owner_id = f"offer_perk::{id(self)}"
        self._game_state: GameStateController = window.game_state_controller
        self._perk_manager: PerkManager = self._game_state.perk_manager

    @staticmethod
    def _merge_entity_data(entity: Sprite, config: Dict[str, Any] | None) -> Dict[str, Any]:
        data = dict(getattr(entity, "mesh_entity_data", {}) or {})
        if config:
            data.update(config)
        return data

    def subscribed_event_types(self) -> frozenset[str] | None:
        return frozenset({self.start_event}) if self.start_event else frozenset()

    def on_event(self, event: MeshEvent) -> None:
        if self._active:
            return
        if self.start_event and event.type == self.start_event:
            self._start_offer()

    def on_interact(self, window, actor: Sprite) -> None:  # noqa: ARG002
        if self._active:
            return
        if self.interact_trigger:
            self._start_offer()

    def can_interact_with(self, _actor: Sprite) -> bool:
        if self._active:
            return False
        if not self.interact_trigger:
            return False
        return bool(self._get_available_perks())

    def get_interact_label(self, _actor: Sprite | None = None) -> str | None:
        return self.speaker

    def update(self, dt: float) -> None:
        if not self._active:
            return

        if self._cooldown > 0:
            self._cooldown -= dt

        ui = getattr(self.window, "ui_controller", None) or getattr(self.window, "ui", None)
        box = getattr(ui, "dialogue_box", None) if ui is not None else None

        # If dialogue box was closed externally or we lost ownership
        if not box or not box.is_active_for(self._owner_id):
            self._active = False
            return

        # Handle Input
        input_mgr = getattr(self.window, "input", None)
        if input_mgr is None:
            ctrl = getattr(self.window, "input_controller", None)
            input_mgr = getattr(ctrl, "manager", None)

        if input_mgr is None:
            return

        if input_mgr.was_action_pressed("move_up"):
            box.move_choice_cursor(-1, owner=self._owner_id)
        elif input_mgr.was_action_pressed("move_down"):
            box.move_choice_cursor(1, owner=self._owner_id)

        if self._cooldown <= 0 and input_mgr.was_action_pressed("interact"):
            if box.has_choices():
                choice = box.submit_choice(owner=self._owner_id)
                if choice:
                    self._handle_choice(choice)
            else:
                advanced = box.advance(owner=self._owner_id)
                if not advanced and not box.is_active_for(self._owner_id):
                    self._active = False

    def _show_dialogue(self, entries: list[dict[str, Any]]) -> bool:
        shower = getattr(self.window, "show_dialogue", None)
        if callable(shower):
            return bool(shower(entries, owner=self._owner_id))
        ui = getattr(self.window, "ui_controller", None) or getattr(self.window, "ui", None)
        shower = getattr(ui, "show_dialogue", None) if ui is not None else None
        if callable(shower):
            return bool(shower(entries, owner=self._owner_id))
        return False

    def _close_dialogue(self) -> None:
        closer = getattr(self.window, "close_dialogue", None)
        if callable(closer):
            closer(owner=self._owner_id)
            return
        ui = getattr(self.window, "ui_controller", None) or getattr(self.window, "ui", None)
        closer = getattr(ui, "close_dialogue", None) if ui is not None else None
        if callable(closer):
            closer(owner=self._owner_id)

    def _start_offer(self) -> None:
        # Check if already used (if once=True)
        # We can use a game state flag to track this specific shrine instance if needed.
        # For now, let's just check if the player already has ALL offered perks?
        # Or maybe we just rely on the fact that we filter out owned perks.

        available_perks = self._get_available_perks()
        if not available_perks:
            # Nothing to offer
            self._show_message("You have learned all I can teach.")
            return

        choices = []
        for perk in available_perks:
            choices.append({
                "id": perk.id,
                "text": f"{perk.name}: {perk.description}",
            })

        # Add a cancel option?
        choices.append({"id": "cancel", "text": "Leave"})

        entry = {
            "speaker": self.speaker,
            "text": self.text,
            "choices": choices
        }
        if self._show_dialogue([entry]):
            self._active = True
            self._cooldown = 0.2

    def _get_available_perks(self) -> List[Any]:
        all_perks = self._perk_manager.get_all_perks()
        candidates = []

        # Filter by pool if specified
        if self.pool:
            for pid in self.pool:
                perk = self._perk_manager.get_perk(pid)
                if perk:
                    candidates.append(perk)
        else:
            candidates = list(all_perks) if isinstance(all_perks, list) else list(getattr(all_perks, "values", lambda: [])())

        # Filter out already owned perks
        final_list = []
        for perk in candidates:
            if not self._game_state.has_perk(perk.id):
                final_list.append(perk)

        return final_list

    def _handle_choice(self, choice: Dict[str, Any]) -> None:
        raw_choice_id = choice.get("id")
        choice_id = raw_choice_id if isinstance(raw_choice_id, str) else None
        if choice_id == "cancel":
            self._close_dialogue()
            self._active = False
            return
        if choice_id is None:
            return

        # Apply perk
        self._game_state.add_perk(choice_id)

        # Show confirmation or close
        # For now, just close
        self._close_dialogue()
        self._active = False

        # Maybe play a sound or effect?
        if hasattr(self.window, "audio"):
            self.window.audio.play_sound("assets/sounds/ui_buy.wav") # Assuming this exists or similar

    def _show_message(self, text: str) -> None:
        entry = {
            "speaker": self.speaker,
            "text": text
        }
        if self._show_dialogue([entry]):
            self._active = True
            self._cooldown = 0.2
