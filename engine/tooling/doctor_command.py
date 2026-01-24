import argparse

from engine.tooling.doctor import DoctorRunner
from engine.tooling.explain import ExplainRunner


def doctor_command(args: argparse.Namespace) -> int:
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
