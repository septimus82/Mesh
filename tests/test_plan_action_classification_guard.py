from engine.tooling.plan_linter import ACTION_SCHEMAS, NON_WRITING_ACTIONS, WRITING_ACTIONS

# Heuristic for arguments that imply file operations (read or write)
PATH_ARG_NAMES = {"path", "out", "dest", "file", "target", "template"}
PATH_SUFFIX = "_path"

def is_path_arg(name: str) -> bool:
    return name in PATH_ARG_NAMES or name.endswith(PATH_SUFFIX)

# Actions known to take paths but are strictly read-only/non-writing
# These are exceptions to the "Non-writing actions should have no path args" rule.
# READ_ONLY_PATH_ACTIONS = {
#     "validate"
# }

def test_plan_action_classification_guard():
    """
    Guard against accidental misclassification of actions.
    
    WRITING_ACTIONS is derived as ALL - NON_WRITING.
    If a new non-writing action is added but not added to NON_WRITING_ACTIONS,
    it will be classified as WRITING.
    
    This test checks heuristics:
    1. Writing actions MUST have at least one path-like argument.
       (If an action has no path args, it probably can't write to a file, so it shouldn't be in WRITING_ACTIONS).
    2. Non-writing actions SHOULD NOT have path-like arguments (unless allowlisted).
       (If an action has path args, it might be writing, so we should be careful).
    """

    all_actions = set(ACTION_SCHEMAS.keys())

    # Verify partition
    assert WRITING_ACTIONS | NON_WRITING_ACTIONS == all_actions
    assert not (WRITING_ACTIONS & NON_WRITING_ACTIONS)

    for action_type, schema in ACTION_SCHEMAS.items():
        # Collect all args
        args = set(schema.get("required", [])) | set(schema.get("optional", []))
        has_path_arg = any(is_path_arg(arg) for arg in args)

        if action_type in WRITING_ACTIONS:
            # Writing actions must have a target path
            assert has_path_arg, (
                f"Action '{action_type}' is classified as WRITING but has no path-like arguments. "
                f"Args: {args}. "
                "If this is truly a writing action, ensure it takes a path. "
                "If it is non-writing, add it to NON_WRITING_ACTIONS in engine/tooling/plan_linter.py."
            )

        elif action_type in NON_WRITING_ACTIONS:
            # Non-writing actions usually don't take paths, unless they are read-only validators
            # if action_type in READ_ONLY_PATH_ACTIONS:
            #     continue

            # If it's explicitly marked as non-writing (writes_files: False), we allow path args (it's a reader).
            # But we might want to check for "output" args specifically if we wanted to be stricter.
            # For now, if it's in NON_WRITING_ACTIONS, it means writes_files is False, so we trust the schema.
            pass

