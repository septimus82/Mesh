import argparse

from engine.tooling import health_defaults
from engine.tooling.doctor import DoctorRunner
from engine.tooling.explain import ExplainRunner


def _fix_health_defaults(world: str | None) -> int:
    """``--fix-health-defaults``: the one thing doctor writes, and only when asked (#651, owner decision D12)."""
    from engine.editor import project_ownership  # noqa: PLC0415

    target, err = DoctorRunner()._resolve_target_path(world)
    if err or target is None:
        print(f"[DOCTOR] {err}")
        return 1
    try:
        fixed = health_defaults.fix(target)
    except (project_ownership.OwnedElsewhere, project_ownership.OwnershipUnavailable) as exc:
        print("[DOCTOR] " + project_ownership.refused_write(f"mesh doctor {health_defaults.FIX_FLAG}", exc))
        return 1
    for finding in fixed:
        print(f"[DOCTOR] Fixed {finding.file}: {finding.entity}'s {finding.behaviour} (dropped {', '.join(finding.drop)})")
    print(f"[DOCTOR] {len(fixed)} setting(s) fixed" + (" (originals under .mesh/backups/)" if fixed else ""))
    return 0


def doctor_command(args: argparse.Namespace) -> int:
    if getattr(args, "fix_health_defaults", False):
        return _fix_health_defaults(getattr(args, "world", None))
    runner = DoctorRunner()
    result = runner.run_result(world=getattr(args, "world", None))
    code = int(result.exit_code)
    report = result.to_doctor_report_dict()

    explainer = ExplainRunner()
    if code != 0:
        explainer.store_last_failure(result)

    if bool(getattr(args, "explain", False)):
        output = explainer.explain_result(result, json_output=bool(getattr(args, "json", False)))
    else:
        artifacts = []
        if code != 0:
            artifacts.append(str(explainer._last_failure_path).replace("\\", "/"))

        output = runner.format_report(
            report,
            quiet=bool(getattr(args, "quiet", False)),
            json_output=bool(getattr(args, "json", False)),
            artifacts=artifacts,
        )

    print(output, end="")
    return int(code)
