from engine.tooling.plan_linter import ACTION_SCHEMAS
from engine.tooling.plan_schema_command import METADATA, NO_METADATA_ACTIONS


def test_plan_schema_metadata_coverage():
    """
    Enforce that all actions in the linter schema have corresponding metadata
    (description, arg types) for external documentation/schema generation.
    """

    for action, schema in ACTION_SCHEMAS.items():
        # 1. Existence check
        if action in NO_METADATA_ACTIONS:
            continue

        assert action in METADATA, f"Action '{action}' missing from METADATA in plan_schema_command.py"

        meta = METADATA[action]

        # 2. Description check
        assert meta.get("description"), f"Action '{action}' missing description in METADATA"

        # 3. Argument coverage check
        # We require that all REQUIRED args in the linter schema have type definitions in metadata.
        # Optional args are good to have but we enforce required at minimum.

        required_args = set(schema.get("required", []))
        arg_types = meta.get("arg_types", {})

        missing_args = required_args - set(arg_types.keys())
        assert not missing_args, f"Action '{action}' missing metadata for required args: {missing_args}"

        # 4. Typo check
        # Ensure metadata doesn't define args that don't exist in the schema (required or optional)
        all_schema_args = required_args | set(schema.get("optional", []))
        extra_meta_args = set(arg_types.keys()) - all_schema_args

        assert not extra_meta_args, f"Action '{action}' has metadata for unknown args: {extra_meta_args}"
