from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine import json_io


EVENTS_REL_PATH = Path("assets/data/events.json")
QUESTS_REL_PATH = Path("assets/data/quests.json")
CUTSCENES_REL_PATH = Path("cutscenes.json")
DIALOGUES_REL_PATH = Path("assets/data/dialogues.json")
PREFABS_REL_PATH = Path("assets/prefabs.json")


@dataclass(frozen=True, slots=True)
class EpisodeScaffoldPlan:
    out_dir: Path
    episode_id: str
    episode_number: int
    episode_number_padded: str
    title: str
    seed: int

    scene_stem: str
    scene_rel_path: Path
    doc_rel_path: Path
    test_rel_path: Path

    events_rel_path: Path
    quests_rel_path: Path
    cutscenes_rel_path: Path
    dialogues_rel_path: Path
    prefabs_rel_path: Path

    quest_id: str
    dialogue_id: str
    cutscene_intro_id: str
    cutscene_outro_id: str

    prefab_mentor_id: str
    prefab_trigger_id: str
    prefab_door_id: str
    prefab_reward_id: str
    prefab_controller_id: str

    event_entered: str
    event_intro_start: str
    event_intro_done: str
    event_choice_made: str
    event_clue_found: str
    event_exit_unlocked: str
    event_exit_door_interact: str
    event_outro_start: str
    event_complete: str
    event_quest_complete: str

    flag_entered: str
    flag_choice_help: str
    flag_choice_solo: str
    flag_exit_unlocked: str
    flag_complete: str

    reward_flag_complete: str

    @property
    def scene_display_name(self) -> str:
        return f"Episode {self.episode_number_padded}: {self.title}"

    @property
    def runtime_prefix(self) -> str:
        return f"episode_{self.episode_number_padded}_{self.episode_id}"

    @property
    def episode_tag(self) -> str:
        return f"episode_{self.episode_number_padded}"

    @property
    def event_names(self) -> tuple[str, ...]:
        return (
            self.event_entered,
            self.event_intro_start,
            self.event_intro_done,
            self.event_choice_made,
            self.event_clue_found,
            self.event_exit_unlocked,
            self.event_exit_door_interact,
            self.event_outro_start,
            self.event_complete,
            self.event_quest_complete,
        )

    @property
    def prefab_ids(self) -> tuple[str, ...]:
        return (
            self.prefab_mentor_id,
            self.prefab_trigger_id,
            self.prefab_door_id,
            self.prefab_reward_id,
            self.prefab_controller_id,
        )


def build_episode_scaffold_plan(
    *,
    episode_id: str,
    title: str,
    out_dir: str | Path,
    seed: int = 123,
) -> EpisodeScaffoldPlan:
    normalized_id = str(episode_id or "").strip().lower()
    if not normalized_id:
        raise ValueError("episode id is required")
    if not re.fullmatch(r"[a-z][a-z0-9_]*", normalized_id):
        raise ValueError("episode id must be snake-like (letters, digits, underscores) and start with a letter")

    number_match = re.search(r"(\d+)", normalized_id)
    if number_match is None:
        raise ValueError("episode id must contain a numeric chapter hint (example: ep02)")
    episode_number = int(number_match.group(1))
    episode_number_padded = f"{episode_number:02d}"

    normalized_title = str(title or "").strip()
    if not normalized_title:
        raise ValueError("title is required")

    resolved_out_dir = Path(out_dir).resolve()
    scene_stem = f"episode_{episode_number_padded}_{normalized_id}"

    quest_id = scene_stem
    event_prefix = normalized_id
    dialogue_id = f"{event_prefix}_dialogue_intro"
    cutscene_intro_id = f"{event_prefix}_intro"
    cutscene_outro_id = f"{event_prefix}_outro"

    return EpisodeScaffoldPlan(
        out_dir=resolved_out_dir,
        episode_id=normalized_id,
        episode_number=episode_number,
        episode_number_padded=episode_number_padded,
        title=normalized_title,
        seed=int(seed),
        scene_stem=scene_stem,
        scene_rel_path=Path("scenes") / f"{scene_stem}.json",
        doc_rel_path=Path("docs") / f"{scene_stem}.md",
        test_rel_path=Path("tests") / f"test_{scene_stem}_integration.py",
        events_rel_path=EVENTS_REL_PATH,
        quests_rel_path=QUESTS_REL_PATH,
        cutscenes_rel_path=CUTSCENES_REL_PATH,
        dialogues_rel_path=DIALOGUES_REL_PATH,
        prefabs_rel_path=PREFABS_REL_PATH,
        quest_id=quest_id,
        dialogue_id=dialogue_id,
        cutscene_intro_id=cutscene_intro_id,
        cutscene_outro_id=cutscene_outro_id,
        prefab_mentor_id=f"{event_prefix}_mentor",
        prefab_trigger_id=f"{event_prefix}_trigger",
        prefab_door_id=f"{event_prefix}_door",
        prefab_reward_id=f"{event_prefix}_reward",
        prefab_controller_id=f"{event_prefix}_controller",
        event_entered=f"{event_prefix}_entered",
        event_intro_start=f"{event_prefix}_intro_start",
        event_intro_done=f"{event_prefix}_intro_cutscene_done",
        event_choice_made=f"{event_prefix}_choice_made",
        event_clue_found=f"{event_prefix}_clue_found",
        event_exit_unlocked=f"{event_prefix}_exit_unlocked",
        event_exit_door_interact=f"{event_prefix}_exit_door_interact",
        event_outro_start=f"{event_prefix}_outro_start",
        event_complete=f"{event_prefix}_complete",
        event_quest_complete=f"quest_{quest_id}_complete",
        flag_entered=f"{event_prefix}.entered",
        flag_choice_help=f"{event_prefix}.choice_help",
        flag_choice_solo=f"{event_prefix}.choice_solo",
        flag_exit_unlocked=f"{event_prefix}.exit_unlocked",
        flag_complete=f"{event_prefix}.complete",
        reward_flag_complete=f"{quest_id}_complete",
    )


def apply_episode_scaffold(plan: EpisodeScaffoldPlan, *, dry_run: bool) -> list[tuple[str, str]]:
    _ensure_file_absent(plan.out_dir / plan.scene_rel_path)
    _ensure_file_absent(plan.out_dir / plan.doc_rel_path)
    _ensure_file_absent(plan.out_dir / plan.test_rel_path)

    events_root = _read_json_object(plan.out_dir / plan.events_rel_path)
    quests_root = _read_json_object(plan.out_dir / plan.quests_rel_path)
    cutscenes_root = _read_json_object(plan.out_dir / plan.cutscenes_rel_path)
    prefabs_root = _read_json_list(plan.out_dir / plan.prefabs_rel_path)
    dialogues_root = _read_dialogues_root(plan.out_dir / plan.dialogues_rel_path)

    events_list = _read_object_list(events_root, "events", plan.events_rel_path)
    quests_list = _read_object_list(quests_root, "quests", plan.quests_rel_path)
    cutscenes_list = _read_object_list(cutscenes_root, "cutscenes", plan.cutscenes_rel_path)
    dialogues_list = _read_object_list(dialogues_root, "dialogues", plan.dialogues_rel_path)

    _assert_unique_key(events_list, key="name", label=plan.events_rel_path.as_posix())
    _assert_unique_key(quests_list, key="id", label=plan.quests_rel_path.as_posix())
    _assert_unique_key(cutscenes_list, key="id", label=plan.cutscenes_rel_path.as_posix())
    _assert_unique_key(prefabs_root, key="id", label=plan.prefabs_rel_path.as_posix())
    _assert_unique_key(dialogues_list, key="id", label=plan.dialogues_rel_path.as_posix())

    new_events = _build_event_entries(plan)
    new_quest = _build_quest_entry(plan)
    new_cutscenes = _build_cutscene_entries(plan)
    new_dialogue = _build_dialogue_entry(plan)
    new_prefabs = _build_prefab_entries(plan)
    new_scene = _build_scene_payload(plan)
    new_doc = _build_doc_text(plan)
    new_test = _build_test_text(plan)

    _assert_absent(events_list, new_events, key="name", label=plan.events_rel_path.as_posix())
    _assert_absent(quests_list, [new_quest], key="id", label=plan.quests_rel_path.as_posix())
    _assert_absent(cutscenes_list, new_cutscenes, key="id", label=plan.cutscenes_rel_path.as_posix())
    _assert_absent(dialogues_list, [new_dialogue], key="id", label=plan.dialogues_rel_path.as_posix())
    _assert_absent(prefabs_root, new_prefabs, key="id", label=plan.prefabs_rel_path.as_posix())

    events_list.extend(new_events)
    quests_list.append(new_quest)
    cutscenes_list.extend(new_cutscenes)
    dialogues_list.append(new_dialogue)
    prefabs_root.extend(new_prefabs)

    events_root["events"] = events_list
    quests_root["quests"] = quests_list
    cutscenes_root["cutscenes"] = cutscenes_list
    dialogues_root["dialogues"] = dialogues_list

    actions: list[tuple[str, str]] = []
    _record_action(actions, plan, plan.events_rel_path, f"append {len(new_events)} events")
    _record_action(actions, plan, plan.quests_rel_path, "append 1 quest")
    _record_action(actions, plan, plan.cutscenes_rel_path, "append 2 cutscenes")
    _record_action(actions, plan, plan.dialogues_rel_path, "append 1 dialogue script")
    _record_action(actions, plan, plan.prefabs_rel_path, f"append {len(new_prefabs)} prefabs")
    _record_action(actions, plan, plan.scene_rel_path, "create scene")
    _record_action(actions, plan, plan.doc_rel_path, "create episode docs")
    _record_action(actions, plan, plan.test_rel_path, "create integration test")

    if dry_run:
        return actions

    json_io.write_json_atomic(plan.out_dir / plan.events_rel_path, events_root)
    json_io.write_json_atomic(plan.out_dir / plan.quests_rel_path, quests_root)
    json_io.write_json_atomic(plan.out_dir / plan.cutscenes_rel_path, cutscenes_root)
    json_io.write_json_atomic(plan.out_dir / plan.dialogues_rel_path, dialogues_root)
    json_io.write_json_atomic(plan.out_dir / plan.prefabs_rel_path, prefabs_root)
    json_io.write_json_atomic(plan.out_dir / plan.scene_rel_path, new_scene)
    json_io.write_text_atomic(plan.out_dir / plan.doc_rel_path, new_doc, encoding="utf-8")
    json_io.write_text_atomic(plan.out_dir / plan.test_rel_path, new_test, encoding="utf-8")

    return actions


def _ensure_file_absent(path: Path) -> None:
    if path.exists():
        raise ValueError(f"refusing to overwrite existing file: {path.as_posix()}")


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    if not isinstance(payload, dict):
        raise ValueError(f"{path.as_posix()} must be a JSON object")
    return payload


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    if not isinstance(payload, list):
        raise ValueError(f"{path.as_posix()} must be a JSON array")
    out: list[dict[str, Any]] = []
    for index, entry in enumerate(payload):
        if not isinstance(entry, dict):
            raise ValueError(f"{path.as_posix()}[{index}] must be an object")
        out.append(entry)
    return out


def _read_dialogues_root(path: Path) -> dict[str, Any]:
    if path.exists():
        root = _read_json_object(path)
        if "dialogues" not in root:
            root["dialogues"] = []
        return root
    return {"dialogues": []}


def _read_json(path: Path) -> Any:
    if not path.exists():
        raise ValueError(f"required file not found: {path.as_posix()}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"failed to parse JSON at {path.as_posix()}: {exc}") from exc


def _read_object_list(root: dict[str, Any], key: str, source_path: Path) -> list[dict[str, Any]]:
    data = root.get(key)
    if data is None:
        data = []
    if not isinstance(data, list):
        raise ValueError(f"{source_path.as_posix()} key '{key}' must be an array")
    out: list[dict[str, Any]] = []
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            raise ValueError(f"{source_path.as_posix()} key '{key}' index {index} must be an object")
        out.append(entry)
    return out


def _assert_unique_key(entries: list[dict[str, Any]], *, key: str, label: str) -> None:
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        raw_value = entry.get(key)
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError(f"{label} entry {index} missing non-empty '{key}'")
        value = raw_value.strip()
        if value in seen:
            raise ValueError(f"{label} contains duplicate {key} '{value}'")
        seen.add(value)


def _assert_absent(
    existing_entries: list[dict[str, Any]],
    new_entries: list[dict[str, Any]],
    *,
    key: str,
    label: str,
) -> None:
    existing_values = {str(entry.get(key, "")).strip() for entry in existing_entries}
    for entry in new_entries:
        value = str(entry.get(key, "")).strip()
        if not value:
            raise ValueError(f"internal scaffold error: missing '{key}' in new entry for {label}")
        if value in existing_values:
            raise ValueError(f"{label} already defines {key} '{value}'")
        existing_values.add(value)


def _record_action(actions: list[tuple[str, str]], plan: EpisodeScaffoldPlan, rel_path: Path, summary: str) -> None:
    _ = plan
    actions.append((rel_path.as_posix(), summary))


def _build_event_entries(plan: EpisodeScaffoldPlan) -> list[dict[str, Any]]:
    chapter = f"Episode {plan.episode_number_padded}"
    return [
        {
            "name": plan.event_entered,
            "description": f"Fired when the player enters the {chapter} scene.",
            "payload": {"zone": "string", "entity": "string"},
        },
        {
            "name": plan.event_intro_start,
            "description": f"Requests the {chapter} intro cutscene to start.",
            "payload": {},
        },
        {
            "name": plan.event_intro_done,
            "description": f"Fired when the {chapter} intro cutscene reaches dialogue handoff.",
            "payload": {},
        },
        {
            "name": plan.event_choice_made,
            "description": f"Fired when the player chooses a dialogue branch in {chapter}.",
            "payload": {"choice": "string"},
        },
        {
            "name": plan.event_clue_found,
            "description": f"Fired when the objective interactable is used in {chapter}.",
            "payload": {"target": "string", "interactor": "string"},
        },
        {
            "name": plan.event_exit_unlocked,
            "description": f"Fired when the {chapter} exit is unlocked.",
            "payload": {},
        },
        {
            "name": plan.event_exit_door_interact,
            "description": f"Fired when the {chapter} exit door is interacted with.",
            "payload": {"target": "string", "interactor": "string"},
        },
        {
            "name": plan.event_outro_start,
            "description": f"Requests the {chapter} outro cutscene to start.",
            "payload": {},
        },
        {
            "name": plan.event_complete,
            "description": f"Fired when {chapter} is completed.",
            "payload": {},
        },
        {
            "name": plan.event_quest_complete,
            "description": f"Fired when the {chapter} quest completes.",
            "payload": {"quest_id": "string"},
        },
    ]


def _build_quest_entry(plan: EpisodeScaffoldPlan) -> dict[str, Any]:
    return {
        "id": plan.quest_id,
        "title": plan.scene_display_name,
        "description": f"Talk to the mentor, recover the clue, and exit in {plan.scene_display_name}.",
        "type": "main",
        "reward": {
            "set_flags": {
                plan.reward_flag_complete: True,
            }
        },
        "stages": [
            {
                "id": "step0",
                "title": "Choose Your Approach",
                "text": "Speak with the mentor and choose how to proceed.",
                "complete_on": plan.event_choice_made,
            },
            {
                "id": "step1",
                "title": "Find the Clue",
                "text": "Inspect the objective item to recover the clue.",
                "complete_on": plan.event_clue_found,
            },
            {
                "id": "step2",
                "title": "Reach the Exit",
                "text": "Use the unlocked door and finish the episode.",
                "complete_on": plan.event_complete,
                "emit_events_on_complete": [plan.event_quest_complete],
            },
        ],
    }


def _build_cutscene_entries(plan: EpisodeScaffoldPlan) -> list[dict[str, Any]]:
    mentor_name = _mentor_mesh_name(plan)
    return [
        {
            "id": plan.cutscene_intro_id,
            "schema_version": 1,
            "steps": [
                {"type": "wait", "duration": 0.3},
                {"type": "emit_event", "event": plan.event_intro_done},
            ],
            "commands": [
                {"type": "wait", "duration": 0.3},
                {"type": "emit_event", "event_type": plan.event_intro_done},
                {"type": "start_dialogue", "dialogue_id": plan.dialogue_id, "target": mentor_name},
                {"type": "stop"},
            ],
        },
        {
            "id": plan.cutscene_outro_id,
            "schema_version": 1,
            "steps": [
                {"type": "wait", "duration": 0.2},
                {"type": "emit_event", "event": plan.event_complete},
            ],
            "commands": [
                {"type": "wait", "duration": 0.2},
                {"type": "emit_event", "event_type": plan.event_complete},
                {"type": "stop"},
            ],
        },
    ]


def _build_dialogue_entry(plan: EpisodeScaffoldPlan) -> dict[str, Any]:
    return {
        "id": plan.dialogue_id,
        "schema_version": 1,
        "start_node": "start",
        "script": _dialogue_script_nodes(plan),
    }


def _build_prefab_entries(plan: EpisodeScaffoldPlan) -> list[dict[str, Any]]:
    author = plan.quest_id
    return [
        {
            "id": plan.prefab_mentor_id,
            "tags": [plan.episode_tag, "npc", "mentor"],
            "metadata": {"author": author},
            "display_name": f"{plan.scene_display_name} Mentor",
            "entity": {
                "sprite": "assets/placeholder.png",
                "behaviours": ["DialogueRunner"],
                "behaviour_config": {
                    "DialogueRunner": {
                        "dialogue_id": plan.dialogue_id,
                        "start_node": "start",
                        "auto_advance": True,
                        "script": _dialogue_script_nodes(plan),
                    }
                },
            },
        },
        {
            "id": plan.prefab_trigger_id,
            "tags": [plan.episode_tag, "trigger"],
            "metadata": {"author": author},
            "display_name": f"{plan.scene_display_name} Entry Trigger",
            "entity": {
                "sprite": None,
                "behaviours": ["TriggerVolume"],
                "behaviour_config": {
                    "TriggerVolume": {
                        "volume_type": "rect",
                        "width": 96,
                        "height": 96,
                        "target_tags": ["player"],
                        "on_enter_event": plan.event_entered,
                        "one_shot": True,
                    }
                },
            },
        },
        {
            "id": plan.prefab_door_id,
            "tags": [plan.episode_tag, "door"],
            "metadata": {"author": author},
            "display_name": f"{plan.scene_display_name} Exit Door",
            "entity": {
                "sprite": "assets/placeholder.png",
                "behaviours": ["Interactable"],
                "behaviour_config": {
                    "Interactable": {
                        "interact_event": plan.event_exit_door_interact,
                        "interact_label": "Exit",
                        "target_tags": ["player"],
                    }
                },
            },
            "require_flags": [plan.flag_exit_unlocked],
        },
        {
            "id": plan.prefab_reward_id,
            "tags": [plan.episode_tag, "objective"],
            "metadata": {"author": author},
            "display_name": f"{plan.scene_display_name} Clue Item",
            "entity": {
                "sprite": "assets/placeholder.png",
                "behaviours": ["Interactable"],
                "behaviour_config": {
                    "Interactable": {
                        "interact_event": plan.event_clue_found,
                        "interact_label": "Inspect",
                        "target_tags": ["player"],
                        "one_shot": True,
                    }
                },
            },
        },
        {
            "id": plan.prefab_controller_id,
            "tags": [plan.episode_tag, "controller"],
            "metadata": {"author": author},
            "display_name": f"{plan.scene_display_name} Controller",
            "entity": {
                "sprite": None,
                "behaviours": ["ActionListRunner"],
                "behaviour_config": {
                    "ActionListRunner": {
                        "listen_events": [],
                        "actions": [],
                    }
                },
            },
        },
    ]


def _build_scene_payload(plan: EpisodeScaffoldPlan) -> dict[str, Any]:
    prefix = plan.runtime_prefix
    mentor_name = _mentor_mesh_name(plan)
    return {
        "name": plan.scene_display_name,
        "version": 1,
        "schema_version": 1,
        "settings": {
            "background_color": "#1e2a38",
            "world_width": 640,
            "world_height": 384,
        },
        "layers": [
            {"name": "background"},
            {"name": "entities"},
            {"name": "foreground"},
        ],
        "entities": [
            {
                "id": f"{prefix}_player",
                "name": f"Episode{plan.episode_number_padded}Player",
                "prefab_id": "player",
                "layer": "entities",
                "x": 64.0,
                "y": 192.0,
            },
            {
                "id": f"{prefix}_entry_trigger",
                "name": f"Episode{plan.episode_number_padded}EntryTrigger",
                "prefab_id": plan.prefab_trigger_id,
                "layer": "background",
                "x": 96.0,
                "y": 192.0,
            },
            {
                "id": f"{prefix}_mentor",
                "name": mentor_name,
                "prefab_id": plan.prefab_mentor_id,
                "layer": "entities",
                "x": 256.0,
                "y": 192.0,
            },
            {
                "id": f"{prefix}_clue",
                "name": f"Episode{plan.episode_number_padded}Clue",
                "prefab_id": plan.prefab_reward_id,
                "layer": "entities",
                "x": 352.0,
                "y": 192.0,
            },
            {
                "id": f"{prefix}_exit_door",
                "name": f"Episode{plan.episode_number_padded}ExitDoor",
                "prefab_id": plan.prefab_door_id,
                "layer": "entities",
                "x": 512.0,
                "y": 192.0,
            },
            {
                "id": f"{prefix}_intro_start_ctrl",
                "name": f"Episode{plan.episode_number_padded}IntroStart",
                "prefab_id": plan.prefab_controller_id,
                "layer": "background",
                "x": 0.0,
                "y": 0.0,
                "behaviour_config": {
                    "ActionListRunner": {
                        "listen_events": [plan.event_entered],
                        "actions": [
                            {"type": "set_flag", "flag": plan.flag_entered},
                            {"type": "emit_event", "event_type": plan.event_intro_start},
                        ],
                    }
                },
            },
            {
                "id": f"{prefix}_choice_help_ctrl",
                "name": f"Episode{plan.episode_number_padded}ChoiceHelp",
                "prefab_id": plan.prefab_controller_id,
                "layer": "background",
                "x": 0.0,
                "y": 0.0,
                "behaviour_config": {
                    "ActionListRunner": {
                        "listen_events": ["dialogue_choice"],
                        "event_filter": {"choice_text": "I can help."},
                        "actions": [
                            {"type": "set_flag", "flag": plan.flag_choice_help},
                            {"type": "clear_flag", "flag": plan.flag_choice_solo},
                            {"type": "emit_event", "event_type": plan.event_choice_made, "payload": {"choice": "help"}},
                        ],
                    }
                },
            },
            {
                "id": f"{prefix}_choice_solo_ctrl",
                "name": f"Episode{plan.episode_number_padded}ChoiceSolo",
                "prefab_id": plan.prefab_controller_id,
                "layer": "background",
                "x": 0.0,
                "y": 0.0,
                "behaviour_config": {
                    "ActionListRunner": {
                        "listen_events": ["dialogue_choice"],
                        "event_filter": {"choice_text": "I work alone."},
                        "actions": [
                            {"type": "set_flag", "flag": plan.flag_choice_solo},
                            {"type": "clear_flag", "flag": plan.flag_choice_help},
                            {"type": "emit_event", "event_type": plan.event_choice_made, "payload": {"choice": "solo"}},
                        ],
                    }
                },
            },
            {
                "id": f"{prefix}_unlock_help_ctrl",
                "name": f"Episode{plan.episode_number_padded}UnlockHelp",
                "prefab_id": plan.prefab_controller_id,
                "layer": "background",
                "x": 0.0,
                "y": 0.0,
                "behaviour_config": {
                    "ActionListRunner": {
                        "listen_events": [plan.event_clue_found],
                        "require_flags": [plan.flag_choice_help],
                        "actions": [
                            {"type": "set_flag", "flag": plan.flag_exit_unlocked},
                            {"type": "emit_event", "event_type": plan.event_exit_unlocked},
                        ],
                    }
                },
            },
            {
                "id": f"{prefix}_unlock_solo_ctrl",
                "name": f"Episode{plan.episode_number_padded}UnlockSolo",
                "prefab_id": plan.prefab_controller_id,
                "layer": "background",
                "x": 0.0,
                "y": 0.0,
                "behaviour_config": {
                    "ActionListRunner": {
                        "listen_events": [plan.event_clue_found],
                        "require_flags": [plan.flag_choice_solo],
                        "actions": [
                            {"type": "set_flag", "flag": plan.flag_exit_unlocked},
                            {"type": "emit_event", "event_type": plan.event_exit_unlocked},
                        ],
                    }
                },
            },
            {
                "id": f"{prefix}_outro_ctrl",
                "name": f"Episode{plan.episode_number_padded}OutroStart",
                "prefab_id": plan.prefab_controller_id,
                "layer": "background",
                "x": 0.0,
                "y": 0.0,
                "behaviour_config": {
                    "ActionListRunner": {
                        "listen_events": [plan.event_exit_door_interact],
                        "require_flags": [plan.flag_exit_unlocked],
                        "actions": [
                            {"type": "emit_event", "event_type": plan.event_outro_start},
                        ],
                    }
                },
            },
            {
                "id": f"{prefix}_complete_ctrl",
                "name": f"Episode{plan.episode_number_padded}Complete",
                "prefab_id": plan.prefab_controller_id,
                "layer": "background",
                "x": 0.0,
                "y": 0.0,
                "behaviour_config": {
                    "ActionListRunner": {
                        "listen_events": [plan.event_complete],
                        "actions": [
                            {"type": "set_flag", "flag": plan.flag_complete},
                        ],
                    }
                },
            },
        ],
    }


def _build_doc_text(plan: EpisodeScaffoldPlan) -> str:
    lines = [
        f"# {plan.scene_display_name}",
        "",
        "Generated scaffold wiring:",
        f"- Scene: `{plan.scene_rel_path.as_posix()}`",
        f"- Quest: `{plan.quest_id}`",
        f"- Cutscenes: `{plan.cutscene_intro_id}`, `{plan.cutscene_outro_id}`",
        f"- Dialogue: `{plan.dialogue_id}`",
        "",
        "## Prefabs",
        f"- `{plan.prefab_mentor_id}`: DialogueRunner mentor NPC.",
        f"- `{plan.prefab_trigger_id}`: TriggerVolume that emits `{plan.event_entered}`.",
        f"- `{plan.prefab_door_id}`: Interactable exit gate (requires `{plan.flag_exit_unlocked}`).",
        f"- `{plan.prefab_reward_id}`: Interactable objective clue.",
        f"- `{plan.prefab_controller_id}`: ActionListRunner controller base.",
        "",
        "## Event Flow",
        f"1. Entry emits `{plan.event_entered}` and sets `{plan.flag_entered}`.",
        f"2. Intro start emits `{plan.event_intro_start}`.",
        f"3. Intro cutscene emits `{plan.event_intro_done}` and starts dialogue `{plan.dialogue_id}`.",
        f"4. Dialogue choice emits `{plan.event_choice_made}` and sets branch flags.",
        f"5. Clue interaction emits `{plan.event_clue_found}`.",
        f"6. Branch controllers emit `{plan.event_exit_unlocked}` and set `{plan.flag_exit_unlocked}`.",
        f"7. Exit interaction emits `{plan.event_exit_door_interact}` then `{plan.event_outro_start}`.",
        f"8. Outro cutscene emits `{plan.event_complete}`.",
        f"9. Quest completion emits `{plan.event_quest_complete}`.",
        "",
        "## Flags",
        f"- `{plan.flag_entered}`",
        f"- `{plan.flag_choice_help}`",
        f"- `{plan.flag_choice_solo}`",
        f"- `{plan.flag_exit_unlocked}`",
        f"- `{plan.flag_complete}`",
        "",
        "## Test Notes",
        f"- Generated test: `{plan.test_rel_path.as_posix()}`",
        "- Determinism check runs the same quest event stream twice and compares digests.",
        "",
    ]
    return "\n".join(lines)


def _build_test_text(plan: EpisodeScaffoldPlan) -> str:
    return f'''"""Generated integration tests for {plan.scene_display_name}."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from engine.gameplay_event_bus import GameplayEvent
from engine.quest_runtime.runner import QuestRunner


SEED = {plan.seed}
SCENE_PATH = Path("{plan.scene_rel_path.as_posix()}")
PREFABS_PATH = Path("{plan.prefabs_rel_path.as_posix()}")
QUESTS_PATH = Path("{plan.quests_rel_path.as_posix()}")
CUTSCENES_PATH = Path("{plan.cutscenes_rel_path.as_posix()}")
DIALOGUES_PATH = Path("{plan.dialogues_rel_path.as_posix()}")
EVENTS_PATH = Path("{plan.events_rel_path.as_posix()}")

QUEST_ID = "{plan.quest_id}"
DIALOGUE_ID = "{plan.dialogue_id}"
CUTSCENE_IDS = ("{plan.cutscene_intro_id}", "{plan.cutscene_outro_id}")
EVENT_NAMES = {list(plan.event_names)!r}
PREFAB_IDS = {list(plan.prefab_ids)!r}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(payload: Any) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _find_by_id(entries: list[dict[str, Any]], entry_id: str) -> dict[str, Any]:
    for entry in entries:
        if str(entry.get("id", "")) == entry_id:
            return entry
    raise AssertionError(f"missing id: {{entry_id}}")


def _run_quest_path(choice: str) -> dict[str, Any]:
    runner = QuestRunner()
    runner.load_definitions(QUESTS_PATH)
    assert runner.get_definition(QUEST_ID) is not None
    assert runner.start_quest(QUEST_ID) is True

    if choice == "help":
        choice_payload = {{"choice": "help"}}
    else:
        choice_payload = {{"choice": "solo"}}

    events = [
        GameplayEvent(event_type="{plan.event_choice_made}", payload=choice_payload, sequence=1),
        GameplayEvent(event_type="{plan.event_clue_found}", payload={{"target": "clue"}}, sequence=2),
        GameplayEvent(event_type="{plan.event_complete}", payload={{}}, sequence=3),
    ]

    emitted_types: list[str] = []
    for event in events:
        emitted = runner.process_events([event])
        emitted_types.extend(e.event_type for e in emitted)

    state = runner.get_quest_state(QUEST_ID)
    assert state is not None
    assert state.status == "completed"
    assert "{plan.event_quest_complete}" in emitted_types
    return {{
        "choice": choice,
        "completed_stages": list(state.completed_stages),
        "emitted_types": emitted_types,
    }}


def test_episode_scaffold_content_wiring() -> None:
    scene = _load_json(SCENE_PATH)
    assert scene.get("schema_version") == 1

    prefabs = _load_json(PREFABS_PATH)
    prefab_map = {{entry["id"]: entry for entry in prefabs if isinstance(entry, dict) and "id" in entry}}
    for prefab_id in PREFAB_IDS:
        assert prefab_id in prefab_map

    scene_entities = list(scene.get("entities", []))
    for entity in scene_entities:
        if not isinstance(entity, dict):
            continue
        prefab_id = str(entity.get("prefab_id", "")).strip()
        if prefab_id:
            assert prefab_id in prefab_map

    quests = _load_json(QUESTS_PATH).get("quests", [])
    quest_entry = _find_by_id(quests, QUEST_ID)
    assert len(list(quest_entry.get("stages", []))) == 3

    cutscenes = _load_json(CUTSCENES_PATH).get("cutscenes", [])
    for cutscene_id in CUTSCENE_IDS:
        _find_by_id(cutscenes, cutscene_id)

    dialogues = _load_json(DIALOGUES_PATH).get("dialogues", [])
    _find_by_id(dialogues, DIALOGUE_ID)

    events = _load_json(EVENTS_PATH).get("events", [])
    event_names = {{str(entry.get("name", "")) for entry in events if isinstance(entry, dict)}}
    for event_name in EVENT_NAMES:
        assert event_name in event_names


def test_episode_scaffold_determinism() -> None:
    _ = SEED
    scene_digest_a = _digest(_load_json(SCENE_PATH))
    scene_digest_b = _digest(_load_json(SCENE_PATH))
    assert scene_digest_a == scene_digest_b

    help_a = _run_quest_path("help")
    help_b = _run_quest_path("help")
    assert _digest(help_a) == _digest(help_b)

    solo_a = _run_quest_path("solo")
    solo_b = _run_quest_path("solo")
    assert _digest(solo_a) == _digest(solo_b)
'''


def _dialogue_script_nodes(plan: EpisodeScaffoldPlan) -> dict[str, Any]:
    return {
        "start": {
            "speaker": "Mentor",
            "text": f"{plan.scene_display_name} begins now. Will you coordinate or improvise?",
            "choices": [
                {"text": "I can help.", "next": "help_path"},
                {"text": "I work alone.", "next": "solo_path"},
            ],
        },
        "help_path": {
            "speaker": "Mentor",
            "text": "Good. Keep the channel clear and we finish this together.",
            "next": "confirm",
        },
        "solo_path": {
            "speaker": "Mentor",
            "text": "Then move quickly and trust your own notes.",
            "next": "confirm",
        },
        "confirm": {
            "speaker": "Mentor",
            "text": "Retrieve the clue and meet me at the exit.",
            "next": None,
        },
    }


def _mentor_mesh_name(plan: EpisodeScaffoldPlan) -> str:
    return f"Episode{plan.episode_number_padded}Mentor"
