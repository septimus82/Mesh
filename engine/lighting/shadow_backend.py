from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class ShadowBackendDecision:
    name: str
    reason: str
    fallbacks: list[str]
    ok: bool


@dataclass(frozen=True, slots=True)
class ShadowPipeline:
    texture: Any
    fbo: Any
    decision: ShadowBackendDecision
    activate_cm: Any | None


def choose_shadow_backend(
    env: Mapping[str, str] | None,
    flags: Mapping[str, Any] | None,
    capabilities: Mapping[str, Any],
) -> ShadowBackendDecision:
    # Keep ordering deterministic and identical to prior behavior.
    has_use = bool(capabilities.get("has_use"))
    has_activate = bool(capabilities.get("has_activate"))

    if has_use:
        return ShadowBackendDecision(
            name="fbo.use",
            reason="fbo.use available",
            fallbacks=["fbo.activate", "none"],
            ok=True,
        )
    if has_activate:
        return ShadowBackendDecision(
            name="fbo.activate",
            reason="fbo.activate available",
            fallbacks=["none"],
            ok=True,
        )
    return ShadowBackendDecision(
        name="none",
        reason="fbo has no use/activate",
        fallbacks=[],
        ok=False,
    )


def build_shadow_pipeline(
    decision: ShadowBackendDecision,
    *,
    texture: Any,
    fbo: Any,
) -> ShadowPipeline:
    activate_cm: Any | None = None
    if decision.name == "fbo.use":
        use = getattr(fbo, "use", None)
        if not callable(use):
            raise RuntimeError("fbo.use unavailable")
        use()
    elif decision.name == "fbo.activate":
        activate = getattr(fbo, "activate", None)
        if not callable(activate):
            raise RuntimeError("fbo.activate unavailable")
        activate_cm = activate()
        enter = getattr(activate_cm, "__enter__", None) if activate_cm is not None else None
        if callable(enter):
            enter()
    elif decision.name != "none":
        raise ValueError(f"unknown shadow backend: {decision.name}")
    return ShadowPipeline(texture=texture, fbo=fbo, decision=decision, activate_cm=activate_cm)


def decision_to_diagnostics(decision: ShadowBackendDecision) -> dict[str, object]:
    return {
        "schema_version": 1,
        "selected": str(decision.name),
        "reason": str(decision.reason),
        "fallbacks": list(decision.fallbacks),
    }

