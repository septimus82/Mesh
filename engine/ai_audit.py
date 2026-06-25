"""AI Audit tool for scanning scenes and quests."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set

from .content_index import ContentIndex
from .paths import resolve_path


@dataclass
class SceneAuditReport:
    scene_id: str
    npc_count: int = 0
    npc_with_dialogue: int = 0
    npc_without_dialogue: int = 0
    npc_with_tags: int = 0
    npc_without_tags: int = 0
    transition_count: int = 0
    transitions_with_missing_target: int = 0
    quest_hooks: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class QuestAuditReport:
    id: str
    has_triggers: bool = False


@dataclass
class AIAuditReport:
    scenes: List[SceneAuditReport] = field(default_factory=list)
    quests: List[QuestAuditReport] = field(default_factory=list)
    global_warnings: List[str] = field(default_factory=list)


def _extract_quest_ids(raw_quests: Any) -> Set[str]:
    if isinstance(raw_quests, dict):
        quests = raw_quests.get("quests")
        if isinstance(quests, list):
            return _extract_quest_ids_from_list(quests)
        return {str(key) for key in raw_quests.keys() if str(key).strip()}
    if isinstance(raw_quests, list):
        return _extract_quest_ids_from_list(raw_quests)
    return set()


def _extract_quest_ids_from_list(raw_quests: List[Any]) -> Set[str]:
    quest_ids: Set[str] = set()
    for entry in raw_quests:
        if not isinstance(entry, dict):
            continue
        quest_id = entry.get("id")
        if isinstance(quest_id, str) and quest_id.strip():
            quest_ids.add(quest_id)
    return quest_ids


def build_audit_report(scene_paths: List[Path] | None = None) -> AIAuditReport:
    """
    Builds an AI audit report.
    If scene_paths is provided, only audits those scenes (scoped audit).
    If scene_paths is None, audits all scenes in the project (full audit).
    """
    report = AIAuditReport()

    # 1. Load Content Index to find all scenes
    # We need to initialize ContentIndex with roots.
    roots = [Path(".")]
    index = ContentIndex(roots)
    index.build()

    # 2. Load Quests to validate IDs
    quest_ids: Set[str] = set()
    quests_path = resolve_path("assets/data/quests.json")
    if quests_path.exists():
        try:
            raw_quests = json.loads(quests_path.read_text(encoding="utf-8"))
            quest_ids = _extract_quest_ids(raw_quests)
        except Exception as e:
            report.global_warnings.append(f"Failed to load quests.json: {e}")

    # Track which quests are referenced
    referenced_quests: Set[str] = set()

    # 3. Determine scenes to scan
    is_full_audit = scene_paths is None
    resolved_scene_paths: List[Path] = []
    if is_full_audit:
        for key, entry in index.entries.items():
            if key.endswith(".json") and ("scenes/" in key or "scenes\\" in key):
                resolved_scene_paths.append(entry.resolved_path)
    else:
        assert scene_paths is not None
        resolved_scene_paths = list(scene_paths)

    # 4. Scan Scenes
    for scene_path in resolved_scene_paths:
        # Ensure path is absolute or resolved relative to cwd for reading
        if not scene_path.is_absolute():
            scene_path = resolve_path(str(scene_path))

        if not scene_path.exists():
            report.global_warnings.append(f"Scene file not found: {scene_path}")
            continue

        scene_report = _audit_scene(scene_path, index, quest_ids)
        report.scenes.append(scene_report)
        referenced_quests.update(scene_report.quest_hooks)

    # 5. Analyze Quests
    # For scoped audit, we only include referenced quests.
    # For full audit, we include all quests and warn about unused ones.
    if is_full_audit:
        for q_id in sorted(quest_ids):
            report.quests.append(QuestAuditReport(
                id=q_id,
                has_triggers=q_id in referenced_quests
            ))
            if q_id not in referenced_quests:
                report.global_warnings.append(f"Quest '{q_id}' has no triggers in any scene.")
    else:
        # Scoped: only report referenced quests
        for q_id in sorted(referenced_quests):
            if q_id in quest_ids:
                report.quests.append(QuestAuditReport(id=q_id, has_triggers=True))
            else:
                # Referenced but not defined? _audit_scene handles that warning per scene,
                # but we can add it to the list if we want.
                pass

    return report


def run_ai_audit(json_output: bool = False) -> Dict[str, Any] | None:
    """
    Scan all scenes and quests to produce an AI surface report.

    Args:
        json_output: If True, returns the report as a dictionary.
                     If False, prints a human-readable summary and returns None.
    """
    report = build_audit_report()

    if json_output:
        return asdict(report)

    _print_text_report(report)
    return None

    _print_text_report(report)
    return None


def _audit_scene(scene_path: Path, index: ContentIndex, valid_quest_ids: Set[str]) -> SceneAuditReport:
    scene_id = str(scene_path.as_posix())
    audit = SceneAuditReport(scene_id=scene_id)

    try:
        data = json.loads(scene_path.read_text(encoding="utf-8"))
    except Exception as e:
        audit.warnings.append(f"Failed to load scene: {e}")
        return audit

    entities = data.get("entities", [])

    for entity in entities:
        # Check for NPC-ness (name, dialogue, tags)
        is_npc = False
        has_dialogue = False

        name = entity.get("name")
        dialogue = entity.get("dialogue")
        tags = entity.get("tags")

        if name or dialogue or tags:
            is_npc = True

        # Also check behaviours for NPC-like traits if needed, but data is usually enough

        if is_npc:
            audit.npc_count += 1

            has_dialogue = bool(dialogue and isinstance(dialogue, dict) and dialogue.get("id"))
            if has_dialogue:
                audit.npc_with_dialogue += 1
            else:
                audit.npc_without_dialogue += 1
                # Only warn if it looks like it SHOULD have dialogue (e.g. has a name)
                if name:
                    audit.warnings.append(f"NPC '{name}' has no dialogue ID.")

            if tags and isinstance(tags, list) and len(tags) > 0:
                audit.npc_with_tags += 1
            else:
                audit.npc_without_tags += 1
                # Warn if it has dialogue but no tags (AI might need tags)
                if has_dialogue:
                    audit.warnings.append(f"NPC '{name or 'Unnamed'}' has dialogue but no tags.")

        # Check Behaviours
        behaviours = entity.get("behaviours", [])
        for b in behaviours:
            if isinstance(b, str):
                b_type = b
                params = {}
            else:
                b_type = b.get("type")
                params = b.get("params", {})

            # Transitions
            if b_type == "SceneTransition":
                audit.transition_count += 1
                target = params.get("target_scene")
                if not target:
                    audit.transitions_with_missing_target += 1
                    audit.warnings.append("Transition missing target_scene.")
                else:
                    # Validate target exists
                    # We can use the index to check if the file exists
                    # target is usually a relative path like "scenes/foo.json"
                    # ContentIndex stores absolute paths or relative?
                    # Usually we resolve it.
                    resolved = resolve_path(target)
                    if not resolved.exists():
                        audit.transitions_with_missing_target += 1
                        audit.warnings.append(f"Transition target '{target}' does not exist.")

            # Quest Hooks
            # Look for behaviours that reference quest_id
            # e.g. IncrementCounterOnEvent, SetGameStateOnEvent might have quest_id
            q_id = params.get("quest_id")
            if q_id:
                audit.quest_hooks.append(q_id)
                if q_id not in valid_quest_ids:
                    audit.warnings.append(f"References unknown quest '{q_id}'.")

    return audit


def _print_text_report(report: AIAuditReport) -> None:
    print("AI Audit Report")
    print("===============")
    print("")

    for scene in report.scenes:
        print(f"Scene: {scene.scene_id}")
        print(f"  NPCs: {scene.npc_count}")
        print(f"    With Dialogue: {scene.npc_with_dialogue}")
        print(f"    Without Dialogue: {scene.npc_without_dialogue}")
        print(f"    With Tags: {scene.npc_with_tags}")
        print(f"    Without Tags: {scene.npc_without_tags}")
        print(f"  Transitions: {scene.transition_count}")
        if scene.transitions_with_missing_target > 0:
            print(f"    MISSING TARGETS: {scene.transitions_with_missing_target}")

        if scene.quest_hooks:
            print(f"  Quest Hooks: {', '.join(sorted(set(scene.quest_hooks)))}")

        if scene.warnings:
            print("  Warnings:")
            for w in scene.warnings:
                print(f"    - {w}")
        print("")

    print("Global Warnings")
    print("===============")
    if not report.global_warnings:
        print("None.")
    else:
        for w in report.global_warnings:
            print(f"- {w}")
    print("")
