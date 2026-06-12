from engine.tooling.plan_linter import ACTION_SCHEMAS as LINTER_SCHEMAS
from engine.tooling.plan_schema_command import PLAN_SCHEMA as EXPORT_SCHEMA


def test_plan_schema_sync_guard():
    """
    Ensure the internal linter schema and the exported CLI schema stay in sync.
    
    Checks:
    1. Action keys match exactly.
    2. 'writes_files' metadata matches (defaulting to True if missing).
    3. Argument lists (required/optional) match.
    """

    linter_keys = set(LINTER_SCHEMAS.keys())
    export_keys = set(EXPORT_SCHEMA["actions"].keys())

    # 1. Keys match
    missing_in_export = linter_keys - export_keys
    missing_in_linter = export_keys - linter_keys

    assert not missing_in_export, f"Actions in linter but missing from export schema: {missing_in_export}"
    assert not missing_in_linter, f"Actions in export schema but missing from linter: {missing_in_linter}"

    for action in linter_keys:
        linter_def = LINTER_SCHEMAS[action]
        export_def = EXPORT_SCHEMA["actions"][action]

        # 2. writes_files matches
        # Default is True if not specified
        linter_writes = linter_def.get("writes_files", True)
        export_writes = export_def.get("writes_files", True)

        assert linter_writes == export_writes, (
            f"Action '{action}' writes_files mismatch. "
            f"Linter: {linter_writes}, Export: {export_writes}"
        )

        # 3. Arguments match
        # Linter structure: {"required": [...], "optional": [...]}
        # Export structure: {"args": {"arg_name": {"required": bool, ...}}}

        linter_req = set(linter_def.get("required", []))
        linter_opt = set(linter_def.get("optional", []))

        export_args = export_def.get("args", {})
        export_req = {k for k, v in export_args.items() if v.get("required", False)}
        export_opt = {k for k, v in export_args.items() if not v.get("required", False)}

        # Check required args
        missing_req_export = linter_req - export_req
        extra_req_export = export_req - linter_req
        assert not missing_req_export, f"Action '{action}' required args missing in export: {missing_req_export}"
        assert not extra_req_export, f"Action '{action}' has extra required args in export: {extra_req_export}"

        # Check optional args
        missing_opt_export = linter_opt - export_opt
        extra_opt_export = export_opt - linter_opt
        assert not missing_opt_export, f"Action '{action}' optional args missing in export: {missing_opt_export}"
        assert not extra_opt_export, f"Action '{action}' has extra optional args in export: {extra_opt_export}"
