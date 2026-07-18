"""Selection -> display-label rename request for Creator Mode."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

DISPLAY_LABEL_FIELD = "name"
MAX_DISPLAY_LABEL_LENGTH = 80


@dataclass(frozen=True, slots=True)
class CreatorEntityRenameRequest:
    """Canonical display-label rename request."""

    ok: bool
    entity_id: str = ""
    current_label: str = ""
    proposed_label: str = ""
    source_scene: str = ""
    label_field: str = DISPLAY_LABEL_FIELD
    reason: str = ""

    @property
    def available(self) -> bool:
        return bool(self.ok)


def normalize_display_label(value: object) -> str:
    """Trim user-facing label boundaries while preserving internal text."""

    return str(value or "").strip()


def validate_display_label(
    proposed_label: object,
    *,
    current_label: object = "",
) -> str:
    """Return an empty string when a proposed display label is valid."""

    proposed = normalize_display_label(proposed_label)
    current = normalize_display_label(current_label)
    if not proposed:
        return "Enter a display label."
    if proposed == current:
        return "The new label matches the current label."
    if len(proposed) > MAX_DISPLAY_LABEL_LENGTH:
        return "The label is too long."
    if any(_unsupported_control_character(ch) for ch in proposed):
        return "The label contains unsupported characters."
    return ""


def build_creator_entity_rename_request(
    selected: Mapping[str, Any] | None,
    *,
    source_scene: str,
    proposed_label: object,
) -> CreatorEntityRenameRequest:
    """Build a display-label rename request from the selected authored entity."""

    if selected is None:
        return CreatorEntityRenameRequest(ok=False, reason="No entity is selected.")

    if not isinstance(selected, Mapping):
        return CreatorEntityRenameRequest(ok=False, reason="Selection is not an authored entity.")

    entity_id = _stable_entity_id(selected)
    if not entity_id:
        return CreatorEntityRenameRequest(
            ok=False,
            reason="Selected entity has no stable authored identity.",
        )

    if _is_runtime_or_helper(selected):
        return CreatorEntityRenameRequest(
            ok=False,
            entity_id=entity_id,
            reason="Selected entity is not part of the authored scene.",
        )

    current_label = _display_label(selected)
    if current_label is None:
        return CreatorEntityRenameRequest(
            ok=False,
            entity_id=entity_id,
            reason="This entity does not expose an editable display label.",
        )

    if any(_unsupported_control_character(ch) for ch in current_label):
        return CreatorEntityRenameRequest(
            ok=False,
            entity_id=entity_id,
            reason="Current display label is malformed.",
        )

    scene = str(source_scene or "").strip()
    if not scene:
        return CreatorEntityRenameRequest(
            ok=False,
            entity_id=entity_id,
            current_label=current_label,
            reason="Current scene path is unavailable.",
        )

    proposed = normalize_display_label(proposed_label)
    reason = validate_display_label(proposed, current_label=current_label)
    if reason:
        return CreatorEntityRenameRequest(
            ok=False,
            entity_id=entity_id,
            current_label=current_label,
            proposed_label=proposed,
            source_scene=scene,
            reason=reason,
        )

    return CreatorEntityRenameRequest(
        ok=True,
        entity_id=entity_id,
        current_label=current_label,
        proposed_label=proposed,
        source_scene=scene,
    )


def creator_entity_rename_request_key(request: CreatorEntityRenameRequest) -> str:
    """Stable duplicate-staging key for one display-label rename request."""

    if not request.ok:
        return ""
    return "|".join(
        (
            request.source_scene,
            request.entity_id,
            request.label_field,
            request.current_label,
            request.proposed_label,
        )
    )


def _stable_entity_id(selected: Mapping[str, Any]) -> str:
    """Return only identity fields that remain distinct from display label."""

    for key in ("id", "entity_id"):
        value = selected.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _display_label(selected: Mapping[str, Any]) -> str | None:
    value = selected.get(DISPLAY_LABEL_FIELD)
    if not isinstance(value, str):
        return None
    return value


def _unsupported_control_character(ch: str) -> bool:
    if ch in ("\t", "\n", "\r"):
        return True
    return ord(ch) < 32 or ord(ch) == 127


def _is_runtime_or_helper(selected: Mapping[str, Any]) -> bool:
    if bool(selected.get("_runtime_generated")) or bool(selected.get("runtime_generated")):
        return True
    if bool(selected.get("_editor_only")) or bool(selected.get("editor_only")):
        return True
    kind = str(selected.get("kind") or selected.get("_kind") or "").strip().lower()
    if kind in {"runtime", "helper", "marker", "editor_helper"}:
        return True
    tags = selected.get("tags")
    if isinstance(tags, (list, tuple)) and "editor_helper" in tags:
        return True
    return False
