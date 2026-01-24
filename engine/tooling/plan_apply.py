from __future__ import annotations

import argparse


def apply_plan(
    *,
    plan_path: str,
    ai_safe: bool = False,
    dry_run: bool = False,
    no_lint: bool = False,
    run_tests: bool = False,
) -> int:
    """Shared apply-plan entrypoint for pipeline/orchestrators (delegates to CLI implementation)."""
    import mesh_cli

    args = argparse.Namespace(
        command="apply-plan",
        plan_path=plan_path,
        ai_safe=ai_safe,
        dry_run=dry_run,
        no_lint=no_lint,
        run_tests=run_tests,
    )
    return int(mesh_cli._handle_apply_plan(args))

