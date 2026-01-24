"""AI Bundle generator."""
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from engine.ai_audit import build_audit_report
from engine.tooling_runtime.ai_context_exporter import export_ai_context
from engine.tooling_runtime.ai_plan_command import generate_ai_schema, generate_plan_skeleton
from engine.version import ENGINE_VERSION


def build_ai_bundle(scene_paths: List[Path], goal: str) -> Dict[str, Any]:
    """
    Builds a comprehensive AI bundle containing schema, context, audit, and plan skeleton.
    """
    # 1. Schema
    schema = generate_ai_schema()

    # 2. Context
    context = export_ai_context(scene_paths)

    # 3. Audit (Scoped)
    audit_report = build_audit_report(scene_paths)
    audit = asdict(audit_report)

    # 4. Plan Skeleton
    plan_skeleton = generate_plan_skeleton(goal)

    # 5. Meta
    meta = {
        "bundle_id": f"bundle_{int(datetime.now(timezone.utc).timestamp())}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "engine_version": ENGINE_VERSION
    }

    return {
        "meta": meta,
        "goal": goal,
        "schema": schema,
        "context": context,
        "audit": audit,
        "plan_skeleton": plan_skeleton
    }
