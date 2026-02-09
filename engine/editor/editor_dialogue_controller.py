from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, cast

import engine.optional_arcade as optional_arcade

from engine.editor.dialogue_panel import (
    apply_dialogue_edit_to_root as _apply_dialogue_edit_to_root_impl,
    build_dialogue_nodes_list as _build_dialogue_nodes_list_impl,
    collect_dialogue_warnings as _collect_dialogue_warnings_impl,
    entity_has_dialogue as _entity_has_dialogue_impl,
    get_dialogue_edit_value as _get_dialogue_edit_value_impl,
    get_entity_dialogue_config as _get_entity_dialogue_config_impl,
    next_dialogue_field as _next_dialogue_field_impl,
    prev_dialogue_field as _prev_dialogue_field_impl,
)
from engine.logging_tools import get_logger
from engine.ui_overlays.common import draw_panel_bg
from engine.behaviours.utils import parse_flag_list

logger = get_logger(__name__)


class EditorDialogueController:
    """Encapsulates dialogue panel orchestration and edits."""

    def __init__(self, editor: Any) -> None:
        self._editor = editor

    def toggle_dialogue_panel(self) -> None:
        if not self.entity_has_dialogue(self._editor.selected_entity):
            logger.info("[Editor] Dialogue panel unavailable: select an entity with Dialogue")
            return
        self._editor.dialogue_panel_active = not self._editor.dialogue_panel_active
        self._editor.dialogue_editing = False
        self._editor.dialogue_edit_buffer = ""
        if self._editor.dialogue_panel_active:
            inspector = getattr(self._editor, "inspector", None)
            if inspector is not None:
                inspector.set_inspector_active(False)
            self._editor.palette_active = False
            self._editor.palette_filter_active = False
            self._editor.hierarchy_active = False
            self.refresh_dialogue_cache()
            logger.info("[Editor] Dialogue panel OPEN")
        else:
            self.close_dialogue_panel()

    def close_dialogue_panel(self) -> None:
        self._editor.dialogue_panel_active = False
        self._editor.dialogue_editing = False
        self._editor.dialogue_edit_buffer = ""
        self._editor._cached_dialogue_nodes = []
        self._editor._dialogue_warnings = []
        self._editor.animation_active = False
        self._editor.animation_editing = False
        self._editor.animation_edit_buffer = ""
        self._editor._set_tile_panel_active(False)

    def entity_has_dialogue(self, sprite: Optional[optional_arcade.arcade.Sprite]) -> bool:
        return _entity_has_dialogue_impl(sprite)

    def refresh_dialogue_cache(self) -> None:
        self._editor._cached_dialogue_nodes = []
        self._editor._dialogue_warnings = []
        self._editor.dialogue_selected_node = 0
        self._editor.dialogue_selected_choice = 0
        if not self._editor.selected_entity:
            return
        dialogue_root = self.get_entity_dialogue_config(self._editor.selected_entity)
        nodes = dialogue_root.get("nodes", {})
        if isinstance(nodes, dict):
            self._editor._cached_dialogue_nodes = sorted(nodes.keys())
        start_node = dialogue_root.get("start")
        if start_node in self._editor._cached_dialogue_nodes:
            self._editor.dialogue_selected_node = self._editor._cached_dialogue_nodes.index(start_node)
        self._editor._dialogue_warnings = self.collect_dialogue_warnings(dialogue_root)

    def get_entity_dialogue_config(self, sprite: optional_arcade.arcade.Sprite) -> Dict[str, Any]:
        return _get_entity_dialogue_config_impl(self._editor.window.scene_controller, sprite)

    def set_entity_dialogue_config(self, sprite: optional_arcade.arcade.Sprite, dialogue_root: Dict[str, Any]) -> None:
        entity_name = getattr(sprite, "mesh_name", "")
        self._editor._update_param_internal("Dialogue", "dialogue", dialogue_root, entity_name)

    def dialogue_nodes(self) -> List[Dict[str, Any]]:
        nodes: List[Dict[str, Any]] = []
        if not self._editor.selected_entity:
            return nodes
        dialogue_root = self.get_entity_dialogue_config(self._editor.selected_entity)
        raw_nodes = dialogue_root.get("nodes", {})
        if isinstance(raw_nodes, dict):
            for node_id in self._editor._cached_dialogue_nodes:
                node = raw_nodes.get(node_id, {})
                if isinstance(node, dict):
                    node_copy = dict(node)
                    node_copy["_id"] = node_id
                    nodes.append(node_copy)
        return nodes

    def get_selected_node(self) -> Optional[Dict[str, Any]]:
        nodes = self.dialogue_nodes()
        if not nodes:
            return None
        self._editor.dialogue_selected_node = max(
            0, min(self._editor.dialogue_selected_node, len(nodes) - 1)
        )
        return cast(Dict[str, Any], nodes[self._editor.dialogue_selected_node])

    def get_selected_choice(self, node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        choices = node.get("choices") or []
        if not isinstance(choices, list) or not choices:
            return None
        self._editor.dialogue_selected_choice = max(
            0, min(self._editor.dialogue_selected_choice, len(choices) - 1)
        )
        choice = choices[self._editor.dialogue_selected_choice]
        return choice if isinstance(choice, dict) else None

    def handle_dialogue_input(self, key: int, modifiers: int) -> bool:
        if not self._editor.dialogue_panel_active:
            return False

        if self._editor.dialogue_editing:
            if key == optional_arcade.arcade.key.ENTER:
                self.commit_dialogue_edit()
                return True
            if key == optional_arcade.arcade.key.ESCAPE:
                self._editor.dialogue_editing = False
                self._editor.dialogue_edit_buffer = ""
                return True
            if key == optional_arcade.arcade.key.BACKSPACE:
                self._editor.dialogue_edit_buffer = self._editor.dialogue_edit_buffer[:-1]
                return True
            return False

        if key == optional_arcade.arcade.key.ESCAPE:
            self.close_dialogue_panel()
            return True

        nodes = self.dialogue_nodes()
        if not nodes:
            return False
        node = self.get_selected_node()
        choice = node and self.get_selected_choice(node)

        if key == optional_arcade.arcade.key.UP:
            if modifiers & optional_arcade.arcade.key.MOD_SHIFT and choice:
                self._editor.dialogue_selected_choice = max(0, self._editor.dialogue_selected_choice - 1)
            else:
                self._editor.dialogue_selected_node = max(0, self._editor.dialogue_selected_node - 1)
                self._editor.dialogue_selected_choice = 0
            return True
        if key == optional_arcade.arcade.key.DOWN:
            if modifiers & optional_arcade.arcade.key.MOD_SHIFT and choice:
                choices = node.get("choices") if node else []
                count = len(choices) if isinstance(choices, list) else 0
                if count:
                    self._editor.dialogue_selected_choice = min(
                        count - 1, self._editor.dialogue_selected_choice + 1
                    )
            else:
                self._editor.dialogue_selected_node = min(len(nodes) - 1, self._editor.dialogue_selected_node + 1)
                self._editor.dialogue_selected_choice = 0
            return True
        if key == optional_arcade.arcade.key.RIGHT and choice:
            self._editor.dialogue_field_focus = self.next_dialogue_field(
                self._editor.dialogue_field_focus, has_choice=True
            )
            return True
        if key == optional_arcade.arcade.key.LEFT:
            self._editor.dialogue_field_focus = self.prev_dialogue_field(
                self._editor.dialogue_field_focus, has_choice=bool(choice)
            )
            return True
        if key in (optional_arcade.arcade.key.TAB,):
            self._editor.dialogue_field_focus = self.next_dialogue_field(
                self._editor.dialogue_field_focus, has_choice=bool(choice)
            )
            return True
        if key == optional_arcade.arcade.key.ENTER:
            self.begin_dialogue_edit()
            return True
        return False

    def next_dialogue_field(self, current: str, *, has_choice: bool) -> str:
        return _next_dialogue_field_impl(current, has_choice=has_choice)

    def prev_dialogue_field(self, current: str, *, has_choice: bool) -> str:
        return _prev_dialogue_field_impl(current, has_choice=has_choice)

    def begin_dialogue_edit(self) -> None:
        node = self.get_selected_node()
        if not node:
            return
        choice = self.get_selected_choice(node)
        focus = self._editor.dialogue_field_focus
        value = _get_dialogue_edit_value_impl(node, choice, focus)
        self._editor.dialogue_edit_buffer = value
        self._editor.dialogue_editing = True

    def commit_dialogue_edit(self) -> None:
        node = self.get_selected_node()
        if not node or not self._editor.selected_entity:
            self._editor.dialogue_editing = False
            self._editor.dialogue_edit_buffer = ""
            return
        choice = self.get_selected_choice(node)
        focus = self._editor.dialogue_field_focus
        new_text = self._editor.dialogue_edit_buffer
        success = self.apply_dialogue_edit(node, choice, focus, new_text)
        if success:
            self.refresh_dialogue_cache()
        self._editor.dialogue_editing = False
        self._editor.dialogue_edit_buffer = ""

    def apply_dialogue_edit(
        self,
        node: Dict[str, Any],
        choice: Optional[Dict[str, Any]],
        focus: str,
        new_text: str,
    ) -> bool:
        if not self._editor.selected_entity:
            return False
        before = self.get_entity_dialogue_config(self._editor.selected_entity)
        dialogue_root = copy.deepcopy(before)
        nodes = dialogue_root.setdefault("nodes", {})
        node_id = node.get("_id")
        if not node_id:
            return False
        current_node = nodes.get(node_id, {})
        if not isinstance(current_node, dict):
            current_node = {}
        nodes[node_id] = current_node
        if focus == "node_text":
            current_node["text"] = new_text
        else:
            choices = current_node.setdefault("choices", [])
            if not isinstance(choices, list):
                choices = []
                current_node["choices"] = choices
            if choice is None:
                return False
            if 0 <= self._editor.dialogue_selected_choice < len(choices):
                target = choices[self._editor.dialogue_selected_choice]
                if not isinstance(target, dict):
                    target = {}
                    choices[self._editor.dialogue_selected_choice] = target
            else:
                return False
            if focus == "choice_text":
                target["text"] = new_text
            elif focus == "choice_next":
                target["next"] = new_text or None
            elif focus == "choice_require":
                target["require_flags"] = parse_flag_list(new_text)
            elif focus == "choice_forbid":
                target["forbid_flags"] = parse_flag_list(new_text)
            else:
                return False
        self.set_entity_dialogue_config(self._editor.selected_entity, dialogue_root)
        self._editor._push_command({
            "type": "EditDialogue",
            "entity_name": getattr(self._editor.selected_entity, "mesh_name", ""),
            "before": before,
            "after": dialogue_root,
        })
        return True

    def collect_dialogue_warnings(self, dialogue_root: Dict[str, Any]) -> List[str]:
        return _collect_dialogue_warnings_impl(dialogue_root)

    def draw_dialogue_panel(self) -> None:
        lines: List[str] = ["DIALOGUE (D)", "--------------"]
        if self._editor.dialogue_editing:
            lines.append("Editing: type to change, ENTER to save, ESC to cancel")
        nodes = self.dialogue_nodes()
        if not nodes:
            lines.append("No dialogue nodes found on this entity.")
        else:
            for idx, node in enumerate(nodes):
                prefix = "> " if idx == self._editor.dialogue_selected_node else "  "
                node_id = node.get("_id", f"node_{idx}")
                text = str(node.get("text", ""))[:80]
                lines.append(f"{prefix}{node_id}: {text}")
                choices = node.get("choices") or []
                if isinstance(choices, list):
                    for c_idx, choice in enumerate(choices):
                        marker = "    *" if (
                            idx == self._editor.dialogue_selected_node
                            and c_idx == self._editor.dialogue_selected_choice
                        ) else "     "
                        if not isinstance(choice, dict):
                            continue
                        label = choice.get("text", "<empty>")
                        nxt = choice.get("next") or "<end>"
                        lines.append(f"{marker} [{choice.get('id','?')}] {label} -> {nxt}")
        if self._editor._dialogue_warnings:
            lines.append("Warnings:")
            for warn in self._editor._dialogue_warnings[:4]:
                lines.append(f"  - {warn}")

        start_x = 320
        start_y = self._editor.window.height - 80
        panel_width = 520
        draw_panel_bg(
            start_x - 10,
            start_x + panel_width,
            start_y - len(lines) * 18 - 12,
            start_y + 20,
        )
        for i, line in enumerate(lines):
            color = (
                optional_arcade.arcade.color.CYAN
                if line.startswith(">") or "Editing" in line
                else optional_arcade.arcade.color.WHITE
            )
            optional_arcade.arcade.draw_text(
                line,
                start_x,
                start_y - i * 18,
                color,
                12,
                font_name="Consolas",
            )

    def draw_quest_context_panel(self) -> None:
        related = self._related_quest_ids(self._editor.selected_entity) if self._editor.selected_entity else set()
        quests = self._quest_definitions()
        lines: List[str] = ["QUEST CONTEXT", "--------------"]
        if not quests:
            lines.append("No quests loaded.")
        else:
            for quest_id, quest in quests.items():
                prefix = "*" if quest_id in related else "-"
                stage_count = len(quest.get("stages") or [])
                lines.append(f"{prefix} {quest_id} ({stage_count} stages)")
                if quest_id in related:
                    title = quest.get("name") or quest.get("title") or ""
                    if title:
                        lines.append(f"    {title}")
        start_x = self._editor.window.width - 320
        start_y = self._editor.window.height - 80
        panel_width = 300
        draw_panel_bg(
            start_x - 10,
            start_x + panel_width,
            start_y - len(lines) * 18 - 12,
            start_y + 20,
        )
        for i, line in enumerate(lines):
            color = optional_arcade.arcade.color.YELLOW if line.startswith("*") else optional_arcade.arcade.color.WHITE
            optional_arcade.arcade.draw_text(
                line,
                start_x,
                start_y - i * 18,
                color,
                12,
                font_name="Consolas",
            )

    def _quest_definitions(self) -> Dict[str, Dict[str, Any]]:
        quests: Dict[str, Dict[str, Any]] = {}
        manager = getattr(self._editor.window, "quest_manager", None)
        definitions = getattr(manager, "_definitions", None)
        if isinstance(definitions, dict):
            quests.update(definitions)
        return quests

    def _related_quest_ids(self, sprite: Optional[optional_arcade.arcade.Sprite]) -> set[str]:
        related: set[str] = set()
        if sprite is None:
            return related
        scene_controller = self._editor.window.scene_controller
        entity_data = scene_controller._ensure_entity_data_dict(sprite)
        config_root = scene_controller._ensure_behaviour_config_root(entity_data)
        for behaviour_cfg in config_root.values():
            if not isinstance(behaviour_cfg, dict):
                continue
            quest_id = behaviour_cfg.get("quest_id")
            if isinstance(quest_id, str) and quest_id.strip():
                related.add(quest_id.strip())
        quest_defs = self._quest_definitions()
        for behaviour_cfg in config_root.values():
            if not isinstance(behaviour_cfg, dict):
                continue
            for key in ("require_flags", "set_flags", "clear_flags"):
                flags = behaviour_cfg.get(key)
                if isinstance(flags, dict):
                    for flag in flags.keys():
                        if flag in quest_defs:
                            related.add(flag)
                elif isinstance(flags, list):
                    for flag in flags:
                        if isinstance(flag, str) and flag in quest_defs:
                            related.add(flag)
        return related
