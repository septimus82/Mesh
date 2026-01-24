"""Dialogue panel helpers for the editor."""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from arcade import Sprite


def get_entity_dialogue_config(
    scene_controller: Any,
    sprite: "Sprite",
) -> Dict[str, Any]:
    """Get a deep copy of the dialogue config for an entity."""
    entity_data = scene_controller._ensure_entity_data_dict(sprite)
    config_root = scene_controller._ensure_behaviour_config_root(entity_data)
    dialogue_cfg = config_root.get("Dialogue", {})
    if not isinstance(dialogue_cfg, dict):
        dialogue_cfg = {}
    dialogue_root = dialogue_cfg.get("dialogue", {})
    if not isinstance(dialogue_root, dict):
        dialogue_root = {}
    return copy.deepcopy(dialogue_root)


def entity_has_dialogue(sprite: Optional["Sprite"]) -> bool:
    """Check if an entity has dialogue-related behaviours."""
    if sprite is None:
        return False
    behaviours = getattr(sprite, "mesh_behaviours", []) or []
    return "Dialogue" in behaviours or "SequencePlayer" in behaviours or "MessageOnZoneEnter" in behaviours


def build_dialogue_nodes_list(
    dialogue_root: Dict[str, Any],
    cached_node_ids: List[str],
) -> List[Dict[str, Any]]:
    """Build a list of dialogue node dicts with _id attached."""
    nodes: List[Dict[str, Any]] = []
    raw_nodes = dialogue_root.get("nodes", {})
    if isinstance(raw_nodes, dict):
        for node_id in cached_node_ids:
            node = raw_nodes.get(node_id, {})
            if isinstance(node, dict):
                node_copy = dict(node)
                node_copy["_id"] = node_id
                nodes.append(node_copy)
    return nodes


def collect_dialogue_warnings(dialogue_root: Dict[str, Any]) -> List[str]:
    """Collect warnings about dialogue config issues."""
    warnings: List[str] = []
    nodes = dialogue_root.get("nodes", {})
    if not isinstance(nodes, dict):
        return warnings
    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        choices = node.get("choices") or []
        if not isinstance(choices, list):
            continue
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            next_id = choice.get("next")
            if next_id and next_id not in nodes:
                warnings.append(f"Choice '{choice.get('id', '<unnamed>')}' points to missing node '{next_id}'")
    return warnings


def next_dialogue_field(current: str, *, has_choice: bool) -> str:
    """Get the next dialogue field in cycle order."""
    fields = ["node_text"]
    if has_choice:
        fields.extend(["choice_text", "choice_next", "choice_require", "choice_forbid"])
    if current not in fields:
        return fields[0]
    idx = (fields.index(current) + 1) % len(fields)
    return fields[idx]


def prev_dialogue_field(current: str, *, has_choice: bool) -> str:
    """Get the previous dialogue field in cycle order."""
    fields = ["node_text"]
    if has_choice:
        fields.extend(["choice_text", "choice_next", "choice_require", "choice_forbid"])
    if current not in fields:
        return fields[-1]
    idx = (fields.index(current) - 1) % len(fields)
    return fields[idx]


def get_dialogue_edit_value(
    node: Dict[str, Any],
    choice: Optional[Dict[str, Any]],
    focus: str,
) -> str:
    """Get the current value for a dialogue field being edited."""
    value = ""
    if focus == "node_text":
        value = str(node.get("text", ""))
    elif choice:
        if focus == "choice_text":
            value = str(choice.get("text", ""))
        elif focus == "choice_next":
            value = str(choice.get("next", "") or "")
        elif focus == "choice_require":
            value = ", ".join(choice.get("require_flags") or [])
        elif focus == "choice_forbid":
            value = ", ".join(choice.get("forbid_flags") or [])
    return value


def apply_dialogue_edit_to_root(
    dialogue_root: Dict[str, Any],
    node_id: str,
    choice_index: int,
    focus: str,
    new_text: str,
    parse_flag_list_fn: Any,
) -> bool:
    """Apply an edit to a dialogue root dict. Returns True if successful."""
    nodes = dialogue_root.setdefault("nodes", {})
    current_node = nodes.get(node_id, {})
    if not isinstance(current_node, dict):
        current_node = {}
    nodes[node_id] = current_node
    
    if focus == "node_text":
        current_node["text"] = new_text
        return True
    
    # Choice editing
    choices = current_node.setdefault("choices", [])
    if not isinstance(choices, list):
        choices = []
        current_node["choices"] = choices
    
    if not (0 <= choice_index < len(choices)):
        return False
    
    target = choices[choice_index]
    if not isinstance(target, dict):
        target = {}
        choices[choice_index] = target
    
    if focus == "choice_text":
        target["text"] = new_text
    elif focus == "choice_next":
        target["next"] = new_text or None
    elif focus == "choice_require":
        target["require_flags"] = parse_flag_list_fn(new_text)
    elif focus == "choice_forbid":
        target["forbid_flags"] = parse_flag_list_fn(new_text)
    else:
        return False
    
    return True
