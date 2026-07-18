"""Selection -> authored alpha/opacity request for Creator Mode."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

ALPHA_FIELD = "alpha"
ALPHA_MIN = 0.0
ALPHA_MAX = 1.0


@dataclass(frozen=True, slots=True)
class CreatorEntityAlphaState:
    """Authored/effective alpha state for one entity."""

    present: bool
    authored_value: float | None
    effective_value: float

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "present": bool(self.present),
            "effective": float(self.effective_value),
        }
        if self.present:
            payload["value"] = float(self.authored_value if self.authored_value is not None else self.effective_value)
        return payload


@dataclass(frozen=True, slots=True)
class CreatorEntityOpacityRequest:
    """Canonical opacity request for staging a narrow alpha proposal."""

    ok: bool
    entity_id: str = ""
    entity_label: str = ""
    source_scene: str = ""
    current_alpha: CreatorEntityAlphaState | None = None
    proposed_alpha: float = 1.0
    draft_text: str = ""
    reason: str = ""

    @property
    def available(self) -> bool:
        return bool(self.ok)


def normalize_alpha(value: object) -> float | None:
    """Return canonical alpha in 0..1, or None for malformed input."""

    if isinstance(value, bool):
        return None
    try:
        alpha = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(alpha):
        return None
    if alpha < ALPHA_MIN or alpha > ALPHA_MAX:
        return None
    return round(alpha, 6)


def resolve_alpha_state(selected: Mapping[str, Any]) -> CreatorEntityAlphaState | None:
    """Resolve authored alpha while preserving omission versus explicit value."""

    if ALPHA_FIELD not in selected:
        return CreatorEntityAlphaState(present=False, authored_value=None, effective_value=1.0)
    alpha = normalize_alpha(selected.get(ALPHA_FIELD))
    if alpha is None:
        return None
    return CreatorEntityAlphaState(present=True, authored_value=alpha, effective_value=alpha)


def format_opacity_percent(alpha: float) -> str:
    """Format an alpha value as a whole percentage for the overlay."""

    return f"{int(round(float(alpha) * 100.0))}%"


def alpha_to_draft_percent(alpha: float) -> str:
    """Return the editable percentage draft for an alpha value."""

    percent = Decimal(str(round(float(alpha), 6))) * Decimal("100")
    normalized = percent.quantize(Decimal("0.001")).normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def parse_opacity_percent_draft(text: object) -> tuple[float | None, str]:
    """Parse a percentage draft without clamping or truncating."""

    raw = str(text if text is not None else "").strip()
    if not raw:
        return None, "Enter an opacity from 0% to 100%."
    if raw.endswith("%"):
        raw = raw[:-1].strip()
    try:
        percent = Decimal(raw)
    except InvalidOperation:
        return None, "Enter an opacity from 0% to 100%."
    if not percent.is_finite():
        return None, "Enter an opacity from 0% to 100%."
    if percent < Decimal("0"):
        return None, "Opacity cannot be below 0%."
    if percent > Decimal("100"):
        return None, "Opacity cannot exceed 100%."
    alpha = percent / Decimal("100")
    return normalize_alpha(float(alpha)), ""


def validate_opacity_draft(text: object, *, current_alpha: float) -> str:
    """Return an empty string when a proposed percentage is valid and changed."""

    proposed, reason = parse_opacity_percent_draft(text)
    if reason:
        return reason
    if proposed is None:
        return "Enter an opacity from 0% to 100%."
    if proposed == normalize_alpha(current_alpha):
        return "The proposed opacity matches the current opacity."
    return ""


def build_creator_entity_opacity_request(
    selected: Mapping[str, Any] | None,
    *,
    source_scene: str,
    draft_percent: object,
) -> CreatorEntityOpacityRequest:
    """Build an opacity request from the selected authored entity."""

    if selected is None:
        return CreatorEntityOpacityRequest(ok=False, reason="Select one authored entity.")
    if not isinstance(selected, Mapping):
        return CreatorEntityOpacityRequest(ok=False, reason="Selection is not an authored entity.")

    entity_id = _stable_entity_id(selected)
    if not entity_id:
        return CreatorEntityOpacityRequest(
            ok=False,
            reason="This entity has no stable authored ID.",
        )
    if _is_runtime_or_helper(selected):
        return CreatorEntityOpacityRequest(
            ok=False,
            entity_id=entity_id,
            reason="Selected entity is not part of the authored scene.",
        )

    alpha_state = resolve_alpha_state(selected)
    if alpha_state is None:
        return CreatorEntityOpacityRequest(
            ok=False,
            entity_id=entity_id,
            reason="This entity's opacity value is malformed.",
        )

    scene = str(source_scene or "").strip()
    if not scene:
        return CreatorEntityOpacityRequest(
            ok=False,
            entity_id=entity_id,
            current_alpha=alpha_state,
            reason="Current scene path is unavailable.",
        )

    proposed, parse_reason = parse_opacity_percent_draft(draft_percent)
    if parse_reason:
        return CreatorEntityOpacityRequest(
            ok=False,
            entity_id=entity_id,
            entity_label=_entity_label(selected, entity_id),
            source_scene=scene,
            current_alpha=alpha_state,
            draft_text=str(draft_percent or ""),
            reason=parse_reason,
        )
    if proposed is None:
        return CreatorEntityOpacityRequest(
            ok=False,
            entity_id=entity_id,
            source_scene=scene,
            current_alpha=alpha_state,
            draft_text=str(draft_percent or ""),
            reason="Enter an opacity from 0% to 100%.",
        )
    reason = validate_opacity_draft(draft_percent, current_alpha=alpha_state.effective_value)
    if reason:
        return CreatorEntityOpacityRequest(
            ok=False,
            entity_id=entity_id,
            entity_label=_entity_label(selected, entity_id),
            source_scene=scene,
            current_alpha=alpha_state,
            proposed_alpha=proposed,
            draft_text=str(draft_percent or ""),
            reason=reason,
        )

    return CreatorEntityOpacityRequest(
        ok=True,
        entity_id=entity_id,
        entity_label=_entity_label(selected, entity_id),
        source_scene=scene,
        current_alpha=alpha_state,
        proposed_alpha=proposed,
        draft_text=str(draft_percent or ""),
    )


def creator_entity_opacity_request_key(request: CreatorEntityOpacityRequest) -> str:
    """Stable duplicate-staging key for one opacity request."""

    if not request.ok or request.current_alpha is None:
        return ""
    current = request.current_alpha
    return "|".join(
        (
            request.source_scene,
            request.entity_id,
            "present" if current.present else "absent",
            "" if current.authored_value is None else f"{current.authored_value:.6f}",
            f"{current.effective_value:.6f}",
            f"{request.proposed_alpha:.6f}",
        )
    )


def _stable_entity_id(selected: Mapping[str, Any]) -> str:
    for key in ("id", "entity_id"):
        value = selected.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _entity_label(selected: Mapping[str, Any], entity_id: str) -> str:
    for key in ("name", "mesh_name", "id", "entity_id"):
        value = selected.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return entity_id


def _is_runtime_or_helper(selected: Mapping[str, Any]) -> bool:
    if bool(selected.get("_runtime_generated")) or bool(selected.get("runtime_generated")):
        return True
    if bool(selected.get("_editor_only")) or bool(selected.get("editor_only")):
        return True
    kind = str(selected.get("kind") or selected.get("_kind") or "").strip().lower()
    if kind in {"runtime", "helper", "marker", "editor_helper"}:
        return True
    tags = selected.get("tags")
    return isinstance(tags, (list, tuple)) and "editor_helper" in tags
