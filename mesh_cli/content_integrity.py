
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from engine.diagnostics import Diagnostic, DiagnosticLevel, sort_diagnostics
from engine.log_utils import normalize_path
from engine.persistence_io import dumps_json_deterministic


SCHEMA_VERSION = 1

EVENTS_REL = Path("assets/data/events.json")
QUESTS_REL = Path("assets/data/quests.json")
CUTSCENES_REL = Path("cutscenes.json")
DIALOGUES_REL = Path("assets/data/dialogues.json")
PREFABS_REL = Path("assets/prefabs.json")
SCENES_DIR_REL = Path("scenes")

REQUIRED_CONTENT_ROOTS: tuple[Path, ...] = (
    EVENTS_REL,
    QUESTS_REL,
    CUTSCENES_REL,
    PREFABS_REL,
    SCENES_DIR_REL,
)

DEFAULT_MINIMUM_COUNTS: dict[str, int] = {
    "events": 100,
    "quests": 20,
    "cutscenes": 6,
    "dialogues": 4,
    "prefabs": 50,
    "scenes": 10,
}

EVENT_NAME_RE = re.compile(r"^[a-z][a-z0-9_.]*$")
ID_RE = re.compile(r"^[a-z0-9_]+$")
FLAG_RE = re.compile(r"^[a-z][a-z0-9_.-]*$")


def _norm_path(path: Path) -> str:
    return normalize_path(path.as_posix())


def _ptr(parent: str, token: str) -> str:
    escaped = token.replace("~", "~0").replace("/", "~1")
    return f"$/{escaped}" if parent == "$" else f"{parent}/{escaped}"


def _iptr(parent: str, index: int) -> str:
    return _ptr(parent, str(index))


@dataclass(frozen=True, slots=True)
class AuditIssue:
    severity: str
    code: str
    file: str
    pointer: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "file": self.file,
            "pointer": self.pointer,
            "message": self.message,
        }

    def to_diagnostic(self) -> Diagnostic:
        level = DiagnosticLevel.WARN if self.severity == "warning" else DiagnosticLevel.ERROR
        return Diagnostic(
            level=level,
            code=self.code,
            message=self.message,
            context={
                "file": self.file,
                "pointer": self.pointer,
            },
            hint=None,
        )

    @classmethod
    def from_diagnostic(cls, diag: Diagnostic) -> "AuditIssue":
        context = diag.context if isinstance(diag.context, dict) else {}
        file = str(context.get("file", "<unknown>") or "<unknown>")
        pointer = str(context.get("pointer", "$") or "$")
        severity = "warning" if diag.level == DiagnosticLevel.WARN else "error"
        return cls(
            severity=severity,
            code=str(diag.code),
            file=file,
            pointer=pointer,
            message=str(diag.message),
        )


@dataclass(frozen=True, slots=True)
class FileDigest:
    file: str
    sha256: str
    size: int

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "sha256": self.sha256, "size": self.size}


@dataclass(frozen=True, slots=True)
class ContentAuditReport:
    schema_version: int
    ok: bool
    errors: tuple[AuditIssue, ...]
    warnings: tuple[AuditIssue, ...]
    stats: dict[str, int]
    digests: tuple[FileDigest, ...]
    events_emitted: tuple[str, ...]
    events_referenced: tuple[str, ...]
    events_missing: tuple[str, ...]
    diagnostics: tuple[Diagnostic, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ok": self.ok,
            "errors": [item.to_dict() for item in self.errors],
            "warnings": [item.to_dict() for item in self.warnings],
            "stats": dict(self.stats),
            "digests": [item.to_dict() for item in self.digests],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "events": {
                "emitted": list(self.events_emitted),
                "referenced": list(self.events_referenced),
                "missing": list(self.events_missing),
            },
        }


class _Collector:
    def __init__(self) -> None:
        self.errors: list[AuditIssue] = []
        self.warnings: list[AuditIssue] = []

    def error(self, *, code: str, file: str, pointer: str, message: str) -> None:
        self.errors.append(AuditIssue("error", code, file, pointer, message))

    def warning(self, *, code: str, file: str, pointer: str, message: str) -> None:
        self.warnings.append(AuditIssue("warning", code, file, pointer, message))


class _Loader:
    def __init__(self, repo_root: Path, collector: _Collector) -> None:
        self.repo_root = repo_root
        self.collector = collector
        self.digests: dict[str, FileDigest] = {}

    def _record_digest(self, rel_path: Path, raw: bytes) -> None:
        file = _norm_path(rel_path)
        self.digests[file] = FileDigest(file, hashlib.sha256(raw).hexdigest(), len(raw))

    def load_json(self, rel_path: Path, *, required: bool = True) -> Any:
        file = _norm_path(rel_path)
        abs_path = self.repo_root / rel_path
        if not abs_path.exists():
            if required:
                self.collector.error(code="content.file.missing", file=file, pointer="$", message=f"required file not found: {file}")
            return None

        raw = abs_path.read_bytes()
        self._record_digest(rel_path, raw)
        text = raw.decode("utf-8")
        if text.startswith("\ufeff"):
            self.collector.error(code="content.json.bom", file=file, pointer="$", message="UTF-8 BOM is forbidden in JSON content files")
            text = text[1:]

        dupes: list[str] = []

        def _hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            out: dict[str, Any] = {}
            for key, value in pairs:
                if key in out:
                    dupes.append(key)
                out[key] = value
            return out

        try:
            payload = json.loads(text, object_pairs_hook=_hook)
        except json.JSONDecodeError as exc:
            self.collector.error(
                code="content.json.parse_error",
                file=file,
                pointer="$",
                message=f"invalid JSON: {exc.msg} (line {exc.lineno}, col {exc.colno})",
            )
            return None

        for key in sorted(set(dupes)):
            self.collector.error(
                code="content.json.duplicate_key",
                file=file,
                pointer="$",
                message=f"duplicate JSON key detected (best-effort): '{key}'",
            )
        return payload


def has_required_content_roots(repo_root: Path) -> bool:
    root = Path(repo_root)
    for rel in REQUIRED_CONTENT_ROOTS:
        if not (root / rel).exists():
            return False
    return True


def _as_object_array(payload: Any, *, file: str, pointer: str, key: str | None, collector: _Collector) -> list[dict[str, Any]]:
    data = payload
    source_ptr = pointer
    if key is not None:
        if isinstance(payload, dict):
            data = payload.get(key, [])
            source_ptr = _ptr(pointer, key)
        else:
            collector.error(code="content.json.invalid_root", file=file, pointer=pointer, message="JSON root must be an object")
            return []

    if data is None:
        data = []
    if not isinstance(data, list):
        collector.error(code="content.json.invalid_array", file=file, pointer=source_ptr, message="expected an array")
        return []

    out: list[dict[str, Any]] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            collector.error(
                code="content.json.invalid_entry",
                file=file,
                pointer=_iptr(source_ptr, index),
                message="array entry must be an object",
            )
            continue
        out.append(item)
    return out


def _add_ref(
    refs: list[tuple[str, str, str, str]],
    *,
    name: str,
    file: str,
    pointer: str,
    source: str,
) -> None:
    normalized = name.strip()
    if normalized:
        refs.append((normalized, file, pointer, source))


def _collect_refs(
    value: Any,
    *,
    file: str,
    pointer: str,
    collector: _Collector,
    event_refs: list[tuple[str, str, str, str]],
    emitted_events: set[str],
    dialogue_refs: list[tuple[str, str, str]],
    cutscene_refs: list[tuple[str, str, str]],
    inline_dialogue_ids: set[str],
) -> None:
    if isinstance(value, dict):
        has_inline_dialogue = isinstance(value.get("dialogue_id"), str) and isinstance(value.get("script"), dict)
        if has_inline_dialogue:
            inline_dialogue_ids.add(str(value.get("dialogue_id", "")).strip())

        for key in sorted(value.keys()):
            child = value[key]
            child_ptr = _ptr(pointer, str(key))
            if key in {
                "event",
                "event_type",
                "emit_event",
                "listen_event",
                "on_enter_event",
                "on_exit_event",
                "interact_event",
                "start_on_event",
            } and isinstance(child, str):
                _add_ref(event_refs, name=child, file=file, pointer=child_ptr, source=key)
                if key in {"event", "event_type", "emit_event", "on_enter_event", "on_exit_event", "interact_event"}:
                    emitted_events.add(child.strip())
            elif key in {"listen_events", "emit_events_on_complete"} and isinstance(child, list):
                for index, item in enumerate(child):
                    if isinstance(item, str):
                        item_ptr = _iptr(child_ptr, index)
                        _add_ref(event_refs, name=item, file=file, pointer=item_ptr, source=key)
                        if key == "emit_events_on_complete":
                            emitted_events.add(item.strip())
            elif key == "dialogue_id" and isinstance(child, str):
                dialogue_refs.append((child.strip(), file, child_ptr))
            elif key == "cutscene_id" and isinstance(child, str):
                cutscene_refs.append((child.strip(), file, child_ptr))
            elif key in {"require_flags", "forbid_flags", "requires_flags", "blocks_flags"}:
                if not isinstance(child, list):
                    collector.error(code="content.flags.invalid_type", file=file, pointer=child_ptr, message=f"{key} must be an array")
                else:
                    for index, item in enumerate(child):
                        item_ptr = _iptr(child_ptr, index)
                        if not isinstance(item, str) or not item.strip():
                            collector.error(code="content.flags.invalid_item", file=file, pointer=item_ptr, message=f"{key}[{index}] must be a non-empty string")
                        elif not FLAG_RE.fullmatch(item):
                            collector.error(code="content.flags.invalid_name", file=file, pointer=item_ptr, message=f"flag name does not match pattern: '{item}'")

            _collect_refs(
                child,
                file=file,
                pointer=child_ptr,
                collector=collector,
                event_refs=event_refs,
                emitted_events=emitted_events,
                dialogue_refs=dialogue_refs,
                cutscene_refs=cutscene_refs,
                inline_dialogue_ids=inline_dialogue_ids,
            )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _collect_refs(
                item,
                file=file,
                pointer=_iptr(pointer, index),
                collector=collector,
                event_refs=event_refs,
                emitted_events=emitted_events,
                dialogue_refs=dialogue_refs,
                cutscene_refs=cutscene_refs,
                inline_dialogue_ids=inline_dialogue_ids,
            )


def scan_events(payload: Any, *, collector: _Collector) -> tuple[int, set[str]]:
    file = _norm_path(EVENTS_REL)
    events = _as_object_array(payload, file=file, pointer="$", key="events" if isinstance(payload, dict) else None, collector=collector)
    seen: set[str] = set()
    for index, entry in enumerate(events):
        entry_ptr = _iptr("$/events" if isinstance(payload, dict) else "$", index)
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            collector.error(code="content.events.missing_name", file=file, pointer=_ptr(entry_ptr, "name"), message="event name is required")
            continue
        normalized = name.strip()
        if normalized in seen:
            collector.error(code="content.events.duplicate_name", file=file, pointer=_ptr(entry_ptr, "name"), message=f"duplicate event name '{normalized}'")
            continue
        seen.add(normalized)
        if not EVENT_NAME_RE.fullmatch(normalized):
            collector.error(
                code="content.events.invalid_name",
                file=file,
                pointer=_ptr(entry_ptr, "name"),
                message=f"event name does not match pattern {EVENT_NAME_RE.pattern}: '{normalized}'",
            )
    return len(seen), seen


def _extract_quest_event_refs(
    raw: Any,
    *,
    file: str,
    pointer: str,
    event_refs: list[tuple[str, str, str, str]],
) -> None:
    if isinstance(raw, str):
        _add_ref(event_refs, name=raw, file=file, pointer=pointer, source="quest_event")
    elif isinstance(raw, dict):
        event_type = raw.get("type")
        if isinstance(event_type, str):
            _add_ref(event_refs, name=event_type, file=file, pointer=_ptr(pointer, "type"), source="quest_event")
    elif isinstance(raw, list):
        for index, item in enumerate(raw):
            _extract_quest_event_refs(item, file=file, pointer=_iptr(pointer, index), event_refs=event_refs)


def scan_quests(
    payload: Any,
    *,
    collector: _Collector,
    event_refs: list[tuple[str, str, str, str]],
    emitted_events: set[str],
) -> tuple[int, set[str]]:
    file = _norm_path(QUESTS_REL)
    quests = _as_object_array(payload, file=file, pointer="$", key="quests" if isinstance(payload, dict) else None, collector=collector)
    seen_ids: set[str] = set()

    for index, quest in enumerate(quests):
        base_ptr = _iptr("$/quests" if isinstance(payload, dict) else "$", index)
        quest_id = quest.get("id")
        if not isinstance(quest_id, str) or not quest_id.strip():
            collector.error(code="content.quests.missing_id", file=file, pointer=_ptr(base_ptr, "id"), message="quest id is required")
            continue
        normalized_id = quest_id.strip()
        if normalized_id in seen_ids:
            collector.error(code="content.quests.duplicate_id", file=file, pointer=_ptr(base_ptr, "id"), message=f"duplicate quest id '{normalized_id}'")
        else:
            seen_ids.add(normalized_id)
        if not ID_RE.fullmatch(normalized_id):
            collector.error(code="content.quests.invalid_id", file=file, pointer=_ptr(base_ptr, "id"), message=f"quest id does not match pattern: '{normalized_id}'")

        for flag_key in ("requires_flags", "blocks_flags"):
            raw_flags = quest.get(flag_key)
            if raw_flags is None:
                continue
            if not isinstance(raw_flags, list):
                collector.error(code="content.flags.invalid_type", file=file, pointer=_ptr(base_ptr, flag_key), message=f"{flag_key} must be an array")
                continue
            for flag_index, flag in enumerate(raw_flags):
                flag_ptr = _iptr(_ptr(base_ptr, flag_key), flag_index)
                if not isinstance(flag, str) or not flag.strip() or not FLAG_RE.fullmatch(flag):
                    collector.error(code="content.flags.invalid_name", file=file, pointer=flag_ptr, message=f"invalid flag name '{flag}'")

        stages = quest.get("stages")
        if stages is None and isinstance(quest.get("steps"), list):
            stages = quest.get("steps")
        if not isinstance(stages, list):
            collector.error(code="content.quests.invalid_stages", file=file, pointer=_ptr(base_ptr, "stages"), message="quest stages must be an array")
            continue

        stage_ids: set[str] = set()
        for stage_index, stage in enumerate(stages):
            stage_ptr = _iptr(_ptr(base_ptr, "stages"), stage_index)
            if not isinstance(stage, dict):
                collector.error(code="content.quests.invalid_stage", file=file, pointer=stage_ptr, message="quest stage must be an object")
                continue

            stage_id = stage.get("id")
            if not isinstance(stage_id, str) or not stage_id.strip():
                collector.error(code="content.quests.stage_missing_id", file=file, pointer=_ptr(stage_ptr, "id"), message="stage id is required")
            else:
                stage_id_norm = stage_id.strip()
                if stage_id_norm in stage_ids:
                    collector.error(code="content.quests.duplicate_stage_id", file=file, pointer=_ptr(stage_ptr, "id"), message=f"duplicate stage id '{stage_id_norm}'")
                else:
                    stage_ids.add(stage_id_norm)

            _extract_quest_event_refs(stage.get("start_on_event"), file=file, pointer=_ptr(stage_ptr, "start_on_event"), event_refs=event_refs)
            _extract_quest_event_refs(stage.get("complete_on"), file=file, pointer=_ptr(stage_ptr, "complete_on"), event_refs=event_refs)

            emits = stage.get("emit_events_on_complete")
            if emits is not None:
                if not isinstance(emits, list):
                    collector.error(code="content.quests.invalid_emit_events", file=file, pointer=_ptr(stage_ptr, "emit_events_on_complete"), message="emit_events_on_complete must be an array")
                else:
                    for emit_index, item in enumerate(emits):
                        emit_ptr = _iptr(_ptr(stage_ptr, "emit_events_on_complete"), emit_index)
                        if isinstance(item, str):
                            _add_ref(event_refs, name=item, file=file, pointer=emit_ptr, source="emit_events_on_complete")
                            emitted_events.add(item.strip())

    return len(seen_ids), seen_ids

def scan_cutscenes(
    payload: Any,
    *,
    collector: _Collector,
    event_refs: list[tuple[str, str, str, str]],
    emitted_events: set[str],
    dialogue_refs: list[tuple[str, str, str]],
    cutscene_refs: list[tuple[str, str, str]],
    inline_dialogue_ids: set[str],
) -> tuple[int, set[str]]:
    file = _norm_path(CUTSCENES_REL)
    cutscenes = _as_object_array(payload, file=file, pointer="$", key="cutscenes" if isinstance(payload, dict) else None, collector=collector)

    seen_ids: set[str] = set()
    for index, cutscene in enumerate(cutscenes):
        base_ptr = _iptr("$/cutscenes" if isinstance(payload, dict) else "$", index)
        cutscene_id = cutscene.get("id")
        if not isinstance(cutscene_id, str) or not cutscene_id.strip():
            collector.error(code="content.cutscenes.missing_id", file=file, pointer=_ptr(base_ptr, "id"), message="cutscene id is required")
            continue
        cutscene_id_norm = cutscene_id.strip()
        if cutscene_id_norm in seen_ids:
            collector.error(code="content.cutscenes.duplicate_id", file=file, pointer=_ptr(base_ptr, "id"), message=f"duplicate cutscene id '{cutscene_id_norm}'")
        else:
            seen_ids.add(cutscene_id_norm)

        labels: set[str] = set()
        gotos: list[tuple[str, str]] = []
        for section in ("steps", "commands"):
            raw = cutscene.get(section)
            if raw is None:
                continue
            if not isinstance(raw, list):
                collector.error(code="content.cutscenes.invalid_section", file=file, pointer=_ptr(base_ptr, section), message=f"{section} must be an array")
                continue
            for step_index, step in enumerate(raw):
                step_ptr = _iptr(_ptr(base_ptr, section), step_index)
                if not isinstance(step, dict):
                    collector.error(code="content.cutscenes.invalid_step", file=file, pointer=step_ptr, message="cutscene step must be an object")
                    continue

                step_type = str(step.get("type", "") or "").strip().lower()
                if step_type == "label":
                    label_name = step.get("label") if isinstance(step.get("label"), str) else step.get("name")
                    if isinstance(label_name, str) and label_name.strip():
                        labels.add(label_name.strip())
                elif step_type in {"goto", "jump"}:
                    target = step.get("label") if isinstance(step.get("label"), str) else step.get("target")
                    if isinstance(target, str) and target.strip():
                        gotos.append((target.strip(), step_ptr))

                _collect_refs(
                    step,
                    file=file,
                    pointer=step_ptr,
                    collector=collector,
                    event_refs=event_refs,
                    emitted_events=emitted_events,
                    dialogue_refs=dialogue_refs,
                    cutscene_refs=cutscene_refs,
                    inline_dialogue_ids=inline_dialogue_ids,
                )

        for target_label, goto_ptr in sorted(gotos):
            if target_label not in labels:
                collector.error(code="content.cutscenes.missing_label", file=file, pointer=goto_ptr, message=f"goto target label not found: '{target_label}'")

    return len(seen_ids), seen_ids


def scan_dialogues(
    payload: Any,
    *,
    collector: _Collector,
    event_refs: list[tuple[str, str, str, str]],
    emitted_events: set[str],
) -> tuple[int, set[str]]:
    file = _norm_path(DIALOGUES_REL)
    dialogues = _as_object_array(payload, file=file, pointer="$", key="dialogues" if isinstance(payload, dict) else None, collector=collector)

    seen_ids: set[str] = set()
    for index, dialogue in enumerate(dialogues):
        base_ptr = _iptr("$/dialogues" if isinstance(payload, dict) else "$", index)
        dialogue_id = dialogue.get("id")
        if not isinstance(dialogue_id, str) or not dialogue_id.strip():
            collector.error(code="content.dialogues.missing_id", file=file, pointer=_ptr(base_ptr, "id"), message="dialogue id is required")
            continue
        dialogue_id_norm = dialogue_id.strip()
        if dialogue_id_norm in seen_ids:
            collector.error(code="content.dialogues.duplicate_id", file=file, pointer=_ptr(base_ptr, "id"), message=f"duplicate dialogue id '{dialogue_id_norm}'")
        else:
            seen_ids.add(dialogue_id_norm)

        script = dialogue.get("script")
        if not isinstance(script, dict):
            collector.error(code="content.dialogues.invalid_script", file=file, pointer=_ptr(base_ptr, "script"), message="dialogue script must be an object")
            continue

        node_ids = sorted(str(key).strip() for key in script.keys())
        node_set = {node_id for node_id in node_ids if node_id}
        start_node = dialogue.get("start_node")
        if not isinstance(start_node, str) or not start_node.strip():
            collector.error(code="content.dialogues.missing_start", file=file, pointer=_ptr(base_ptr, "start_node"), message="start_node is required")
        elif start_node.strip() not in node_set:
            collector.error(code="content.dialogues.missing_start_node", file=file, pointer=_ptr(base_ptr, "start_node"), message=f"start_node '{start_node.strip()}' does not exist in script")

        for node_name in sorted(script.keys()):
            node = script[node_name]
            node_ptr = _ptr(_ptr(base_ptr, "script"), str(node_name))
            if not isinstance(node, dict):
                collector.error(code="content.dialogues.invalid_node", file=file, pointer=node_ptr, message="dialogue node must be an object")
                continue

            node_next = node.get("next")
            if isinstance(node_next, str) and node_next.strip() and node_next.strip() not in node_set:
                collector.error(code="content.dialogues.invalid_next", file=file, pointer=_ptr(node_ptr, "next"), message=f"next node '{node_next.strip()}' does not exist")

            choices = node.get("choices")
            if choices is not None:
                if not isinstance(choices, list):
                    collector.error(code="content.dialogues.invalid_choices", file=file, pointer=_ptr(node_ptr, "choices"), message="choices must be an array")
                else:
                    for choice_index, choice in enumerate(choices):
                        choice_ptr = _iptr(_ptr(node_ptr, "choices"), choice_index)
                        if not isinstance(choice, dict):
                            collector.error(code="content.dialogues.invalid_choice", file=file, pointer=choice_ptr, message="choice entry must be an object")
                            continue
                        choice_next = choice.get("next")
                        choice_end = bool(choice.get("end", False))
                        if isinstance(choice_next, str) and choice_next.strip() and choice_next.strip() not in node_set:
                            collector.error(code="content.dialogues.invalid_choice_next", file=file, pointer=_ptr(choice_ptr, "next"), message=f"choice next node '{choice_next.strip()}' does not exist")
                        if not choice_end and choice_next is None:
                            collector.warning(code="content.dialogues.choice_terminal", file=file, pointer=choice_ptr, message="choice has no 'next' and no 'end': true")

                        emit_event = choice.get("emit_event")
                        if isinstance(emit_event, str):
                            _add_ref(event_refs, name=emit_event, file=file, pointer=_ptr(choice_ptr, "emit_event"), source="emit_event")
                            emitted_events.add(emit_event.strip())

            _collect_refs(
                node,
                file=file,
                pointer=node_ptr,
                collector=collector,
                event_refs=event_refs,
                emitted_events=emitted_events,
                dialogue_refs=[],
                cutscene_refs=[],
                inline_dialogue_ids=set(),
            )

    return len(seen_ids), seen_ids


def scan_prefabs(
    payload: Any,
    *,
    collector: _Collector,
    event_refs: list[tuple[str, str, str, str]],
    emitted_events: set[str],
    dialogue_refs: list[tuple[str, str, str]],
    cutscene_refs: list[tuple[str, str, str]],
    inline_dialogue_ids: set[str],
) -> tuple[int, set[str]]:
    file = _norm_path(PREFABS_REL)
    prefabs = _as_object_array(payload, file=file, pointer="$", key="prefabs" if isinstance(payload, dict) else None, collector=collector)

    seen_ids: set[str] = set()
    for index, prefab in enumerate(prefabs):
        base_ptr = _iptr("$/prefabs" if isinstance(payload, dict) else "$", index)
        prefab_id = prefab.get("id")
        if not isinstance(prefab_id, str) or not prefab_id.strip():
            collector.error(code="content.prefabs.missing_id", file=file, pointer=_ptr(base_ptr, "id"), message="prefab id is required")
            continue
        prefab_id_norm = prefab_id.strip()
        if prefab_id_norm in seen_ids:
            collector.error(code="content.prefabs.duplicate_id", file=file, pointer=_ptr(base_ptr, "id"), message=f"duplicate prefab id '{prefab_id_norm}'")
        else:
            seen_ids.add(prefab_id_norm)
        if not ID_RE.fullmatch(prefab_id_norm):
            collector.error(code="content.prefabs.invalid_id", file=file, pointer=_ptr(base_ptr, "id"), message=f"prefab id does not match pattern: '{prefab_id_norm}'")

        _collect_refs(
            prefab,
            file=file,
            pointer=base_ptr,
            collector=collector,
            event_refs=event_refs,
            emitted_events=emitted_events,
            dialogue_refs=dialogue_refs,
            cutscene_refs=cutscene_refs,
            inline_dialogue_ids=inline_dialogue_ids,
        )

    return len(seen_ids), seen_ids


def scan_scenes(
    *,
    repo_root: Path,
    loader: _Loader,
    collector: _Collector,
    prefab_ids: set[str],
    event_refs: list[tuple[str, str, str, str]],
    emitted_events: set[str],
    dialogue_refs: list[tuple[str, str, str]],
    cutscene_refs: list[tuple[str, str, str]],
    inline_dialogue_ids: set[str],
) -> int:
    scenes_root = repo_root / SCENES_DIR_REL
    if not scenes_root.exists() or not scenes_root.is_dir():
        collector.error(code="content.scenes.missing_dir", file=_norm_path(SCENES_DIR_REL), pointer="$", message="scenes directory not found")
        return 0

    scene_paths = sorted(path for path in scenes_root.glob("*.json") if path.is_file())
    for scene_path in scene_paths:
        rel_path = scene_path.relative_to(repo_root)
        payload = loader.load_json(rel_path, required=True)
        if payload is None:
            continue

        file = _norm_path(rel_path)
        if not isinstance(payload, dict):
            collector.error(code="content.scenes.invalid_root", file=file, pointer="$", message="scene root must be an object")
            continue

        entities = payload.get("entities", [])
        if entities is None:
            entities = []
        if not isinstance(entities, list):
            collector.error(code="content.scenes.invalid_entities", file=file, pointer="$/entities", message="scene entities must be an array")
            entities = []

        for index, entity in enumerate(entities):
            entity_ptr = _iptr("$/entities", index)
            if not isinstance(entity, dict):
                collector.error(code="content.scenes.invalid_entity", file=file, pointer=entity_ptr, message="entity entry must be an object")
                continue
            prefab_id = entity.get("prefab_id")
            if isinstance(prefab_id, str) and prefab_id.strip() and prefab_id.strip() not in prefab_ids:
                collector.error(code="content.scenes.missing_prefab", file=file, pointer=_ptr(entity_ptr, "prefab_id"), message=f"prefab '{prefab_id.strip()}' not found in {PREFABS_REL.as_posix()}")

        _collect_refs(
            payload,
            file=file,
            pointer="$",
            collector=collector,
            event_refs=event_refs,
            emitted_events=emitted_events,
            dialogue_refs=dialogue_refs,
            cutscene_refs=cutscene_refs,
            inline_dialogue_ids=inline_dialogue_ids,
        )

    return len(scene_paths)

def _validate_reference_sets(
    *,
    collector: _Collector,
    event_refs: list[tuple[str, str, str, str]],
    known_events: set[str],
    dialogue_refs: list[tuple[str, str, str]],
    known_dialogues: set[str],
    cutscene_refs: list[tuple[str, str, str]],
    known_cutscenes: set[str],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    referenced_events = tuple(sorted({name for name, _file, _ptr, _src in event_refs if name}))
    emitted_events = tuple(sorted({name for name, _file, _ptr, source in event_refs if source in {"event", "event_type", "emit_event", "on_enter_event", "on_exit_event", "interact_event", "emit_events_on_complete"}}))

    missing_events = sorted(name for name in referenced_events if name not in known_events)
    missing_event_set = set(missing_events)
    for name, file, pointer, source in sorted(event_refs, key=lambda item: (item[1], item[2], item[0], item[3])):
        if name in missing_event_set:
            collector.error(
                code="content.events.missing_reference",
                file=file,
                pointer=pointer,
                message=f"event '{name}' ({source}) is not defined in {EVENTS_REL.as_posix()}",
            )

    for dialogue_id, file, pointer in sorted(dialogue_refs, key=lambda item: (item[1], item[2], item[0])):
        if dialogue_id and dialogue_id not in known_dialogues:
            collector.error(
                code="content.dialogues.missing_reference",
                file=file,
                pointer=pointer,
                message=f"dialogue_id '{dialogue_id}' is not defined in {DIALOGUES_REL.as_posix()} or inline scripts",
            )

    for cutscene_id, file, pointer in sorted(cutscene_refs, key=lambda item: (item[1], item[2], item[0])):
        if cutscene_id and cutscene_id not in known_cutscenes:
            collector.error(
                code="content.cutscenes.missing_reference",
                file=file,
                pointer=pointer,
                message=f"cutscene_id '{cutscene_id}' is not defined in {CUTSCENES_REL.as_posix()}",
            )

    return emitted_events, referenced_events, tuple(missing_events)


def _apply_minimum_count_ratchets(*, collector: _Collector, stats: dict[str, int], minimum_counts: dict[str, int]) -> None:
    for key in sorted(minimum_counts.keys()):
        threshold = int(minimum_counts[key])
        current = int(stats.get(key, 0))
        if current < threshold:
            collector.error(
                code="content.ratchet.minimum_count",
                file="<stats>",
                pointer=f"$/stats/{key}",
                message=f"{key} count fell below ratchet minimum ({current} < {threshold})",
            )


def run_content_audit(
    repo_root: Path,
    *,
    minimum_counts: dict[str, int] | None = None,
) -> ContentAuditReport:
    resolved_root = Path(repo_root).resolve()
    collector = _Collector()
    loader = _Loader(resolved_root, collector)

    events_payload = loader.load_json(EVENTS_REL, required=True)
    quests_payload = loader.load_json(QUESTS_REL, required=True)
    cutscenes_payload = loader.load_json(CUTSCENES_REL, required=True)
    dialogues_payload = loader.load_json(DIALOGUES_REL, required=True)
    prefabs_payload = loader.load_json(PREFABS_REL, required=True)

    event_refs: list[tuple[str, str, str, str]] = []
    emitted_events_set: set[str] = set()
    dialogue_refs: list[tuple[str, str, str]] = []
    cutscene_refs: list[tuple[str, str, str]] = []
    inline_dialogue_ids: set[str] = set()

    event_count, known_events = scan_events(events_payload, collector=collector)
    quest_count, _ = scan_quests(
        quests_payload,
        collector=collector,
        event_refs=event_refs,
        emitted_events=emitted_events_set,
    )
    cutscene_count, known_cutscenes = scan_cutscenes(
        cutscenes_payload,
        collector=collector,
        event_refs=event_refs,
        emitted_events=emitted_events_set,
        dialogue_refs=dialogue_refs,
        cutscene_refs=cutscene_refs,
        inline_dialogue_ids=inline_dialogue_ids,
    )
    dialogue_count, known_dialogues_from_file = scan_dialogues(
        dialogues_payload,
        collector=collector,
        event_refs=event_refs,
        emitted_events=emitted_events_set,
    )
    prefab_count, known_prefabs = scan_prefabs(
        prefabs_payload,
        collector=collector,
        event_refs=event_refs,
        emitted_events=emitted_events_set,
        dialogue_refs=dialogue_refs,
        cutscene_refs=cutscene_refs,
        inline_dialogue_ids=inline_dialogue_ids,
    )
    scene_count = scan_scenes(
        repo_root=resolved_root,
        loader=loader,
        collector=collector,
        prefab_ids=known_prefabs,
        event_refs=event_refs,
        emitted_events=emitted_events_set,
        dialogue_refs=dialogue_refs,
        cutscene_refs=cutscene_refs,
        inline_dialogue_ids=inline_dialogue_ids,
    )

    known_dialogues = set(known_dialogues_from_file)
    known_dialogues.update(name for name in inline_dialogue_ids if name)

    emitted_events, referenced_events, missing_events = _validate_reference_sets(
        collector=collector,
        event_refs=event_refs,
        known_events=known_events,
        dialogue_refs=dialogue_refs,
        known_dialogues=known_dialogues,
        cutscene_refs=cutscene_refs,
        known_cutscenes=known_cutscenes,
    )

    stats = {
        "events": event_count,
        "quests": quest_count,
        "cutscenes": cutscene_count,
        "dialogues": dialogue_count,
        "prefabs": prefab_count,
        "scenes": scene_count,
        "events_emitted": len(emitted_events),
        "events_referenced": len(referenced_events),
    }

    thresholds = dict(DEFAULT_MINIMUM_COUNTS)
    if minimum_counts is not None:
        thresholds.update({key: int(value) for key, value in minimum_counts.items()})
    _apply_minimum_count_ratchets(collector=collector, stats=stats, minimum_counts=thresholds)

    diagnostics_all = sort_diagnostics(
        tuple(item.to_diagnostic() for item in collector.errors)
        + tuple(item.to_diagnostic() for item in collector.warnings)
    )
    sorted_errors = tuple(
        AuditIssue.from_diagnostic(item)
        for item in diagnostics_all
        if item.level == DiagnosticLevel.ERROR
    )
    sorted_warnings = tuple(
        AuditIssue.from_diagnostic(item)
        for item in diagnostics_all
        if item.level == DiagnosticLevel.WARN
    )
    sorted_digests = tuple(sorted(loader.digests.values(), key=lambda item: item.file))

    return ContentAuditReport(
        schema_version=SCHEMA_VERSION,
        ok=len(sorted_errors) == 0,
        errors=sorted_errors,
        warnings=sorted_warnings,
        stats=stats,
        digests=sorted_digests,
        diagnostics=diagnostics_all,
        events_emitted=tuple(sorted(set(emitted_events))),
        events_referenced=tuple(sorted(set(referenced_events))),
        events_missing=tuple(sorted(set(missing_events))),
    )


def format_content_audit_text(report: ContentAuditReport, *, max_items: int = 20) -> str:
    lines: list[str] = []
    lines.append("Mesh Content Audit Report")
    lines.append(f"Result: {'OK' if report.ok else 'FAILED'}")
    lines.append(f"Schema Version: {report.schema_version}")
    lines.append(f"Errors: {len(report.errors)}")
    lines.append(f"Warnings: {len(report.warnings)}")
    lines.append("")
    lines.append("Stats:")
    for key in sorted(report.stats.keys()):
        lines.append(f"- {key}: {report.stats[key]}")

    lines.append("")
    lines.append("Event Coverage:")
    lines.append(f"- emitted: {len(report.events_emitted)}")
    lines.append(f"- referenced: {len(report.events_referenced)}")
    lines.append(f"- missing: {len(report.events_missing)}")

    if report.events_missing:
        lines.append("- missing sample:")
        for name in report.events_missing[:max_items]:
            lines.append(f"  - {name}")

    if report.errors:
        lines.append("")
        lines.append("Errors (first entries):")
        for item in report.errors[:max_items]:
            lines.append(f"- {item.file}:{item.pointer} [{item.code}] {item.message}")

    if report.warnings:
        lines.append("")
        lines.append("Warnings (first entries):")
        for item in report.warnings[:max_items]:
            lines.append(f"- {item.file}:{item.pointer} [{item.code}] {item.message}")

    lines.append("")
    lines.append("Digests:")
    for digest in report.digests:
        lines.append(f"- {digest.file} sha256={digest.sha256} size={digest.size}")

    return "\n".join(lines) + "\n"


def content_audit_report_to_json(report: ContentAuditReport) -> str:
    return dumps_json_deterministic(report.to_dict(), indent=2, sort_keys=True, trailing_newline=True)
