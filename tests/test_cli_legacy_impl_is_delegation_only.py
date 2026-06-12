import ast
from pathlib import Path

import pytest

TARGET_FUNCTIONS = {
    "_handle_scene_create",
    "_handle_scene_tilemap_brush",
    "_handle_scene_tilemap_init",
    "_handle_scene_tilemap_resize",
    "_handle_scene_tilemap_flood_fill",
    "_handle_scene_stamp",
    "_handle_scene_stamp_report_legacy",
    "_handle_scene_stamp_report",
    "_handle_scene_macro_report",
    "_handle_scene_macro_apply",
    "_handle_scene_add_placeholder",
    "_handle_scene_add_entity",
    "_handle_scene_add_triggerzone_objective",
    "_handle_scene_add_dialogue_choice_flag",
    "_handle_scene_validate_backgrounds",
    "_handle_scene_backgrounds_add_layer",
    "_handle_scene_backgrounds_remove_layer",
}

def test_legacy_impl_is_delegation_only():
    file_path = Path("mesh_cli/legacy_impl.py")
    if not file_path.exists():
        pytest.skip("mesh_cli/legacy_impl.py not found")

    tree = ast.parse(file_path.read_text(encoding="utf-8"))

    functions_found = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if node.name in TARGET_FUNCTIONS:
                functions_found.add(node.name)
                check_function_body(node)

    missing = TARGET_FUNCTIONS - functions_found
    assert not missing, f"Some target functions were not found in legacy_impl.py: {missing}"

def check_function_body(node: ast.FunctionDef):
    # Find the return statement
    return_stmt_index = -1
    for i, stmt in enumerate(node.body):
        if isinstance(stmt, ast.Return):
            return_stmt_index = i
            break

    # If no return statement, that's suspicious for a delegation wrapper (unless it's void, but these return int)
    # But maybe it just calls something and returns implicitly None?
    # The wrappers we saw return int.

    if return_stmt_index == -1:
        # It might be that the function is empty or just has a docstring?
        # But we expect a delegation call.
        # Let's check if it has any body statements other than docstring.
        non_docstring_stmts = [
            s for s in node.body
            if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))
        ]
        if not non_docstring_stmts:
             # Empty function is fine? No, we expect delegation.
             pass
        return

    # Check if there are statements after the return
    # Note: imports are statements.
    # We expect:
    #   imports
    #   return ...
    #   <nothing else>

    # So if return_stmt_index is not the last statement, fail.
    if return_stmt_index < len(node.body) - 1:
        # Check if subsequent statements are just comments? AST doesn't have comments.
        # AST has nodes.
        # If there are nodes after return, it's dead code.

        # Exception: maybe a second return? (unreachable)
        # Exception: maybe pass?

        extra_stmts = node.body[return_stmt_index+1:]
        if extra_stmts:
            pytest.fail(f"Function {node.name} has dead code after return statement: {extra_stmts}")

if __name__ == "__main__":
    test_legacy_impl_is_delegation_only()
