import argparse
import json

from engine.tooling import plan_schema_command


def test_plan_schema_ai_out_deterministic(capsys):
    """
    Ensure that the schema output is byte-for-byte deterministic.
    This prevents spurious diffs in CI/CD or version control.
    """

    # Run 1
    args = argparse.Namespace(out=None, ai_out=None, verify=False)
    plan_schema_command.plan_schema_command(args)
    out1 = capsys.readouterr().out

    # Run 2
    plan_schema_command.plan_schema_command(args)
    out2 = capsys.readouterr().out

    # Byte-for-byte equality
    assert out1 == out2, "Schema output is not deterministic!"

    # Parse and verify structure
    data = json.loads(out1)

    # 1. Actions are sorted
    actions = list(data["actions"].keys())
    assert actions == sorted(actions), "Actions keys are not sorted!"

    # 2. Args are sorted (if we can check insertion order, but dicts are ordered in modern python)
    # However, json.dumps(sort_keys=True) ensures keys are sorted.
    # Let's verify that sort_keys=True was likely used by checking if keys are sorted in the string output.
    # But we already parsed it.
    # Let's check if the output string matches a sorted dump.

    expected_dump = json.dumps(data, indent=2, sort_keys=True)
    # Normalize newlines just in case
    out1_norm = out1.strip().replace("\r\n", "\n")
    expected_norm = expected_dump.strip().replace("\r\n", "\n")

    assert out1_norm == expected_norm, "Output does not match json.dumps(sort_keys=True)"

    # 3. Check writes_files consistency
    for action, schema in data["actions"].items():
        if "writes_files" in schema:
            assert schema["writes_files"] is False, "writes_files should only be present if False (or check logic)"
            # Actually, our logic adds it if False. If True, it's omitted.
            # So if present, it must be False.
